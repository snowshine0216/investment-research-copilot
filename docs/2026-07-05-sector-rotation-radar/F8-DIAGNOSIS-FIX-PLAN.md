# F8 diagnosis + fix plan — board-endpoint egress block

**Date:** 2026-07-05
**Owner:** picked up in a fresh session (post-#206 / #207 merge)
**Covers:** TODOS "Sector rotation radar" → **F8** (blocker), **F7** (turnover fetch),
**Do-now** (first `irc rotation seed`), and the reconciliation of
`docs/2026-07-05-sector-rotation-radar/items/001-probe-notes.md`.

---

## 0. Phase 1 RESULT — GATE OUTCOME: hard-blocked (branch 2c) — 2026-07-05

Diagnosis ran (`scripts/rotation_f8_diagnose.py`, unsandboxed, 2 runs incl. a
mid-run proxy restart). **F8 confirmed hard-blocked from this host.** Full matrix
+ interpretation in [`items/001-probe-notes.md`](items/001-probe-notes.md)
"Addendum 2026-07-05 (later)". Signature:

- Proxy tunnel is alive (baidu-via-proxy 200/0.1s) but its **exit IP is EM-blocked**
  (every `push2*` host → fast ~1.1s ProxyError); restarting revives the tunnel, not
  EM access. Rotates to an EM-allowed exit only transiently (that window produced
  the probe-notes "2/2").
- Direct egress is **burst-throttled** (`ulist.np` 200×3 → 502×3) and the board
  endpoints are refused outright (502 / RemoteDisconnected) — endpoint + IP specific.

**Branch taken → 2c (hard-blocked).** No code/autodev fix exists — the block is
egress. **Not built: F8 migration** (deferred; also needs a reachable history
source, and `push2his` is blocked too). **Real fix = a working CN egress**
(CN-residential/EM-allowed proxy exit, CN VPS, or paid CN data source).

**What proceeds without egress (this session):**
- Phase 5 doc reconciliation — DONE (probe-notes addendum, this section, TODOS).
- Phase 3 F7 build — **DONE** (offline TDD; branch `fix/rotation-f7-board-turnover`,
  unmerged). `fetch_board_hist` fields2 → `f51..f61`; `parse_board_hist` reads
  turnover from position 10 (f61) when `len(parts) >= 11`, else `None` (8-col
  back-compat); chg stays derived; no `RADAR_VERSION` bump. Fixture = the real
  BK0475 (银行Ⅱ) 11-col rows from the probe notes. tests/rotation 62 + commands
  rotation 12 green, ruff clean. Makes the seed capture turnover from day 1 the
  moment egress returns (F7-before-seed order satisfied).

**Blocked until a CN egress exists:** Phase 4 (seed), Phase 6 (monitor board-PE
un-dark). Re-run `scripts/rotation_f8_diagnose.py` after any egress change; if the
board rows come back, run F7-then-seed and verify `data/rotation/` + forward ledger.

---

## 1. Problem statement

The rotation vertical shipped (#206) but has never produced a real radar: the
first `irc rotation seed` failed, and the daily run writes `data_status:
"abstain"`. Root symptom (**F8**): the two board endpoints in
`src/irc/rotation/board_fetch.py` are unreachable through the current
`IRC_CN_PROXY` egress —

- `push2.eastmoney.com/api/qt/clist/get?fs=m:90+t:2` — board **snapshot /
  enumeration** (every daily run), and
- `push2his.eastmoney.com/api/qt/stock/kline/get` — board **history**
  (seed backfill + F7 turnover) —

both fail with `ProxyError` / `Read timed out`, **while `ulist.np` (the monitor
flow endpoint) works on the same host + same proxy.**

**The docs contradict each other and neither is yet trusted:**

- `001-probe-notes.md` **addendum** (lines 128–172) records F7's `f61` turnover
  probe as **"2/2 calls succeeded via `IRC_CN_PROXY`… F7 is probe-cleared, ready
  to build."**
- TODOS **F7/F8** (reconciled by commit `92773fd4`, TODOS only) records a later
  **reproducible unsandboxed re-probe: `push2his` ProxyError 3/3** incl. real
  codes BK0475/BK1036 — i.e. the addendum's success was **not reproducible**.

We do **not** assume either is correct. The addendum itself carries the caveat
that *a sandboxed Claude Code shell resets both direct push2his connections and
the proxy CONNECT* — so the "2/2 success" and the "3/3 fail" may have been run
under different shell/egress conditions. **F8 must be pinned empirically before
any fix is chosen.**

### Why this gates everything

`clist/get` (snapshot) is needed on **every** daily run; `push2his kline/get` is
needed by the seed backfill and by F7. With both dark:

- **F7** (board-kline turnover, `f61`) cannot be built *or* verified — its only
  data source is `push2his kline/get`.
- **First seed** cannot run (`boards={'done': 0}`) — so `data/rotation/` stays
  absent, the forward ledger never starts (F1's 4–6-week clock), and boards stay
  `immature`.
- **Monday 2026-07-06 15:45** fire will `abstain` (honest, not broken).
- **Side effect, same root cause:** the monitor's dual-track valuation *industry*
  leg (also `clist/get`, via `em_raw.fetch_board_pe_frame`) has been silently
  DARK since 2026-06-30 (`data/monitor/industry_pe/` newest file is empty `{}`),
  ADR-0020-tolerated.

---

## 2. Goals / non-goals

**Goals**

1. Pin the **real** F8 failure signature (proxy-dead vs tunnel-rotation-flaky vs
   EM endpoint-throttle vs push2his-host-block) with one paced, unsandboxed probe
   matrix — *and* capture the real 11-col `f61` kline row F7 needs in the same run.
2. From that evidence, choose the F8 fix branch (reachable egress / rotation-aware
   retry / migrate / accept-abstain).
3. If egress is reachable: land **F7** (before the seed), run the **first seed**,
   and confirm the monitor board-PE leg un-darkens.
4. Reconcile `001-probe-notes.md` with reality (one honest story), tighten TODOS.

**Non-goals**

- Building the `clist/get`→`ulist.np` **migration** (TODOS F8 option b) up front.
  It is only reached on the hard-blocked branch, and only after a user decision —
  it is non-trivial (needs a static BK-code enumerator **and** a reachable
  board-history source; `push2his` is itself blocked).
- Any `radar_version` bump. F7 is an availability-class change (f100-fix
  precedent). No engine/schema change anywhere in this plan.
- F1–F6 layer-3 hooks (data-gated / priority-deferred; unchanged).

---

## 3. Staged plan (hard gate after Phase 1)

```
Phase 1  F8 diagnosis probe (user runs unsandboxed)
   │
  GATE   read signature table → pick branch
   ├── 2a egress reachable ──► Phase 3 (F7) ─► Phase 4 (seed) ─► Phase 6 (monitor verify)
   ├── 2b tunnel-flaky      ──► bounded rotation-aware retry → (2a if it works, else 2c)
   └── 2c hard-blocked      ──► user sub-fork: migrate vs accept-abstain (no F7/seed)
Phase 5  doc reconciliation  (known-wrong correction now; final wording after the gate)
```

Phase 5's *known-wrong* correction is done **immediately** (independent of the
gate); its final wording folds in the Phase-1 finding.

---

## 4. Phase 1 — F8 diagnosis probe

**Deliverable:** `scripts/rotation_f8_diagnose.py`, extended from the existing
`scripts/rotation_probe.py` transport (raw `requests` through `resolve_cn_proxy()`
— **T2: never curl-through-proxy**). Ops/diagnostic script → lives in `scripts/`,
reuses `board_fetch.py`'s pure parsers, no TDD ceremony (it *is* the effect edge).

**Matrix** — for each cell, N≈4 paced calls (~3s apart):

| Endpoint | Host | through `IRC_CN_PROXY` | direct (no proxy) |
|---|---|---|---|
| `ulist.np` (flow — known-good control) | push2 | ✓ | ✓ |
| `clist/get` board snapshot (`fs=m:90+t:2`) | push2 | ✓ | ✓ |
| `push2his kline/get` (`fields2=f51..f61`) | push2his | ✓ | ✓ |
| `baidu.com` (tunnel-liveness control) | — | ✓ | — |

**Per call, capture:** HTTP status **or** exception class (distinguish
`ProxyError` / `ConnectionError` / `ReadTimeout` / empty-200-body), latency,
body-nonempty. Emit a compact table + a machine-readable JSONL block to paste
into the doc.

**Pacing note (not a hammer):** measuring a *success rate* across a rotating
tunnel needs a few paced calls. This is deliberate, spaced diagnosis — **not** the
tight-loop retry-while-blocking self-DoS the ADR/ T3 forbids. Modest N, fixed
spacing, single session, then stop.

**Two-birds:** the kline cell uses **extended `fields2=f51..f61`**, so any success
also produces F7's real 11-col capture (position 10 = `f61` = 换手率) — discharging
the F7 live-probe requirement in the same run.

**Signature → root cause → branch:**

| Observation | Root cause | Branch |
|---|---|---|
| baidu-through-proxy fails | tunnel dead / bad creds | 2b (fix tunnel) |
| ulist.np-proxy OK, boards-proxy **intermittent** ProxyError across repeats | tunnel rotation: only some exit IPs reach board plane | 2b (rotation-aware retry) |
| boards-proxy **consistently** fail AND boards-direct fail, ulist.np-proxy OK | EM board-plane endpoint-specific geo-throttle | 2c (CN-residential IP / migrate) |
| clist OK, only push2his fails | push2his host-specific block | 2c (separate history source) |
| all-**direct** OK | proxy is the problem, not EM | 2a (drop proxy for boards) |
| boards-proxy OK (contradicts TODOS) | prior failure was a sandbox/transient artifact | 2a (F8 resolved) |

**Caveat:** I (the assistant) am sandboxed; sandboxed shells reset EM connections
(memory + probe-notes). **The probe must be run by the user in an unsandboxed
shell**, with `IRC_CN_PROXY` exported. The baidu control confirms the shell's
proxy CONNECT is live before we read anything into an EM failure.

---

## 5. GATE + Phase 2 branches

Read the Phase-1 table, then:

- **2a — egress reachable.** F8 resolved. Record the working config (proxy on/off,
  which host, any exit-IP stickiness) in the probe notes + TODOS. → **Phase 3**.
- **2b — tunnel-flaky.** If the boards are reachable on *some* exit IPs, add a
  bounded, paced rotation-aware retry (a few attempts, spaced, respecting the
  never-hammer rule) at the `board_fetch` edge; classify persistent failure as
  TRANSIENT (already the contract). If that yields workable coverage → treat as 2a;
  else → 2c.
- **2c — hard-blocked.** F8 = confirmed egress block. **Stop and bring a sub-fork
  to the user:** (i) migrate the board fetch off `clist/get`+`push2his` (needs a
  static BK enumerator + a reachable history source — non-trivial), or (ii) accept
  honest `abstain` until a CN VPS/residential proxy appears. The daily run already
  abstains correctly, so nothing is *broken* on this branch — it just stays
  advisory-dark. **No F7, no seed** on this branch.

---

## 6. Phase 3 — F7 turnover build *(only on the egress-reachable branch)*

Small, TDD (red → green), in `src/irc/rotation/board_fetch.py`:

1. **Red.** Pin an 11-col kline fixture from the **real** BK0475 capture in the
   probe-notes addendum:
   `2026-07-02,3843.00,3880.50,…,2.37,1.20,46.11,0.29` (turnover `0.29` at
   position 10) and the `0.25` row. Assert `parse_board_hist` fills
   `turnover_pct` from position 10. Add an 8-col back-compat fixture → asserts
   `turnover_pct` stays `None` (old snapshot/backfill rows unaffected).
2. **Green.** Extend `fetch_board_hist` `fields2` to `f51,…,f61`; in
   `parse_board_hist`, parse position 10 with the tolerant `_f` **only when**
   `len(parts) >= 11` (shorter rows → `None`, as today).
3. **Keep** `chg_pct` **derived** from close-vs-prev-close — `f59` is an incidental
   cross-check only; do not switch tested logic. Flow leg stays `None` on backfill
   (kline carries no flow). `board_pe` stays `None` on backfill (snapshot-only).
4. **No `radar_version` bump** (availability class — f100 precedent). Docstrings in
   `board_fetch.py` that currently say "do NOT add f61 without an AC1-style live
   probe first" get updated to "probe-confirmed by Phase 1 <date>".

**Order constraint (locked):** F7 must land **before** the first `irc rotation
seed`. Seed resumability (AC2) skips boards already ≥`MIN_TD` rows in the store, so
backfill rows written with `turnover_pct=None` are **never healed** by a re-seed;
post-seed, F7 only helps re-seeds/new boards while the turn leg waits ~20 live
snapshot days.

---

## 7. Phase 4 — first seed *(only on the egress-reachable branch, after F7)*

- Run `irc rotation seed` (resumable, partial-tolerant; holdings cache already warm
  — 479 funds in `data/narrative_holdings/`; ≈86 paced board-history calls +
  stock→board `ulist.np` chunks bounded by `IRC_ROTATION_TOPUP_BUDGET`).
- If the ~2–3k-symbol board map doesn't complete in one run, rerun (resumable) or
  raise `IRC_ROTATION_TOPUP_BUDGET`.
- **Verify:** `data/rotation/` populated, series store has boards, and the first
  post-seed run appends to `data/rotation/forward_ledger.jsonl` (starts F1's clock).
- Ideally before the Mon 15:45 fire (else that fire abstains — acceptable).

---

## 8. Phase 5 — doc reconciliation

**Now (independent of the gate) — the known-wrong correction:**

- `001-probe-notes.md`: append a dated correction to the F7 addendum marking
  **"F7 is probe-cleared, ready to build"** as **SUPERSEDED by F8** — the 2/2 via
  `IRC_CN_PROXY` was **not reproducible** (a later unsandboxed re-probe failed
  3/3); point to TODOS F8. Keep the `f61`/field-code table as *best-known, pending
  Phase-1 confirmation* (don't delete hard-won field codes). Note the likely
  sandbox/transient explanation without over-committing.

**After the gate — final wording:**

- Fold the Phase-1 diagnosis result (the real signature) into the probe-notes
  correction and into TODOS F7/F8/do-now. TODOS was already reconciled by
  `92773fd4`; only tighten with the outcome (e.g. "F8 root cause = <X>; fix branch
  = <Y>").

---

## 9. Phase 6 — monitor board-PE side-check *(verification only)*

Same `clist/get` root cause as the monitor dual-track valuation *industry* leg
(dark since 2026-06-30). No new engineering:

- **If Phase 1 finds a reachable egress:** confirm `data/monitor/industry_pe/`
  repopulates on the next monitor brief (industry leg un-darkens).
- **If hard-blocked:** record that the monitor industry leg stays ADR-0020-tolerated
  DARK for the same reason; note it in TODOS alongside F8 so the two aren't tracked
  as separate mysteries.

---

## 10. Risks / traps (carried from the vertical's scars)

- **T2 — never curl-through-proxy.** Probe uses `requests` through
  `resolve_cn_proxy()`; a curl-through-proxy false-fails (memory: flow-coverage).
- **T3 — never hammer live EM.** Phase 1 is paced + bounded + single-session; the
  breaker/probe posture is protective, never self-extending.
- **Sandbox resets EM connections.** All live probes run **unsandboxed** by the
  user; baidu control confirms tunnel liveness first.
- **F7-before-seed order** is a correctness constraint, not a preference (§6).
- **No `radar_version` bump** (§2) — availability class.
- **Field codes are interface-specific** (f127→f100 scar) — Phase 1's real capture
  is the confirmation of record for `f61`.

---

## 11. Open decisions deferred to the gate

1. Which Phase-2 branch (decided by the Phase-1 signature table).
2. On 2c only: migrate vs accept-abstain (explicit user sub-fork).
3. Whether 2b's rotation-aware retry is worth building (depends on the measured
   success rate across exit IPs).
