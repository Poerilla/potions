# NQ failure_fade broker-like replay

Engine + PaperBroker on **NQ daily**. Market entries fill next open (`live_after_ts`).

- Slippage: **1** tick · fee **$1.50**/unit · NQ $20/pt
- Sizing: **10** entry / **5** @ TP1 / remainder @ TP2

| Book | Trades | Units | Net $ | Stress DD $ | N/S | Win units |
|---|---:|---:|---:|---:|---:|---:|
| primary only (`nq_failure_fade_primary`) | 22 | 220 | -5564.75 | -295821.25 | -0.02 | 70 |
| fade+reclaim (`nq_failure_fade_reclaim`) | 34 | 340 | 43634.75 | -360658.50 | 0.12 | 110 |

## Notes

- Primary-only book disables reclaim (`enable_reclaim=false`).
- Fade+reclaim is the full sequence plugin.
- Expect PnL deltas vs pandas playbook (close fill vs next-open + resting OCO).

## Files

- `states/<slug>/fills.csv`
- `audits/`
