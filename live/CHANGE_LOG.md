# Live Runtime CHANGE_LOG

## 2026-08-30 — CFD limit-retest replication + V2B wick-range alignment

- OCO stop-entry contrast failed earlier same day → limit-retest demoted from
  demo path; kept as frozen research signal only.
- CFD replication (frozen NQ decision box, no CHOP20): driver
  `live/cfd_wick_reject_range_seed_retest.py` →
  `live/state/cfd_wick_reject_range_seed_retest/`.
  - NAS100 mirrors NQ (dev avgR +0.09 / holdout −0.23) — portability only.
  - SPX500/US30 holdout+ is thin/inconsistent vs failed development — not
    broader-index confirmation. **Demo blocked.**
- V2B causal state label (not hybrid): driver
  `live/nq_v2b_wick_range_alignment.py` →
  `live/state/nq_v2b_wick_range_alignment/`.
  - Prior-opposed resting-limit NQ: OPPOSED_BREAK not harmful (avg $/trade
    above ALIGNED); skip-opposed CF not run. Sparse coverage (53/439 under
    active resolved seed).

## 2026-08-30 — NQ WICK_REJECT range-seed breakout–retest (Phases 0–3)

- Reframe: 4h WICK_REJECT as **range seed**, not fade (Prototype B follow-on).
- Driver: `live/nq_wick_reject_range_seed_retest.py`
- Hub: `live/state/nq_wick_reject_range_seed_retest/` (MODEL_CONTRACT.yaml frozen).
- Census: 91/122 eligible seeds; 67 primary limit-retest fills (74% of seeds).
- Locked primary: **dev** +$23.9k PF 1.90 avgR +0.18 (53 fills); **holdout** avgR −0.04 (14 fills).
- Controls: retest > immediate chase on dev; synthetic boundary fill stronger than retest — edge may be break+box, not pullback.
- Stance: **RESEARCH** (not promote). Phase 4 / StrategyPlugin blocked.

## 2026-08-29 — US30 continuation campaign audit (post A/B/C)

- A/B/C matrix complete: A/B rejected; C 2R→10R N/S 1.84 (5207u / **1736 campaigns**).
- Frozen contract `us30_st_pmc_completed_hour_continuation_v1` +
  `CONTINUATION_AUDIT.md` before further path-C variation.
- One-entry/signal PASS on preferred tape; profit-cap 2R/3R → N/S deeply
  negative (runner/tail). Engine slippage stress running (DSR `TRL-2026-00188`).
- PMC failed-break fade Phase 1/2 also complete (`us30_pmc_failed_break_fade/`,
  `TRL-2026-00187`) — RESEARCH_WEAK_POSITIVE, no promote.

## 2026-08-29 — US30 ST+PMC fair-3R invalidated; causal revival A/B/C

- Signal-hour attribution on retired fair-3R (578 campaigns): 12.8% same-hour
  fills; 90% post-close ST-limit retest opportunity; 54% post-close H/L
  continuation. Hub: `live/state/us30_st_pmc_signal_hour_attribution/`.
- Demo decision: `demo_us30_hourly_st_pmc` **alpha_status=invalidated**
  (prefer stop; lifecycle/reconcile only if retained). Do not cite N/S 29.39.
- New plugin `hourly_st_pmc_causal_revival` + driver
  `live/us30_st_pmc_causal_revival_abc.py` (paths A pre-posted PMC, B one-shot
  PMC retest 240m, C H/L continuation; locked 2R→10R cell; DSR `TRL-2026-00186`).
- Completed-hour control remains N/S 1.47 (2R→10R) / −0.21 (fair 3R) under
  `live/state/us30_st_pmc_runner_variants/`.

## 2026-08-28 — W1+8h v1 cross-market portability (NQ/MNQ/YM/MYM)

- Overnight stress/port left futures xmarket at 0 trades (`KeyError: ts_event` on
  front-month 4h `time`/`date` CSVs). Added `_load_4h_any` in
  `live/weekly_open_day_breakout_w1_add8h_stress_portability.py`.
- Re-ran `--stages xmarket` broker-like Engine + 1m fill. All five books positive
  net; decision → **broader index structural effect — locked OOS/forward next;
  still NO demo** (paper gate unchanged). Hub:
  `live/state/weekly_open_day_breakout_w1_add8h_v1_stress_port` · DSR `TRL-2026-00168`.

## 2026-08-21 — OPEN_ORDER_STATUSES + US30 ST+PMC stale-arm cancel

- **Bug:** `StrategyContext.strategy_open_orders` (and RiskManager open-order
  counts) only treated `submitted` / `partially_filled` as open. OANDA rests
  land as `working`, so ST+PMC hourly refresh saw zero priors and stacked a new
  LIMIT each hour (`orders=1→5` on `us30_…_3r_oanda` / `-003`).
- **Fix:** shared `OPEN_ORDER_STATUSES` in `live/models.py` includes
  `working` / `pendingnew` / `accepted` / `pending`; wired into
  `StrategyContext`, `RiskManager`, ST+PMC `_open_entry_limits`, and London
  prior-opposed gate audit helpers. Unit test covers `working`.
- **Ops:** stopped daemon; cancelled remote LIMITs **5/6/7/8**; kept **11**
  (`ord_0fc075855acd` @ 52945.2). Local CSV aligned. Restarted
  `demo-us30-hourly-st-pmc-oanda` → heartbeat `orders=1`. Artifacts:
  `live/demo/oanda_practice_snapshot/STALE_ARM_DEDUPE_R3.{md,json}`.

## 2026-08-19 — Gmail potions-prompt poll TLS rebuild

- Poll loop rebuilt Gmail client after transient `Broken pipe` / SSL unexpected
  EOF (stale httplib2 after long agent runs). These were the user-visible
  "timeouts" — not Cursor `AGENT_TIMEOUT_SEC` (no agent TimeoutExpired in log).

## 2026-08-19 — OANDA containment false-positive fix + cross-book entry gate

- Classifier: flat + intentional `bracket_role=entry` → `armed_entry` (ok), not
  `orphan_protective`. True SL/TP leftovers stay orphans. Flat + entry arms while
  account already holds the focus instrument → `cross_book_entry` (shadow detect).
- Sweep: do not cancel local entry arms when flat; shadow no longer would-cancel
  on healthy armed books.
- **Always-on** `OandaBroker` gate blocks entry submits when sibling/account qty
  is open and local strategy is flat (`cross_book_instrument_open`); manager
  records `routing_blocked`. Containment remains **shadow**.
- Ops: cancelled NAS100 orphans 1719/1756/1758/1760 (+ restart re-arm 1767).
  Restarted `nas100_…_3r_oanda` + `nas100_v2b_ungated_oanda`.
- Tests/fixtures: armed_entry + orphan_SL cases; Aug 14 entry-STOP fixtures
  reclassified to `armed_entry`.

## 2026-08-19 — RTH first-hour follow broker variants (NQ + NAS100) RETAIN

- Plugin `first_hour_follow` extended: `entry_mode` (market_close / retrace_limit),
  `sl_mode` (open / body_frac / extreme), `tp_mode` (body_mult / r_mult),
  `tp_ladder_r` (1R/2R/3R scale-out).
- Drivers: `live/nq_1h_first_hour_broker_variants.py` (also `--instrument NAS100`),
  wrapper `live/nas100_1h_first_hour_broker_variants.py`.
- **NQ hub** `live/state/nq_1h_first_hour_broker_variants/`:
  baseline SL=open TP=3×body **N/S 5.57** (+$177k); half-body 3R 4.74;
  0.75-body ladder 3.95; retrace72 **0.33 reject**.
- **NAS100 hub** `live/state/nas100_1h_first_hour_broker_variants/`:
  same rank order — baseline **N/S 4.09**; ladder dollars; retrace 0.33 reject.
- Mechanics / why (open continuation, 3×body efficiency):
  `…/nq_1h_first_hour_broker_variants/MECHANICS.md`.
- Tracker: **RETAIN** sleeve under STRATEGY_TRACKER “RTH first-hour follow”
  (below prior-opposed / ST+PMC / Asia-range; good capital-efficient daily book).
  Emails sent.

## 2026-08-18 — NQ 15m + first-hour large-candle p99 (fallback p95)

- Same 3R follow contract as the p90 books, causal expanding **p99** range
  (fallback **p95** if p99 days <8% or events <80).
- **15m kept p99** (35.9% of days, 5,051 bars). Hub
  `live/state/nq_15m_large_candle_p99/`. Follow-3R n=2290 WR **34.5%** /
  N/S **1.52** vs p90 WR 29.2% / N/S 2.96. **p95** 15m n=6738 WR 31.1% /
  N/S **4.46** is the better N/S sleeve. ATR-norm p99 WR 39.0% / N/S 3.61.
  217 charts. **Do not promote.**
- 15m HA mill hub `live/state/nq_15m_large_candle_ha_p99/`. Fade/1R still
  lose. During-PO fade-ST 3R n=71 WR **52.1%** / N/S 4.67 (p90 analogue
  n=574 WR 34.1% / N/S 7.41). **Do not promote.**
- First-hour: p99 **too rare** (5.9% of days, n=238, N/S 0.20) → **p95**
  sleeve. Hub `live/state/nq_1h_first_hour_ha_p99/`. Follow-3R p95 n=879
  WR **43.8%** / N/S **2.56** (p90 was WR 43.6% / N/S 6.64). Fade dies.
  154 charts. Diagnostic — **do not promote.** Emails sent.

## 2026-08-18 — NQ 15m large-candle + first-hour 1h follow/fade HA

- 15m analogue of the 5m p90 large-candle 3R study (resampled from
  `nq/nq_5min_rth.csv`). Hub: `live/state/nq_15m_large_candle/`. p90 follow-3R
  n=9853 WR **29.2%** / N/S **2.96** / PF 1.05 vs non-large control WR 22.7%
  N/S −0.76; ATR-norm p90 WR 32.7% / N/S 3.90. 214 charts. **Do not promote.**
- 15m HA mill (fade, 1R, futures HP + prior-opposed overlay). Hub:
  `live/state/nq_15m_large_candle_ha/`. Unconditional fade/1R still lose.
  During-PO fade-ST 3R n=574 WR 34.1% / N/S **7.41**. PO HP buckets do not
  transfer. **Do not promote.**
