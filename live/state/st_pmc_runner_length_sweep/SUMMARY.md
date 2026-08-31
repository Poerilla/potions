# ST+PMC long-runner length sweep (postprocess)

Source: `*_runners_2r_indef` tapes (US30 prefers `audits_lot_correct`).
Structure: TP1 + fixed 2R + long@k×TP1 (BE after TP1; BE starts the bar *after* TP1 fill).
Grid: k ∈ {2,3,4,5,6,7,8,9,10,12,15,indef}. JPY → USD normalized.

## Validation (k=10 vs archived 2R→10R)

| market | post pts | ref pts | diff | ok |
|---|---:|---:|---:|---|
| `us30` | 28789.6 | 28568.4 | 221.1 | **yes** |
| `nas100` | 12272.2 | 12322.2 | -50.0 | **yes** |
| `eurusd` | — | — | — | skipped_no_indef |
| `gbpusd` | — | — | — | skipped_no_indef |
| `usdjpy` | — | — | — | skipped_no_indef |

## Best finite k by N/S

| market | best k | N/S | net | stress | vs 3R | vs 10R |
|---|---:|---:|---:|---:|---|---|
| `us30` | **15** | **0.96** | $20955 | $-21762 | no | YES |
| `nas100` | **15** | **7.13** | $46338 | $-6498 | no | YES |
| `eurusd` | — | — | — | — | skipped_no_indef | — |
| `gbpusd` | — | — | — | — | skipped_no_indef | — |
| `usdjpy` | — | — | — | — | skipped_no_indef | — |

## Queued (waiting on indef tape)

`eurusd`, `gbpusd`, `usdjpy`

Postprocess appends automatically when `*_runners_2r_indef` unit_fills appear; no parallel StrategyPlugin rerun.

## Full grid

| market | k | net | stress | N/S | long pts | beats 3R? |
|---|---:|---:|---:|---:|---:|---|
| `us30` | 2 | $-3406 | $-22362 | -0.15 | 27009.7 |  |
| `us30` | 3 | $935 | $-22362 | 0.04 | 31350.5 |  |
| `us30` | 4 | $3419 | $-22362 | 0.15 | 33834.4 |  |
| `us30` | 5 | $5317 | $-22362 | 0.24 | 35733.0 |  |
| `us30` | 6 | $6949 | $-21912 | 0.32 | 37364.1 |  |
| `us30` | 7 | $12498 | $-21912 | 0.57 | 42913.8 |  |
| `us30` | 8 | $14556 | $-21912 | 0.66 | 44971.6 |  |
| `us30` | 9 | $16506 | $-21912 | 0.75 | 46921.2 |  |
| `us30` | 10 | $17207 | $-21912 | 0.79 | 47622.9 |  |
| `us30` | 12 | $16906 | $-21912 | 0.77 | 47321.2 |  |
| `us30` | 15 | $20955 | $-21762 | 0.96 | 51370.7 |  |
| `us30` | indef | $80175 | $-65214 | 1.23 | 110591.0 |  |
| `nas100` | 2 | $27191 | $-6345 | 4.29 | 18012.1 |  |
| `nas100` | 3 | $29423 | $-6498 | 4.53 | 20243.5 |  |
| `nas100` | 4 | $31046 | $-6498 | 4.78 | 21866.8 |  |
| `nas100` | 5 | $29204 | $-6498 | 4.49 | 20025.0 |  |
| `nas100` | 6 | $29053 | $-6498 | 4.47 | 19874.2 |  |
| `nas100` | 7 | $30703 | $-6498 | 4.72 | 21523.8 |  |
| `nas100` | 8 | $30810 | $-6498 | 4.74 | 21630.5 |  |
| `nas100` | 9 | $32609 | $-6498 | 5.02 | 23430.3 |  |
| `nas100` | 10 | $35309 | $-6498 | 5.43 | 26130.2 |  |
| `nas100` | 12 | $37788 | $-6498 | 5.82 | 28609.2 |  |
| `nas100` | 15 | $46338 | $-6498 | 7.13 | 37159.1 |  |
| `nas100` | indef | $54331 | $-6498 | 8.36 | 45152.2 |  |

## Notes

- Fair 3R alone cannot answer runner length (flat at TP1).
- 2R→10R censors k>10; indef tape is the uncensored source.
- Promote a k only if it beats **both** fair 3R N/S and k=10 N/S with max open 3.
- Promotion candidates this run: none.

## Artifacts

- `summary.csv`
- Per market: `<market>/sweep.csv`, `<market>/result.json`, `<market>/ns_vs_k.png`

