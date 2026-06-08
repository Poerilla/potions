# Yearly ORB Research Notes

This note captures the path of the yearly ORB study so the current state is easy to recover later.

## Starting Point

The original yearly ORB model uses Jan-Mar as the opening range and trades Apr-Dec. A daily close outside the yearly range arms a retest entry, with target at one full range extension and stop at the opposite range boundary. The baseline result was attractive because it had very low trade count and held up on both MNQ and the longer NQ sample, but the opposing-boundary stop was capital heavy.

Baseline yearly ORB:

| Market | Sample | Trades | Win Rate | Net | Max DD |
|---|---:|---:|---:|---:|---:|
| MNQ | 2020-2025 | 7 | 85.7% | $23,326 | -$6,686 |
| NQ | 2011-2025 | 19 | 57.9% | $224,925 | -$66,860 |

## Swing Stop Unlimited

Next we replaced the opposing-boundary stop with the latest confirmed daily swing: long stop at the most recent confirmed swing low below entry, short stop at the most recent confirmed swing high above entry. We also allowed as many trades as the year provided.

This improved capital efficiency and reduced drawdown.

| Market | Trades | Win Rate | Net | Max DD | Net/DD | Avg MAE | Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 10 | 60.0% | $23,560 | -$3,120 | 7.55 | $1,218 | $4,038 |
| NQ | 35 | 34.3% | $227,715 | -$32,445 | 7.02 | $5,752 | $40,385 |

Charts:

- `mnq/case_studies/yearly_orb_swing_stop_unlimited/`
- `nq/case_studies/yearly_orb_swing_stop_unlimited/`

## Scaleout3 Boundary Entry

Then we tested 3 units on the same swing-stop structure:

- Unit 1 exits at 25% of the distance from entry to TP.
- Unit 2 exits at the full yearly ORB measured-move TP.
- Unit 3 is a runner.
- The runner stop moves to breakeven only after Unit 2 reaches TP.

Two management variants were tested:

- Runner: keep the runner until breakeven stop or period close.
- Range-close restricted: if a daily candle closes back inside the yearly ORB, close all remaining units, then allow re-entry on the next breakout.

Results:

| Variant | Market | Trades | Win Rate | Net | Max DD | Net/DD | Avg MAE | Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Boundary runner | MNQ | 10 | 60.0% | $62,944 | -$4,568 | 13.78 | $2,814 | $8,077 |
| Boundary range-close | MNQ | 26 | 38.5% | $55,368 | -$2,445 | 22.65 | $796 | $2,212 |
| Boundary runner | NQ | 33 | 39.4% | $631,970 | -$62,975 | 10.04 | $14,637 | $80,770 |
| Boundary range-close | NQ | 72 | 34.7% | $639,698 | -$24,495 | 26.12 | $4,695 | $22,065 |

Current read: boundary range-close is the strongest capital-efficiency candidate. It gives up win rate and trades more often, but it cuts drawdown sharply while preserving most of the large-trend upside.

Charts:

- `mnq/case_studies/yearly_orb_swing_stop_scaleout3_runner/`
- `mnq/case_studies/yearly_orb_swing_stop_scaleout3_range_close/`
- `nq/case_studies/yearly_orb_swing_stop_scaleout3_runner/`
- `nq/case_studies/yearly_orb_swing_stop_scaleout3_range_close/`

## Inside-Range Swing Stop Correction

We then corrected the stop-source definition. The intended swing stop is not just the latest confirmed swing anywhere on the chart. The stop-source swing must come from a pivot candle that is fully inside the Jan-Mar yearly ORB:

- pivot candle high <= yearly ORB high;
- pivot candle low >= yearly ORB low.

This was run as a separate study so the prior any-swing version remains available for comparison.

| Variant | Market | Trades | Win Rate | Net | Max DD | Net/DD | Avg MAE | Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Any swing range-close | MNQ | 26 | 38.5% | $55,368 | -$2,445 | 22.65 | $796 | $2,212 |
| Inside-range swing range-close | MNQ | 26 | 38.5% | $68,082 | -$3,026 | 22.50 | $796 | $2,212 |
| Any swing range-close | NQ | 72 | 34.7% | $639,698 | -$24,495 | 26.12 | $4,695 | $22,065 |
| Inside-range swing range-close | NQ | 71 | 32.4% | $758,754 | -$30,210 | 25.12 | $4,780 | $22,065 |