- First-hour only (09:30–10:30) follow vs fade, 1R/3R, p90 first-hour range,
  first-hour-native conditions, HP mill. Hub: `live/state/nq_1h_first_hour_ha/`.
  **Follow** 3R all first hours n=3968 WR **38.2%** / N/S **9.32**; fade 3R
  N/S −0.92. Strong-body first hour WR lift +14.4pp; p90 first-hour follow-3R
  WR 43.6% / N/S 6.64. PO overlay at 10:30 is thin (n≤26). 151 charts.
  Diagnostic — large stop (first-hour open); **do not promote.**
  Emails sent.

## 2026-08-18 — Prior-opposed Heikin Ashi overlay + NQ 5m large-candle 3R

- Diagnostic HA (Heikin Ashi) overlay on NQ/YM prior-opposed RL vs current HP
  buckets. Hub: `live/state/prior_opposed_ha/`. NQ: HA-with-prior-trend (n=105)
  WR 71.4% / avg $4.4k vs HA-with-fade n=327 WR 64.2% / avg $2.7k — not stronger
  than existing OR-norm HP. YM: HA-with-fade is the better bucket (tiny n on
  trend-HA). Post-exit 3R (candle-direction match): continuation and re-fade
  both WR ~18–22% (≤ fair 3R). **Do not promote.**
- NQ RTH 5m large-candle study (causal expanding p90 range, follow close / SL
  open / 3R). Hub: `live/state/nq_5m_large_candle/`. Raw p90 WR 25.6% (fair 3R
  ~25%); ATR-norm p90 WR 29.2% / N/S 2.75 / PF 1.07 vs all-candle baseline WR
  22.4% net-negative. Charts: 211-day stratified sample. **Do not promote.**
  Emails sent.

## 2026-08-18 — OANDA orphan LIMIT mass-cancel (logged)

- **Ops:** Practice account flat; cancelled **53** pending broker orders (US30/NAS100
  ST+PMC-style entry LIMITs + MonOR bare STOP/LIMIT 1610/1611). Pending left **0**.
- Local working rests cleared on US30/NAS100 ST+PMC runners + US30 MonOR CSVs.
- **Audit hub:** `live/demo/oanda_practice_snapshot/ORPHAN_LIMIT_CANCEL.md`
  (+ `.json` / `_META.json` / `_LOCAL.json`, `INCIDENT_LOG.md`, demo `PROGRESS.log` +
  `reconciliation_events.jsonl` markers). Email: `live/demo/EMAIL_ORPHAN_LIMIT_CANCEL_2026-08-18.txt`.
- Same-day related: remote-ack-before-local `cancel_order`; containment email → NY EOD digest.
  Containment still **shadow** (would-cancel only) — mass-cancel was manual ops.


## 2026-08-17 — Yearly ORB HP + bucket charts on causal broker-like fills

- Re-ran the NQ/ES/YM HP pipeline **throughout** on the next-open range-close
  tape (same L_4_1_1 / L_4_2_1 / L_4_1_1 cells). Drivers:
  `python -m live.yearly_orb_hp_sizeup --causal-close --email` and
  `python -m live.yearly_orb_bucket_charts --causal-close --email`.
- Hubs: `yearly_daily_condition_profile_futures_causal_close/`,
  `yearly_orb_hp_live_plan_causal_close/`, `yearly_orb_hp_charts_causal_close/`.
- Book WR: NQ **20/68 = 29.4%**, ES **15/73 = 20.5%**, YM **18/81 = 22.2%**.
  All six HP pairs **NOT VALIDATED** at 1.25× and 2× — stay 1.0×.
- NQ bucket charts (every campaign, PNG not zip): mixed MA 18 @ **33.3%**
  (6/12), wide OR 20 @ **40%** (8/12), ATR q4 24 @ **41.7%** (10/14).
  Union 41 campaigns / 26 losses. Pre-causal 86–100% WRs were scratches.

## 2026-08-17 — Futures yearly ORB causal close (same pass as FX/metals)

- Replayed NQ/ES/YM default 19-cell grid with next-open range-close
  (`live_after_ts=decision_bar.ts`). Hub
  `live/state/yearly_orb_sizing_sweep_futures_causal_close/` + `COMPARISON.md`.
- Pre-causal NQ `L_4_1_1` 86.8% WR / N/S 11.01 was same-bar-open scratches
  (28/68 campaigns). Causal: **29.4% WR**, net $765k, N/S **4.80**.
- Mixed MA 100%→33%; wide OR 95%→40%; ATR q4 96%→42%. Still lift vs 29%
  book WR; not 95–100% sleeves. ES `L_4_2_1` **9.90→0.40** (died). YM
  `L_4_1_1` 7.64→1.78. NQ OCO `4/2/1` rc20 held **6.74→5.82**.
- Stance: do not promote from pre-causal futures yearly-ORB N/S or WR.
  Analog to FX metals (AUDJPY died; XAU/XAG survived weak).

## 2026-08-17 — NQ yearly ORB bucket charts (mixed MA / wide OR / ATR q4)

- Emailed **every** NQ L_4_1_1 campaign in the three HP notables as PNG
  attachments (not zip): mixed MA stack n=18 100% WR; wide OR n=20 95%;
  ATR q4 n=24 95.8%. Driver `python -m live.yearly_orb_bucket_charts --email`.
- Hub `live/state/yearly_orb_hp_charts/nq_buckets/`. 5 chart emails
  (18+18+2+18+6). Overlaps repeated on purpose. Diagnostic only.

## 2026-08-17 — Yearly ORB HP size-up (NQ/ES/YM) — not validated

- Added **YM L_4_1_1** to `yearly_daily_condition_profile` (was NQ+ES only).
- Ran matched-added-exposure **1.25× and 2×** + LIVE_PLAN:
  `live/state/yearly_orb_hp_live_plan/` (nulls hubs `yearly_orb_hp_sizeup_nulls/` + `_2x/`).
- **NQ 86% WR recount HOLDS:** 59/68 = **86.8%** (Wilson 95% CI 76.7–92.9%).
  ES 56/73 = 76.7%; YM 73/81 = **90.1%**. Baseline tape, not a size-up claim.
- HP pairs (coverage <35%): NQ mixed-MA, ES ATR-q4 / shorts, YM shorts / ATR-q4.
  All **NOT VALIDATED** (selection-aware master fails; NQ mixed-MA placebo p_ΔNS=0.053).
- Stance: keep **1.0×** yearly ORB ladders; do not HP-size. Driver
  `python -m live.yearly_orb_hp_sizeup --email`. Best-outcome PNG charts emailed
  per instrument (not zipped) under `live/state/yearly_orb_hp_charts/`.

## 2026-08-17 — HP research capital LOCK v1 (EURUSD @40×)

- Locked research capital package: **NQ OR-norm @4×**, **ES ST-age @4×**,
  **EURUSD ST+PMC Thursday @40×**. Hub `live/state/hp_size_lock_v1/`
  (`LOCKED_PLAN.md`, `LOCKED_SLEEVES.csv`).
- EURUSD @40×: net **$1.43M** / stress **$168k** / N/S **8.50**; $250k→**$1.68M**;
  ≈IM ~$100k; tick participation negligible.
- US30 high-size **not** locked (YM-proxy liquidity binds by ~80×).
- Does **not** change deploy auth: NQ provisional ≤2×; FX VALIDATED @1.25× only.

## 2026-08-17 — NQ OR-norm 5×/10× size sensitivity + liquidity

- Best HP sleeve from `futures_intraday_hp_sizeup_v1`: **NQ prior-opposed OR-norm**
  (provisional @1.25× / @2×). Extreme linear scale hub
  `live/state/futures_intraday_hp_nq_or_norm_extreme_size/`.
- N/S: 1× 24.06 → **2× 36.26 (peak)** → 5× 33.45 → 10× 31.48 (entry_qty 5→25→50).
- Liquidity vs NQ 1m: med entry-bar share **0.9% / 1.8%** at 5×/10×; >25% bar days ≈0.
  Capital/IM (~$0.5M / $1M) grows; tape thinness is **not** the veto.
- Stance: **sit on 5×/10×**; keep controlled paper at ≤2× until dedicated nulls.

## 2026-08-17 — Yearly ORB FX/metals causal close + exit variants (research sit)

- **Causal close:** range-close / year-change market exits use
  `live_after_ts=decision_bar.ts` (next daily open). Hub
  `live/state/yearly_orb_sizing_sweep_fx_metals_causal_close/` — pre-causal
  FX metals top-4 N/S (tracker 24.87 / 15.32 / 8.58) **not promotion-safe**.
- **Exit variants** on `yearly_orb_scaleout3`: `exit_mode=mid_close` (YOR mid)
  and `inside_swing_take` (trail SL to latest inside-range swing). Pack hub
  `live/state/yearly_orb_exit_variants_fx_metals/` + `PNL_ATTRIBUTION.md`.
- **Attribution-shaped sizing:** XAU mid TP/runner
  `live/state/yearly_orb_xauusd_mid_tprunner/` best **`L_0_3_3_mid` N/S 4.75**
  (vs mid 1/1/1 4.31); XAG range front-load
  `live/state/yearly_orb_xagusd_range_frontload/` best **`L_6_2_1` N/S 1.37**
  (vs `L_4_2_1` 1.29). AUDJPY still stop-dominated — sit out.
- Stance: **mild / research**; do not promote causal metals ORB from these hubs.
  Plugin also allows explicit `tp25_qty=0`.

## 2026-08-16 — FX/metals yearly ORB sizing + deep-checks

- Extended `live/yearly_orb_sizing_sweep.py` to AUDJPY/XAUUSD/XAGUSD; hub
  `live/state/yearly_orb_sizing_sweep_fx_metals/` (19 cells × 3 markets).
- Best N/S: AUDJPY **`4/1/1` 24.87**, XAU **`4/2/1` 15.32**, XAG **`5/2/1` 8.58**
  (vs `1/1/1` baselines 15.26 / 11.30 / 6.21). Front-heavy again; RC20/OCO lose.
