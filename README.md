# Potions - Futures, ORB, and ETF Strategy Research

This workspace is the research and replay lab for the MNQ/NQ ORB family,
cross-market futures systems, and ETF accumulation studies. The detailed source
of truth is the strategy tracker:

- Main tracker: [`mnq/case_studies/STRATEGY_TRACKER.md`](mnq/case_studies/STRATEGY_TRACKER.md)
- Fair capital benchmark: [`mnq/case_studies/fair_benchmark_comparison/TOP_STRATS.md`](mnq/case_studies/fair_benchmark_comparison/TOP_STRATS.md)
- Broker realism notes: [`live/CHANGE_LOG.md`](live/CHANGE_LOG.md)
- Start-small execution plan: [`live/specs/START_SMALL_BROKER_EXECUTION_PLAN.md`](live/specs/START_SMALL_BROKER_EXECUTION_PLAN.md)
- FX Monday OR research (2026-07-21): [`live/state/eurusd_monday_or_breakout_15m/RESEARCH.md`](live/state/eurusd_monday_or_breakout_15m/RESEARCH.md) · family [`…/MONDAY_ORB_FAMILY.md`](live/state/eurusd_monday_or_breakout_15m/MONDAY_ORB_FAMILY.md) · broker sizing [`live/state/monday_or_sizing_sweep_broker/INDEX.md`](live/state/monday_or_sizing_sweep_broker/INDEX.md) · pre-sweep cross-pair [`live/state/fx_monday_or_breakout_broker/SUMMARY.md`](live/state/fx_monday_or_breakout_broker/SUMMARY.md)

## Current Status

**Production-canonical ORB plumbing remains `scripts/step2_preplaced_stops.py`.**
It is the original OCO stop-entry model: place buy-stop/sell-stop around the
opening range, OCO the unfilled peer, bracket the fill, optionally reverse after
the first campaign exits, and flatten near the end of session. Keep this as the
reference implementation for the simple ORB execution lifecycle.

**Research ranking has moved beyond the old v2b headline.** The old MNQ
adaptive v2b `$83k` scanner result is now treated as a diagnostic because it was
long-priority ordering, not a broker/Pine OCO book. Current ranking uses strict
`StrategyPlugin`/`Engine`/`PaperBroker` replays with the 2026-05-20 realism
baseline.

**First live/paper plumbing target is small on purpose:** MNQ v2b TP1-only
`1/0/0`, max one open unit. It is not the highest-return row; its job is to
prove cloud runtime, live 1m feed, 5m OR state, OCO order lifecycle, fill
reconciliation, and EOD flattening before larger v2b or higher-timeframe systems
are funded.

## Live Replay System

The current automation-runtime standard is the flat-file live replay path:

- `live/strategies/`: strategy plugins emit orders only after confirming bars
  are complete.
- `live/engine.py` / `Engine`: feeds historical bars, persists strategy state,
  and routes orders.
- `live/paper_broker.py` / `PaperBroker`: applies broker-like fills, OCO
  collapse, slippage, fees, gap-through stop logic, and intrabar stress
  projection.
- `live/state/`: replay outputs, summaries, unit tapes, audits, and chart packs.

The 2026-05-20 realism baseline used by the current ranked tables:

- 1-tick adverse slippage on market and stop fills.
- Gapped-through stops fill at the worse of stop or bar open.
- Stops are evaluated before limits in same-bar ambiguity.
- `$1.50` fee per closed unit in audit rows.
- OCO peers are collapsed in risk projection.

## Ranking Sources

Use these layers in order:

1. **Strict delayed-arming prior-opposed ST+PMC -> v2b gate**: NQ flagship is now
   the **resting-limit** variant (arm when opposite ST limit is posted). Legacy
   hourly fill-stamp rows are diagnostic. Keep separate until tick reconstruction
   resolves same-minute/pre-arm-touch questions.
2. **Max 3x-stress normalized benchmark**: exact apples-to-apples capital math
   from `TOP_STRATS.md`.
3. **Generated broker-like replay table**: standard `StrategyPlugin` rows after
   realism, excluding the separate prior-opposed family.
