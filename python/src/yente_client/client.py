"""Synchronous yente / OpenSanctions client.

Endpoint methods (match, search, fetch, …) land in subsequent M2 phases.
This module ships the constructor, the request/error plumbing, and the
context-manager protocol — everything endpoints will share.
"""

from __future__ import annotations

import warnings
from typing import Any, Final, Self, overload
from urllib.parse import quote

import httpx

from ._http import build_user_agent, raise_for_response, validate_app_name
from ._translation import merge_filters, serialise_match_filters, serialise_search_filters
from .entities import EntityInput
from .exceptions import TransportError
from .filters import MatchFilters, SearchFilters
from .models import (
    AdjacentPropertyResponse,
    AdjacentResponse,
    AlgorithmsResponse,
    CatalogResponse,
    Entity,
    MatchResponse,
    SearchResponse,
    StatusResponse,
)

BEST_ALGORITHM: Final[str] = "best"
"""Canonical algorithm name resolving to whichever scoring algorithm the
server currently recommends. Stable across algorithm version bumps — pass
``algorithm=BEST_ALGORITHM`` for forward-compatibility."""

_HOSTED_HOSTS = ("api.opensanctions.org", "api.test.opensanctions.org")


class Client:
    """Synchronous client for the yente / OpenSanctions API.

    Use as a context manager for deterministic cleanup of the underlying
    ``httpx.Client``. See the design doc §4.6 for the full constructor
    contract.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = "https://api.opensanctions.org",
        app_name: str | None = None,
        user_agent: str | None = None,
        timeout: float | httpx.Timeout | None = None,
        verify: bool | str = True,
        proxy: str | None = None,
        headers: dict[str, str] | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if app_name is not None:
            validate_app_name(app_name)

        if api_key is None and self._looks_hosted(base_url):
            warnings.warn(
                "Client constructed against the hosted OpenSanctions API without an "
                "api_key. Set api_key= or pass OPENSANCTIONS_API_KEY via env.",
                stacklevel=2,
            )

        # Caller's headers go in first; ours (Authorization, User-Agent) win.
        merged_headers: dict[str, str] = dict(headers or {})
        if api_key:
            merged_headers["Authorization"] = f"ApiKey {api_key}"
        merged_headers["User-Agent"] = build_user_agent(app_name=app_name, override=user_agent)

        client_kwargs: dict[str, Any] = {
            "base_url": base_url.rstrip("/"),
            "headers": merged_headers,
            "timeout": timeout or httpx.Timeout(30.0, connect=10.0),
            "follow_redirects": True,
            "verify": verify,
        }
        if proxy is not None:
            client_kwargs["proxy"] = proxy
        # If the caller provided a transport (typically respx.MockTransport for
        # tests), use it verbatim. Otherwise stack httpx's connection-level
        # retries so DNS / connection-refused failures get a free retry.
        client_kwargs["transport"] = transport or httpx.HTTPTransport(retries=2)

        self._http = httpx.Client(**client_kwargs)
        self._base_url = base_url

    @staticmethod
    def _looks_hosted(base_url: str) -> bool:
        return any(host in base_url for host in _HOSTED_HOSTS)

    @property
    def user_agent(self) -> str:
        """The User-Agent header this client sends on every request."""
        return self._http.headers["User-Agent"]

    def close(self) -> None:
        """Close the underlying ``httpx.Client``."""
        self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        """Issue one HTTP request; map errors and decode JSON.

        Caller passes ``params=`` / ``json=`` / etc. as for ``httpx.Client.request``.
        Returns parsed JSON on 2xx; raises an ``APIError`` subclass on non-2xx
        and ``TransportError`` on connection-level failure.
        """
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TransportError as exc:
            raise TransportError(str(exc)) from exc

        if not response.is_success:
            raise_for_response(response)

        return response.json()

    # ----- system / health endpoints -----

    def healthz(self) -> StatusResponse:
        """Liveness check. ``{"status": "ok"}`` whenever the server is up.

        Useful for Kubernetes liveness probes. See ``readyz()`` for index
        readiness.
        """
        return StatusResponse.model_validate(self._request("GET", "/healthz"))

    def readyz(self) -> StatusResponse:
        """Readiness check: confirms the search index is ready to serve queries.

        Returns the same shape as ``healthz()`` but the server returns 503 (which
        we map to ``ServerError``) until the index is loaded.
        """
        return StatusResponse.model_validate(self._request("GET", "/readyz"))

    # ----- catalog / introspection -----

    def catalog(self) -> CatalogResponse:
        """Return the catalog of indexed datasets and their freshness state."""
        return CatalogResponse.model_validate(self._request("GET", "/catalog"))

    def algorithms(self) -> AlgorithmsResponse:
        """Return the list of enabled matching algorithms with their defaults."""
        return AlgorithmsResponse.model_validate(self._request("GET", "/algorithms"))

    # ----- entity fetch -----

    def fetch(self, entity_id: str, *, nested: bool = True) -> Entity:
        """Fetch a single entity by ID.

        Follows ``308`` redirects transparently when the supplied ID is a
        referent of a canonical entity (`follow_redirects=True` is set on the
        httpx client). Pass ``nested=False`` for a lighter response that
        omits adjacent entities like sanctions and ownership links.
        """
        params = {"nested": "true" if nested else "false"}
        path = f"/entities/{quote(entity_id, safe='')}"
        return Entity.model_validate(self._request("GET", path, params=params))

    @overload
    def adjacent(
        self,
        entity_id: str,
        *,
        prop: None = None,
        limit: int | None = None,
        offset: int = 0,
        sort: list[str] | None = None,
    ) -> AdjacentResponse: ...

    @overload
    def adjacent(
        self,
        entity_id: str,
        *,
        prop: str,
        limit: int | None = None,
        offset: int = 0,
        sort: list[str] | None = None,
    ) -> AdjacentPropertyResponse: ...

    def adjacent(
        self,
        entity_id: str,
        *,
        prop: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        sort: list[str] | None = None,
    ) -> AdjacentResponse | AdjacentPropertyResponse:
        """Paginated adjacency for an entity.

        Without ``prop``: returns the full adjacency map keyed by property
        name. With ``prop``: returns paginated results for that one property.
        """
        params: dict[str, Any] = {"offset": offset}
        if limit is not None:
            params["limit"] = limit
        if sort:
            params["sort"] = sort

        eid = quote(entity_id, safe="")
        if prop is None:
            raw = self._request("GET", f"/entities/{eid}/adjacent", params=params)
            return AdjacentResponse.model_validate(raw)
        path = f"/entities/{eid}/adjacent/{quote(prop, safe='')}"
        return AdjacentPropertyResponse.model_validate(self._request("GET", path, params=params))

    # ----- search -----

    def search(
        self,
        q: str,
        *,
        filters: SearchFilters | None = None,
        limit: int | None = None,
        offset: int = 0,
        sort: list[str] | None = None,
        fuzzy: bool = False,
        simple: bool = False,
        facets: list[str] | None = None,
        **filter_kwargs: Any,
    ) -> SearchResponse:
        """Full-text search across one or more datasets.

        Pass filter fields either via ``filters=SearchFilters(...)`` or as
        kwargs (``datasets=[...]``, ``schema=``, ``countries=[...]``, …).
        Kwargs win over a passed-in filters object on the fields they specify.

        The ``datasets`` filter is translated to the v1 wire as
        ``/search/<first-dataset>`` with the rest passed as repeated
        ``include_dataset`` query params; see §4.8.
        """
        f = merge_filters(SearchFilters, filters, filter_kwargs)
        dataset, params = serialise_search_filters(f)

        params["q"] = q
        params["offset"] = offset
        if limit is not None:
            params["limit"] = limit
        if sort:
            params["sort"] = sort
        if fuzzy:
            params["fuzzy"] = "true"
        if simple:
            params["simple"] = "true"
        if facets:
            params["facets"] = facets

        return SearchResponse.model_validate(
            self._request("GET", f"/search/{quote(dataset, safe='')}", params=params)
        )

    # ----- match -----

    def match(
        self,
        entity: EntityInput,
        *,
        filters: MatchFilters | None = None,
        threshold: float | None = None,
        algorithm: str | None = None,
        weights: dict[str, float] | None = None,
        config: dict[str, Any] | None = None,
        limit: int | None = None,
        **filter_kwargs: Any,
    ) -> MatchResponse:
        """Query-by-example match against a dataset.

        Constructs a single-query payload on the v1 wire (``queries={"q":
        entity.to_payload()}``) and unwraps the response into a flat
        ``MatchResponse``. The unwrap is the one structural difference from
        v2's planned shape (§4.8): swap it out when ``/v2/match`` ships.

        Pass filter fields either via ``filters=MatchFilters(...)`` or as
        kwargs (``datasets=[...]``, ``topics=[...]``, ``exclude_entities=[...]``).
        Kwargs win over a passed-in filters object on the fields they specify.

        ``algorithm`` is a string — common values are ``"best"`` (the
        canonical default; ``BEST_ALGORITHM`` exposed at module level),
        ``"logic-v2"``, ``"name-matcher"``. The full set is dynamic and can
        be retrieved via ``client.algorithms()``.
        """
        f = merge_filters(MatchFilters, filters, filter_kwargs)
        dataset, params = serialise_match_filters(f)

        if threshold is not None:
            params["threshold"] = threshold
        if algorithm is not None:
            params["algorithm"] = algorithm
        if limit is not None:
            params["limit"] = limit

        body: dict[str, Any] = {
            "queries": {"q": entity.to_payload()},
            "weights": weights or {},
            "config": config or {},
        }

        raw = self._request("POST", f"/match/{quote(dataset, safe='')}", params=params, json=body)

        return MatchResponse.model_validate(_unwrap_match_response(raw))


def _unwrap_match_response(raw: dict[str, Any]) -> dict[str, Any]:
    """Translate the v1 ``{responses: {q: {...}}, limit: N}`` envelope into
    the v2-shaped flat ``{query, results, total, limit}`` MatchResponse takes."""
    inner = raw["responses"]["q"]
    return {
        "query": inner["query"],
        "results": inner["results"],
        "total": inner["total"],
        "limit": raw["limit"],
    }
