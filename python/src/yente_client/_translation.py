"""Filter ↔ wire-format translation.

Lives in its own module because the v1↔v2 mapping is the one piece of code
that will change when ``/v2/match`` ships (per design doc §4.8). Keeping it
isolated means swapping it doesn't ripple through the endpoint methods.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, TypeVar

from pydantic import BaseModel

from .filters import MatchFilters, SearchFilters, _CommonFilters

FT = TypeVar("FT", bound=BaseModel)


def merge_filters(cls: type[FT], filters: FT | None, kwargs: dict[str, Any]) -> FT:
    """Merge endpoint ``**kwargs`` into an optional ``filters=`` object.

    Kwargs win on any field they explicitly specify. ``None`` in a kwarg means
    "not supplied" rather than "clear this field", so a caller passing only
    ``filters=`` doesn't have its values clobbered by missing kwargs.

    Aliases are resolved (``schema=`` becomes ``schema_=``) so kwargs can
    target a filter field by either its Python name or its wire alias.
    """
    explicit = {k: v for k, v in kwargs.items() if v is not None}
    explicit = {_resolve_alias(cls, k): v for k, v in explicit.items()}

    if filters is None:
        return cls(**explicit)

    base = filters.model_dump()
    base.update(explicit)
    return cls(**base)


def _resolve_alias(cls: type[BaseModel], key: str) -> str:
    """Map an alias back to its field name; passes through field names unchanged."""
    for field_name, field_info in cls.model_fields.items():
        if field_info.alias == key:
            return field_name
    return key


def datasets_for_wire(datasets: list[str] | None) -> tuple[str, list[str]]:
    """Split a datasets filter into (path-param, include_dataset-extras).

    The v1 wire takes one dataset in the URL path and extras via repeated
    ``include_dataset`` query params. We default to ``"default"`` when the
    caller didn't specify any — same as the server-side default.
    """
    materialised = datasets or ["default"]
    return materialised[0], materialised[1:]


def _serialise_common(f: _CommonFilters) -> dict[str, Any]:
    """Translate the fields _CommonFilters carries into v1 wire query params.

    Renames: ``exclude_datasets`` → ``exclude_dataset``,
    ``exclude_schemata`` → ``exclude_schema``. ``changed_since`` is stringified
    if a ``datetime`` was passed.
    """
    params: dict[str, Any] = {}
    if f.exclude_datasets:
        params["exclude_dataset"] = f.exclude_datasets
    if f.exclude_schemata:
        params["exclude_schema"] = f.exclude_schemata
    if f.topics:
        params["topics"] = f.topics
    if f.changed_since:
        cs = f.changed_since
        params["changed_since"] = cs.isoformat() if isinstance(cs, datetime) else cs
    return params


def serialise_search_filters(f: SearchFilters) -> tuple[str, dict[str, Any]]:
    """Translate a ``SearchFilters`` into ``(dataset_for_path, query_params)``."""
    dataset, include = datasets_for_wire(f.datasets)
    params = _serialise_common(f)
    if include:
        params["include_dataset"] = include
    if f.countries:
        params["countries"] = f.countries
    if f.schema_:
        params["schema"] = f.schema_
    if f.filter_:
        params["filter"] = f.filter_
    return dataset, params


def serialise_match_filters(f: MatchFilters) -> tuple[str, dict[str, Any]]:
    """Translate a ``MatchFilters`` into ``(dataset_for_path, query_params)``.

    Renames specific to ``/match``: ``exclude_entities`` → ``exclude_entity_ids``.
    """
    dataset, include = datasets_for_wire(f.datasets)
    params = _serialise_common(f)
    if include:
        params["include_dataset"] = include
    if f.exclude_entities:
        params["exclude_entity_ids"] = f.exclude_entities
    return dataset, params
