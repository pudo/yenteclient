---
description: Implementation plan for M1 — Python codegen pipeline + per-schema entity classes + literal types. No HTTP client yet; that's M2.
date: 2026-05-29
tags: [yente, sdk, python, m1, codegen]
---

# M1 — Python codegen pipeline + entity classes

Companion to `plans/2026-05-29-sdk-and-cli-design.md`. Read that first for the full SDK design; this doc is the concrete execution plan for the first milestone.

## Goal

A user can:

```python
from yente_client.entities import Person, Company

p = Person(firstName="Aleksandr", lastName="Zacharov", birthDate="1965")
p.to_payload()                    # {"schema": "Person", "properties": {"firstName": ["Aleksandr"], ...}}
```

…and get full IDE autocomplete, `mypy --strict` satisfaction, and `extra="forbid"` rejection of typos like `birth_date=...`. No HTTP, no `Client`, no `match()` yet.

## In scope

1. Python project scaffolding (pyproject, dev venv, Makefile).
2. Canonical `model/model.json` snapshot, committed at repo root.
3. Minimal `yente_client.schemas` package: loaded raw dict + four lookup helpers.
4. `yente_client.entities._base` module: `_EntityBase`, `EntityInput` TypeAlias, `_ensure_list` validator.
5. `scripts/regen_model.py` — fetch/copy/generate/format orchestrator with `--check` and `--skip-fetch` modes.
6. Two Jinja templates: `python_entities.py.j2`, `python_literals.py.j2`.
7. Generated committed artefacts:
   - `python/src/yente_client/entities/_generated.py`
   - `python/src/yente_client/entities/__init__.py` (also generated — pure re-exports)
   - `python/src/yente_client/schemas/_literals.py`
   - `python/src/yente_client/schemas/model.json` (copy of the canonical one)
8. Tests for everything above.
9. CI workflow: lint, mypy --strict, pytest, `regen_model.py --check`.

## Out of scope (deferred, no exceptions)

- `Client`, `AsyncClient`, response models, error hierarchy, HTTP transport. **M2.**
- Async support of any kind. **M3.**
- `match_many` / `match_iter`. **M4.**
- CLI. **M5.**
- TypeScript bindings — Jinja templates are Python-only for now. **M6.**
- Generic `Entity(schema=, properties=)` escape hatch — no real use case identified yet.
- Runtime `DeprecationWarning` emission — the codegen-time `# DEPRECATED:` comment is enough signal until users ask for more.
- Polished introspection API (Pydantic-typed `SchemaDef`, `PropertyDef`, etc.) — raw dict is fine.
- Topic aliases (`"risk"`, `"all"`), dataset DSL acceptance, cross-include/exclude self-validation in Filters — all v2 server behaviour we don't try to mirror.

## Phases

### Phase A — Scaffolding

**A1. `python/pyproject.toml`**

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "yente-client"
version = "0.0.1"
description = "Client SDK for the yente / OpenSanctions matching API."
readme = "README.md"
license = "MIT"
requires-python = ">=3.11"
authors = [{ name = "OpenSanctions" }]
dependencies = [
  "pydantic>=2.5,<3",
  "httpx>=0.27,<1",      # not used in M1 but pinning now keeps pyproject stable
]

[project.optional-dependencies]
dev = [
  "pytest>=8",
  "pytest-cov",
  "respx>=0.21",         # for M2 mocking; harmless to install now
  "ruff>=0.6",
  "mypy>=1.11",
  "jinja2>=3",           # build-time only (codegen); declared as dev
]

[tool.hatch.build.targets.wheel]
packages = ["src/yente_client"]

