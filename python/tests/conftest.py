"""Shared test fixtures: testdata loader and a helper to build a Client with a stubbed transport."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest

from yente_client.client import Client

# Top-level testdata/ at the repo root, shared with the future TS SDK.
TESTDATA_DIR = Path(__file__).resolve().parent.parent.parent / "testdata"


@pytest.fixture
def load_fixture() -> Callable[[str], dict]:
    """Return a callable that loads ``testdata/<name>.json`` and returns it as a dict."""

    def _load(name: str) -> dict:
        return json.loads((TESTDATA_DIR / f"{name}.json").read_text())

    return _load


@pytest.fixture
def make_client() -> Callable[..., Client]:
    """Return a factory for ``Client`` instances backed by an httpx.MockTransport.

    Pass ``handler=`` to control responses per test:

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={...})

        client = make_client(handler=handler)
    """

    def _factory(
        *,
        handler: Callable[[httpx.Request], httpx.Response],
        api_key: str = "test",
        base_url: str = "https://api.test.opensanctions.org",
    ) -> Client:
        return Client(api_key=api_key, base_url=base_url, transport=httpx.MockTransport(handler))

    return _factory
