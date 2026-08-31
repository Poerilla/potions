# Close vs wick — NQ structure-change

Population: 4h invalidation events, `min_pen_ATR=0.05`, **dev** slice.
WICK_REJECT scored in **reject (opposite) direction**; break-dir diagnostics also reported.

## Close-break continuation

| Pen quartile | n | med MFE | med MAE | 1R/60m | fail |
|---|---:|---:|---:|---:|---:|
| Q1 | 32 | 0.49 | 0.57 | 0.0% | 34.4% |
| Q2 | 31 | 0.76 | 0.42 | 0.0% | 16.1% |
| Q3 | 31 | 0.43 | 0.32 | 0.0% | 19.4% |
| Q4 | 32 | 0.46 | 1.06 | 0.0% | 43.8% |

## Wick-reject reversal (primary = outcome / opposite dir)

- Wick n=95; median **reject-dir** MFE=0.58R ATR; 1R/60m reject-dir=0.0%; median **break-dir** MFE=0.63R; 1R/60m break-dir=0.0%; fail(reject)=33.7%; immediate retrace=1.1%.
- Vs controls median MFE 0.54R / MAE 0.49R (matched outcome dir).

## Verdict

- Close confirmation vs wick tabulated above; do **not** promote Phase 5 without audit PASS + holdout.

