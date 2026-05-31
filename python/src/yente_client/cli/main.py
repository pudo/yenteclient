"""``yente-client`` CLI entry point.

The Typer app is configured here; the subcommands themselves live in
:mod:`yente_client.cli.commands`. The ``main()`` function is what
``pyproject.toml``'s ``[project.scripts]`` entry calls.
"""

from yente_client.cli._deps import typer
from yente_client.cli.commands import register, version_command

app = typer.Typer(
    name="yente-client",
    help="OpenSanctions / yente API client.",
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)


@app.callback(invoke_without_command=True)
def _app_callback(
    ctx: typer.Context,
    show_version: bool = typer.Option(
        False,
        "--version",
        help="Show client + bundled FtM model version and exit.",
        is_eager=True,
    ),
) -> None:
    """Global flags applied before any subcommand."""
    if show_version:
        version_command()
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        # No subcommand and no global-flag short-circuit: show help.
        typer.echo(ctx.get_help())
        raise typer.Exit()


register(app)


def main() -> None:
    """Console-script entry point registered in ``pyproject.toml``."""
    app()


if __name__ == "__main__":
    main()
