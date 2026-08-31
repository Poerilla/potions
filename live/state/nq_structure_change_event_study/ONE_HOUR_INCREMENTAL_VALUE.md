# One-hour incremental value vs 4h

Same swing engine on 1h RTH bars. Tests A–E use **dev** CLOSE_BREAK invalidation where possible.

## B — 1h only CLOSE_BREAK

| Class | n | med MFE | 1R/60m | fail |
|---|---:|---:|---:|---:|
| 1h CLOSE_BREAK | 455 | 1.27 | 14.3% | 31.6% |
| 4h CLOSE_BREAK (A) | 126 | 0.56 | 0.0% | 28.6% |

## C/D — 4h bias alignment at 1h CLOSE_BREAK

| Test | n | med MFE | 1R/60m | fail |
|---|---:|---:|---:|---:|
| C aligned | 200 | 1.35 | 15.0% | 26.5% |
| D opposed | 173 | 1.34 | 15.6% | 35.8% |

Δ 1R rate (aligned 1h − 4h-only CLOSE_BREAK) = **+15.0 pp**.

## E — 1h break inside unchanged 4h bias

See opposed/aligned split above; opposed ≈ conflict / early reversal candidate.

## Verdict

- 1h is a separate signal layer; promote only if Δ survives holdout.

