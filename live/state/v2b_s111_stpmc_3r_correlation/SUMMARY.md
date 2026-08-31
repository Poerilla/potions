# Base v2b S_1_1_1 ↔ ST+PMC fair 3R correlation

**v2b book: ungated `S_1_1_1` (1 TP1 + 1 TP2 + 1 runner)** from `v2b_sizing_sweep`.
**Not** prior-opposed. **Not** S_1_1_3.

US30/NAS100 have no archived base v2b S_1_1_1 book — cross pairs use YM/NQ v2b vs CFD ST.

## Same-market

| pair | Jaccard | dir-agree | same-dir | daily ρ | separable? |
|---|---:|---:|---:|---:|---|
| MNQ v2b S_1_1_1 vs MNQ ST+PMC 3R | 0.21 | 0.708 | 150 | -0.02 | YES |
| MYM v2b S_1_1_1 vs MYM ST+PMC 3R | 0.19 | 0.7 | 153 | -0.065 | YES |
| NQ v2b S_1_1_1 vs NQ ST+PMC 3R | 0.16 | 0.7 | 149 | -0.026 | YES |
| YM v2b S_1_1_1 vs YM ST+PMC 3R | 0.14 | 0.717 | 161 | -0.037 | YES |

## Cross

| bucket | pair | Jaccard | ρ | sep |
|---|---|---:|---:|---|
| cross_v2b_s111_vs_stpmc | YM v2b S_1_1_1 vs US30 ST+PMC 3R | 0.16 | -0.048 | Y |
| cross_v2b_s111_vs_stpmc | NQ v2b S_1_1_1 vs NAS100 ST+PMC 3R | 0.16 | -0.061 | Y |
| cross_v2b_s111_vs_stpmc | NQ v2b S_1_1_1 vs MNQ ST+PMC 3R | 0.21 | -0.025 | Y |
| cross_v2b_s111_vs_stpmc | YM v2b S_1_1_1 vs MYM ST+PMC 3R | 0.19 | -0.058 | Y |
| cross_stpmc_vs_stpmc | YM ST+PMC 3R vs US30 ST+PMC 3R | 0.42 | 0.851 | n |
| cross_stpmc_vs_stpmc | NQ ST+PMC 3R vs NAS100 ST+PMC 3R | 0.58 | 0.956 | n |
| cross_stpmc_vs_stpmc | NQ ST+PMC 3R vs MNQ ST+PMC 3R | 0.47 | 0.98 | n |
