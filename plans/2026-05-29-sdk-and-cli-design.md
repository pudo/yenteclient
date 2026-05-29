---
description: Initial design for a Python + TypeScript client SDK and a Python CLI for the yente / hosted OpenSanctions API.
date: 2026-05-29
tags: [yente, sdk, cli, python, typescript, design]
---

# yente client SDK + CLI — design

## 1. Scope

Two client libraries and one CLI, in a single repo (`/home/pudo/code/yenteclient`):

- **`python/`** — `yente-client` on PyPI. Sync + async, both backed by `httpx`. Powers the CLI.
- **`typescript/`** — `@opensanctions/yente-client` on npm. ESM, native `fetch`, types via `@alephdata/followthemoney`.
- **`python/yente_client/cli/`** — `yente` CLI, built on Typer, driving the Python SDK.

Both SDKs target **the hosted API and self-hosted yente from one client surface**: `base_url` defaults to `https://api.opensanctions.org`; passing an `api_key` adds `Authorization: ApiKey <key>`; omitting it works against self-hosted yente.

**Non-goals (v1):** OpenRefine reconciliation helpers, `/statements` bulk export, `/updatez` admin flows. They can be added behind the same `Client` later; designing them is out of scope here.

## 2. API surface to cover

From the live OpenAPI (`https://api.opensanctions.org/openapi.json`, yente 5.4.0):

| Endpoint | SDK method | CLI |
| --- | --- | --- |
| `POST /match/{dataset}` | `client.match(queries, dataset="default", **opts)` | `yente match` |
| `GET /search/{dataset}` | `client.search(q, dataset="default", **opts)` | `yente search` |
| `GET /entities/{id}` | `client.fetch(id, nested=True)` | `yente fetch` |
| `GET /entities/{id}/adjacent[/{prop}]` | `client.adjacent(id, prop=None, **paging)` | `yente fetch --adjacent` |
| `GET /catalog` | `client.catalog()` | `yente catalog` |
| `GET /algorithms` | `client.algorithms()` | `yente algorithms` |
| `GET /healthz` / `GET /readyz` | `client.healthz()` / `client.readyz()` | (ops only, no CLI v1) |

Deferred to a later iteration: `/reconcile/*`, `/statements`, `/updatez`.

## 3. Repo layout

```
yenteclient/
├── README.md                        # what this is, links to python/ and typescript/
├── plans/                           # design docs (this file lives here)
├── python/
│   ├── pyproject.toml               # PyPI: yente-client
│   ├── src/yente_client/
│   │   ├── __init__.py              # exports Client, AsyncClient, models, exceptions
│   │   ├── client.py                # sync Client (httpx.Client)
│   │   ├── async_client.py          # AsyncClient (httpx.AsyncClient)
│   │   ├── _http.py                 # shared request building, error mapping
│   │   ├── models.py                # pydantic response models
│   │   ├── exceptions.py            # YenteError hierarchy
│   │   ├── schemas/
│   │   │   ├── __init__.py          # loads schemas.json
│   │   │   ├── schemas.json         # generated, committed
│   │   │   └── _literals.py         # generated Literal types for autocomplete
│   │   ├── cli/
│   │   │   ├── __init__.py
│   │   │   ├── main.py              # `yente` entrypoint (Typer app)
│   │   │   ├── commands.py          # search, match, fetch, catalog, algorithms
│   │   │   └── output.py            # json / table / jsonl formatters
│   │   └── _version.py
│   ├── scripts/regen_schemas.py     # pulls from followthemoney, writes schemas.json + _literals.py
│   └── tests/
│       ├── conftest.py              # respx-based fixtures
│       ├── test_client.py
│       ├── test_models.py
│       └── test_cli.py
├── typescript/
│   ├── package.json                 # npm: @opensanctions/yente-client
│   ├── tsconfig.json
│   ├── src/
│   │   ├── index.ts                 # Client, AsyncClient (or just Client; see §6)
│   │   ├── http.ts                  # request/response plumbing
│   │   ├── models.ts                # zod schemas → inferred TS types
│   │   └── errors.ts
│   └── test/
└── .github/workflows/ci.yml         # matrix: python {3.10,3.11,3.12,3.13} + node {20,22}
```

## 4. Python SDK design

### 4.1 Client surface

