# Stage B — timing / expiry diagnostics (S1)

**Updated:** 2026-08-30 13:45 ET
**Contract:** seed expiry fixed at 30 × 4h; order-life cases 24 / 48 / 72h.
**Rule:** report only — no tuning this run.

## Seed → first 4h break (hours)

| p25 | median | p75 | p90 | n |
|---:|---:|---:|---:|---:|
| 2.98 | 6.98 | 27.24 | 71.98 | 91 |

## Break → first retest touch (hours)

| p25 | median | p75 | p90 | n |
|---:|---:|---:|---:|---:|
| 0.45 | 2.63 | 18.50 | 22.30 | 58 |

## Retest order-life capture (among seeds with a 4h break)

| Window | fraction |
|---|---:|
| ≤12h | (see soft scan below; primary flags 24/48/72) |
| ≤24h | 58.2% |
| ≤48h | 61.5% |
| ≤72h | 63.7% |

### Filled primary (48h book) capture cumulative

| ≤12h | ≤24h | ≤36h | ≤48h | ≤72h |
|---:|---:|---:|---:|---:|
| 54% | 95% | 98% | 100% | 100% |

## Expired / non-fill taxonomy (48h primary book, n=91 seeds)

| Reason | n | rate |
|---|---:|---:|
| no break before seed expiry | 0 | 0.0% |
| no retest (limit life / age) | 35 | 38.5% |
| re-entered seed range (4h close) | 0 | 0.0% |
| opposite side broke first | 0 | 0.0% |
| FILLED | 56 | 61.5% |

## Order-life cases (seed expiry fixed 30 × 4h)

| Life | fills | fill% | net $ | avg R | med R | WR | PF |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 24h | 53 | 58% | +25360 | +0.125 | +0.249 | 55% | 1.74 |
| 48h | 56 | 62% | +17241 | +0.101 | +0.248 | 54% | 1.40 |
| 72h | 58 | 64% | +21967 | +0.126 | +0.248 | 55% | 1.51 |

Primary decision book = **48h**. 24h = 1h-model control horizon; 72h = slower diagnostic.

## S2 gate

S2 gate opened after S1; Stage C executed — see SUMMARY Stage C / `trades_s2_48h.csv`.