Read: the intended inside-range swing rule increases absolute PnL materially while keeping Net/DD close to the prior any-swing variant. It is a little less capital efficient by Net/DD, but it better matches the intended structure and improves total return on both MNQ and NQ.

Charts:

- `mnq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/`
- `nq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/`

## Breakout-Close Entry Test

We then tested whether moving the limit entry from the yearly range boundary to the breakout candle close would catch more strong breakouts without giving up too much capital. These orders are filled only on later daily candles, not the breakout confirmation candle.

This did not improve the system. Both runner and range-close versions were weaker than the boundary-entry versions.

| Variant | Market | Trades | Win Rate | Net | Max DD | Net/DD | Avg MAE | Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Close-entry runner | MNQ | 13 | 38.5% | $39,387 | -$5,003 | 7.87 | $2,777 | $8,463 |
| Close-entry range-close | MNQ | 26 | 23.1% | $36,950 | -$4,814 | 7.68 | $1,434 | $5,378 |
| Close-entry runner | NQ | 41 | 34.1% | $381,366 | -$62,100 | 6.14 | $14,738 | $84,750 |
| Close-entry range-close | NQ | 74 | 23.0% | $403,181 | -$48,060 | 8.39 | $7,862 | $53,580 |

Conclusion: the breakout-close limit did not juice the results. It increased adverse selection: it buys/sells closer to the target with less reward left, while still accepting large swing-stop risk.

Charts:

- `mnq/case_studies/yearly_orb_swing_stop_scaleout3_close_entry_runner/`
- `mnq/case_studies/yearly_orb_swing_stop_scaleout3_close_entry_range_close/`
- `nq/case_studies/yearly_orb_swing_stop_scaleout3_close_entry_runner/`
- `nq/case_studies/yearly_orb_swing_stop_scaleout3_close_entry_range_close/`

## Repeated Outside Next-Open Trail Study (Archived)

We tested a higher-turnover yearly ORB scalp/trailing idea:

- wait for a daily close outside the yearly ORB;
- enter 1 unit at the next daily open;
- requested research stop: the entry-day low/high becomes the initial stop after that day completes;
- then trail using the prior daily low for longs and prior daily high for shorts, without loosening;
- unlimited trades per year.

Results:

| Market | Sample | Trades | Win Rate | Net | Max DD | Net/DD | Avg MAE | Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 2020-2025 | 338 | 40.5% | $28,796 | -$4,971 | 5.79 | $438 | $3,249 |
| NQ | 2011-2025 | 726 | 38.8% | $326,215 | -$48,935 | 6.67 | $2,613 | $32,460 |

Read: viable as a research signal, but not currently better than the scaleout3 boundary range-close family. It has many more trades and the requested initial stop is not live-causal because the entry-day low/high is not known at the entry open. It was also not the intended rule; it repeatedly re-entered while price remained outside the yearly range.

Files:

- `scripts/yearly_orb_next_open_trail.py`
- `mnq/mnq_yearly_orb_repeated_outside_next_open_trail.csv`
- `nq/nq_yearly_orb_repeated_outside_next_open_trail.csv`
- `mnq/case_studies/yearly_orb_repeated_outside_next_open_trail/`
- `nq/case_studies/yearly_orb_repeated_outside_next_open_trail/`

## Fresh Breakout-Open Retest Trail Study

We then corrected the scalp idea to match the intended rule:

- wait for a fresh daily close outside the yearly ORB;
- place one retest limit at that breakout candle's open;
- use the breakout candle low as the long stop and breakout candle high as the short stop;
- after fill, trail using the prior daily low/high without loosening;
- do not place repeated orders while price remains outside the yearly range;
- wait for price to reset and create another fresh breakout candle before considering another order.

Results:

| Market | Sample | Trades | Win Rate | Net | Max DD | Net/DD | Avg MAE | Worst MAE |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 2020-2025 | 11 | 18.2% | $604 | -$952 | 0.63 | $320 | $718 |
| NQ | 2011-2025 | 42 | 2.4% | -$3,620 | -$16,285 | -0.22 | $1,536 | $7,175 |

Read: not viable as written. The corrected version greatly reduces trade count, but the breakout-candle open entry plus breakout-candle low/high stop mostly creates small stop-outs. MNQ only stays positive because one 2025 short offsets the losses; the longer NQ sample rejects the structure.

Files:

- `scripts/yearly_orb_next_open_trail.py`
- `mnq/mnq_yearly_orb_next_open_trail.csv`
- `nq/nq_yearly_orb_next_open_trail.csv`
- `mnq/case_studies/yearly_orb_next_open_trail/`
- `nq/case_studies/yearly_orb_next_open_trail/`