```python
from yente_client import Client, AsyncClient
from yente_client.models import MatchResponse, SearchResponse, Entity

with Client(api_key="...") as c:
    out: MatchResponse = c.match(
        queries={"alpha": {"schema": "Person",
                            "properties": {"firstName": ["Aleksandr"],
                                          "lastName": ["Zacharov"]}}},
        dataset="default",
        threshold=0.7,
        algorithm="best",
        topics=["sanction"],
    )
    for hit in out.responses["alpha"].results:
        print(hit.id, hit.score, hit.caption)

    e: Entity = c.fetch("NK-aU5ybkbRFJucf8YMwsJvDw")
    for s in e.properties.get("sanctions", []):
        print(s.properties["authority"])

async with AsyncClient(api_key="...") as ac:
    out = await ac.match(...)
```

Symmetry rule: `Client` and `AsyncClient` expose the **same method names and signatures**; the only difference is `await`. Achieved by routing both through a single `_RequestBuilder` that produces `httpx.Request` + a parsing callback; each client wraps its own transport.

### 4.2 Type system — lightweight FtM

We **do not** depend on `followthemoney` at runtime. We ship a generated artefact under `yente_client/schemas/`:

- **`schemas.json`** — flat map: `{schema_name: {"parent": str|None, "extends": [str], "properties": {prop_name: {"type": str, "schema_range": str|None}}}}`. Generated from the local `followthemoney` checkout via `scripts/regen_schemas.py`. ~50 KB; committed to the repo.
- **`_literals.py`** — generated `Schema = Literal["Person", "Company", ...]`. Used for IDE autocomplete and `mypy` checks. Regenerated alongside `schemas.json`.

At runtime we load `schemas.json` lazily on first use. The schema module exposes:

```python
from yente_client.schemas import schemas, is_a, property_type

schemas["Person"].properties["birthDate"].type  # "date"
is_a("LegalEntity", "Thing")                    # True
```

The point is **type hinting + light validation**, not full FtM parity. We don't transliterate, normalize, or validate property values — the server does that.

**Input ergonomics:** `match()` accepts either a plain dict (`{"schema": "Person", "properties": {...}}`) or a `MatchInput` TypedDict. Property values can be `str | list[str]` and we coerce to lists internally.

**Schema regeneration:** `make regen-schemas` runs `scripts/regen_schemas.py` using the user's local `followthemoney` checkout (`/home/pudo/code/followthemoney`) — invoked via `/home/pudo/.venv/wrangle/bin/python` per CLAUDE.md. The script writes `schemas.json` and `_literals.py`. Both are committed; CI verifies they're up to date with whatever followthemoney version is pinned.

### 4.3 Response models

Pydantic v2 models, lifted directly from `yente/data/common.py`:

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

class MatchResults(BaseModel):
    status: int
    results: list[ScoredEntity]
    total: TotalSpec
    query: dict

class MatchResponse(BaseModel):
    responses: dict[str, MatchResults]
    limit: int

class SearchResponse(BaseModel):
    results: list[Entity]
    facets: dict[str, SearchFacet] = {}
    total: TotalSpec
    limit: int
    offset: int
```

The recursive `Entity` (nested entities inside `properties`) is the only structural subtlety. Pydantic handles forward refs cleanly.

### 4.4 Errors

```
YenteError                  # base
├── ConfigurationError      # missing api_key when hosted base_url is used (warn, not raise — see §4.5)
├── TransportError          # network/timeout
├── APIError                # any non-2xx with a JSON detail body
│   ├── BadRequestError     # 400
│   ├── AuthenticationError # 401, 403
│   ├── NotFoundError       # 404
│   ├── RateLimitError      # 429 (carries .retry_after if present)
│   └── ServerError         # 5xx
```

Every `APIError` carries `.status_code`, `.detail` (from the response body's `detail` field), and `.response` (raw `httpx.Response`).

### 4.5 HTTP, redirects, retries, timeouts

- **Transport:** `httpx.Client` / `AsyncClient` with `follow_redirects=True`. The `308` on `/entities/{referent}` → `/entities/{canonical}` is followed transparently.
- **Timeout:** default `httpx.Timeout(30.0, connect=10.0)`; overridable via `Client(timeout=...)`.
- **Retries:** `httpx`'s transport supports retries on connection errors only. For HTTP-level retries (429, 502, 503, 504), we use a small wrapper: exponential backoff (base 0.5s, factor 2, max 4 attempts, max delay 16s, plus full jitter). Honoring `Retry-After` when present on 429. Configurable via `Client(retry=RetryPolicy(...))`.
- **Auth header:** when `api_key` is set, we attach `Authorization: ApiKey {key}` to every request. When missing and `base_url` points at `api.opensanctions.org`, we emit a `warnings.warn` once — not an exception (self-hosted setups don't need keys, and the user may be on an internal proxy).
- **User-Agent:** `yente-client/{version} python/{py_version}` — useful for hosted-side telemetry.

### 4.6 List-valued query parameters

Yente's `/search` and `/match` take repeated query params (`include_dataset=a&include_dataset=b`). `httpx` handles `list` values natively. We accept both `str` and `list[str]` in the SDK and normalize to lists.

### 4.7 Bulk-screening helpers (v2, but designed now)

```python
def match_iter(
    self,
    queries: Iterable[tuple[str, MatchInput]],   # (key, entity) tuples
    dataset: str = "default",
    batch_size: int = 100,
    workers: int = 4,
    **opts,
) -> Iterator[tuple[str, MatchResults]]:
    ...