4. **Research/artifact studies**: useful for ideas, sizing, and chart review,
   but not promotion rows unless rebuilt through the plugin/broker path.

## Strict Prior-Opposed Gate Ranking

**NQ promotion semantics (2026-07-16):** arm v2b after the same-session opposite
ST+PMC entry limit is **knowably resting at hour-complete** (`live_after + 1h`).
Left-label resting-limit and hourly fill stamps are diagnostic. Early-sleeve PnL
is recovered by delaying arm (~60m); median entry delay is 0.
[`early_pnl_recovery`](live/state/nq_v2b_prior_opposed_causal_proxies/early_pnl_recovery/INDEX.md).
Proxy comparison:
[`live/state/nq_v2b_prior_opposed_causal_proxies/INDEX.md`](live/state/nq_v2b_prior_opposed_causal_proxies/INDEX.md).

| Rank | Market / gate | Campaigns | Units | Net | Stress DD (MTM) | Net/Stress | Output |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | **NQ resting-limit hour-complete** | 432 | 2,160 | **$1,330,920** | **-$68,610** | **19.40** | [`causal_proxies/resting_limit`](live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md) |
| 2 | **MNQ resting-limit hour-complete** | 428 | 2,140 | **$128,360** | **-$6,960** | **18.44** | [`mnq_..._resting_limit`](live/state/mnq_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) |
| 3 | **YM resting-limit hour-complete** | 436 | 2,180 | **$289,225** | **-$33,894** | **8.53** | [`ym_..._resting_limit`](live/state/ym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) |
| 4 | **MYM resting-limit hour-complete** | 423 | 2,115 | **$22,101** | **-$3,417** | **6.47** | [`mym_..._resting_limit`](live/state/mym_v2b_prior_opposed_stpmc_resting_limit/INDEX.md) |
| — | ES resting-limit | — | — | — | — | — | **blocked** (ES 1m DBN missing); legacy fill [`es_..._broker_like`](live/state/es_v2b_prior_opposed_stpmc_broker_like/INDEX.md) |
| — | NQ left-label / fill-stamp diagnostics | — | — | — | — | — | See [`causal_proxies/INDEX`](live/state/nq_v2b_prior_opposed_causal_proxies/INDEX.md) |

Cross-market: [`live/state/v2b_prior_opposed_resting_limit_cross_market/INDEX.md`](live/state/v2b_prior_opposed_resting_limit_cross_market/INDEX.md).
NQ lookahead re-review: **SOLID** ([`LOOKAHEAD_REVIEW.md`](live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/LOOKAHEAD_REVIEW.md)).

Execution scrutiny on the **legacy fill-stamp** family still needs a refresh on hour-complete books before live funding.

## Capital-Normalized Ranking

The fair benchmark now uses the largest 3x-stress requirement in the selected
set as the common starting capital. Current anchor: **$927,206**, set by NQ ATR
daily 3-initial 10-max. Fractional books are allowed here because this is
comparison math, not an executable order plan.

| Rank | Strategy | Scale | Scaled Net | Return | Stress DD | Net/DD | Note |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | NQ v2b prior-opposed **resting-limit hour-complete** | — | — | — | — | **19.40** | Use [`causal_proxies/resting_limit`](live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/INDEX.md); rebuild TOP_STRATS scaled row before allocator use. |
| 1b | NQ v2b prior-opposed (legacy hourly fill) | 5.74x | $6,799,226 | 733.3% | -$309,068 | **22.00** | **Inflated diagnostic** — do not promote. |
| 2 | ES Yearly ORB scaleout3 | 7.65x | $2,514,650 | 271.2% | -$309,068 | **8.14** |
| 3 | NQ Yearly ORB scaleout3 | 2.90x | $2,462,568 | 265.6% | -$309,068 | **7.97** |
| 4 | YM Yearly ORB scaleout3 | 7.76x | $2,241,789 | 241.8% | -$309,068 | **7.25** |
| 5 | MNQ Yearly ORB scaleout3 | 28.97x | $1,968,204 | 212.3% | -$309,068 | **6.37** |
| 6 | NQ ATR daily ladder 1/1/2/2/2 10-max | 1.21x | $1,898,416 | 204.7% | -$309,068 | **6.14** |
| 7 | MNQ ATR daily ladder 1/1/2/2/2 10-max | 12.07x | $1,772,528 | 191.2% | -$309,068 | **5.74** |
| 8 | NQ ATR daily 3-initial 10-max | 1.00x | $1,717,280 | 185.2% | -$309,068 | **5.56** |
| 9 | MNQ ATR daily 3-initial 10-max | 10.53x | $1,682,936 | 181.5% | -$309,068 | **5.45** |

