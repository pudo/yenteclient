---
description: Design for a Python + TypeScript client SDK and a Python CLI for the yente / hosted OpenSanctions API. Public surface mirrors the planned /v2/match shape while the call layer targets the current v1 wire.
date: 2026-05-29
tags: [yente, sdk, cli, python, typescript, design]
---

# yente client SDK + CLI — design

## 1. Scope

Two client libraries and one CLI, in a single repo (`/home/pudo/code/yenteclient`):

- **`python/`** — `yente-client` on PyPI. Sync + async, both backed by `httpx`. Powers the CLI.
- **`typescript/`** — `@opensanctions/yente-client` on npm. ESM, native `fetch`.
- **`python/yente_client/cli/`** — `yente-client` CLI (binary name matches PyPI package), built on Typer, driving the Python SDK.

Both SDKs target **the hosted API and self-hosted yente from one client surface**: `base_url` defaults to `https://api.opensanctions.org`; passing an `api_key` adds `Authorization: ApiKey <key>`; omitting it works against self-hosted yente.

Both SDKs bake in the same FtM model snapshot (see §4.2), so the Python and TypeScript types cannot drift from each other or from the server.

**Guiding rule — design for `/v2/match` today, call `/v1` underneath.** The yente team has speccéd a cleaner v2 endpoint (issue #1100); the public SDK API mirrors that shape so user code is forward-compatible. The HTTP layer translates to the current `POST /match/{dataset}` wire on the way out. When v2 ships, only the translation layer changes.

**Non-goals (v1):** OpenRefine reconciliation helpers, `/statements` bulk export, `/updatez` admin flows. They can be added behind the same `Client` later; designing them is out of scope here.

## 2. API surface to cover

From the live OpenAPI (`https://api.opensanctions.org/openapi.json`, yente 5.4.0):

| Endpoint (v1 wire) | SDK method | CLI |
| --- | --- | --- |
| `POST /match/{dataset}` (one query at a time, see §4.7) | `client.match(entity, **filters)` → `MatchResponse` | `yente-client match` |
| same, looped client-side | `client.match_many(entities, workers=N)` → `list[MatchResponse]` | (consumed by `yente-client screen`) |
| same, streaming | `client.match_iter(entity_iter, workers=N)` → `Iterator[(key, MatchResponse)]` | `yente-client screen` |
| `GET /search/{dataset}` | `client.search(q, datasets=["default"], **opts)` → `SearchResponse` | `yente-client search` |
| `GET /entities/{id}` | `client.fetch(id, nested=True)` → `Entity` | `yente-client fetch` |
| `GET /entities/{id}/adjacent[/{prop}]` | `client.adjacent(id, prop=None, **paging)` | `yente-client fetch --adjacent` |
| `GET /catalog` | `client.catalog()` | `yente-client catalog` |
| `GET /algorithms` | `client.algorithms()` | `yente-client algorithms` |
| `GET /healthz` / `GET /readyz` | `client.healthz()` / `client.readyz()` | (ops only, no CLI v1) |

Deferred to a later iteration: `/reconcile/*`, `/statements`, `/updatez`.

## 3. Repo layout

```
yenteclient/
├── README.md                        # what this is, links to python/ and typescript/
├── Makefile                         # regen-model, test
├── plans/                           # design docs (this file lives here)
├── model/
│   └── model.json                   # canonical FtM model snapshot, committed
├── scripts/
│   ├── regen_model.py               # fetches model.json, fans out to each language
│   └── templates/
│       ├── python_entities.py.j2    # Jinja template for python entity classes
│       ├── python_literals.py.j2    # Schema / PropertyType / Topic Literal types
│       ├── ts_entities.ts.j2        # TS interfaces + builders
│       └── ts_literals.ts.j2        # Schema / Topic string-union types
├── python/
│   ├── pyproject.toml               # PyPI: yente-client
│   ├── src/yente_client/
│   │   ├── __init__.py              # exports Client, AsyncClient, MatchFilters, SearchFilters, exceptions
│   │   ├── client.py                # sync Client (httpx.Client)
│   │   ├── async_client.py          # AsyncClient (httpx.AsyncClient)
│   │   ├── _http.py                 # request building, retry, error mapping, v1<->v2 translation
│   │   ├── models.py                # pydantic response models (Entity, ScoredEntity, MatchResponse, ...)
│   │   ├── filters.py               # _CommonFilters, MatchFilters, SearchFilters
│   │   ├── exceptions.py            # YenteError hierarchy
│   │   ├── entities/
│   │   │   ├── __init__.py          # re-exports every schema class (regenerated)
│   │   │   ├── _base.py             # _EntityBase, EntityInput TypeAlias, _ensure_list
│   │   │   └── _generated.py        # 69 per-schema BaseModels; REGENERATED, do not edit by hand
│   │   ├── schemas/
│   │   │   ├── __init__.py          # exposes the raw model dict + lookup helpers
│   │   │   ├── _lookup.py           # has_schema, iter_properties, is_a, is_deprecated
│   │   │   ├── model.json           # copied from /model/model.json by regen
│   │   │   └── _literals.py         # generated Schema / PropertyType / Topic / Gender Literal types
│   │   ├── cli/
│   │   │   ├── __init__.py
│   │   │   ├── main.py              # `yente-client` entrypoint (Typer app)
│   │   │   ├── commands.py          # search, match, fetch, catalog, algorithms
│   │   │   └── output.py            # json / table / jsonl formatters
│   │   └── _version.py
│   └── tests/
│       ├── conftest.py              # respx-based fixtures
│       ├── test_client.py
│       ├── test_models.py
│       ├── test_entities.py
│       └── test_cli.py
├── typescript/
│   ├── package.json                 # npm: @opensanctions/yente-client
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts                 # Client + exports
│   │   ├── http.ts                  # request/response plumbing
│   │   ├── models.ts                # zod schemas → inferred TS types
│   │   ├── errors.ts
│   │   ├── filters.ts               # Filters type
│   │   ├── entities/
│   │   │   ├── index.ts             # re-exports every schema interface + builder
│   │   │   └── _generated.ts        # per-schema interfaces + builders; REGENERATED
│   │   ├── model.json               # copied from /model/model.json by regen
│   │   └── model.types.ts           # generated Schema / Topic string-union types
│   └── test/
├── testdata/                        # fixture JSON shared across language test suites
└── .github/workflows/ci.yml         # python {3.10–3.13} + node {20, 22}; runs `regen --check`
```

## 4. Python SDK design

### 4.1 Client surface

The public surface mirrors the planned v2 shape: one entity per `match` call, filters grouped under one logical roof, flat response with `query` + `results`.

```python
from yente_client import Client, AsyncClient, MatchFilters, SearchFilters
from yente_client.entities import Person, Company

with Client(api_key="...") as c:
    # Single — the common interactive case
    hits = c.match(
        Person(firstName="Aleksandr", lastName="Zacharov", birthDate="1965"),
        datasets=["sanctions"],
        topics=["sanction", "role.pep"],
        threshold=0.7,
        algorithm="best",
        changed_since="2022-02-24",
        exclude_entities=["Q7747"],
        exclude_schemata=["Address"],
    )
    # hits: MatchResponse(query=..., results=[ScoredEntity, ...], total=..., limit=...)
    if hits.top is not None:                     # None when results is empty
        print(hits.top.score, hits.top.caption)
    for h in hits.matches:                       # score >= threshold
        print(h.id, h.properties.get("topics", []))

    # Explicit filter object — useful when the same config is reused
    f = MatchFilters(datasets=["sanctions"], topics=["sanction"])
    hits = c.match(Person(name="Acme Holdings"), filters=f, threshold=0.7)

    # Many — pure client-side fan-out; one HTTP call per entity
    results: list[MatchResponse] = c.match_many(
        [Person(...), Person(...), Company(...)],
        datasets=["sanctions"],
        workers=4,
    )

    # Stream — for arbitrary-size inputs; yields as results return
    def queries():
        for row in csv_reader:
            yield row["customer_id"], Person(firstName=row["fn"], lastName=row["ln"])

    for key, hits in c.match_iter(queries(), datasets=["sanctions"], workers=8):
        write_row(key, hits)

    # Search uses the same dataset filter shape as match
    e = c.fetch("NK-aU5ybkbRFJucf8YMwsJvDw")        # follows 308 transparently
    res = c.search("acme", datasets=["default"], schema="Company", topics=["sanction"])

async with AsyncClient(api_key="...") as ac:
    hits = await ac.match(Person(firstName="X", lastName="Y"), datasets=["sanctions"])
    async for key, hits in ac.match_iter(queries(), workers=16):
        ...
```

**Sync ↔ async pairing:** `Client` and `AsyncClient` expose the same method *names* and kwarg sets. The differences are structural where the language requires them: `match` / `match_many` become coroutines (caller writes `await`), `match_iter` returns an `AsyncIterator` (caller writes `async for`). Both halves share one request-builder layer that produces `httpx.Request` + a parsing callback; each client wraps its own transport.

**Match-call semantics:**

- **Filter kwargs and `filters=` are merged** — kwargs override fields on a passed-in `MatchFilters` (or `SearchFilters` for `search`). Conflicting include/exclude (same value in `datasets` and `exclude_datasets`, etc.) raises `ValidationError` client-side before the HTTP call. Passing a search-only kwarg to `match` (or vice versa) is also a `ValidationError`.
- **`datasets` is `str | list[str] | dict`** — `"sanctions"` and `["sanctions"]` are equivalent. A `dict` is accepted for forward-compatibility with the planned dataset DSL (ftm #272); today it's serialized verbatim and the server may reject it, that's fine.
- **Structural pre-validation (names only)** — constructing a `Person` with an unknown kwarg raises immediately (`extra="forbid"` on every entity class). This matches v2's planned "400 on invalid properties" behaviour without a round-trip.
- **No value-level cleaning client-side** — we pass property values straight to the wire (after `str → list[str]` normalisation, which is type adaptation, not validation). Date parsing, name cleaning, country canonicalisation, identifier checksums, etc. are deliberately not attempted: doing them properly requires `normality` + `rigour` + the rest of the FtM stack, and an inexact reimplementation would be a footgun ("the SDK said it was valid, the server returned 400"). The server is the source of truth on values; the SDK ships errors back unchanged.

### 4.2 Type system — bundled FtM model + per-schema codegen

We **do not** depend on `followthemoney` at runtime. The single authoritative source baked into both SDKs is the published OpenSanctions model snapshot:

> **`https://data.opensanctions.org/meta/model.json`**

This is the same model the production stack and `yente` are pinned to, so client types cannot disagree with the server about what `Person.birthDate` is. It contains:

- `model.schemata` — 69 schemas, each with `schemata` (full ancestor chain, already flattened), `extends`, `featured`, `required`, `caption`, `temporalExtent`, `matchable`, and per-property `{type, label, description, maxLength, range, deprecated}`.
- `model.types` — 20 property types (`name`, `address`, `date`, `country`, `topic`, `gender`, …) with `matchable`, `group`, and enum `values` where applicable.
- `target_topics` and `enrich_topics` — flat lists of topics that flag an entity as a screening target / enrichment candidate.

A single canonical copy lives at **`model/model.json`** at the repo root, committed and refreshed via `make regen-model`.

#### 4.2.1 Per-schema pydantic classes (the headline ergonomic)

Dynamic generation via `pydantic.create_model` doesn't give static analysers anything to see, so IDE autocomplete and `mypy` / `pyright` get nothing. To get **perfect Python type annotations** — IDE field completion, refactoring tools, deprecation warnings on deprecated properties — we commit **generated `.py` files**, one BaseModel per schema, with properties flattened from the `schemata` ancestor chain.

```python
# python/src/yente_client/entities/_generated.py — REGENERATED, do not edit
from typing import ClassVar, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator
from ._base import _ensure_list, PropertyValue   # PropertyValue = str | list[str]


class _EntityBase(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")
    id: str | None = None
    schema_: ClassVar[str]                       # set on subclasses

    def to_payload(self) -> dict: ...            # serialises for /match


class Person(_EntityBase):
    """A natural person, as opposed to a corporation of some type."""
    schema_: ClassVar[Literal["Person"]] = "Person"

    name:        list[str] = Field(default_factory=list)
    firstName:   list[str] = Field(default_factory=list)
    lastName:    list[str] = Field(default_factory=list)
    middleName:  list[str] = Field(default_factory=list)
    birthDate:   list[str] = Field(default_factory=list)
    nationality: list[str] = Field(default_factory=list)
    country:     list[str] = Field(default_factory=list)   # inherited from LegalEntity
    topics:      list[str] = Field(default_factory=list)   # inherited from Thing
    # ... all own + inherited properties, flat ...

    _coerce = field_validator("*", mode="before")(_ensure_list)


class Company(_EntityBase):
    schema_: ClassVar[Literal["Company"]] = "Company"
    name:              list[str] = Field(default_factory=list)
    jurisdiction:      list[str] = Field(default_factory=list)
    incorporationDate: list[str] = Field(default_factory=list)
    ...
```

Properties of note:

- **Flat property set per class** — own + inherited via the `schemata` ancestor list. No MRO walk at runtime.
- **camelCase preserved** — matches wire format, matches docs, matches the bundled model. `Person(birth_date=...)` would not autocomplete and would raise `extra="forbid"`.
- **`Literal` discriminator on `schema_`** — type checkers can refine `_EntityBase` → `Person` after `isinstance` checks.
- **`list[str]` everywhere** — one wildcard `field_validator` normalises `str → [str]` so users can pass either.
- **`extra="forbid"`** — typos fail at construction, matching v2's planned 400-on-unknown-property behaviour.
- **Name-only validation, never values** — `extra="forbid"` rejects unknown kwargs (typos, properties not on the schema). Values are accepted as-is and forwarded. Proper value cleaning needs `normality` + `rigour` and is the server's job; a half-reimplementation would diverge over time and turn the SDK into an unreliable gate.
- **Deprecation surfacing (codegen-time only)** — properties marked `deprecated: true` in the model get a `# DEPRECATED: <description>` line above the field in the generated source. Shows up in IDE hover and code diffs. A runtime `DeprecationWarning` channel was considered and dropped for now — the codegen comment is sufficient signal until users ask for more.

#### 4.2.2 Runtime introspection

The `schemas/` package loads `model.json` at import time (~150 KB; cheap) and exposes the raw dict plus a few helpers. No Pydantic-typed wrappers — the codegen reads `model.json` directly, and users who want introspection get dict access:

```python
from yente_client.schemas import model, has_schema, is_a, iter_properties, is_deprecated

model["schemata"]["Person"]["properties"]["birthDate"]["type"]     # "date"
has_schema("Person")                                                # True
is_a("LegalEntity", "Thing")                                        # True
list(iter_properties("Person"))                                     # ["birthDate", "country", ...]
is_deprecated("Person", "secondName")                               # True
"sanction" in model["types"]["topic"]["values"]                     # True (full topic enum)
```

#### 4.2.3 Codegen pipeline

`scripts/regen_model.py` (plain stdlib `urllib` + `jinja2` for templating + `ruff format` as a postprocess; no FtM dep, no `wrangle` env coupling):

1. Fetch `https://data.opensanctions.org/meta/model.json`, write `model/model.json`.
2. Copy to `python/src/yente_client/schemas/model.json` and `typescript/src/model.json`.
3. Render `python/src/yente_client/entities/_generated.py` from `python_entities.py.j2`: one class per schema, properties flattened across `schemata`, deprecation markers preserved.
4. Render `python/src/yente_client/schemas/_literals.py` from `python_literals.py.j2`: `Schema = Literal["Person", ...]`, `PropertyType = Literal[...]`, `Topic = Literal[...]` (full 71-value enum from `model.types["topic"].values`), `Gender = Literal[...]`.
5. Run `ruff format` on the Python output. (TypeScript codegen lands with the TS SDK milestone — see §9.)

CI runs `python scripts/regen_model.py --check` and fails if any committed artefact differs from what the live model would generate. Upstream drift then surfaces as a normal PR review — release notes can call out additions, deprecations, removals.

**Why hand-rolled with Jinja, not `datamodel-code-generator`:** `model.json` is the FtM meta-model, not JSON Schema. Going through `datamodel-code-generator` would require a `model.json → JSON Schema` transformer first — roughly the same volume of code as the direct generator, with the loss of fine-grained control over the output (Literal placement, deprecation markers, classvar use). `openapi-python-client` would generate a full client and fight our hand-crafted v2-shaped surface. Hand-rolled wins at this scale because the inputs are well-defined and the outputs are opinionated.

### 4.3 Response models

Pydantic v2 models, mirroring the v2-flat response shape (translated from v1's `responses[key]` wrapper in the call layer):

```python
class Entity(BaseModel):
    id: str
    caption: str
    schema_: str = Field(alias="schema")
    properties: dict[str, list[str | Entity]]
    datasets: list[str] = []
    referents: list[str] = []
    target: bool = False
    first_seen: datetime | None = None
    last_seen: datetime | None = None
    last_change: datetime | None = None


class ScoredEntity(Entity):
    score: float
    match: bool
    explanations: dict[str, FeatureResult] = {}


class MatchResponse(BaseModel):
    """v2-shaped flat response. The v1 `responses[key]` envelope is unwrapped in the call layer."""
    query: dict
    results: list[ScoredEntity]
    total: TotalSpec
    limit: int

    @property
    def top(self) -> ScoredEntity | None: ...        # highest-scoring result, or None
    @property
    def matches(self) -> list[ScoredEntity]: ...     # filtered to match=True


class SearchResponse(BaseModel):
    results: list[Entity]
    facets: dict[str, SearchFacet] = {}
    total: TotalSpec
    limit: int
    offset: int
```

The recursive `Entity` (nested entities inside `properties`) is the only structural subtlety. Pydantic v2 handles forward refs cleanly.

### 4.4 Filters

`/match` and `/search` accept overlapping but non-identical filter sets. We split into two public types sharing a small base, so an irrelevant field can't silently no-op:

```python
class _CommonFilters(BaseModel):
    """Shared by MatchFilters and SearchFilters; do not use directly."""
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    datasets:         list[str] | None = None
    exclude_datasets: list[str] | None = None
    exclude_schemata: list[str] | None = None
    topics:           list[Topic] | None = None
    changed_since:    str | datetime | None = None


class MatchFilters(_CommonFilters):
    """Filters for client.match() / match_many() / match_iter()."""
    exclude_entities: list[str] | None = None


class SearchFilters(_CommonFilters):
    """Filters for client.search()."""
    countries: list[str] | None = None                   # ISO country codes
    schema_:   Schema | None = Field(default=None, alias="schema")
    filter_:   list[str] | None = Field(default=None, alias="filter")
    # `filter` and `schema` are Python-builtin / Pydantic-sensitive names;
    # populate_by_name=True means callers can still pass schema=/filter= as kwargs.
```

`extra="forbid"` on both filter types makes cross-endpoint typos fail at construction: passing `countries=` to `match()` raises because `MatchFilters` doesn't have that field, and vice versa. The server validates content (contradictory include/exclude, etc.) — we don't mirror that client-side.

**Kwargs flow:** every endpoint method accepts both `filters=` (the typed object) and **kwargs that name the filter's fields directly. Kwargs override fields on a passed `filters=` object.

`search()` signature:

```python
def search(
    self,
    q: str,
    *,
    filters: SearchFilters | None = None,
    limit: int | None = None,                            # server default 10, max 500
    offset: int = 0,                                     # max 9489
    sort: list[str] | None = None,
    fuzzy: bool = False,
    simple: bool = False,
    facets: list[str] | None = None,                     # defaults: countries, topics, datasets
    **filter_kwargs,                                     # merged into SearchFilters
) -> SearchResponse: ...
```

The `datasets` filter is translated to the v1 URL the same way as `match()` — first dataset → path param, rest → repeated `include_dataset` query params (see §4.8).

### 4.5 Errors

```
YenteError                  # base
├── ConfigurationError      # bad client config (e.g. empty base_url)
├── TransportError          # network / timeout
├── APIError                # any non-2xx with a JSON detail body
│   ├── BadRequestError     # 400
│   ├── AuthenticationError # 401, 403
│   ├── NotFoundError       # 404
│   ├── RateLimitError      # 429 (carries .retry_after if present)
│   └── ServerError         # 5xx
└── ValidationError         # client-side: unknown property/schema, contradictory filters,
                            # search-only kwarg on match() or vice versa
```

Every `APIError` carries `.status_code`, `.detail` (from the response body), and `.response` (raw `httpx.Response`). Client-side `ValidationError` is raised before any HTTP call.

### 4.6 HTTP, redirects, retries, timeouts

**Constructor surface (M2):**

```python
class Client:
    def __init__(
        self,
        *,
        # Auth / URL
        api_key: str | None = None,
        base_url: str = "https://api.opensanctions.org",

        # User-Agent
        app_name: str | None = None,                 # caller's app identifier, no version
        user_agent: str | None = None,               # escape hatch; overrides default UA entirely

        # HTTP behaviour
        timeout: float | httpx.Timeout | None = None,
        verify: bool | str = True,                   # SSL: False, or path to CA bundle
        proxy: str | None = None,                    # singular per httpx 0.27+
        headers: dict[str, str] | None = None,       # merged onto every request

        # Test seam
        transport: httpx.BaseTransport | None = None,
    ) -> None: ...
```

**Behaviour:**

- **Transport:** `httpx.Client` / `AsyncClient` with `follow_redirects=True`. The `308` on `/entities/{referent}` → `/entities/{canonical}` is followed transparently.
- **Timeout:** default `httpx.Timeout(30.0, connect=10.0)`; overridable via `timeout=`.
- **Retries:** **deferred past M2.** Transient failures (429, 5xx, network errors) bubble up as `APIError` / `TransportError` for users to handle. We'll add a `RetryPolicy` + `retry=` kwarg when there's a concrete need (probably alongside `match_many` / `match_iter` in M5, where it matters most). httpx's connection-level transport retries (`HTTPTransport(retries=2)`) stay on, so DNS / connection-refused failures already get a free retry.
- **Auth header:** when `api_key` is set, attach `Authorization: ApiKey {key}` to every request. When missing and `base_url` points at `api.opensanctions.org`, emit `warnings.warn` once — not an exception (self-hosted setups don't need keys).
- **User-Agent:** RFC-7231 bracket-comment form. The product is always `yente-client/{ver}`; caller's `app_name` and runtime versions sit in the parenthesised comment:
  - No `app_name`: `yente-client/0.0.1 (python/3.12.5; httpx/0.28.1)`
  - With `app_name="MyScreeningApp"`: `yente-client/0.0.1 (MyScreeningApp; python/3.12.5; httpx/0.28.1)`
  - With `user_agent=...`: the whole string is replaced verbatim (no concat). `app_name` is ignored in that case.

  Versions come from `importlib.metadata.version("yente-client")` and `httpx.__version__` at import time — no hand-edited `_version.py`. `app_name` is validated to reject characters that would break UA grammar (whitespace, parens, semicolons); invalid values raise `ConfigurationError` at construct time.

- **Headers:** caller-supplied `headers=` are merged onto every request; `Authorization` and `User-Agent` set by the client take precedence (caller can't accidentally clobber them, since auth/UA are applied last).
- **List query parameters:** httpx serialises `list[str]` as repeated keys natively (`include_dataset=a&include_dataset=b`); we always pass lists.
- **Test seam:** `transport=` accepts `httpx.MockTransport` (or `httpx.AsyncBaseTransport` for the async client) so `respx`-driven tests can intercept without monkey-patching.

### 4.7 One HTTP call per match — never wire-level batching

**Rule:** every `match()` call issues exactly one `POST /match/{dataset}` request with `queries={"q": <entity>}`. Wire-level batching is disabled by design.

Why:

- The yente team has observed wire-level batching to be a performance anti-pattern (issue #1100): a single slow query in a batch holds up the whole response, and server-side parallelism saturates differently than client-side parallelism.
- `/v2/match` will drop wire-level batching entirely. By restricting ourselves now, the migration is a no-op.

Public type alias for entity inputs (used in the signatures below):

```python
# in yente_client.entities
EntityInput: TypeAlias = _EntityBase            # any per-schema class: Person, Company, Vessel, ...
```

Three public methods, sharing one set of match-side kwargs (`filters`, `threshold`, `algorithm`, `weights`, `config`, `limit`):

```python
def match(
    self,
    entity: EntityInput,
    *,
    filters: MatchFilters | None = None,
    threshold: float | None = None,             # server default 0.70
    algorithm: str | None = None,               # server default "best"
    weights: dict[str, float] | None = None,
    config: dict | None = None,
    limit: int | None = None,                   # results per query; server default 5, max 500
    **filter_kwargs,                            # merged into MatchFilters
) -> MatchResponse:
    """One /match call. The dominant interactive case."""
    ...

def match_many(
    self,
    entities: Sequence[EntityInput],
    *,
    workers: int = 4,
    filters: MatchFilters | None = None,
    threshold: float | None = None,
    algorithm: str | None = None,
    weights: dict[str, float] | None = None,
    config: dict | None = None,
    limit: int | None = None,
    on_error: Literal["raise", "collect"] = "raise",
    **filter_kwargs,
) -> list[MatchResponse]:
    """Run /match for each entity in parallel; return results in input order."""
    ...

def match_iter(
    self,
    entities: Iterable[tuple[str, EntityInput]],   # (key, entity) pairs
    *,
    workers: int = 4,
    filters: MatchFilters | None = None,
    threshold: float | None = None,
    algorithm: str | None = None,
    weights: dict[str, float] | None = None,
    config: dict | None = None,
    limit: int | None = None,
    on_error: Literal["raise", "collect"] = "raise",
    **filter_kwargs,
) -> Iterator[tuple[str, MatchResponse]]:
    """Stream /match over an iterable; yield (key, response) as each completes.
    Order is completion order, not input order — the key disambiguates."""
    ...
```

The async variants (`AsyncClient.match`, `.match_many`, `.match_iter`) have identical kwargs; `match` and `match_many` become coroutines, and `match_iter` returns an `AsyncIterator`.

Implementation:

- **Sync:** `ThreadPoolExecutor(max_workers=workers)`. `match_iter` uses `as_completed`; `match_many` collects and reorders.
- **Async:** an `asyncio.Semaphore(workers)` bounds concurrency. `match_iter` is an `async for`-friendly generator.
- **Backpressure:** `match_iter` submits one new task per yielded result, so the in-flight set stays at `~workers` regardless of how big the input iterable is.
- **Errors:** by default a failed item raises and cancels in-flight work; with `on_error="collect"` errors are returned in-band as `MatchError(key=..., exception=...)` so a large run can continue.
- **Rate limits:** the same `RetryPolicy` applies per call; a 429 with `Retry-After` pauses *that* worker, others continue.

The threaded CSV CLI (`yente-client screen`, §5.5) is a thin shell around `match_iter` — same retry policy, same backpressure.

### 4.8 v1 ↔ v2 translation map

The call layer in `_http.py` translates the v2-shaped public API to the current v1 wire. When `/v2/match` ships, this layer changes URL, body, and response parsing; no public-facing rename.

| SDK / v2 (public) | v1 wire (today) |
| --- | --- |
| `client.match(entity, datasets=["sanctions"])` | `POST /match/sanctions` with `queries={"q": entity}` |
| `client.match(entity, datasets=["sanctions", "us_ofac_sdn"])` | `POST /match/sanctions` with query param `include_dataset=us_ofac_sdn` |
| `filters.exclude_entities` | query param `exclude_entity_ids` |
| `filters.exclude_schemata` | query param `exclude_schema` |
| `filters.exclude_datasets` | query param `exclude_dataset` |
| `filters.changed_since` (str or datetime) | query param `changed_since` (ISO 8601 str) |
| `MatchResponse(query, results, total, limit)` | unwrapped from `raw["responses"]["q"]` plus top-level `limit` |
| Strict 400 on unknown property name | enforced client-side via `extra="forbid"` (names only — values pass through) |

The unwrap is the one structural asymmetry: v1 wraps the result in `responses["q"]`; v2 returns it flat. The call layer unwraps unconditionally so the public response shape is stable.

## 5. CLI design

### 5.1 Commands (v1)

```
yente-client search QUERY [--datasets default]                    # repeatable
                   [--schema Thing]                        # entity-type filter
                   [--limit 10] [--offset 0]
                   [--topics sanction --topics role.pep]   # repeatable
                   [--countries ru]                        # repeatable
                   [--filter properties.birthDate:1985]    # repeatable
                   [--format json|jsonl|table]

yente-client match  --schema Person                               # entity type to construct
             [-p KEY=VALUE] [-p ...]                       # universal property setter; `--property` is the long form
             [--from-file query.json]                      # see format note below
             [--datasets sanctions]                        # repeatable
             [--topics sanction --topics role.pep]
             [--threshold 0.7] [--algorithm best] [--limit 10]
             [--changed-since 2022-02-24]
             [--exclude-entities Q7747]                    # repeatable
             [--exclude-schemata Address]                  # repeatable
             [--format json|table]

yente-client fetch  ENTITY_ID
             [--nested/--no-nested]
             [--adjacent PROPERTY]                         # paginated adjacency
             [--limit 10] [--offset 0]
             [--format json|table]

yente-client catalog    [--current-only] [--format json|table]
yente-client algorithms [--format json|table]
```

Notes:

- `--datasets` (plural) is used by both `search` and `match`; the CLI translates the same way the SDK does (first → URL path param, rest → repeated `include_dataset` query params). See §4.8.
- `--schema` is overloaded by context: on `yente-client search` it filters results by entity type; on `yente-client match` it specifies the type of entity being constructed from the other flags. Acceptable because each command has only one natural meaning for it.
- `--from-file path.json` (for `yente-client match`) reads a JSON document of shape `{"schema": "...", "properties": {...}}` — the wire-format match query. The CLI looks up the schema name in the bundled model, constructs the matching per-schema class, and feeds it to `match()`. Flag-derived properties (`-p KEY=VALUE`) merge into / override the file's properties.
- `-p` / `--property KEY=VALUE` is the universal property setter on `match`. Repeatable; same key passed twice produces a multi-value property. No per-schema shortcuts (`--first-name` etc.) — the property name on the wire is always what you'd find in the FtM model (`firstName`, `birthDate`, …). Unknown property names fail at construction with a clear pydantic message.
- The CLI extra `[cli]` pulls in Typer + Rich. Users who install `yente-client` without the extra and try to invoke the binary get a single-line error pointing them at `pip install yente-client[cli]` — see `yente_client.cli._deps` for the import-shim that emits it.
- CLI flag names follow the v2 conventions (`--datasets`, `--exclude-entities`, `--exclude-schemata`). The translation to v1 is identical to the SDK's.

### 5.2 Config precedence

1. CLI flag
2. Environment variable (`OPENSANCTIONS_API_KEY`, `YENTE_BASE_URL`)
3. Config file at `${XDG_CONFIG_HOME:-~/.config}/yente/config.toml` (`[default]` section)
4. Compiled defaults

`OPENSANCTIONS_API_KEY` is the canonical env var, matching the official quickstart.

### 5.3 Output formats

- **`--format json`** (default for piping) — single JSON document, matching the v2-flat shape (`{query, results, total, limit}` for `match`).
- **`--format jsonl`** — one entity / hit per line. Useful for `jq` and the `screen` command.
- **`--format table`** (default for TTY, auto-detected) — Rich table; columns for `match`: `score | id | caption | datasets | topics`. Truncates long captions; full record available via `yente-client fetch ID`.

### 5.4 Exit codes

- `0` — success, at least one result (or any result for `fetch`/`catalog`).
- `1` — success, zero results.
- `2` — usage error (bad flag, malformed input).
- `3` — API error (non-2xx response).
- `4` — transport error (network, timeout).

The zero-results-as-1 convention is deliberate: it lets shell scripts use `yente-client match … && …` to gate on "we found something."

### 5.5 v2 — `yente-client screen`

```
yente-client screen INPUT.csv
             --schema Person
             --map first_name:firstName --map last_name:lastName --map dob:birthDate
             [--id-col customer_id]                # used as the per-row key
             [--datasets sanctions]
             [--threshold 0.7]
             [--workers 8]
             [-o OUTPUT.jsonl]
             [--resume RESUME_FILE]                # for restartability
```

Built on `match_iter`. Streams output as it goes; resumable state file records completed input row IDs. No `--batch-size` flag — wire batch size is always 1, only `--workers` matters.

## 6. TypeScript SDK design

```ts
import { Client, Person } from "@opensanctions/yente-client";

const client = new Client({ apiKey: process.env.OPENSANCTIONS_API_KEY });

const hits = await client.match(
  new Person({ firstName: "Aleksandr", lastName: "Zacharov", birthDate: "1965" }),
  {
    datasets: ["sanctions"],
    topics: ["sanction"],
    threshold: 0.7,
    algorithm: "best",
  },
);

console.log(hits.top?.score, hits.top?.caption);
for (const h of hits.matches) {
  console.log(h.id, h.properties.topics);
}
```

Notes:

- **One `Client`** — JS is async-by-default, so no sync/async split.
- **Transport:** native `fetch` (Node 20+, deno, modern browsers). No `axios`.
- **Schema types:** generated from the same `model/model.json` snapshot the Python SDK uses (§4.2). `entities/_generated.ts` exports a class per schema with typed kwargs; `model.types.ts` exports `Schema`, `PropertyType`, `TargetTopic` string unions. `@alephdata/followthemoney` is **not** a dependency — the bundled snapshot keeps both SDKs locked to the same model version.
- **Match shape:** same v2-flat response; same one-call-per-entity rule; `matchMany` and `matchIter` for fan-out using `Promise.all` with a `p-limit`-style semaphore.
- **Bundling:** ESM only. CJS interop via Node's auto-resolution.
- **Errors:** parallel hierarchy (`YenteError`, `ApiError`, `RateLimitError`, …) with `.statusCode` and `.detail`.
- **Browser caveat:** the hosted API allows CORS, but exposing API keys in browser JS is a bad idea. Document this; do not block the use case.

## 7. Testing

- **Python:** `pytest` + `respx` (mock httpx). Fixtures include captured response bodies for `/match`, `/search`, `/entities`, `/catalog`. CLI tests use `Typer`'s `CliRunner`. Generator tests assert that `regen --check` is idempotent and that the generated entity classes round-trip through `model.json` correctly. A small "live" suite runs against the public API gated on `OPENSANCTIONS_API_KEY`; off by default in CI.
- **TypeScript:** `vitest` + `msw` for fetch mocking. Same fixture corpus shared with the Python side under `testdata/` (top-level, language-agnostic).

## 8. Release / packaging

- **PyPI** — `yente-client`. Build with `hatch`. Wheel + sdist. Semver, starting `0.1.0`.
- **npm** — `@opensanctions/yente-client`. Built with `tsup`. Semver, starting `0.1.0`.
- **CI:** GitHub Actions matrix; lint (`ruff`, `mypy`, `eslint`, `tsc --noEmit`) + tests + `regen --check`. Release on tag.
- **Docs:** README in each language folder with a quickstart that mirrors the official OpenSanctions quickstart, so a user finding either entry point lands on the same shape. Auto-generated API docs deferred.

## 9. Milestones

1. **Python codegen pipeline + entity classes + literal types** — `scripts/regen_model.py`, Python Jinja templates, committed `model/model.json`, generated `python/src/yente_client/entities/_generated.py` and `schemas/_literals.py`. CI `--check`. No HTTP client yet. End: `from yente_client.entities import Person` is importable; `mypy --strict` passes on the generated module; `regen --check` is idempotent. See the dedicated M1 plan in `plans/2026-05-29-m1-python-codegen.md` for the breakdown.
2. **Python sync Client + response models + errors + tests** — covers `match` (v2-shaped surface, v1 wire), `search`, `fetch`, `adjacent`, `catalog`, `algorithms`, `healthz`, `readyz`. Builds on M1's generated entities and bundled model. No async, no CLI. End: `yente-client` installable from source; tests pass against fixtures.
3. **AsyncClient** — parity with `Client`, reusing the request-builder layer.
4. **CLI MVP** — `yente-client search` / `match` / `fetch` / `catalog` / `algorithms`. JSON / JSONL / table formatters. Config precedence + env var handling. Single-call only — bulk workflows wait for the fan-out kernel in M5. End: a working CLI that drives the existing Client end-to-end.
5. **`match_many` / `match_iter`** — client-side fan-out, threaded + async, with bounded concurrency and `on_error` policy. SDK-level only at this stage; the CLI gets its bulk command in M7.
6. **TypeScript SDK v1** — `Client` + models + errors + entities. Native fetch. zod-based response validation. Extends the regen pipeline with TS Jinja templates so both languages stay model-locked.
7. **`yente-client screen` CLI** — threaded CSV screening, resumable, built on `match_iter` (M5). Bulk-workflow surface that turns the SDK into a useful command-line screening tool.
8. **First publish** — PyPI + npm 0.1.0, README quickstarts, GitHub Actions release on tag. Pushed back from earlier to keep the first release feature-complete (CLI single + bulk + TS).
9. **Coverage gaps** — `/reconcile/*`, `/statements`, `/updatez`. Added as separate methods; no API redesign needed.
10. **`/v2/match` cut-over** — when the server ships v2, rewrite the call layer in `_http.py` only. Public API unchanged; users get strict 400 errors and dataset DSL for free.

**Sequencing rationale:** the CLI MVP (M4) precedes the fan-out kernel (M5) so we get a user-facing command-line tool early, and `match_many` / `match_iter` are designed with a known concrete consumer (`yente-client screen` in M7). Publishing waits until both the single-call and bulk CLI exist so first-impression users don't see an obviously incomplete tool.

Stop and check in at the end of each milestone. Especially before publishing (step 8) — that's a one-way door.

## 10. Open questions to revisit

- **`MatchFilters`/`SearchFilters` object vs kwargs as canonical**: both are supported; the docs need to pick one as primary in examples. Lean: kwargs (concise; matches the §4.1 examples). Filter objects are for reusable configs and for callers that build them programmatically.
- **`/v2/match` self-hosted yente compatibility**: when v2 ships, do we keep the v1 call layer available for users running older yente builds, or just bump SDK major and drop v1? Lean: minor-version coexistence (the call layer probes `/v2/match` once per client and falls back to v1).
- **`/statements`**: shape and pagination semantics weren't fully surveyed. Worth a short read of `yente/routers/` before milestone 9.
- **Browser bundle for TS**: ship a separate browser-targeted bundle, or punt to Vite/Webpack from the ESM source? Lean: punt unless the website team wants something specific.
- **Model snapshot drift policy**: when CI's `regen --check` fails because upstream `model.json` moved, do we auto-PR the diff (bot commit) or surface it for human review? Lean: human review — a property rename or removal can break user code and should be in release notes.