- Instrument deep-checks + win/loss charts emailed for those three books.
- Docs: STRATEGY_TRACKER metals top-4 + sizing section; TOP_STRATS FX note;
  `YEARLY_ORB_RESEARCH_NOTES.md` path; hub one-pagers; fx_metals_top4 SUMMARY.

## 2026-08-15 — OANDA daemon containment + curated fault fixtures

- **Containment:** `live/demo/oanda_daemon_reconcile.py` — bracket invariant watchdog
  (~2m), 15m hard reconcile, daemon state machine, `FLAT_FOR_DAY.json`. Default
  `POTIONS_OANDA_CONTAINMENT=shadow` (would-actions only); `live` freezes / flattens.
  Foreign-bleed check reads the **unscoped** store (scope-filtered broker mirrors
  were hiding sibling-instrument rows).
- **Stream staleness:** ≥180s without tick/heartbeat → `stream_stale` DISARM + entry
  freeze; reconnect path REST-reconciles then rearms. Covers Aug 14 hung-stream
  missed-entry class. Wired on v2b / Monday OR / ST+PMC / asia-range / London
  prior-opposed OANDA stream loops.
- **Wire:** v2b OANDA common + Monday OR OANDA + hourly ST+PMC OANDA + asia-range
  London + US30 London prior-opposed (`install_containment` /
  `oanda_broker_with_supervisor`).
- **Broker:** `sweep_orphan_protectives_when_flat` cancels lingering SL/TP when flat
  (Aug 14 orphan class). Supervisor sticky modes survive `mark_reconciled`.
- **Backoff:** `next_stream_backoff` adds ±20% jitter (429 floor unchanged).
- **Curated fault env:** `live/tests/fixtures/oanda_faults/` with Aug 13–14 **real
  OANDA demo 1m bar slices** + frozen books (incl. `2026-08-14_stream_hung_missed_entry`);
  harness `python -m potions.live.demo.oanda_fault_replay`
  (`--also-plugin-replay --hub live/state/oanda_fault_replay_curated --email`).
  Tests: `test_oanda_daemon_containment.py`, `test_oanda_fault_day_replay.py`.
- Spec: `live/specs/OANDA_DAEMON_RECONCILE_FLAT_FOR_DAY_TODO.md`.

## 2026-08-15 — MAE percentile sweep (p80/85/90/95) + OANDA reconcile TODO

- **MAE study:** `live/oanda_winner_mae_carry.py` now sweeps winner-MAE carry at
  **p80 / p85 / p90 / p95**; hub `live/state/oanda_winner_mae_carry/`. Favorable
  **2/15**: EURUSD ST+PMC 3R → `p80_winner_mae` (Δ+$16k); NAS100 ST+PMC runners
  → `p95_winner_mae` (Δ+$3.2k). Risk-guard overlay accepts any `pXX_winner_mae`.
- **TODO:** was plan-only; superseded by containment implementation above.


## 2026-08-15 — Risk-guard shadow + winner MAE / p80 carry

- **Daemon:** `live/risk_guard_shadow.py` + `scripts/risk_guard_shadow.sh` —
  shadow (log-only) through **2026-08-28**, avg-loss pts threshold; would-actions
  to `live/state/risk_guard_shadow/actions.csv`. No freeze/close/stop.
- **MAE study:** `live/oanda_winner_mae_carry.py` →
  `live/state/oanda_winner_mae_carry/` — winner path MAE + p80-carry vs hard stops
  on 15 OANDA practice books. **1/15 favorable** (`eurusd_hourly_st_pmc_sl50_tp150_3r`);
  daemon overlays p80 MAE thr for that book only.
- HTML multipart emails sent (armed / MAE complete / overnight digest).

## 2026-08-14 — OANDA stream hung-fix + 429 backoff

- **Ops:** Cleared orphan NAS100/SPX500 v2b protective STOPs (broker STOP=0).
  Cooldown + stagger-restart recovered USDJPY/US30 Monday OR OANDA after
  post-429 zombies. NAS100/SPX500 v2b OANDA left stopped overnight (cash
  closed) to protect rate limit — restart before Mon RTH.
- **Code:** `live/demo.next_stream_backoff` — 429 reconnects use ≥120s / ≤300s
  ceiling (Monday OR OANDA + `oanda_v2b_ungated_common`). Ledger:
  `live/demo/ADHERENCE_ISSUES.md` remediation section.

## 2026-08-13 — Futures HP ΔN/S Phase-3 repair + portfolio N/S

- **Phase-3 @1.25× rerun** (`--phase3`): ES ST-age + YM overnight-middle →
  **NOT VALIDATED** under ΔN/S (`p_master_ΔNS`≈0.77 / 0.99). Sole survivor:
  NQ OR-norm **PROVISIONAL PAPER** (`p_master_ΔNS`≈0.074, ΔN/S +4.70).
  Tier A empty. Hardened `_progress` against `BrokenPipeError`.
- **Deployment:** `DEPLOYMENT_PLAN.md` / `LIVE_PLAN.md` / skill /
  STRATEGY_TRACKER aligned to ΔN/S labels (Aug-12 “two validated 1.25×”
  superseded). NQ OR-norm @2× remains highest-conviction controlled paper.
- **Boards:** `canonical_ns_research` finite core excludes prior-opposed 10R
  addon + indefinite; US30 market harvest fixed (`market=?` → US30);
  overlay board dedupes null hubs over sensitivity ladder.
- **Phase 4:** `python -m live.canonical_ns_portfolio --email` →
  `live/state/canonical_ns_research/portfolio/` (HOLD_ONE + ≤1 prior-opposed
  HP; additive joint-stress upper bound). Best legal Portfolio N/S ≈ **11.55**
  with NQ OR-norm @2× + EURUSD Thu @1.50× provisional.

## 2026-08-13 — Canonical N/S selection + NQ OR-norm @2× high-priority paper

- **Policy:** whole-book **N/S** is the canonical higher-is-better score for
  finite comparable strategies; overlays/size-ups rank by **ΔN/S**. Raw Δnet
  remains viability/reporting only. Master/placebo/shift nulls select and
  decide on ΔN/S (`p_master_delta_NS`). Labels: SIZE-UP VALIDATED /
  PROVISIONAL PAPER / RISK THROTTLE / SENSITIVITY ONLY / NOT VALIDATED.
- **Code:** `live/intraday_hp_sizeup_nulls.py` `_select_score` + classify;
  futures driver aliases RISK THROTTLE; sleeve pick uses ΔN/S.
- **Phase 1 hub:** `live/state/canonical_ns_research/`
  (`POLICY.md`, `CANDIDATE_LEDGER.csv`, `ELIGIBILITY_AUDIT.csv`,
  `BASELINE_REGISTRY.csv`, `ECONOMIC_SLEEVE_MAP.csv`, `BOARDS.md`,
  `ALL_RESULTS.md` / `ALL_RESULTS_WITH_COUPONS.csv` — ledger-order table with
  net/stress/N/S coupons vs baseline, no sorting) via
  `python -m live.canonical_ns_research --email`.
- **NQ prior-opposed RL · OR-normal @2×:** economic conviction **HIGHEST** in
  current HP sizing research. Δnet ≈ +$582k; N/S 24.06→36.26 (Δ+12.20);
  MTM DD −$55.3k→−$52.8k; matched + shift pass; master p≈0.064
  (**SELECTION-AWARE BORDERLINE**). Ops: **HIGH-PRIORITY CONTROLLED PAPER**
  (not funded-production). Hub `futures_intraday_hp_sizeup_nulls_2x/`.

## 2026-08-12 — Futures HP size-up v1: Tier A/B/C deployment plan

- Study `futures_intraday_hp_sizeup_v1`: two **SIZE-UP VALIDATED** @1.25×
  (ES prior-opposed ST-age>180m; YM prior-opposed overnight middle) + NQ
  prior-opposed OR-norm **PROVISIONAL PAPER**; Tier C shadow-only risk-budget
  rows. NOT VALIDATED = no action.
- Compare driver `live/futures_intraday_hp_sizeup_compare.py`: baseline vs
  1.25/2/3/4× (net, MTM DD, N/S, yearly best/worst/bad) + prior-opposed
  incremental-sleeve overlap (hold ≤1 HP/session until joint gate clears).
- Hubs: `live/state/futures_intraday_hp_live_plan/{DEPLOYMENT_PLAN,LIVE_PLAN,COMPARISON}.md`
  · skill `potions-futures-intraday-hp-sizeup`.
- Tier A/B bookkeeping: retain 1.0× baseline + book incremental 0.25× separately;
  do not stack yet. 2–4× = sensitivity only (not validation).

## 2026-08-12 — HP size-up classifier tightened + 1.25× shadow rollout

- Immutable decision tiers in `live/intraday_hp_sizeup_nulls.py`:
  **SIZE-UP VALIDATED** (`p_placebo/p_shift/p_master ≤ 0.05` + WF + stress),
  **BORDERLINE PAPER** (`0.05 < p_master ≤ 0.10`),
  **RISK-BUDGET PROFILE** (`p_master > 0.10` or WF fail / broad coverage).
- Reclassified banked pairs (`--reclassify-existing`): EURUSD Thu + US30 h11
  stay validated **only at 1.25×**; 1.5× → borderline; 2× US30 h11 demoted from
  false VALIDATED → risk-budget (`p_master=0.106`).
- Expected book N/S lift @1.25×: EURUSD Thu **3.18→3.52 (Δ+0.34)**; US30 h11
  **1.96→2.16 (Δ+0.20)**; incremental sleeve N/S stays 8.39 / 6.69 across mults.
- Rollout started in **shadow** on paper demos (no size change; qty=1):
  `python -m live.hp_size_shadow --once` → `state/hp_shadow.csv`.
- Docs: hub `ROLLOUT.md` / `SUMMARY.md`, overlay `LIVE_PLAN.md`, tracker callout.

## 2026-08-12 — OANDA fill matching: no instrument fallback

- Root cause of orphan US30 +2 @ 54071.5: `on_fill` attached untagged shared-account
  fills to the active v2b `runner_stop` (false local fill @ 53783.8 on Aug 11) while
  the real OANDA buy-stop stayed pending and filled next day unprotected.
