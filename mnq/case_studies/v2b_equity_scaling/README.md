# v2b-Family Equity Scaling

Sizing rule: run N identical bundles of the current strategy, and at each calendar-year start choose the largest N where capital is at least `3 x daily-closed max DD x N`. This is a closed/session-equity overlay; it does not include intraday open heat unless the source strategy already baked it into realized exits.

Run cap: max bundles = 250.

| Variant | Instrument | Start Capital | End Capital | Dynamic Net | Dynamic Daily DD | End/Start | Peak Bundles | Peak Max Contracts | Base Net | Base Daily DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ adaptive 50/150 v2b-only scaleout | MNQ | $14,874 | $76,925 | $62,051 | $-9,916 | 5.17x | 3 | 6 | $35,847 | $-4,958 |
| MNQ full adaptive 50/150 scaleout | MNQ | $22,412 | $52,630 | $30,218 | $-7,470 | 2.35x | 1 | 2 | $30,218 | $-7,470 |
| MNQ monthly-aligned v2d + unchanged v2b scaleout | MNQ | $14,874 | $74,395 | $59,521 | $-9,916 | 5.00x | 3 | 6 | $35,903 | $-4,958 |
| MNQ adaptive 50/150 child 3max | MNQ | $16,138 | $42,930 | $26,791 | $-5,380 | 2.66x | 2 | 6 | $22,020 | $-5,380 |
| MNQ v2b child 3max | MNQ | $20,130 | $42,738 | $22,608 | $-6,710 | 2.12x | 1 | 3 | $22,608 | $-6,710 |
| MNQ v2b child 1-add | MNQ | $16,828 | $37,431 | $20,602 | $-5,610 | 2.22x | 1 | 2 | $20,602 | $-5,610 |
| MNQ v2b tier-1 only | MNQ | $14,140 | $30,424 | $16,284 | $-4,714 | 2.15x | 1 | 1 | $16,284 | $-4,714 |
| NQ adaptive 50/150 v2b-only scaleout | NQ | $297,822 | $296,337 | $-1,485 | $-2,009 | 1.00x | 1 | 2 | $414,773 | $-99,274 |
| NQ all-v2b-days scaleout reference | NQ | $307,695 | $306,711 | $-984 | $-7,344 | 1.00x | 1 | 2 | $443,816 | $-102,565 |

## Notes

- For v2b scaleout, one bundle is the full two-contract TP1 + runner plan.
- For child variants, one bundle is the full parent/child execution path as stored in the source CSV.
- The NQ v2b rows show an important brittleness: starting with exactly 3x historical daily DD, the first available year loses enough to drop below the one-bundle requirement, so the strict model stops trading thereafter. A live account would need extra buffer or an explicit minimum-size rule.
- This is best used for capital-sizing sensitivity, not as proof that fills remain identical at larger size.
