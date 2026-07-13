# Institutional Strategy Metrics

Generated from saved replay equity curves and summary CSVs. These are **hypothetical/backtested** metrics, not audited live performance.

## Method

- Reference capital is **3x each strategy's intrabar stress DD**.
- Daily returns are daily close-equity changes divided by that reference capital.
- Calmar/MAR is CAGR divided by max intrabar stress DD percentage on that reference capital.
- Sharpe and Sortino are daily-return annualized metrics using 252 trading days.
- Correlation, beta, up-capture, and downside-capture are measured against QQQ adjusted-close returns over each strategy's overlapping dates.
- Drawdown duration uses close-equity high-water marks; intrabar stress still defines the capital anchor.

## Ranked Snapshot

| Rank | Strategy | Window | Ref Cap | Net | CAGR | Calmar | Sharpe | Sortino | DD duration | QQQ corr | QQQ downside capture | PF | Notes |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | NQ prior-opposed v2b gate S_1_1_3 | 2021-03-04 to 2026-03-06 | $161,541 | $1,184,585 | 52.8% | 1.58 | 3.29 | 4.80 | 401d | -0.11 | -1.31 | 2.65 | Prior-opposed v2b |
| 2 | MNQ prior-opposed v2b gate S_1_1_3 | 2021-03-04 to 2026-03-06 | $16,254 | $113,548 | 51.5% | 1.54 | 3.14 | 4.58 | 401d | -0.11 | -1.27 | 2.52 | Prior-opposed v2b |
| 3 | YM prior-opposed v2b gate S_1_1_3 | 2021-03-04 to 2026-04-02 | $80,505 | $320,190 | 37.2% | 1.11 | 2.32 | 3.06 | 302d | -0.00 | -0.38 | 1.85 | Prior-opposed v2b |
| 4 | ES prior-opposed v2b gate S_1_1_3 | 2021-03-04 to 2026-03-06 | $99,490 | $348,688 | 35.1% | 1.05 | 2.26 | 2.51 | 326d | 0.04 | -0.32 | 2.08 | Prior-opposed v2b |
| 5 | MYM prior-opposed v2b gate S_1_1_3 | 2021-03-04 to 2026-03-06 | $7,995 | $26,054 | 33.6% | 1.01 | 2.02 | 2.62 | 302d | -0.00 | -0.33 | 1.71 | Prior-opposed v2b |
| 6 | MNQ Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | $32,007 | $67,942 | 18.1% | 0.54 | 0.91 | 0.63 | 378d | -0.09 | 0.03 | 32.63 | Broker-like leaderboard |
| 7 | MNQ ATR daily ladder 1/1/2/2/2 10-max | 2019-05-05 to 2026-03-08 | $76,830 | $146,875 | 16.9% | 0.51 | 0.80 | 0.65 | 632d | 0.38 | 0.71 | 4.54 | Broker-like leaderboard |
| 8 | MNQ ATR daily 3-initial 10-max | 2019-05-05 to 2026-03-08 | $88,052 | $159,819 | 16.3% | 0.49 | 0.84 | 0.73 | 567d | 0.43 | 0.73 | 3.52 | Broker-like leaderboard |
| 9 | MNQ Yearly ORB scaleout3 20% range-close | 2019-05-05 to 2026-03-08 | $42,423 | $66,845 | 14.8% | 0.44 | 0.81 | 0.71 | 194d | -0.01 | 0.19 | 7.94 | Broker-like leaderboard |
| 10 | MES hourly ST+PMC close_against_entry_next_open | 2019-05-05 to 2023-08-17 | $7,182 | $5,525 | 14.2% | 0.43 | 0.69 | 0.80 | 308d | 0.11 | 0.13 | 1.40 | Hourly ST+PMC |
| 11 | MYM hourly ST+PMC base_1x_50sl_150tp | 2019-05-05 to 2026-03-08 | $4,096 | $6,051 | 14.2% | 0.43 | 1.43 | 3.45 | 374d | 0.03 | -0.07 | 1.35 | Hourly ST+PMC |
| 12 | MNQ hourly ST+PMC sl25_tp75_3r | 2019-05-05 to 2026-04-23 | $7,386 | $10,922 | 13.9% | 0.42 | 1.20 | 2.44 | 500d | 0.02 | -0.02 | 1.29 | Hourly ST+PMC |
| 13 | MES ATR weekly 2-initial / 3-add / 6-max | 2019-05-05 to 2023-08-17 | $51,638 | $37,444 | 13.6% | 0.41 | 0.63 | 0.57 | 596d | 0.46 | 0.57 | 9.23 | Broker-like leaderboard |
| 14 | MYM Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | $11,748 | $15,123 | 12.9% | 0.39 | 0.63 | 0.28 | 356d | -0.18 | -0.09 | 19.88 | Broker-like leaderboard |
| 15 | MNQ ATR weekly 2-initial / 3-add / 6-max | 2019-05-05 to 2026-03-08 | $128,510 | $119,295 | 10.1% | 0.30 | 0.53 | 0.51 | 728d | 0.53 | 0.73 | 7.94 | Broker-like leaderboard |
| 16 | MES Monthly ORB restricted scaleout3 boundary-stop entry | 2019-05-05 to 2023-08-17 | $24,512 | $11,066 | 9.1% | 0.27 | 0.38 | 0.43 | 629d | -0.10 | -0.01 | 1.27 | Broker-like leaderboard |
| 17 | ES Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | $121,209 | $328,728 | 8.7% | 0.26 | 0.66 | 0.44 | 819d | 0.07 | 0.09 | 6.05 | Broker-like leaderboard |
| 18 | NQ Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | $320,160 | $850,314 | 8.6% | 0.26 | 0.72 | 0.45 | 533d | -0.03 | 0.07 | 18.18 | Broker-like leaderboard |
| 19 | YM Yearly ORB scaleout3 | 2010-06-06 to 2026-05-06 | $119,430 | $288,757 | 8.0% | 0.24 | 0.64 | 0.35 | 737d | -0.08 | 0.01 | 13.93 | Broker-like leaderboard |
| 20 | MES Yearly ORB scaleout3 20% range-close | 2019-05-05 to 2023-08-17 | $25,636 | $9,878 | 7.9% | 0.24 | 0.41 | 0.34 | 295d | -0.17 | -0.06 | 2.20 | Broker-like leaderboard |
| 21 | MYM Yearly ORB scaleout3 20% range-close | 2019-05-05 to 2026-03-08 | $18,294 | $12,098 | 7.7% | 0.23 | 0.40 | 0.33 | 718d | -0.12 | 0.04 | 2.91 | Broker-like leaderboard |
| 22 | NQ ATR daily ladder 1/1/2/2/2 10-max | 2010-06-06 to 2026-03-08 | $767,850 | $1,572,142 | 7.3% | 0.22 | 0.55 | 0.44 | 1190d | 0.33 | 0.46 | 3.41 | Broker-like leaderboard |
| 23 | NQ hourly ST+PMC sl25_tp75_3r | 2010-06-06 to 2026-03-08 | $73,906 | $144,521 | 7.1% | 0.21 | 0.86 | 1.42 | 876d | 0.01 | 0.02 | 1.24 | Hourly ST+PMC |
| 24 | NQ ATR daily 3-initial 10-max | 2010-06-06 to 2026-03-08 | $927,206 | $1,717,280 | 6.9% | 0.21 | 0.58 | 0.48 | 875d | 0.38 | 0.45 | 2.80 | Broker-like leaderboard |
| 25 | YM hourly ST+PMC ma_bull_prior_only | 2010-06-06 to 2026-05-06 | $20,922 | $38,828 | 6.8% | 0.20 | 0.61 | 0.91 | 1843d | 0.05 | 0.05 | 1.22 | Hourly ST+PMC |
| 26 | NQ Yearly ORB scaleout3 20% range-close | 2010-06-06 to 2026-03-08 | $423,630 | $741,289 | 6.6% | 0.20 | 0.57 | 0.46 | 1057d | 0.05 | 0.19 | 4.45 | Broker-like leaderboard |
| 27 | YM hourly ST+PMC sl40_tp120_3r | 2010-06-06 to 2026-05-06 | $44,094 | $71,990 | 6.3% | 0.19 | 0.97 | 1.93 | 1445d | 0.00 | -0.04 | 1.24 | Hourly ST+PMC |
| 28 | ES ATR weekly 2-initial / 3-add / 6-max | 2010-06-06 to 2026-03-08 | $600,624 | $853,550 | 5.8% | 0.17 | 0.43 | 0.39 | 1180d | 0.49 | 0.57 | 4.56 | Broker-like leaderboard |
| 29 | ES Yearly ORB scaleout3 20% range-close | 2010-06-06 to 2026-03-08 | $258,998 | $350,746 | 5.6% | 0.17 | 0.47 | 0.41 | 2264d | -0.02 | 0.12 | 2.52 | Broker-like leaderboard |
| 30 | MYM ATR weekly 2-initial / 3-add / 6-max | 2019-05-05 to 2026-03-08 | $57,096 | $24,726 | 5.4% | 0.16 | 0.28 | 0.31 | 1013d | 0.34 | 0.39 | 2.79 | Broker-like leaderboard |

## Reading The Metrics

- **Sharpe is only a baseline.** Strategies with lumpy intraday payouts can look mediocre on Sharpe while still having attractive drawdown-adjusted economics.
- **Sortino matters for runner-style systems.** It penalizes downside volatility while leaving upside volatility alone.
- **Calmar/MAR is the main CTA-style metric here.** The prior-opposed and yearly ORB rows remain strong because their CAGR is high relative to their modeled stress capital.
- **Drawdown duration is now tracked explicitly.** A shallow drawdown that lasts months is operationally different from a deeper but fast-recovering one.
- **QQQ downside capture is a portfolio-fit measure.** Negative values mean the strategy tended to make money on QQQ down days over the overlap.
- **Capacity/slippage is not solved by these ratios.** Live shadow/paper runs must track expected vs actual fill price, queue slippage, rejected orders, and broker reconciliation deltas.

Full machine-readable table: [`metrics.csv`](metrics.csv).
