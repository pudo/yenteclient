"""Live integration tests against a real yente instance.

Gated on ``OPENSANCTIONS_API_KEY`` being present (see ``live_client`` fixture).
Run locally with ``pytest -m live``; CI runs them in a separate job that's
gated on the secret being available (which excludes PRs from forks).

Kept deliberately small — these are smoke tests, not a comprehensive suite.
They double as a drift detector for the hosted API's response shapes.
"""

from __future__ import annotations

import pytest

from yente_client.entities import Person
from yente_client.models import (
    AlgorithmsResponse,
    CatalogResponse,
    MatchResponse,
    SearchResponse,
    StatusResponse,
)

pytestmark = pytest.mark.live


def test_healthz_returns_ok(live_client) -> None:
    r = live_client.healthz()
    assert isinstance(r, StatusResponse)
    assert r.status == "ok"


def test_catalog_returns_datasets(live_client) -> None:
    r = live_client.catalog()
    assert isinstance(r, CatalogResponse)
    assert len(r.datasets) > 0


def test_algorithms_includes_best_resolver(live_client) -> None:
    r = live_client.algorithms()
    assert isinstance(r, AlgorithmsResponse)
    # `best` is set by the server; ensure it's a non-empty string we can pass back.
    assert r.best
    assert isinstance(r.best, str)


def test_match_known_sanctioned_person(live_client) -> None:
    """Aleksandr Zacharov is a long-standing OFAC SDN entry; a high-confidence
    match here is the integration check that match() actually works."""
    hits = live_client.match(
        Person(firstName="Aleksandr", lastName="Zacharov", birthDate="1965"),
        datasets=["sanctions"],
    )
    assert isinstance(hits, MatchResponse)
    assert hits.top is not None
    assert hits.top.score > 0.7
    # Should be flagged as a screening target.
    assert hits.top.target is True


def test_search_returns_results(live_client) -> None:
    r = live_client.search("acme", datasets=["default"], limit=5)
    assert isinstance(r, SearchResponse)
    assert r.limit == 5


async def test_async_match_known_sanctioned_person(live_async_client) -> None:
    """Mirror of the sync match test, run through the async path."""
    hits = await live_async_client.match(
        Person(firstName="Aleksandr", lastName="Zacharov", birthDate="1965"),
        datasets=["sanctions"],
    )
    assert isinstance(hits, MatchResponse)
    assert hits.top is not None
    assert hits.top.score > 0.7
    assert hits.top.target is True


async def test_async_healthz_returns_ok(live_async_client) -> None:
    r = await live_async_client.healthz()
    assert isinstance(r, StatusResponse)
    assert r.status == "ok"
