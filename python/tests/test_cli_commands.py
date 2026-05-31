"""Tests for read-only CLI subcommands (Phase D).

Uses Typer's ``CliRunner`` for invocation and ``respx`` for HTTP mocking.
Each test sets ``--api-key`` and ``--base-url`` flags so the missing-key
warning doesn't fire against the hosted URL default.
"""

import json

import httpx
import pytest
import respx
from typer.testing import CliRunner

from yente_client.cli.main import app


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


_BASE_URL = "http://test.local"
_BASE_FLAGS = ["--api-key", "test", "--base-url", _BASE_URL]


# ---------- version ----------


def test_version_command(runner) -> None:
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "yente-client" in result.stdout
    assert "Bundled FtM model" in result.stdout


def test_top_level_version_flag(runner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "yente-client" in result.stdout


# ---------- healthz / readyz ----------


def test_healthz_table_output(runner, load_fixture) -> None:
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get("/healthz").mock(return_value=httpx.Response(200, json=load_fixture("status_ok")))
        result = runner.invoke(app, [*_BASE_FLAGS, "healthz"])
    assert result.exit_code == 0
    assert "ok" in result.stdout


def test_healthz_json_format(runner, load_fixture) -> None:
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get("/healthz").mock(return_value=httpx.Response(200, json=load_fixture("status_ok")))
        result = runner.invoke(app, [*_BASE_FLAGS, "healthz", "-f", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed == {"status": "ok"}


def test_readyz_command(runner, load_fixture) -> None:
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get("/readyz").mock(return_value=httpx.Response(200, json=load_fixture("status_ok")))
        result = runner.invoke(app, [*_BASE_FLAGS, "readyz"])
    assert result.exit_code == 0
    assert "ok" in result.stdout


# ---------- catalog ----------


def test_catalog_table(runner, load_fixture) -> None:
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get("/catalog").mock(return_value=httpx.Response(200, json=load_fixture("catalog")))
        result = runner.invoke(app, [*_BASE_FLAGS, "catalog", "-f", "table"])
    assert result.exit_code == 0
    assert "default" in result.stdout
    assert "us_ofac_sdn" in result.stdout


def test_catalog_json(runner, load_fixture) -> None:
    payload = load_fixture("catalog")
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get("/catalog").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, [*_BASE_FLAGS, "catalog", "-f", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert "datasets" in parsed
    assert len(parsed["datasets"]) == 2


# ---------- algorithms ----------


def test_algorithms_table(runner, load_fixture) -> None:
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get("/algorithms").mock(
            return_value=httpx.Response(200, json=load_fixture("algorithms"))
        )
        # CliRunner captures into a non-TTY stream — auto would resolve to
        # JSON, so we force table explicitly.
        result = runner.invoke(app, [*_BASE_FLAGS, "algorithms", "-f", "table"])
    assert result.exit_code == 0
    assert "logic-v2" in result.stdout
    assert "name-matcher" in result.stdout
    # The "best" algorithm gets a marker.
    assert "★" in result.stdout


# ---------- fetch ----------


def test_fetch_table_summary(runner, load_fixture) -> None:
    payload = load_fixture("entity_person")
    eid = payload["id"]
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get(f"/entities/{eid}").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, [*_BASE_FLAGS, "fetch", eid, "-f", "table"])
    assert result.exit_code == 0
    assert eid in result.stdout
    assert "Person" in result.stdout
    assert "sanction" in result.stdout


def test_fetch_json(runner, load_fixture) -> None:
    payload = load_fixture("entity_person")
    eid = payload["id"]
    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get(f"/entities/{eid}").mock(return_value=httpx.Response(200, json=payload))
        result = runner.invoke(app, [*_BASE_FLAGS, "fetch", eid, "-f", "json"])
    assert result.exit_code == 0
    parsed = json.loads(result.stdout)
    assert parsed["id"] == eid
    assert parsed["schema"] == "Person"


def test_fetch_no_nested_flag(runner, load_fixture) -> None:
    captured: list[str] = []
    payload = load_fixture("entity_person")

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.url.params.get("nested") or "")
        return httpx.Response(200, json=payload)

    with respx.mock(base_url=_BASE_URL) as mock:
        mock.get(f"/entities/{payload['id']}").mock(side_effect=handler)
        result = runner.invoke(
            app, [*_BASE_FLAGS, "fetch", payload["id"], "--no-nested", "-f", "json"]
        )
    assert result.exit_code == 0
    assert captured == ["false"]
