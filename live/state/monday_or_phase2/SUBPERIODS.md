# Monday OR Phase 2 — sub-period stability

Unit PnL from Phase 1 broker audits, sliced by exit timestamp.
Pass: positive net in ≥2/3 slices; no slice with N/S ≤ 0 while total still large.
Scope: core (EURUSD/USDJPY) + extended (GBPUSD/AUDJPY/XAUUSD). Silver excluded.

## EURUSD `M1_S2_R2`

| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |
|---|---:|---:|---:|---:|---|
| pre_2020 | 6076 | $+144465 | $-47238 | **3.06** | yes |
| 2020_2022 | 1081 | $-2557 | $-27295 | **-0.09** | NO |
| 2023_plus | 1133 | $-6202 | $-30150 | **-0.21** | NO |

**Slice pass count:** 1/3 → **FAIL**

## USDJPY `M2_S3_R1`

| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |
|---|---:|---:|---:|---:|---|
| pre_2020 | 5583 | $+153759 | $-22460 | **6.85** | yes |
| 2020_2022 | 998 | $+27951 | $-18751 | **1.49** | yes |
| 2023_plus | 1119 | $+37285 | $-22210 | **1.68** | yes |

**Slice pass count:** 3/3 → **PASS**

## USDJPY `M2_S3_R2`

| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |
|---|---:|---:|---:|---:|---|
| pre_2020 | 6650 | $+181407 | $-21433 | **8.46** | yes |
| 2020_2022 | 1168 | $+21806 | $-22224 | **0.98** | yes |
| 2023_plus | 1333 | $+24475 | $-25352 | **0.97** | yes |

**Slice pass count:** 3/3 → **PASS**

## GBPUSD `M1_S1_R2`

| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |
|---|---:|---:|---:|---:|---|
| pre_2020 | 6249 | $+252577 | $-76641 | **3.30** | yes |
| 2020_2022 | 1209 | $-5591 | $-62452 | **-0.09** | NO |
| 2023_plus | 1281 | $-2599 | $-27387 | **-0.09** | NO |

**Slice pass count:** 1/3 → **FAIL**

## AUDJPY `M1_S2_R2`

| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |
|---|---:|---:|---:|---:|---|
| pre_2020 | 5823 | $+78060 | $-47579 | **1.64** | yes |
| 2020_2022 | 1062 | $+2400 | $-42846 | **0.06** | yes |
| 2023_plus | 1160 | $+15472 | $-26751 | **0.58** | yes |

**Slice pass count:** 3/3 → **PASS**

## XAUUSD `M2_S2_R3`

| Slice | Units | ≈USD Net | Closed DD | **N/S** | Pass? |
|---|---:|---:|---:|---:|---|
| pre_2020 | 8905 | $+283497 | $-68247 | **4.15** | yes |
| 2020_2022 | 1539 | $-17931 | $-121072 | **-0.15** | NO |
| 2023_plus | 1695 | $+190582 | $-193880 | **0.98** | yes |

**Slice pass count:** 2/3 → **PASS**