```

- Chunks input into batches of `MAX_BATCH=100`.
- Submits batches across `workers` threads (sync) or via `asyncio.gather` (async).
- Yields per-query results as they complete. Order matches input only if `workers=1`.
- Each chunk failure raises with which keys were in flight; the iterator does not silently drop work.

The threaded CSV CLI (`yente screen`) is a thin shell around this — same retry policy, same backpressure. Designing the kernel now keeps the CLI a wrapper rather than a re-implementation.

## 5. CLI design

### 5.1 Commands (v1)

```
yente search QUERY [--dataset default] [--schema Thing]
                   [--limit 10] [--offset 0]
                   [--topics sanction --topics role.pep]
                   [--country ru] [--filter properties.birthDate:1985]
                   [--format json|jsonl|table]

yente match  --schema Person
             [--first-name X] [--last-name Y] [--birth-date 1965]
             [--property name=Acme]                 # repeatable, schema-agnostic
             [--from-file query.json]               # alternative to flags
             [--dataset default] [--threshold 0.7]
             [--algorithm best]
             [--topics sanction]
             [--format json|table]

yente fetch  ENTITY_ID
             [--nested/--no-nested]
             [--adjacent PROPERTY]                  # paginated adjacency
             [--limit 10] [--offset 0]
             [--format json|table]

yente catalog    [--current-only] [--format json|table]
yente algorithms [--format json|table]
```

### 5.2 Config precedence

1. CLI flag
2. Environment variable (`OPENSANCTIONS_API_KEY`, `YENTE_BASE_URL`)
3. Config file at `${XDG_CONFIG_HOME:-~/.config}/yente/config.toml` (`[default]` section)
4. Compiled defaults

`OPENSANCTIONS_API_KEY` is the canonical env var, matching the official quickstart.

### 5.3 Output formats

- **`--format json`** (default for piping) — single JSON document. Identical to the API response.
- **`--format jsonl`** — one entity / hit per line. Useful for `jq` and for the future `screen` command.
- **`--format table`** (default for TTY, auto-detected) — Rich table, columns: `score | id | caption | datasets | topics`. Truncates long captions; full record available via `yente fetch ID`.

### 5.4 Exit codes

- `0` — success, at least one result (or any result for `fetch`/`catalog`).
- `1` — success, zero results.
- `2` — usage error (bad flag, malformed input).
- `3` — API error (non-2xx response).
- `4` — transport error (network, timeout).

The zero-results-as-1 convention is deliberate: it lets shell scripts use `yente match … && …` to gate on "we found something."

### 5.5 v2 — `yente screen`

```
yente screen INPUT.csv
             --schema Person
             --map first_name:firstName --map last_name:lastName --map dob:birthDate
             [--id-col customer_id]                # used as the query key
             [--dataset default] [--threshold 0.7]
             [--workers 4] [--batch-size 100]
             [-o OUTPUT.jsonl]
             [--resume RESUME_FILE]                # for restartability
```

Built on `match_iter`. Streams output as it goes; resumable state file records completed input row IDs.

## 6. TypeScript SDK design

```ts
import { Client } from "@opensanctions/yente-client";

