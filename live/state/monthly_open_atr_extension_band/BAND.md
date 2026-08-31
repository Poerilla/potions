# Monthly open extension — working band

ATR: **monthly Wilder ATR(14)** @ prior month close.
Extension window: after opening week through month end.

Each side band spans **mean(min) → mean(max)** ATR extension with
**mean(median)** inside. Entry at inner edge; SL at outer extreme.

| Market | N months | Up min | Up med | Up max | Dn min | Dn med | Dn max |
|---|---:|---:|---:|---:|---:|---:|---:|
| NQ | 175 | 0.034× | 0.278× | 0.610× | 0.019× | 0.147× | 0.558× |
| US30 | 91 | 0.036× | 0.273× | 0.589× | 0.026× | 0.177× | 0.614× |
| YM | 174 | 0.026× | 0.247× | 0.538× | 0.021× | 0.147× | 0.534× |

## Price levels (example: current band × monthly ATR)

At month open `O` and monthly ATR `A`:

- **Long band:** `[O − dn_max·A, O − dn_min·A]` — buy at `O − dn_min·A`, SL `O − dn_max·A`
- **Short band:** `[O + up_min·A, O + up_max·A]` — sell at `O + up_min·A`, SL `O + up_max·A`
- Target: month open `O`; flatten runner at EOM if still open.