[tool.ruff]
line-length = 100
target-version = "py311"

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
strict = true
python_version = "3.11"
files = ["src/yente_client"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

Floor at Python 3.11: modern union syntax, no `from __future__ import annotations` ceremony, faster startup.

**A2. Project-local venv at `python/.venv/`**

Created via `python3.11 -m venv .venv && .venv/bin/pip install -e .[dev]`. Stays out of git via existing `.gitignore`.

**A3. Top-level `Makefile`**

```make
PY := python/.venv/bin/python

.PHONY: regen-model test lint

regen-model:
	$(PY) scripts/regen_model.py

test:
	cd python && .venv/bin/pytest

lint:
	cd python && .venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
```

Three targets. `lint` exists because we run it often during dev; CI uses its own commands.

> **Checkpoint A:** `pip install -e .[dev]` succeeds; `pytest` runs (no tests yet); `ruff check` and `mypy` pass on the empty package.

### Phase B — Bundled model + tiny schemas package

**B1. `model/model.json`** — fetched once via `curl` and committed by hand for this phase. The regen script will own subsequent updates.

**B2. `python/src/yente_client/schemas/__init__.py`** — loads `schemas/model.json` at import time into a module-level `model` dict; re-exports the lookup helpers.

```python
import json
from pathlib import Path

from ._lookup import has_schema, is_a, is_deprecated, iter_properties

_MODEL_PATH = Path(__file__).parent / "model.json"
model: dict = json.loads(_MODEL_PATH.read_text())

__all__ = ["model", "has_schema", "is_a", "is_deprecated", "iter_properties"]
```

**B3. `python/src/yente_client/schemas/_lookup.py`** — four helpers, ~30 LoC total.

```python
from . import model    # avoid circular: defer to a lazy lookup if needed

def has_schema(name: str) -> bool: ...
def iter_properties(schema: str) -> Iterator[str]: ...
def is_a(schema: str, ancestor: str) -> bool: ...      # walks model[schemata][schema][schemata]
def is_deprecated(schema: str, prop: str) -> bool: ...
```

Note: `_lookup.py` imports from `schemas/__init__.py`, which loads `model.json` at import time. The circular reference is solved by deferring `from . import model` to inside each helper, or by having `_lookup.py` read `model.json` itself (its own import is cheap). Sort that out in implementation.

**B4. Tests** — `tests/test_schemas.py`:

- `model["schemata"]["Person"]["properties"]["birthDate"]["type"] == "date"`
- `has_schema("Person") is True`, `has_schema("NotARealSchema") is False`
- `is_a("LegalEntity", "Thing") is True`, `is_a("Address", "Thing") is False`
- `"sanction" in model["types"]["topic"]["values"]`
- `is_deprecated("Person", "secondName") is True`

> **Checkpoint B:** `python -c "from yente_client.schemas import has_schema; print(has_schema('Person'))"` returns `True`. ~5 tests pass.

### Phase C — `entities/_base.py`

**C1.** `python/src/yente_client/entities/_base.py`:

```python
from typing import Any, ClassVar, TypeAlias
from pydantic import BaseModel, ConfigDict


PropertyValue: TypeAlias = str | list[str]


def _ensure_list(value: Any) -> Any:
    """Wildcard `field_validator(mode='before')` for entity classes.
    Coerces single string to single-element list; passes lists through unchanged;
    returns None unchanged (Pydantic uses its own default handling)."""
    if value is None or isinstance(value, list):
        return value
    if isinstance(value, str):
        return [value]
    raise ValueError(f"expected str or list[str], got {type(value).__name__}")


class _EntityBase(BaseModel):
    """Shared base for every per-schema entity class.

    Per-schema subclasses (Person, Company, ...) live in `_generated.py` and
    declare their FtM properties as `list[str]` fields. The `schema_` ClassVar
    is the discriminator; the actual JSON key on the wire is "schema"."""

    model_config = ConfigDict(extra="forbid")

    id: str | None = None
    schema_: ClassVar[str]                    # set on subclasses

    def to_payload(self) -> dict:
        """Serialise for the /match wire format."""
        props = {
            name: value
            for name, value in self.model_dump(exclude={"id"}).items()
            if value                          # drop empty lists
        }
        payload: dict = {"schema": self.schema_, "properties": props}
        if self.id is not None:
            payload["id"] = self.id
        return payload


EntityInput: TypeAlias = _EntityBase          # public alias for parameter signatures
```

**C2.** `python/src/yente_client/entities/__init__.py` for Phase C — hand-written until D regenerates it:

```python
from ._base import _EntityBase, EntityInput

__all__ = ["EntityInput"]
```

**C3.** Tests — `tests/test_base.py`:

- Define a `_TestPerson(_EntityBase)` with `schema_: ClassVar = "Person"` and a couple of `list[str]` fields with the `_ensure_list` validator.
- `_TestPerson(name="X")` normalises to `name=["X"]`.
- `_TestPerson(name=["X", "Y"])` round-trips unchanged.
- `_TestPerson(unknown="X")` raises `ValidationError`.
- `to_payload()` returns the expected dict; drops empty lists; includes `id` only when set.

> **Checkpoint C:** `_EntityBase` works against a hand-rolled subclass. ~6 tests.

### Phase D — Codegen

**D1. `scripts/regen_model.py`** — the orchestrator.

```
usage: regen_model.py [--check] [--skip-fetch] [--model-url URL]

Default: fetch model.json from data.opensanctions.org, regenerate all
artefacts in place, format with ruff.

--check       Render to a temp dir, compare against committed files, exit
              nonzero on diff. CI runs this to detect upstream drift.
--skip-fetch  Use the existing model/model.json (developer iteration mode).
--model-url   Override the source URL (testing).
```

Concrete behaviour:

1. Fetch `https://data.opensanctions.org/meta/model.json` (or skip).
2. Write `model/model.json` (atomic: write to `model/model.json.tmp`, rename).
3. Copy to `python/src/yente_client/schemas/model.json`.
4. Render templates with Jinja:
   - `python/src/yente_client/entities/_generated.py` from `scripts/templates/python_entities.py.j2`.
   - `python/src/yente_client/entities/__init__.py` from `scripts/templates/python_entities_init.py.j2` (just re-exports).
   - `python/src/yente_client/schemas/_literals.py` from `scripts/templates/python_literals.py.j2`.
5. Run `ruff format <files>` as a final pass.
6. On `--check`, render everything to a temp dir, run ruff format there too, then diff against the committed copies. Exit 1 on mismatch with a useful diff in stderr.

Determinism rules (so diffs are stable when upstream changes):

- Schemas in alphabetical order in `_generated.py` and `__init__.py`.
- Properties within a schema in alphabetical order.
- Literal values in alphabetical order in `_literals.py`.
- Newlines between classes are uniform (template handles this).
- No timestamps, no Python version stamps, no model snapshot date in the output. The committed `model/model.json` itself is the version anchor.

Stdlib only for fetch (`urllib.request`); jinja2 for templating; `subprocess` for ruff format.

**D2. Jinja templates** under `scripts/templates/`.

`python_entities.py.j2` — one class per schema; properties flattened across `schemata`; deprecated comment lines. Sketch:

```jinja2
"""Generated by scripts/regen_model.py. DO NOT EDIT by hand.

Source: model/model.json (commit-pinned snapshot of the FtM model).
"""
from typing import ClassVar, Literal
from pydantic import Field, field_validator

from ._base import _EntityBase, _ensure_list

{% for schema in schemata %}
class {{ schema.name }}(_EntityBase):
    {%- if schema.description %}
    """{{ schema.description | trim }}"""
    {%- endif %}
    schema_: ClassVar[Literal["{{ schema.name }}"]] = "{{ schema.name }}"

    {% for prop in schema.properties %}
    {%- if prop.deprecated %}
    # DEPRECATED: {{ prop.deprecated_reason or "property is deprecated" }}
    {%- endif %}
    {{ prop.name }}: list[str] = Field(default_factory=list)
    {% endfor %}
    _coerce = field_validator("*", mode="before")(_ensure_list)


{% endfor %}
```

`python_literals.py.j2` — flat enum-like Literal types:

```jinja2
"""Generated by scripts/regen_model.py. DO NOT EDIT by hand."""
from typing import Literal

Schema = Literal[{{ schemas | map_to_literal_args }}]
PropertyType = Literal[{{ types | map_to_literal_args }}]
Topic = Literal[{{ topics | map_to_literal_args }}]
Gender = Literal[{{ genders | map_to_literal_args }}]
```

`python_entities_init.py.j2` — pure re-export:

```jinja2
"""Generated by scripts/regen_model.py. DO NOT EDIT by hand."""
from ._base import EntityInput, _EntityBase
from ._generated import (
{% for name in schema_names %}    {{ name }},
{% endfor %})

__all__ = ["EntityInput", "_EntityBase", {% for name in schema_names %}"{{ name }}", {% endfor %}]
```

**D3. Run regen, commit outputs.** First real run produces:

- `_generated.py` — one class per FtM schema, ~2.5–3k LoC after `ruff format`.
- `entities/__init__.py` — ~80 lines of re-exports.
- `_literals.py` — ~5 lines (one Literal per type, each very long).

Commit all four (including the copy of `model.json` under `schemas/`).

**D4. Tests** — `tests/test_generated.py`:

- `Person(firstName="X").firstName == ["X"]`
- `Person(firstName=["X", "Y"]).firstName == ["X", "Y"]`
- `Person(birth_date="1965")` raises `ValidationError` (snake_case not in fields).
- `Person(unknownProp="X")` raises `ValidationError`.
- `Person.schema_ == "Person"` and is `ClassVar`.
- `isinstance(Person(name="X"), _EntityBase)` is `True`.
- `Person(firstName="X").to_payload()` shape correct.
- Sanity scan: `len(Schema.__args__) > 30` and includes known anchors like `"Person"` / `"Company"` (from `_literals.py`). Don't lock in an exact count — that's drift-prone.
- `from yente_client.entities import Person, Company` works.

`tests/test_regen.py`:

- Run `scripts/regen_model.py --check --skip-fetch` in a subprocess; assert exit 0 against the committed files.
- (Optional but high-value) Modify a committed generated file by one byte in a temp checkout; assert `--check` exits 1.

> **Checkpoint D:** end-to-end M1 works. `from yente_client.entities import Person; Person(firstName='X')` succeeds; `mypy --strict src/yente_client` is green; `pytest` is green; `make regen-model --check` (or the direct script call) is idempotent.

### Phase E — CI

**E1. `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  push: { branches: [main] }
  pull_request:
jobs:
  python:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ matrix.python-version }}" }
      - run: pip install -e python/.[dev]
      - run: cd python && ruff check .
      - run: cd python && ruff format --check .
      - run: cd python && mypy
      - run: cd python && pytest
      - run: python scripts/regen_model.py --check --skip-fetch
```

The final step is the drift detector. It runs `--skip-fetch` so CI doesn't hit the network unnecessarily; we'll add a separate scheduled job later that runs without `--skip-fetch` against the live `model.json` to surface upstream drift on a daily cadence.

> **Checkpoint E:** green CI on a real PR.

## File-by-file summary

New files committed at the end of M1:

| Path | Origin | Size |
| --- | --- | --- |
| `python/pyproject.toml` | hand-written | ~50 lines |
| `python/README.md` | hand-written | ~30 lines (quickstart stub) |
| `python/src/yente_client/__init__.py` | hand-written | ~10 lines (re-export `Person`, `Company`, etc. for top-level access; pulls from `.entities`) |
| `python/src/yente_client/entities/__init__.py` | **generated** | ~80 lines |
| `python/src/yente_client/entities/_base.py` | hand-written | ~50 lines |
| `python/src/yente_client/entities/_generated.py` | **generated** | ~2.5–3k lines |
| `python/src/yente_client/schemas/__init__.py` | hand-written | ~15 lines |
| `python/src/yente_client/schemas/_lookup.py` | hand-written | ~30 lines |
| `python/src/yente_client/schemas/_literals.py` | **generated** | ~5 lines (long Literals) |
| `python/src/yente_client/schemas/model.json` | **copied** | ~150 KB |
| `python/tests/test_schemas.py` | hand-written | ~30 lines |
| `python/tests/test_base.py` | hand-written | ~40 lines |
| `python/tests/test_generated.py` | hand-written | ~60 lines |
| `python/tests/test_regen.py` | hand-written | ~30 lines |
| `model/model.json` | **fetched** | ~150 KB |
| `scripts/regen_model.py` | hand-written | ~200 lines |
| `scripts/templates/python_entities.py.j2` | hand-written | ~30 lines |
| `scripts/templates/python_literals.py.j2` | hand-written | ~15 lines |
| `scripts/templates/python_entities_init.py.j2` | hand-written | ~10 lines |
| `Makefile` | hand-written | ~15 lines |
| `.github/workflows/ci.yml` | hand-written | ~25 lines |

Total hand-written: ~600 lines of code + ~150 lines of tests. Generated: ~3k lines (mostly the per-schema class bodies). Snapshot data: ~300 KB.

## Acceptance criteria

A reviewer can verify M1 is done by running:

```
cd python && pip install -e .[dev]
python -c "from yente_client.entities import Person; p = Person(firstName='X'); print(p.to_payload())"
# -> {'schema': 'Person', 'properties': {'firstName': ['X']}}

python -c "from yente_client.entities import Person; Person(birth_date='X')"
# -> ValidationError

mypy
pytest
python ../scripts/regen_model.py --check --skip-fetch
# all exit 0
```

…and CI is green on a PR that exercises the same.

## Implementation order and stop points

The user-facing milestones are A → B → C → D → E; each ends in a checkpoint. Natural commit boundaries:

1. **Commit 1** — Phase A done (scaffolding only, empty package).
2. **Commit 2** — Phase B done (schemas package works).
3. **Commit 3** — Phase C done (`_EntityBase` works with a stub subclass).
4. **Commit 4** — Phase D1 + D2 done (regen script + templates, but no committed generated files yet).
5. **Commit 5** — Phase D3 done (`make regen-model` run; generated files committed).
6. **Commit 6** — Phase D4 done (tests for generated classes pass).
7. **Commit 7** — Phase E done (CI green).

I'll stop after each commit and surface state. Especially after commit 5 — that's the first big visible artefact and worth a look before tests get added on top.

## Implementation questions to surface during the work

These probably resolve naturally but worth flagging:

1. **Class for non-matchable schemas?** Only a subset of FtM schemas have `matchable: true`; the rest (Document, Article, Sanction, …) aren't intended as match query targets. Generate classes for all schemas for consistency, or only the matchable ones? Lean: all of them — the server is the gate, the client doesn't need to second-guess.
2. **Top-level package re-exports.** Should `from yente_client import Person` work, or do users always go via `yente_client.entities`? Lean: both, but the top-level export adds one name per schema to `yente_client.__init__.py`. Could be ergonomic or noisy. Decide when looking at the actual user surface.
3. **Property docstrings on generated fields.** `model.json` has `description` on most properties. Worth surfacing as a `# description here` comment line or as a `Field(description=...)`? Lean: `Field(description=...)` — shows up in IDE hover via Pydantic and in `model_json_schema()` if users ever generate docs.
4. **`schemas/__init__.py` circularity.** `_lookup.py` imports `model` from `__init__.py`. Either lazy import inside each helper or have `_lookup.py` open `model.json` itself. Decide when writing.