Practical `$1,000,000` whole-book ranking is also in
[`TOP_STRATS.md`](mnq/case_studies/fair_benchmark_comparison/TOP_STRATS.md).
At `$1M`, the legacy NQ prior-opposed fill-stamp row still leads the frozen
table (6 books / `$7,107,510` / 22.00 Net/DD) but that scaled figure is
**timestamp-inflated**; rebuild from resting-limit before allocation.

## Broker-Like Replay Leaders

Generated `broker_like_replays` rows after the 2026-05-20 realism baseline,
excluding the separate prior-opposed family:

| Rank | Candidate | Market | Net | Stress DD | Max Units | Net/Stress |
|---:|---|---|---:|---:|---:|---:|
| 1 | Yearly ORB scaleout3 | ES | $328,728 | -$40,403 | 3 | **8.14** |
| 2 | Yearly ORB scaleout3 | NQ | $850,314 | -$106,720 | 3 | **7.97** |
| 3 | Yearly ORB scaleout3 | YM | $288,757 | -$39,810 | 3 | **7.25** |
| 4 | Yearly ORB scaleout3 | MNQ | $67,942 | -$10,669 | 3 | **6.37** |
| 5 | ATR daily ladder 1/1/2/2/2 10-max | NQ | $1,572,142 | -$255,950 | 10 | **6.14** |
| 6 | Hourly ST + PMC 25/75 3R | NQ | $144,521 | -$24,635 | 1 | **5.87** |
| 7 | ATR daily ladder 1/1/2/2/2 10-max | MNQ | $146,875 | -$25,610 | 10 | **5.74** |
| 8 | YM hourly ST + PMC prior-bull gate | YM | $38,828 | -$6,974 | 1 | **5.57** |
| 9 | ATR daily 3-initial 10-max | NQ | $1,717,281 | -$309,069 | 10 | **5.56** |
| 10 | ATR daily 3-initial 10-max | MNQ | $159,819 | -$29,351 | 10 | **5.45** |

Full generated table:
[`live/state/broker_like_replays/SUMMARY.md`](live/state/broker_like_replays/SUMMARY.md).

## Instrument Read

| Instrument | Current read |
|---|---|
| MNQ | First live plumbing target is v2b TP1-only `1/0/0`. Strong research rows include prior-opposed v2b (**$113,548 / -$5,418 / 20.96**), yearly ORB (**$67,942 / -$10,669 / 6.37**), and ATR daily ladder (**$146,875 / -$25,610 / 5.74**). |
| NQ | Strongest overall market. Prior-opposed v2b is the top row (**$1.18M / -$53.8k / 22.00**). Yearly ORB, v2b `S_1_1_3`, ATR daily, and hourly ST+PMC all confirm, but stress is much larger than MNQ. |
| ES | Best generated broker-like yearly ORB row (**$328,728 / -$40,403 / 8.14**) and strict prior-opposed confirmation (**$348,688 / -$33,164 / 10.51**). Monthly overlap and raw v2b weakened sharply under stop gap-through realism. |
| YM | Prior-opposed confirms (**$320,190 / -$26,835 / 11.93**) and yearly ORB is strong (**$288,757 / -$39,810 / 7.25**). Plain v2b remains weak under realism. |
| MYM | Prior-opposed is the best micro Dow expression (**$26,054 / -$2,665 / 9.78**). Yearly ORB is modest but positive; old MYM ATR weekly-primary promotion is revoked because of the daily/weekly ATR mapper bug. |
| MES | Partial coverage and generally weak. MES has some positive WO-gap and ATR-weekly rows, but yearly ORB and monthly/overlap rows are not promotion-grade under current data. |
| QQQ / ETFs | QQQ monthly DCA, yearly ORB, RSI timing, OBV, market-structure, 2-month-low sidecars, DJD, BTCC, AMZN, DIA, SHOP, and GOOGL studies live mostly under `nq/case_studies/`. QQQ DCA is a serious passive benchmark, but top futures rows beat it under the max-stress normalized comparison. |

