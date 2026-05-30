"""Tests for client.search() — filter merge + v1-wire translation + response shape."""

from collections.abc import Callable

import httpx

from yente_client.filters import SearchFilters
from yente_client.models import SearchResponse


def _record_request(
    payload: dict,
) -> tuple[Callable[[httpx.Request], httpx.Response], list[httpx.Request]]:
    """Build a handler that captures the inbound request and returns `payload`."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=payload)

    return handler, seen


def test_search_returns_search_response(make_client, load_fixture) -> None:
    handler, _ = _record_request(load_fixture("search_basic"))
    with make_client(handler=handler) as c:
        r = c.search("acme")
    assert isinstance(r, SearchResponse)
    assert r.total.value == 2
    assert len(r.results) == 2
    assert "countries" in r.facets


def test_search_empty_results(make_client, load_fixture) -> None:
    handler, _ = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        r = c.search("zzzzz")
    assert r.results == []
    assert r.total.value == 0


def test_search_default_dataset_is_default(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("anything")
    assert seen[0].url.path == "/search/default"


def test_search_dataset_first_goes_to_path(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", datasets=["sanctions"])
    assert seen[0].url.path == "/search/sanctions"


def test_search_multiple_datasets_extras_via_include_dataset(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", datasets=["sanctions", "us_ofac_sdn", "eu_fsf"])
    req = seen[0]
    assert req.url.path == "/search/sanctions"
    include = req.url.params.get_list("include_dataset")
    assert include == ["us_ofac_sdn", "eu_fsf"]


def test_search_kwarg_filters_passed_through(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search(
            "x",
            datasets=["default"],
            topics=["sanction", "role.pep"],
            countries=["ru"],
            schema="Person",
        )
    p = seen[0].url.params
    assert p.get_list("topics") == ["sanction", "role.pep"]
    assert p.get_list("countries") == ["ru"]
    assert p.get("schema") == "Person"


def test_search_filters_object_works(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    f = SearchFilters(datasets=["default"], topics=["sanction"], schema_="Company")
    with make_client(handler=handler) as c:
        c.search("acme", filters=f)
    p = seen[0].url.params
    assert p.get("schema") == "Company"
    assert p.get_list("topics") == ["sanction"]


def test_search_kwargs_override_filters_object(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    f = SearchFilters(datasets=["default"], topics=["sanction"])
    with make_client(handler=handler) as c:
        c.search("x", filters=f, topics=["role.pep"])
    assert seen[0].url.params.get_list("topics") == ["role.pep"]


def test_search_exclude_datasets_renamed_to_exclude_dataset(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", datasets=["default"], exclude_datasets=["us_ofac_sdn"])
    assert seen[0].url.params.get_list("exclude_dataset") == ["us_ofac_sdn"]
    assert "exclude_datasets" not in seen[0].url.params


def test_search_exclude_schemata_renamed_to_exclude_schema(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", exclude_schemata=["Address"])
    assert seen[0].url.params.get_list("exclude_schema") == ["Address"]


def test_search_filter_field_alias_passes_through(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", filter=["properties.birthDate:1965"])
    assert seen[0].url.params.get_list("filter") == ["properties.birthDate:1965"]


def test_search_changed_since_passes_string(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", changed_since="2022-02-24")
    assert seen[0].url.params.get("changed_since") == "2022-02-24"


def test_search_pagination(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", limit=50, offset=100)
    p = seen[0].url.params
    assert p.get("limit") == "50"
    assert p.get("offset") == "100"


def test_search_fuzzy_simple_flags(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", fuzzy=True, simple=True)
    p = seen[0].url.params
    assert p.get("fuzzy") == "true"
    assert p.get("simple") == "true"


def test_search_facets_request(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("x", facets=["countries", "topics"])
    assert seen[0].url.params.get_list("facets") == ["countries", "topics"]


def test_search_q_in_query_params(make_client, load_fixture) -> None:
    handler, seen = _record_request(load_fixture("search_no_results"))
    with make_client(handler=handler) as c:
        c.search("alexander zacharov")
    assert seen[0].url.params.get("q") == "alexander zacharov"


def test_search_results_are_entities(make_client, load_fixture) -> None:
    from yente_client.models import Entity

    handler, _ = _record_request(load_fixture("search_basic"))
    with make_client(handler=handler) as c:
        r = c.search("acme")
    assert all(isinstance(item, Entity) for item in r.results)
    assert r.results[0].schema_ == "Person"
    assert r.results[1].schema_ == "Company"
