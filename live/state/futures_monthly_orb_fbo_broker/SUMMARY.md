# Index futures monthly ORB — FBO transfer test + $250k reports

## 1. Does the promoted EURUSD FBO edge transfer to ES/NQ/YM? **No.**

FBO 1/1/3 runner@2R BE@TP25 close-SL (exact promoted config, fee $1.50/unit,
1-tick slip), plus the atr80 filter that helped EURUSD:

| Market | Variant | n | WR | Net | Stress DD | Net/Stress |
|---|---|---:|---:|---:|---:|---:|
| ES | base | 123 | 39.0% | $-111,241 | $-322,134 | -0.35 |
| ES | atr80 | 106 | 35.8% | $-161,904 | $-211,183 | -0.77 |
| NQ | base | 116 | 43.1% | $27,859 | $-233,097 | 0.12 |
| NQ | atr80 | 96 | 43.8% | $-38,261 | $-252,938 | -0.15 |
| YM | base | 131 | 44.3% | $-45,152 | $-224,931 | -0.20 |
| YM | atr80 | 116 | 43.1% | $-188,320 | $-211,240 | -0.89 |

Fading the first monthly break works in a mean-reverting FX cross; equity
indices trend (drift + vol regimes) and run the fade over. The atr80 filter
makes futures *worse* — in equities the high-vol months are where short fades
paid, opposite of FX. Lesson does not transfer.

## 2. Existing best futures monthly ORB (restricted scaleout3) — $250k reports

Reports: `book_250k_reports/{es,nq,ym}/` (yearly + monthly CSVs, equity_daily).
MTM reconstruction validated vs published audits (ES net matches to <0.1%).

| $250k book | ES | YM | NQ (see caveat) |
|---|---:|---:|---:|
| Years | 15.8 | 15.9 | 15.8 |
| Net | $246,293 | $179,498 | $-87,456 |
| CAGR | 4.45% | 3.46% | -2.70% |
| Sharpe | 0.52 | 0.49 | -0.04 |
| Max DD | -17.9% | -17.2% | -68.0% |
| Stress DD | $-66,162 (-18.2%) | $-56,795 (-17.4%) | $-345,841 |
| Exposure | 95% | 95% | 39% |
| Positive years | 65% | 71% | 53% |

**NQ caveat:** the published leaderboard row (+$430k / 3.53) is NOT reproducible
from the current state dir — it holds a different (month-end-flatten, 225
campaign) run whose fills reconstruct to -$87k. The +$430k NQ number should be
treated as stale/unverified until rerun.

**Character warning:** ES/YM scaleout3 books are ~95% time-in-market and
**98-99% long**. Sharpe ~0.5 with -11% in 2022 (ES) — this is substantially
repackaged equity beta with a trend gate, not an absolute-return stream.

## 3. Would $800M into them be wise? **No.**

- Capacity itself is fine: ES turns over ~$300-400B notional/day; $800M is
  ~0.2-0.3% of ADV, executable via slicing (same as the EURUSD conclusion).
- But: ES/YM books carry Sharpe ~0.5 built on **18 campaigns in 16 years** —
  far too thin a sample to underwrite institutional size.
- They are ~99% long index futures: $800M here is mostly S&P/Dow beta you could
  buy for ~1bp via futures/ETFs without strategy risk.
- NQ, the headline number of the family, is currently unverifiable (above).
- The EURUSD FBO sleeve is a genuine absolute-return stream but Sharpe ~0.2-0.3.

Sensible use: futures monthly ORB as a *timing overlay* on an existing equity
allocation (it de-risked 2022 only partially), and EURUSD FBO as a small
uncorrelated sleeve. Nothing in this family justifies $800M concentration;
a diversified multi-sleeve book (intraday FX + monthly FX + index overlays)
at vol-targeted sizing is the defensible construction.

Driver: inline scripts in session; states under `states/`, filters under `filters/`.
