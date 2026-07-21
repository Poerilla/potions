# Monday OR Phase 2 — SUMMARY

**Status: Phase 2 complete** (core + extended ex-silver, 2026-07-21).

## Locked / extended candidates

| Pair | Tag | Role |
|---|---|---|
| EURUSD | `M1_S2_R2` | Core — paper-only if sub-period FAIL |
| USDJPY | `M2_S3_R1` | Core primary |
| USDJPY | `M2_S3_R2` | Core alternate |
| GBPUSD | `M1_S1_R2` | Extended |
| AUDJPY | `M1_S2_R2` | Extended |
| XAUUSD | `M2_S2_R3` | Extended — heat caution |
| XAGUSD | — | **Excluded** (Phase 1 reject) |

## Robustness verdict

### Sub-periods

- EURUSD `M1_S2_R2`: 1/3 slices positive N/S → **FAIL**
- USDJPY `M2_S3_R1`: 3/3 slices positive N/S → **PASS**
- USDJPY `M2_S3_R2`: 3/3 slices positive N/S → **PASS**
- GBPUSD `M1_S1_R2`: 1/3 slices positive N/S → **FAIL**
- AUDJPY `M1_S2_R2`: 3/3 slices positive N/S → **PASS**
- XAUUSD `M2_S2_R3`: 2/3 slices positive N/S → **PASS**

### Clustering

- EURUSD `M1_S2_R2`: top-week 13.1%, top-5% weeks 36.0% → FLAG
- USDJPY `M2_S3_R1`: top-week 6.0%, top-5% weeks 29.8% → OK
- USDJPY `M2_S3_R2`: top-week 5.0%, top-5% weeks 30.2% → OK
- GBPUSD `M1_S1_R2`: top-week 18.4%, top-5% weeks 33.8% → FLAG
- AUDJPY `M1_S2_R2`: top-week 20.0%, top-5% weeks 38.6% → FLAG
- XAUUSD `M2_S2_R3`: top-week 19.3%, top-5% weeks 39.9% → FLAG

### Sensitivity

- AUDJPY `M1_S2_R2` dd25_45: ΔN/S -13% → PASS
- AUDJPY `M1_S2_R2` dd35_55: ΔN/S +26% → PASS
- EURUSD `M1_S2_R2` dd25_45: ΔN/S +35% → PASS
- EURUSD `M1_S2_R2` dd35_55: ΔN/S +8% → PASS
- GBPUSD `M1_S1_R2` dd25_45: ΔN/S -8% → PASS
- GBPUSD `M1_S1_R2` dd35_55: ΔN/S +3% → PASS
- USDJPY `M2_S3_R1` dd25_45: ΔN/S -20% → PASS
- USDJPY `M2_S3_R1` dd35_55: ΔN/S +1% → PASS
- XAUUSD `M2_S2_R3` dd25_45: ΔN/S -19% → PASS
- XAUUSD `M2_S2_R3` dd35_55: ΔN/S -13% → PASS

## Artifacts

- [`PERTURBATIONS.md`](PERTURBATIONS.md)
- [`SUBPERIODS.md`](SUBPERIODS.md)
- [`CLUSTERING.md`](CLUSTERING.md)
- [`SENSITIVITY.md`](SENSITIVITY.md)
- [`DEPLOYMENT_RULES.md`](DEPLOYMENT_RULES.md)
- Specs: `SPEC_EURUSD_*`, `SPEC_USDJPY_*`, `SPEC_GBPUSD_*`, `SPEC_AUDJPY_*`, `SPEC_XAUUSD_*`

## Do-not-cross-use

- EURUSD / AUDJPY light-sidecar `M1_S2_R2` ≠ USDJPY `M2_S3_*`
- GBPUSD matched `M1_S1_R2` is its own recipe
- XAUUSD `M2_S2_R3` is heat-heavy — not a clean FX sleeve clone
- XAGUSD excluded