- `on_fill` now requires `clientExtensions.id` / `clientOrderID` / mapped remote
  `orderID`; rejects instrument-level guessing; ignores fills on terminal local orders.
- Ops: closed unprotected trades 1256 (US30) + 1280 (NAS100); left ST+PMC US30 ±1
  lots with SL/TP; practice-sync repaired demo position CSVs.
- Tests: `test_oanda_on_fill_rejects_untagged_instrument_fallback` (+ resolve / terminal).

## 2026-08-12 — OANDA remote order authority + cancel/resubmit refresh (A+B)

- Root cause: plugin `regime_off` / `_cancel_entry_limits` only cancelled what
  local `reconcile_orders()` knew; `modify_order` → `replace_order` left ghost
  OANDA rests (0 cancel events) that kept filling after the gate flipped.
- **A:** `OandaBroker.sweep_remote_order_authority` on startup reconcile + timer
  (`poll_account_changes`): cancel tagged entry orphans not in
  `_active_order_ids`; never touch trade-linked SL/TP; alert when
  `pending_remote > local_open`.
- **B:** `modify_order(refresh_entry)` prefers cancel + resubmit with audited
  cancel events and remapped `_oanda_order_ids` (Paper unchanged).
- Tests: `live/tests/test_oanda_adapter.py` orphan sweep + cancel/resubmit.
- Docs: Platform §6 + known concerns. Restart OANDA demos to pick up patch;
  practice sync repairs local positions.

## 2026-08-11 — US30 London prior-opposed ¼-size demos (live ST gate)

- Wired `demo-us30-london-prior-opposed-{paper,oanda}` — London OR 03:00–03:15 →
  flatten 11:59, `prior_opposite_only`, **`size_mult=0.25`** (book `S_1_0_0`).
- Live ST+PMC events from sibling `us30_hourly_st_pmc_sl50_tp150_3r_{paper,oanda}`
  fills merged into `dynamic_sizing_events` (+ research resting-limit seed).
- Price source default `st_feed_bars` (sibling 1m tape) to avoid US30 stream caps.
- Gate audit CSV: session / prior ST ts+side / arm decision / OCO / fill / skip.
- Plugin: empty `dynamic_sizing_events` now blocks when `prior_opposite_only`.
- Hub: `live/state/fx_v2b_london_prior_opposed`. Half/full size still gated on live
  ST parity + concentration clarity (not yet promoted).

## 2026-08-11 — EURUSD/US30 ungated dropped + missed promote demos

- Stopped live **EURUSD/US30 v2b ungated** paper+OANDA (sleeve review losers; broker ungated reject).
- Offline screen `live/eurusd_us30_missed_promote_screen.py` → hub
  `live/state/eurusd_us30_missed_promote_screen/` (month blackout + roll WR/PF;
  ST+PMC WR floor 22%; deep-checks emailed HTML multipart).
- **Promoted demos (UP):**
  - EURUSD ST+PMC 50/150 fair 3R full — `demo-eurusd-hourly-st-pmc-{paper,oanda}`
  - EURUSD ST+PMC 2R→10R **½** — `demo-eurusd-hourly-st-pmc-2r10r-{paper,oanda}`
  - US30 Monday OR `M3_S3_R2` **½** + Sep skip — `demo-us30-monday-or-{paper,oanda}`
  - EURUSD Monday OR `M1_S2_R2` **½ paper-only** + Aug skip — `demo-eurusd-monday-or-paper`
- **Later same day:** US30 London prior-opposed wired at ¼ size (see entry above).
  London 4h + Monday `M3_S3_R3` remain reject.
- NAS100/SPX500 ungated v2b left running.

## 2026-08-11 — USDJPY Asia-range three-book hierarchy LOCKED (C capital-efficient)

- Locked deployability hierarchy in `THREE_BOOK_FORWARD.md` + tracker:
  **C** primary capital-efficient demo · **B** alpha/return control · **A** unfiltered shadow.
- Verdict code **`C_PRIMARY_CAPITAL_EFFICIENT_B_ALPHA_CONTROL`** (supersedes
  `B_WINS_FORWARD_C_RISK_THROTTLE` for portfolio implementation ranking; OOS facts unchanged —
  B still wins frozen shadow OOS N/S 6.56).
- Broker matched-net note: C ≈ **1.025×** base capital matches B’s $182.6k net at ~−$25.2k
  stress (~54% below B); 1.3× C linear projection ~$231.6k / −$32.0k. Validate lot/margin/OCO.
- Driver stance string updated so regenerations keep the lock.
- Practice demos stay on **C**; funded sleeve still **NO**.

## 2026-08-11 — USDJPY Asia-range funded-sleeve gates confirmation check-in

- Re-confirmed frozen-rule checklist before any funded-sleeve claim:
  OOS / walk-forward / attribution / path-aware offline **PASS**; filter nulls =
  risk throttle; three-book = `B_WINS_FORWARD_C_RISK_THROTTLE`.
- **50-campaign warmup** called out again: cold research replays pass through
  first 50 on roll gate; live demos keep last-50 seed (`shadow_campaigns.json`
  nets=50) so paper/OANDA are warm from day one. Proof windows may shrink only
  when history/shadow seed already covers the window.
- Path-aware fills/OCO/slippage/exposure stay in promoted hub logs +
  `validation_path_aware.json` for daily/weekly post-process (not retune).
- Live-parity still **pending_first_campaigns** (Asia OR collect → London inject;
  `campaign_parity.csv` not written yet). Paper+OANDA demos UP on book C.
- Stance unchanged: research/practice **PROMOTE**; **funded sleeve NO**.

## 2026-08-11 — USDJPY Asia-range sit-out candle-sim + three-book check-in

- Sit-out candle-sim wired on Asia-range demos (`candle_sim_unfiltered_campaign_net`):
  skip days advance shadow via unfiltered PaperBroker replay on stored 1m bars.
- Three-book forward driver + hub (`THREE_BOOK_FORWARD.md`) checked in:
  verdict `B_WINS_FORWARD_C_RISK_THROTTLE` (Jan-only wins frozen OOS).
- Funded-sleeve open item reduced to **live parity row-compare** after first London campaigns.
- Stance unchanged: research/practice **PROMOTE** on C; **funded sleeve NO**.

## 2026-08-11 — USDJPY Asia-range frozen three-book forward

- Driver: `live/fx_v2b_asia_range_london_usdjpy_three_book_forward.py` → `THREE_BOOK_FORWARD.md`.
- Locked books: **A** unfiltered `S_3_1_3` · **B** January-only · **C** Jan + roll50 WR40/PF1.
- Shadow OOS (years > 2021): **B wins** N/S 6.56 / net≈+$169k vs C 4.23 / +$102k vs A 5.35 / +$150k.
- Full-sample shadow N/S still **C** 6.07 (stress −$24k vs B −$54k); broker N/S C 7.23 / B 3.35 / A 2.14.
- Jan-only PaperBroker state: `…/states/usdjpy_v2b_asia_range_london_S_3_1_3_jan/` (N/S 3.35, +$183k).
- Verdict **`B_WINS_FORWARD_C_RISK_THROTTLE`**: aligns with FILTER_NULLS; practice demos stay on C; funded sleeve still **NO**.

## 2026-08-11 — USDJPY Asia-range validation gates + filter nulls check-in

