# EURUSD PMC-follow v2b S_1_1_3

Plain `v2b_scaleout` (no prior-opposed ST gate) with **previous-month-close follow**:

- Long only when price is **above** PMC
- Short only when price is **below** PMC

| Sizing | Sessions | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S_1_1_3 | 3710 | 2792 | 13960 | $-336914.00 | $-338771.00 | $-339066.00 | -0.99 | 21.7 | 0.665 |

- Mode: **follow**
- Start: **2003-06-02**
- Entry / TP1 / TP2 / runner: **5 / 1 / 1 / 3**
- PMC map: [`session_prev_month_closes.csv`](session_prev_month_closes.csv)

