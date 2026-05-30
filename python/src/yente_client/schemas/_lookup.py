"""Runtime access to the bundled FtM model snapshot.

Loads ``schemas/model.json`` at import time and exposes the inner ``model``
dict plus four small lookup helpers. No Pydantic-typed wrappers — the codegen
reads ``model.json`` directly and users who want introspection get dict access.
"""

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

_RAW: dict[str, Any] = json.loads((Path(__file__).parent / "model.json").read_text())

model: dict[str, Any] = _RAW["model"]


def has_schema(name: str) -> bool:
    """Return True if ``name`` is a valid schema in the bundled model."""
    return name in model["schemata"]


def iter_properties(schema: str) -> Iterator[str]:
    """Yield every property name available on ``schema``, including inherited ones.

    ``model.json`` stores own-properties only on each schema definition; we walk
    the pre-flattened ``schemata`` ancestor list and yield each property name
    at most once, even if multiple ancestors define a property of the same name.
    """
    if not has_schema(schema):
        raise KeyError(schema)
    seen: set[str] = set()
    for ancestor in model["schemata"][schema]["schemata"]:
        ancestor_props = model["schemata"].get(ancestor, {}).get("properties", {})
        for prop in ancestor_props:
            if prop not in seen:
                seen.add(prop)
                yield prop


def is_a(schema: str, ancestor: str) -> bool:
    """Return True if ``schema`` extends ``ancestor`` transitively.

    Reflexive on ``schema`` itself. O(1) lookup against the pre-flattened
    ``schemata`` list — no MRO walk needed.
    """
    if not has_schema(schema):
        raise KeyError(schema)
    return ancestor in model["schemata"][schema]["schemata"]


def is_deprecated(schema: str, prop: str) -> bool:
    """Return True if ``prop`` is marked ``deprecated`` on ``schema`` or any ancestor."""
    if not has_schema(schema):
        raise KeyError(schema)
    for ancestor in model["schemata"][schema]["schemata"]:
        props = model["schemata"].get(ancestor, {}).get("properties", {})
        if prop in props:
            return bool(props[prop].get("deprecated", False))
    raise KeyError(prop)