- Offline funded-sleeve gates already green (OOS / walk-forward / attribution / path-aware); **funded sleeve still NO**.
- Filter nulls driver `live/fx_v2b_asia_range_london_usdjpy_filter_nulls.py` → `FILTER_NULLS.md`: **RETAIN AS RISK THROTTLE** (matched-exposure + selection-aware fail; circular-shift timing pass; Jan #1/12).
- Validation driver now scrapes live-parity status + OANDA margin ops snapshot into `VALIDATION_GATES.md`.
- `oanda-practice-sync` records `marginUsed` / `marginAvailable` / closeout %; DEMO_FOCUS includes `usdjpy_asia_range_london_oanda`.
- Practice account (shared): NAV≈$102k, marginUsed≈$16.5k, marginAvail≈$85.5k; USDJPY flat until London inject. Demos UP with **50-campaign** shadow seed.
- Open: live `campaign_parity.csv` row-compare after first London campaigns (sit-out candle-sim now wired).

## 2026-08-11 — USDJPY Asia-range funded-sleeve validation gates

- Driver: `live/fx_v2b_asia_range_london_usdjpy_validation.py` → hub `VALIDATION_GATES.md` + attribution/OOS/yearly/decision-tape CSVs.
- Frozen rules locked: `S_3_1_3` + Jan + roll50 WR40/PF1 (no retune).
- Attribution (shadow tape): Jan Δ≈+$29k; PF dominant sit-outs (681); combined not Jan-only (629 extra roll skips).
- Frozen OOS after 2021: taken net≈+$102k **PASS**; yearly stability **PASS** (2022 31% abs share, 7 green years).
- Live-parity: paper/OANDA demos append `campaign_parity.csv`; plugin `session_gate_decision`; research tape `validation_decision_tape.csv`.
- **50-campaign warmup** documented; demos seed last-50 so live is not cold-start.
- Path-aware scrape (promoted hub fills/orders): OCO cancelled/filled counts, fill reasons, adverse-vs-mid, max exposure — weekly post-process source, not retune.
- Stance unchanged: research/practice **PROMOTE**; **funded sleeve NOT YET**.

## 2026-08-11 — USDJPY Asia-range London filtered promote

- **Family:** Asia OR **19:00–03:00** NY → arm v2b OCO at London **03:00** → flatten **11:59** (`session_or_ranges` on `v2b_scaleout`).
- Multi-pair majors hub: only USDJPY green (`live/state/fx_v2b_asia_range_london/`).
- USDJPY sizing sweep (`…/fx_v2b_asia_range_london_usdjpy_sizing/`): unfiltered leaders `S_0_5_0` N/S 2.18, `S_3_1_3` 2.14.
- **Filters** (`…/fx_v2b_asia_range_london_usdjpy_filters/`): January blackout + shadow roll50 WR≥40%/PF≥1 on **unfiltered** campaign book → filtered `S_3_1_3` N/S **7.23** (+$178k / −$25k). See `FILTERS.md`.
- Plugin: `skip_entry_months` + `shadow_roll_*` / `shadow_campaigns_path` on `v2b_scaleout`; helper `live/asia_range_shadow.py`.
- **Live demos:** `demo-usdjpy-asia-range-{paper,oanda}` → `live/demo/usdjpy_asia_range_london_{paper,oanda}/` (running).
- Tracker + skills: month + shadow WR/PF filters are default decision tools for similar sleeves.
- Ranking note: daily London Asia-OR sleeve (USDJPY); not interchangeable with Monday OR weekly `M2_S3_R1` (N/S 8.20) — both promoted, different clocks.

## 2026-08-10/11 — London FX exploration (mostly REJECT)

Broker-like majors/CFD/metals screens under `live/state/`. **Promote path emerged only from Asia-range USDJPY + filters.**

| Hub | Stance | Top line |
|-----|--------|----------|
| `fx_v2b_london_ungated` | REJECT | FX red; indices soft-negative |
| `fx_v2b_london_prior_opposed` | RESEARCH / not promote | NAS100 N/S **8.38**, US30 **6.23** (thin sample); FX red |
| `fx_v2b_london_prior_aligned` | REJECT | All red |
| `fx_v2b_london_2h_or` (03–05) | REJECT FX; CFD soft | NAS100 1.38 / US30 1.19; majors ≤−0.9 |
| `fx_v2b_london_4h_or` (03–07) | REJECT FX; US30 soft | US30 1.57 / 1.34; majors red |
| `fx_v2d_london` | REJECT | All red |
| `fx_v2b_london_fbo` | REJECT | All red |
| `fx_ny_liquidity_grab_london` | REJECT | All red |
| `fx_london_sweep_reversal` | REJECT | USDJPY N/S 0.05; EUR/GBP red |
| `fx_v2b_asia_range_london` | → sizing → filters | USDJPY only green (S_1_1_3 N/S 2.03) → **promote filtered S_3_1_3** |

Deep-check / win-loss charts on asia `S_1_1_3` and sweep USDJPY under those hubs’ `deep_check/` / `winloss_charts/`.

## 2026-08-08 — ST+PMC live demos: promote 3R + 2R→10R

- Updated fair-control tracker notes (US30 N/S 29.4, NAS100 N/S 19.6 lot-correct).
- New demos for **2R→10R runners** (max 3; TP1 + runner@2R + runner@10R; BE after TP1):
  `demo-us30-hourly-st-pmc-2r10r-{paper,oanda}`,
  `demo-nas100-hourly-st-pmc-2r10r-{paper,oanda}`.
- Commons: `us30_hourly_st_pmc_common.py` / `nas100_hourly_st_pmc_common.py` book registry.
- Indefinite not demoed (inventory sleeve). Sync map + demo README updated.
- US30 indef portfolio risk profile: `live/state/us30_st_pmc_runner_variants/INDEF_PORTFOLIO_PROFILE/`
  (stress DD −$31.2k as sleeve risk unit; scale = budget / |stress|).
- FX/index/metals runner hub in flight: `live/state/fx_index_metals_st_pmc_runner_variants/`
  (NAS100 done; EUR/GBP/USDJPY mid-run; metals queued; SPX500 skipped).

## 2026-08-08 — Lot-correct multi-campaign accounting (BUGFIX)

Indefinite ST+PMC runner books (45–137 concurrent same-direction units) had **contaminated** FIFO nets/stress: `units_from_live_fills` paired exits across `trade_id`s, inventing multi-thousand-point “losses” on BE runners and a false NQ indef +$4.57M / N/S 2.35.

- `units_from_live_fills`: match **within `trade_id`**; optional hard-stop / BE-after-TP1 metadata.
- `audit_units`: **reachable** intrabar stress (clip to live stop; gap-open fill).
- StrategyPlugin ST+PMC audit path: force-mark leftover open lots at final sample close.
- Post-process: `live/indefinite_lot_accounting.py` → continuous + forced-flat + reachable vs raw stress (`LOT_CORRECT_ACCOUNTING.md`).
- **Rankable:** fair 3R and 2R→10R. **Not rankable yet:** indefinite (separate inventory sleeve until forced-flat figures reviewed).

## 2026-08-07 — HTF lookahead fill on 1m-tape replays (BUGFIX)

- Bug: `_replay_hourly_with_1m` (and EURUSD day-bias DCA broker) called
  `Engine.process_bar` on **1h** bars before the 1m tape, so PaperBroker matched
  resting limits against the **full hour OHLC at the hour timestamp** — fills
  appeared before price touched on 1m (same-bar entry+target common).
- Fix: `Engine.process_bar(..., broker_fills=False)` for HTF signal bars; 1m tape
  owns fills. Paper ST+PMC demos use the same rule on completed 1h bars.
- Platform §6 note + `test_htf_signal_bar_does_not_lookahead_fill_when_broker_fills_disabled`.
- Re-run required for US30/NAS100 `*_1mfill*` hubs and runner variants.

## 2026-08-04 — structure VWAP scale-in (FAIL)

- Plan `vwap_scalein`: spaced session-VWAP slices inside structure (5×3ct,
  ≤1/15m); SL at structure extreme; 15m reclaim re-arm after stop-out; ladder
  +25→±12 / +50 / +200; fav_be; RTH EOD flatten.
- Analytic NQ 2020+: **−$6.44M PF 0.171** (13898; avg 1.14 slices).
- PaperBroker: **−$1.11M PF 0.044** (267 camps / 909 units). DSR **TRL-2026-00086**.
- Hubs: `structure_program_st/vwap_scalein/`, `structure_program_st_broker_vwap_scalein/`.
  Family still PARKED.

## 2026-08-04 — touch_st_align invalidity + fade20 (FAIL)

- Invalidity audit: ~37% of touch_align broker fills still/deep through structure
  at entry (through −$651k). Hub: `…/invalid_audit/`.
- fade20 (through≥20m → fade limit @ key ±25): analytic +$670k PF1.34 → broker
  **−$871k PF0.75** (fade legs −$593k WR10%). DSR TRL-2026-00085. Still PARKED.

## 2026-08-03 — touch_st_align (analytic promise → broker FAIL)

- New plan: structure touch+through → ST flip aligned → market; SL=ST trail;
  +25 scale→±12 SL; then +50/+200; fav_be. Analytic NQ +$1.37M PF 1.30 WR 58%.
- PaperBroker: **−$1.25M PF 0.84** (1391 camps). Hold≤1 ~1% (entry timing fixed)
  but managed path still loses. DSR TRL-2026-00084. Charts 100W/100L under
  `live/state/structure_program_st_broker_touch_align/trade_charts/`.

## 2026-08-03 — Structure-only resting + v2b level align (FAIL)

- Plugin: `signal_source=structure_only` resting limit @ structure (no ST arm);
  guards one-shot submit / non-marketable / consume-key after fill|blow.
- PaperBroker NQ scale_run r8 fav_be: **−$2.13M PF 0.185** (493 camps) —
  worse than ST-gated −$103k. DSR TRL-2026-00083 (00082 invalid churn).
- v2b align: keys **against** first break 77.6%; ~7% in 0–2R when aligned.
  Hubs: `structure_program_st_broker_struct_v2/`, `structure_program_st/v2b_align/`.

## 2026-08-03 — Structure-program ST `scale_run` broker gate (FAIL)

- **Analytic** `structure_sl_scale_run` (NQ): 15ct ladder 5@+22/+50/+200, fav ST→BE;
  +$2.03M PF 9.6; winners hit 25/100/200 at 96%/61%/40%. Gate evidence that fav
  ST-flips truncate runners: `live/state/structure_program_st/structure_sl_scale_run/GATE.md`.
  Path writeup: `live/state/structure_program_st/RESEARCH_PATH.md`.
- **Plugin** `structure_program_st` plan `scale_run` + `st_flip_mode=fav_be`
  (no EOD flatten). Replay: `live/structure_program_st_replay.py --plan scale_run --risk-pts 8`.
- **PaperBroker NQ** (`live/state/structure_program_st_broker_scale_run/`):
  **−$102.6k PF 0.70** (228 trades) — fails promotion. Adverse `st_flip` + risk
  stops dominate; only 20 runner units. Split15 broker variants also failed earlier
  (always −$130k / adverse −$204k / after_n10 −$232k / off −$247k).
- DSR **TRL-2026-00079** pre-registered then COMPLETE. Family parked / research-only.

## 2026-08-02 — FX turtle soup + Plan C OR profiles (2026H2fx)

- **FX turtle soup** (`live/fx_turtle_soup_study.py`, clocks in `live/fx_or_markets.py`):
  same R/5 soup geometry on US30/NAS100 RTH, EURUSD London+NY OR, USDJPY NY,
  XAU NY. Index CFD OR books dead; EURUSD London OR+wick25 +$20.3k / PF 1.25
  (9/24 neg years) kept as research lead only — not promote. Hub:
  `live/state/fx_turtle_soup/`.
- **Plan C OR profile tables** (`--asof 2026H2fx`): US30/NAS100 match NQ
  headline chains within ~2–4 pts; EURUSD/USDJPY/XAU show much higher
  P(1R|break) / P(2R|1R). Join to ST+PMC 1mfill (`live/fx_or_profile_join.py`):
  US30/NAS100 flat-gap and q4 edges are *positive* vs all — **do not import**
  NQ P1/P3 overlays onto those CFD books. Hub:
  `live/state/or_profile_engine/2026H2fx_PLAN_C.md`.

## 2026-08-02 — HTF turtle soup parked; P8 runner ladder rejected; P9 reverse≤12:00 promoted

- **HTF turtle soup** (`live/htf_turtle_soup_study.py`): same close5 OUT→IN →
  soup-the-swing geometry, but level = prior 3d / 4w / 2m high-low; risk from
  that day's OR. Daily & monthly books negative; weekly_4 + wick≥0.25R nets
  +$31.5k / PF 2.24 but 10/17 neg years (2026-dominated) — parked.
- **Plugin knobs:** `runner_target_r_mult` (runner TP at NR) and
  `reverse_only_when` + `session_or_width_q` on `v2b_scaleout`.
- **P8 runner ladder** (chain≥0.30 → 3R runner; chain<0.18 → no runner):
  REJECTED on NQ validation ($316k vs $389k baseline). DSR TRL-2026-00066/70.
- **P9 reverse_only_when time≤12:00:** PROMOTED overlay — NQ +$29.6k net vs
  baseline, MNQ +$3.2k; both improve N/S slightly. q1-only rejected.
  Next natural stack: P5 (flat-gap skip + q4 no-runner) + P9_time_1200.
  Validation hub: `live/state/or_profile_engine/v2b_join/2026H2/validation/`.

## 2026-08-02 — Q1 fakeout satellite + v2b time gate: both causally REJECTED; plans queued

- **New StrategyPlugin** `q1_fakeout_reversal` (`live/strategies/q1_fakeout_reversal.py`,
  registered in `live/registry.py`): on q1-OR-width days (trailing-250 causal
  in-plugin history), a morning touch break failing on a 5m close inside
  within 2 candles is reversed at market; stop at the failed extreme, TPs at
  opposite boundary / opposite 1R. All thresholds a priori from the stable
  cells; DSR TRL-2026-00062..65 registered pre-review.
- **Verdict** (driver `live/q1_fakeout_satellite_replay.py`, NQ 2010–2026 +
  MNQ, hardened realism): NOT promotable — NQ split $9.9k/447 trades
  (PF 1.089, N/S 0.59, 8 negative years), MNQ flat/negative. The 0.92 flip
  cell is real but stop-clipped (32–41% win) and already harvested by v2b's
  reverse leg. Hub: `live/state/q1_fakeout_satellite/`.
- **New v2b config flag** `entry_cutoff_time` (`v2b_scaleout`): entry stops
  expire at the cutoff (NY) and arming stops after it; exits unchanged;
  default unset = legacy. Causal validation as P6 (alone) and P7 (stacked on
  P5) in `or_profile_v2b_join validate`: **REJECTED** on both markets
  (NQ $359.6k vs $389.4k baseline; P7 $252.3k vs P5 $366.8k) — the reverse
  leg monetises late weak breaks. P5 stays the promoted overlay.
- **Loss autopsy** (`live/q1_fakeout_loss_autopsy.py`, 447 NQ trades,
  1m-tape what-ifs + 100/100 loser/winner charts): 57.7% of stops are
  directional invalidation (orig break resumes to its own 1R), 35.7%
  shakeouts, median 6 min to stop. Deep invalidation stops raise TP rate to
  62.6% but 2.6× risk halves net (PF 1.04); retest entries PF 1.02–1.17
  (pennies); limit-at-failed-extreme and London/5m-swing entries negative
  (adverse selection). **Satellite binned per protocol** — majority of
  stops are true invalidation. `live/state/q1_fakeout_satellite/autopsy/`.
- **Structure follow-up** (`live/q1_fakeout_structure_followup.py`): the
  close5-confirmed boundary fade (touch break → 5m close outside → 5m close
  back inside → limit at the boundary) lifts PF to 1.74 (187 fills) but is
  regime-concentrated — >100% of 16-yr net from 2021/23/24, 6/16 negative
  years, 2010–2020 flat — fails the stability bar. The invalidation add-on
  at OR mid is REJECTED with a conditioning correction: unconditional
  first-touch after failure is 62.9% opposite boundary vs 34.0% orig 1R
  (the 57.7% figure was losers-only), so adding with the break fights the
  majority path (PF 0.95). Satellite stays binned.
- **Queued frozen plans** (`live/specs/OR_PROFILE_NEXT_PLANS.md`): runner
  ladder from the extension chain, asymmetric reverse leg
  (`reverse_only_when`), FX/CFD rollout of the OR-profile stats.
- Combined book + these verdicts promoted in `STRATEGY_TRACKER.md`
  ("Combined book + OR-profile follow-ups").

## 2026-08-02 — Combined book: prior-opposed RL core + non-gate v2b satellite (causal)

- **Driver** (`live/v2b_combined_book_replay.py`): core = promoted
  prior-opposed resting-limit S_1_1_3 book (own Engine+PaperBroker fills);
  satellite = all-days v2b S_1_1_3 **re-replayed** via Engine+PaperBroker,
  `regime_dates` restricted to days with **no gate limit resting at 09:45**
  (`available_at_ts` from the core's `dynamic_sizing_events`) plus the
  OR-profile flat-gap skip. Merged units audited on one union 1m bar tape.
- **NQ** (2021-03→2026-03): core $1.331M / −$68.6k stress / **N/S 19.4**;
  naive stack N/S 13.1; **core + complement satellite + flat-gap skip
  $1.921M / −$85.3k / N/S 22.5** — +44% net AND better ratio than the core.
- **MNQ**: identical ordering — core 18.4 → combo+skipflat **21.3**
  ($183.0k / −$8.6k). Hubs: `live/state/{nq,mnq}_v2b_combined_book_causal/`.

## 2026-08-02 — OR Profile Probability Engine → v2b policies (NQ/MNQ/YM/MYM)

- **Engine** (`live/or_profile_engine.py`): batch replay of 1m RTH tapes;
  per session builds the 09:30–09:45 OR (same defs as `v2b_scaleout`: R = OR
  width, targets = boundary ±1R/2R/3R), walks a causal event state machine
  under dual break triggers (`touch` = 1m pierce matching v2b stop fills,
  `close5` = 5m close outside), labels terminal day profiles and emits
  conditional probability tables (Wilson 95% CI, yearly stability slices).
  Sessions walked: NQ 3,987 (2010–2026), YM 3,963, MYM 1,698, MNQ 1,245.
  Refresh is one command: `python -m live.or_profile_engine --markets nq mnq
  ym mym --asof <tag>`. Hub: `live/state/or_profile_engine/<mkt>/2026H2/`.
- **Cross-market invariants:** P(1R|touch break) 0.54–0.56, P(2R|1R) ≈0.49,
  P(re-enter OR|break) 0.88–0.91 on all four markets. Stable NQ edges (sign
  holds ≥70% of years): late breaks 10:30–12:00 hit 1R only **0.29** vs 0.54
  pooled (16 yrs); wide-OR q4 P(2R|1R) **0.37** vs 0.50 (16 yrs); narrow-OR
  q1 failed breaks flip to opposite break **0.92**.
- **v2b join + policies** (`live/or_profile_v2b_join.py join`): joined touch
  sessions to `S_1_1_3` tapes. Fit ≤2024-12-31: flat-gap sessions (|gap| <
  0.1× prior range, knowable 09:45) −$211/session NQ, negative every year;
  MNQ agrees. Frozen policies: **P1** skip flat-gap, **P3** no-runner (1/1/0)
  on q4 OR-width, **P4** early-cut analytic (failed breaks re-enter ≤2×5m,
  −$4.8k/session NQ), **P5** = P1+P3. Size-up (P2) found no stable cell.
- **Causal validation** (`validate`, Engine+PaperBroker, hardened realism,
  2025-01→2026-06): NQ P1 **$414.0k** vs baseline $389.4k on 38 fewer
  sessions (net/session +27%); P3 net flat with stress DD −24%; P5 best PF
  1.446 / net-stress 5.3 vs 3.6. MNQ same ordering. Rolling refit
  (≤2025-06-30 → validate 2025-07+): NQ P1 again beats baseline (+$19.5k);
  policies structurally stable ⇒ semi-annual refresh cadence confirmed.
  Hub: `live/state/or_profile_engine/v2b_join{,_refit}/2026H2/validation/`.

## 2026-07-30 — ST+PMC 1mfill causality + live demos (US30 + NAS100)

- **Causality:** Hourly OHLC fill resolution overstates ST+PMC 50/150 on US30
  (same-bar entry+target when H/L both touch). Fair control with StrategyPlugin
  + 1m fill tape: N/S **10.34** (+$20.4k / −$2.0k) vs hourly **3.91**. Retest
  adds modest; BB-add ×3 (N/S 6.18) **worse than 1mfill**. Artifacts:
  `live/state/us30_st_pmc_retest_add_experiment/`.
- **Cross-market 1mfill** (`live/st_pmc_1mfill_cross_market.py`): YM/MYM/NQ/MNQ
  strong; **NAS100 +$9.5k N/S 4.59** (only profitable FX/index CFD); EURUSD /
  USDJPY negative on 50/150 pips. Metals on same 50/150 pts: XAU N/S **0.16**
  (not live); XAG 0 closed units (stop scale unusable) — keep metals on yearly
  ORB / ST+PMC MA-bull.
- **Live demos:** US30 paper+OANDA restarted on fair-control config
  (`fill_tape=1m`, no BB/retest). NAS100 paper+OANDA added — seed 1h from
  `fx/nas100_1h.csv`, inherit 1m bars from running `nas100_v2b_*` demos.
  CLI: `demo-nas100-hourly-st-pmc-{paper,oanda}`.

## 2026-07-21 — Monday OR Phase 2 extended (GBP/AUD/XAU; ex-silver)

- Ran Phase 2 robustness on **GBPUSD `M1_S1_R2`**, **AUDJPY `M1_S2_R2`**,
  **XAUUSD `M2_S2_R3`**. Silver excluded.
- Sub-periods: AUDJPY **PASS** 3/3; XAU **PASS** 2/3; GBPUSD **FAIL** 1/3
  (same post-2019 softness as EURUSD).
- DD sensitivity: all three tags **PASS** (±30% N/S band).
- Specs + deployment rules updated; AUDJPY optional satellite; XAU heat caution;
  GBP paper-only. Hub: `live/state/monday_or_phase2/`.

## 2026-07-21 — Monday OR Phase 2 hardening complete

- Locked pair tags (`live/monday_or_phase2_tags.py`): EURUSD `M1_S2_R2`,
  USDJPY `M2_S3_R1` / alt `M2_S3_R2`. Wired into `fx_monday_or_breakout_broker`.
- Robustness (`live/monday_or_phase2_robustness.py`): sub-periods, clustering,
  DD sensitivity (25/45, 35/55). Hub: `live/state/monday_or_phase2/`.
- **USDJPY PASS** (3/3 slices, sensitivity OK) → live/paper eligible under 3–5M.
- **EURUSD paper-only** (2020–22 / 2023+ slices negative) despite full-sample N/S 1.74.
- Specs + deployment rules + STRATEGY_TRACKER report checklist closed.
  Phase 3 = USDJPY-first track-record.

## 2026-07-21 — Monday OR sizing sweep all FX + metals

- Extended broker Phase 1 to **GBPUSD, AUDJPY, XAUUSD, XAGUSD** (27 cells each).
  Hub: `live/state/monday_or_sizing_sweep_broker/SUMMARY_ALL.md`.
- Cross-pair #1 by N/S: USDJPY `M2_S3_R1` **8.20** · GBPUSD `M1_S1_R2` **2.67** ·
  XAUUSD `M2_S2_R3` **1.90** (high heat) · AUDJPY `M1_S2_R2` **1.83** ·
  EURUSD `M1_S2_R2` **1.74** · XAGUSD fail (−0.97).

## 2026-07-21 — Monday OR sizing sweep through broker

- Ran all 27 Phase 1 cells × EURUSD + USDJPY via Engine + PaperBroker
  (`live/monday_or_sizing_sweep_broker.py`). Ranked by ≈USD Net/Stress.
- **EURUSD #1 `M1_S2_R2`**: N/S **1.74** (+$123k / −$71k) — confirms pandas winner;
  **beats ST+PMC 1.49**. Baseline `M1_S1_R1` was 0.83.
- **USDJPY #1 `M2_S3_R1`**: N/S **8.20** (+$219k / −$27k); near-tie `M2_S3_R2` at 8.19.
  Pandas pick `M3_S3_R2` is broker #3 (7.54). EURUSD light-sidecar is weak on USDJPY.
- Hub: `live/state/monday_or_sizing_sweep_broker/INDEX.md`. Docs: MONDAY_ORB_FAMILY,
  RESEARCH, STRATEGY_TRACKER Forex leaderboard.

## 2026-07-20 — Monday OR sizing sweep Phase 1

- Adapted generic sizing plan to **shifted-primary** sidecar (not same-direction
  SL re-entry). Dimensions: main DD-split (M*), shifted size (S*), max primary
  trades/week (R*). Driver: `live/monday_or_sizing_sweep.py`.
- Phase 1 (27 cells): EURUSD winner **`M1_S2_R2`** CE **3.28** (vs 2.21 baseline);
  USDJPY winner **`M3_S3_R2`** CE **13.37** (vs 8.90). Theme: max primary/week
  2→3 helps; EURUSD prefers lighter shifted, USDJPY smaller main + heavier shifted.
- Artifacts: `live/state/monday_or_sizing_sweep/`, `…_usdjpy/`, `PHASE1_RESULTS.md`.

## 2026-07-20 — FX Monday OR breakout (research → StrategyPlugin → cross-pair)

- Built **Monday opening-range breakout** family on EURUSD 15m: Mon H/L → Tue–Fri
  close breakout → **3** lots, drop **2**@30% DD, cut **1**@50% (no runner), SL=1R
  TP=2R, max 2 primary/week. HTF skip when 1h MA50/150 **and** OBV×SMA20 both opposed.
- Sidecar path: reverse fades tested; **parallel shifted primary** (failed MonH →
  same structure at MonL, and mirror) is research CE leader at **2.21** Net/|DD|
  (+$124.6k / −$56.4k closed). Exclusive-wait shifted rejected (1.89).
- New plugin `monday_or_breakout` + driver `live/fx_monday_or_breakout_broker.py`.
  Broker-like (1-tick slip, $1.50/unit) across `fx/raw`: **USDJPY 4.27**, **GBPUSD 1.87**,
  AUDJPY 1.07, XAU 1.04, **EURUSD 0.83**, XAG −1.00 (≈USD N/S). EURUSD does **not**
  beat promoted ST+PMC intraday (1.49); USDJPY/GBPUSD are the viability story.
- Docs: `live/state/eurusd_monday_or_breakout_15m/{MONDAY_ORB_FAMILY,RESEARCH}.md`,
  `live/state/fx_monday_or_breakout_broker/{SUMMARY,PROGRESS}.md`, STRATEGY_TRACKER
  Forex section. USDJPY W/L charts: `…/charts_usdjpy/{winners,losers}/`.

## 2026-07-16 — Cross-market resting-limit hour-complete + lookahead re-review

- NQ hour-complete baseline re-reviewed: **SOLID** for minute-by-minute execution
  (`LOOKAHEAD_REVIEW.md`). No remaining gate lookahead; residual risks are OHLC
  path ambiguity and cancelled-ST gate semantics.
- Re-ran MNQ / YM / MYM with the same gate. ES blocked (missing 1m DBN).
  Cross-market: `live/state/v2b_prior_opposed_resting_limit_cross_market/`.
  | Market | Trades | Net | Stress | Net/Stress |
  |---|---:|---:|---:|---:|
  | NQ | 432 | $1,330,920 | -$68,610 | 19.40 |
  | MNQ | 428 | $128,360 | -$6,960 | 18.44 |
  | YM | 436 | $289,225 | -$33,894 | 8.53 |
  | MYM | 423 | $22,101 | -$3,417 | 6.47 |

## 2026-07-16 — Resting-limit hour-complete baseline (remove left-label lookahead)

- Gate availability for `resting_limit` is now `live_after_ts + 1h` (ST hour
  complete), matching when ST+PMC would actually post. Left-label mode kept as
  `resting_limit_left_label` diagnostic.
- NQ causal baseline: **432** / **$1,330,920** / **-$68,610** stress / **19.40**
  Net/Stress — slightly beats left-label **$1,321,745 / 19.26**.
- Early-sleeve recovery: **103/104** former early sessions kept via delayed arm
  (median arm +60m, median entry +0). Post-hoc “drop early → $753k” was the wrong
  counterfactual. Provisional confirm-60m does not beat the gated baseline.
- Artifacts: `live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/`,
  `.../early_pnl_recovery/`, `.../resting_limit_left_label_diagnostic/`.

## 2026-07-15 — NQ prior-opposed gate-timestamp correction

- Timing autopsy showed ~76–78% of the banked NQ prior-opposed net came from
  v2b entries before the true 1m ST fill was knowable (hourly left-label fill
  stamps). Artifacts under `live/state/nq_v2b_prior_opposed_timing_study/` and
  `live/state/nq_v2b_prior_opposed_causal_proxies/`.
- **NQ promotion candidate:** `gate_mode=resting_limit` — arm after opposite ST
  entry limit is posted (`live_after_ts`). **434** campaigns / **$1,321,745** /
  **-$68,610** MTM stress / **19.26** Net/Stress. Still filters causally
  (**434 / 1164** regime days).
- Strict 1m-touch fill gate: **$225,825** / **-$153,087** MTM / **1.48** Net/Stress.
- Provisional + invalidate 60m: **$467,748** / **-$131,315** MTM / **3.56** Net/Stress.
- Legacy hourly fill-stamp banked folder demoted to diagnostic. Docs updated in
  `STRATEGY_TRACKER.md`, `README.md`, and related INDEX/pitch artifacts.

## 2026-05-20 — Broker realism + risk projection fixes (run #1)

Scope: paper broker fill realism, risk OCO collapse, audit fee support, and
plumbing through the existing replay drivers. The Tradovate live adapter is
still inert (no live routing). All edits keep test parity (`pytest -q
potions/live/tests` → `6 passed`).

### Broker (`potions/live/broker.py`)

- Added `slippage_ticks`, `tick_size`, and `strict_moc` parameters to
  `PaperBroker.__init__`. Default `slippage_ticks=0` preserves legacy tests; the
  replay drivers (`broker_like_replays.py`, `monthly_orb_overlap_st_retest_replay.py`,
  `v2b_strategy_replay.py`, `v2b_strategy_cross_market_replay.py`,
  `v2b_clean_break_replays.py`) now default to **1 tick** of adverse slippage
  on market and stop fills.
- Per-instrument tick sizes live in `DEFAULT_TICK_SIZE` (NQ/MNQ/ES/MES = 0.25,
  YM/MYM = 1.0); per-call overrides are merged on top.
- **Stop gap-through fix.** `_base_fill_price` now returns
  `max(stop_price, bar.open)` for buy-stops and `min(stop_price, bar.open)` for
  sell-stops, so a stop that gaps through fills at the open instead of the
  trigger price. This was the largest single source of optimism in the prior
  implementation. Slippage is layered on top of the gap-adjusted price.
- **Stop-first same-bar ordering.** `_priority_sorted_active_ids()` enforces
  deterministic intra-bar order: `market` → `stop` → `limit` → `market_close`.
  This makes same-bar stop+target races pessimistic for protective exits, and
  replaces the previous implicit dict-insertion order.
- **Tighter `market_close` semantics.** When `strict_moc=True`, `market_close`
  orders only fill on a bar whose timestamp exactly matches
  `order.live_after_ts`, preventing accidental lookahead from intraday
  strategies that misuse MOC. Daily strategies (where bar.ts is the date)
  behave identically because they set `live_after_ts=bar.ts`.

### Risk manager (`potions/live/risk.py`)

- Replaced the signed-quantity projection with `_projected_exposure_with_intent`,
  which groups submitted entry orders by `oco_group` (or per-order id when
  there is no OCO) and counts only the **largest** leg per group. This fixes
  two real bugs:
  1. Same-side OCO peers (e.g., two `buy stop` legs sharing an OCO group) used
     to be double-counted and could falsely trip `max_contracts_exceeded`.
  2. Opposite-side OCO peers (long + short on the same range) only passed
     before because their signed quantities happened to cancel — a fragile
     coincidence that broke as soon as both legs had the same side or
     different sizes.
- The new projection is conservative: `open_position_abs + sum(max-per-group)`.

### Replay audit (`potions/live/replay_audit.py`)

- `audit_units(..., fee_per_unit: float = 0.0)` now subtracts a per-unit
  round-trip fee from realized P/L every time a unit closes. Drawdowns and
  Net/Stress-DD ratios reflect fee drag, not just the headline net. Default
  remains `0.0` so other callers keep their existing semantics until they
  opt in.

### Engine (`potions/live/engine.py`)

- `Engine(..., slippage_ticks, tick_size, strict_moc)` threads the broker
  realism knobs through default `PaperBroker` construction. Callers that pass
  an explicit `broker=` keep full control.

### Drivers

- `broker_like_replays.py`
  - New module constants `DEFAULT_SLIPPAGE_TICKS=1.0` and
    `DEFAULT_FEE_PER_UNIT=1.50`.
  - `run_broker_like_replays` and `_write_summary` thread both knobs through
    to the engine and the audit, and record them in `SUMMARY.md`.
- `monthly_orb_overlap_st_retest_replay.py`
  - Same realism defaults; engine constructed with `slippage_ticks=1.0`; audit
    now passes `fee_per_unit=1.50`.
- `v2b_strategy_replay.py`, `v2b_strategy_cross_market_replay.py`,
  `v2b_clean_break_replays.py`
  - `Engine(..., slippage_ticks=1.0)`. Their bespoke
    `fast_intraday_audit` already deducts `FEE_PER_UNIT`, so no audit change
    needed.

### Strategy hardening

- `strategies/monthly_orb_overlap_st_retest.py` raises an `Alert` of level
  `warning` at construction if `daily_close_4h_ts` is empty. This is a no-op
  when the replay driver populates the list, but surfaces the missing
  scheduler input the moment the strategy is enabled live without it.

### Not yet addressed (documented, deferred)

- Tradovate live adapter is still inert.
- Bar-timestamp comparisons in `_ts_after` / `_ts_before` still use string
  ordering; safe within a single timeframe, fragile across mixed daily +
  intraday + timezone formats. Acceptable for the current configurations and
  flagged for a future datetime-based rewrite.
- Partial fills for parent entry orders are not modeled; first touch fills
  100% of size. Material for large-size ES/YM only.
- No bid/ask spread, no exchange halt or LULD handling.
- Margin / day-trade-buying-power / daily loss cap not in the risk manager.

## Re-runs after the realism fixes (run #1)

### `broker_like_replays` (daily ORB / yearly ORB / ATR Supertrend)

Re-ran the full daily cross-market matrix end-to-end with `slippage_ticks=1`
and `fee_per_unit=1.50`. Top of post-fix ranking
(`potions/live/state/broker_like_replays/SUMMARY.md`):

| Rank | Candidate | Instrument | Units | Net | Stress DD | Net/Stress |
|---:|---|---|---:|---:|---:|---:|
| 1 | Yearly ORB scaleout3 | ES | 219 | $328,727.75 | $-40,403.00 | 8.14 |
| 2 | Yearly ORB scaleout3 | NQ | 204 | $850,314.00 | $-106,720.00 | 7.97 |
| 3 | Yearly ORB scaleout3 | YM | 243 | $288,756.75 | $-39,810.00 | 7.25 |
| 4 | Yearly ORB scaleout3 | MNQ | 72 | $67,942.12 | $-10,669.00 | 6.37 |
| 5 | ATR daily ladder 1/1/2/2/2 10-max | NQ | 402 | $1,572,142.00 | $-255,950.00 | 6.14 |
| 6 | ATR daily ladder 1/1/2/2/2 10-max | MNQ | 162 | $146,875.00 | $-25,610.00 | 5.74 |
| 7 | ATR daily 3-initial 10-max | NQ | 623 | $1,717,280.50 | $-309,068.50 | 5.56 |
| 8 | ATR daily 3-initial 10-max | MNQ | 233 | $159,819.00 | $-29,350.50 | 5.45 |
| 9 | Yearly ORB 20% range-close | NQ | 138 | $741,289.25 | $-141,210.00 | 5.25 |
| 10 | Yearly ORB 20% range-close | MNQ | 30 | $66,845.25 | $-14,141.00 | 4.73 |

Snapshots of the pre-fix table are preserved alongside as
`summary_before_realism_fixes.csv` and `SUMMARY_before_realism_fixes.md` for
audit. Note: the snapshot pre-dates *this* commit's realism fixes but
post-dates the earlier OCO/range-close strategy edits from this session, so
slug-level deltas mix the strategy hardening with the realism effects.

### `monthly_orb_overlap_st_retest_broker_like` (4h, all six markets)

Re-ran with `slippage_ticks=1`, `fee_per_unit=1.50`. The MNQ+NQ pass was
re-run alongside the daily replays; ES/MES/YM/MYM were re-run next; finally
all six audits were combined into a single `SUMMARY.md`.

| Market | Net (before) | Net (after) | Δ Net | Stress DD (before) | Stress DD (after) |
|---|---:|---:|---:|---:|---:|
| MNQ | $73,523 | **$60,325** | -$13,198 (-18.0%) | -$18,348 | -$20,428 |
| NQ  | $787,811 | **$549,976** | -$237,835 (-30.2%) | -$108,655 | -$127,455 |
| ES  | $322,847 | **$135,734** | -$187,113 (-57.9%) | -$76,882 | -$101,515 |
| YM  | $247,382 | **$15,090** | **-$232,292 (-93.9%)** | -$54,030 | -$46,115 |
| MYM | $14,043 | **$9,813** | -$4,231 (-30.1%) | -$5,053 | -$5,325 |
| MES | $8,744 | **$2,613** | -$6,131 (-70.1%) | -$7,828 | -$10,344 |

That ~94% YM and ~58% ES erosion is dominated by stop gap-through; both
markets see frequent 4h-bar gaps that the old broker masked. NQ/MNQ stay
materially positive but lose ~18-30% of net.

### `v2b_clean_break_broker_like` (5m, MNQ + NQ, four variants each)

| Market | Variant | Net (before) | Net (after) | Δ Net |
|---|---|---:|---:|---:|
| MNQ | Bullish 2R/RL | $9,498 | **$8,878** | -$621 |
| MNQ | 09:45 fourth RL | $5,110 | **$4,712** | -$399 |
| MNQ | 09:45 fourth boundary | $1,554 | **$1,128** | -$425 |
| MNQ | 09:45 fourth ladder3 | $2,363 | **$1,086** | -$1,276 |
| NQ  | Bullish 2R/RL | $112,026 | **$93,097** | -$18,930 (-17%) |
| NQ  | 09:45 fourth RL | $85,804 | **$75,125** | -$10,680 |
| NQ  | 09:45 fourth boundary | $31,334 | **$20,054** | -$11,280 |
| NQ  | 09:45 fourth ladder3 | $62,206 | **$28,406** | -$33,800 (-54%) |

Net read: the 09:45 ladder-3 runner gets the worst realism cost because it
holds the most contracts through stop gap-through events. Broad bullish
2R/RL still survives with attractive Net/Stress (MNQ 4.40, NQ 3.79).

### `v2b_strategy_plugin_replay` (1m MNQ, two modes)

| Mode | Net (before) | Net (after) | Δ Net | Net/Stress before → after |
|---|---:|---:|---:|---|
| oco_then_reverse | $34,444 | **$24,770** | -$9,675 (-28%) | 5.87 → 3.92 |
| strict_long_then_short | $18,927 | **$12,688** | -$6,239 (-33%) | 3.07 → 1.73 |

### `v2b_strategy_plugin_cross_market_requested` (1m all six markets, start 2021-03-04)

| Market | Net (before) | Net (after) | Δ Net | Net/Stress before → after |
|---|---:|---:|---:|---|
| NQ  | $389,026 | **$299,477** | -$89,549 (-23%) | 6.61 → 4.69 |
| MNQ | $34,444 | **$25,053** | -$9,392 (-27%) | 5.87 → 3.97 |
| YM  | $76,271 | **$26,930** | -$49,341 (-65%) | 1.47 → 0.38 |
| ES  | $63,239 | **-$27,929** | -$91,169 (flips losing) | 0.87 → -0.24 |
| MYM | $4,092 | **-$198** | -$4,290 (flips losing) | 0.60 → -0.02 |
| MES | $1,466 | **-$2,797** | -$4,263 (flips losing) | 0.27 → -0.38 |

Net read: under realism, only **NQ and MNQ** keep meaningful V2B edge. ES,
MYM, and MES flip to net-negative; YM goes from "weak positive" to
"essentially flat with 35% more stress DD".

### Strategy tracker

`potions/mnq/case_studies/STRATEGY_TRACKER.md` has been updated end-to-end
with the new numbers and a banner pointing to this changelog. Pre-fix copy
preserved at
`potions/mnq/case_studies/STRATEGY_TRACKER_before_realism_fixes.md`.

### Pre-fix artifacts preserved

Every replay state directory now has `*_before_realism_fixes.csv` and
`*_before_realism_fixes.md` alongside the new `summary.csv` /
`SUMMARY.md` so the impact is auditable per row.

### Chart regeneration (2026-05-21)

All chart builders gained a `REALISM_CAPTION` footnote that is rendered on
every PNG and prepended to every INDEX.md, so the realism baseline is
visually obvious. Regenerated packs:

- `live/state/broker_like_replays/charts/detail/` — 1,940 charts across all
  42 candidate slugs (yearly ORB, monthly ORB, ATR variants × 6 markets);
  plus the two SUMMARY ATR comparison PNGs (theoretical vs broker-like and
  weekly 2/3/6 broker-like).
- `live/state/monthly_overlap_st_retest_broker_like/charts/detail/` — 229
  charts across MNQ/NQ/ES/MES/YM/MYM (all six markets).
- `live/state/v2b_strategy_plugin_replay/charts/oco_then_reverse/` and
  `.../strict_long_then_short/` — 101 charts each, including the
  equity-overview PNG.
- `live/state/v2b_strategy_plugin_cross_market_requested/charts/<market>_v2b_scaleout_oco_then_reverse/`
  for NQ/ES/YM/MYM/MES — 101 charts each.

Legacy targeted dirs preserved but tagged:

- `live/state/broker_like_replays_monthly_boundary_stop_test/charts/INDEX.md`
  and `live/state/yearly_orb_range_close_20pct_test/charts/detail/INDEX.md`
  now carry a `> PRE-REALISM-FIX SNAPSHOT (2026-05-19 or earlier)` banner at
  the top with a pointer to the equivalent broker_like_replays detail packs.
  The PNGs themselves are left in place for diff/audit.

Not regenerated:

- `v2b_clean_break_broker_like` has no chart pack of its own
  (`build_v2b_strategy_charts.py` is OCO-specific). The replay state now
  has post-fix fills + audits with realism deltas in `CHANGE_LOG.md`.
