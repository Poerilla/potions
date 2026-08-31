# Monthly ORB restricted scaleout3 — target before opposite OR

Path race after breakout entry on **daily** OHLC (stop before target same bar).
Ignores range-close exits — pure geometry: does price touch **1R TP**
(`entry ± OR width`) before the **opposite OR boundary**?

## MNQ restricted scaleout3 (n=139 bundles)

| Outcome | Count | Rate |
|---|---:|---:|
| 1R target first | 82 | 59.0% |
| Opposite OR first | 37 | 26.6% |
| Neither by month-end | 20 | 14.4% |

- **Conditional hitrate** (1R before opposite | either touched): **68.9%** (n=119 resolved)
- TP25 before opposite (conditional): **94.8%** (n=135)
- Sim Unit2 full-TP fill rate (range-close can exit first): 48.2%
- Sim Boundary-Stop rate: 2.9%

## NQ restricted scaleout3 (n=313 bundles)

| Outcome | Count | Rate |
|---|---:|---:|
| 1R target first | 195 | 62.3% |
| Opposite OR first | 82 | 26.2% |
| Neither by month-end | 36 | 11.5% |

- **Conditional hitrate** (1R before opposite | either touched): **70.4%** (n=277 resolved)
- TP25 before opposite (conditional): **94.2%** (n=308)
- Sim Unit2 full-TP fill rate (range-close can exit first): 49.8%
- Sim Boundary-Stop rate: 3.5%

## Read for Band-max overlay

Monthly ORB 1R target is hit before the opposite boundary on ~**70%** of
resolved NQ paths. Opposite-boundary stopouts are uncommon in the
*restricted* sim because range-close often exits earlier — but the raw
path race is the relevant figure for using OR levels as a management overlay.