## Next-Day 5-Minute Level Inspection Charts

To study whether the yearly ORB boundary is visually meaningful for intraday scalps, we generated 00:00-16:00 ET 5-minute charts for the session after every daily candle that:

- opened inside the Jan-Mar yearly ORB;
- closed outside the yearly ORB;
- used the upper yearly boundary for bullish breaks and the lower yearly boundary for bearish breaks.

These charts are observational only. They do not score a trade. The goal is to inspect midnight-to-close next-session behavior around the yearly boundary and decide whether a more causal intraday scalp rule is worth modeling.

Generated set:

| Market | Sample | Charts | Bullish | Bearish | Missing |
|---|---:|---:|---:|---:|---:|
| MNQ | 2020-2025 | 26 | 17 | 9 | 0 |
| NQ | 2011-2025 | 69 | 52 | 17 | 0 |

Files:

- `scripts/yearly_orb_next_day_5m_charts.py`
- `mnq/case_studies/yearly_orb_next_day_5m/`
- `nq/case_studies/yearly_orb_next_day_5m/`
- `mnq/case_studies/yearly_orb_next_day_5m.csv`
- `nq/case_studies/yearly_orb_next_day_5m.csv`

## Breakout Day + Five-Day 1-Hour Context Charts

We then zoomed the same observational chart study out from next-day 5-minute candles to multi-day 1-hour context:

- same signal definition as the next-day 5-minute study;
- daily candle must open inside the Jan-Mar yearly ORB and close outside it;
- chart includes the breakout date plus the next five weekday trading dates;
- each included date plots 00:00-23:59 ET, resampled from 1-minute data to 1-hour candles, so the evening/Asian session is included through the 23:00 candle;
- only the relevant yearly ORB boundary is shown: high for bullish breaks, low for bearish breaks;
- yellow X marks the last plotted hourly candle on the breakout date.

Generated set:

| Market | Sample | Charts | Bullish | Bearish | Missing |
|---|---:|---:|---:|---:|---:|
| MNQ | 2020-2025 | 26 | 17 | 9 | 0 |
| NQ | 2011-2025 | 69 | 52 | 17 | 0 |

Files:

- `scripts/yearly_orb_breakout_1h_context_charts.py`
- `mnq/case_studies/yearly_orb_breakout_1h_context/`
- `nq/case_studies/yearly_orb_breakout_1h_context/`
- `mnq/case_studies/yearly_orb_breakout_1h_context.csv`
- `nq/case_studies/yearly_orb_breakout_1h_context.csv`

## Yearly ORB Bias Filter On v2b-Only Scaleout

We tested whether the current adaptive 50/150 v2b-only scaleout winner improves if it trades only when the prior trading day was outside the yearly ORB and the v2b leg aligns with that yearly breakout direction.

Primary filter:

- prior day traded above yearly OR high -> allow only Long v2b legs;
- prior day traded below yearly OR low -> allow only Short v2b legs;
- prior day traded both sides -> skip as ambiguous;
- entries/exits remain the existing v2b-only scaleout fills.

Result:

| Market | Variant | Legs | Net | Trade DD | Win Rate | PF |
|---|---|---:|---:|---:|---:|---:|
| MNQ | Baseline v2b-only scaleout | 1,430 | $35,847 | -$5,190 | 55.0% | 1.19 |
| MNQ | Yearly aligned | 465 | $12,672 | -$4,362 | 55.7% | 1.24 |
| NQ | Baseline v2b-only scaleout | 4,739 | $414,773 | -$100,010 | 51.9% | 1.13 |
| NQ | Yearly aligned | 1,358 | $118,911 | -$40,966 | 51.8% | 1.13 |

Read: not an upgrade. The filter reduces drawdown, but it removes too much of the book and barely changes win rate or profit factor. The no-direction version is more interesting than the aligned version, but still does not clearly beat the simple baseline.

Files:

- `scripts/filter_v2b_scaleout_yearly_orb_bias.py`
- `mnq/case_studies/yearly_orb_v2b_bias_filter/`

## ES And Dow-Family Cross-Market Run

We ran the current yearly candidate, `yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close`, on ES and the available Dow-family data.

