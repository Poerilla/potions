# EURUSD hourly ST day-bias DCA — broker verdict

**Status:** Not promoted (2026-07-18)  
**Plugin:** `hourly_st_daybias_dca`  
**Replay:** `python3 -m live.eurusd_hourly_st_daybias_dca_broker`

## Rules (as stressed)

- Bias from **prior NY day** hourly ATR SuperTrend (14×3): ≥70% bull → long next day; ≥70% bear → short.
- Enter 0.5-lot unit at prev-day pullback fraction f; SL at prev-day extreme.
- Max 5 adds / calendar month; never two entries same NY day.
- Exit on stop or period end (week = Fri ≥16:00 NY; month = month-end ≥16:00).
- Engine + PaperBroker: **1h signals / 1m fills**, 1-tick slip, FX half-spread, fee $0.75/unit.

## Gate

vs promoted sleeve `eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior`:  
net ≥ **$23.5k** and Net/Stress ≥ **1.49**.

## Broker results (2015-01-01 → 2026-03-31)

| Variant | Net | Stress DD | Net/Stress | Promote |
|---|---:|---:|---:|---|
| f30 week | −$590 | −$9.8k | −0.06 | no |
| f30 month | −$11.7k | −$19.4k | −0.60 | no |
| f40 week | −$8.5k | −$13.4k | −0.63 | no |
| f40 month | −$19.2k | −$26.3k | −0.73 | no |
| f50 week | −$20.0k | −$24.8k | −0.81 | no |

## vs pandas research

Research path (same window) showed positive closed-equity for f≤50% week/month, led by f30 week. Under broker realism the edge **does not survive**: same ~675 unit capacity, but much shorter holds and stop-heavy exits once fill lag, spread, and slippage are applied.

## Promotion decision

**Do not promote.** Keep the FX intraday sleeve as:

`live/state/eurusd_forex_intraday_baseline/`  
(`eurusd_hourly_st_pmc_sl25_tp75_3r_ma_bull_prior`, ~$23.5k / 1.49 Net/Stress)

Plugin remains registered for further experiments; not a Tier-1 / pack candidate.
