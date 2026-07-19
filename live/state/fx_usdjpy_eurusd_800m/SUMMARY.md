# $800M allocation — USDJPY 65% / EURUSD 35% FBO 1/1/3 atr80

Sleeves: monthly ORB FBO 1/1/3 runner@2R BE@TP25 close-SL + **atr80** filter
(the tracked leaders: USDJPY N/S 4.25, EURUSD 1.62). Broker fills, USDJPY P&L
converted to USD at daily close. Sizing: **2:1 gross leverage** ($1.6B notional,
scaled from the 5-lot base book), split 65/35 by the Sharpe-optimal weight grid
(`weight_grid.csv`; optimum plateau w_usdjpy 0.55–0.70, chose 0.65 for stress).
Daily P&L correlation between sleeves: **+0.03** (essentially uncorrelated).

| Metric | USDJPY ($520M) | EURUSD ($280M) | **Combined ($800M)** |
|---|---:|---:|---:|
| Net (22.9y) | $193.7M | $97.2M | **$290.9M** |
| CAGR | 1.39% | 1.31% | **1.36%** |
| Sharpe | 0.3 | 0.26 | **0.38** |
| Sortino | 0.16 | 0.12 | 0.26 |
| Ann vol | 3.94% | 4.41% | 3.01% |
| Max DD | -8.69% | -14.46% | **-6.68%** |
| Stress DD | $-58.9M (-9.78%) | $-60.0M (-15.22%) | $-79.3M (-7.73%) |
| Net/Stress | 3.29 | 1.62 | **3.67** |
| Best / worst month | +4.55% / -4.94% | +6.75% / -5.22% | +4.01% / -2.59% |
| Positive months / years | 27.3% / 66.7% | 22.5% / 58.3% | 38.5% / 62.5% |

Diversification: combined Sharpe **0.38** vs 0.30 / 0.26 standalone; worst month
compresses to **−2.6%** (vs −4.9% / −5.2%); max DD **−6.7%**.

## Capacity at $800M

USDJPY sleeve holds up to ~$1.04B notional (0.2–0.3% of USDJPY ADV), EURUSD
~$0.56B — executable with 1–2bp slicing impact per prior analysis. ~12 stop
entries/yr across both books.

## Caveats

- Returns are leverage-scalable but small at 2:1 (CAGR ~1.4%); Sharpe 0.38 is
  the real number to underwrite. 3–4x gross would give ~2.7–4% CAGR with
  proportional DD.
- JPY fee modeled at ¥7/unit (understated ~1–2% of net); USD conversion of JPY
  P&L done at daily close (correct marking, no flat-rate approximation).
- USDJPY N/S 4.25 is single-pair, single-configuration — expect regression
  toward the family mean out of sample; the combined book leans on it 65%.

Reports: `usdjpy/`, `eurusd/`, `combined/` (metrics.json, yearly_returns.csv,
monthly_returns_pct.csv, equity_daily.csv) · chart `equity_800m.png` ·
weight grid `weight_grid.csv`.
