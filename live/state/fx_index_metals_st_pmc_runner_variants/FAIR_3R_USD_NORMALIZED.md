# Fair 3R — USD-normalized performance

Variant `sl50_tp150_3r_1mfill` (1m fill tape).

**JPY pairs:** platform `POINT_VALUES=100000` is JPY per 1.0 price move. Normalized as `usd = points × 100000 / USDJPY_rate − $1.50` per unit (rate = exit price for realized; hourly close for equity/stress path).

| Rank | Market | Class | Net USD | Stress | N/S | Units | WR% |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | **US30** | index CFD | $19,028 | $-647 | **29.39** | 578 | 42.6 |
| 2 | **NAS100** | index CFD | $15,219 | $-778 | **19.56** | 477 | 41.9 |
| 3 | **GBPUSD** | FX | $108,058 | $-13,310 | **8.12** | 1026 | 30.6 |
| 4 | **EURUSD** | FX | $64,449 | $-21,432 | **3.01** | 866 | 29.0 |
| 5 | **USDJPY** | FX | $30,407 | $-19,540 | **1.56** | 869 | 27.5 |

## Pending

AUDJPY, XAUUSD, XAGUSD


**US30 stress:** lot-correct *reachable* (−$647, N/S 29.39). MTM audit still prints raw intrabar (−$907, N/S 20.97).

## USDJPY bridge

- Platform (JPY-scaled “$”): net $4,040,012 / stress $-2,282,415 / N/S 1.77
- USD-normalized: net $30,407 / stress $-19,540 / N/S **1.56**
- Net points (price units): 40.41
- Equity bars missing rate join: 0

