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
| 1 | NQ prior-opposed v2b gate S_1_1_3 (legacy fill stamp) | 2021-03-04 to 2026-03-08 | $161,826 | $1,175,785 | 52.4% | 1.57 | 2.95 | 3.97 | 401d | -0.11 | -1.31 | 2.63 | Prior-opposed v2b legacy |
| 2 | MNQ prior-opposed v2b gate S_1_1_3 (legacy fill stamp) | 2021-03-04 to 2026-03-03 | $16,282 | $114,970 | 51.8% | 1.56 | 2.86 | 3.88 | 227d | -0.10 | -1.26 | 2.54 | Prior-opposed v2b legacy |
| 3 | NQ prior-opposed v2b resting-limit (hour-complete) | 2021-03-04 to 2026-03-08 | $205,830 | $1,330,920 | 49.4% | 1.48 | 2.88 | 3.80 | 408d | -0.11 | -1.01 | 2.33 | Prior-opposed v2b resting-limit |
| 4 | MNQ prior-opposed v2b resting-limit (hour-complete) | 2021-03-04 to 2026-03-03 | $20,880 | $128,360 | 48.2% | 1.45 | 2.74 | 3.63 | 232d | -0.09 | -0.94 | 2.26 | Prior-opposed v2b resting-limit |
| 5 | YM prior-opposed v2b gate S_1_1_3 (legacy fill stamp) | 2021-03-04 to 2026-04-02 | $80,730 | $318,791 | 37.0% | 1.11 | 2.05 | 2.46 | 303d | 0.00 | -0.37 | 1.84 | Prior-opposed v2b legacy |
| 6 | ES prior-opposed v2b gate S_1_1_3 (legacy fill stamp) | 2021-03-04 to 2026-03-06 | $99,490 | $348,688 | 35.1% | 1.05 | 2.26 | 2.51 | 326d | 0.04 | -0.32 | 2.08 | Prior-opposed v2b legacy |
| 7 | MYM prior-opposed v2b gate S_1_1_3 (legacy fill stamp) | 2021-03-04 to 2026-03-08 | $8,084 | $26,089 | 33.3% | 1.00 | 1.80 | 2.12 | 303d | -0.00 | -0.32 | 1.70 | Prior-opposed v2b legacy |
| 8 | YM prior-opposed v2b resting-limit (hour-complete) | 2021-03-04 to 2026-04-02 | $101,681 | $289,225 | 30.4% | 0.91 | 1.76 | 2.13 | 300d | 0.02 | -0.21 | 1.59 | Prior-opposed v2b resting-limit |
| 9 | MYM prior-opposed v2b resting-limit (hour-complete) | 2021-03-04 to 2026-03-08 | $10,250 | $22,101 | 25.8% | 0.77 | 1.45 | 1.70 | 371d | 0.02 | -0.13 | 1.46 | Prior-opposed v2b resting-limit |
| 10 | MNQ hourly ST+PMC sl25_tp75_3r | 2021-03-04 to 2026-03-03 | $7,386 | $10,922 | 19.9% | 0.60 | 1.34 | 2.51 | 449d | 0.01 | -0.04 | 1.29 | Hourly ST+PMC |
| 11 | MNQ Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | $32,007 | $67,942 | 18.1% | 0.54 | 0.91 | 0.63 | 378d | -0.09 | 0.03 | 32.63 | Broker-like leaderboard |
| 12 | MNQ ATR daily ladder 1/1/2/2/2 10-max | 2019-05-05 to 2026-03-08 | $76,830 | $146,875 | 16.9% | 0.51 | 0.80 | 0.65 | 632d | 0.38 | 0.71 | 4.54 | Broker-like leaderboard |
| 13 | MNQ ATR daily 3-initial 10-max | 2019-05-05 to 2026-03-08 | $88,052 | $159,819 | 16.3% | 0.49 | 0.84 | 0.73 | 567d | 0.43 | 0.73 | 3.52 | Broker-like leaderboard |
| 14 | MNQ Yearly ORB scaleout3 20% range-close | 2019-05-05 to 2026-03-08 | $42,423 | $66,845 | 14.8% | 0.44 | 0.81 | 0.71 | 194d | -0.01 | 0.19 | 7.94 | Broker-like leaderboard |
| 15 | MES hourly ST+PMC close_against_entry_next_open | 2019-05-05 to 2023-08-17 | $7,182 | $5,525 | 14.2% | 0.43 | 0.69 | 0.80 | 308d | 0.11 | 0.13 | 1.40 | Hourly ST+PMC |
| 16 | MYM hourly ST+PMC base_1x_50sl_150tp | 2019-05-05 to 2026-03-08 | $4,096 | $6,051 | 14.2% | 0.43 | 1.43 | 3.45 | 374d | 0.03 | -0.07 | 1.35 | Hourly ST+PMC |
| 17 | MES ATR weekly 2-initial / 3-add / 6-max | 2019-05-05 to 2023-08-17 | $51,638 | $37,444 | 13.6% | 0.41 | 0.63 | 0.57 | 596d | 0.46 | 0.57 | 9.23 | Broker-like leaderboard |
| 18 | MYM Yearly ORB scaleout3 | 2019-05-05 to 2026-03-08 | $11,748 | $15,123 | 12.9% | 0.39 | 0.63 | 0.28 | 356d | -0.18 | -0.09 | 19.88 | Broker-like leaderboard |
| 19 | MNQ ATR weekly 2-initial / 3-add / 6-max | 2019-05-05 to 2026-03-08 | $128,510 | $119,295 | 10.1% | 0.30 | 0.53 | 0.51 | 728d | 0.53 | 0.73 | 7.94 | Broker-like leaderboard |
| 20 | ES Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | $121,209 | $328,728 | 8.7% | 0.26 | 0.66 | 0.44 | 819d | 0.07 | 0.09 | 6.05 | Broker-like leaderboard |
| 21 | NQ Yearly ORB scaleout3 | 2010-06-06 to 2026-03-08 | $320,160 | $850,314 | 8.6% | 0.26 | 0.72 | 0.45 | 533d | -0.03 | 0.07 | 18.18 | Broker-like leaderboard |
| 22 | AUDJPY Yearly ORB scaleout3 | 2003-12-02 to 2026-03-31 | $37,763 | $192,125 | 8.4% | 0.25 | 0.70 | 0.40 | 654d | 0.05 | 0.02 | 8.85 | FX/Metals Yearly ORB |
| 23 | YM Yearly ORB scaleout3 | 2010-06-06 to 2026-05-06 | $119,430 | $288,757 | 8.0% | 0.24 | 0.64 | 0.35 | 737d | -0.08 | 0.01 | 13.93 | Broker-like leaderboard |
| 24 | MES Yearly ORB scaleout3 20% range-close | 2019-05-05 to 2023-08-17 | $25,636 | $9,878 | 7.9% | 0.24 | 0.41 | 0.34 | 295d | -0.17 | -0.06 | 2.20 | Broker-like leaderboard |
| 25 | MYM Yearly ORB scaleout3 20% range-close | 2019-05-05 to 2026-03-08 | $18,294 | $12,098 | 7.7% | 0.23 | 0.40 | 0.33 | 718d | -0.12 | 0.04 | 2.91 | Broker-like leaderboard |
| 26 | NQ ATR daily ladder 1/1/2/2/2 10-max | 2010-06-06 to 2026-03-08 | $767,850 | $1,572,142 | 7.3% | 0.22 | 0.55 | 0.44 | 1190d | 0.33 | 0.46 | 3.41 | Broker-like leaderboard |
| 27 | XAUUSD Yearly ORB scaleout3 | 2003-05-06 to 2026-03-31 | $143,709 | $541,254 | 7.1% | 0.21 | 0.72 | 0.43 | 1471d | -0.01 | -0.04 | 15.08 | FX/Metals Yearly ORB |
| 28 | NQ hourly ST+PMC sl25_tp75_3r | 2010-06-06 to 2026-06-16 | $73,906 | $144,521 | 7.0% | 0.21 | 0.85 | 1.38 | 876d | 0.01 | 0.02 | 1.24 | Hourly ST+PMC |
| 29 | NQ ATR daily 3-initial 10-max | 2010-06-06 to 2026-03-08 | $927,206 | $1,717,280 | 6.9% | 0.21 | 0.58 | 0.48 | 875d | 0.38 | 0.45 | 2.80 | Broker-like leaderboard |
| 30 | MES Monthly ORB restricted scaleout3 boundary-stop entry | 2019-05-05 to 2023-08-17 | $29,509 | $9,685 | 6.8% | 0.21 | 0.33 | 0.37 | 628d | -0.11 | -0.01 | 1.23 | Broker-like leaderboard |

## Reading The Metrics

- **Sharpe is only a baseline.** Strategies with lumpy intraday payouts can look mediocre on Sharpe while still having attractive drawdown-adjusted economics.
- **Sortino matters for runner-style systems.** It penalizes downside volatility while leaving upside volatility alone.
- **Calmar/MAR is the main CTA-style metric here.** The prior-opposed and yearly ORB rows remain strong because their CAGR is high relative to their modeled stress capital.
- **Drawdown duration is now tracked explicitly.** A shallow drawdown that lasts months is operationally different from a deeper but fast-recovering one.
- **QQQ downside capture is a portfolio-fit measure.** Negative values mean the strategy tended to make money on QQQ down days over the overlap.
- **Capacity/slippage is not solved by these ratios.** Live shadow/paper runs must track expected vs actual fill price, queue slippage, rejected orders, and broker reconciliation deltas.

Full machine-readable table: [`metrics.csv`](metrics.csv).
