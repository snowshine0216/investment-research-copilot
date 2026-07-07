from __future__ import annotations
import os
import click
from dotenv import load_dotenv


@click.group(help="Investment Research Copilot")
def main() -> None:
    """Entry point for the `irc` CLI."""
    load_dotenv()
    from irc.observability import setup_logging
    try:
        from irc.settings import Settings
        debug = Settings().debug
    except Exception:
        # Settings() requires DEEPSEEK_API_KEY for full validation; fall back to
        # raw env so `irc init` and `irc config validate` work without secrets.
        debug = os.environ.get("DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}
    setup_logging(debug=debug)


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


@main.group(help="Paid-API spend / balance gate.")
def spend() -> None:
    pass


@spend.command("status", help="Show effective ledger balances (read-only).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def spend_status(repo_root: str) -> None:
    from irc.commands.spend_cmd import run_spend_status
    raise SystemExit(run_spend_status(repo_root=repo_root))


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


@main.command(name="run", help="Run the default pipeline; include research when RESEARCH_ENABLED=true.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--from", "from_stage", type=str, default=None, help="Resume from this stage.")
@click.option("--only", "only_stage", type=str, default=None, help="Run only this stage.")
@click.option("--resume", is_flag=True, default=False,
              help="Resume from the stage that halted in the most recent failed run (today only).")
def run_command(repo_root: str, from_stage: str | None, only_stage: str | None, resume: bool) -> None:
    from irc.commands.run_cmd import run_pipeline
    rc = run_pipeline(repo_root=repo_root, from_stage=from_stage, only_stage=only_stage, resume=resume)
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


@main.command(help="Compose decision-readiness report from today's outputs.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def decision(repo_root: str) -> None:
    from irc.commands.decision_cmd import run_decision
    rc = run_decision(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Run opportunity/thesis/discipline layer; writes 3 outputs.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--output-dir", type=click.Path(file_okay=False), default=None,
              help="Override the default outputs/<today>/ directory.")
@click.option("--limit", type=int, default=None,
              help="Cap cn_equity_fund autobuild rows (rejected on canonical paths).")
@click.option("--rebuild-fundamentals", is_flag=True, default=False,
              help="Force full re-fetch of active-fund caches (skip freshness probe).")
@click.option("--adversarial", is_flag=True, default=False,
              help="Emit advisory bull/bear thesis_debate.md (opt-in; doubles thesis-LLM calls).")
def opportunity(
    repo_root: str, output_dir: str | None, limit: int | None,
    rebuild_fundamentals: bool, adversarial: bool,
) -> None:
    from irc.commands.opportunity_cmd import run_opportunity
    rc = run_opportunity(
        repo_root=repo_root,
        output_dir=output_dir,
        limit=limit,
        rebuild_fundamentals=rebuild_fundamentals,
        adversarial=adversarial,
    )
    raise SystemExit(rc)


@main.command(help="Mine funds tied to a narrative; screen by holdings, optionally deep-analyse.")
@click.argument("name", required=True)
@click.option("--screen-only", "screen_only", is_flag=True, default=False,
              help="Stop after the light screen (default behaviour when no flag given).")
@click.option("--analyze", "analyze", is_flag=True, default=False,
              help="Run the screen then deep-analyse the shortlist (cache-only snapshot path).")
@click.option("--min-overlap", "min_overlap", type=float, default=None,
              help="Min basket-weight %% to qualify; overrides the config "
                   "thresholds.min_basket_weight_pct when given (spec §3.1).")
@click.option("--quarter", type=str, default=None,
              help="Snapshot quarter for --analyze (default: latest cached on disk).")
@click.option("--db", "db_path", type=click.Path(dir_okay=False), default=None,
              help="DuckDB path for --analyze (default data/local.duckdb).")
@click.option("--role", type=str, default="satellite_cn_metals",
              help="Role label stamped on synthesized analyze rows (display only).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--out", "out_dir", type=click.Path(file_okay=False), default=None,
              help="Output dir (default outputs/<today>/narrative/).")
def narrative(
    name: str, screen_only: bool, analyze: bool, min_overlap: float | None,
    quarter: str | None, db_path: str | None, role: str, repo_root: str,
    out_dir: str | None,
) -> None:
    from irc.commands.narrative_cmd import run_narrative
    # --screen-only is the default; --analyze opts into the cache-only deep path.
    rc = run_narrative(
        repo_root=repo_root, name=name, analyze=(analyze and not screen_only),
        out_dir=out_dir, quarter=quarter, db_path=db_path, role=role,
        min_overlap=min_overlap,
    )
    raise SystemExit(rc)


@main.command("lookthrough-diff", help="Write the Phase D look-through diff report (gate-#5 artifact). Cached-only; computes regardless of the flag.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--output-dir", type=click.Path(file_okay=False), default=None)
@click.option("--coverage-floor", type=click.FloatRange(min=0.0, max=1.0, min_open=True), default=0.50, show_default=True)
@click.option("--pb-uses-pe-gate", is_flag=True, default=False)
def lookthrough_diff(repo_root: str, output_dir: str | None, coverage_floor: float, pb_uses_pe_gate: bool) -> None:
    from irc.commands.lookthrough_diff_cmd import run_lookthrough_diff
    rc = run_lookthrough_diff(
        repo_root=repo_root, output_dir=output_dir,
        coverage_floor=coverage_floor, pb_uses_pe_gate=pb_uses_pe_gate,
    )
    raise SystemExit(rc)


@main.command("eval-funds", help="Evaluate an explicit fund-id list; report opportunity_state + core_dca.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--ids", type=str, default=None, help="Comma-separated fund ids.")
@click.option("--ids-file", type=click.Path(dir_okay=False, exists=True), default=None,
              help="File with comma/newline-separated fund ids.")
@click.option("--quarter", type=str, default=None,
              help="Snapshot quarter (default: latest cached on disk).")
@click.option("--role", type=str, default="satellite_cn_metals",
              help="Role label stamped on synthesized score rows (display only).")
@click.option("--db", "db_path", type=click.Path(dir_okay=False), default=None,
              help="DuckDB path (default data/local.duckdb).")
@click.option("--out", "out_path", type=click.Path(dir_okay=False), default=None,
              help="Markdown output path (default outputs/<today>/fund_eval.md; .json sibling).")
def eval_funds(
    repo_root: str, ids: str | None, ids_file: str | None, quarter: str | None,
    role: str, db_path: str | None, out_path: str | None,
) -> None:
    from irc.commands.fund_eval_cmd import run_eval_funds
    rc = run_eval_funds(
        repo_root=repo_root, ids=ids, ids_file=ids_file, quarter=quarter,
        role=role, db_path=db_path, out_path=out_path,
    )
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


@main.group(help="Universe generation.")
def universe() -> None:
    pass


@universe.command("build-cn-funds", help="Build generated CN fund universe from Akshare catalog.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".",
              help="Repo root (defaults to cwd).")
def universe_build_cn_funds(repo_root: str) -> None:
    from irc.commands.universe_cmd import run_build_cn_funds
    rc = run_build_cn_funds(repo_root=repo_root)
    raise SystemExit(rc)


@main.group(invoke_without_command=True, help="Daily monitor brief for the Monitor set.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.pass_context
def monitor(ctx: click.Context, repo_root: str) -> None:
    if ctx.invoked_subcommand is None:
        from irc.commands.monitor_cmd import run_monitor
        raise SystemExit(run_monitor(repo_root=repo_root))


@monitor.command("snapshot", help="Refresh per-fund snapshot caches for the Monitor set.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--top-n", type=int, default=10, show_default=True)
def monitor_snapshot(repo_root: str, top_n: int) -> None:
    from irc.commands.monitor_cmd import run_monitor_snapshot
    raise SystemExit(run_monitor_snapshot(repo_root=repo_root, top_n=top_n))


@monitor.command("flow-capture",
                 help="15:45 job: append the completed-day flow batch to the series store.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def monitor_flow_capture(repo_root: str) -> None:
    from irc.commands.monitor_cmd import run_flow_capture
    raise SystemExit(run_flow_capture(repo_root=repo_root))


@main.group(invoke_without_command=True,
            help="Daily sector rotation radar (advisory; zero-LLM).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.pass_context
def rotation(ctx: click.Context, repo_root: str) -> None:
    if ctx.invoked_subcommand is None:
        from irc.commands.rotation_cmd import run_rotation
        raise SystemExit(run_rotation(repo_root=repo_root))


@rotation.command("seed",
                  help="One-time resumable backfill (board history + holdings + stock→board map).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def rotation_seed(repo_root: str) -> None:
    from irc.commands.rotation_cmd import run_rotation_seed
    raise SystemExit(run_rotation_seed(repo_root=repo_root))


@main.group(help="Fundamentals snapshot cache management.")
def fundamentals() -> None:
    pass


@fundamentals.command("snapshot", help="Rebuild cached constituent snapshot(s).")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option(
    "--target", "targets", multiple=True, required=True,
    help="Lookthrough target to rebuild. Repeat for multiple targets; use 'all' for every registered target.",
)
@click.option("--top-n", type=int, default=10, show_default=True, help="Top constituents to fetch per target.")
def fundamentals_snapshot(repo_root: str, targets: tuple[str, ...], top_n: int) -> None:
    from irc.commands.fundamentals_cmd import run_snapshot_rebuild
    rc = run_snapshot_rebuild(repo_root=repo_root, targets=targets, top_n=top_n)
    raise SystemExit(rc)


@fundamentals.command(
    "stock-valuation",
    help="Refresh cached per-stock PE/PB history for A-share holdings (heavy; own cadence).",
)
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--force", is_flag=True, default=False, help="Refetch every A-share, ignoring staleness.")
@click.option(
    "--threshold-days", type=int, default=30, show_default=True,
    help="Skip stocks fresh within this many days.",
)
def fundamentals_stock_valuation(repo_root: str, force: bool, threshold_days: int) -> None:
    from irc.commands.fundamentals_cmd import run_stock_valuation_refresh
    rc = run_stock_valuation_refresh(
        repo_root=repo_root, force=force, threshold_days=threshold_days
    )
    raise SystemExit(rc)


@main.command(help="Show data freshness summary.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def freshness(repo_root: str) -> None:
    from irc.commands.freshness_cmd import run_freshness
    rc = run_freshness(repo_root=repo_root)
    raise SystemExit(rc)


@main.command(help="Run web-research jobs; write data/research/<theme>.md.")
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option("--theme", "themes", multiple=True, help="Theme key to run. Repeat for multiple themes. Defaults to all configured research themes.")
def research(repo_root: str, themes: tuple[str, ...]) -> None:
    from irc.commands.research_cmd import run_research
    rc = run_research(repo_root=repo_root, themes=themes or None)
    raise SystemExit(rc)


@main.command(help="Run per-stage eval; produces report.json under outputs/<date>/evals/<stage>/.")
@click.argument("stage", required=False)
@click.option("--all", "all_stages", is_flag=True, default=False)
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
def eval(stage: str | None, all_stages: bool, repo_root: str) -> None:
    from irc.commands.eval_cmd import run_eval
    rc = run_eval(repo_root=repo_root, stage=stage, all_stages=all_stages)
    raise SystemExit(rc)


@main.command(
    "notify-status",
    help="Classify the last scheduled run's outcome and notify (macOS + optional Feishu).",
)
@click.option("--repo-root", type=click.Path(file_okay=False, exists=True), default=".")
@click.option(
    "--run-kind",
    type=click.Choice(["daily", "weekly", "monitor", "flow-capture"]),
    required=True,
    help="Which scheduled cadence produced this run.",
)
@click.option(
    "--last-exit-code",
    "last_exit_code",
    type=int,
    required=True,
    help="The pipeline process exit code captured by the launchd wrapper.",
)
@click.option(
    "--notify-on-clean/--no-notify-on-clean",
    "notify_on_clean",
    default=None,
    help=(
        "Emit a quiet notification on a clean run. CLI flag wins; else "
        "IRC_NOTIFY_ON_CLEAN env var (accepted truthy: 1/true/yes/on; "
        "any other non-empty value is falsy); default on."
    ),
)
def notify_status(
    repo_root: str,
    run_kind: str,
    last_exit_code: int,
    notify_on_clean: bool | None,
) -> None:
    from irc.commands.notify_cmd import run_notify_status

    rc = run_notify_status(
        repo_root=repo_root,
        run_kind=run_kind,
        last_exit_code=last_exit_code,
        notify_on_clean=notify_on_clean,
    )
    raise SystemExit(rc)
