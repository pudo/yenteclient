"""Synchronous yente / OpenSanctions client.

Endpoint methods (match, search, fetch, …) land in subsequent M2 phases.
This module ships the constructor, the request/error plumbing, and the
context-manager protocol — everything endpoints will share.
"""

from __future__ import annotations

import warnings
from typing import Any, Self

import httpx

from ._http import build_user_agent, raise_for_response, validate_app_name
from .exceptions import TransportError

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