| Market | Data Source | Sample | Trades | Win Rate | Net | Max DD |
|---|---|---:|---:|---:|---:|---:|
| ES | ES daily CSV | 2011-2025 | 81 | 33.3% | $441,669 | -$27,525 |
| YM-equivalent | MYM-derived daily CSV | 2020-2025 | 30 | 56.7% | $169,491 | -$12,185 |
| MYM actual | MYM-derived daily CSV | 2020-2025 | 30 | 56.7% | $16,949 | -$1,218 |

Read: ES confirms the broad higher-timeframe thesis over a longer sample, but with a lower win rate and more churn. The Dow-family result is smoother, but the available repo data is MYM starting in 2019, so the YM line is a YM-dollar-equivalent view of MYM price history.

Files:

- `es/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/`
- `mym/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/`
- `mnq/case_studies/yearly_orb_cross_market_scaleout3_inside_range_summary.md`

## MNQ + MYM Portfolio Sizing Note

The smoothest practical combination found so far is **1 MNQ unit + 4 MYM units** on the same yearly ORB scaleout3 / inside-range swing / range-close rule.

Important sizing definition:

- 1 MNQ unit = the full 3-contract ladder, or 3 MNQ contracts.
- 1 MYM unit = the full 3-contract ladder, or 3 MYM contracts.
- 1 MNQ unit + 4 MYM units = **3 MNQ + 12 MYM**, scaled out as MNQ 1/1/1 and MYM 4/4/4.

Overlap sample, 2020-2025:

| Book | Trades | Win Rate | Net | Closed DD | Open-Heat Stress DD | Worst Trade MAE |
|---|---:|---:|---:|---:|---:|---:|
| 1 MNQ unit | 26 | 38.5% | $68,082 | -$3,026 | n/a | $2,212 |
| 4 MYM units | 30 | 56.7% | $67,796 | -$4,874 | n/a | $3,360 |
| Combined | 56 | 48.2% | $135,878 | -$3,292 | -$6,239 | $3,360 |

Read: the combo almost doubles the MNQ-only net while historical closed drawdown rises only slightly. The more realistic number to respect is the open-heat stress drawdown, not just closed DD. This supports MYM as a possible diversifier for the MNQ yearly ORB book, but the MYM sample is shorter than NQ/ES.

Files:

- `mnq/case_studies/yearly_orb_mnq_mym_portfolio/README.md`
- `mnq/case_studies/yearly_orb_mnq_mym_portfolio/mnq1_mym4_trades.csv`
- `mnq/case_studies/yearly_orb_mnq_mym_portfolio/mnq1_mym4_daily_stress_equity.csv`
- Pine sizing harness: `pine/yearly_orb_scaleout3_range_close.pine`

## Current Candidate

Best current yearly ORB candidate: **Scaleout3 boundary range-close with inside-range swing stop**.

Why:

- It matches the intended stop-source rule better than the any-swing version.
- It materially increases total PnL on both MNQ and NQ while keeping Net/DD near the prior capital-efficiency leader.
- NQ confirms it over a larger 2011-2025 sample.
- It has much lower mechanical burden than the intraday adaptive v2b family.
- It appears more capital-efficient than the high-trade-count systems, especially after allowing for fees, slippage, missed fills, and operational errors.

Runner-only is still worth keeping as the simpler, lower-trade-count version. It has higher drawdown than range-close but fewer decisions and less re-entry churn.

## Important Caveat

The boundary-entry studies inherit the daily ORB fill convention: a breakout candle can close outside the range and still be treated as filled at the boundary during that same daily candle if the candle traded through the boundary. That is useful research, but not fully live-equivalent because a live strategy only knows the breakout close after the daily bar closes.

Before this becomes a live/paper candidate, rerun the best boundary-entry variants with strict next-bar order placement:

- daily close outside yearly ORB confirms breakout;
- boundary limit becomes live only on the next daily candle;
- no same-confirmation-candle fills;
- cancel or skip stale orders if the fixed TP was already touched before the limit filled.

The breakout-close tests already use strict subsequent-candle fills, but they performed worse. The next test should therefore be strict-next-bar boundary entry, not close-entry.

## Files

- Summary CSV: `mnq/case_studies/yearly_orb_research_summary.csv`
- Intended-rule trade report: `mnq/case_studies/yearly_orb_scaleout3_inside_range_swing_trade_report.md`
- Inside-range swing comparison: `mnq/case_studies/yearly_orb_inside_range_swing_comparison.csv`
- Main script: `scripts/yearly_orb_swing_stop_scaleout3.py`
- Swing-stop 1-unit script: `scripts/yearly_orb_swing_stop_unlimited.py`
