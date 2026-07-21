# EURUSD Forex Intraday Baseline (promoted)

**Status:** Promoted FX intraday sleeve (2026-07-17)  
**Strategy ID:** `eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior`  
**Family:** Hourly ST + PMC retest · 25/75 3R · `ma_filter=bull_prior_only`

| | |
|---|---|
| Net | **$23,533.68** |
| Stress DD | **−$15,745.46** |
| Net / Stress | **1.49** |
| Trades / WR | **1,148 / 27.4%** |
| Daily Sharpe (full sample) | **0.29** |
| Causal verdict | **PASS** |

## Pack contents

- [`ONE_PAGE_PITCH.md`](ONE_PAGE_PITCH.md) — allocator one-pager
- [`CAUSAL_CHECK.md`](CAUSAL_CHECK.md) — lookahead / fill-lag audit
- [`YEARLY_PERFORMANCE.md`](YEARLY_PERFORMANCE.md) — calendar year table
- `yearly_performance.csv` / `yearly_macro_join.csv` / `macro_correlation.json`
- `headline.json` / `causal_check.json`

## Source replay

- States: `../eurusd_overnight_sweep/st_pmc/states/eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior/`
- Audit: `../eurusd_overnight_sweep/st_pmc/audits/eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior/`
- Sample charts: `../eurusd_overnight_sweep/st_pmc/charts/eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior/`

## Macro read

| Pairing | Correlation |
|---|---:|
| Yearly PnL vs Fed funds level (FRED RIFSPFFNA) | **0.11** |
| Yearly PnL vs Fed funds YoY change | **−0.47** |
| Yearly PnL vs EURUSD yearly return | **0.24** |
| Yearly PnL vs USD strength (−EURUSD) | **−0.24** |

Not a carry / rates book; weak link to broad USD direction.

## Related FX intraday challenger (2026-07-20)

**Monday OR breakout** (15m, 3/DD30/50, shifted primary, HTF) was battle-tested as
`monday_or_breakout` StrategyPlugin. On EURUSD broker-like it prints **+$76k /
−$92k stress / 0.83 N/S** — more dollars than this ST+PMC baseline but **worse CE**,
so it does **not** displace this pack. Cross-pair strength is on **USDJPY (4.27)**
and **GBPUSD (1.87)**. See [`../eurusd_monday_or_breakout_15m/RESEARCH.md`](../eurusd_monday_or_breakout_15m/RESEARCH.md)
and [`../fx_monday_or_breakout_broker/SUMMARY.md`](../fx_monday_or_breakout_broker/SUMMARY.md).
