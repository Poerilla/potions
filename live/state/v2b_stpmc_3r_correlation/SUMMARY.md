# v2b prior-opposed ↔ ST+PMC fair 3R correlation

Join: NY session date (+ direction).

## Same-market (v2b PO vs ST+PMC 3R)

| pair | Jaccard | dir-agree | same-dir events | daily ρ | separable? |
|---|---:|---:|---:|---:|---|
| MNQ prior-opposed vs MNQ ST+PMC 3R | 0.33 | 0.056 | 10 | -0.142 | YES |
| NAS100 prior-opposed vs NAS100 ST+PMC 3R | 0.25 | 0.02 | 3 | -0.329 | YES |
| NQ prior-opposed vs NQ ST+PMC 3R | 0.21 | 0.055 | 10 | -0.14 | YES |
| US30 prior-opposed vs US30 ST+PMC 3R | 0.08 | 0.808 | 42 | 0.052 | YES |
| YM prior-opposed vs YM ST+PMC 3R | 0.16 | 0.044 | 9 | -0.129 | YES |

## Cross-market

| bucket | pair | Jaccard | daily ρ | separable? |
|---|---|---:|---:|---|
| cross_v2b_vs_stpmc | YM prior-opposed vs US30 ST+PMC 3R | 0.19 | -0.107 | YES |
| cross_v2b_vs_stpmc | US30 prior-opposed vs YM ST+PMC 3R | 0.05 | 0.004 | YES |
| cross_v2b_vs_stpmc | NQ prior-opposed vs NAS100 ST+PMC 3R | 0.20 | -0.218 | YES |
| cross_v2b_vs_stpmc | NAS100 prior-opposed vs NQ ST+PMC 3R | 0.19 | -0.334 | YES |
| cross_stpmc_vs_stpmc | YM ST+PMC 3R vs US30 ST+PMC 3R | 0.42 | 0.851 | no |
| cross_stpmc_vs_stpmc | NQ ST+PMC 3R vs NAS100 ST+PMC 3R | 0.58 | 0.956 | no |
| cross_stpmc_vs_stpmc | NQ ST+PMC 3R vs MNQ ST+PMC 3R | 0.47 | 0.98 | no |

## Read

- Same-market PO vs ST should be **separable** (OR/v2b vs hourly retest).
- Cross ST+PMC on linked underlyings (YM↔US30, NQ↔NAS100) often **correlated**.

Hub: `live/state/v2b_stpmc_3r_correlation/`

