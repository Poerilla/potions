# Tick Replay Audit (NQ)

Manifest: `live/state/v2b_prior_opposed_execution_scrutiny/nq/tick_replay_manifest.csv`

| Rows | Conflicts |
|---:|---:|
| 10 | 0 |

Synthetic adverse path uses open→low→high for longs and open→high→low for shorts.
When trades DBN is unavailable, this is a conservative stand-in for tick reconstruction.
