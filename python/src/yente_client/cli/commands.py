"""``yente-client`` subcommand implementations.

Each command is a thin wrapper around the SDK; entity construction, filter
translation, and HTTP details live in :mod:`yente_client.client`. This
module's job is argument-parsing + output formatting.
"""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any

from yente_client.cli._deps import typer
from yente_client.cli.config import _DEFAULT_BASE_URL, CliConfig
from yente_client.cli.output import (
    Format,
    print_json,
    print_jsonl,
    print_table,
    resolve_format,
)
from yente_client.models import Entity

_FORMAT_HELP = "Output format. `auto` (default) renders a table on a TTY and JSON when piped."


# ----- version -----


def version_command() -> None:
    """Print the client version and the bundled FtM model identity.

    Output includes the package version, the FtM model snapshot's ``run_time``
    (so callers — including LLM agents — can reason about which schemas and
    topics are available without poking around), and the default API target.
    """
    try:
        client_version = version("yente-client")
    except PackageNotFoundError:
        client_version = "0.0.0+unknown"

    typer.echo(f"yente-client {client_version}")
    typer.echo(f"Bundled FtM model: {_read_model_snapshot_date()}")
    typer.echo(f"Default API:       {_DEFAULT_BASE_URL}")


def _read_model_snapshot_date() -> str:
    """Return the bundled ``model.json``'s ``run_time`` field as a string."""
    model_path = Path(__file__).resolve().parent.parent / "schemas" / "model.json"
    try:
        raw: dict[str, Any] = json.loads(model_path.read_text())
    except (OSError, ValueError):
        return "unknown"
    run_time = raw.get("run_time")
    return str(run_time) if run_time else "unknown"


# ----- health probes -----


def healthz_command(
    ctx: typer.Context,
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Probe server liveness.

    Returns ``{"status": "ok"}`` whenever the server process is up. Useful for
    Kubernetes liveness probes. See ``readyz`` for index readiness, which can
    fail independently.
    """
    config: CliConfig = ctx.obj
    with config.make_client() as client:
        result = client.healthz()
    if resolve_format(format_) in (Format.JSON, Format.JSONL):
        print_json(result)
    else:
        typer.echo(result.status)


def readyz_command(
    ctx: typer.Context,
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Probe whether the search index is ready to serve queries.

    Returns 503 (mapped to a ``ServerError`` exit) until the index has loaded.
    """
    config: CliConfig = ctx.obj
    with config.make_client() as client:
        result = client.readyz()
    if resolve_format(format_) in (Format.JSON, Format.JSONL):
        print_json(result)
    else:
        typer.echo(result.status)


# ----- catalog / algorithms -----


def catalog_command(
    ctx: typer.Context,
    current_only: bool = typer.Option(
        False, "--current-only", help="Only show datasets whose index is current."
    ),
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Fetch the catalog of indexed datasets and their freshness state.

    Use this to discover what dataset names you can pass to ``-d`` /
    ``--datasets`` on ``search`` / ``match``.
    """
    config: CliConfig = ctx.obj
    with config.make_client() as client:
        catalog = client.catalog()

    datasets = catalog.datasets
    if current_only:
        current = set(catalog.current)
        datasets = [d for d in datasets if d.name in current]

    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(catalog if not current_only else {"datasets": datasets})
    elif fmt == Format.JSONL:
        print_jsonl(datasets)
    else:
        current_set = set(catalog.current)
        rows = [
            [
                d.name,
                d.title or "",
                d.version or "",
                "yes" if d.name in current_set else "no",
            ]
            for d in datasets
        ]
        print_table(rows, headers=["name", "title", "version", "current"])


def algorithms_command(
    ctx: typer.Context,
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """List enabled matching algorithms and the server's "best" pick.

    Use the ``name`` from this list with ``-a`` / ``--algorithm`` on ``match``.
    ``best`` is the server's canonical default — passing ``-a best`` is stable
    across algorithm version bumps.
    """
    config: CliConfig = ctx.obj
    with config.make_client() as client:
        algorithms = client.algorithms()

    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(algorithms)
    elif fmt == Format.JSONL:
        print_jsonl(algorithms.algorithms)
    else:
        rows = [
            [a.name, "★" if a.name == algorithms.best else "", a.description or ""]
            for a in algorithms.algorithms
        ]
        print_table(
            rows,
            headers=["name", "best", "description"],
            title=f"default={algorithms.default!r}  best={algorithms.best!r}",
        )


# ----- fetch -----


def fetch_command(
    ctx: typer.Context,
    entity_id: str = typer.Argument(..., help="Entity ID returned by `match` or `search`."),
    no_nested: bool = typer.Option(
        False,
        "--no-nested",
        help="Skip inline adjacent entities (sanctions, ownership, family, ...).",
    ),
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Fetch a single entity by ID.

    Follows ``308`` redirects transparently when the supplied ID is a referent
    of a canonical entity. The default (with ``nested=true``) returns related
    entities inline; pass ``--no-nested`` for a lighter response.
    """
    config: CliConfig = ctx.obj
    with config.make_client() as client:
        entity = client.fetch(entity_id, nested=not no_nested)

    fmt = resolve_format(format_)
    if fmt in (Format.JSON, Format.JSONL):
        print_json(entity)
    else:
        _print_entity_summary(entity)


def _print_entity_summary(entity: Entity) -> None:
    """Render an entity as a key-value summary table for TTY output.

    Full property detail is too wide for a table; users wanting it should use
    ``-f json``. This summary is the at-a-glance view.
    """
    topics = [t for t in entity.properties.get("topics", []) if isinstance(t, str)]
    rows: list[list[Any]] = [
        ["id", entity.id],
        ["caption", entity.caption],
        ["schema", entity.schema_],
        ["target", "yes" if entity.target else "no"],
        ["datasets", ", ".join(entity.datasets)],
        ["topics", ", ".join(topics)],
    ]
    print_table(rows, headers=["field", "value"], title=entity.caption)


# ----- registration -----


def register(app: typer.Typer) -> None:
    """Attach all subcommands to ``app``."""
    app.command("version", help="Print client + bundled FtM model version.")(version_command)
    app.command("healthz")(healthz_command)
    app.command("readyz")(readyz_command)
    app.command("catalog")(catalog_command)
    app.command("algorithms")(algorithms_command)
    app.command("fetch")(fetch_command)