## Research Families

### V2B ORB

- Canonical OCO stop-entry implementation: `scripts/step2_preplaced_stops.py`
- Mature intraday plugin: `live/strategies/v2b_scaleout.py`
- All-day best sizing: NQ/MNQ `S_1_1_3` back-loaded runner variant.
- First live-plumbing target: MNQ `1/0/0`, TP1 only, max one open unit.
- Prior-opposed gate: strongest research family, but still tick-confirmation
  required before live funding.

Key outputs:

- [`live/state/v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md`](live/state/v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md)
- [`live/state/v2b_sizing_sweep/SUMMARY.md`](live/state/v2b_sizing_sweep/SUMMARY.md)
- [`live/state/v2b_tp1_only_quick_study/MNQ_1_0_0_STATS.md`](live/state/v2b_tp1_only_quick_study/MNQ_1_0_0_STATS.md)

### Yearly ORB

The current generated broker-like leader family. Rule family: Jan-Mar yearly
range, Apr-Dec entries, scaleout3 exits, inside-range swing stop, and realism
baseline fills.

Best generated rows: ES 8.14, NQ 7.97, YM 7.25, MNQ 6.37 Net/Stress. Sizing
sweep shows front-loaded ladders dominate; `L_4_2_1` is the user-friendly
promotion shape, while `L_4_1_1` often wins pure efficiency.

Key outputs:

- [`live/state/yearly_orb_sizing_sweep_all/SUMMARY.md`](live/state/yearly_orb_sizing_sweep_all/SUMMARY.md)
- [`live/state/yearly_orb_range_close_20pct_test/SUMMARY.md`](live/state/yearly_orb_range_close_20pct_test/SUMMARY.md)
- [`mnq/case_studies/YEARLY_ORB_RESEARCH_NOTES.md`](mnq/case_studies/YEARLY_ORB_RESEARCH_NOTES.md)

### ATR Supertrend / DCA

Daily ATR rows remain strong on MNQ/NQ in broker-like replay, especially the
ladder `1/1/2/2/2` 10-max variant. Weekly ATR rows are retained but generally
carry more heat. The old MYM weekly-primary promotion is revoked because the
local weekly mapper had been resolving daily ATR columns.

Key files:

- [`pine/atr_supertrend_dca_10max_entry_guard_3initial.pine`](pine/atr_supertrend_dca_10max_entry_guard_3initial.pine)
- [`mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/README.md`](mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/README.md)
- [`mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/README.md`](mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/README.md)

### Hourly ST + Prior-Month Close

True plugin sweep across MNQ, NQ, ES, MES, MYM, and YM. NQ 25/75 3R is the
strongest expression (**$144,521 / -$24,635 / 5.87**). YM has useful variants
with prior-bull gate and 40/120 3R. MYM base 50/150 is surprisingly efficient
but small.

Key outputs:

- [`live/state/hourly_st_pmc_strategyplugin_variants_cross_market/SUMMARY.md`](live/state/hourly_st_pmc_strategyplugin_variants_cross_market/SUMMARY.md)
- [`live/state/hourly_st_pmc_strategyplugin_variants/SUMMARY.md`](live/state/hourly_st_pmc_strategyplugin_variants/SUMMARY.md)

### Monthly ORB / Overlap / Boundary Stops

Monthly restricted and boundary-stop variants were demoted hard by stop
gap-through realism. Monthly overlap daily-ST retest x5 still has meaningful
NQ/MNQ rows but no longer leads. Treat these as research branches until rebuilt
with tighter intraday sequencing and a better stop model.

