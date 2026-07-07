from __future__ import annotations

import pytest

from irc.notify.classify import _ALWAYS_NOTIFY, classify_run_outcome
from irc.notify.health import HealthDigest, HealthItem
from irc.notify.types import RunOutcome


def _outcome(**overrides) -> RunOutcome:
    base = dict(
        run_kind="daily",
        last_exit_code=0,
        today_dir_exists=True,
        pipeline_halted=False,
        stale_ingest=False,
        actionable_buy_count=0,
        trim_count=0,
        exit_count=0,
        review_count=0,
    )
    base.update(overrides)
    return RunOutcome(**base)


def test_missing_today_dir_is_failed_even_at_exit_zero():
    decision = classify_run_outcome(_outcome(today_dir_exists=False, last_exit_code=0))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert "never produced output" in decision.body


@pytest.mark.parametrize(
    "code,label",
    [(1, "runtime"), (2, "config"), (3, "fetch-budget"), (4, "lock"), (5, "spend-gate")],
)
def test_nonzero_exit_codes_are_failed_and_named(code, label):
    decision = classify_run_outcome(_outcome(last_exit_code=code))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert label in decision.title.lower()


def test_pipeline_halted_is_halted():
    decision = classify_run_outcome(_outcome(pipeline_halted=True))
    assert decision.severity == "halted"
    assert decision.should_notify is True


def test_stale_ingest_is_stale():
    decision = classify_run_outcome(_outcome(stale_ingest=True))
    assert decision.severity == "stale"
    assert decision.should_notify is True


def test_null_sell_counts_are_action_unknown():
    decision = classify_run_outcome(
        _outcome(trim_count=None, exit_count=None, review_count=None)
    )
    assert decision.severity == "action"
    assert decision.should_notify is True
    assert "unknown" in decision.body.lower()
    assert "irc opportunity" in decision.body
    # never rendered as 0 or "healthy"
    assert "0" not in decision.body.replace("irc opportunity", "")
    assert "healthy" not in decision.body.lower()


def test_single_null_among_sell_counts_is_action_unknown():
    decision = classify_run_outcome(_outcome(trim_count=None, exit_count=0, review_count=0))
    assert decision.severity == "action"
    assert "unknown" in decision.body.lower()


def test_buys_only_is_action():
    decision = classify_run_outcome(_outcome(actionable_buy_count=2))
    assert decision.severity == "action"
    assert "2" in decision.body


def test_sell_signals_only_is_action():
    decision = classify_run_outcome(_outcome(trim_count=1, exit_count=0, review_count=0))
    assert decision.severity == "action"
    assert "trim" in decision.body.lower()


def test_buys_and_sell_signals_rollup():
    decision = classify_run_outcome(
        _outcome(actionable_buy_count=2, trim_count=1, exit_count=1, review_count=0)
    )
    assert decision.severity == "action"
    body = decision.body.lower()
    assert "2" in body and "buy" in body
    assert "trim" in body and "exit" in body


def test_all_zero_is_clean():
    decision = classify_run_outcome(_outcome())
    assert decision.severity == "clean"


def test_clean_notify_on_clean_true_notifies():
    decision = classify_run_outcome(_outcome(), notify_on_clean=True)
    assert decision.severity == "clean"
    assert decision.should_notify is True


def test_clean_notify_on_clean_false_suppresses():
    decision = classify_run_outcome(_outcome(), notify_on_clean=False)
    assert decision.severity == "clean"
    assert decision.should_notify is False


def test_failed_precedence_beats_halted_and_action():
    # exit 1 AND a positive buy count AND halted: failed wins.
    decision = classify_run_outcome(
        _outcome(last_exit_code=1, pipeline_halted=True, actionable_buy_count=3)
    )
    assert decision.severity == "failed"


def test_halted_precedence_beats_stale_and_action():
    decision = classify_run_outcome(
        _outcome(pipeline_halted=True, stale_ingest=True, actionable_buy_count=3)
    )
    assert decision.severity == "halted"


# ---- P0-3: rc=124 (watchdog timeout) → failed with timeout label ----

def test_exit_124_is_failed_with_timeout_label():
    """P0-3: watchdog kills the pipeline → rc=124 → severity failed, 'timeout' in title."""
    decision = classify_run_outcome(_outcome(last_exit_code=124))
    assert decision.severity == "failed"
    assert decision.should_notify is True
    assert "timeout" in decision.title.lower()


# ---- Unknown nonzero exit codes (127/137/143/99) must be failed, never clean ----

