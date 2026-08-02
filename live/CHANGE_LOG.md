# Live Runtime CHANGE_LOG

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
