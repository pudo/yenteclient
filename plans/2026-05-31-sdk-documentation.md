---
description: Documentation intermission between M4 (CLI MVP) and M5 (batch screening). Sets up python/docs/ with one Python tutorial, one CLI overview, and an auto-generated API reference for the Python SDK.
date: 2026-05-31
tags: [docs, sdk, intermission]
---

# SDK documentation intermission

## Why now

M1–M4 shipped the Python SDK and a working CLI. The public surface is stable
enough to write about without immediately rewriting. Before M5
(`match_many` / `match_iter` and the screening CLI), worth spending a focused
effort on documentation so the patterns we settle on are visible to users.

The README has a Quickstart and a CLI listing — useful as a 60-second pitch,
not enough for someone trying to actually build with the SDK. One tutorial
that walks the public surface end-to-end fills the gap; an auto-generated
API ref backs it.

## Goals (and non-goals)

**Goals:**
- A single `tutorial.md` under `python/docs/` that covers install, auth, the
  match workflow, search, fetch/adjacent, async, errors, and entity model
  basics — linear and runnable.
- A single `cli.md` covering the `yente-cli` command surface in overview
  form — when to reach for the CLI, the command list, output formats, exit
  codes. Per-command detail stays in `--help`; this page links into it.
- An auto-generated API reference covering every public symbol in
  `yente_client.__all__`.
- `make docs` regenerates the API ref deterministically (same determinism
  rules as `make regen-model`); `make docs-check` in CI catches drift.
- Bidirectional cross-linking with opensanctions.org/docs (their
  domain-level docs, our SDK/CLI docs). We link out for product /
  domain context; we ask knowledgebase to link in for SDK reference.

**Non-goals (defer):**
- A hosted doc site (MkDocs, GitHub Pages). The markdown reads fine on
  GitHub today; site infrastructure can come later without redoing the
  source files.
- TypeScript SDK docs. Lives under `typescript/docs/` when TS ships in M6.
- A per-command CLI reference. The `--help` epilogs are the canonical
  surface; `cli.md` is overview-level only.
- Multi-page guides (configuration / async / errors as their own files).
  One tutorial in linear form is the right granularity until users
  actually ask for more.
- Tutorials beyond the SDK surface — OpenSanctions onboarding, the
  sanctions-screening domain primer, etc. Those stay on
  opensanctions.org/docs; we cross-link into them.

## Directory layout

```
python/docs/
  README.md                           # one-screen index pointing at the three docs
  tutorial.md                         # the linear SDK walk-through
  cli.md                              # CLI overview (per-command detail stays in --help)
  api/
    index.md                          # generated TOC
    client.md                         # one file per module
    async_client.md
    models.md
    exceptions.md
    filters.md
    entities.md
```

## Tutorial outline

One file, ~1500–2500 words, walked top-to-bottom. Each section opens with
**when you'd reach for this** in the user's "lead with why" style, then a
runnable example, then a forward link to the API ref for full signatures.

1. **Install and authenticate.** `pip install yente-client`, get an API key,
   set `OPENSANCTIONS_API_KEY`. First `Client(api_key=...)` call. Where the
   hosted API lives.
2. **Your first match.** Construct a `Person`, call `client.match(person)`,
   inspect `MatchResponse.top` and `.matches`. What a `ScoredEntity`
   carries (score, match flag, explanations).
3. **Matching in depth.** Threshold semantics, choosing an algorithm
   (`BEST_ALGORITHM`), `MatchFilters` (datasets, topics, schema). Note:
   one HTTP call per `match()` — batching is M5's job.
4. **Fetch and adjacency.** `fetch(id, nested=True)` for UI display vs
   `nested=False` for pipelines. The `adjacent` overload set with paging.
   Natural follow-up to step 2: you have an ID from a match result.
5. **Search (for user-facing search UIs).** A different use case from
   matching — search is for building end-user search experiences:
   autocomplete fields, browse interfaces, "search this database"
   pages. **Any matching task — even with partial information — uses
   `match`.** Search returns `Entity` (no score); match returns
   `ScoredEntity`. Worked example: powering a search box that lets a
   journalist look up companies by name. Covers `SearchFilters`,
   facets, and pagination. Reaches this section after matching/fetch
   because that's the SDK's primary workflow; search is a parallel
   use case, not a fallback.
6. **Async.** `AsyncClient`, lifecycle (`async with`, `aclose()`), running
   many `match()` calls concurrently with `asyncio.gather`. When async
   actually wins.
7. **Errors.** The `YenteError` tree, what raises what, catching by
   category vs by type. `pydantic.ValidationError` is unwrapped (input
   shape).
