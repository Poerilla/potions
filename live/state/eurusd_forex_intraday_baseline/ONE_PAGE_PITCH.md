# EURUSD Forex Intraday Baseline

**One-page promotion exhibit.** Hourly SuperTrend + prior-month-close retest, **25 pip stop / 75 pip target (3R)**, gated by **prior-hour MA50 > MA150** (`bull_prior_only`). Broker-like `StrategyPlugin` replay on Histdata EURUSD.

**Promoted role:** practical **FX intraday sleeve** — modest edge, liquid hours, clean causality. Not a flagship vs Yearly ORB; improvement room later.

## Headline (2003-06 → 2026-03)

| Metric | Value |
|---|---:|
| Net (fee $1.50/unit) | **$23,534** |
| Intrabar stress DD | **−$15,745** |
| Net / stress DD | **1.49** |
| Trades / win rate | **1,148 / 27.4%** |
| Full-sample daily Sharpe | **0.29** |
| Causal check | **PASS** (0 violations; fills strictly after hour-complete) |

## Why this book

- **Rules are simple and causal:** hour-complete ST + PMC side filter + prior-hour MA bull gate; resting limit at ST with fixed 25/75 bracket.
- **Liquidity:** ~81% of entries fall in London–NY hours (03:00–16:00 NY).
- **Not a rates/USD beta sleeve:** yearly PnL vs Fed funds level **r ≈ 0.11**; vs USD strength proxy **|r| ≈ 0.24** (FRED RIFSPFFNA; −EURUSD yearly return).
- **Throughput:** ~50 trades/year on average — enough for a live FX desk paper trail without Yearly ORB sparsity.

## Honest limits

- Absolute dollars are **small** vs futures flagships; Net/Stress **~1.5** is workable, not elite.
- Win rate is low by design (3R); edge is payoff asymmetry, not hit rate.
- Several calendar years are negative; path depends on clustered trend years (e.g. 2008, 2013, 2025).

## Promotion pointer

- State: `live/state/eurusd_overnight_sweep/st_pmc/states/eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior/`
- Charts: `live/state/eurusd_overnight_sweep/st_pmc/charts/eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior/`
- Yearly + causal pack: this folder (`YEARLY_PERFORMANCE.md`, `CAUSAL_CHECK.md`)

**Caveat:** hypothetical/backtested performance. Promote for paper/live-test sequencing, not capital commitment sizing.
