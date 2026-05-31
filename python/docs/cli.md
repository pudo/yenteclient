# yente-cli — command-line overview

The `yente-cli` binary ships with the `yente-client[cli]` install extra.
It mirrors the SDK surface — same matching, search, fetch, server-state
endpoints — and is designed for one-off lookups, shell pipelines, and
LLM-agent automations.

This page is the overview. For per-command detail (every option, every
exit code, output JSON shape, worked examples), run
`yente-cli <command> --help`.

## When to reach for the CLI vs the SDK

| Situation | Reach for |
|---|---|
| Ad-hoc lookup — *"is Acme on the sanctions list?"* | CLI |
| Shell pipeline (`jq`, `awk`, …) | CLI |
| LLM-agent automation that needs structured JSON | CLI (`-f jsonl`) |
| Embedded screening inside a Python service | SDK |
| Long-running background workload | SDK |
| Bulk screening (many entities) | SDK + `asyncio.gather` for now |

## Install

```bash
pip install yente-client[cli]
```

The `[cli]` extra pulls in `typer` and `rich`. Without it, `yente-cli`
emits a one-line install hint and exits.

Authenticate by exporting your API key (the same one the SDK uses):

```bash
export OPENSANCTIONS_API_KEY=sk_live_…
```

To point at a self-hosted yente, set `YENTE_BASE_URL` or pass
`--base-url`.

## The command surface

| Command | One-line |
|---|---|
| `match` | Match a single entity (built from `-p key=value` flags or `--from-file`) against a dataset. The canonical command for any matching task. |
| `search` | Free-text search across one or more datasets — for backing user-facing search UIs. |
| `fetch` | Fetch one entity by ID. |
| `catalog` | List indexed datasets and their freshness. |
| `algorithms` | List enabled matching algorithms + the server defaults. |
| `status` | Client setup + server health + loaded datasets, at a glance. |
| `healthz` | Liveness probe only. |
| `ref schemas` | List every FtM schema (offline; uses bundled snapshot). |
| `ref schema NAME` | Detail view: properties, types, `directly_scored` flag, deprecation. |
| `ref topics` | The `Topic` enum (sanction, role.pep, crime.fraud, …). |
| `ref countries` | The country-code → label lookup. |

`yente-cli --help` carries the full workflow block; per-command
`--help` carries worked examples, OUTPUT-shape blocks, and EXIT-CODE
tables.

## Output formats

Every command takes `-f` / `--format`:

- **`-f table`** — Rich table, the default on a TTY.
- **`-f json`** — pretty JSON, the default when piped.
- **`-f jsonl`** — one item per line. Ideal for `jq` pipelines and LLM
  consumption.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success, at least one result (or any successful response for `fetch` / `catalog`). |
| `1` | Success, zero results. Lets shell scripts gate on `match … && action`. |
| `2` | Usage error — bad flag, unknown schema, malformed `-p key=value`. |
| `3` | API error — non-2xx response. |
| `4` | Transport error — network, timeout, TLS. |

## Worked examples

```bash
# Screen a person against the sanctions collection
yente-cli match -s Person \
  -p firstName=Vladimir -p lastName=Putin -p birthDate=1952-10-07 \
  -d sanctions

# Multi-value property (the same key twice appends):
yente-cli match -s Person \
  -p firstName=Alexander -p firstName=Alex -p lastName=Smith \
  -d sanctions

# From a JSON file (the wire-format match query):
yente-cli match -s Person -i query.json -d sanctions

# Free-text search for a company
yente-cli search "acme" -d default -s Company -l 10

# Fetch one entity, full record
yente-cli fetch NK-aU5ybkbRFJucf8YMwsJvDw

# Check the client setup and server state
yente-cli status

# Inspect what's matchable, machine-readable
yente-cli ref schemas --matchable -f json
yente-cli ref schema Person -f json
```

Every command has an EXAMPLES block in its `--help`.

## Agent-friendly help

The CLI is designed for LLM coding agents that have never read the
OpenSanctions docs:

- **`yente-cli --help`** opens with a *WORKFLOWS* block (intent →
  command) and a *PICK A COMMAND* dispatch table. Includes a NOTE
  block explicitly steering matching tasks away from `search`.
- **Per-command `--help` carries an EXAMPLES epilog** with 2–4
  realistic invocations.
- **OUTPUT blocks** in `--help` document the JSON shape so agents know
  what fields they get back without invoking-then-parsing.
- **Error messages point to the next command.** Examples:
  - `Unknown schema 'Persn'. … Did you mean: Person?`
  - `Property 'birth_date' not on Person. … Did you mean: birthDate?`
  - `Schema 'Document' is not a matchable target … (run `yente-cli ref schemas --matchable` …).`

Run `yente-cli --help` first.

## Where to go next

- [SDK tutorial](tutorial.md) — embedded Python usage; the matching
  workflow in depth.
- [API reference](api/index.md) — full signatures of every public symbol.
- [OpenSanctions docs](https://www.opensanctions.org/docs/) — domain
  context (sanctions screening, the FtM data model, the hosted-API
  quickstart, account / API-key page).
