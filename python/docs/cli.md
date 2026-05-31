# yente-cli — command-line overview

The `yente-cli` binary ships with the `yente-client[cli]` install extra.
It mirrors the SDK surface and is meant for one-off lookups, shell
pipelines, and LLM-agent automations.

For per-command detail, run `yente-cli <command> --help` — every
command carries worked examples, an output-shape block, and exit
codes. This page is the overview: when to reach for the CLI, what
commands exist, what they look like.

## 1. CLI vs SDK — when to use which

_(stub — to be written in step 4.)_

## 2. Install

_(stub. `pip install yente-client[cli]`.)_

## 3. The command surface

_(stub. Table of commands with one-line descriptions: match, search,
fetch, catalog, algorithms, status, healthz, ref schemas, ref schema
NAME, ref topics, ref countries.)_

## 4. Output formats

_(stub. `-f table` / `-f json` / `-f jsonl`.)_

## 5. Exit codes

_(stub. 0 ≥1 result; 1 zero results; 2 usage; 3 API; 4 transport.)_

## 6. Worked examples

_(stub. One `match`, one `search`, one `fetch`, one `status`.)_

## 7. Agent-friendly help

_(stub. The `--help` epilogs carry workflow blocks, EXAMPLES, OUTPUT
shapes. Fuzzy schema/property suggestions in error messages. Pointer:
run `yente-cli --help` first.)_

## 8. Where to go next

- [SDK tutorial](tutorial.md) for embedded usage.
- [API reference](api/index.md) for full signatures.
- [OpenSanctions docs](https://www.opensanctions.org/docs/) for
  product / domain context.
