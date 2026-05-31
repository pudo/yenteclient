# yente-client documentation

Python SDK and CLI for the [yente](https://github.com/opensanctions/yente)
matching API and the hosted [OpenSanctions](https://www.opensanctions.org)
API.

## Start here

- **[Tutorial](tutorial.md)** — a linear walk through the SDK: install,
  first match, search, fetch, async, errors, the FtM model.
- **[CLI overview](cli.md)** — the `yente-cli` command, when to reach
  for it, the command list, output formats, exit codes.
- **[API reference](api/index.md)** — auto-generated from docstrings;
  every public symbol re-exported from `yente_client`.

## What's in scope here

The matching workflow (the SDK's primary use case) and the
search/fetch endpoints that surround it. For broader context — what
sanctions screening is, what datasets exist, how to get an API key —
see the [OpenSanctions docs](https://www.opensanctions.org/docs/).

## Regenerating the API reference

The `api/` tree is generated from docstrings; do not hand-edit. Run
`make docs` to regenerate after changing public docstrings; CI runs
`make docs-check` to catch drift.
