# AUDJPY — top tracked futures strategies sweep

Engine + PaperBroker, Histdata daily/hourly/1m (2003-12 → 2026-03), 1-tick slip,
fee ¥7/unit (FX pack convention; understates JPY costs slightly). P&L in JPY;
approx USD at 110 except the best-report (daily USDJPY conversion).

| Family | Strategy | Trades | Net (JPY) | Stress DD | **N/S** | ~USD |
|---|---|---:|---:|---:|---:|---:|
| yearly_orb | **Yearly ORB scaleout3** | 146 | **¥21.13M** | **¥-1.38M** | **15.26** | **+$192k** |
| hourly_st_pmc | ST+PMC sl25/tp75 3R (no MA gate) | 1981 | ¥4.27M | ¥-1.73M | **2.47** | +$39k |
| hourly_st_pmc | ST+PMC sl25/tp75 + MA bull prior* | 1075 | ¥2.79M | ¥-2.15M | 1.30 | +$25k |
| monthly_orb | restricted scaleout3 | 320 | ¥6.37M | ¥-7.91M | 0.80 | +$58k |
| hourly_st_pmc | ST+PMC 40/120 directional prior | 1268 | ¥1.09M | ¥-1.58M | 0.69 | |
| monthly_orb | restricted scaleout3 boundary-stop | 616 | ¥3.30M | ¥-7.46M | 0.44 | |
| hourly_st_pmc | ST+PMC 50/150 base | 1338 | ¥0.60M | ¥-2.61M | 0.23 | |
| atr_st | ATR daily ladder 10-max | 216 | ¥2.11M | ¥-15.45M | 0.14 | |
| atr_st | ATR daily 3-initial 10-max | 216 | ¥1.91M | ¥-15.30M | 0.12 | |
| yearly_orb | scaleout3 20% range-close | 82 | ¥-0.71M | ¥-13.38M | -0.05 | |
| atr_st | ATR weekly 2i/3a/6max | 64 | ¥-1.18M | ¥-18.03M | -0.07 | |
| v2b | v2b OCO prior-opposed 1/1/3 (2015+) | ~1261 | ¥-10.79M | ¥-11.37M | **-0.95** | -$98k |

*from the earlier cross-pair run (`fx_cross_pair_tracker_leaders`).

## Winner: Yearly ORB scaleout3 — $250k report (`best_report_yearly_orb/`)

Q1 range → trade Apr–Dec breakouts, scaleout3, fresh-break requirement.
USD conversion at daily USDJPY close. Independently reconstructed from fills
(net matches audit to 0.01%).

| Metric | Value |
|---|---:|
| Net (22.3y) | **$193,498** |
| CAGR | 2.60% |
| **Sharpe** | **1.03** |
| Sortino | 0.57 |
| Ann vol | 2.03% |
| Max DD | **-2.69%** |
| Stress DD | -$13,020 (-3.4%) |
| Net/Stress (USD) | 14.86 |
| Exposure | 10.2% (8% long / 2% short) |
| Trades / unit WR | 146 / 88.8% |
| Best / worst month | +6.69% / **-1.33%** |
| Positive years | **87.5%** (21/24; worst -0.43%) |

Best years: 2007 +10.1%, 2010 +9.7%, 2008 +6.6%, 2005 +4.8%. Never a losing
year worse than -0.4%. Tables: `yearly_returns.csv`, `monthly_returns_pct.csv`.

## Takeaways

1. **Yearly ORB scaleout3 is the standout** — the carry-trend character that
   killed the FBO fade on AUDJPY is exactly what a yearly breakout harvest
   wants. Sharpe 1.03 with a -2.7% max DD is the best risk-adjusted stream in
   the workspace, but caveats below.
2. **ST+PMC 25/75 works unfiltered (2.47)** — better than with the MA bull
   gate (1.30); AUDJPY trends persistently enough that gating hurts.
3. ATR supertrend DCA family: flat-to-poor. v2b prior-opposed: clear fail
   (as on EURUSD).
4. Variant fragility warning: the 20% range-close yearly variant destroys the
   edge (-0.05), and 146 trades/22y is a modest sample with 88.8% unit WR —
   the yearly result leans on runner holds during the 2004-2012 carry era.
   Validate on other JPY crosses before promoting.

Driver: `live/audjpy_futures_strats_sweep.py` (stages: daily / stpmc / v2b).
