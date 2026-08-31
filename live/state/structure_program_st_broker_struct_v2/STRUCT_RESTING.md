# Structure-only resting entry (no ST signal)

## Intent
Resting limit at the current program structure key (buy→bull LL, sell→bear HH)
**without** requiring an ST break to arm. Enter any day the limit is hit.
Exits still use `scale_run` + `fav_be` ST-flip→BE.

## Guards (v2 — after churn bug)
First impl (TRL-2026-00082) re-armed into marketable limits every exit → 43k
campaigns / −$1.8B. Fixed path:
1. Submit entry intent **once** per arm
2. Arm only when limit is **non-marketable** (long: close > key; short: close < key)
3. **Consume** the key after fill / blow / program flip until a new structure key prints

## Broker result (TRL-2026-00083)

| | ST-gated scale_run | structure_only resting |
|--|--:|--:|
| Trades | 228 | 493 |
| Net | −$103k | **−$2.13M** |
| PF | 0.70 | **0.185** |
| Unit WR | 7.9% | 6.6% |
| hold≤1 share | 69% | 82% |
| hold≤1 $ | −$258k | **−$2.55M** |
| hold>1 $ | +$155k | +$421k |

**FAIL** — dropping the ST entry filter adds more short-hold deaths; survivors stay green but are swamped.

Artifacts: this directory. Invalid churn run kept at
`../structure_program_st_broker_struct/` for forensics only.