8. **Entities and the FtM model.** Per-schema classes (camelCase fields
   match the wire format), bundled model snapshot, `yente-cli ref schemas`
   as the discovery path, regen workflow when upstream moves.
9. **Where to go next.** Link to the API ref, `cli.md`, and the
   OpenSanctions product docs (sanctions screening guide, FtM model
   reference, hosted-API quickstart).

## CLI page outline

One file, ~500–800 words. Lives at the same level as the tutorial because
many users reach for the CLI before they touch the SDK (LLM agents,
shell-script automations, ad-hoc lookups).

1. **When to use the CLI vs the SDK.** CLI for one-off lookups,
   shell pipelines, agent automation; SDK for embedded screening,
   long-running services, batch workloads.
2. **Install.** `pip install yente-client[cli]` ships `yente-cli`.
3. **The command surface.** Table with one line each:
   `match`, `search`, `fetch`, `catalog`, `algorithms`, `status`,
   `healthz`, `ref schemas`, `ref schema NAME`, `ref topics`,
   `ref countries`.
4. **Output formats.** `-f table` (TTY default), `-f json` (piped
   default), `-f jsonl` (one line per item, jq / LLM friendly).
5. **Exit codes.** 0 ≥1 result; 1 zero results; 2 usage; 3 API; 4
   transport. Lets `match … && action` work in shell.
6. **Worked example.** One `match`, one `search`, one `fetch`, one
   `status`. End-to-end, copy-pasteable.
7. **Agent-friendly help.** `--help` carries workflow blocks, OUTPUT
   shapes, EXAMPLES per command, and fuzzy schema/property suggestions
   in error messages. Pointer to run `yente-cli --help` first.
8. **Where to go next.** Link to `tutorial.md` for the SDK,
   `api/` for full reference, the OpenSanctions docs for product
   context.

## API reference generation

Use **lazydocs**: it reads Google-style docstrings (which the project
already uses), emits one `.md` per module, no Python doc-site dependency.
The generation script lives at `scripts/regen_docs.py`.

`make docs` runs:

```
python scripts/regen_docs.py
```

The script:
- Walks `yente_client.__all__` to enumerate exported public symbols.
- For each module that contains at least one exported symbol, writes a
  markdown file under `python/docs/api/`.
- Filters out anything starting with `_`.
- Writes a deterministic `index.md` (symbols alphabetised, modules in a
  fixed order).
- Runs `ruff format --check` on source files first to catch drift.

CI gets a `make docs-check` step (mirrors `make regen-model-check`) that
verifies committed API ref matches what regeneration would produce.

If lazydocs turns out brittle, a hand-rolled equivalent is ~150 LoC: walk
`__all__`, use `inspect.getmembers`, render with a Jinja template. We
already have Jinja in dev deps.

## Style rules

Inherits from `~/.claude/CLAUDE.md` and `yenteclient/CLAUDE.md`:

- Lead with **when you'd reach for this**, not what it does.
- Code blocks: every example is runnable. No pseudocode. Imports included.
- No hardcoded FtM counts ("69 schemas"), no upstream version strings.
- Link forward to the API ref for full signatures; don't duplicate them
  in the tutorial.
- Show error paths with actual exception types; don't hide failure modes
  behind try/except in examples.

## Sequencing

1. **Scaffold** — this plan, `python/docs/README.md`, the directory tree,
   `tutorial.md` and `cli.md` stubs with section headings. Commit.
2. **API-ref tool** — add lazydocs to `[project.optional-dependencies.dev]`,
   write `scripts/regen_docs.py`, generate `python/docs/api/`. Commit.
3. **Write the tutorial** — top-to-bottom, fixing docstring gaps as we
   find them. Commit when the tutorial reads cleanly end-to-end.
4. **Write the CLI page** — overview only, link out to `--help` for
   per-command detail. Commit.
5. **`make docs-check` in CI**, sanity-read all three surfaces, commit,
   push.

Each step is a separate commit; we check in after each so we can pause
or reshape mid-stream. No push until the user has seen the final state.

## Open questions

- **Hosted doc site:** when does this become valuable? Once TS ships, a
  unified site (one URL, both SDK trees) is appealing. Punt to M8.
- **OpenSanctions.org cross-links:** which specific pages over there
  earn links from us, and which of ours earn a link back? Map this out
  when writing each section — likely candidates: their hosted-API
  quickstart, their FtM model reference, their sanctions-screening
  guide, their account / API-key page. File a knowledgebase task to
  add SDK reference links from those pages.
- **Versioning:** docs ship with the wheel; users on v0.1.0 read the
  v0.1.0 docs. Revisit if we ever need multiple SDK majors.
