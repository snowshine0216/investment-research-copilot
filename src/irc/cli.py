from __future__ import annotations
import click


@click.group(help="Investment Research Copilot")
def main() -> None:
    """Entry point for the `irc` CLI."""


@main.group(help="Configuration management.")
def config() -> None:
    pass


@main.command(help="Initialize repo with default inputs/ and config/.")
@click.option("--repo-root", type=click.Path(file_okay=False), default=".",
              help="Repo root (defaults to cwd).")
@click.option("--force", is_flag=True, default=False,
              help="Overwrite existing files.")
def init(repo_root: str, force: bool) -> None:
    from irc.commands.init_cmd import run_init
    rc = run_init(repo_root=repo_root, force=force)
    raise SystemExit(rc)


@config.command("validate", help="Validate all YAML inputs and configs against schemas.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def config_validate(repo_root: str) -> None:
    from irc.commands.validate_cmd import run_validate
    rc = run_validate(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Ingest data from OpenBB + AKShare into data/local.duckdb.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def ingest(repo_root: str) -> None:
    from irc.commands.ingest_cmd import run_ingest
    rc = run_ingest(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Show data freshness summary.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def freshness(repo_root: str) -> None:
    from irc.commands.freshness_cmd import run_freshness
    rc = run_freshness(repo_root=repo_root)
    raise SystemExit(rc)
