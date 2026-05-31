"""``yente-client`` subcommand implementations.

Each command is a thin wrapper around the SDK; entity construction, filter
translation, and HTTP details live in :mod:`yente_client.client`. This
module's job is argument-parsing + output formatting.
"""

import contextlib
import difflib
import json
from collections.abc import Iterator
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
from yente_client.client import Client
from yente_client.entities import EntityInput
from yente_client.exceptions import (
    APIError,
    ConfigurationError,
    TransportError,
    YenteError,
)
from yente_client.models import Entity
from yente_client.schemas import has_schema, iter_properties, model

_FORMAT_HELP = "Output format. `auto` (default) renders a table on a TTY and JSON when piped."


# ----- error handling + suggestions -----


def _exit_code_for(exc: YenteError) -> int:
    """Map a ``YenteError`` to the CLI exit code per §5.4."""
    if isinstance(exc, TransportError):
        return 4
    if isinstance(exc, (APIError, ConfigurationError)):
        return 3
    return 3


def _emit_yente_error(ctx: typer.Context, exc: YenteError) -> None:
    """Render a YenteError as a clean one-line message to stderr.

    ``-v`` / ``--verbose`` (read from ``ctx.obj.verbose``) shows the full
    chain via the active Python traceback handler instead.
    """
    config: CliConfig | None = ctx.obj if isinstance(ctx.obj, CliConfig) else None
    if config and config.verbose:
        raise exc
    if isinstance(exc, APIError):
        typer.echo(f"error: {type(exc).__name__} ({exc.status_code}): {exc.detail}", err=True)
    else:
        typer.echo(f"error: {type(exc).__name__}: {exc}", err=True)


@contextlib.contextmanager
def _with_client(ctx: typer.Context) -> Iterator[Client]:
    """Context manager that builds a Client and converts SDK errors to clean exits.

    Wraps each endpoint command. ``YenteError`` subclasses are rendered as a
    one-line stderr message and re-raised as ``typer.Exit`` with the right
    exit code. ``-v`` / ``--verbose`` short-circuits to the original
    traceback for debugging.
    """
    config: CliConfig = ctx.obj
    try:
        with config.make_client() as client:
            yield client
    except YenteError as exc:
        _emit_yente_error(ctx, exc)
        raise typer.Exit(code=_exit_code_for(exc)) from exc


def _suggest_schema(name: str) -> str | None:
    """Return the closest valid FtM schema name, or ``None`` if no close match."""
    valid = list(model["schemata"].keys())
    matches = difflib.get_close_matches(name, valid, n=1, cutoff=0.6)
    return matches[0] if matches else None


