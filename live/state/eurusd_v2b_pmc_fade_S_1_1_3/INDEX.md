# EURUSD PMC-fade v2b S_1_1_3

Plain `v2b_scaleout` (no prior-opposed ST gate) with **previous-month-close fade**:

- Long only when price is **below** PMC
- Short only when price is **above** PMC

| Sizing | Sessions | Trades | Units | Net | Closed DD | Stress DD | Net/Stress | Win% | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| S_1_1_3 | 3710 | 2727 | 13635 | $-427029.00 | $-430429.00 | $-430619.00 | -0.99 | 19.8 | 0.574 |

- Start: **2003-06-02**
- Entry / TP1 / TP2 / runner: **5 / 1 / 1 / 3**
- PMC map: [`session_prev_month_closes.csv`](session_prev_month_closes.csv)

