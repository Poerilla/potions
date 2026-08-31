# First-hour follow 3R all days (broker-like)

Engine + PaperBroker + StrategyPlugin `first_hour_follow` on NY RTH 5m.
Book: **follow 3R, every directional first hour** (09:30–10:30). Entry `market_close` on last FH bar (10:25); SL = FH open; TP = 3× body; flatten 15:59.
Realism: slip 1 tick, spread model, fee $1.50/unit. JPY pairs ÷110 for USD.

| Rank | Market | Family | Sessions | Trades | WR | Net USD | Stress DD | N/S | Window |
|---:|---|---|---:|---:|---:|---:|---:|---:|---|
| 1 | NQ | futures | 4046 | 3943 | 37.2% | $176,743 | $-31,718 | 5.57 | 2010-06-07 → 2026-03-06 |
| 2 | NAS100 | cfd | 2277 | 2213 | 37.6% | $7,728 | $-1,889 | 4.09 | 2016-11-15 → 2025-09-30 |
| 3 | GBPUSD | fx | 5955 | 5908 | 28.8% | $-384 | $-42,389 | -0.01 | 2003-05-06 → 2026-03-31 |
| 4 | MES | futures | 1107 | 1075 | 32.1% | $-1,665 | $-5,288 | -0.31 | 2019-05-06 → 2023-08-16 |
| 5 | US30 | cfd | 2246 | 2051 | 31.9% | $-4,491 | $-12,027 | -0.37 | 2016-10-27 → 2025-07-15 |
| 6 | EURUSD | fx | 5955 | 5909 | 25.8% | $-16,369 | $-29,620 | -0.55 | 2003-05-06 → 2026-03-31 |
| 7 | AUDJPY | fx | 5803 | 5744 | 25.9% | $-33,386 | $-38,399 | -0.87 | 2003-12-02 → 2026-03-31 |
| 8 | YM | futures | 4092 | 3981 | 33.1% | $-51,174 | $-58,156 | -0.88 | 2010-06-07 → 2026-05-06 |
| 9 | XAUUSD | metal | 5933 | 5825 | 24.4% | $-114,413 | $-127,535 | -0.90 | 2003-05-06 → 2026-03-31 |
| 10 | USDJPY | fx | 5944 | 5856 | 25.7% | $-28,380 | $-31,011 | -0.92 | 2003-05-06 → 2026-03-31 |
| 11 | XAGUSD | metal | 5869 | 5426 | 17.3% | $-181,272 | $-183,008 | -0.99 | 2003-05-06 → 2026-03-31 |

## Skipped

- **ES**: ES 1m DBN missing locally (daily only)

## Stance

Research / diagnostic. Same large first-hour-open stop as the NQ pandas mill. Do not promote from this table alone; compare N/S and WR vs the NQ broker-like hub `live/state/nq_1h_first_hour_broker/` (all-days N/S 5.57).

Hub: `/home/tester/hsm/potions/live/state/first_hour_follow_broker`