const client = new Client({ apiKey: process.env.OPENSANCTIONS_API_KEY });

const out = await client.match({
  dataset: "default",
  queries: { alpha: { schema: "Person", properties: { firstName: ["Aleksandr"], lastName: ["Zacharov"] } } },
  threshold: 0.7,
  algorithm: "best",
});

for (const hit of out.responses.alpha.results) {
  console.log(hit.id, hit.score, hit.caption);
}
```

Notes:

- **One `Client`** — JS is async-by-default, so no need for a sync/async split. Every method returns a `Promise`.
- **Transport:** native `fetch` (Node 20+, deno, modern browsers). No `axios`.
- **Schema types:** use `@alephdata/followthemoney`'s exported schema name unions where they exist. For our response models, declare `zod` schemas (giving runtime validation in addition to TS types). If `@alephdata/followthemoney`'s TS types are too thin, fall back to a generated `Schema` union from the same `schemas.json` we generate for Python.
- **Bundling:** ESM only. CJS interop via Node's auto-resolution; we don't ship a separate `.cjs` bundle.
- **Errors:** parallel hierarchy (`YenteError`, `ApiError`, `RateLimitError`, …) with the same `.statusCode` and `.detail` shape.
- **Browser caveat:** the hosted API allows CORS, but exposing API keys in browser JS is a bad idea. Document this; do not block the use case.

## 7. Testing

- **Python:** `pytest` + `respx` (mock httpx). Fixtures include captured response bodies for `/match`, `/search`, `/entities`, `/catalog`. CLI tests use `Typer`'s `CliRunner`. A small "live" suite runs against the public API gated by `OPENSANCTIONS_API_KEY` being set in env; off by default in CI.
- **TypeScript:** `vitest` + `msw` for fetch mocking. Same fixture corpus shared with the Python side under `testdata/` (top-level, language-agnostic).

## 8. Release / packaging

- **PyPI** — `yente-client`. Build with `hatch`. Wheel + sdist. Versioning: semver, starting `0.1.0`.
- **npm** — `@opensanctions/yente-client`. Built with `tsup`. Versioning: semver, starting `0.1.0`.
- **CI:** GitHub Actions matrix; lint (`ruff`, `mypy`, `eslint`, `tsc --noEmit`) + tests. Release on tag.
- **Docs:** README in each language folder with a quickstart that mirrors the official OpenSanctions quickstart, so a user finding either entry point lands on the same shape. Auto-generated API docs deferred.

## 9. Milestones

1. **Skeleton + Python sync client + models + errors + tests** — covers `match`, `search`, `fetch`, `catalog`, `algorithms`, `healthz`, `readyz`. No CLI, no async, no schemas.json. End: `yente-client` 0.1 installable from source.
2. **Schemas.json + Literal types + property type hints** — `regen_schemas.py`, generated artefacts, CI check.
3. **AsyncClient** — parity with `Client`, reusing the request-builder layer.
4. **CLI v1** — `search`, `match`, `fetch`, `catalog`, `algorithms`. JSON / JSONL / table formatters. Config precedence + env var handling.
5. **TypeScript SDK v1** — `Client` + models + errors. Native fetch. zod-based response validation.
6. **First publish** — PyPI + npm 0.1.0, README quickstarts, GitHub Actions release on tag.
7. **`match_iter` + `yente screen`** — threaded CSV screening, resumable. The point where the CLI starts paying for itself in real workflows.
8. **Coverage gaps** — `/reconcile/*`, `/statements`, `/updatez`. Added as separate methods; no API redesign needed.

Stop and check in at the end of each milestone. Especially before publishing (step 6) — that's a one-way door.

## 10. Open questions to revisit

- **`/statements`**: shape and pagination semantics weren't fully surveyed (the Explore agent skipped its details). Worth a short read of `yente/routers/` before milestone 8.
- **Schema generation invocation**: do we want `regen_schemas.py` to dynamically resolve the `followthemoney` package, or to read its YAML files directly from `/home/pudo/code/followthemoney/followthemoney/schema/*.yaml`? The latter is more reproducible and avoids any Python-env coupling. Decide before milestone 2.
- **Browser bundle for TS**: do we ship a separate browser-targeted bundle, or punt and let Vite/Webpack handle it from the ESM source? Probably the latter, but worth confirming with the website team if they intend to use this directly.
