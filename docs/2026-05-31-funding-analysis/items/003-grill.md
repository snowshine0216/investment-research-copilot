Verdict: PASS

Subagent: opus
Questions resolved: 9
Docs touched:
  - CONTEXT.md (commit 7d21515)
  - docs/adr/0010-cn-fundamentals-provider-seam.md (commit 7d21515)
Spec refined: items/003-spec.md (commit 7d21515)

## Resolved decisions

- **Q: G1 — which Tushare endpoints map to the three seam methods, and does `target_price` need a paid tier?**
  A: filing digest → `fina_indicator` (+`income`); broker `target_price` → `report_rc`; index valuation → `index_dailybasic`. `report_rc` (target prices) is points/paid-tier gated and cannot be confirmed offline. `TushareProvider` methods degrade to `None`/`()` when an endpoint is unreachable, so the seam is correct on a free token; the double-gated live test is the pin-point with its **mandatory assertion scoped to filing-digest only** and the `target_price` smoke optional.
  Rationale: the live test, not an offline guess, is the designed pin point; degrade-to-`None` makes an unconfirmed endpoint a no-op, never a regression (ADR 0009 unchanged when `target_price` is unreachable).
  Doc impact: ADR 0010 §4; CONTEXT.md `TushareProvider` + `live_tushare` gate; spec `## Resolved decisions` G1.

- **Q: G2 — does a Tushare fallback call count against the fetch budget?**
  A: No. V1 = AkShare-only budget accounting; Tushare not metered.
  Rationale: verified `FetchPlan.total_calls()` is a static preflight formula over cold/stale AkShare-fund cardinality (`opportunity_cmd.py:96,840-843`); no live per-call counter exists; the `fetch_budget_exhausted` sentinel fires pre-build independent of provider. A Tushare fallback fires inside already-budgeted `fetch_cn_*` execution on a per-constituent miss — it changes neither `total_calls()` nor the sentinel emission path, so the abstraction structurally cannot change when/whether the sentinel fires.
  Doc impact: ADR 0010 §3; CONTEXT.md "Provider seam vs fetch budget"; spec G2.

- **Q: G3 — thread the provider deep, or resolve once at the edge?**
  A: Resolve `default_cn_provider()` once at each command edge; thread ONE keyword-only `provider` param through `build_snapshot`/`populate_inputs` to the call-sites; inner functions keep default-arg `default_cn_provider()`.
  Rationale: DI at the edge keeps stage cores pure (CLAUDE.md) and is the smallest behavior-preserving diff; default-args keep every existing inner-function test green. All four call-sites confirmed: filing/broker via `build_snapshot → _build_active_fund_snapshot → _evidence_for_constituent` (snapshot.py:337,355) and `_build_legacy_snapshot → _build_cn_snapshot` (snapshot.py:595,600); index via `populate_inputs → _index_valuation_metrics` (inputs_loader.py:105).
  Doc impact: CONTEXT.md `default_cn_provider`; spec G3.

- **Q: DEFAULT behavior-preservation — how is the refactor locked?**
  A: Byte-equality regression on stubbed `_ak_call` — `AkShareProvider().fetch_*(x)` asserted equal to the direct module-function call on the same stub. Feasible: the two `_ak_call` monkeypatch points already exist; no parsing re-implemented in the provider layer.
  Rationale: token-absent default is `AkShareProvider`-only ⇒ byte-identical to pre-003.
  Doc impact: ADR 0010 Consequences; CONTEXT.md `AkShareProvider`; spec Resolved decisions.

- **Q: PROXY — direct or via `IRC_HTTPS_PROXY`?**
  A: Direct. `api.tushare.pro` is mainland-CN, same class as the AkShare CN calls kept direct. No `http_proxy.py` change.
  Rationale: only LLM/web/Jina/DXY-via-EastMoney are proxied (`http_proxy.py`, README).
  Doc impact: ADR 0010 Consequences; CONTEXT.md `_tushare_call`.

- **Q: NETWORK MOCK SEAM — exact monkeypatch point?**
  A: A single `_tushare_call(token, fn_name, **kwargs)` edge (local `import tushare`), mirroring `_ak_call`; unit tests monkeypatch it / feed fixture frames to the pure mapping helpers; `FallbackProvider` tested with in-memory fakes.
  Rationale: keeps I/O at the edge; no `tushare` import at module load.
  Doc impact: CONTEXT.md `_tushare_call`; spec NETWORK MOCK SEAM.

- **Q: Are the existing typed returns reusable, or are new DTOs needed?**
  A: Reuse `FilingDigest`/`BrokerReport` (`fundamentals/types.py`) + `IndexValuation` (`fundamentals/index_valuation_types.py`); no new DTOs.
  Rationale: verified the three fetchers already return exactly these frozen dataclasses.
  Doc impact: CONTEXT.md `CnFundamentalsProvider`; ADR 0010 §1.

- **Q: Default vs fallback semantics — config-selectable primary or per-method fallback?**
  A: Per-method fallback (AkShare primary, Tushare fills misses), never-raises; no YAML knob; selection implicit on token presence.
  Rationale: AkShare-first reproduces today exactly; Tushare only fills documented gaps (target_price). A config primary swap is surface for no V1 value and risks output drift.
  Doc impact: ADR 0010 §2; CONTEXT.md `FallbackProvider`.

- **Q: Does the spec's AC9 static-profile claim hold against the test?**
  A: No — FALSE as written. `test_static_profile_invariant.py` enumerates `akshare_fundamentals.py` + `snapshot.py` explicitly (no glob scope), so the new modules are NOT auto-in-scope.
  Rationale: read the test; it lists files literally.
  Doc impact: spec AC9 struck-through + corrected to require a new grep assertion over `provider.py`/`tushare_provider.py`; ADR 0010 Consequences.

## Notes

- No spec-vs-load-bearing-ADR/code contradiction found ⇒ PASS.
- Four migration call-sites (inputs_loader.py:105; snapshot.py:337,355,595,600) verified TRUE.
- Fetch-budget non-interaction verified TRUE.
- One false claim found and corrected: AC9 static-profile grep scope.
- ADR 0010 created (cleared all three of the three-of-three bar: hard-to-reverse architectural seam; surprising fallback-not-primary + not-metered semantics; real complexity-vs-extensibility + budget-accounting trade-off).
