"""``yente-cli`` CLI entry point.

The Typer app is configured here; the subcommands themselves live in
:mod:`yente_client.cli.commands`. The ``main()`` function is what
``pyproject.toml``'s ``[project.scripts]`` entry calls.
"""

from yente_client.cli._deps import typer
from yente_client.cli.commands import register
from yente_client.cli.config import _DEFAULT_BASE_URL, CliConfig

app = typer.Typer(
    name="yente-cli",
    help=(
        "OpenSanctions / yente API client.\n"
        "\n"
        "WORKFLOWS:\n"
        "  Screen a known entity (KYC/sanctions):  match -s Person -p firstName=… -p lastName=…\n"
        "  Free-text discovery by name:            search 'acme' -d default\n"
        "  Fetch one entity by ID:                 fetch <id>\n"
        "  Discover the data model (offline):      ref schemas, ref schema Person\n"
        "  Discover the server:                    catalog, algorithms\n"
        "\n"
        "PICK A COMMAND:\n"
        "  Have a full entity (name+dob+country)? → match\n"
        "  Have a name to look up?                → search\n"
        "  Have an ID already?                    → fetch\n"
        "  Not sure what's queryable?             → ref schemas\n"
        "  What datasets / algorithms exist?      → catalog, algorithms\n"
        "\n"
        "ENV: OPENSANCTIONS_API_KEY (auth), YENTE_BASE_URL (override target).\n"
        "Use -f json (or jsonl) for machine-readable / LLM-friendly output."
    ),
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _app_callback(
    ctx: typer.Context,
    api_key: str | None = typer.Option(
        None,
        "--api-key",
        envvar="OPENSANCTIONS_API_KEY",
        show_envvar=True,
        help="API key for the hosted OpenSanctions API. Falls back to env.",
    ),
    base_url: str = typer.Option(
        _DEFAULT_BASE_URL,
        "--base-url",
        envvar="YENTE_BASE_URL",
        show_envvar=True,
        help="API root. Use to target a self-hosted yente instance.",
    ),
    app_name: str | None = typer.Option(
        None,
        "--app-name",
        help="Identifier embedded in the User-Agent. Helpful for hosted-side telemetry.",
    ),
    user_agent: str | None = typer.Option(
        None,
        "--user-agent",
        help="Full User-Agent override; bypasses app-name assembly.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Show full tracebacks on errors instead of one-line summaries.",
    ),
) -> None:
    """Global flags applied before any subcommand."""
    ctx.obj = CliConfig(
        api_key=api_key,
        base_url=base_url,
        app_name=app_name,
        user_agent=user_agent,
        verbose=verbose,
    )
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


register(app)


def main() -> None:
    """Console-script entry point registered in ``pyproject.toml``."""
    app()


if __name__ == "__main__":
    main()
