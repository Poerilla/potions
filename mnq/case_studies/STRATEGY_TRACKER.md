# MNQ ORB — Strategy tracker (research notes)

Central index of execution variants explored in this workspace / chat threads.
**Canonical live model** for Production remains **`scripts/step2_preplaced_stops.py`** (OCO stops, bracket-then-reverse) — see `scripts/validation.md` and `potions/README.md`.

> **2026-05-20 broker realism re-baseline.** The `PaperBroker` now applies
> 1-tick adverse slippage on market and stop fills, fills gapped-through stops
> at `max/min(stop, bar.open)`, evaluates stops before limits in same-bar
> ambiguity, charges `$1.50` per closed unit in `audit_units`, and collapses
> OCO peers in the risk projection. All broker-like and StrategyPlugin replays
> in the tables below have been re-run under these defaults unless noted.
> Pre-fix snapshots are preserved next to each summary as
> `*_before_realism_fixes.*`. See [`../../live/CHANGE_LOG.md`](../../live/CHANGE_LOG.md).

## Forex Strategy Leaderboard

> **2026-07-30 — ST+PMC 1m fill-tape (index CFDs).** Hourly OHLC can fill
> entry+target on the same bar when H/L both touch even if the high came
> *before* a causal limit fill. Fair control = StrategyPlugin + **1m fill tape**
> (`sl50_tp150_3r_1mfill`). US30: N/S **10.34** (vs hourly 3.91). Cross-market:
> NAS100 **4.59** (only profitable FX/index CFD on this exact variant);
> EURUSD/USDJPY **fail** at 50/150 pips. BB-add / retest pyramids do **not**
> beat the 1mfill control. Live: US30 + NAS100 paper/OANDA demos on fair control.
> Hub: [`../../live/state/st_pmc_1mfill_cross_market/SUMMARY.md`](../../live/state/st_pmc_1mfill_cross_market/SUMMARY.md) ·
> causality: [`../../live/state/us30_st_pmc_retest_add_experiment/SUMMARY.md`](../../live/state/us30_st_pmc_retest_add_experiment/SUMMARY.md).

### Index CFD ST+PMC 50/150 — 1mfill ranks (2026-07-30)

| Rank | Market | Net | Stress | **N/S** | WR% | Live demo |
|---:|---|---:|---:|---:|---:|---|
| 1 | **US30** | +$20.4k | −$2.0k | **10.34** | 34.6% | `demo-us30-hourly-st-pmc-{paper,oanda}` |
| 2 | **NAS100** | +$9.5k | −$2.1k | **4.59** | 31.6% | `demo-nas100-hourly-st-pmc-{paper,oanda}` |
| — | XAUUSD 50/150 pts | +$27.2k | −$169k | **0.16** | 26.8% | not promoted (keep MA-bull / yearly ORB) |
| — | XAGUSD 50/150 pts | 0 units | — | 0.00 | — | stop scale unusable vs silver price |
| — | EURUSD (50/150 pips) | −$5.1k | −$36k | −0.14 | 25.0% | not promoted |
| — | USDJPY (50/150 pips) | (JPY PV) | — | −0.88 | 23.5% | not promoted |

EURUSD sleeves ranked by broker-like **Net/Stress** (Engine + `PaperBroker`, Histdata daily/hourly as noted). Fee conventions differ by family ($1.50 intraday ST+PMC / Monday OR pack vs $7/unit monthly ORB pack) — compare within sleeve, then across with that caveat.