@pytest.mark.parametrize(
    "code,expected_label_fragment",
    [
        (127, "127"),
        (137, "137"),
        (143, "143"),
        (99, "99"),
    ],
)
def test_unknown_nonzero_exit_is_failed(code, expected_label_fragment):
    """Any nonzero exit not in _EXIT_LABELS must produce severity=failed (not clean/halted/stale).

    Exit 127 = command not found, 137 = SIGKILL/OOM, 143 = SIGTERM,
    99 = generic unknown code — all must be treated as failures.
    """
    decision = classify_run_outcome(_outcome(last_exit_code=code))
    assert decision.severity == "failed", (
        f"exit {code} must be severity=failed, got {decision.severity!r}"
    )
    assert decision.should_notify is True, f"exit {code} must trigger notification"
    assert expected_label_fragment in decision.title or expected_label_fragment in decision.body, (
        f"exit code {code} must appear in title or body; "
        f"title={decision.title!r}, body={decision.body!r}"
    )


def test_unknown_nonzero_exit_beats_halted_and_stale():
    """Unknown nonzero exit (137) must take precedence over halted/stale flags."""
    decision = classify_run_outcome(
        _outcome(last_exit_code=137, pipeline_halted=True, stale_ingest=True)
    )
    assert decision.severity == "failed"


def test_unknown_nonzero_exit_never_clean():
    """An unknown nonzero exit (99) with all-zero counts must NOT classify as clean."""
    decision = classify_run_outcome(_outcome(last_exit_code=99))
    assert decision.severity != "clean", "exit 99 must never produce severity=clean"


def test_promotions_alone_trigger_action_with_ids_in_body():
    """A fund newly reaching core_dca / accelerate_dca must page as 'action'
    even when there are zero buys/sells — the promotion IS the signal."""
    decision = classify_run_outcome(_outcome(
        promotion_count=2, promotion_ids=("161903", "018132"),
    ))
    assert decision.severity == "action"
    assert decision.should_notify is True
    assert "2 promotions" in decision.body
    assert "161903" in decision.body and "018132" in decision.body


def test_promotions_rollup_joins_with_buys():
    decision = classify_run_outcome(_outcome(
        actionable_buy_count=1, promotion_count=1, promotion_ids=("519069",),
    ))
    assert decision.severity == "action"
    assert "1 buys" in decision.body
    assert "1 promotion" in decision.body
    assert "519069" in decision.body


def test_promotion_ids_capped_in_body():
    ids = tuple(f"00000{i}" for i in range(8))
    decision = classify_run_outcome(_outcome(promotion_count=8, promotion_ids=ids))
    assert decision.severity == "action"
    assert "000004" in decision.body      # first five named
    assert "000007" not in decision.body  # tail elided
    assert "…" in decision.body


# ---- Task 7: degraded severity, health-append, recovery notice ----


def _warn_digest():
    return HealthDigest((HealthItem("board_pe_dark", "warn",
                                    "板块PE: DARK ≥4td — 价值陷阱检测不可用"),))


def _info_digest():
    return HealthDigest((HealthItem("board_pe_stale", "info", "板块PE: STALE-1 (07-06)"),))


def test_always_notify_contains_degraded():
    assert "degraded" in _ALWAYS_NOTIFY


def test_health_warn_escalates_clean_to_degraded():
    d = classify_run_outcome(_outcome(health=_warn_digest()))
    assert d.severity == "degraded"
    assert d.should_notify is True
    assert "DARK" in d.body


def test_degraded_notifies_even_when_notify_on_clean_false():
    d = classify_run_outcome(_outcome(health=_warn_digest()), notify_on_clean=False)
    assert d.severity == "degraded"
    assert d.should_notify is True


def test_health_warn_escalates_action_to_degraded_keeps_rollup():
    d = classify_run_outcome(_outcome(actionable_buy_count=2, health=_warn_digest()))
    assert d.severity == "degraded"
    assert "2 buys" in d.body        # action rollup preserved in body
    assert "DARK" in d.body


def test_stale_precedence_beats_degraded_but_appends_health():
    d = classify_run_outcome(_outcome(stale_ingest=True, health=_warn_digest()))
    assert d.severity == "stale"     # stale > degraded
    assert "DARK" in d.body          # health still appended to body


def test_failed_appends_health_to_body():
    d = classify_run_outcome(_outcome(last_exit_code=1, health=_warn_digest()))
    assert d.severity == "failed"
    assert "DARK" in d.body


def test_info_only_health_stays_clean():
    d = classify_run_outcome(_outcome(health=_info_digest()))
    assert d.severity == "clean"


def test_health_none_backcompat_stays_clean():
    d = classify_run_outcome(_outcome(health=None))
    assert d.severity == "clean"


def test_recovery_notice_forces_clean_notify():
    d = classify_run_outcome(
        _outcome(recovery_notice="轮动雷达恢复 ok (200 boards) — 此前弃权 1 日"),
        notify_on_clean=False,
    )
    assert d.severity == "clean"
    assert d.should_notify is True
    assert d.title == "IRC: 轮动雷达恢复"
    assert "恢复" in d.body


def test_degraded_warn_suppresses_recovery():
    # A recovering day that also has a warn pages degraded, not a recovery notice.
    d = classify_run_outcome(_outcome(
        health=_warn_digest(), recovery_notice="轮动雷达恢复 ok (1 boards) — 此前弃权 1 日",
    ))
    assert d.severity == "degraded"
