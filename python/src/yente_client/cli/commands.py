"""``yente-client`` subcommand implementations.

Each command is a thin wrapper around the SDK; entity construction, filter
translation, and HTTP details live in :mod:`yente_client.client`. This
module's job is argument-parsing + output formatting.
"""

import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any, cast

from pydantic import ValidationError

from yente_client import entities
from yente_client.cli._deps import typer
from yente_client.cli.config import _DEFAULT_BASE_URL, CliConfig
from yente_client.cli.output import (
    Format,
    print_json,
    print_jsonl,
    print_table,
    resolve_format,
)
from yente_client.entities import EntityInput
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


def search_command(
    ctx: typer.Context,
    q: str = typer.Argument(..., help="Free-text query (name fragment, identifier, ...)."),
    datasets: list[str] | None = typer.Option(
        None,
        "--datasets",
        "-d",
        help="Restrict to dataset(s). Repeatable. Default: `default` (combined dataset).",
    ),
    schema: str | None = typer.Option(
        None, "--schema", "-s", help="Restrict to one entity type, e.g. `Person`, `Company`."
    ),
    topics: list[str] | None = typer.Option(
        None,
        "--topics",
        "-t",
        help="Filter by risk topic(s), e.g. `sanction`, `role.pep`. Repeatable.",
    ),
    countries: list[str] | None = typer.Option(
        None, "--countries", help="Filter by ISO country code(s). Repeatable."
    ),
    filter_: list[str] | None = typer.Option(
        None,
        "--filter",
        help="Property filter `field:value` (e.g. `properties.birthDate:1965`). Repeatable.",
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Results per page (server default 10)."
    ),
    offset: int = typer.Option(0, "--offset", help="Pagination offset."),
    sort: list[str] | None = typer.Option(None, "--sort", help="Sort key(s). Repeatable."),
    fuzzy: bool = typer.Option(False, "--fuzzy", help="Allow fuzzy query syntax."),
    simple: bool = typer.Option(False, "--simple", help="Use the simple-query parser."),
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Free-text search across one or more datasets.

    Use `match` instead when you have a known entity (name + dob + country)
    and want to screen it against risk lists; `search` ranks by text
    relevance, `match` by entity-shape scoring.

    Exits 1 (no results) when the query returns zero hits, so shell scripts
    can gate on `yente-client search … && …`.
    """
    config: CliConfig = ctx.obj

    search_kwargs: dict[str, Any] = {}
    if datasets:
        search_kwargs["datasets"] = datasets
    if schema:
        search_kwargs["schema"] = schema
    if topics:
        search_kwargs["topics"] = topics
    if countries:
        search_kwargs["countries"] = countries
    if filter_:
        search_kwargs["filter"] = filter_

    with config.make_client() as client:
        response = client.search(
            q,
            limit=limit,
            offset=offset,
            sort=sort or None,
            fuzzy=fuzzy,
            simple=simple,
            **search_kwargs,
        )

    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(response)
    elif fmt == Format.JSONL:
        print_jsonl(response.results)
    else:
        rows = [
            [
                r.id,
                r.caption,
                r.schema_,
                ", ".join(r.datasets[:3]),
                ", ".join(t for t in r.properties.get("topics", []) if isinstance(t, str)),
            ]
            for r in response.results
        ]
        print_table(
            rows,
            headers=["id", "caption", "schema", "datasets", "topics"],
            title=f"total={response.total.value}{'+' if response.total.relation == 'gte' else ''}",
        )

    if not response.results:
        raise typer.Exit(code=1)


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


# ----- match -----


def match_command(
    ctx: typer.Context,
    schema: str = typer.Option(
        ...,
        "--schema",
        "-s",
        help="FtM schema name (Person, Company, Vessel, ...). Run `ref schemas --matchable`.",
    ),
    properties: list[str] | None = typer.Option(
        None,
        "--property",
        "-p",
        help=(
            "Set a property, repeatable: `-p firstName=Aleksandr -p lastName=Zacharov`. "
            "Same key passed twice produces a multi-value property. "
            "Names are FtM camelCase (e.g. `birthDate`, not `birth_date`)."
        ),
    ),
    from_file: Path | None = typer.Option(
        None,
        "--from-file",
        "-i",
        help='JSON file with shape {"schema": "...", "properties": {...}}. '
        "`-s` and `-p` flags override values from the file.",
    ),
    datasets: list[str] | None = typer.Option(
        None, "--datasets", "-d", help="Restrict to dataset(s). Repeatable."
    ),
    topics: list[str] | None = typer.Option(
        None, "--topics", "-t", help="Topic filter. Repeatable."
    ),
    threshold: float | None = typer.Option(
        None, "--threshold", help="Score threshold for the match flag (server default 0.70)."
    ),
    algorithm: str | None = typer.Option(
        None,
        "--algorithm",
        "-a",
        help='Scoring algorithm. "best" is stable across versions; see `algorithms`.',
    ),
    limit: int | None = typer.Option(
        None, "--limit", "-l", help="Max results per query (server default 5)."
    ),
    changed_since: str | None = typer.Option(
        None,
        "--changed-since",
        help="Only match entities updated since this ISO 8601 date.",
    ),
    exclude_entities: list[str] | None = typer.Option(
        None, "--exclude-entities", help="Exclude these entity IDs from results. Repeatable."
    ),
    exclude_schemata: list[str] | None = typer.Option(
        None, "--exclude-schemata", help="Exclude these schemas from results. Repeatable."
    ),
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Match a single entity (built from `-p` flags or `--from-file`) against a dataset.

    Use `search` instead for free-text discovery by name; `match` scores a
    fully-described entity against the dataset's risk lists.

    Exits 1 if no results returned, so shell scripts can gate on
    `yente-client match … && …`.
    """
    config: CliConfig = ctx.obj
    entity = _build_entity_input(schema, properties or [], from_file)

    match_kwargs: dict[str, Any] = {}
    if datasets:
        match_kwargs["datasets"] = datasets
    if topics:
        match_kwargs["topics"] = topics
    if changed_since:
        match_kwargs["changed_since"] = changed_since
    if exclude_entities:
        match_kwargs["exclude_entities"] = exclude_entities
    if exclude_schemata:
        match_kwargs["exclude_schemata"] = exclude_schemata

    with config.make_client() as client:
        response = client.match(
            entity,
            threshold=threshold,
            algorithm=algorithm,
            limit=limit,
            **match_kwargs,
        )

    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(response)
    elif fmt == Format.JSONL:
        print_jsonl(response.results)
    else:
        rows = [
            [
                f"{r.score:.2f}",
                "✓" if r.match else "",
                r.id,
                r.caption,
                r.schema_,
                ", ".join(r.datasets[:3]),
                ", ".join(t for t in r.properties.get("topics", []) if isinstance(t, str)),
            ]
            for r in response.results
        ]
        print_table(
            rows,
            headers=["score", "match", "id", "caption", "schema", "datasets", "topics"],
            title=(
                f"total={response.total.value}"
                f"{'+' if response.total.relation == 'gte' else ''} "
                f"threshold-passing={len(response.matches)}"
            ),
        )

    if not response.results:
        raise typer.Exit(code=1)


def _build_entity_input(schema: str, properties: list[str], from_file: Path | None) -> EntityInput:
    """Construct a per-schema entity from CLI inputs.

    Properties from ``--from-file`` are loaded first; ``-p KEY=VALUE`` flags
    are then layered on top (later wins on first set, same-key repeats append).
    The resulting dict is passed to the per-schema class — Pydantic enforces
    property-name validity via ``extra="forbid"``.
    """
    schema_cls = getattr(entities, schema, None)
    if schema_cls is None or not isinstance(schema_cls, type):
        typer.echo(
            f"error: Unknown schema {schema!r}. Run `yente-client ref schemas` for the list.",
            err=True,
        )
        raise typer.Exit(code=2)

    props: dict[str, list[str]] = {}
    if from_file is not None:
        try:
            raw: dict[str, Any] = json.loads(from_file.read_text())
        except (OSError, ValueError) as exc:
            typer.echo(f"error: could not read {from_file}: {exc}", err=True)
            raise typer.Exit(code=2) from exc
        file_props = raw.get("properties") or {}
        for key, value in file_props.items():
            props[key] = value if isinstance(value, list) else [value]

    for spec in properties:
        if "=" not in spec:
            typer.echo(
                f"error: --property must be KEY=VALUE; got {spec!r}",
                err=True,
            )
            raise typer.Exit(code=2)
        key, value = spec.split("=", 1)
        props.setdefault(key, []).append(value)

    try:
        return cast(EntityInput, schema_cls(**props))
    except ValidationError as exc:
        typer.echo(f"error: invalid {schema} entity: {exc}", err=True)
        raise typer.Exit(code=2) from exc


# ----- registration -----


def register(app: typer.Typer) -> None:
    """Attach all subcommands to ``app``."""
    app.command("version", help="Print client + bundled FtM model version.")(version_command)
    app.command("healthz")(healthz_command)
    app.command("readyz")(readyz_command)
    app.command("catalog")(catalog_command)
    app.command("algorithms")(algorithms_command)
    app.command("fetch")(fetch_command)
    app.command("search")(search_command)
    app.command("match")(match_command)
