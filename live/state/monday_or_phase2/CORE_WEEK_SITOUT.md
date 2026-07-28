# Monday OR — core tune-ups (StrategyPlugin-locked)

Fill-proxy studies suggest candidates; **only broker-confirmed rules are core.**
See `tuneup_broker/SUMMARY.md`.

## Locked ON (broker-confirmed)

| Pair | Tag | Knobs | Net ≈$ | MTM DD ≈$ | N/S | vs Phase 1 |
|---|---|---|---:|---:|---:|---|
| **USDJPY** | `M2_S3_R1` | sitout +3 **+** skip Aug/Sep | **+293,966** | −27,726 | **10.60** | **+2.40 N/S · +$75k** |
| **USDJPY** | `M2_S3_R2` | skip-1-after-2W **+** skip Aug/Sep | **+300,288** | −28,278 | **10.62** | **+2.43 N/S · +$73k** |
| **XAUUSD** | `M2_S2_R3` | sitout +100 **+** skip Jul/Sep/Dec | **+580,139** | **−172,265** | **3.37** | **+1.47 N/S · +$142k** |

### USDJPY ladder (`M2_S3_R1`)

| Stage | Net ≈$ | MTM DD ≈$ | N/S |
|---|---:|---:|---:|
| Phase 1 | +218,890 | −26,688 | 8.20 |
| + sitout +3 | +243,506 | −27,726 | 8.78 |
| **+ sitout +3 + skip Aug/Sep (core)** | **+293,966** | −27,726 | **10.60** |

### XAUUSD ladder

| Stage | Net ≈$ | MTM DD ≈$ | N/S |
|---|---:|---:|---:|
| Phase 1 | +437,940 | −230,359 | 1.90 |
| + sitout +100 | +510,243 | −214,892 | 2.37 |
| **+ sitout +100 + skip Jul/Sep/Dec (core)** | **+580,139** | **−172,265** | **3.37** |

Sources: `monday_or_breakout.py`, `monday_or_phase2_tags.py` (`PAIR_TUNEUPS`), `plugin_config(..., pair=)`.

## Rejected after StrategyPlugin audit

| Pair | Tag | Candidate | Broker result |
|---|---|---|---|
| EURUSD | `M1_S2_R2` | skip-1-after-W | N/S 1.74→1.79 but **net −$11k** → OFF |
| GBPUSD | `M1_S1_R2` | skip-1-after-W | N/S **2.67→1.60**; **net −$67k** → OFF |
| AUDJPY | `M1_S2_R2` | skip-1-after-2W / Jul–Sep–Dec transplant | fill-proxy or hurts → OFF |

## Notes

- Do **not** copy gold’s Jul/Sep/Dec onto USDJPY (Dec is strong for JPY).
- Do **not** copy USDJPY’s Aug/Sep onto gold without a fresh study.
- Pre-tune baselines: `BASELINE_PRE_TUNE.md`.
