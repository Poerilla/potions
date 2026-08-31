# EURUSD — PMC break + prior opposite ST trail (3R)

Plugin: `hourly_st_pmc_break_prev_trail`

## Rules

- Hourly ATR SuperTrend 14×3; prior-month close bias; **MA50>MA150 prior** (same as promoted sleeve).
- **Long:** hourly close > PMC and ST bullish → buy **limit at last bearish ST trail**; SL at current bullish ST; TP = entry + **3R**.
- **Short:** hourly close < PMC and ST bearish → sell limit at last bullish ST trail; SL at current bearish ST; TP = entry − 3R.
- Entries only **London 08:00 → NY 15:00** (arming window); 15:00 NY hour cancels resting limits. Open risk can finish outside the window.
- Fee $1.50/unit, PV $100k, 1-tick stop slip (Engine + PaperBroker).

## Headline

| Metric | Value |
|---|---:|
| Campaigns | 1222 |
| Units (audit) | 1222 |
| Net | $-102,369.27 |
| Stress DD | $-112,579.95 |
| Net/Stress | -0.91 |
| Win % | 21.0 |

## Session consistency (by entry fill time)

| Session | Trades | Wins | Win % | Net | Avg PnL | PF |
|---|---:|---:|---:|---:|---:|---:|
| **london** | 561 | 114 | 20.3% | $-60,540 | $-108 | 0.71 |
| **ny** | 661 | 143 | 21.6% | $-41,829 | $-63 | 0.84 |

**Most consistent session (win rate, ≥20 trades):** **ny** (21.6% WR, $-41,829 net).

State: `/home/tester/hsm/potions/live/state/eurusd_st_pmc_break_prev_trail/states/eurusd_hourly_st_pmc_break_prev_trail_pmc_only_3r`
Trades CSV: `/home/tester/hsm/potions/live/state/eurusd_st_pmc_break_prev_trail/trades_by_session.csv`
Session JSON: `/home/tester/hsm/potions/live/state/eurusd_st_pmc_break_prev_trail/session_stats.json`
