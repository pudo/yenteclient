"""Tests for filter types: cross-endpoint rejection, alias round-trip, Literal validation."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from yente_client.filters import MatchFilters, SearchFilters, _CommonFilters


def test_match_filters_basic() -> None:
    f = MatchFilters(
        datasets=["sanctions"],
        topics=["sanction", "role.pep"],
        exclude_entities=["Q1"],
        changed_since="2022-02-24",
    )
    assert f.datasets == ["sanctions"]
    assert f.topics == ["sanction", "role.pep"]
    assert f.exclude_entities == ["Q1"]


def test_match_filters_rejects_search_only_fields() -> None:
    # `countries` is search-only; presence on MatchFilters is a typo.
    with pytest.raises(ValidationError, match="countries"):
        MatchFilters(datasets=["sanctions"], countries=["us"])  # type: ignore[call-arg]


def test_search_filters_basic() -> None:
    f = SearchFilters(datasets=["default"], countries=["ru"], topics=["sanction"])
    assert f.countries == ["ru"]


def test_search_filters_rejects_match_only_fields() -> None:
    with pytest.raises(ValidationError, match="exclude_entities"):
        SearchFilters(datasets=["default"], exclude_entities=["Q1"])  # type: ignore[call-arg]


def test_search_filters_schema_alias_round_trip() -> None:
    # Both `schema=` (alias) and `schema_=` (field name) work.
    f1 = SearchFilters(schema="Company")  # type: ignore[call-arg]
    assert f1.schema_ == "Company"

    f2 = SearchFilters(schema_="Person")
    assert f2.schema_ == "Person"


def test_search_filters_filter_alias_round_trip() -> None:
    f1 = SearchFilters(filter=["properties.birthDate:1965"])  # type: ignore[call-arg]
    assert f1.filter_ == ["properties.birthDate:1965"]

    f2 = SearchFilters(filter_=["topics:sanction"])
    assert f2.filter_ == ["topics:sanction"]


def test_topics_literal_rejects_unknown_topic() -> None:
    # `topics` is typed as list[Topic]; bogus values fail at construction.
    with pytest.raises(ValidationError):
        MatchFilters(topics=["not-a-real-topic"])  # type: ignore[list-item]


def test_schema_literal_rejects_unknown_schema() -> None:
    with pytest.raises(ValidationError):
        SearchFilters(schema_="NotARealSchema")  # type: ignore[arg-type]


def test_exclude_schemata_literal_rejects_unknown() -> None:
    with pytest.raises(ValidationError):
        MatchFilters(exclude_schemata=["NotARealSchema"])  # type: ignore[list-item]


def test_changed_since_accepts_string() -> None:
    f = MatchFilters(changed_since="2022-02-24")
    assert f.changed_since == "2022-02-24"


def test_changed_since_accepts_datetime() -> None:
    dt = datetime(2022, 2, 24, 12, 0, 0)
    f = MatchFilters(changed_since=dt)
    assert f.changed_since == dt


def test_common_filters_not_directly_useful() -> None:
    # _CommonFilters is the shared base; users should pick Match or Search.
    # It's importable but doesn't carry endpoint-specific fields.
    f = _CommonFilters(datasets=["x"])
    assert f.datasets == ["x"]
    assert not hasattr(f, "exclude_entities")
    assert not hasattr(f, "countries")


def test_extra_forbid_blocks_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        MatchFilters(datasets=["x"], nonsense_field="value")  # type: ignore[call-arg]