Key outputs:

- [`live/state/monthly_overlap_st_retest_broker_like/SUMMARY.md`](live/state/monthly_overlap_st_retest_broker_like/SUMMARY.md)
- [`mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED.md`](mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED.md)
- [`mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md`](mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md)

### WO Gap Reversal

Weekly 1h gap-reversal plugin. Positive on ES, NQ, MES, and MNQ, but below
yearly ORB, ATR daily, and prior-opposed v2b. Best row: ES
`$120,647 / -$45,687 / 2.64`.

Key output:
[`live/state/wo_gap_reversal_broker_like/INDEX.md`](live/state/wo_gap_reversal_broker_like/INDEX.md)

### ETF / Passive / Stock Accumulation

ETF work is kept in this repo because QQQ/SPY/DIA are the passive benchmark for
futures capital efficiency. Main conclusions:

- QQQ monthly DCA is a serious passive baseline, but not the top strategy under
  max-stress normalized futures comparison.
- QQQ yearly ORB is useful as an ETF timing sleeve; DCA-core + stop-breakout
  cash sweep is the highest-net QQQ yearly-ORB hybrid in that study.
- OBV bearish-cross timing generally trims heat but does not beat blind monthly
  DCA.
- 2-month-low signals work better as **extra cash sidecars** than as DCA
  replacements.
- GOOGL monthly RSI70 deferral is a real research candidate; GOOGL/QQQ 70/30
  monthly-DCA + LHLL-RSI<50 bulk improves on combined signal rows but still does
  not beat plain monthly DCA.

Key outputs:

- [`nq/case_studies/qqq_yearly_orb_study/INDEX.md`](nq/case_studies/qqq_yearly_orb_study/INDEX.md)
- [`nq/case_studies/qqq_smoothed_rsi_reliability/INDEX.md`](nq/case_studies/qqq_smoothed_rsi_reliability/INDEX.md)
- [`nq/case_studies/qqq_sliding_2m_low_limit_dca_study/EXTRA_500_OVERLAY.md`](nq/case_studies/qqq_sliding_2m_low_limit_dca_study/EXTRA_500_OVERLAY.md)
- [`nq/case_studies/googl_qqq_weekly_rsi50_cash_regime_study/INDEX.md`](nq/case_studies/googl_qqq_weekly_rsi50_cash_regime_study/INDEX.md)
- [`nq/case_studies/top_index_obv_yearly_rotation/YEARLY_ROTATION.md`](nq/case_studies/top_index_obv_yearly_rotation/YEARLY_ROTATION.md)

## Folder Map

| Path | Contents |
|---|---|
| `scripts/` | Research builders, legacy ORB scripts, ETF studies, chart builders. |
| `live/` | StrategyPlugin runtime, engine, paper broker, replay drivers, state outputs. |
| `mnq/` | MNQ source data, case studies, strategy tracker, v2d/v2e branches. |
| `nq/` | NQ futures studies plus most QQQ/ETF/GOOGL research outputs. |
| `es/`, `ym/`, `mym/`, `mes/` | Cross-market futures data and case-study outputs. |
| `pine/` | TradingView paper-test and parity scripts. |
| `combined_orb/`, `orb-portfolio/` | Older multi-session portfolio research. |
| `archived/` | Historical v1/v1b scripts and stale artifacts retained for audit. |

## Common Commands

```bash
# Original canonical OCO stop-entry ORB backtest.
python scripts/step2_preplaced_stops.py --product MNQ
python scripts/step2_preplaced_stops.py --product MYM

# Current fair capital benchmark.
python scripts/top_strat_fair_benchmark.py

# Current GOOGL/QQQ RSI50 cash-regime and 70/30 hybrid study.
python scripts/googl_qqq_weekly_rsi50_cash_regime_study.py
```

For current promotion decisions, read
[`mnq/case_studies/STRATEGY_TRACKER.md`](mnq/case_studies/STRATEGY_TRACKER.md)
before using any older README inside a case-study folder. Many older folders
preserve pre-realism or artifact results for audit only.
