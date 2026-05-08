from __future__ import annotations
import click
from dotenv import load_dotenv


@click.group(help="Investment Research Copilot")
def main() -> None:
    """Entry point for the `irc` CLI."""
    load_dotenv()


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


@main.command(help="Score every candidate from discovered_watchlist.csv via 5 factors.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def score(repo_root: str) -> None:
    from irc.commands.score_cmd import run_score
    rc = run_score(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Run Discovery 5-step funnel; produces discovered_watchlist.csv.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def discover(repo_root: str) -> None:
    from irc.commands.discover_cmd import run_discover
    rc = run_discover(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Ingest data from OpenBB + AKShare into data/local.duckdb.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def ingest(repo_root: str) -> None:
    from irc.commands.ingest_cmd import run_ingest
    rc = run_ingest(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(name="run", help="Run the full pipeline (ingest→discover→score→gold→allocate→plan→memo).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--from", "from_stage", type=str, default=None, help="Resume from this stage.")
@click.option("--only", "only_stage", type=str, default=None, help="Run only this stage.")
def run_command(repo_root: str, from_stage: str | None, only_stage: str | None) -> None:
    from irc.commands.run_cmd import run_pipeline
    rc = run_pipeline(repo_root=repo_root, from_stage=from_stage, only_stage=only_stage)
    raise SystemExit(rc)


@main.command(help="Answer a research question using memo + scores context.")
@click.argument("question", nargs=-1, required=True)
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def ask(question: tuple[str, ...], repo_root: str) -> None:
    from irc.commands.ask_cmd import run_ask
    rc = run_ask(repo_root=repo_root, question=" ".join(question))
    raise SystemExit(rc)


@main.command(help="Synthesize investment memo using LLM.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def memo(repo_root: str) -> None:
    from irc.commands.memo_cmd import run_memo
    rc = run_memo(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Build trade plan from proposed_allocation.yaml.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def plan(repo_root: str) -> None:
    from irc.commands.plan_cmd import run_plan
    rc = run_plan(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Compute proposed allocation from scores + gold tilt.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def allocate(repo_root: str) -> None:
    from irc.commands.allocate_cmd import run_allocate
    rc = run_allocate(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Run gold scoring (regime + band + 6 drivers + scenario).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def gold(repo_root: str) -> None:
    from irc.commands.gold_cmd import run_gold
    rc = run_gold(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Show data freshness summary.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def freshness(repo_root: str) -> None:
    from irc.commands.freshness_cmd import run_freshness
    rc = run_freshness(repo_root=repo_root)
    raise SystemExit(rc)
