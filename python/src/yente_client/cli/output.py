"""Output formatters for ``yente-client`` subcommands.

Three formats — ``json`` (pretty), ``jsonl`` (one item per line, for ``jq`` /
LLM pipelines), and ``table`` (Rich, default on TTY). Per-command callers
build the table rows themselves; this module only renders.
"""

import json
import sys
from collections.abc import Iterable
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

from yente_client.cli._deps import Console, Table, typer


class Format(StrEnum):
    """``-f`` / ``--format`` choice. ``AUTO`` resolves to ``TABLE`` on a TTY,
    ``JSON`` on a pipe."""

    JSON = "json"
    JSONL = "jsonl"
    TABLE = "table"
    AUTO = "auto"


def resolve_format(requested: Format) -> Format:
    """Resolve ``AUTO`` to a concrete format based on stdout being a TTY."""
    if requested != Format.AUTO:
        return requested
    return Format.TABLE if sys.stdout.isatty() else Format.JSON


def to_jsonable(obj: Any) -> Any:
    """Convert pydantic models, datetimes, etc. to plain JSON-able types.

    Uses ``model_dump(mode="json", by_alias=True)`` so the wire-format aliases
    (e.g. ``schema``, not ``schema_``) reach the output unchanged.
    """
    if isinstance(obj, BaseModel):
        return obj.model_dump(mode="json", by_alias=True)
    return obj


def print_json(obj: Any) -> None:
    """Print one object as pretty JSON to stdout."""
    typer.echo(json.dumps(to_jsonable(obj), indent=2, ensure_ascii=False, default=str))


def print_jsonl(items: Iterable[Any]) -> None:
    """Print each item on its own line of JSON (``jsonl`` format)."""
    for item in items:
        typer.echo(json.dumps(to_jsonable(item), ensure_ascii=False, default=str))


def print_table(
    rows: Iterable[Iterable[Any]],
    headers: list[str],
    *,
    title: str | None = None,
    console: Console | None = None,
) -> None:
    """Render ``rows`` as a Rich table.

    Cells are coerced to ``str``; callers truncate or transform earlier if
    they want narrower columns.
    """
    table = Table(*headers, title=title, show_lines=False)
    for row in rows:
        table.add_row(*(str(cell) for cell in row))
    (console or Console()).print(table)