def _suggest_property(schema: str, prop_name: str) -> str | None:
    """Return the closest valid property name for ``schema``, or ``None``."""
    try:
        valid = list(iter_properties(schema))
    except KeyError:
        return None
    matches = difflib.get_close_matches(prop_name, valid, n=1, cutoff=0.6)
    return matches[0] if matches else None


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
    with _with_client(ctx) as client:
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
    with _with_client(ctx) as client:
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
    with _with_client(ctx) as client:
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
    with _with_client(ctx) as client:
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
    with _with_client(ctx) as client:
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

    with _with_client(ctx) as client:
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

    with _with_client(ctx) as client:
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
        suggestion = _suggest_schema(schema)
        hint = f" Did you mean: {suggestion}?" if suggestion else ""
        typer.echo(
            f"error: Unknown schema {schema!r}.{hint} Run `yente-client ref schemas` for the list.",
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
        # If any error is a known-extra-fields-forbidden case, try to suggest
        # the closest valid property name for the agent reading the message.
        suggestions: list[str] = []
        for err in exc.errors():
            if err.get("type") == "extra_forbidden" and err.get("loc"):
                bad_prop = str(err["loc"][0])
                close = _suggest_property(schema, bad_prop)
                if close:
                    suggestions.append(f"{bad_prop!r} → did you mean {close!r}?")
        tail = " " + "; ".join(suggestions) if suggestions else ""
        typer.echo(f"error: invalid {schema} entity: {exc}.{tail}", err=True)
        raise typer.Exit(code=2) from exc


# ----- ref (offline FtM model introspection) -----


def ref_schemas_command(
    matchable_only: bool = typer.Option(
        False,
        "--matchable",
        help="Filter to schemas that can be used as `match` query targets.",
    ),
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """List every FtM schema in the bundled model.

    Offline — no API call, no API key needed. Use this to discover what `-s`
    values you can pass to `match` or `search`. For details on one schema,
    run ``ref schema NAME``.
    """
    schemata = model["schemata"]
    entries: list[dict[str, Any]] = []
    for name in sorted(schemata):
        defn = schemata[name]
        if matchable_only and not defn.get("matchable"):
            continue
        entries.append(
            {
                "name": name,
                "label": defn.get("label", ""),
                "matchable": bool(defn.get("matchable", False)),
                "abstract": bool(defn.get("abstract", False)),
                "extends": list(defn.get("extends") or []),
                "description": (defn.get("description") or "").strip(),
            }
        )

    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(entries)
    elif fmt == Format.JSONL:
        print_jsonl(entries)
    else:
        rows = [
            [
                e["name"],
                "✓" if e["matchable"] else "",
                "abstract" if e["abstract"] else "",
                ", ".join(e["extends"]),
                _truncate(e["description"], 60),
            ]
            for e in entries
        ]
        print_table(
            rows,
            headers=["schema", "matchable", "flags", "extends", "description"],
            title=f"{len(entries)} schema(s)",
        )


def ref_schema_command(
    name: str = typer.Argument(..., help="Schema name, e.g. `Person`, `Company`, `Vessel`."),
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """Show one schema's properties, types, and inheritance.

    Includes inherited properties (walks the ancestor chain), so what you
    see is the complete set of fields you can pass via `-p KEY=VALUE` to
    `match`. With ``-f json`` the output is LLM-friendly and includes per-
    property type and `deprecated` flags.
    """
    if not has_schema(name):
        suggestion = _suggest_schema(name)
        hint = f" Did you mean: {suggestion}?" if suggestion else ""
        typer.echo(
            f"error: Unknown schema {name!r}.{hint} Run `yente-client ref schemas` for the list.",
            err=True,
        )
        raise typer.Exit(code=2)

    schemata = model["schemata"]
    defn = schemata[name]
    properties = _collect_schema_properties(name)
    summary: dict[str, Any] = {
        "name": name,
        "label": defn.get("label", ""),
        "description": (defn.get("description") or "").strip(),
        "matchable": bool(defn.get("matchable", False)),
        "abstract": bool(defn.get("abstract", False)),
        "extends": list(defn.get("extends") or []),
        "schemata": list(defn.get("schemata") or []),
        "featured": list(defn.get("featured") or []),
        "required": list(defn.get("required") or []),
        "properties": properties,
    }

    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(summary)
    elif fmt == Format.JSONL:
        # One property per line — useful for agents iterating over the prop list.
        print_jsonl(properties)
    else:
        typer.echo(f"{name}  ({defn.get('label', '')})")
        if summary["description"]:
            typer.echo(summary["description"])
        typer.echo("")
        typer.echo(f"  matchable:  {'yes' if summary['matchable'] else 'no'}")
        typer.echo(f"  extends:    {', '.join(summary['extends']) or '(none)'}")
        typer.echo(f"  featured:   {', '.join(summary['featured']) or '(none)'}")
        typer.echo(f"  required:   {', '.join(summary['required']) or '(none)'}")
        typer.echo("")
        rows = [
            [
                p["name"],
                p["type"],
                "deprecated" if p["deprecated"] else "",
                _truncate(p["description"], 50),
            ]
            for p in properties
        ]
        print_table(
            rows,
            headers=["property", "type", "flags", "description"],
            title=f"{len(properties)} property/properties (own + inherited)",
        )


def _collect_schema_properties(name: str) -> list[dict[str, Any]]:
    """Walk the ancestor chain and return one row per property name.

    Mirrors ``scripts/regen_model.py``'s ``collect_properties`` shape so the
    `ref schema` view matches what the codegen would generate. Stub
    properties (reverse edges) are excluded — they're navigation-only.
    """
    schemata = model["schemata"]
    seen: set[str] = set()
    rows: list[dict[str, Any]] = []
    for ancestor in schemata[name].get("schemata", [name]):
        anc_props = schemata.get(ancestor, {}).get("properties", {})
        for prop_name, prop_def in anc_props.items():
            if prop_name in seen or prop_def.get("stub"):
                continue
            seen.add(prop_name)
            rows.append(
                {
                    "name": prop_name,
                    "type": prop_def.get("type", "string"),
                    "label": prop_def.get("label", ""),
                    "description": (prop_def.get("description") or "").strip(),
                    "deprecated": bool(prop_def.get("deprecated", False)),
                    "from_schema": ancestor,
                }
            )
    rows.sort(key=lambda r: r["name"])
    return rows


def ref_topics_command(
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """List the Topic enum (the canonical risk tags an entity can carry).

    Use these names with `-t` / `--topics` on `match` and `search`. Sourced
    from ``model.types["topic"].values`` in the bundled snapshot.
    """
    topic_values = model["types"].get("topic", {}).get("values", {})
    entries = [{"name": name, "label": label} for name, label in sorted(topic_values.items())]
    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(entries)
    elif fmt == Format.JSONL:
        print_jsonl(entries)
    else:
        rows = [[e["name"], e["label"]] for e in entries]
        print_table(rows, headers=["topic", "label"], title=f"{len(entries)} topic(s)")


def ref_countries_command(
    format_: Format = typer.Option(Format.AUTO, "--format", "-f", help=_FORMAT_HELP),
) -> None:
    """List valid country codes for the ``country`` property type.

    Use these with ``--countries`` on ``search`` or as values on
    country-typed properties (``country``, ``nationality``, ``birthCountry``,
    ``jurisdiction``, …). Sourced from ``model.types["country"].values``.
    """
    country_values = model["types"].get("country", {}).get("values", {})
    entries = [{"code": code, "name": name} for code, name in sorted(country_values.items())]
    fmt = resolve_format(format_)
    if fmt == Format.JSON:
        print_json(entries)
    elif fmt == Format.JSONL:
        print_jsonl(entries)
    else:
        rows = [[e["code"], e["name"]] for e in entries]
        print_table(rows, headers=["code", "name"], title=f"{len(entries)} country code(s)")


def _truncate(text: str, max_len: int) -> str:
    """Truncate a string with an ellipsis if it exceeds `max_len`."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


# ----- registration -----


def register(app: typer.Typer) -> None:
    """Attach all subcommands to ``app``."""
    app.command("version", help="Print client + bundled FtM model version.")(version_command)
    app.command("healthz", epilog=_HEALTHZ_EPILOG)(healthz_command)
    app.command("readyz", epilog=_HEALTHZ_EPILOG)(readyz_command)
    app.command("catalog", epilog=_CATALOG_EPILOG)(catalog_command)
    app.command("algorithms", epilog=_ALGORITHMS_EPILOG)(algorithms_command)
    app.command("fetch", epilog=_FETCH_EPILOG)(fetch_command)
    app.command("search", epilog=_SEARCH_EPILOG)(search_command)
    app.command("match", epilog=_MATCH_EPILOG)(match_command)

    ref_app = typer.Typer(
        name="ref",
        help="Inspect the bundled FtM model (offline; no API key required).",
        no_args_is_help=True,
    )
    ref_app.command("schemas", epilog=_REF_SCHEMAS_EPILOG)(ref_schemas_command)
    ref_app.command("schema", epilog=_REF_SCHEMA_EPILOG)(ref_schema_command)
    ref_app.command("topics")(ref_topics_command)
    ref_app.command("countries")(ref_countries_command)
    app.add_typer(ref_app, name="ref")


# ----- epilogs (worked examples + output shape notes for agent use) -----

_HEALTHZ_EPILOG = """\
OUTPUT: a `{status: 'ok'}` object on success. The server returns 503
(mapped to a ServerError exit, code 3) when the index isn't ready.
"""

_CATALOG_EPILOG = """\
EXAMPLES:
  yente-client catalog                       # human-readable table
  yente-client catalog -f json               # full CatalogResponse as JSON
  yente-client catalog --current-only        # skip stale-index datasets

OUTPUT (with -f json):
  {datasets: [{name, title, version, index_current}, ...],
   current: [str], outdated: [str], index_stale: bool}

The `name` field is what you pass to `-d` / `--datasets` on match/search.
"""

_ALGORITHMS_EPILOG = """\
EXAMPLES:
  yente-client algorithms
  yente-client algorithms -f json

OUTPUT (with -f json):
  {algorithms: [{name, description, docs}], default: str, best: str}

Pass `best` to `match -a best` for the server's recommended algorithm —
stable across version bumps.
"""

_FETCH_EPILOG = """\
EXAMPLES:
  yente-client fetch NK-aU5ybkbRFJucf8YMwsJvDw                # summary table
  yente-client fetch <id> -f json                              # full Entity as JSON
  yente-client fetch <id> --no-nested                          # skip adjacent entities

OUTPUT (with -f json):
  Entity object: {id, caption, schema, properties: {<name>: [...]}, datasets,
                  referents, target, first_seen, last_seen, last_change}

Property values are always lists. With nested=true (default), entity-valued
properties (sanctions, ownerships, family, ...) inline as nested Entity objects.
"""

_SEARCH_EPILOG = """\
EXAMPLES:
  yente-client search "acme"                                            # default dataset
  yente-client search "acme" -d default -s Company                      # type filter
  yente-client search "vladimir putin" -d sanctions -t sanction -l 5
  yente-client search "x" -d default --filter properties.birthDate:1965 -f json

OUTPUT (with -f json):
  SearchResponse: {results: [Entity, ...], facets: {...}, total: {value, relation},
                   limit, offset}

EXIT CODES:
  0  ≥1 result
  1  zero results
  3  API error (4xx, 5xx)
  4  network/transport error

Use `match` instead when you have a known entity (name + dob + country)
and want to screen it against risk lists.
"""

_MATCH_EPILOG = """\
EXAMPLES:
  yente-client match -s Person -p firstName=Aleksandr -p lastName=Zacharov -d sanctions
  yente-client match -s Company -p name="Acme LLC" -p jurisdiction=us -d default
  yente-client match -s Person -p firstName=X -p firstName=Alexander -d sanctions   # multi-value
  yente-client match -s Person -i query.json -d sanctions -a best                    # from JSON
  yente-client match -s Person -p name=Putin -d sanctions -f jsonl     # LLM-friendly

PROPERTY NAMES:
  Run `yente-client ref schema Person` (or Company, Vessel, ...) to see what
  properties a schema accepts. Names are FtM camelCase: `firstName`, `birthDate`,
  `lastName`, `country`, `nationality` — not snake_case.

OUTPUT (with -f json):
  MatchResponse: {query: {...}, results: [ScoredEntity, ...], total, limit}
  Each ScoredEntity: {id, caption, schema, score (0-1), match (bool),
                      properties: {...}, datasets, target, explanations: {...}}

EXIT CODES:
  0  ≥1 result returned (may not have crossed threshold; check .match)
  1  zero results
  2  usage error (unknown schema, bad property, malformed -p)
  3  API error
  4  network/transport error

Use `search` instead for free-text discovery by name.
"""

_REF_SCHEMAS_EPILOG = """\
EXAMPLES:
  yente-client ref schemas                       # all schemas
  yente-client ref schemas --matchable           # only what you can `match` against
  yente-client ref schemas -f json               # for LLM consumption

For details on one schema (properties, types, deprecation flags):
  yente-client ref schema Person
"""

_REF_SCHEMA_EPILOG = """\
EXAMPLES:
  yente-client ref schema Person
  yente-client ref schema Company -f json        # full LLM-friendly summary
  yente-client ref schema Sanction -f jsonl      # one property per line

OUTPUT (with -f json):
  {name, label, description, matchable, abstract, extends, schemata,
   featured, required, properties: [{name, type, label, description,
   deprecated, from_schema}, ...]}

The property list is flat (own + inherited), excluding stub
(reverse-edge) properties that aren't user-settable.
"""
