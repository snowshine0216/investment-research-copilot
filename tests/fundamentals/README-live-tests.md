# Live AkShare tests — run discipline

The tests in `test_fund_announcement_em_live.py` hit the real AkShare network
to verify that `ak.fund_announcement_em` exists and returns usable data for
the three Q4-prerequisite symbols (gold `518880`, bond `000001`, active fund
`005827`).

## How to run

Both the marker AND the env var are required (dual gate):

```bash
IRC_RUN_LIVE_AKSHARE=1 pytest -m live_akshare \
    tests/fundamentals/test_fund_announcement_em_live.py -v -s
```

Expected: 5 tests pass (1 preflight + 3 per-symbol + 1 aggregate gate).
Each per-symbol test prints a one-line summary; the aggregate gate prints
the AkShare version on success.

## Fixture refresh behaviour

Successful per-symbol runs write/overwrite:

- `tests/fixtures/akshare/fund_announcement_em_518880.json`
- `tests/fixtures/akshare/fund_announcement_em_000001.json`
- `tests/fixtures/akshare/fund_announcement_em_005827.json`

Each file carries `columns`, `rows`, `captured_at` (ISO-8601 UTC),
`akshare_version`. Chinese column names are preserved verbatim
(`ensure_ascii=False`). The fixture is **always overwritten** — it is a
captured shadow of the latest live response, not a frozen snapshot.

Tests never assert content equality against the fixture (only column shape
+ non-empty), so daily content drift is benign. Diff churn on the fixture
file is expected and signals that new announcements arrived upstream.

## What FAILURE means

Any failing test raises with a structured message prefixed
`Q4 PREREQUISITE FAILURE: …`. The first failing-test stdout line carries
the symbol, the specific check, the next action ("STOP and re-decide Q4"),
and the three fall-back options.

Fall-back options (verbatim from `docs/diagnosis-thesis-cards-evidence-gap.md` §5):

- **(a) Re-pin AkShare** to a version that exposes `fund_announcement_em`.
- **(b) Reuse theme reports with promoted scope** — treat asset-class macro
  citations as information-leg for gold + cn_bond_fund.
- **(c) Exclude gold + cn_bond_fund from V1** — drop those asset classes
  from the actionable opportunity surface.

The autodev orchestrator does NOT auto-select a fall-back; it escalates to
the user with the structured failure message. See
`docs/2026-05-22-thesis-cards-evidence-gap/items/004-spec.md` §"Stop /
proceed contract" for the operational steps the orchestrator follows on
FAIL.

## Default `pytest` behaviour

Running `pytest` (or `pytest -x`) without the marker AND env var skips
every live test in this file. Zero AkShare calls occur in default suite
runs.

The companion file `test_fund_announcement_em_failure_modes.py` runs in
every default suite invocation — it patches `_ak_call` to lock the
failure-trace tone and does NOT hit the network.