| Rank | Sleeve | Plugin / ID | Net | Stress DD | Net/Stress | WR | Role |
|---|---|---|---:|---:|---:|---:|---|
| 1 | **Monday OR `M1_S2_R2`** (15m, light shifted, max 3/wk) | `monday_or_breakout` · Phase 2 | **+$123.3k** | −$70.9k | **1.74** | — | **Phase 2 hardened · paper-only** (sub-period fail 2020+); full-sample beats ST+PMC · [report](#monday-or-fx-strategy-tracker-report) |
| — | Monthly ORB FBO 1/1/3 + ema100(1h)+atr80 | same + filter csv | +$69.0k | −$40.4k | 1.71 | 50.7% | Lowest-stress FBO variant; EMA leg costs net vs atr80-only |
| 2 | **Monthly ORB FBO 1/1/3 + atr80 filter** | `monthly_orb_v2b_oco` + `entry_filter_csv` · `eurusd_monthly_orb_fbo_filt_atr80only_1_1_3` | **+$91.9k** | −$56.8k | **1.62** | 52.1% | **Promoted FX monthly sleeve (filtered)** |
| 3 | **Hourly ST+PMC 25/75 + MA bull prior** | `hourly_st_pmc_retest` · `eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior` | **+$23.5k** | −$15.7k | **1.49** | 27.4% | Prior promoted FX intraday baseline |
| 4 | **Monthly ORB FBO 1/1/3** (0.25R/1R/2R, BE@TP25, close-SL) | `monthly_orb_v2b_oco` · `eurusd_monthly_orb_fbo_r2r_be1_1_1_3` | **+$77.3k** | −$74.0k | **1.04** | 50.3% | **Promoted FX monthly sleeve (unfiltered)** |
| 5 | **Monthly ORB FBO 1/2/3** (same rules) | `monthly_orb_v2b_oco` · `eurusd_monthly_orb_fbo_r2r_be1_1_2_3` | **+$90.6k** | −$88.8k | **1.02** | 50.3% | **Promoted FX monthly sleeve (absolute net)** |
| — | Monday OR pre-sweep `M1_S1_R1` | same plugin | +$76.0k | −$91.7k | **0.83** | — | Superseded by `M1_S2_R2` on broker |
| — | Monthly ORB FBO 1/1/1 runner@2R | same plugin | +$38.2k | −$46.4k | 0.82 | 57.2% | Research / smaller size |
| — | Monthly ORB limit-retest scaleout3 | `monthly_orb_restricted_scaleout3` | +$21.8k | −$48.3k | 0.45 | — | Prior monthly candidate; superseded for FBO |
| — | Hourly ST day-bias DCA (f30 week) | `hourly_st_daybias_dca` | ~−$0.6k | — | −0.06 | — | Failed promote gate |

**Promoted packs**

- Intraday: [`../../live/state/eurusd_forex_intraday_baseline/`](../../live/state/eurusd_forex_intraday_baseline/)
- Monthly FBO: [`../../live/state/eurusd_forex_monthly_orb_fbo_baseline/`](../../live/state/eurusd_forex_monthly_orb_fbo_baseline/) · stress source [`../../live/state/eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/`](../../live/state/eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/)
- Filtered FBO A/B (atr80, ema100+atr80): [`../../live/state/eurusd_monthly_orb_fbo_filtered_broker/`](../../live/state/eurusd_monthly_orb_fbo_filtered_broker/) — filter mechanism `entry_filter_csv` in `live/strategies/monthly_orb_v2b_oco.py`; EMA100(1h) counterfactual did **not** survive in-engine rerun, atr80 did.
- Monday OR broker cross-pair: [`../../live/state/fx_monday_or_breakout_broker/`](../../live/state/fx_monday_or_breakout_broker/) · sizing sweep hub [`../../live/state/monday_or_sizing_sweep_broker/INDEX.md`](../../live/state/monday_or_sizing_sweep_broker/INDEX.md) · plugin `live/strategies/monday_or_breakout.py`

**Monday OR — broker sizing sweep all pairs (2026-07-21):** 27 Phase 1 cells × EURUSD / GBPUSD / USDJPY / AUDJPY / XAUUSD / XAGUSD. Full report: [Monday OR FX Strategy Tracker Report](#monday-or-fx-strategy-tracker-report).

| Pair | Broker #1 | N/S | ≈USD net | vs baseline | Status |
|---|---|---:|---:|---|---|
| **USDJPY** | **`M2_S3_R1`** | **8.20** | +$219k | 4.27 → 8.20 | **Phase 2 hardened** (live/paper eligible) |
| **GBPUSD** | **`M1_S1_R2`** | **2.67** | +$231k | 1.87 → 2.67 | Phase 2 extended · **paper-only** (sub-period FAIL) |
| **XAUUSD** | **`M2_S2_R3`** | **1.90** | +$438k | 1.04 → 1.90 (stress −$230k) | Phase 2 extended · heat / default do-not-fund |
| **AUDJPY** | **`M1_S2_R2`** | **1.83** | +$96k | 1.07 → 1.83 | Phase 2 extended · satellite (sub-period PASS) |
| **EURUSD** | **`M1_S2_R2`** | **1.74** | +$123k | 0.83 → 1.74; beats ST+PMC 1.49 | **Phase 2 hardened · paper-only** |
| **XAGUSD** | `M2_S2_R3` | **−0.97** | −$224k | Still fail | **Excluded** from Phase 2 |

Hub: [`…/monday_or_sizing_sweep_broker/INDEX.md`](../../live/state/monday_or_sizing_sweep_broker/INDEX.md) · Phase 2: [`…/monday_or_phase2/`](../../live/state/monday_or_phase2/). **Stance:** USDJPY-first Phase 2, EURUSD Phase 2; GBPUSD Phase 1 footnote; metals — gold dollars-with-heat only, silver reject.

## Monday OR FX Strategy Tracker Report

**Status:** Phase 1 complete · **Phase 2 hardening complete** (2026-07-21). Hub: [`monday_or_phase2/SUMMARY.md`](../../live/state/monday_or_phase2/SUMMARY.md).

**Phase 2 outcome:** USDJPY `M2_S3_R1` **hardened** (sub-periods 3/3, sensitivity pass) → default live/paper candidate under caps. EURUSD `M1_S2_R2` **hardened but paper-only** — full-sample N/S 1.74 still leads ST+PMC, but 2020–2022 and 2023+ unit slices are negative.

This report consolidates the Monday OR intraday FX strategy family into a single tracker entry, combining the original backtest rationale, the broker-like Phase 1 sizing sweep results, and the Phase 2 hardening plan. The goal is to maintain a current, allocator-ready reference for research status, promotion status, candidate configurations, and next validation steps.

Hubs: [`monday_or_sizing_sweep_broker/INDEX.md`](../../live/state/monday_or_sizing_sweep_broker/INDEX.md) · [`RESEARCH.md`](../../live/state/eurusd_monday_or_breakout_15m/RESEARCH.md) · [`MONDAY_ORB_FAMILY.md`](../../live/state/eurusd_monday_or_breakout_15m/MONDAY_ORB_FAMILY.md) · Phase 2 [`monday_or_phase2/`](../../live/state/monday_or_phase2/).

The current Phase 1 broker-like sweep established two pair-specific Phase 2 leaders: **EURUSD `M1_S2_R2`** and **USDJPY `M2_S3_R1`**, with `M2_S3_R2` retained as a close alternate for USDJPY. These findings materially improve on baseline Monday OR configurations and, in EURUSD, exceed the currently promoted FX intraday ST+PMC baseline on Net/Stress (1.74 vs 1.49).

### Strategy family definition

The Monday OR model is an intraday FX breakout framework with two linked components:

- A **main leg** that enters on the Monday opening-range breakout and scales out based on drawdown buckets before the full symbolic stop.
- A **shifted primary sidecar** that, after the main leg flats at the 50% drawdown bucket, waits for a breakout of the **opposite** Monday extreme (failed Mon high → short Mon low; mirror for failed Mon low) and runs the same DD-ladder structure.
- A **re-entry limiter** that caps how many fresh primary attempts may occur within the week (`R1`=2, `R2`=3, `R3`=unlimited).

The structural premise is that intraday FX breakouts frequently experience partial failure and stop-run behavior before a cleaner continuation emerges. The model monetizes the initial breakout and a shifted second chance at the opposite OR boundary, while truncating adverse excursions early rather than waiting for full-stop outcomes.

### Backtest rationale

#### Core behavioral hypothesis

1. Initial breakouts often move in the expected direction but suffer meaningful early adverse excursion.
2. Trades that extend to deeper drawdown are less likely to recover cleanly, making early scale-outs more capital-efficient.
3. After a failed primary flats at 50% DD, the **opposite** Monday extreme is a secondary opportunity area (shifted primary), not a same-direction stop re-entry.

#### Baseline implementation

- **Main leg:** `M1` = 3 units total, 2 @ 30% DD, 1 @ 50% DD.
- **Shifted sidecar:** `S1` = same structure as the main leg.
- **Re-entry cap:** `R1` = max **2** primary trades/week.

### Sizing tag reference

#### Main-leg tags

| Tag | Definition |
|---|---|
| `M1` | 3 units = 2 at 30% DD, 1 at 50% DD |
| `M2` | 3 units = 1 at 30% DD, 2 at 50% DD |
| `M3` | 2 units = 1 at 30% DD, 1 at 50% DD |

#### Shifted-sidecar tags

| Tag | Definition |
|---|---|
| `S1` | 3 units = 2 at 30% DD, 1 at 50% DD |
| `S2` | 2 units = 1 at 30% DD, 1 at 50% DD |
| `S3` | 4 units = 2 at 30% DD, 2 at 50% DD |

#### Re-entry tags

| Tag | Definition |
|---|---|
| `R1` | Max **2** primary entries/week (tighter) |
| `R2` | Max **3** primary entries/week (more permissive) |
| `R3` | Unlimited primary entries/week (research reserve) |

### Phase 1 broker-like sweep

#### Scope

Phase 1 completed a 27-cell broker-like sweep through Engine + PaperBroker across **all six** instruments (EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD), ranked by ≈USD Net/Stress. Driver: `live/monday_or_sizing_sweep_broker.py`. **Phase 2 promotion anchors remain EURUSD and USDJPY only**; other pairs are footnotes.

#### Phase 2 anchors (EURUSD / USDJPY)

| Pair | Baseline `M1_S1_R1` | Broker #1 | Net/Stress | Approx. USD Net | Stress |
|---|---|---|---:|---:|---:|
| EURUSD | 0.83, +$76k | `M1_S2_R2` | 1.74 | +$123k | −$71k |
| USDJPY | 4.27, +$138k | `M2_S3_R1` | 8.20 | +$219k | −$27k |

EURUSD preferred a lighter shifted sidecar; USDJPY preferred a runner-heavier main leg plus a larger shifted sidecar.

#### Pandas-to-broker comparison

| Pair | Pandas #1 | Broker rank of pandas tag | Broker #1 |
|---|---|---:|---|
| EURUSD | `M1_S2_R2` | #1 | `M1_S2_R2` |
| USDJPY | `M3_S3_R2` | #3 | `M2_S3_R1` |

#### All-pairs Phase 1 footnote

| Pair | Broker #1 | N/S | Status |
|---|---|---:|---|
| USDJPY | `M2_S3_R1` | 8.20 | Phase 2 hardened · live/paper |
| GBPUSD | `M1_S1_R2` | 2.67 | Phase 2 extended · paper-only |
| XAUUSD | `M2_S2_R3` | 1.90 | Phase 2 extended · heat / do-not-fund default |
| AUDJPY | `M1_S2_R2` | 1.83 | Phase 2 extended · satellite |
| EURUSD | `M1_S2_R2` | 1.74 | Phase 2 hardened · paper-only |
| XAGUSD | `M2_S2_R3` | −0.97 | **Excluded** from Phase 2 |

### Pair-specific read

#### EURUSD — `M1_S2_R2`

- Main: 3 = 2@30, 1@50; shifted: 2 = 1@30, 1@50; max primary/week: **3** (`R2`).
- EURUSD rewards a cautious structure: front-loaded main risk reduction + light sidecar.
- Roughly doubles baseline N/S (0.83 → 1.74) and exceeds ST+PMC 1.49.

#### USDJPY — `M2_S3_R1` / `M2_S3_R2`

- Primary: main 3 = 1@30, 2@50; shifted 4 = 2@30, 2@50; max **2**/week (`R1`) → N/S **8.20**.
- Alternate `M2_S3_R2` (max 3/week): N/S **8.19**, ~+$9k more net, slightly more stress.
- EURUSD’s light-sidecar recipe is **weak** on USDJPY (~rank 26) — do not cross-use.

### Phase 2 hardening plan

Phase 2 locks the pair-specific winners and hardens them for promotion — **not** a full re-sweep.

| Workstream | Purpose | Deliverable |
|---|---|---|
| Sub-period stability | Edge across FX regimes | [`SUBPERIODS.md`](../../live/state/monday_or_phase2/SUBPERIODS.md) |
| Monday/event clustering | Concentration check | [`CLUSTERING.md`](../../live/state/monday_or_phase2/CLUSTERING.md) |
| Local sensitivity | 30%/50% not knife-edge | [`SENSITIVITY.md`](../../live/state/monday_or_phase2/SENSITIVITY.md) |
| Live deployment thresholds | Operational sleeves | [`DEPLOYMENT_RULES.md`](../../live/state/monday_or_phase2/DEPLOYMENT_RULES.md) |
| Capacity / specs | Allocator-ready pair docs | `SPEC_EURUSD_*.md`, `SPEC_USDJPY_*.md` |

| Pair | Phase 1 status | Phase 2 outcome |
|---|---|---|
| EURUSD | Broker-confirmed leader | **Hardened · paper-only** (sub-period FAIL) |
| USDJPY | Broker-confirmed leader | **Hardened** — default Monday OR USDJPY candidate |
| USDJPY `M2_S3_R2` | Close alternate | Retained higher-dollar alternate (also 3/3 sub-periods) |

### Do-not-cross-use rules

- EURUSD uses **`M1_S2_R2`** only (light shifted sidecar).
- USDJPY uses **`M2_S3_R1`** (or `M2_S3_R2` alt) only — runner-heavy main + heavy sidecar.
- Do not transplant EURUSD’s light-sidecar recipe onto USDJPY (or vice versa).

### Phase 2 checklist

- [x] Fix EURUSD candidate: `M1_S2_R2` as default research-to-production config
- [x] Fix USDJPY candidates: `M2_S3_R1` (primary), `M2_S3_R2` (alt); `M3_S3_R2` research-only #3
- [x] Run robustness checks (sub-period, Monday clustering, DD sensitivity) → [`monday_or_phase2/`](../../live/state/monday_or_phase2/)
- [x] Define live deployment rules → [`DEPLOYMENT_RULES.md`](../../live/state/monday_or_phase2/DEPLOYMENT_RULES.md)
- [x] Produce pair-specific documentation → [`SPEC_EURUSD_M1_S2_R2.md`](../../live/state/monday_or_phase2/SPEC_EURUSD_M1_S2_R2.md), [`SPEC_USDJPY_M2_S3_R1.md`](../../live/state/monday_or_phase2/SPEC_USDJPY_M2_S3_R1.md)
- [x] Record do-not-cross-use rules (EURUSD vs USDJPY patterns)

### Suggested tracker fields (per candidate)

| Field | EURUSD | USDJPY |
|---|---|---|
| Strategy family | Monday OR intraday FX | Monday OR intraday FX |
| Current promoted tag | `M1_S2_R2` | `M2_S3_R1` |
| Alternate tag | — | `M2_S3_R2` |
| Baseline tag | `M1_S1_R1` | `M1_S1_R1` |
| Broker Net/Stress | 1.74 | 8.20 |
| Approx. USD Net | +$123k | +$219k |
| Stress | −$71k | −$27k |
| Structural read | Front-loaded main + light sidecar | Runner-heavy main + heavy sidecar |
| Status | Phase 2 hardened · **paper-only** | Phase 2 hardened · live/paper eligible |
| Next action | Regime filter / re-validate 2020+ | Phase 3 track-record under 3–5M cap |

### Strategic significance

This family broadens the intraday sleeve mix beyond plain CTA trend: Monday OR breakouts + shifted-primary re-engagement add non-vanilla intraday FX behaviour, capacity via major pairs, and a multi-horizon intraday + trend stack narrative. Futures intraday sleeves sell primarily on raw return; FX Monday OR sells on decorrelation, capacity, and differentiated market structure.

### Current conclusions

Phase 1 delivered pair-specific winners; Phase 2 locked and hardened them. **USDJPY `M2_S3_R1`** is the default Monday OR sleeve for live/paper under 3–5M caps. **EURUSD `M1_S2_R2`** remains the full-sample EURUSD N/S leader vs ST+PMC but is **paper-only** until post-2019 slices improve. Sizing is **not portable across pairs**. Phase 3 = live track-record (USDJPY-first).

**Cross-pair generalization (2026-07-19, [`../../live/state/fx_cross_pair_tracker_leaders/`](../../live/state/fx_cross_pair_tracker_leaders/)):**

| Pair | FBO 1/1/3 base | FBO 1/1/3 atr80 | ST+PMC MA-bull |
|---|---:|---:|---:|
| EURUSD | 1.04 | **1.62** | **1.49** |
| GBPUSD | 0.26 (stress −$659k) | **1.60** (stress −$69k) | **1.35** |
| USDJPY | **3.30** | **4.25** | −0.65 |
| AUDJPY | 0.58 | 0.46 | **1.30** |

USDJPY is the strongest FBO pair tested; atr80 helped 5/6 USD-pair variants (rescued GBPUSD); AUDJPY weak for FBO but fine intraday. FBO does **not** transfer to equity index futures (ES/NQ/YM all fail, [`../../live/state/futures_monthly_orb_fbo_broker/`](../../live/state/futures_monthly_orb_fbo_broker/)).

**Metals gambit + cross-universe top-4 (2026-07-19, [`../../live/state/metals_futures_strats_sweep/`](../../live/state/metals_futures_strats_sweep/), [`../../live/state/fx_metals_top4_report/`](../../live/state/fx_metals_top4_report/)):**

XAUUSD/XAGUSD converted from `fx/raw/` (PV 100 / 1000). Silver 2011-01-20 100× spike fixed before final ranking. Monthly FBO fails on metals (same as indices). **v2b prior-opposed** (ST+PMC 25/75 gate, 2015+) also fails: XAU N/S **−0.96**, XAG **−0.88** — same failure mode as AUDJPY (−0.95).

| Rank | Pair | Strategy | Net | MTM stress | **N/S** | CAGR | Sharpe | Max DD | Worst mo | Worst yr | Charts |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | **AUDJPY** | Yearly ORB scaleout3 | +$194k | −$9.0k | **15.26** | 2.60% | **1.03*** | −2.7%* | −1.33% | −0.40% | [24 yr](../../live/state/fx_metals_top4_report/charts/yearly_orb/audjpy_yearly_orb_scaleout3/INDEX.md) |
| 2 | **XAUUSD** | Yearly ORB scaleout3 | +$541k | −$48k | **11.30** | 5.16% | 0.76 | −10.4% | −5.60% | −0.36% | [24 yr](../../live/state/fx_metals_top4_report/charts/yearly_orb/xauusd_yearly_orb_scaleout3/INDEX.md) |
| 3 | **XAGUSD** | Yearly ORB scaleout3 | +$121k | −$20k | **6.21** | 1.74% | 0.65 | −5.5% | −2.34% | −0.01% | [24 yr](../../live/state/fx_metals_top4_report/charts/yearly_orb/xagusd_yearly_orb_scaleout3/INDEX.md) |
| 4 | **USDJPY** | Monthly ORB FBO 1/1/3 atr80 | +$93k | −$27k | **4.25** | 1.39% | 0.29 | −9.0% | −4.94% | −4.23% | [134 mo](../../live/state/fx_metals_top4_report/charts/usdjpy_fbo_1_1_3_atr80/INDEX.md) |

\*AUDJPY Sharpe/Max DD from validated `$250k` report (`audjpy_futures_strats_sweep/best_report_yearly_orb/`). Rank 5: XAUUSD ST+PMC MA-bull N/S **3.31** — [112 profitable trade charts](../../live/state/fx_metals_top4_report/charts/xauusd_stpmc_ma_bull_profitable/INDEX.md).

**2026-07-30 note:** Exact `sl50_tp150_3r_1mfill` on metals is **not** a promote path — XAU N/S **0.16**, XAG 0 closed units. Index CFD 1mfill live demos are US30 + NAS100 only ([`../../live/state/st_pmc_1mfill_cross_market/SUMMARY.md`](../../live/state/st_pmc_1mfill_cross_market/SUMMARY.md)).

**Chart hub:** [`../../live/state/fx_metals_top4_report/charts/INDEX.md`](../../live/state/fx_metals_top4_report/charts/INDEX.md) (driver `live/fx_metals_top4_charts.py`).

**Monthly FBO rules (promoted):** OR = first 3 sessions → ignore first break → arm opposite stop → max 2/month → **1 @ 0.25R / N @ 1R / 3 @ 2R** → BE after TP25 → daily-close SL → month-end flatten. Plugin: `live/strategies/monthly_orb_v2b_oco.py`.

**Post-TP2 path (1/1/3, n=60 TP2 hits):** after 1R, only **~42%** fill 2R; **~40%** touch entry/BE again; d+3 close still in favor **~49%** (coin flip). Study: [`../../live/state/eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/post_tp2_study/SUMMARY.md`](../../live/state/eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/post_tp2_study/SUMMARY.md).

## OR Profile Probability Engine → v2b policies (2026-08-02)

Batch probability engine over the v2b 15-minute opening range (`live/or_profile_engine.py`): replays 1m RTH tapes, walks each session as a causal event sequence (FirstBreak → 1R/2R/3R hits, re-entry, opposite break) under **dual triggers** — `touch` (1m pierce, matches v2b stop fills) and `close5` (5m close outside OR) — and labels terminal day profiles (`clean_break_1r`, `break_extend_2r`, `break_revert`, `fakeout_opposite`, `one_r_reversal`, `double_fail_range`, `no_break_range`). Refresh cadence is semi-annual: `python -m live.or_profile_engine --markets nq mnq ym mym --asof <tag>`.

- **Coverage:** NQ 3,987 sessions (2010–2026), YM 3,963, MYM 1,698, MNQ 1,245. Tables carry N / Wilson 95% CI / per-year stability. Hub: [`../../live/state/or_profile_engine/`](../../live/state/or_profile_engine/) (`SUMMARY_2026H2.md` pooled + per-market `2026H2/SUMMARY.md`).
- **Cross-market invariants (touch):** P(1R|break) **0.54–0.56**, P(2R|1R) **≈0.49**, P(re-enter OR|break) **0.88–0.91**, P(fakeout→opposite hits 1R|opp break) **0.14–0.17** on all four markets.
- **Stable NQ edges** (sign holds ≥70% of years, N≥30): breaks 10:30–12:00 hit 1R only **0.29** vs 0.54 pooled (16 yrs, 100%); wide-OR **q4** P(2R|1R) **0.37** vs 0.50 (16 yrs, 100%); narrow-OR **q1** failed breaks flip to an opposite break **0.92** (14 yrs).
- **v2b join** (`live/or_profile_v2b_join.py join`, S_1_1_3 tapes, fit ≤2024-12-31): **flat-gap sessions** (|gap| < 0.1× prior range, knowable at 09:45 arm time) run **−$211/session** on NQ (139 fit sessions, negative every year; MNQ agrees). Failed breaks (re-entry before 1R, p75 ≤ 2×5m candles) cost **−$4.8k/session** NQ. No stable size-up cell found.
- **Causal validation** (Engine+PaperBroker, hardened realism, frozen policies, 2025-01→2026-06): NQ **P1 skip flat-gap $414.0k** vs baseline $389.4k on 38 fewer sessions (net/session **+27%**, PF 1.36 vs 1.28); **P3 no-runner on q4** net flat, intrabar stress DD **−24%**; **P5 = P1+P3** best PF **1.446** and net/stress **5.3 vs 3.6**. MNQ orders identically. Rolling refit (fit ≤2025-06-30, validate 2025-07+) re-derives the same NQ policy and beats baseline again (+$19.5k) ⇒ semi-annual refresh cadence is sufficient. Hub: [`../../live/state/or_profile_engine/v2b_join/2026H2/`](../../live/state/or_profile_engine/v2b_join/2026H2/).
- **Promotion candidates:** NQ/MNQ v2b S_1_1_3 + **flat-gap skip** (max net) or **+ q4 no-runner combo** (max PF / net-stress). Early-cut exit (P4) needs a small `v2b_scaleout` config flag before it can be replayed causally — analytic-only for now.

## Combined book + OR-profile follow-ups (2026-08-02)

**PROMOTED: combined book = prior-opposed RL core + complement v2b satellite + flat-gap skip.** Causal Engine+PaperBroker replay (`live/v2b_combined_book_replay.py`): core B = promoted prior-opposed resting-limit S_1_1_3 (its own fills); satellite A = all-days v2b S_1_1_3 re-replayed with `regime_dates` restricted to days where **no gate limit was resting at 09:45** (knowable from B's `dynamic_sizing_events`), plus OR-profile flat-gap skip; all variants stress-audited on one union 1m tape. Hubs: [`../../live/state/nq_v2b_combined_book_causal/SUMMARY.md`](../../live/state/nq_v2b_combined_book_causal/SUMMARY.md), [`../../live/state/mnq_v2b_combined_book_causal/SUMMARY.md`](../../live/state/mnq_v2b_combined_book_causal/SUMMARY.md).

| Market | Portfolio | Net | Stress DD | N/S | PF |
|---|---|---:|---:|---:|---:|
| NQ | B_only (core) | $1,330,920 | -$68,610 | 19.4 | 2.326 |
| NQ | **B + A complement + skipflat** | **$1,921,202** | **-$85,341** | **22.51** | 1.585 |
| MNQ | B_only (core) | $128,360 | -$6,960 | 18.44 | 2.257 |
| MNQ | **B + A complement + skipflat** | **$182,965** | **-$8,606** | **21.26** | 1.554 |

Read: the complement satellite adds ~44% net on ~24% more stress and *raises* net/stress above the core alone on both markets. In live terms the satellite is a **second strategy instance (sidecar)** on the same account: it waits until 09:45, checks whether the core has a resting gate limit, and only arms v2b on non-gate, non-flat-gap days.

**REJECTED after causal test — q1 fakeout reversal satellite** (`live/strategies/q1_fakeout_reversal.py`, new StrategyPlugin; driver `live/q1_fakeout_satellite_replay.py`; DSR TRL-2026-00062..65). The stable 0.86–0.93 q1 failed-break→opposite-break flip cell does not convert to a standalone trade: stop at the failed extreme is clipped before the traverse completes (32–41% win), NQ split $9.9k/16yrs (PF 1.089, 8 negative years), MNQ flat/negative. v2b's reverse leg already harvests this move. Hub: [`../../live/state/q1_fakeout_satellite/SUMMARY.md`](../../live/state/q1_fakeout_satellite/SUMMARY.md).

**REJECTED after causal test — 10:30 entry time gate on v2b** (new `entry_cutoff_time` config flag in `v2b_scaleout`, kept for future studies). P6 (gate alone) and P7 (gate + P5 combo) lose net on both markets (NQ $359.6k vs $389.4k baseline; $252.3k vs $366.8k for P5) — late weak breaks are monetised by the reverse leg, so expiring the stops costs more than it saves. **P5 (flat-gap skip + q4 no-runner) stays the promoted v2b overlay.** Hub: [`../../live/state/or_profile_engine/v2b_join/2026H2/validation/SUMMARY.md`](../../live/state/or_profile_engine/v2b_join/2026H2/validation/SUMMARY.md).

**Queued plans (frozen, not executed):** runner ladder from the extension chain, asymmetric reverse leg (`reverse_only_when`), and the FX/CFD rollout of the OR-profile stats — [`../../live/specs/OR_PROFILE_NEXT_PLANS.md`](../../live/specs/OR_PROFILE_NEXT_PLANS.md).

## Intraday ORB Research Leader

**Adaptive 50/150 v2b-only scaleout** remains the mature intraday ORB candidate, but the 2026-05 ordering/plugin audit demotes the headline `$83k` run from "live-real" to "scanner diagnostic."

- Rule: prior-day **MA50 > MA150** (causal `shift(1)` on MNQ daily closes) → trade **v2b breakout only**; otherwise **skip the day** (no v2d).
- Management: **2 MNQ**, 1 off at TP1, runner stop to range-boundary breakeven, runner target at TP2 (`mnq/v2d/README_adaptive_50_150_scaleout.md`).
- **Ordering audit** (`mnq/v2d/paper_replay_v2b_scaleout_ordering.py`, DBN through 2026-04): the published **$83,245 / -$3,130 MTM** row is reproducible, but it is a **Long-priority scanner**. It gives Long the whole-day first chance; if Long never fills, it can still accept a Short that may have occurred earlier. That is useful research, but not how a broker/Pine OCO book behaves.
- **True intraday StrategyPlugin replay** (`live/strategies/v2b_scaleout.py` through `Engine` + `PaperBroker`), post-2026-05-20 realism re-baseline (1-tick slippage, $1.50 fees, stop gap-through, stop-first): the live-orderable OCO mode is **1,391 trades / 2,778 unit exits**, **$24,770 net**, **-$6,290 closed DD**, **-$6,318 intrabar stress DD**, **45.6%** win, **1.13 PF**, **3.92 Net/Stress** (pre-fix snapshot $34,444 / -$5,870 / 5.87 is preserved next to it).
- **Literal Long-first executable StrategyPlugin replay** (only trade Short after a filled Long exits): **1,052 trades / 2,102 unit exits**, **$12,688 net**, **-$7,326 closed DD**, **-$7,336 intrabar stress DD**, **45.7%** win, **1.09 PF**, **1.73 Net/Stress** (pre-fix $18,927 / -$6,163 / 3.07).
- Cross-market hardened OCO pass, common start **2021-03-04**, post-2026-05-20 realism re-baseline: **NQ remains the best V2B expression** with **2,785 unit exits / 1,394 campaigns**, **$299,477 net**, **-$63,828 intrabar stress DD**, **45.9%** win, **1.16 PF**, **4.69 Net/Stress**. MNQ holds at **$25,053 / -$6,318 stress / 3.97 Net/Stress** (still the cleanest low-capital row). **YM is no longer compelling at $26,930 / -$70,071 / 0.38**, and **ES (-$27,929 / -$115,020 / -0.24), MYM (-$198 / -$8,577 / -0.02), and MES (-$2,797 / -$7,294 / -0.38) flip to negative Net/Stress under realism**. MES is partial coverage because the local MES DBN is corrupted and the fallback CSV ends in 2023-08.
- **V2B sizing sweep (2026-05-21 / 22).** The v2b plugin is now configurable per bucket (`tp1_qty` / `tp2_qty` / runner = entry - tp1 - tp2). A 10-scenario × 6-market sweep was run through the same broker-like 1m path used by `v2b_strategy_cross_market_replay.py`. Full output: [`../../live/state/v2b_sizing_sweep/SUMMARY.md`](../../live/state/v2b_sizing_sweep/SUMMARY.md). Source: `potions/live/v2b_sizing_sweep.py`.

  **Best v2b sizing per market (limit_retest entry, realism baseline):**

  | Market | Best sizing | TP1 / TP2 / Runner | Entry | Net | Stress DD | Net / DD | vs 1/1/0 baseline |
  |---|---|---|---:|---:|---:|---:|---:|
  | NQ  | `S_1_1_3` | 1 / 1 / 3 | 5 |   $867,355 | -$118,094 | **7.34** | +2.65 vs 4.69 |
  | MNQ | `S_1_1_3` | 1 / 1 / 3 | 5 |    $74,442 |  -$12,372 | **6.02** | +2.05 vs 3.97 |
  | YM  | `S_1_1_0` | 1 / 1 / 0 (baseline) | 2 |    $26,930 |  -$70,072 | **0.38** | — |
  | MYM | `S_1_1_0` | 1 / 1 / 0 (baseline) | 2 |      -$198 |   -$8,577 | **-0.02** | — |
  | ES  | `S_4_2_1` (best of 3 partial) | 4 / 2 / 1 | 7 |   -$59,956 | -$393,564 | **-0.15** | partial coverage; full re-run in flight |
  | MES | — | — | — | — | — | — | not yet completed; ES + MES sweep re-running in background |

  **V2B's sizing bias is the OPPOSITE of yearly ORB.** Where yearly ORB rewards loading the TP25 (front-load), v2b rewards loading the **runner** (back-load). The reason: v2b's TP1 hits roughly as often as the runner stop, but the runner captures the larger intrabar trend on days where momentum persists past TP1. On NQ and MNQ the optimum is `1/1/3` (entry 5, big runner) at Net/Stress **7.34 / 6.02**; the user's `4/2/1` ladder is rank 6-7 of 10 (~4.5-5.2 Net/Stress) — still ~+15% better than the 1/1/0 production baseline but far below the back-loaded variants.

  **Symmetric and front-loaded variants under-perform on v2b.** `2/2/2` and `2/1/2` come in around 5.5-6.8 Net/Stress on the viable markets; `4/2/1`, `4/1/1`, `5/2/1` all sit in the 4.4-5.5 range. The pattern is consistent: more contracts on the runner bucket wins; more contracts on TP1 hurts.

  **YM / MYM v2b is not viable** under realism at any sizing tested. YM peaks at 0.38 Net/Stress (worse than every yearly ORB row); MYM is net-negative on every sizing.

  Recommended v2b promotion candidate: **`S_1_1_3` (entry 5, runner 3)** on NQ and MNQ. On NQ that's **+78% net** ($867k vs $488k baseline) at slightly lower Net/Stress drag than the user's 4/2/1 alternative. The user's `4/2/1` remains usable if a larger TP25 contribution is preferred for psychological reasons, but the data favours runner-heavy on this strategy.

  Full `1/1/3` stats are now broken out as standalone support docs: MNQ **1,164 sessions / 1,384 campaigns / 6,886 units**, **$74,441.50 net**, **-$12,234.50 closed DD**, **-$12,372.00 max MTM stress**, **53.61% campaign win**, **1.160 campaign PF**, **6.02 Net/Stress**, max **5** open units ([`MNQ_1_1_3_STATS.md`](../../live/state/v2b_sizing_sweep/MNQ_1_1_3_STATS.md)); NQ **1,164 sessions / 1,386 campaigns / 6,900 units**, **$867,355.00 net**, **-$116,718.50 closed DD**, **-$118,093.50 max MTM stress**, **53.82% campaign win**, **1.189 campaign PF**, **7.34 Net/Stress**, max **5** open units ([`NQ_1_1_3_STATS.md`](../../live/state/v2b_sizing_sweep/NQ_1_1_3_STATS.md)). Read: this is the best plain all-days v2b OCO expression, but it is a post-plumbing candidate after `1/0/0` because it adds runner management, larger notional exposure, and materially wider stress.
- **MNQ v2b ST+PMC regime-weighting pass (2026-05-24).** The first causal timing study shows **ST+PMC same-direction first is not a v2b size-up gate**: v2b after aligned ST+PMC is only **$3,775 / 1.08 PF**, while v2b after **opposite-direction prior ST+PMC** is the standout branch at **183 trades / $57,669 / 66.1% win / 2.24 PF**. Full timing output: [`../../live/state/mnq_v2b_st_pmc_timing_study/INDEX.md`](../../live/state/mnq_v2b_st_pmc_timing_study/INDEX.md).

  Regime-weighting research from the `S_1_1_3` unit tape confirms the hard filter is not the best answer. Using campaign-level 1m MAE stress reconstruction, baseline `1/1/3` is **$74,442 / -$10,246 reconstructed stress / 7.27 Net-Stress**. Hard-filtering to not-aligned keeps **$70,667** but worsens reconstructed stress to **-$11,907**. Weighted rows raise net but lower efficiency: `2/1/3` on not-aligned is **$86,674 / -$12,399 / 6.99**, `2/2/3` is **$99,992 / -$14,398 / 6.94**, and `3/2/3` is **$112,224 / -$16,904 / 6.64**. Read from this historical pass: keep `S_1_1_3` as the all-day v2b default, but treat the opposite-prior-ST+PMC branch as a separate delayed-arming gate; that strict plugin replay is now banked below. Output: [`../../live/state/mnq_v2b_regime_weighting_research/INDEX.md`](../../live/state/mnq_v2b_regime_weighting_research/INDEX.md). 15m review charts: [`../../live/state/mnq_v2b_regime_weighting_research/charts/prior_opposed_15m/INDEX.md`](../../live/state/mnq_v2b_regime_weighting_research/charts/prior_opposed_15m/INDEX.md). Source: `potions/live/mnq_v2b_regime_weighting_research.py`; chart builder: `potions/live/mnq_v2b_prior_opposed_15m_charts.py`.

  Cross-market follow-up using each market's `S_1_1_3` v2b tape and best available same-market ST+PMC candidate first identified **NQ as the strongest non-micro extension** of the MNQ prior-opposed idea. NQ base `S_1_1_3` is **$867,355 / -$100,085 reconstructed stress / 8.67**, and the prior-opposed branch is **184 trades / $616,085 / 2.35 PF / 11.25 Net-Stress**. ES, MES, YM, and MYM did show some prior-opposed improvement, but their full v2b books remained weak or negative: ES base **-$54,266**, MES **-$3,916**, YM only **0.18 Net-Stress**, MYM **-$5,028**. Output: [`../../live/state/v2b_regime_weighting_research_all/INDEX.md`](../../live/state/v2b_regime_weighting_research_all/INDEX.md). Read: that all-market pass was an after-the-fact unit-tape filter; the true delayed-arming plugin replays below supersede it for promotion decisions.

  Full broker-like confirmations were banked as real `StrategyPlugin` gates for **NQ, MNQ, ES, YM, and MYM**: v2b only arms after same-session same-market hourly ST+PMC has already **entered** in the opposite direction. The ES/YM/MYM rerun also adds a full-RTH-session filter after finding two YM/MYM early-close/holiday entries that could not rely on the normal 15:55 EOD flatten; the cleaned fill books have **0 entry-without-exit campaigns**.

  **2026-07-15 NQ gate-timestamp causality correction.** The banked “prior-opposed fill” gate used hourly **left-labeled** ST fill stamps (`fill.ts = hour open`). That is optimistic: a fill stamped `10:00` only means the limit was touched sometime in `[10:00, 11:00)`. Timing autopsy vs 1m first-touch reconstruction shows **~76–78% of NQ banked net** came from campaigns whose v2b entry was **before the true 1m ST fill was knowable** (lookahead victims). Artifacts: [`../../live/state/nq_v2b_prior_opposed_timing_study/INDEX.md`](../../live/state/nq_v2b_prior_opposed_timing_study/INDEX.md), [`../../live/state/nq_v2b_prior_opposed_stpmc_1m_touch/INDEX.md`](../../live/state/nq_v2b_prior_opposed_stpmc_1m_touch/INDEX.md), [`../../live/state/nq_v2b_prior_opposed_causal_proxies/INDEX.md`](../../live/state/nq_v2b_prior_opposed_causal_proxies/INDEX.md).

  | NQ gate semantics (2021-03-04+) | Campaigns | Net | Closed DD | Intrabar / MTM stress DD | Win % | PF | Net/Stress | Causal read |
  |---|---:|---:|---:|---:|---:|---:|---:|---|
  | **Resting-limit hour-complete (baseline)** — arm after opposite ST limit is knowably posted (`live_after + 1h`) | 432 | **$1,330,920** | -$68,110 | **-$68,610** | 66.0% | 2.33 | **19.40** | Causal; 432/1164 regime days; 0 violations |
  | Resting-limit left-label (diagnostic) | 434 | $1,321,745 | -$68,110 | -$68,610 | 65.7% | 2.30 | 19.26 | Lookahead on unfinished ST hours — demoted |
  | Hourly fill stamp (legacy banked) | 352 | $1,175,785 | -$53,267 | -$53,942 | 69.3% | 2.63 | 21.80 | **Inflated** — treat as diagnostic only |
  | Provisional all-regime + confirm resting ST in 60m | 1,279 | $878,900 | — | -$97,692 | — | — | 9.00 | Causal but weaker than gated baseline |
  | Provisional all-regime + invalidate if no 1m ST fill in 60m | 1,268 | $467,748 | -$130,390 | **-$131,315** | 53.3% | 1.14 | 3.56 | Causal; 664 invalidate exits |
  | Strict 1m-touch **fill** gate | 350 | $225,825 | -$152,412 | **-$153,087** | 48.9% | 1.20 | 1.48 | Causal but weak; waits for ST fill |

  **2026-07-16 hour-complete fix.** Left-label resting-limit had **104** early arms (**$569k**). Dropping them post-hoc understated the honest book. Re-stamping availability to **hour-complete** recovers **103/104** early sessions (median arm delay 60m, median entry delay **0**); causal baseline **$1,330,920 / 19.40** slightly beats left-label. Provisional overlays do not beat the gated baseline. Artifacts: [`../../live/state/nq_v2b_prior_opposed_causal_proxies/early_pnl_recovery/INDEX.md`](../../live/state/nq_v2b_prior_opposed_causal_proxies/early_pnl_recovery/INDEX.md).

  **Resting-limit still filters causally:** on each 1m bar it only arms v2b if an opposite-side ST+PMC entry limit is knowably resting (`available_at = live_after + 1h < now`). It does **not** wait for that limit to fill. Relative to all-regime v2b it still skips most days (**432 / 1,164**).

  **2026-06-29 feature-level causality refresh.** The saved replay folders for the important live candidates have now been regenerated with `FeatureSnapshot` audit rows. For prior-opposed, the refreshed NQ/MNQ/YM/MYM folders persist opening-range, regime-filter, and v2b entry-gate features and pass `event_ts <= available_at_ts <= current_bar_ts` with **0 actual causality violation rows**. Snapshot row counts: **NQ 1,261,429**, **MNQ 1,254,641**, **YM 1,260,441**, **MYM 1,245,441**. ES prior-opposed remains the earlier strict replay because the local ES 1m DBN is missing; restore ES 1m before claiming the same feature-snapshot refresh on ES. The regenerated runs also write replay manifests, making the common-window state more reproducible than the older summary-only folders.

  Cross-market table below is the **resting-limit hour-complete** family (NQ/MNQ/YM/MYM). **ES** still needs a restored 1m DBN. Legacy hourly-fill-stamp books remain under `*_stpmc_broker_like/` as diagnostics only.

  | Market | Campaigns | Units | Net | Closed DD | Stress DD | Win % | PF | Net/Stress | Causal |
  |---|---:|---:|---:|---:|---:|---:|---:|---:|---|
  | **NQ** | 432 | 2,160 | **$1,330,920** | -$68,110 | **-$68,610** | 66.0% | 2.33 | **19.40** | 0 violations; hour-complete baseline |
  | **MNQ** | 428 | 2,140 | **$128,360** | -$6,905 | **-$6,960** | 65.4% | 2.26 | **18.44** | 0 violations |
  | **YM** | 436 | 2,180 | **$289,225** | -$33,325 | **-$33,894** | 61.0% | 1.59 | **8.53** | 0 violations |
  | **MYM** | 423 | 2,115 | **$22,101** | -$3,387 | **-$3,417** | 60.5% | 1.46 | **6.47** | 0 violations |
  | ES | — | — | — | — | — | — | — | — | **blocked** — ES 1m DBN missing; legacy fill $348,688 / 10.51 |

  Cross-market INDEX: [`../../live/state/v2b_prior_opposed_resting_limit_cross_market/INDEX.md`](../../live/state/v2b_prior_opposed_resting_limit_cross_market/INDEX.md). Lookahead re-review (NQ): [`../../live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/LOOKAHEAD_REVIEW.md`](../../live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/LOOKAHEAD_REVIEW.md) — **SOLID** for minute-by-minute execution.

  **NQ long-history raw rerun (2026-06-17).** After restoring the long NQ 1m DBN, the strict delayed-arming NQ replay was rerun separately from **2010-06-06** using `nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst`. The supporting daily regime file and hourly ST+PMC gate tape currently end in early March 2026, so this is effectively a **2010-06-06 -> 2026-03-06** validated-window run even though the raw DBN extends to 2026-06-16. Result: **877 campaigns / 4,385 units**, **$1,713,277.50 net**, **-$53,172 closed DD**, **-$53,847 intrabar stress DD**, **64.77% win**, **2.427 PF**, **31.82 Net/Stress**, **877 / 877 prior-opposite entries**, **0 causal violations**. Compared with the banked 2021-start row, the added pre-2021 section contributes **525 campaigns** and **$528,692.50 net** without deepening full-window closed or intrabar stress DD. Output: [`../../live/state/nq_v2b_prior_opposed_stpmc_full_history_raw/INDEX.md`](../../live/state/nq_v2b_prior_opposed_stpmc_full_history_raw/INDEX.md). Read: this long-history tape still uses the **legacy hourly fill-stamp** gate; re-run with resting-limit before treating full-history Net/Stress as promotion truth.

  Outputs: cross-market resting-limit [`v2b_prior_opposed_resting_limit_cross_market`](../../live/state/v2b_prior_opposed_resting_limit_cross_market/INDEX.md); NQ [`causal_proxies/resting_limit`](../../live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md) + [`LOOKAHEAD_REVIEW`](../../live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/LOOKAHEAD_REVIEW.md); MNQ/YM/MYM [`mnq`](../../live/state/mnq_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) / [`ym`](../../live/state/ym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) / [`mym`](../../live/state/mym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md). Legacy fill-stamp diagnostics remain under `*_stpmc_broker_like/`. ES resting-limit pending 1m DBN restore.

  Robustness pressure points match across markets but the best risk lever differs by market. **NQ:** 2022 is weak (**$13,425 / 1.17 PF**), gap-through stop cost is large, and widest opening-range days degrade sharply (Q4 OR-width only **1.52 Net/closed-DD**); reducing Q4 OR-width campaigns to `1/1/1` keeps **$1,137,539 net** while improving reconstructed Net/Stress from **25.60** to **30.04**. **MNQ:** 2022 is also weak (**$874.50 / 1.11 PF / 0.27 Net/closed-DD**), gap-through stop cost beyond the baseline 1 tick is **$51,483**, and Q4 OR-width has only **1.44 Net/closed-DD**; the same Q4 OR-width `1/1/1` lever keeps **$109,077.50 net** while improving reconstructed Net/Stress from **24.40** to **28.47**. **ES:** weakest year is **2023** (**$22,030 / 1.27 PF / 0.79 Net/closed-DD**), gap-through cost is **$233,375**, and Q4 OR-width is the soft bucket (**3.48 Net/closed-DD**); best filter is `skip_2022_or_or_q4`, improving reconstructed Net/Stress from **11.92** to **13.95** but cutting net to **$242,295**. **YM:** base is the best filter/event row (**$320,190 / reconstructed 13.18 Net/Stress**), but there are **13** rolling 50-campaign PF<1 windows, **$161,525** gap-through cost, and Q3 OR-width is the soft bucket (**3.46 Net/closed-DD**). **MYM:** weakest year is **2024** (**$1,789 / 1.16 PF / 0.72 Net/closed-DD**), gap-through cost is **$17,096**, and Q3 OR-width is weak (**0.81 Net/closed-DD**); reducing Q4 OR-width to `1/1/1` improves reconstructed Net/Stress from **10.18** to **11.14** while keeping **$22,530** net. CPI/FOMC day skipping did not beat base on NQ/MNQ/YM; ES event-day skipping and MYM event-day size reduction improve reconstructed efficiency but need tick/date-overfit review before becoming rules.

  Execution-scrutiny pass is now separated from optimization and has been refreshed for all five strict markets. Output: [`../../live/state/v2b_prior_opposed_execution_scrutiny/INDEX.md`](../../live/state/v2b_prior_opposed_execution_scrutiny/INDEX.md); implementation spec: [`../../live/specs/V2B_PRIOR_OPPOSED_EXECUTION_SCRUTINY.md`](../../live/specs/V2B_PRIOR_OPPOSED_EXECUTION_SCRUTINY.md). All five pass fill-book causality (**0 violations**), but none is tick-proven yet. Bar-safe / same-1m ambiguous / pre-arm-touch: **NQ 141 / 45 / 166**, **MNQ 142 / 44 / 167**, **ES 95 / 22 / 128**, **YM 187 / 38 / 122**, **MYM 177 / 33 / 123**. Coarse not-bar-safe retest splits (later level retest / trigger-only / no later 1m touch): **NQ 146 / 64 / 1**, **MNQ 147 / 63 / 1**, **ES 113 / 36 / 1**, **YM 114 / 44 / 2**, **MYM 111 / 44 / 1**. Read: the bar-level complete-miss bucket is tiny across the family, but same-minute and pre-arm-touch campaigns still need tick/broker reconstruction before live funding.

  Combined-system check (2026-05-25) confirms the prior ST+PMC leg is additive but not the main engine. The audit keeps views separate: v2b gated only, the specific prior ST+PMC gate trades, paired prior-ST+v2b, and full ST+PMC plus gated-v2b portfolio. **NQ paired prior-ST+v2b** is **$1,206,797 net / -$63,195 conservative stress / 19.10 Net-Stress**, while the **full NQ ST+PMC + gated-v2b portfolio** is **$1,272,236 / -$78,482 / 16.21**. **MNQ paired** is **$115,442 / -$6,504 / 17.75**, and **full MNQ portfolio** is **$122,425 / -$7,880 / 15.54**. The prior ST+PMC gate trades alone are only modestly positive, so the edge remains mostly v2b-after-failed/opposed-ST+PMC rather than ST+PMC itself. Combined output: [`../../live/state/v2b_prior_opposed_stpmc_combined_system/INDEX.md`](../../live/state/v2b_prior_opposed_stpmc_combined_system/INDEX.md). Full-span 15m chart packs start at the prior ST+PMC entry and run to RTH close: [`MNQ`](../../live/state/v2b_prior_opposed_stpmc_combined_system/mnq/charts/combined_15m/INDEX.md), [`NQ`](../../live/state/v2b_prior_opposed_stpmc_combined_system/nq/charts/combined_15m/INDEX.md).
- **Start-small infrastructure candidate:** MNQ v2b TP1-only **`1/0/0`** (`entry_qty=1`, `tp1_qty=1`, `tp2_qty=0`, no runner) is now the explicit first paper/live plumbing target, even though it is not the highest-return v2b expression. Broker-like quick study: **1,164 sessions / 1,306 trades**, **$10,084.50 net**, **-$3,095 closed DD**, **-$3,109 max MTM / intrabar stress DD**, **54.52% win**, **1.113 PF**, **3.24 Net/Stress**, **max 1 open unit**, **$7.72 avg trade**, **$53.50 median trade**, **best $722 / worst -$572**, **max losing streak 6 / max winning streak 13**. On a `$7,500` reference stake, the full-window net is **134.5%**, but the yearly path is uneven: **2021 $2,030 / 27.1%**, **2022 $4.50 / 0.1%**, **2023 -$628.50 / -8.4%**, **2024 $1,868 / 24.9%**, **2025 $2,854.50 / 38.1%**, **2026 $3,956 / 52.7% through the local replay end**. Worst calendar-year stress was **-$3,097** in 2025; 2023 is the only negative calendar year. Exit mix: **617 TP1 wins / +$92,562.50**, **513 wide stops / -$83,174**, **176 EOD closes / +$696**. Its job is to prove the cloud runtime, 1m feed, 5m OR state, OCO order lifecycle, fill reconciliation, and EOD flattening before larger v2b buckets or higher-timeframe systems are funded. Detailed stats: [`../../live/state/v2b_tp1_only_quick_study/MNQ_1_0_0_STATS.md`](../../live/state/v2b_tp1_only_quick_study/MNQ_1_0_0_STATS.md). Plan: `live/specs/START_SMALL_BROKER_EXECUTION_PLAN.md`; cloud bootstrap: `live/specs/START_SMALL_CLOUD_BOOTSTRAP.md`; deploy scaffold: `live/deploy/README.md`.

  NQ mirror for the same TP1-only `1/0/0` rule is much larger but no longer a tiny plumbing test: **1,164 sessions / 1,303 trades**, **$121,160.50 net**, **-$32,330 closed DD**, **-$32,475 max MTM / intrabar stress DD**, **54.64% win**, **1.137 PF**, **3.73 Net/Stress**, **max 1 open unit**, **$92.99 avg trade**, **$558.50 median trade**, **best $7,248.50 / worst -$5,696.50**, **max losing streak 6 / max winning streak 13**. On a `$75k` reference stake it is **161.5%** full-window net, with yearly returns **2021 30.1%**, **2022 1.8%**, **2023 1.5%**, **2024 32.1%**, **2025 40.9%**, **2026 55.2% through the local replay end**. Worst calendar-year stress was **-$30,788** in 2025. Detailed stats: [`../../live/state/v2b_tp1_only_quick_study/NQ_1_0_0_STATS.md`](../../live/state/v2b_tp1_only_quick_study/NQ_1_0_0_STATS.md). Read: NQ `1/0/0` is a credible later paper candidate after MNQ infrastructure is stable, but its drawdown scale means it should not be the first live-plumbing target.
- **Clean-break StrategyPlugin replay** (`live/strategies/v2b_clean_break.py` on completed 5m RTH bars), re-run under the 2026-05-20 realism defaults (1-tick slippage, $1.50 fees, stop gap-through, stop-first):
  - **MNQ** Bullish 2R/RL: **675 trades / $8,878 net / -$2,016 stress / 4.40 Net-Stress** (was $9,498 / -$1,950 / 4.87).
  - **NQ** Bullish 2R/RL: **2,039 trades / $93,097 net / -$24,535 stress / 3.79 Net-Stress** (was $112,027 / -$19,115 / 5.86). The realism cost on NQ Net is the largest single percentage drop in the clean-break family (-17%).
  - **NQ** 09:45 fourth-RL baseline: **1,157 trades / $75,125 net / -$32,580 / 2.31**; **NQ** boundary-stop: **1,161 trades / $20,054 net / -$9,928 / 2.02**; **NQ** ladder-3 runner: **1,161 trades / $28,406 net / -$28,880 / 0.98**.
  - **MNQ** fourth variants are now sub-$5k and Net/Stress 1.0–1.4; the MNQ ladder-3 runner is essentially flat at $1,086 net.
  - Read: broad bullish clean-break survives, but the 09:45 boundary-stop and ladder variants are no longer attractive on their own under realism. They keep heat low but give up most of the upside.

**C3 calendar filter (diagnostic, 2026-05):** v2b scaleout on C3 days only (no MA filter) was **$57,396 / $4,412 MTM DD** — inflated vs tracker because it trades v2b on **v2d-regime** C3 days too. **C3 + MA50>MA150** (causal): **681 legs**, **$41,844 net**, **$4,412 MTM DD**. Neither beats the all-days v2b-only book. The separate **C3 hit + swing + opposite v2b break (×1)** branch remains a lower-frequency overlay (**445 trades**, **$5,556 net**, **$2,108 MTM DD**).

Pine paper-test: `pine/orb_adaptive_50_150_v2b_scaleout.pine`. MTM script: `mnq/v2d/mtm_v2b_scaleout.py`. Ordering audit report: `mnq/v2d/V2B_SCALEOUT_ORDERING_AUDIT.md`. Hardened plugin report: `live/state/v2b_strategy_plugin_replay/V2B_STRATEGY_PLUGIN_REPLAY.md`. Cross-market hardened report: `live/state/v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md`; NQ chart pack: `live/state/v2b_strategy_plugin_cross_market_requested/charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md`. Clean-break plugin report: `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`.

## ATR Supertrend Pine-Parity Correction

The prior promotion of **MYM ATR Supertrend weekly-primary / 10 max / 3-initial / entry guard** is revoked pending a fresh causal validation pass.

What changed:

- A TradingView parity check on 2026-05-08 showed the Pine script was using actual completed-week ATR, while the local chart/result behaved like a daily ATR stop engine.
- Root cause: the Python weekly ATR mapper was called after daily ATR columns already existed, so `atr_stop` / `atr_trend` resolved to the daily columns. The old "weekly-primary" result was therefore mislabeled.
- The old weekly-primary loop also entered on the same daily bar whose close produced the daily flip, which is too early for live execution.
- The shared weekly ATR mapper has been fixed so future weekly-primary runs actually use completed-week ATR.

Corrected MYM comparison:

| Variant | Net | MTM DD | Closed DD | Win Rate | PF | Status |
|---|---:|---:|---:|---:|---:|---|
| Legacy mislabeled MYM "weekly" | $81,587 | -$7,292 | -$1,922 | 57.8% | 15.04 | Research artifact only; not live-promoted |
| Causal daily ATR, no weekly-flat filter | $11,725 | -$13,602 | -$6,942 | 20.6% | 1.45 | Pine default now targets this family |
| Actual completed-week ATR | $40,296 | -$26,958 | -$10,242 | 11.5% | 3.52 | Cleaner weekly concept, but much more heat |

Current practical read: do **not** fund MYM ATR from the old $81k expectation. For MNQ, the first flat-file `StrategyPlugin` ATR signal replays are now banked below; those rows supersede the older ATR artifact leaderboard for live-test ranking. MYM still needs the same plugin pass before it is promoted again.

Key files:

- Legacy artifact and warning: `mym/case_studies/atr_supertrend_fixed_no_scaling/weekly_3initial/README.md`
- Causal daily correction: `mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/README.md`
- Actual weekly correction: `mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/README.md`
- Pine parity script: `pine/atr_supertrend_dca_10max_entry_guard_3initial.pine`

## Broker-Like Bar Replay Rankings

This is the current **new standard** table. Rows here are generated by `StrategyPlugin` logic through the flat-file `Engine` + `PaperBroker`: orders become active only after the confirming bar closes, fills come from later bars, positions are persisted, and open units are marked at the final replay close. Full output: `live/state/broker_like_replays/SUMMARY.md`. Summary charts: `live/state/broker_like_replays/charts/INDEX.md`. Detail chart packs: `live/state/broker_like_replays/charts/detail/INDEX.md`. Targeted yearly ORB OCO branch output: `live/state/yearly_orb_range_close_20pct_test/SUMMARY.md` and `live/state/yearly_orb_range_close_20pct_test/charts/detail/INDEX.md`. Targeted monthly overlap ST-retest output: `live/state/monthly_overlap_st_retest_broker_like/SUMMARY.md`; MNQ/NQ validation charts: `live/state/monthly_overlap_st_retest_broker_like/charts/detail/INDEX.md`. Targeted YM hourly ST+PMC retest output: `live/state/hourly_st_pmc_retest/SUMMARY.md`; broker-like trade charts: `ym/case_studies/ym_hourly_st_pmc_retest_replay/broker_like_trade_charts_200/INDEX.md`. Full hourly ST+PMC StrategyPlugin variant sweeps: YM-only `live/state/hourly_st_pmc_strategyplugin_variants/SUMMARY.md`; cross-market `live/state/hourly_st_pmc_strategyplugin_variants_cross_market/SUMMARY.md`. **WO gap reversal** (weekly 1h, cross-market): `live/state/wo_gap_reversal_broker_like/INDEX.md`; master doc: [`../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/WO_GAP_REVERSAL_STRATEGY.md`](../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/WO_GAP_REVERSAL_STRATEGY.md).

Numbers below are after the **2026-05-20 broker realism re-baseline**
(`slippage_ticks=1`, `fee_per_unit=$1.50`, stop gap-through, stop-first
same-bar ordering, OCO-collapsed risk projection). Every row in this table
and the V2B / overlap rows below has been re-run under those defaults; the
pre-fix snapshots live next to each summary as `*_before_realism_fixes.*`.

**Separate delayed-arming gate note:** the prior-opposed ST+PMC -> v2b family uses **resting-limit hour-complete** across NQ/MNQ/YM/MYM ([`cross_market`](../../live/state/v2b_prior_opposed_resting_limit_cross_market/INDEX.md)). NQ baseline **19.40** Net/Stress; MNQ **18.44**; YM **8.53**; MYM **6.47**. ES blocked pending 1m DBN. Legacy fill-stamp books are diagnostic only. NQ lookahead re-review: **SOLID** for minute-by-minute execution.

### Institutional risk metrics overlay

Allocator-style reporting now lives beside the Net/Stress leaderboard. The generator is [`../../scripts/institutional_strategy_metrics.py`](../../scripts/institutional_strategy_metrics.py), with full output at [`../../live/state/institutional_strategy_metrics/SUMMARY.md`](../../live/state/institutional_strategy_metrics/SUMMARY.md) and machine-readable rows in `live/state/institutional_strategy_metrics/metrics.csv`.

Method: each row (futures, FX, metals) is normalized to **3x intrabar stress-DD reference capital**, daily returns come from saved replay equity curves, QQQ adjusted-close returns are the benchmark, and the report adds **Sharpe, Sortino, Calmar/MAR, close-equity drawdown duration, unit-return skew where available, QQQ correlation/beta/downside capture, win rate, and profit factor**. JPY-quoted books (USDJPY/AUDJPY) are converted to ≈USD at **110**. These are still **hypothetical/backtested** metrics, not audited live performance. Drawdown duration is measured from close-equity high-water marks, while intrabar stress remains the capital anchor.

| Rank | Strategy | Ref Cap | Net | CAGR | Calmar | Sharpe | Sortino | DD duration | QQQ corr | QQQ downside capture | PF | Read |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | **NQ prior-opposed v2b resting-limit (hour-complete)** | $205,830 | $1,330,920 | 49.4% | 1.48 | 2.88 | 3.80 | 408d | -0.11 | -1.01 | 2.33 | **NQ baseline**. Lookahead review SOLID. |
| 2 | **MNQ prior-opposed v2b resting-limit (hour-complete)** | $20,880 | $128,360 | 48.2% | 1.45 | 2.74 | 3.63 | 232d | -0.09 | -0.94 | 2.26 | Micro mirror; replaces legacy fill-stamp sleeve. |
| 3 | **ES prior-opposed v2b gate (legacy hourly fill)** | $99,490 | $348,688 | 35.1% | 1.05 | 2.26 | 2.51 | 326d | 0.04 | -0.32 | 2.08 | **Pending** resting-limit rerun (ES 1m DBN missing). |
| 4 | **YM prior-opposed v2b resting-limit (hour-complete)** | $101,681 | $289,225 | 30.4% | 0.91 | 1.76 | 2.13 | 300d | 0.02 | -0.21 | 1.59 | Dow confirmation under causal gate. |
| 5 | **MYM prior-opposed v2b resting-limit (hour-complete)** | $10,250 | $22,101 | 25.8% | 0.77 | 1.45 | 1.70 | 371d | 0.02 | -0.13 | 1.46 | Micro Dow; causal resting-limit. |
| 6 | **MNQ hourly ST+PMC 25/75 3R** | $7,386 | $10,922 | 19.9% | 0.60 | 1.34 | 2.51 | 449d | 0.01 | -0.04 | 1.29 | Fast-feedback, low-heat MNQ hourly candidate. |
| 7 | **MNQ Yearly ORB scaleout3** | $32,007 | $67,942 | 18.1% | 0.54 | 0.91 | 0.63 | 378d | -0.09 | 0.03 | 32.63 | Low-frequency, lumpy, and capital efficient; PF is high because the sample is sparse. |
| 8 | **MNQ ATR daily ladder 10-max** | $76,830 | $146,875 | 16.9% | 0.51 | 0.80 | 0.65 | 632d | 0.38 | 0.71 | 4.54 | Good net, but more QQQ-like and less diversifying. |
| 9 | **MNQ ATR daily 3-initial 10-max** | $88,052 | $159,819 | 16.3% | 0.49 | 0.84 | 0.73 | 567d | 0.43 | 0.73 | 3.52 | Higher-net ATR expression with higher equity-beta behavior. |
| 10 | **MNQ Yearly ORB 20% range-close** | $42,423 | $66,845 | 14.8% | 0.44 | 0.81 | 0.71 | 194d | -0.01 | 0.19 | 7.94 | Similar net to MNQ yearly baseline with shorter close-equity DD duration. |
| 11 | **MYM hourly ST+PMC base 50/150** | $4,096 | $6,051 | 14.2% | 0.43 | 1.43 | 3.45 | 374d | 0.03 | -0.07 | 1.35 | Best MYM hourly row; small but clean. |
| 12 | **NQ Yearly ORB scaleout3** | $320,160 | $850,314 | 8.6% | 0.26 | 0.72 | 0.45 | 533d | -0.03 | 0.07 | 18.18 | Huge absolute net, but lower normalized CAGR because of the long window and large stress anchor. |
| 13 | **AUDJPY Yearly ORB scaleout3** | $37,763 | $192,125 | 8.4% | 0.25 | 0.70 | 0.40 | 654d | 0.05 | 0.02 | 8.85 | Top FX yearly ORB efficiency (≈USD @ 110). |
| 14 | **XAUUSD Yearly ORB scaleout3** | $143,709 | $541,254 | 7.1% | 0.21 | 0.72 | 0.43 | 1471d | -0.01 | -0.04 | 15.08 | Metals yearly ORB leader by absolute net. |
| 15 | **USDJPY Monday OR M2_S3_R1** | $80,065 | $218,890 | 5.9% | 0.18 | 0.47 | 0.62 | 743d | -0.03 | -0.11 | 1.14 | Phase 2 primary; sub-period PASS 3/3. |
| 16 | **XAGUSD Yearly ORB scaleout3** | $58,524 | $121,185 | 5.0% | 0.15 | 0.62 | 0.32 | 1417d | -0.01 | -0.03 | 27.81 | Silver yearly ORB; Monday OR rejected separately. |
| 17 | **USDJPY Monthly ORB FBO 1/1/3 atr80** | $76,152 | $107,890 | 3.9% | 0.12 | 0.32 | 0.18 | 1648d | -0.02 | -0.05 | 1.47 | Best USDJPY monthly FBO atr80 sleeve. |
| 18 | **GBPUSD Monday OR M1_S1_R2** | $259,849 | $231,279 | 2.8% | 0.08 | 0.36 | 0.53 | 2706d | -0.03 | -0.02 | 1.10 | Paper-only (sub-period FAIL). |
| 19 | **XAUUSD Monday OR M2_S2_R3** | $691,077 | $437,940 | 2.2% | 0.06 | 0.29 | 0.29 | 1331d | 0.01 | -0.02 | 1.09 | Sub-period PASS but heat caution / default do-not-fund. |
| 20 | **AUDJPY Monday OR M1_S2_R2** | $156,726 | $95,822 | 2.2% | 0.06 | 0.21 | 0.28 | 1468d | -0.03 | -0.01 | 1.05 | Optional small satellite; sub-period PASS. |
| 21 | **EURUSD Monday OR M1_S2_R2** | $212,575 | $123,271 | 2.0% | 0.06 | 0.26 | 0.36 | 3865d | -0.02 | -0.02 | 1.07 | Paper-only (sub-period FAIL). |
| 22 | **EURUSD Monthly ORB FBO 1/1/3 atr80** | $170,485 | $91,898 | 1.9% | 0.06 | 0.23 | 0.11 | 5441d | -0.02 | -0.02 | 1.35 | Promoted FX monthly filtered sleeve. |
| 23 | **GBPUSD Monthly ORB FBO 1/1/3 atr80** | $207,267 | $110,469 | 1.9% | 0.06 | 0.21 | 0.12 | 4734d | 0.01 | -0.01 | 1.29 | Cross-pair FBO atr80. |
| 24 | **EURUSD hourly ST+PMC 25/75 MA-bull prior** | $47,236 | $23,534 | 1.8% | 0.05 | 0.29 | 0.38 | 4068d | -0.00 | 0.00 | 1.11 | Promoted FX intraday baseline. |
| 25 | **GBPUSD hourly ST+PMC 25/75 MA-bull prior** | $26,583 | $11,933 | 1.6% | 0.05 | 0.15 | 0.21 | 3880d | 0.04 | 0.03 | 1.05 | Cross-pair ST+PMC MA-bull. |
| 26 | **AUDJPY hourly ST+PMC 25/75 MA-bull prior** | $58,689 | $25,370 | 1.6% | 0.05 | 0.36 | 0.45 | 4054d | 0.08 | 0.03 | 1.13 | Cross-pair ST+PMC MA-bull. |
| 27 | **AUDJPY Monthly ORB FBO 1/1/3 atr80** | $170,925 | $26,441 | 0.6% | 0.02 | 0.07 | 0.03 | 3134d | -0.01 | -0.01 | 1.08 | Cross-pair FBO atr80; weak N/S. |

Current institutional read: **resting-limit hour-complete now has full allocator metrics** — NQ **49.4% CAGR / Calmar 1.48 / Sharpe 2.88** on **$205,830** ref cap (**$1,330,920** net). Legacy fill-stamp NQ remains a diagnostic upper bound only (~52% CAGR / Calmar ~1.57). FX/metals join the overlay: **AUDJPY/XAUUSD yearly ORB** lead cross-asset Calmar after futures; **USDJPY Monday OR M2_S3_R1** is the best Monday OR allocator row (Phase 2 primary); EUR/GBP Monday OR and most FX ST+PMC/FBO sleeves show long DD durations and low Calmar under the same 3× stress capital yardstick. Hourly ST+PMC futures rows remain useful as smaller sleeves; ATR rows remain growth systems with positive QQQ correlation.

Next reporting upgrade for live/paper validation: every run should track expected vs actual fill price, queue/slippage delta, stop gap-through cost, missed fills, rejected orders, broker/local reconciliation deltas, and time-to-recover after live drawdowns. Those execution metrics are the bridge between a good backtest and something a CTM can diligence.

### Target portfolio products (5% / 10% / 15% / 20%)

Multi-tier suite sharing one sleeve universe; only risk weights and profit-lock thresholds change. Generator: [`../../scripts/portfolio_product_tiers.py`](../../scripts/portfolio_product_tiers.py). Hub: [`../../live/state/portfolio_product_tiers/SUMMARY.md`](../../live/state/portfolio_product_tiers/SUMMARY.md). Tier B replaces the prior single-product folder ([`target_10pct_portfolio/`](../../live/state/target_10pct_portfolio/README.md)).

| Tier | Design Σ (haircuted) | Profit-lock CAGR 2010–2026 | Max DD | +Years | Median year | Role |
|---|---:|---:|---:|---:|---:|---|
| **A · 5%** | 5.2% | **11.2%** | -5.5% | 17/17 | 7.7% | Low-risk; trend/mild FX backbone; v2b ≤5% |
| **B · 10%** | 11.7% | **14.4%** | -8.8% | 17/17 | 14.1% | Baseline medium product |
| **C · 15%** | 14.9% | **18.4%** | -11.8% | 15/17 | 18.6% | More v2b + USDJPY Mon OR; raised lock thresholds |
| **D · 20%** | 21.5% (no haircut) | **22.3%** | -11.4% | 17/17 | 19.3% | High-risk; full norm CAGRs; looser lock residual |

Design Σ is the advertised risk budget (weight × haircuted CAGR). Realized compound paths run above target because good years stack — profit-lock is the operating control, not the static uncapped curve.

### Allocator validation / overfit defense

The first institutional scorecard pass is now generated at [`../../live/state/strategy_validation_scorecard/SCORECARD_REPORT.md`](../../live/state/strategy_validation_scorecard/SCORECARD_REPORT.md), with implementation status at [`../../live/state/strategy_validation_scorecard/IMPLEMENTATION_STATUS.md`](../../live/state/strategy_validation_scorecard/IMPLEMENTATION_STATUS.md), a static HTML view at [`../../live/state/strategy_validation_scorecard/index.html`](../../live/state/strategy_validation_scorecard/index.html), and the NQ one-page validation note at [`../../live/state/strategy_validation_scorecard/ONE_PAGE_NQ_VALIDATION_PITCH.md`](../../live/state/strategy_validation_scorecard/ONE_PAGE_NQ_VALIDATION_PITCH.md). Generator: [`../../scripts/generate_strategy_validation_scorecard.py`](../../scripts/generate_strategy_validation_scorecard.py). Validation inputs: [`../../data/validation/dsr_trial_ledger.csv`](../../data/validation/dsr_trial_ledger.csv) and [`../../data/validation/peer_comparison_table.csv`](../../data/validation/peer_comparison_table.csv). Normative spec: [`../../data/docs/DSR_PEER_TECHNICAL_SPEC.md`](../../data/docs/DSR_PEER_TECHNICAL_SPEC.md).

Current implementation status: enough data exists to render a useful **hypothetical/backtested, unaudited** scorecard, but not enough to close allocator diligence. The backfilled DSR ledger uses **55** local strategy metric rows plus one control row and produces **N_eff 53.00**. Prefer resting-limit institutional metrics for NQ promotion (**Sharpe 2.88 / Sortino 3.80 / CAGR 49.4% / Calmar 1.48 / QQQ corr -0.11**); legacy fill-stamp (**Sharpe ~3.0 / CAGR ~52% / Calmar ~1.57**) remains diagnostic only. PSR vs zero and DSR-zero both round to **100.00%**, but this is not treated as "proof"; the scorecard explicitly marks peer-benchmark DSR and peer z-scores as **suppressed** because sourced peer factsheet/database metrics have not been collected.

First null-control layer: an equal-count all-day v2b campaign sampling control draws **352** campaigns from the **1,386** NQ all-day `S_1_1_3` campaigns over **2,000** seeded iterations. Real **legacy** NQ prior-opposed net is **$1,184,585**, versus sampling median **$215,466** and P95 **$471,784**; one-sided sampled-net >= real-net p-value is **0.0005**. Read: supportive of structure on the old tape, but the real net is **timestamp-inflated**; re-run vs resting-limit hour-complete (**$1,330,920**) / 1m-touch (**$225,825**) before treating as promotion evidence.

Second null-control layer (true delayed-arming replay): the random-gate harness runs the unchanged `Engine + PaperBroker + v2b_scaleout` path and randomizes only `dynamic_sizing_events`. Output: [`../../live/state/v2b_prior_opposed_random_gate_replays/INDEX.md`](../../live/state/v2b_prior_opposed_random_gate_replays/INDEX.md); plan/spec: [`../../live/specs/RANDOMIZED_DELAYED_ARMING_GATE_REPLAY_PLAN.md`](../../live/specs/RANDOMIZED_DELAYED_ARMING_GATE_REPLAY_PLAN.md).

**Two independent permutation families (NQ complete; stratified cross-market complete):**

| Family | What it controls for | NQ null median | NQ p(null ≥ real) | Read |
|---|---|---:|---:|---|
| **Stratified** (`stratified_fine_buckets`) | year, gate side, time bucket, OR-width quartile | $11,756 | 0.0050 | Random gates with identical structural characteristics do not reproduce the edge — rules out structural artifacts. |
| **Shuffled labels** (`shuffled_stpmc_side`) | direction only (ST+PMC timing and count fixed) | $370,025 | 0.0050 | Random direction with identical timing does not reproduce the edge — rules out timing-only artifacts. Real ($1,184,585) sits above null p99.5 ($568,650). |

The **non-zero shuffled null median is a feature, not a problem**: ST+PMC timing/count structure alone captures roughly **$370K** of the **~$1.18M legacy** NQ edge on the **2021-03-04–2026-03-06** prior-opposed common replay window. That timing/structure figure reflects NQ positive trend carry over this backtest period (full tape replay, not gate-event PnL alone) — it is **not** portable structural alpha across regimes. The prior-opposed directional component is the portion that cannot be explained by market carry alone. The gap between shuffled median ($370,025) and stratified median ($11,756) is gate-placement precision within structure (~$358K). The remainder above the shuffled median is directional alpha requiring the prior-opposed mechanic (~$457K in the rough decomposition below). **Null families are not orthogonal** — table is qualitative allocator narrative only. **Rebuild this decomposition on resting-limit** before allocator use; the legacy `$1.18M` total is timestamp-inflated.

| Component | Estimated contribution | Source |
|---|---:|---|
| Timing/structure alone (shuffled median) | ~$370K | Shuffled-label null (legacy tape) |
| Gate placement precision within structure | ~$358K | Stratified p50 gap to shuffled p50 |
| Prior-opposed directional mechanic | ~$457K | Real minus timing and placement components |
| **Total real (legacy hourly fill stamp)** | **$1,184,585** | Diagnostic — timestamp-inflated |
| **Total real (NQ resting-limit hour-complete baseline)** | **$1,330,920** | Arm after opposite ST limit knowably posted; nulls not yet re-run |

**Stratified cross-market (structural null):**

| Market | Stratified null seeds | Gate events | Null median net | Null P95 net | Null best net | Real strict net | p(null >= real) |
|---|---:|---:|---:|---:|---:|---:|---:|
| NQ | 200 | 332 | $11,756 | $184,136 | $308,294 | $1,184,585 *(legacy fill stamp)* | 0.0050 |
| MNQ | 200 | 331 | -$231 | $16,138 | $31,682 | $113,548 | 0.0050 |
| YM | 200 | 375 | -$42,778 | $24,353 | $95,549 | $320,190 | 0.0050 |
| MYM | 200 | 368 | -$5,878 | $714 | $3,180 | $26,054 | 0.0050 |

**Shuffled-label (mechanistic null, NQ only so far):** 200 seeds, null range $94,128–$568,650, null median $370,025, 0 causality violations. Ledger: `TRL-2026-00061` (`gate_null_shuffled_stpmc_side_nq`); `seed_hash=45685ee918ec80b8` matches stratified runs (same seed integers 1–200, different null method — documented in `parameters_json`).

Read: real clears **both** permutation families from the same engine. ES stratified remains blocked (missing ES 1m DBN). **Scale queue (resolution-only after mechanistic cross-market):** (1) shuffled-label 200-seed MNQ/YM/MYM, (2) `stratified_coarse_buckets` 200-seed NQ, (3) 2,000-seed `stratified_fine_buckets` on all five markets once ES DBN is restored. Remaining: source direct peer metrics, tick reconstruction for same-minute/pre-arm-touch rows, block-bootstrap / synthetic stress, DSR ledger logging for new exploratory runs.

| Rank | Candidate | Instrument | Net | Intrabar Stress DD | Max Open Units | Net / Stress DD | Current Read |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | **Yearly ORB scaleout3** | ES | **$328,728** | **-$40,403** | 3 | **8.14** | New top row after realism re-baseline; ES is the cleanest low-frequency yearly book once stop gap-through is modeled. |
| 2 | **Yearly ORB scaleout3** | NQ | **$850,314** | **-$106,720** | 3 | **7.97** | Highest absolute net in the broker-like table; needs six-figure stress capacity. |
| 3 | **Yearly ORB scaleout3** | YM | **$288,757** | **-$39,810** | 3 | **7.25** | Now the strongest non-NQ confirmation of the limit-retest yearly book. |
| 4 | **Yearly ORB scaleout3** | MNQ | **$67,942** | **-$10,669** | 3 | **6.37** | Limit-retest variant beats the OCO+20% variant on MNQ once slippage is in the mix. |
| 5 | **ATR daily ladder 1/1/2/2/2 10-max** | NQ | **$1,572,142** | **-$255,950** | 10 | **6.14** | Best NQ ATR efficiency under stricter fills; biggest absolute net of any row. |
| 6 | **Hourly ST + PMC 25/75 3R** | NQ | **$144,521** | **-$24,635** | 1 | **5.87** | Best cross-market hourly ST+PMC row; lower absolute net than NQ ATR, but only one open unit and much lower stress. |
| 7 | **ATR daily ladder 1/1/2/2/2 10-max** | MNQ | **$146,875** | **-$25,610** | 10 | **5.74** | Best MNQ broker-like ATR row; gives up ~0.3 % to slippage vs the pre-fix snapshot. |
| 8 | **YM hourly ST + PMC prior-bull gate** | YM | **$38,828** | **-$6,974** | 1 | **5.57** | Most efficient YM hourly variant; prior completed hourly MA50>MA150 gate keeps only the cleaner tape, but gives up a lot of net. |
| 9 | **ATR daily 3-initial 10-max** | NQ | **$1,717,281** | **-$309,069** | 10 | **5.56** | Top NQ net; more heat than ladder. |
| 10 | **ATR daily 3-initial 10-max** | MNQ | **$159,819** | **-$29,351** | 10 | **5.45** | Top MNQ net; trails ladder on efficiency. |
| 11 | **Yearly ORB scaleout3 20% range-close (OCO entry)** | NQ | **$741,289** | **-$141,210** | 3 | **5.25** | OCO-stop variant still strong on NQ but no longer beats the simple limit-retest book under realism defaults. |
| 12 | **YM hourly ST + PMC 40/120 3R** | YM | **$71,990** | **-$14,698** | 1 | **4.90** | Best practical YM hourly variant so far: 40 pt stop / 120 pt target improves both net and heat versus the base 50/150 branch. |
| 13 | **Yearly ORB scaleout3 20% range-close (OCO entry)** | MNQ | **$66,845** | **-$14,141** | 3 | **4.73** | MNQ OCO+20% variant largely matches the limit-retest variant in stress, similar in net. |
| 14 | **Hourly ST + PMC 25/75 3R** | MNQ | **$10,922** | **-$2,462** | 1 | **4.44** | Best MNQ hourly ST+PMC row; small dollar edge but very low heat and useful fast-feedback behavior. |
| 15 | **Hourly ST + PMC base 50/150** | MYM | **$6,051** | **-$1,366** | 1 | **4.43** | Best MYM hourly row; the original 50/150 branch beats the tighter 3R variants on MYM. |
| 16 | **Monthly ORB overlap daily-ST retest x5** | NQ | **$549,560** | **-$127,455** | 12 | **4.31** | Realism re-run on the targeted MNQ/NQ replay: -$238k vs the pre-fix $787,811 number, mostly from stop gap-through. |
| 17 | **ATR weekly 2-initial / 3-add / 6-max** | ES | **$853,550** | **-$200,208** | 6 | **4.26** | Weekly sweet-spot sizing translates best to ES; slippage cost is small relative to net. |
| 18 | **YM hourly ST + PMC close-against-entry exit** | YM | **$62,227** | **-$14,598** | 1 | **4.26** | Next-open exit when an hourly close moves against the entry level trims stress versus base, but lowers hit rate. |
| 19 | **YM hourly ST + PMC ST-flip exit** | YM | **$60,917** | **-$14,598** | 1 | **4.17** | Similar stress repair to close-against-entry; exits on opposing hourly Supertrend flip. |
| 20 | **YM hourly ST + PMC 35/105 3R** | YM | **$64,054** | **-$15,453** | 1 | **4.15** | Efficient, but the full PaperBroker audit ranks it below 40/120 3R because stress rises faster than net. |
| 21 | **Yearly ORB scaleout3 20% range-close (OCO entry)** | ES | **$350,746** | **-$86,333** | 3 | **4.06** | ES OCO yearly stays competitive but moves behind the limit-retest yearly ES row. |
| 22 | **MYM Yearly ORB scaleout3** | MYM | **$15,123** | **-$3,916** | 3 | **3.86** | Cleanest micro version of the limit-retest yearly book; OCO+20% MYM variant follows at $12,098 / $-6,098. |
| 23 | **YM hourly ST + PMC base 50/150** | YM | **$62,237** | **-$16,417** | 1 | **3.79** | Base one-contract hourly branch retained for comparison; variant sweep supersedes it for YM promotion decisions. |
| 24 | **NQ ATR weekly 2-initial / 3-add / 6-max** | NQ | **$1,443,304** | **-$428,513** | 6 | **3.37** | Still the highest NQ weekly net, but stress is the largest in the table. |
| 25 | **Monthly ORB overlap daily-ST retest x5** | MNQ | **$60,147** | **-$20,428** | 12 | **2.94** | MNQ overlap survives but the realism cost is larger in % terms than on NQ. |
| 26 | **MNQ ATR weekly 2-initial / 3-add / 6-max** | MNQ | **$119,295** | **-$42,836** | 6 | **2.78** | Weekly ATR on MNQ; lags daily-ATR rows by ~3 % from slippage. |
| 27 | **WO gap reversal** (55% gap, 2ct +50/300) | ES | **$120,647** | **-$45,687** | 2 | **2.64** | Best WO-gap market; beats v2b ES under realism; high trade count (~451). See [master doc](../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/WO_GAP_REVERSAL_STRATEGY.md). |
| 28 | **WO gap reversal** (55% gap, 2ct +50/300) | NQ | **$80,472** | **-$34,099** | 2 | **2.36** | Tier-B weekly 1h plugin; below yearly ORB / v2b NQ but above failed weekly-MA500 hardening. |
| 29 | **Hourly ST + PMC close-against-entry exit** | MES | **$5,525** | **-$2,394** | 1 | **2.31** | Best MES hourly row on partial CSV coverage; useful but not competitive with stronger NQ/MNQ/MYM hourly rows. |
| 30 | **WO gap reversal** (55% gap, 2ct +50/300) | MES | **$7,395** | **-$3,315** | 2 | **2.23** | Positive on partial MES history; beats v2b MES. |
| 31 | **WO gap reversal** (55% gap, 2ct +50/300) | MNQ | **$5,932** | **-$2,698** | 2 | **2.20** | Small-account viable; PF ~1.43; below v2b MNQ (3.97) and hourly ST+PMC MNQ (4.44). |
| 32 | **MES ATR weekly 2-initial / 3-add / 6-max** | MES | **$37,444** | **-$17,213** | 6 | **2.18** | MES weekly stays positive but coverage is partial (CSV ends 2023-08). |
| 33 | **Hourly ST + PMC prior-bull gate** | ES | **$96,231** | **-$45,174** | 1 | **2.13** | Best ES hourly row, but ES is not a strong expression of this rule family. |
| 34 | **WO gap reversal** (55% gap, 2ct +50/300) | YM | **$9,651** | **-$12,410** | 2 | **0.78** | Weak positive; same dow-mini band as v2b YM (~0.38); not a promotion market. |
| 35 | **WO gap reversal** (55% gap, 2ct +50/300) | MYM | **-$1,146** | **-$1,670** | 2 | **-0.69** | Net-negative; do not fund (matches v2b MYM band). |

Rows below the top 35 (full list in
[`live/state/broker_like_replays/SUMMARY.md`](../../live/state/broker_like_replays/SUMMARY.md))
include the monthly restricted scaleout3 markets (which mostly went **flat or
mildly negative on Net/Stress** once stops were no longer guaranteed to fill
at the trigger), the lower-ranked YM hourly ST+PMC variants in
[`live/state/hourly_st_pmc_strategyplugin_variants/SUMMARY.md`](../../live/state/hourly_st_pmc_strategyplugin_variants/SUMMARY.md),
the cross-market hourly ST+PMC sweep in
[`live/state/hourly_st_pmc_strategyplugin_variants_cross_market/SUMMARY.md`](../../live/state/hourly_st_pmc_strategyplugin_variants_cross_market/SUMMARY.md),
and the boundary-stop variants which now show how much of their headline edge
depended on gap-through optimism.

Main changes from the theoretical/research tables (post-2026-05-20 realism re-baseline):

- **Monthly restricted scaleout3 is demoted hard across the board.** Under realism defaults the limit-retest book is now: MNQ **$8,849 / -$20,335**, MES **$3,820 / -$7,390**, MYM **$5,471 / -$9,978**, NQ **$173,383 / -$201,682**, ES **$28,208 / -$97,017**, YM **$118,123 / -$56,856**. Same-bar/close assumptions were doing more work than previously known.
- **Boundary-stop monthly variants need a re-think.** The stop gap-through realism shows the boundary-stop entry is far more fragile than the prior optimistic fills suggested: MNQ **$10,755 / -$21,705**, ES **$19,174 / -$171,540**, NQ **$95,097 / -$213,576**, YM **$92,598 / -$84,546**, MES **$11,066 / -$8,171**, MYM **$7,640 / -$8,030**. The MNQ row in particular is now negative on Net/Stress; the earlier promotion was largely a fill-realism artifact.
- **Yearly ORB limit-retest book is the new headline.** Under realism: ES **$328,728 / -$40,403 / 8.14**, NQ **$850,314 / -$106,720 / 7.97**, YM **$288,757 / -$39,810 / 7.25**, MNQ **$67,942 / -$10,669 / 6.37**, MYM **$15,123 / -$3,916 / 3.86**, MES **$1,955 / -$2,859 / 0.68**. This now leads the table.
- **OCO+20%-range-close yearly variant** still posts strong rows but no longer beats the simple limit-retest yearly book on MNQ or ES under realism: NQ **$741,289 / -$141,210 / 5.25**, ES **$350,746 / -$86,333 / 4.06**, MNQ **$66,845 / -$14,141 / 4.73**, YM **$182,900 / -$63,598 / 2.88**, MYM **$12,098 / -$6,098 / 1.98**, MES **$9,878 / -$8,546 / 1.16**.
- **MNQ ATR daily ladder remains the top MNQ ATR row**, but slippage shaved roughly $400-$2k off net per spec. Daily-ATR rows continue to dominate weekly-ATR rows on Net/Stress for MNQ/NQ/MYM.
- **NQ is still the strongest capital-efficient market**, but it requires much larger capital — stress DD is six figures across nearly every NQ row.
- **MES/MYM** are still mixed as broad diversification sleeves: MYM weekly 2/3/6 is **$24,727 / -$19,032**; MES weekly 2/3/6 is **$37,444 / -$17,213**; most monthly/overlap MES/MYM rows remain sub-1.0 Net/Stress under realism. The new hourly ST+PMC pass is the main exception: **MYM base 50/150 posts $6,051 / -$1,366 / 4.43**, while **MES close-against-entry is $5,525 / -$2,394 / 2.31** on partial CSV coverage.
- **Monthly overlap daily-ST retest x5 (4h)** under realism (all six markets):
  - **NQ $549,976 / -$127,455 / 4.32** (pre-fix $787,811 / -$108,655 / 7.25, -30% net)
  - **MNQ $60,325 / -$20,428 / 2.95** (pre-fix $73,523 / -$18,348 / 4.01, -18%)
  - **MYM $9,813 / -$5,325 / 1.84** (pre-fix $14,043 / -$5,053 / 2.78)
  - **ES $135,734 / -$101,515 / 1.34** (pre-fix $322,847 / -$76,882 / 4.20, -58% net and a meaningful DD increase)
  - **YM $15,090 / -$46,115 / 0.33** (pre-fix $247,382 / -$54,030 / 4.58, -94% net — by far the biggest drop in the table)
  - **MES $2,613 / -$10,344 / 0.25** (pre-fix $8,744 / -$7,828 / 1.12)
  
  Net read: stop gap-through realism collapses the YM and ES rows down to "interesting but not investable" while NQ/MNQ are smaller but still meaningful. The earlier MNQ/NQ-only re-run had to be re-combined with the ES/MES/YM/MYM re-run to produce the unified `summary.csv`.
- **v2b MA50>MA150 scaleout, 1m StrategyPlugin replay** (MNQ-only, two modes; full history): **oco_then_reverse $24,770 / -$6,318 / 3.92** (pre-fix $34,444 / -$5,870 / 5.87); **strict_long_then_short $12,688 / -$7,336 / 1.73** (pre-fix $18,927 / -$6,163 / 3.07). Realism cost is ~28% of net for OCO and ~33% for strict, with stop slippage being the dominant effect.
- **v2b OCO cross-market** (common start `2021-03-04`, all six markets): **NQ $299,478 / -$63,828 / 4.69** (pre-fix $389,026 / -$58,840 / 6.61), **MNQ $25,053 / -$6,318 / 3.97** (pre-fix $34,444 / -$5,870 / 5.87), **YM $26,930 / -$70,071 / 0.38** (pre-fix $76,271 / -$51,933 / 1.47), **MYM -$198 / -$8,577 / -0.02** (pre-fix $4,092 / -$6,806 / 0.60), **ES -$27,929 / -$115,020 / -0.24** (pre-fix $63,239 / -$73,105 / 0.87), **MES -$2,797 / -$7,294 / -0.38** (pre-fix $1,466 / -$5,517 / 0.27). Net read: only NQ and MNQ survive realism on this V2B book. ES, MYM, and MES flip from marginal positives to outright losers once stop gap-through is honored; YM goes from "weak positive" to "near breakeven with a heavier DD" and stops being a viable expression at this size.
- **Hourly ST + prior-month-close retest variants** have now been run as true StrategyPlugin books through the same Engine + PaperBroker path across **MNQ, NQ, ES, MES, MYM, and YM**. The rule family is market-selective: **NQ 25/75 3R** is the strongest expression (**1,683 trades, $144,521 net, -$24,635 stress, 5.87 Net-Stress**), **MNQ 25/75 3R** is smaller but clean (**$10,922 / -$2,462 / 4.44**), and **MYM base 50/150** is surprisingly efficient (**$6,051 / -$1,366 / 4.43**). YM still prefers the prior-bull gate for efficiency (**$38,828 / -$6,974 / 5.57**) or 40/120 3R for practical net (**$71,990 / -$14,698 / 4.90**). **MES** is modest on partial CSV coverage (**$5,525 / -$2,394 / 2.31**, close-against-entry), while **ES** is weak outside a narrow prior-bull filter (**$96,231 / -$45,174 / 2.13**). Full cross-market table: `live/state/hourly_st_pmc_strategyplugin_variants_cross_market/SUMMARY.md`; YM-only table: `live/state/hourly_st_pmc_strategyplugin_variants/SUMMARY.md`; existing 200 YM base validation charts: `ym/case_studies/ym_hourly_st_pmc_retest_replay/broker_like_trade_charts_200/INDEX.md`.
- **Weekly previous-range 50% + 15m MA500 retest did not survive broker-like hardening.** The standalone research replay looked excellent, but the strict StrategyPlugin path with real resting midpoint limits, orders active only after the confirming hourly/15m bar, week-roll market flattening, slippage, and fees collapses the edge: **NQ $18,508 / -$44,998 / 0.41**, **YM -$2,037 / -$28,663 / -0.07**, **MNQ $664 / -$4,932 / 0.13**. Treat this branch as a useful visual/context study, not a deployable row unless the execution model is redesigned and revalidated. Hardening output: `live/state/weekly_mid_ma500_bias_broker_like_nq_ym_mnq/INDEX.md`. Daily 50-day MA yearly chart packs for NQ/YM/MNQ: `live/state/daily_ma50_yearly_charts_nq_ym_mnq/INDEX.md`.
- **WO gap reversal (weekly 1h, StrategyPlugin `wo_gap_reversal`)** — full-history cross-market broker-like replay (2026-05): **ES $120,647 / -$45,687 / 2.64**, **NQ $80,472 / -$34,099 / 2.36**, **MES $7,395 / -$3,315 / 2.23**, **MNQ $5,932 / -$2,698 / 2.20**, **YM $9,651 / -$12,410 / 0.78**, **MYM -$1,146 / -$1,670 / -0.69**. Ranks **27–35** in the table above (Tier B: viable on four markets, not yearly-ORB/ATR tier). Research simulator (index points, no fees): NQ both-sides **+7,862 pts / PF 1.46** full history; five rule variants tested — swing filter and 3-trade cap were inert, unlimited trades **-2,854 pts**, RTH-only **-4,667 pts**. Plugin: `live/strategies/wo_gap_reversal.py`; driver: `live/wo_gap_reversal_broker_like.py`; output: [`live/state/wo_gap_reversal_broker_like/INDEX.md`](../../live/state/wo_gap_reversal_broker_like/INDEX.md). Charts + refinement log: [`../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/WO_GAP_REVERSAL_STRATEGY.md`](../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/WO_GAP_REVERSAL_STRATEGY.md) · [`INDEX.md`](../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/INDEX.md) · [`VARIANT_COMPARISON.md`](../../nq/case_studies/nq_weekly_wo_gap_reversal_sample/VARIANT_COMPARISON.md).

### WO Gap Reversal (weekly 1h)

Discovered from **weekly 1h level charts** (WO + prior-week PWH/PWL/PWC/PWO). Hypothesis: a **≥55% body gap through weekly open** after pre-gap context, then **limit @ WO** on retest, **2ct scale-out** (+50 / runner 300, SL 50, BE on runner after +50). Causal plugin replay on **1h** bars across six markets.

| Tier | Markets | Net/Stress band | Read |
|------|---------|-----------------|------|
| **Promising** | ES, NQ | **2.36–2.64** | Best broker-like expression; ES beats raw v2b ES; NQ is mid-table |
| **Small / partial** | MNQ, MES | **2.20–2.23** | Positive but below v2b MNQ and top hourly ST rows |
| **Do not fund** | YM, MYM | **≤0.78** | Same weak dow-mini band as v2b |

Not competitive with **yearly ORB (6–8 Net/Stress)**, **ATR daily ladder (5–6)**, or **hourly ST+PMC NQ (5.87)**. Stronger than **weekly MA500 broker hardening (≤0.41)**. Variant work kept baseline rules; see linked `VARIANT_COMPARISON.md`.

## Research / Artifact Simulation Top 3

These remain useful for idea ranking and sizing hypotheses, but they are not all live-runtime signal replays.

| Rank | Candidate | Market / Size | Net | DD / MTM Heat | Net/DD | Why it is here | Replay Status |
|---:|---|---:|---:|---:|---:|---|---|
| 1 | **Yearly ORB scaleout3 inside-range swing stop, range-close portfolio** | 1 MNQ bundle + 4 MYM bundles = 3 MNQ + 12 MYM units | **$135,878** | **-$6,239 open-heat stress** | **21.78** | Best low-frequency blend found so far; MYM offsets MNQ enough to smooth the equity curve while preserving strong alpha. | Research portfolio sim; MNQ standalone has plugin replay, MYM portfolio plugin replay still needed. |
| 2 | **Yearly ORB scaleout3 inside-range swing stop, range-close standalone** | MNQ, 3-unit bundle | **$68,082** | **-$3,026 closed DD** / **-$4,604 stress** | **22.50 closed** / **14.79 stress** | Cleanest single-market low-frequency sleeve in the research sim. | Plugin replay exists; baseline stricter runtime row is **$39,217 / -$13,379 stress**, and the OCO+20% branch improves to **$66,913 / -$14,141 stress**. |
| 3 | **Monthly ORB overlap range breakout, 4h causal, daily ST limit-retest x5** | MNQ, 3-unit breakout + 5-unit ST retest add | **$87,586** | **-$17,995 4h MTM DD** / **-$18,175 pess. intrabar** | **4.87 MTM** | Research baseline for the overlap continuation branch; uses 4h causal entries and a daily Supertrend retest add to catch trend continuation. | Plugin replay now exists for all six markets; strongest rows are **NQ $787,811 / -$108,655**, **YM $247,382 / -$54,030**, **ES $322,847 / -$76,882**, and **MNQ $73,523 / -$18,348**. |

Runner-up intraday book (post-2026-05-20 realism re-baseline): true StrategyPlugin OCO v2b-only scaleout on MNQ (**$24,770 net / -$6,318 intrabar stress DD / 3.92 Net-Stress**) and the stronger NQ mirror (**$299,477 / -$63,828 stress / 4.69 Net-Stress**) — mature enough for paper/live parity work, but not the $83k scanner headline. The pre-fix snapshot ($34,444 MNQ / $389,026 NQ) is preserved beside each summary.

### Live-Runtime Replay / MTM Audit

The cross-candidate artifact MTM audit is banked at `live/state/candidate_mtm_audits/SUMMARY.md`. It validates execution books and heat for older CSV/unit artifacts, but only the `StrategyPlugin Signal Replay Rankings` table above should be treated as live-runtime signal generation.

## Volume / Participation Overlays

Databento source files and the derived front-month caches are **OHLCV**, so volume is available for participation studies. Confirmed local sources include `mnq/mnq_daily.csv`, `nq/nq_daily.csv`, and `mnq/data/mnq_front_month_4h_from_1m.csv`, all with a `volume` column.

Fresh sidecar charts for the current leaders:

- Yearly ORB inside-range swing/range-close, weekly candles with weekly volume + 20-week average:
  - MNQ: [`yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md`](yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md)
  - NQ: [`../../nq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md`](../../nq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md)
- ATR Supertrend weekly-primary 10max / 3-initial / entry guard, daily candles with daily volume + 20-day average:
  - MNQ: [`atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md`](atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md)
  - NQ: [`../../nq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md`](../../nq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md)

First read: use these as visual false-breakout research, not as an execution filter yet. A real filter should be tested causally with features such as breakout-week volume vs 20-week average, breakout-day volume vs 20-day average, and whether losing trades cluster on low-volume breaks or exhaustion-volume spikes.

## Fair Passive Benchmark

TradingView's buy-and-hold benchmark is useful, but it is not an apples-to-apples capital comparison for these futures sleeves because TV assumes the full initial capital is passively invested in the chart symbol for the full test. For our purposes, compare against a fixed ETF exposure from the same starting capital, then separately compare futures sleeves using the same account and explicit risk sizing.

First-pass `$50k` benchmark report: [`fair_benchmark_comparison/README.md`](fair_benchmark_comparison/README.md). Builder: [`../../scripts/fair_benchmark_comparison.py`](../../scripts/fair_benchmark_comparison.py).

10-year scaling proxy: [`fair_benchmark_comparison/SCALING_10Y.md`](fair_benchmark_comparison/SCALING_10Y.md). Builder: [`../../scripts/fair_benchmark_scaling_10y.py`](../../scripts/fair_benchmark_scaling_10y.py). This variant lets futures resize only at fresh trade entry, while ETF rows remain fully invested and compounded.

Top-strategy benchmark update: [`fair_benchmark_comparison/TOP_STRATS.md`](fair_benchmark_comparison/TOP_STRATS.md). Builder: [`../../scripts/top_strat_fair_benchmark.py`](../../scripts/top_strat_fair_benchmark.py). This now uses a **max 3x-stress normalized ranking** as the exact apples-to-apples table: the starting balance is the largest 3x intrabar stress-DD requirement in the selected strategy set, and every futures setup is scaled by `common capital / its own 3x-stress requirement`. This is fractional-book comparison math, not an executable order-size plan. The report also keeps a **$1,000,000 common-account executable ranking** as the whole-contract deployment view, keeps QQQ monthly DCA as a ranked passive/ETF strategy, keeps fractional exposure-parity as support math, and treats ATR/DCA separately by comparing it to **sizing up the strongest same-market yearly ORB book to the same stress budget**.

**Max-stress normalized comparison added:** the current common stress-capital anchor is **$927,206**, set by **NQ ATR daily 3-initial 10-max**. Under this exact normalized view, every futures row has the same target stress budget (**-$309,068**). Frozen TOP_STRATS still ranks **legacy NQ prior-opposed fill-stamp** #1 at **5.74x / $6,799,226 / 22.00 Net/DD** — that scaled figure is **timestamp-inflated**; NQ promotion baseline is resting-limit hour-complete (**19.40** Net/Stress raw; rebuild scaled TOP_STRATS before allocator use). Legacy fill-stamp still beats same-window QQQ DCA by **$6,282,712** on the frozen table. The next rows are **ES yearly ORB** (**7.65x / $2,514,650 / 271.2%**), **NQ yearly ORB** (**2.90x / $2,462,568 / 265.6%**), **YM yearly ORB** (**7.76x / $2,241,789 / 241.8%**), **MNQ yearly ORB** (**28.97x / $1,968,204 / 212.3%**), and **NQ ATR ladder** (**1.21x / $1,898,416 / 204.7%**). The `$1M` executable table remains useful for whole-book feasibility: at `$1M`, all selected rows can trade at least one full base book, and the NQ prior-opposed gate leads with **6 books / $7,107,510 net / 710.8% return / -$323,082 stress / 22.00 Net/DD**. Output CSVs: `top_strats_max_stress_normalized.csv`, `top_strats_max_stress_normalized_daily.csv`, `top_strats_common_account_executable.csv`, and `top_strats_common_account_executable_daily.csv`.

**QQQ DCA is now tracked as a serious passive strategy candidate.** Assumption: start with the same comparison account, buy equal monthly QQQ slices on the first available trading day, no new outside contributions, no cash interest. On the current top-strategy benchmark window (**2021-03-04 through 2026-03-06**) with the `$1M` common account, cash-funded QQQ monthly DCA ends at **$1,557,065**, with **$557,065 net**, **-$275,236 max DD**, **55.7% return**, and **2.02 Net/DD**. It trails lump-sum QQQ (**$2,032,312 end / $1,032,312 net / -$468,200 DD / 2.20 Net/DD**) in this rising window, but it cuts passive drawdown meaningfully and belongs in the ranked comparison set.

**QQQ / SPY / SHOP OBV bearish-cross DCA pass (2026-06).** Study: [`../../nq/case_studies/qqq_spy_shop_obv_bearish_dca_study/INDEX.md`](../../nq/case_studies/qqq_spy_shop_obv_bearish_dca_study/INDEX.md). Builder: [`../../scripts/etf_obv_bearish_dca_study.py`](../../scripts/etf_obv_bearish_dca_study.py). Rule: contribute **$1,000/month**, buy only when daily OBV crosses below its 20-day SMA, and size each signal buy from observed bearish-cross frequency so it attempts to deploy the same annual budget as blind monthly DCA. On the common SHOP-era window (**2015-06-01 through 2026-06-01**), bearish OBV crosses are **not rare**: QQQ **189 crosses / 17.18 per year / $698 matched add**, SPY **202 / 18.36 / $654**, SHOP **169 / 15.36 / $781**. Monthly blind DCA still wins ending equity on all three: QQQ **$476,490 vs best OBV $469,309**, SPY **$337,215 vs $331,919**, SHOP **$1,261,333 vs $1,238,524**. Read: the 20-day OBV bearish-cross trigger is more of a frequent pullback scheduler than a sparse crash-buy gate; it trims some cash timing/drawdown but does not beat blind monthly DCA in this first pass. Next variation, if needed: longer OBV MA / regime gate to force fewer, larger bearish-cross adds.

**Slower OBV MA sweep follow-up.** Output: [`../../nq/case_studies/qqq_spy_shop_obv_bearish_dca_study/MA_SWEEP.md`](../../nq/case_studies/qqq_spy_shop_obv_bearish_dca_study/MA_SWEEP.md). Tested OBV SMA **20 / 50 / 100 / 150 / 200 / 252 / 504** with the same `$1,000/month` contribution pool. The slower MAs do solve the cadence problem: QQQ closest to 5/year is **SMA150 at 5.36 crosses/year / $2,237 add**, SPY is **SMA200 at 4.27/year / $2,809**, and SHOP is **SMA100 at 5.55/year / $2,164**. But the performance read did **not** improve: best OBV ending equity remains below blind monthly DCA on all three (**QQQ $469,309 vs $476,490**, **SPY $332,445 vs $337,215**, **SHOP $1,238,524 vs $1,261,333**), and very slow SHOP variants miss too much of the major trend. Read: a slower OBV MA alone is not the answer; the next serious version should keep signal frequency down with a bullish-regime / drawdown-depth gate rather than simply waiting for a much slower OBV cross.

**Top SPY / QQQ / DIA holdings OBV DCA leaderboard.** Output: [`../../nq/case_studies/top_index_obv_bearish_dca_leaderboard/LEADERBOARD.md`](../../nq/case_studies/top_index_obv_bearish_dca_leaderboard/LEADERBOARD.md). Builder: [`../../scripts/top_index_obv_leaderboard.py`](../../scripts/top_index_obv_leaderboard.py). Current top-three ETF/index slots are preserved without deduping: SPY **NVDA / AAPL / MSFT**, QQQ **NVDA / AAPL / MSFT**, DIA **GS / CAT / MSFT**, so the basket is a nine-slot overlap/concentration study rather than nine unique companies. Rule: contribute **$1,000/month** to the portfolio, give each slot one ninth of the contribution, and on each slot's own bearish OBV cross buy `MATCHED_ADD_AVERAGE / 9`, where `MATCHED_ADD_AVERAGE = $12k / average crosses per slot per year`. Result on **2015-06-01 through 2026-06-01**: blind monthly top-nine DCA is still #1 at **$2,232,968 ending equity / $2,099,968 net / -$490,645 DD / 4.28 Net/DD**. Best OBV row is **SMA50** at **$1,725,774 / $1,592,774 net / -$370,239 DD / 4.30 Net/DD**, trailing monthly by **-$507,194**. Closest 5/year cadence is **SMA200** at **4.98 crosses/slot/year**, with **$2,410 matched-add average / $268 per slot signal**, but it falls to **$703,667 ending equity**. Read: OBV timing trims heat but sacrifices too much continuous exposure to the dominant top-holding trend; this is not a replacement for blind top-holdings DCA without an additional regime/valuation/drawdown gate.

**Current ranks 8-10 / bottom-of-top-10 diagnostic.** Output: [`../../nq/case_studies/top_index_bottom_top10_obv_leaderboard/LEADERBOARD.md`](../../nq/case_studies/top_index_bottom_top10_obv_leaderboard/LEADERBOARD.md). Builder: [`../../scripts/top_index_bottom_top10_obv_leaderboard.py`](../../scripts/top_index_bottom_top10_obv_leaderboard.py). Current ETF ranks 8-10 are SPY **META / TSLA / MU**, QQQ **TSLA / AVGO / GOOG**, and DIA **AXP / AAPL / SHW**. This is a **static current-holdings diagnostic**, not a true anti-hindsight annual holdings test. On **2015-06-01 through 2026-06-01**, blind monthly bottom-top10 DCA is #1 at **$1,226,258 ending equity / $1,093,258 net / -$308,990 DD / 3.54 Net/DD**. Best OBV row is **SMA20** at **$1,154,462 / $1,021,462 net / -$283,138 DD / 3.61 Net/DD**, trailing blind by **-$71,796**. Closest 5/year cadence is **SMA150** at **5.37 crosses/slot/year**, with **$2,233 matched-add average / $248 per slot signal**, but it falls to **$856,682 ending equity**. Read: the lower top-10 tranche is meaningfully weaker than the static current top-three basket and still does not reward OBV timing over continuous monthly exposure.

**Yearly-rotating ranks 8-10 correction.** Output: [`../../nq/case_studies/top_index_obv_yearly_ranks_8_10/YEARLY_RANKS_8_10.md`](../../nq/case_studies/top_index_obv_yearly_ranks_8_10/YEARLY_RANKS_8_10.md). Builder: [`../../scripts/top_index_obv_yearly_ranks_8_10.py`](../../scripts/top_index_obv_yearly_ranks_8_10.py). Schedule: [`../../nq/case_studies/top_index_obv_yearly_ranks_8_10/annual_ranks_8_10_schedule.csv`](../../nq/case_studies/top_index_obv_yearly_ranks_8_10/annual_ranks_8_10_schedule.csv). This is the true annual-rotation structure for the lower top-10 tranche: each year uses beginning ranks **8 / 9 / 10** from SPY, QQQ, and DIA for new contributions, while existing shares are held. Schedule status is **curated v0 / public-holdings approximation** pending fund-document/SEC audit. On **2010-01-01 through 2026-06-01**, blind monthly ranks 8-10 DCA is **$542,638 ending equity / $372,638 net / -$65,678 DD / 5.67 Net/DD**, far below same-cashflow **QQQ monthly DCA** (**$1,308,351 / $1,110,351 / -$216,105 / 5.14**) and **SPY monthly DCA** (**$772,121 / $574,121 / -$110,777 / 5.18**). Best OBV row is **SMA50** at **$522,877 / $352,877 net / -$64,573 DD / 5.46 Net/DD**, trailing blind by **-$19,762**. Closest 5/year cadence is **SMA200** at **4.87 crosses/slot-year**, with **$2,466 matched-add average / $274 per sleeve signal**. Read: once the current-holdings hindsight is removed, ranks 8-10 are not competitive; the useful top-holdings line remains the annual top-3 rotation, which essentially ties QQQ DCA.

**Yearly-rotating top-holdings correction (anti-hindsight pass).** Output: [`../../nq/case_studies/top_index_obv_yearly_rotation/YEARLY_ROTATION.md`](../../nq/case_studies/top_index_obv_yearly_rotation/YEARLY_ROTATION.md). Builder: [`../../scripts/top_index_obv_yearly_rotation.py`](../../scripts/top_index_obv_yearly_rotation.py). Schedule: [`../../nq/case_studies/top_index_obv_yearly_rotation/annual_top3_schedule.csv`](../../nq/case_studies/top_index_obv_yearly_rotation/annual_top3_schedule.csv). This fixes the major flaw in the static top-holdings leaderboard: instead of applying the 2026 winners back to 2010, each calendar year uses that year's beginning top-three SPY / QQQ / DIA schedule for **new monthly contributions**; existing shares are held, with no annual liquidation, taxes, fees, or cash interest. Schedule status is **curated v0 / public-top-holdings approximation** and should be SEC/fund-document audited before final promotion. On **2010-01-01 through 2026-06-01**, blind monthly yearly-rotation DCA is still #1 but with the hindsight edge removed: **$1,309,697 ending equity / $1,111,697 net / -$247,844 DD / 4.49 Net/DD**. This is almost tied with same-cashflow **QQQ monthly DCA** (**$1,308,351 / $1,110,351 / -$216,105 / 5.14 Net/DD**) and beats **SPY monthly DCA** (**$772,121 / $574,121 / -$110,777 / 5.18**); lump-sum QQQ/SPY are higher-net but use all **$198k** on day one, so they are a different cashflow. Best OBV row is **SMA20** at **$1,228,973 / $1,030,973 net / -$227,256 DD / 4.54 Net/DD**, trailing monthly by only **-$80,724**. Closest 5/year cadence is **SMA200** at **5.13 crosses/slot-year**, with **$2,339 matched-add average / $260 per sleeve signal**, but it falls to **$1,113,287 ending equity**. Read: this is the right structure for top-holdings research; OBV timing still cuts heat slightly but gives up enough exposure that monthly new-money DCA remains the baseline.

**QQQ yearly ORB is now tracked as a serious ETF timing sleeve.** Study: [`../../nq/case_studies/qqq_yearly_orb_study/INDEX.md`](../../nq/case_studies/qqq_yearly_orb_study/INDEX.md). Builder: [`../../scripts/qqq_yearly_orb_study.py`](../../scripts/qqq_yearly_orb_study.py). Rule family: Jan-Mar QQQ opening range, Apr-Dec long-only ETF exposure, no leverage, no fees, no cash interest. Full Yahoo adjusted OHLCV window (**2000-01-03 through 2026-06-01**, `$10k` start): best pure timing efficiency is **close-breakout next-open** at **$72,382 end / $62,382 net / -$7,531 max DD / 8.28 Net/DD / 38.3% exposure**. The resting stop-breakout version earns more absolute net (**$85,802 end / $75,802 net**) but with deeper heat (**-$10,400 max DD / 7.29 Net/DD / 40.0% exposure**). Cash-funded monthly QQQ DCA is fully invested by the end, averages **58.2% invested exposure**, and posts **$125,757 end / $115,757 net / -$22,802 max DD / 5.08 Net/DD**. Two hybrids now matter: **50/50 stop-breakout + monthly DCA** is **$105,780 end / $95,780 net / -$11,740 max DD / 8.16 Net/DD / 49.1% exposure**, while **DCA core + stop-breakout tactical cash sweep** is the highest-net ETF row at **$167,388 end / $157,388 net / -$23,151 max DD / 6.80 Net/DD / 60.2% exposure**. Lump-sum buy-and-hold is **$93,099 end / $83,099 net / -$17,265 max DD / 4.81 Net/DD**. Read: pure stop-breakout is under-invested versus DCA; the hybrid cash-sweep version is the fairer serious ETF candidate, while the close-breakout line remains the cleanest pure-timing efficiency row.

**DJD DCA / yearly ORB / QQQ correlation check.** Study: [`../../nq/case_studies/djd_dca_yearly_orb_correlation/INDEX.md`](../../nq/case_studies/djd_dca_yearly_orb_correlation/INDEX.md). Builder: [`../../scripts/djd_dca_yearly_orb_correlation.py`](../../scripts/djd_dca_yearly_orb_correlation.py). DJD's Yahoo adjusted window is **2015-12-18 through 2026-06-01**. Using the same ETF yearly-ORB convention (`$10k` starting capital, no fees/cash interest), DJD buy-and-hold has the highest absolute result at **$34,068 end / $24,068 net / -$6,130 DD / 3.93 Net/DD**, but cash-funded monthly DCA is the cleanest risk-adjusted row at **$19,740 / $9,740 / -$1,944 / 5.01**. The yearly ORB rows are weak: stop-breakout range-close is only **$11,423 / $1,423 / -$2,572 / 0.55**, close-breakout next-open **$11,296 / $1,296 / -$2,718 / 0.48**, and limit-retest **$10,458 / $458 / -$1,660 / 0.28**. A `$1,000/month` contribution DCA sidecar ends at **$250,699** on **$127,000** contributed (**$123,699 net / -$22,534 DD / 5.49 Net/DD**). Daily return correlation to QQQ is **0.651** (monthly **0.604**, yearly **0.413**), so DJD is a lower-beta/dividend-flavoured equity sleeve, not a low-correlation hedge.

**QQQ inverse/short proxy check:** the current study uses **PSQ** as the 1x inverse QQQ/Nasdaq-100 proxy, with local Yahoo adjusted OHLCV beginning **2006-06-21**. First pass does **not** support adding short exposure to this yearly ORB sleeve: standalone **PSQ inverse close-breakdown next-open** is **$6,654 end / -$3,346 net / -$5,975 max DD / -0.56 Net/DD / 21 trades / 0.40 PF**, and the combined **QQQ/PSQ dual close-confirmed ORB** is only **$48,160 end / $38,160 net / -$8,337 max DD / 4.58 Net/DD / 93 trades / 2.28 PF**. Read: account for shorts as a diagnostic, but do not promote the PSQ leg yet; the QQQ edge is still mostly long-only.

**GOOGL portfolio-booster visual candidate:** monthly adjusted Yahoo candles with causal weekly ATR Supertrend and confirmed monthly **low -> high -> lower low** pivots are charted at [`../../nq/case_studies/googl_monthly_lhll_weekly_atr_charts/INDEX.md`](../../nq/case_studies/googl_monthly_lhll_weekly_atr_charts/INDEX.md). Builder: [`../../scripts/googl_monthly_lhll_weekly_atr_charts.py`](../../scripts/googl_monthly_lhll_weekly_atr_charts.py). Current visual pack spans **2004-08-19 through 2026-06-03** daily data, **262** completed monthly candles, **34** pivot lows, **31** pivot highs, and **9** confirmed LHLL sequences using 2-month left/right confirmation. Read: visual candidate only so far; no DCA or portfolio-return ranking has been run yet.

**GOOGL / QQQ combined 2-month-low + LHLL DCA check:** Study: [`../../nq/case_studies/googl_qqq_combined_2m_low_lhll_dca_study/INDEX.md`](../../nq/case_studies/googl_qqq_combined_2m_low_lhll_dca_study/INDEX.md). Builder: [`../../scripts/googl_qqq_combined_2m_low_lhll_dca_study.py`](../../scripts/googl_qqq_combined_2m_low_lhll_dca_study.py). Rule: treat every 2-month-low touch occurrence plus every confirmed monthly LHLL occurrence as one shared signal pool, then size each buy from the combined expected annual rate. Common window **2004-08-19 through 2026-06-03**, `$1,000/month`, no catch-up/cash interest/fees. Basic GOOGL DCA is still best at **$4,802,541 ending equity / $4,539,541 net / -$934,019 DD / 4.86 Net/DD**; best combined GOOGL row is **first-touch-per-month + LHLL / rolling 5y rate**, **86 signals**, **$4,462,508**, trailing basic DCA by **-$340,033**. QQQ shows the same shape: basic DCA **$2,728,556**, best combined **$2,481,256**, trailing by **-$247,300**. Read: combined dip timing improves deployment versus pure signal replacement but still does not beat basic monthly DCA.

**GOOGL / QQQ RSI overbought deferral check:** Study: [`../../nq/case_studies/googl_qqq_combined_lhll_rsi_deferral_study/INDEX.md`](../../nq/case_studies/googl_qqq_combined_lhll_rsi_deferral_study/INDEX.md). Builder: [`../../scripts/googl_qqq_combined_lhll_rsi_deferral_study.py`](../../scripts/googl_qqq_combined_lhll_rsi_deferral_study.py). Rule: if smoothed RSI is overbought, skip that scheduled buy/add, hold the cash, and redeploy on later allowed buys capped at **2x** normal size. RSI uses causal prior-completed daily/weekly/monthly bars, sweeping thresholds **60/65/70/75/80**. Best result is not the combined signal; it is **plain GOOGL DCA with monthly RSI >=70 deferral**, which ends at **$4,944,145**, beating basic GOOGL DCA by **$141,604** with **46** blocked months and **$5,000** ending cash. Best combined GOOGL row improves to **$4,645,297** but still trails basic DCA by **-$157,244**. QQQ gets almost no benefit: best plain DCA deferral is only **+$764**, and best combined row still trails basic by **-$71,751**. Read: monthly RSI70 deferral is a real GOOGL DCA research candidate; it does not promote the combined signal.

**QQQ smoothed-RSI overbought/oversold timing check:** Study: [`../../nq/case_studies/qqq_smoothed_rsi_reliability/INDEX.md`](../../nq/case_studies/qqq_smoothed_rsi_reliability/INDEX.md). Builder: [`../../scripts/qqq_smoothed_rsi_reliability.py`](../../scripts/qqq_smoothed_rsi_reliability.py). Rule: QQQ adjusted daily RSI(14), smoothed with EMA(14); overbought starts at smoothed RSI **>=70**, oversold buy starts at **<=30**. On **2000-01-03 through 2026-06-02**, completed overbought intervals are **28**; median interval low is **-5.30%**, median interval high is **+11.78%**, median high-low range is **22.71%**, and 126d/252d forward returns are positive **89.3% / 92.6%** of the time. Read: overbought is not a reliable bearish sell signal for QQQ; it marks volatility risk inside a continuing trend. The textbook oversold line is too rare for a standalone buy scheduler (**3 total: 2001-09-21, 2008-10-09, 2008-10-15**). Threshold sweep says the first roughly comparable deployment threshold is **45.0** (**74 touches / 2.80 per year / $4,283 matched add / 91.5% deployed**), and the first **95% deployed** line is **51.5** (**99 touches / 3.75 per year / $3,201 add**). Best matched-add ending-equity threshold is **49.5** (**$3.90M**), still below monthly DCA (**$4.01M**) by **$107k**. The second-threshold lump test looks good only in-sample: contribute **$1,000/month**, hold cash, arm below a higher smoothed-RSI threshold, then buy **all available cash once** if the same drawdown reaches the second threshold. Best true full-sample row is **arm 60.0 / buy 57.5**, **68 buys**, **97.8% deployed**, **$4.079M ending equity**, beating monthly DCA by **$68,960**. But validation rejects promotion: fixed **2016 holdout** picks the same true rule from pre-2016 data and trails monthly DCA by **$16,866**, while yearly walk-forward from **2010** trails by **$337,385** because selected timing rows sit only around **68.7%** average exposure. Read: useful RSI timing diagnostic, but not a deployable DCA replacement as tested.

**QQQ low-high-lower-low-higher-high DCA check:** Study: [`../../nq/case_studies/qqq_market_structure_dca_study/INDEX.md`](../../nq/case_studies/qqq_market_structure_dca_study/INDEX.md). Builder: [`../../scripts/qqq_market_structure_dca_study.py`](../../scripts/qqq_market_structure_dca_study.py). Rule: confirmed daily pivot **low -> high -> lower low -> first later higher high** above that swing high; buy next available daily open. The causal backwards-trace sizing row uses only prior signal frequency to size each buy as `12 months of DCA / prior signals per year`, capped by available cash. Pivot sweep (`1/2/3/5/8` bars, high-break mode) does **not** beat monthly QQQ DCA. Best causal row is **1-bar pivots**, **80 signals / 3.03 per year**, median **7** signals/year, **99.7% deployed**, **$1.831M ending equity**, trailing monthly DCA (**$4.012M**) by **$2.181M**. Read: the structure signal appears too delayed/underexposed for QQQ accumulation as tested; use it as a context marker, not a DCA replacement.

**QQQ low-high-lower-low DCA check:** Study: [`../../nq/case_studies/qqq_market_structure_lhll_dca_study/INDEX.md`](../../nq/case_studies/qqq_market_structure_lhll_dca_study/INDEX.md). Builder: [`../../scripts/qqq_market_structure_lhll_dca_study.py`](../../scripts/qqq_market_structure_lhll_dca_study.py). Rule: confirmed daily pivot **low -> high -> lower low**; buy next available daily open after the lower-low pivot confirmation. This earlier entry is much closer than waiting for the higher high, but still does not beat monthly DCA. With **$1,000/month** contributions, monthly DCA is **$4.012M / -$714k DD / 5.17 Net/DD**. Best causal prior-frequency row is **3-bar pivots**, **207 signals / 7.84 per year**, median **8** signals/year, **89.9% deployed**, **$3.680M ending equity**, trailing DCA by **$332k**. The aggressive all-cash-lump diagnostic gets very close: **2-bar pivots**, **289 signals / 10.94 per year**, **99.4% deployed**, **$4.006M ending equity**, trailing DCA by only **$5.8k**. Read: lower-low confirmation is promising as a dip-deployment timing marker, but the tested matched/causal DCA replacement still loses; next research lever is probably hybridizing with baseline monthly DCA rather than replacing it.

**QQQ weekly-pivot market-structure DCA check:** Study: [`../../nq/case_studies/qqq_market_structure_weekly_pivot_dca_study/INDEX.md`](../../nq/case_studies/qqq_market_structure_weekly_pivot_dca_study/INDEX.md). Builder: [`../../scripts/qqq_market_structure_weekly_pivot_dca_study.py`](../../scripts/qqq_market_structure_weekly_pivot_dca_study.py). This repeats both structure branches on completed weekly candles, buys the **next available daily open** after the weekly signal is known, and now force-deploys any unspent annual budget on the final December weekly bar at that week's **high**. With **$1,000/month** cashflow and monthly DCA baseline (**$4.012M / -$714k DD / 5.17 Net/DD**), the best causal row is **L-H-LL / 3-week pivots / expanding prior-frequency sizing**, **31 signals / 1.17 per year**, **31 signal buys + 26 December sweeps**, **99.4% deployed**, **$3.982M ending equity**, trailing monthly DCA by **$29.5k**. The best any-mode row is **L-H-LL / 3-week pivots / static full-window sizing**, **$3.986M**, trailing DCA by **$25.3k**. The stricter **L-H-LL-HH** branch improves with the December fallback but still trails harder: best causal **18 signals / $3.869M / -$142k vs DCA**. Yearly chart pack for the best weekly row: [`../../nq/case_studies/qqq_market_structure_weekly_pivot_dca_study/charts/yearly_lhll_3w/INDEX.md`](../../nq/case_studies/qqq_market_structure_weekly_pivot_dca_study/charts/yearly_lhll_3w/INDEX.md). Read: weekly lower-low pivots plus a December catch-up nearly match monthly DCA, but most of the repair is from fallback deployment rather than pure signal timing.

**QQQ monthly-pivot market-structure DCA check:** Study: [`../../nq/case_studies/qqq_market_structure_monthly_pivot_dca_study/INDEX.md`](../../nq/case_studies/qqq_market_structure_monthly_pivot_dca_study/INDEX.md). Builder: [`../../scripts/qqq_market_structure_monthly_pivot_dca_study.py`](../../scripts/qqq_market_structure_monthly_pivot_dca_study.py). This repeats the weekly-pivot protocol on completed monthly candles (final partial 2026-06 monthly bar dropped), buys the **next available daily open** after the monthly signal is known, and uses the same final-December-week high catch-up. Monthly pivots are cleaner but too sparse to beat DCA. Best causal row is **L-H-LL / 2-month pivots / expanding prior-frequency sizing**, **11 signals / 0.42 per year**, **11 signal buys + 25 December sweeps**, **98.1% deployed**, **$3.915M ending equity**, trailing monthly DCA by **$96.1k**. The stricter **L-H-LL-HH** branch is again worse: best causal **7 signals / $3.865M / -$146k vs DCA**. Yearly chart pack: [`../../nq/case_studies/qqq_market_structure_monthly_pivot_dca_study/charts/yearly_lhll_2m/INDEX.md`](../../nq/case_studies/qqq_market_structure_monthly_pivot_dca_study/charts/yearly_lhll_2m/INDEX.md). Read: monthly swing structure is useful for context and major drawdown review, but weekly 3-bar pivots are the better timed version of this family.

**QQQ sliding 3-month-low limit DCA check:** Study: [`../../nq/case_studies/qqq_sliding_3m_low_limit_dca_study/INDEX.md`](../../nq/case_studies/qqq_sliding_3m_low_limit_dca_study/INDEX.md). Builder: [`../../scripts/qqq_sliding_3m_low_limit_dca_study.py`](../../scripts/qqq_sliding_3m_low_limit_dca_study.py). Rule: each day calculates the adjusted low of the prior **3 calendar months**, excluding the current day, and treats a touch of that rolling low as a buy-limit fill. Matched-add sizing uses `12 months of DCA / expected fills per year`, capped by available cash. On **2000-01-03 through 2026-06-03**, raw all-touch cadence is **291 signals / 11.02 per year** (`$1,089` static add), the cleaner **new-touch cluster** cadence is **136 / 5.15 per year** (`$2,331` add), and first-touch-per-month is **76 / 2.88 per year** (`$4,171` add). Best tested row is **first-touch-per-month / rolling-5y-rate**, **$3.526M ending equity / -$622k DD / 5.15 Net/DD**, trailing monthly DCA by **$475k** despite **96.0% deployed**. The clean `new_touch_cluster` static row is **$3.336M**, while causal expanding-rate is **$2.765M**. Read: sliding 3-month lows provide a usable dip cadence, but waiting for the rolling floor still gives up too much trend exposure to replace monthly QQQ DCA.

**QQQ sliding 2-month-low limit DCA check:** Study: [`../../nq/case_studies/qqq_sliding_2m_low_limit_dca_study/INDEX.md`](../../nq/case_studies/qqq_sliding_2m_low_limit_dca_study/INDEX.md). Same builder with `--lookback-months 2`; 50/50 hybrid: [`../../nq/case_studies/qqq_sliding_2m_low_limit_dca_study/HYBRID_50_50.md`](../../nq/case_studies/qqq_sliding_2m_low_limit_dca_study/HYBRID_50_50.md); extra-$500 overlay: [`../../nq/case_studies/qqq_sliding_2m_low_limit_dca_study/EXTRA_500_OVERLAY.md`](../../nq/case_studies/qqq_sliding_2m_low_limit_dca_study/EXTRA_500_OVERLAY.md). Shortening the lookback raises cadence and improves net versus the 3-month row, but still does not beat monthly DCA as a replacement. On **2000-01-03 through 2026-06-03**, raw all-touch cadence is **379 signals / 14.35 per year** (`$836` static add), `new_touch_cluster` is **176 / 6.66 per year** (`$1,801` add), and first-touch-per-month is **98 / 3.71 per year** (`$3,234` add). Best timing-only row is **first-touch-per-month / static-full-window**, **$3.656M ending equity / -$640k DD / 5.22 Net/DD**, trailing monthly DCA by **$345k** with **85.8% deployed**. The higher-deployment rolling-5y row is **$3.619M / -$639k / 5.16**, trailing by **$382k** with **97.4% deployed**. A 50/50 monthly-DCA + first-touch-per-month hybrid improves the gap: diagnostic static-full-window hybrid is **$3.829M / -$677k / 5.19**, trailing monthly by **$173k**, while the more defensible rolling-5y hybrid is **$3.810M / -$677k / 5.16**, trailing by **$191k**. The better use is as an **extra-cash sidecar**: keep `$1,000/month` DCA and add a fresh `$500` on 2-month low signals. All-touch adds **$189.5k** extra and ends at **$7.190M**, beating same-total monthly DCA by **$805k**; `new_touch_cluster` adds **$88k** and ends at **$5.395M**, beating same-total monthly by **$287k**; first-touch-per-month adds **$49k** and ends at **$4.735M**, beating same-total monthly by **$117k**. Read: 2-month lows are not a DCA replacement, but they may be useful for deploying **additional** cash into drawdowns.

**BTCC / AMZN / DIA 2-month-low extra-$500 sidecar check:** Study: [`../../nq/case_studies/btcc_amzn_dia_sliding_2m_low_dca_study/INDEX.md`](../../nq/case_studies/btcc_amzn_dia_sliding_2m_low_dca_study/INDEX.md). Builder: [`../../scripts/multi_asset_sliding_low_extra_overlay.py`](../../scripts/multi_asset_sliding_low_extra_overlay.py). Data: Yahoo adjusted daily OHLCV; `BTCC.TO` is TSX/CAD-like and begins **2021-02-25**, so common-window rows are the fair comparison. Rule: keep `$1,000/month` DCA and add a fresh `$500` on each ticker's 2-month-low touch signal. Common-window best rows through **2026-06-03**: **AMZN all-touches** adds **$33k** and ends at **$164,301**, beating same-total monthly DCA by **$8,546**; **BTCC.TO new-touch-cluster** adds **$21k** and ends at **$127,191**, beating same-total monthly by **$7,530** but with very poor drawdown efficiency (**0.37 Net/DD**); **DIA all-touches** adds **$32k** and ends at **$141,442**, beating same-total monthly by **$3,396**. Full available-history best rows: **AMZN new-touch-cluster +$34,983 vs same-total monthly**, **DIA first-touch-per-month +$5,639**, **BTCC.TO same as common window**. Read: the sidecar idea generalizes, but its quality depends heavily on the asset's trend/drawdown profile; BTCC gives strong extra-return timing but extreme heat.

**QQQ previous-quarter-low limit DCA check:** Study: [`../../nq/case_studies/qqq_quarterly_low_limit_dca_study/INDEX.md`](../../nq/case_studies/qqq_quarterly_low_limit_dca_study/INDEX.md). Builder: [`../../scripts/qqq_quarterly_low_limit_dca_study.py`](../../scripts/qqq_quarterly_low_limit_dca_study.py). No-fill year charts: [`../../nq/case_studies/qqq_quarterly_low_limit_dca_study/charts/no_fill_years/INDEX.md`](../../nq/case_studies/qqq_quarterly_low_limit_dca_study/charts/no_fill_years/INDEX.md). Rule: each completed quarter defines a low; in the next quarter, rest one buy limit at that prior-quarter low (Q1 uses prior-year Q4 when available), buy all available cash on touch, and if a calendar year has no quarterly-low fill, buy all available cash on the final trading day close. On **2000-01-03 through 2026-06-02**, prior-quarter lows filled **33 / 105 eligible quarters (31.4%)**, about **1.27 fills/year** across complete years, with **7** no-fill-year fallbacks. The strategy ends at **$3.857M / -$685k DD / 5.17 Net/DD**, trailing monthly DCA by **$154k** despite **99.1% deployed**. Fill rates by quarter are fairly even but lowest in Q1 (**7/26**) and highest in Q3/Q4 (**9/26** each). Read: previous-quarter-low retests are frequent enough for context and staged cash deployment, but too infrequent/late to replace monthly QQQ DCA under this all-cash-on-touch rule.

Window: **2020-01-01 through 2025-12-31**. ETF rows use Yahoo adjusted close. Futures rows include both a fixed one-bundle sleeve and a 3x open-heat stress-DD annual scaling model.

| Sleeve | End Capital | Net | Max DD / Stress DD | Return | Net/DD | Peak Size |
|---|---:|---:|---:|---:|---:|---:|
| Yearly ORB MNQ standalone, 1 bundle fixed | $118,082 | $68,082 | -$4,604 | 136.2% | 14.79 | 3 contracts |
| Yearly ORB MNQ+MYM portfolio, 1 bundle fixed | $185,878 | $135,878 | -$6,240 | 271.8% | 21.78 | 3 MNQ + 12 MYM |
| QQQ buy-and-hold | $147,260 | $97,260 | -$33,121 | 194.5% | 2.94 | full ETF capital |
| SPY buy-and-hold | $114,532 | $64,532 | -$19,083 | 129.1% | 3.38 | full ETF capital |
| 50/50 QQQ+DIA buy-and-hold | $120,093 | $70,093 | -$22,327 | 140.2% | 3.14 | full ETF capital |

Initial read: the fixed MNQ+MYM yearly ORB sleeve beats the passive ETF rows on both net and drawdown efficiency over this window, while fixed MNQ standalone has lower net than QQQ but much lower stress DD. The annual 3x-DD scaling rows show the compounding upside, but ending sizes become operationally large, so treat them as capital-efficiency math rather than a live sizing recommendation.

10-year proxy read: QQQ is a strong passive benchmark, ending near **$302k** from `$50k` over 2016-2025. Entry-resized MNQ yearly ORB wins the account-window test at about **$1.28M**, but it reaches **135 contracts**, so it is a scaling-theory result, not a suggested live route. NQ is the biggest winner once starting capital reaches roughly the 3x-DD requirement, but a `$50k` account cannot start NQ under that rule.

## Live-Test Leaderboard

Legacy mixed-source table. Use the **StrategyPlugin Signal Replay Rankings** section above for current automation-runtime ranking. Rows below are retained for historical comparison across research families and may include research artifacts rather than plugin-generated fills.

Capital efficiency here uses **Net / MTM DD** when mark-to-market equity is available. For older ORB studies, use the listed open-heat / closed-DD caveat in the linked study before treating the number as directly comparable.

| Candidate | Market / Size | Net | MTM DD / Stress DD | Net/DD | Why it matters | Live-test caveat |
|---|---:|---:|---:|---:|---|---|
| ATR legacy mislabeled weekly-primary DCA | MYM, max 10 | $81,587 | -$7,292 MTM | 11.19 | Research artifact that exposed the daily/weekly ATR bug | **Not live-promoted**; use corrected causal runs below |
| Corrected daily ATR, no weekly-flat filter | MYM, max 10 | $11,725 | -$13,602 MTM | 0.86 | Closest tradable interpretation of the daily-stop behavior seen on charts | Pine default now targets this family; needs paper parity before funding |
| Corrected actual completed-week ATR | MYM, max 10 | $40,296 | -$26,958 MTM | 1.49 | True weekly ATR concept after mapper fix | High heat and low hit rate; not currently the top live-test candidate |
| **ATR weekly-primary DCA, 10 max, 3 initial, entry guard** | MNQ, max 10 | **$303,214** | **-$16,524 MTM** | **18.35** | Highest MNQ net found so far with good capital efficiency; NQ confirms strongly at **$3.64M / -$123k MTM** | More moving parts than yearly ORB; needs reliable daily/weekly Supertrend state, Friday 15:50 adds, and close-based guard/re-entry automation |
| **Yearly ORB + 1 MNQ unit / 4 MYM units** | 3 MNQ + 12 MYM scaleout units | **$135,878** | **-$6,239 open-heat stress** | **21.78** | Best low-frequency portfolio smoothness found so far; MYM helps diversify MNQ drawdowns | Cross-market execution and larger total order count; yearly ORB samples are smaller |
| **Yearly ORB MNQ standalone** | 3 MNQ scaleout units | **$68,082** | **-$3,026 DD** | **22.50** | Very capital efficient and low-frequency | Smaller sample and less absolute profit than ATR DCA |
| **Monthly ORB overlap range breakout, daily ST limit-retest x5** (post-2026-05-20 realism re-baseline) | NQ/MNQ confirmed; ES/MES/YM/MYM re-run in progress | **NQ $549,560 / MNQ $60,147** (post-fix); pre-fix snapshot **NQ $787,811 / YM $247,382 / ES $322,847 / MNQ $73,523** preserved in `_before_realism_fixes` files | **NQ -$127,455 / MNQ -$20,428 stress** (post-fix); pre-fix **NQ -$108,655 / YM -$54,030 / ES -$76,882 / MNQ -$18,348** | **NQ 4.31 / MNQ 2.94** (post-fix); pre-fix **NQ 7.25 / YM 4.58 / ES 4.20 / MNQ 4.01** | 4h StrategyPlugin replay with daily Supertrend filter and real resting limit retest add | Riskier exposure profile: max 12 open units. Stop gap-through is the dominant realism effect for this book (-30% net on NQ). ES/MES/YM/MYM rows are being refreshed under the same defaults. |
| **Monthly ORB overlap range breakout, daily ST filter** | MNQ, 3-unit breakout only | **$50,386** | **-$10,020 4h MTM / -$10,843 pess. intrabar** | **5.03 MTM** | Cleaner version of overlap breakout; skips long breakouts against confirmed daily Supertrend | Lower net than retest branch, but simpler and lower heat |
| **Monthly ORB overlap range breakout, daily ST bearish-reclaim scale-in x5** | MNQ, 3-unit breakout + 5-unit reclaim add | **$58,061** | **-$10,020 4h MTM / -$10,843 pess. intrabar** | **5.79 MTM** | Adds after a confirmed bearish ST flip is reclaimed; improved net without worsening 4h MTM DD in this sample | Less upside than retest branch; only 5 add fills so far |
| **ATR daily-primary DCA, 10 max, 3 initial, entry guard** | MNQ, max 10 | **$235,057** | **-$15,606 MTM** | **15.06** | Strong growth variant; entry guard limits some bad early drift | Worse than weekly-primary on NQ and MNQ; higher churn |
| **ATR daily weekly-flat, 10 max, no entry guard** | MNQ, max 10 | **$188,414** | **-$11,331 MTM** | **16.63** | Cleaner than guard variant; fewest ATR DCA restarts among high-net variants | More exposed during early pullbacks; lower net than weekly-primary |
| **ATR daily weekly-flat, 5 max** | MNQ, max 5 | **$155,056** | **-$10,588 MTM** | **14.65** | Conservative ATR automation baseline; lower execution burden | Gives up upside versus 10 max and weekly-primary |
| **Adaptive 50/150 v2b-only scaleout, StrategyPlugin OCO** (post-2026-05-20 realism re-baseline) | MNQ, 2 contracts | **$24,770** (pre-fix $34,444) | **-$6,318 stress** (pre-fix -$5,870) | **3.92** (pre-fix 5.87) | Most mature intraday Pine-style candidate; current plugin arms both sides OCO, then reverses after the first campaign closes | More trades, fee/slippage sensitivity, smaller edge per trade; the $83k long-priority scanner is not the live/Pine parity number. NQ mirror under same realism is $299,477 / -$63,828 / 4.69. |
| **Monthly ORB restricted scaleout3** | MNQ, 3-unit daily bundle | **$105,154** | **-$6,410 stress / -$3,723 closed** | **28.3** | Same monthly OR + range-close rules as 1-lot restricted, with **yearly-style** TP25 / full TP / runner + BE; **~2.4×** the gross pts of 1-lot restricted on this sample | **Worse** heat than 1-lot restricted; **not** the same sample window as yearly ORB (2020–2025) row; daily OHLC; no fees in CSV |
| **Monthly ORB restricted scaleout3** | NQ, 3-unit daily bundle | **$1,323,093** | **-$64,050 stress / -$37,278 closed** | **35.5** | NQ mirror of MNQ scaleout3; very large nominal $ from pt mult | Same caveats as MNQ row; do not rank next to intraday legs without normalizing horizon and contract-equivalents |
| **Monthly ORB restricted stop-limit cycle** | MNQ, 3-unit breakout/bottom + 2-unit refill | **$51,288** | **-$13,144 DD** | **3.90** | New long-only state-machine study: breakout stop, 25% close-stop, bottom-limit reclaim, and post-TP1 top-boundary refills | Daily OHLC only; wide/high-vol ranges can create large losses; needs 4h/1m causal rebuild before live testing |
| **Monthly ORB restricted stop-limit cycle** | NQ, 3-unit breakout/bottom + 2-unit refill | **$612,935** | **-$139,060 DD** | **4.41** | NQ confirms the long-side directional pulse, with similar PF and drawdown behavior | Same daily-OHLC caveat; not yet Pine/Tradovate ready |

Monthly ORB **baseline + range-close restricted** is **about $44k on 1 MNQ** with **about −$2.4k** max equity DD and very sparse fills — intentionally **not** a row-vs-row match to pyramid ATR sizing. Charts and side-by-side read vs these ATR lines: [`monthly_orb/MONTHLY_ORB_RESTRICTED.md`](monthly_orb/MONTHLY_ORB_RESTRICTED.md).

### Monthly ORB restricted — scaleout3 (research)

**Simulator:** [`scripts/monthly_orb_restricted_scaleout3.py`](../../scripts/monthly_orb_restricted_scaleout3.py) · **CSV:** `mnq/mnq_monthly_orb_restricted_scaleout3.csv` (NQ: `nq/nq_monthly_orb_restricted_scaleout3.csv`).

**Stack rank vs this doc (plain read):**

- **vs 1-lot monthly restricted** (~$44k / ~−$2.4k closed in the table above): scaleout3 pushes **much higher gross** on the **bundle point sum** (three units), but **closed DD and stress DD both deepen** versus the single-position book — it trades **capital for expectancy** in the monthly sleeve, not a free lunch.
- **vs Yearly ORB MNQ standalone** ($68k / −$3k on a shorter 2020–2025 yearly sample): scaleout3 shows **higher headline $** on the **full monthly-CSV horizon**, but the windows and rules differ (monthly OR vs Jan–Mar yearly OR, **boundary stop** vs swing stop), so treat as **directional**, not a strict horse race.
- **vs Adaptive v2b-only scaleout** (~$36k / −$5.2k): monthly scaleout3 has **higher Net/closed-DD** on the numbers here, but **far fewer** “trades,” **daily** bar fidelity only, and a **different** economic exposure (three overlapping unit exits per bundle vs 2-lot intraday path).
- **vs ATR DCA 10-max rows**: monthly scaleout3 is **orders of magnitude smaller** in absolute dollars and operational surface than pyramided ATR; it belongs in the **low-touch / low-frequency** bucket with yearly ORB and 1-lot monthly restricted, not next to 10-lot ATR without a sizing bridge.

**Metrics, MAE, stress DD methodology:** [`monthly_orb/METRICS_SCALEOUT3.md`](monthly_orb/METRICS_SCALEOUT3.md). **Charts:** [`monthly_orb/baseline_restricted_scaleout3/INDEX.md`](monthly_orb/baseline_restricted_scaleout3/INDEX.md).

**Broker-like replay update (post-2026-05-20 realism re-baseline):** the daily `StrategyPlugin` / `PaperBroker` version with 1-tick slippage, $1.50/RT fees, and stop gap-through enabled is now: **MNQ $8,849 / -$20,335**, **NQ $173,383 / -$201,682**, **ES $28,208 / -$97,017**, **YM $118,123 / -$56,856**, **MYM $5,471 / -$9,978**, **MES $3,820 / -$7,390**. The old "MNQ ~$2.4k" pre-fix snapshot is preserved in `live/state/broker_like_replays/summary_before_realism_fixes.csv`. The monthly book mostly survives only on YM and (more marginally) ES under realism; MNQ/NQ/MES/MYM rows are now far less attractive than yearly ORB or daily ATR.

### Monthly ORB restricted — stop-limit cycle (research)

**Simulator:** [`scripts/monthly_orb_restricted_stop_limit_cycle.py`](../../scripts/monthly_orb_restricted_stop_limit_cycle.py) · **CSV:** `mnq/mnq_monthly_orb_restricted_stop_limit_cycle.csv` (NQ: `nq/nq_monthly_orb_restricted_stop_limit_cycle.csv`). **Charts:** [`monthly_orb/restricted_stop_limit_cycle/INDEX.md`](monthly_orb/restricted_stop_limit_cycle/INDEX.md). **Report:** [`monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md`](monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md).

Current long-only rule state:

- Monthly OR = first 3 daily rows.
- Primary order is a buy stop at the OR high.
- Breakout packages use 3 contracts: 1 off halfway to TP1, 1 off at TP1, 1 runner to TP2.
- Breakouts are invalidated only by a daily close more than **25% back inside** the OR.
- After a failed breakout before TP1, the bottom-limit reclaim becomes available, but a fresh breakout may still fire before the bottom limit fills.
- Bottom-limit reclaim enters at OR low, uses a **daily-close** stop at `OR low - 0.25 * range`, takes 1 off at OR high, and exits the other 2 at TP1.
- After TP1, a 2-contract top-boundary refill can fill while an earlier runner is still open. The refill now closes before TP1 on any daily close **at or below OR high**, including a close below the full range.

Latest long-only results after the 25% close-stop and top-refill fix:

| Market | Packages | Net | Max DD | Win Rate | PF | Avg MAE | Max MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 148 | $51,288 | -$13,144 | 52.0% | 1.63 | 213.2 pts | 1,039.2 pts |
| NQ | 338 | $612,935 | -$139,060 | 49.1% | 1.58 | 120.0 pts | 1,038.0 pts |

The worst months are not simply high trade-count months. The pattern is **failed expansion in wide/high-volatility ranges**: repeated stop-breakouts close 25% back into the OR before TP1, sometimes followed by a bottom-limit daily-close stop, and no TP2 runner to pay for the churn.

**Short mirror:** [`scripts/monthly_orb_restricted_stop_limit_cycle_short.py`](../../scripts/monthly_orb_restricted_stop_limit_cycle_short.py), reports at [`monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md`](monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md) and NQ mirror. The flipped short-only system is **not viable as-is**: MNQ **-$7,680 / -$23,710 DD / 0.92 PF**, NQ **-$99,092 / -$229,472 DD / 0.92 PF**. Stop-breakdowns and bottom refills were modestly positive, but the top-limit reclaim branch dominated losses.

Practical status: keep this as a promising long-side monthly ORB research branch. It is **not** a live-test candidate yet because the entries, stop invalidations, refills, and same-day sequencing are still daily-OHLC approximations. Next serious step is a 4h or 1m causal rebuild.

### Monthly ORB + weekly Supertrend (scalp + runner, long-only)

Research sim: **`scripts/monthly_orb_st_runner.py`** (weekly ATR Supertrend on daily, causal mapper). Two conceptual lots per qualifying monthly long: **scalp** follows the usual restricted OR exits; **runner** skips the range-close rule while weekly trend stays bullish and exits on monthly RL, weekly bearish flip, or restrictive settle when weekly is not confirming.

**Last batch CSV headline (re-run script for your data window):**

| Instrument | Combined net | $ / pt mult | Max DD (leg-exit equity) | Scalp exits | Runner exits |
|---|---:|---:|---:|---:|---:|
| MNQ | +40,871.75 pts | $2 | −$12,888 | 66 | 85 |
| NQ | +52,941.50 pts | $20 | −$128,705 | 138 | 179 |

Outputs: `mnq/mnq_monthly_orb_st_runner.csv`, `nq/nq_monthly_orb_st_runner.csv`.

### Monthly swing Fib + context charts

Yearly daily PNGs: **monthly fractal swing low → swing high**, default **61.8%** retracement from **H** toward **L** (`H − 0.618×(H−L)`), **green vertical** on the first daily session that trades through that price after pivot confirmation; **weekly Supertrend** stop overlaid; **Jan–Mar yearly OR** high/low for that calendar year. Builder: [`monthly_orb/build_monthly_fib_retrace_charts.py`](monthly_orb/build_monthly_fib_retrace_charts.py) → [`monthly_orb/fib_retrace_yearly/INDEX.md`](monthly_orb/fib_retrace_yearly/INDEX.md) (NQ mirror under `nq/case_studies/monthly_orb/fib_retrace_yearly/` when built with `--daily nq/nq_daily.csv`).

Current practical read: the old ATR weekly-primary leaderboard remains historical context only. The newer **StrategyPlugin signal replay** section above is the live-runtime ranking source for MNQ ATR. MYM/NQ/ES/MES still need equivalent plugin passes before they are used for funding decisions.

## Higher Timeframe ORB Candidate

**Yearly ORB scaleout3 with inside-range swing stop is still the core low-frequency ORB family, and the current broker-like leader branch is the OCO-stop entry + 20% range-close variant.**

- Rule family: Jan-Mar yearly ORB, Apr-Dec retest entries, stop source is the latest confirmed daily swing whose pivot candle is fully inside the yearly ORB, 3 units, Unit 1 off at 25% to TP, Unit 2 off at TP, runner stop to breakeven only after TP, and close remaining units on a daily close back inside the yearly range.
- Targeted broker-like hardening branch (2026-05): OCO stop entries at both yearly boundaries (`oco_stop` entry mode), same scaleout/inside-range swing stop stack, and close only after a daily close reaches **20% back inside** the yearly range (`range_close_inside_frac=0.20`).
- OCO 20% replay snapshot (post-2026-05-20 realism re-baseline, full-history broker-like run): **NQ $741,289 / -$141,210 / 5.25**, **ES $350,746 / -$86,333 / 4.06**, **YM $182,900 / -$63,598 / 2.88**, **MNQ $66,845 / -$14,141 / 4.73**, **MYM $12,098 / -$6,098 / 1.98**, **MES $9,878 / -$8,546 / 1.16**. The earlier targeted-run snapshot (`live/state/yearly_orb_range_close_20pct_test/SUMMARY.md`) is preserved for prior context but is no longer the headline number.

### Sizing sweep (2026-05-21) — front-loaded ladders beat the 1/1/1 baseline on every market

`yearly_orb_scaleout3` is now configurable per bucket (`tp25_qty` / `tp_qty` / `runner_qty`). 19 sizing combinations × 6 markets were run through the realism-baseline broker-like path. Full output: [`../../live/state/yearly_orb_sizing_sweep_all/SUMMARY.md`](../../live/state/yearly_orb_sizing_sweep_all/SUMMARY.md). Source code: `potions/live/yearly_orb_sizing_sweep.py`.

| Market | Best sizing | TP25 / TP / Runner | Total | Net | Stress DD | Net / DD | vs 1/1/1 baseline |
|---|---|---|---:|---:|---:|---:|---:|
| NQ  | `L_4_1_1` | 4 / 1 / 1 | 6 | $1,417,383 | -$128,766 | **11.01** | +3.04 vs 7.97 |
| ES  | `L_4_2_1` (user pick) | 4 / 2 / 1 | 7 |   $657,146 |  -$66,346 |  **9.90** | +1.76 vs 8.14 |
| MNQ | `L_4_1_1` | 4 / 1 / 1 | 6 |   $108,527 |  -$12,851 |  **8.45** | +2.08 vs 6.37 |
| YM  | `L_4_1_1` | 4 / 1 / 1 | 6 |   $515,736 |  -$67,525 |  **7.64** | +0.39 vs 7.25 |
| MYM | `L_4_1_1` | 4 / 1 / 1 | 6 |    $28,376 |   -$4,977 |  **5.70** | +1.84 vs 3.86 |
| MES | `O_1_1_1_rc20` | 1 / 1 / 1 (OCO + 20% range-close) | 3 |     $9,878 |   -$8,546 |  **1.16** | best of a weak market |

**Sizing read.** Front-loading the scale-out bucket dominates symmetric or back-loaded ladders on every futures market except MES (where every sizing has Net/Stress < 1.0 and the market is not viable for yearly ORB at this realism baseline). The user's `4 / 2 / 1` ladder is in the top-3 on five markets and is the **outright #1 on ES** ($657k / -$66k / 9.90). It also gives roughly **2× the net** of the 1/1/1 baseline on every market with no worse Net/Stress.

**Why front-loaded works.** The TP25 partial exit happens at 25% of the way to the full target, which is the most frequently hit level in the sample. Loading more contracts at TP25 captures more of the available edge per unit of stress, because the runner and TP buckets are the contracts that carry the worst intrabar adverse moves.

**Why the `4 / 1 / 1` rows top the leaderboard.** They keep the front-load big (4 contracts at TP25) but use only 1 contract each for TP and runner — minimising the contracts exposed to the worst intrabar adverse moves. `4 / 2 / 1` (the user's pick) gives up only ~0.5 Net/DD vs `4 / 1 / 1` but earns ~25% more absolute net because the TP bucket is doubled, so it is the more capital-efficient promotion candidate.

**Symmetric scaling is just a multiplier.** `1 / 1 / 1`, `2 / 2 / 2`, `3 / 3 / 3` produce identical Net/Stress ratios on every market (6.37 MNQ, 7.97 NQ, 8.14 ES, 7.25 YM, 3.86 MYM, 0.68 MES) — they're linear contract multiples of the same trade tape. Use total contracts as the capital knob, not the per-unit shape, if you want to preserve the risk profile.

**Range-close 20% degrades Net/Stress on every market** when applied on top of any sizing. The OCO-stop entry partly compensates but still trails the no-range-close limit-retest variant of the same sizing.

Recommended promotion candidate per market: **`L_4_2_1` (limit_retest, 4 / 2 / 1)** as the user-friendly default — it's the user's own pick, in the top-3 on 5 markets and #1 on ES, and gives ~2× the baseline's net with no worse Net/Stress. The `L_4_1_1` rows have higher Net/Stress on most markets, but only marginally and at the cost of meaningful TP and runner contribution.

- MNQ 2020-2025: **26 trades**, **$68,082 gross**, **-$3,026 DD**, **38.5%** win rate, **22.50 Net/DD**.
- NQ 2011-2025: **71 trades**, **$758,754 gross**, **-$30,210 DD**, **32.4%** win rate, **25.12 Net/DD**.
- Portfolio note: the current cross-market test to preserve is **1 MNQ unit + 4 MYM units**, where each unit is the full 3-contract scaleout ladder. That means **3 MNQ + 12 MYM**, with combined 2020-2025 net **$135,878**, closed DD **-$3,292**, and open-heat stress DD **-$6,239**. Details: `mnq/case_studies/yearly_orb_mnq_mym_portfolio/README.md`.
- Pine paper-test harness: `pine/yearly_orb_scaleout3_range_close.pine` (strategy only, no `request.security`; causal defaults: `calc_on_order_fills=false`). Optional weekly Supertrend line: `pine/yearly_orb_weekly_st_overlay.pine` on the same daily chart. Set **Contracts per scaleout batch = 1** for MNQ and **4** for MYM.
- One-page standalone MNQ capital/risk sheet: `mnq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/ONE_PAGE_RUNDOWN.md`.
- Read the study path and caveats here: `mnq/case_studies/YEARLY_ORB_RESEARCH_NOTES.md`.

## ATR Supertrend DCA Correction Notes

The old **ATR Supertrend DCA weekly-primary / 10 max / 3 initial / entry guard** promotion is paused. The following historical notes are retained for audit, but the figures that depended on weekly-primary ATR must be rerun after the weekly mapper fix before they are used for live sizing.

- Rule family: **long only**, completed weekly Supertrend-style **ATR(14) × 3** flip enters at the next available daily open, starts with **3 contracts**, adds **1 contract every 2 eligible Fridays at 15:50 ET**, max **10 contracts**, exits the stack at the next available daily open after the weekly ATR flips bearish.
- Initial-entry guard: if a daily close falls below the original first-entry price, flatten at the next daily open. If the completed weekly trend remains bullish, re-enter after a daily close back above that original entry guard and restart scaling.
- Legacy MNQ/NQ weekly-primary figures in older folders may have inherited the same daily/weekly ATR collision and should be treated as stale until rerun.
- Corrected MYM checks on 2026-05-08: causal daily/no-weekly-flat produced **$11,725 net / -$13,602 MTM DD**; actual completed-week ATR produced **$40,296 net / -$26,958 MTM DD**.
- Capitalization guideline for ATR is temporarily suspended: recalculate from corrected causal outputs, not the legacy weekly-primary tables.
- Charts show **solid daily ATR stops** and **dashed completed-week ATR stops** on the same yearly chart. The weekly-primary variant uses the dashed weekly layer as the actual trend engine; the daily layer is context.
- Study folders: `mnq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/README.md` and `nq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/README.md`. Conservative benchmark: `mnq/case_studies/atr_supertrend_dca_long_biweekly_5max_weekly_flat/README.md`.
- Sizing sensitivity: the **1,1,2,2,2, then 1s** ladder reduced heat but gave up upside. MNQ weekly-primary ladder: **$263,784 net**, **-$12,808 MTM DD**, **-$3,209 worst MAE**, **20.60 Net/MTM**. NQ weekly-primary ladder: **$3,044,840 net**, **-$128,200 MTM DD**, **-$32,030 worst MAE**, **23.75 Net/MTM**. It is a viable lower-heat alternative, but the **3-initial** version remains the promoted high-profit candidate because NQ confirmation is stronger.
- Yearly ORB alignment test: first long stacks/restarts were allowed only after a prior daily close above the Jan-Mar yearly ORB high; adds/exits stayed unchanged. This **did not beat the base ATR candidates**. MNQ weekly-primary 3-initial fell to **$93,640 net / -$11,207 MTM DD** from **$303,214 / -$16,524**; NQ weekly-primary 3-initial fell to **$1.36M / -$112k** from **$3.64M / -$123k**. The filter reduced MAE and trade count, but gave up too much trend participation. Study folders use the `_yorb` suffix, e.g. `mnq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial_yorb/README.md`.

| Code / folder | What it is | Tier‑1 entry | Exit / risk | Snapshot performance (MNQ NY, ~2021→)** |
|----------------|------------|--------------|-------------|-------------------------------------------|
| **step2 / `mnq_orb_results_stops.csv`** | README canon **v2b** | OCO **buy stop RH+tick** / **sell stop RL−tick** after OR; slip ticks; bracket TP **RH±Range**, stop **opposite boundary** | Bracket‑then‑reverse; max 2 legs/day; 15:55 cutoff | **~1,991 legs**, Σ Net **~+$15,877**, Max DD **~−$4,716** (see fresh CSV / validation.md) |
| **`open_limit/orb_open_limit_v2b.py` → `mnq_orb_open_limit.csv`** | Research fork (**not** README canon) | First **5 m close** beyond RH/RL; **limit @ 09:30 session open** after breakout bar | Same measured-move idea but **different fills** than OCO | Was used for early charts; **superseded** for canon comparisons by step2 |
| **`v2b_child/orb_open_limit_v2b_child.py`** | Canon **v2b tier‑1** + optional **child** scale‑ins | Same as step2 for tier‑1 | After OCO fill: up to **N** qualifying **5 m** “child” bars → limit @ bar **close**; **flat everyone** at same TP/SL | **max_child_adds=0** reproduces step2 exactly (**Σ Net $15,877**). **+1 add** Σ Net **~+$27,916**; **+2 adds** Σ Net **~+$34,269** (higher risk — deeper DD) — see `v2b_child/README.md` |
| **`v2b_c/`** (`build_case_studies.py`) | **Charts only** for v2b_child (**3‑contract cap** CSV by default) | — | Annotates tier‑1 OCO fill + add1/add2 limits | Batch PNGs + `INDEX.md`; rules identical to `v2b_child` |
| **`swept_liquidity_orb_breakout/resim_scale_in_ladder.py`** | Different playbook on **`mnq_swept_orb_breakout.csv`** legs | L0±15 scale + child candles; TP1‑only sim | Tier‑1 stop **L0±sl_pts**; child stops **RH−edge / RL+edge** | Full CSV replay **~−$573** cumulative Net with ladder defaults; **387** loss charts folder — **not** comparable $‑wise to step2 |
| **`v2d/mnq_orb_results_adaptive_50_150.csv`** | **Adaptive 50/150**: prior‑day **MA50 vs MA150** chooses **v2b vs v2d** per session | v2b arm = OCO breakout; v2d arm = fade per `validation.md` | Mixed | **~1,919 legs**, Σ Net **~+$18,885**, Max DD **~−$3,542** |
| **`v2d/benchmark_v2b_scaleout_candidates.py`** | **Long-priority scanner** for v2b-only scaleout on **1 m** (MA50>MA150 filter); useful diagnostic, not broker OCO | v2b breakout **RH+tick** / **RL−tick**; TP1/TP2 scaleout | Reproducible scanner headline: **1,302** legs, **+$83,245**, closed **−$2,730**, **MTM −$3,130** |
| **`v2d/paper_replay_v2b_scaleout_ordering.py`** | **Execution-ordering audit** for the v2b-only scaleout book | compares long-priority scanner vs Pine-like OCO vs strict long-first | Live/Pine parity OCO: **1,441** legs, **+$35,210**, closed **−$5,190**, **MTM −$5,482** |
| **`v2d/run_adaptive_50_150_scaleout.py`** | Stitched adaptive CSV replay (legacy) | v2b + v2d arms | v2b-only CSV snapshot: **1,430** legs, **+$35,847**, DD **−$5,190**; now best treated as close to the OCO parity row |
| **`v2d/orb_adaptive_50_150_child.py`** | **Unified combined sim:** same routing as rows above + **`v2b_child`** scale‑ins on **both** arms (v2d fade tier‑1 gets the same 5 m child logic as OCO tier‑1) | v2b: OCO + children; v2d: fade + children; shared TP/SL per leg | **`max_child_adds=0`** → **$18,885** / **1,919 legs** (matches stitched adaptive). **`=1`** Σ **~+$27,867**, DD **~−$5,424**. **`=2`** Σ **~+$30,940**, DD **~−$8,757** |
| **`potions/scripts/monthly_orb_restricted_scaleout3.py`** | **Monthly OR** (3 sessions) + range-close + **3-unit** TP25/TP/runner, **boundary** stop | Daily close breakout; retest **limit** at RH/RL; same FSM as 1-lot restricted | MNQ **~$105k** / **−$3.7k** closed DD / **−$6.4k** stress (see `monthly_orb/METRICS_SCALEOUT3.md`); NQ mirror | Daily OHLC; not Pine-parity checked; fees not in CSV |
| **`case_studies/v2b_m/`** | **Filtered research book:** tier‑1 CSV rows restricted to **Long**, **`bullish_break`**, prior‑month‑high OR geometry (`EPS_IDX_PT`) | Same tier‑1 **long** idea as canon on those rows | Stats via `run_v2b_m.py`; optional **2‑lot scale‑out** (**`v2b_m_so/`**): TP1 **RH+R**, runner SL **RH+tick**, TP2 **RH+2R** — **363** overlapping sessions default sample: baseline sim Σ **~+$3,795**, SO Σ **~+$9,418** (see **`v2b_m_so/README.md`** for full discrete rules) |
| **`mnq/v2e/`** (2026 London base) | **London sweep long only** — **no ORB**: ``stop_hunter`` vs **[02:00–09:30)** low → fractal **breaker** → **piercer** → limit pullback | Limit @ **breaker_high** | SL options **London_low / breaker_low / stop_hunter_low**; TP ``SH_low + 3×(piercer_high−SH_low)`` | **~250** setups / default 1 m span; Σ Net **negative** on current defaults — see **`mnq/v2e/README.md`** + ``scripts/backtest_london_sweep_breaker.py`` |

**Note:** Numbers drift slightly when DB end‑date moves; always re‑run the listed script and read CSV totals.

## Where to read full rules

| Topic | Path |
|-------|------|
| Monthly ORB restricted + **scaleout3** (daily sim + charts) | `mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED.md` · `potions/scripts/monthly_orb_restricted_scaleout3.py` |
| Canon v2 / v2b / v2d definitions | `potions/scripts/validation.md` |
| Portfolio README stats | `potions/README.md` |
| Swept ladder (child OR boundary stops, TP1) | `case_studies/swept_liquidity_orb_breakout/README.md` |
| v2b + child backtest (OCO tier‑1) | `case_studies/v2b_child/README.md` |
| v2b_c PNG workflow | `case_studies/v2b_c/README.md` |
| Adaptive **50/150 + children** (single simulator) | `mnq/v2d/orb_adaptive_50_150_child.py` |
| v2d regime **winners / losers** case PNGs | `case_studies/v2d_regime_case_studies/` (`build_v2d_winners_losers.py`) |
| **v2e London sweep (breaker / piercer)** | `mnq/v2e/README.md` |

## Adaptive 50/150 + **v2b_child**

- **Unified sim:** `mnq/v2d/orb_adaptive_50_150_child.py` runs **one** intraday path per session: prior‑day **MA50 vs MA150** selects **v2b OCO + children** or **v2d fade + children** (same 5 m RH/RL child rules and shared TP/SL as `orb_open_limit_v2b_child.py`). **`--max-child-adds 0`** reproduces stitched adaptive totals (**~$18,885** Σ Net on **1,919** legs on this DB snapshot).
- **CSV join (legacy / diagnostic):** `v2b_child/report_adaptive_v2bc.py` pastes **`Regime`** labels onto **`v2b_child`**‑only CSV legs — **different universe** than the unified sim; useful only if you understand overlap (**~224** child‑only keys vs adaptive). See `v2b_child/README.md`.
