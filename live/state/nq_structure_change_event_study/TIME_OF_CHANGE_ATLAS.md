# Time-of-change atlas — NQ 4h invalidation (dev, pen≥0.05)

Sample minimum for descriptive cells: n≥30.

## CLOSE_BREAK by NY session bucket

| Bucket | n | med MFE | 1R/60m | 2R sess | fail |
|---|---:|---:|---:|---:|---:|
| NY_OPEN | 0 | — | — | — | — |  *(n<30)* |
| NY_AM | 0 | — | — | — | — |  *(n<30)* |
| NY_MIDDAY | 87 | 0.49 | 0.0% | 2.3% | 26.4% |
| NY_PM | 0 | — | — | — | — |  *(n<30)* |
| NY_CLOSE | 0 | — | — | — | — |  *(n<30)* |
| GLOBEX | 39 | 0.74 | 0.0% | 0.0% | 33.3% |

### CLOSE_BREAK by weekday

| DOW | n | med MFE | 1R/60m | fail |
|---|---:|---:|---:|---:|
| Monday | 31 | 0.49 | 0.0% | 48.4% |
| Tuesday | 30 | 0.56 | 0.0% | 40.0% |
| Wednesday | 22 | — | — | — |
| Thursday | 16 | — | — | — |
| Friday | 27 | — | — | — |

## WICK_REJECT by NY session bucket

| Bucket | n | med MFE | 1R/60m | 2R sess | fail |
|---|---:|---:|---:|---:|---:|
| NY_OPEN | 0 | — | — | — | — |  *(n<30)* |
| NY_AM | 0 | — | — | — | — |  *(n<30)* |
| NY_MIDDAY | 65 | 0.59 | 0.0% | 0.0% | 33.8% |
| NY_PM | 0 | — | — | — | — |  *(n<30)* |
| NY_CLOSE | 0 | — | — | — | — |  *(n<30)* |
| GLOBEX | 30 | 0.50 | 0.0% | 6.7% | 33.3% |

### WICK_REJECT by weekday

| DOW | n | med MFE | 1R/60m | fail |
|---|---:|---:|---:|---:|
| Monday | 26 | — | — | — |
| Tuesday | 10 | — | — | — |
| Wednesday | 21 | — | — | — |
| Thursday | 24 | — | — | — |
| Friday | 14 | — | — | — |

