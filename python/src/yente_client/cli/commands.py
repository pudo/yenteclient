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

# Default base URL is duplicated from ``Client.__init__`` so ``--version`` can
# print it without instantiating a Client.
_DEFAULT_BASE_URL = "https://api.opensanctions.org"


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


def register(app: typer.Typer) -> None:
    """Attach all subcommands to ``app``."""
    app.command("version", help="Print client + bundled FtM model version.")(version_command)
