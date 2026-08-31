# COMPARISON_BOARD — OCO stop v1 vs limit-retest controls

**study_id:** `nq_wick_reject_range_seed_oco_stop_v1`
**Updated:** 2026-08-30 12:03 ET
**Stance:** RESEARCH ONLY — OCO stop v1 does not clear promotion gates

## Locked books (decision = primary FILLED; AMBIGUOUS excluded)

| Book | seeds | fills | fill% | net $ | avg $ | WR | PF | avg R | med R | stop% | TP1/2/3% | gap_stop | L/S | top1/3/5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| oco_stop_v1_primary_dev | 74 | 74 | 100% | -5414 | -73 | 49% | 0.89 | +0.052 | -0.147 | 55% | 80/55/34 | 3 | 43/31 | 9/23/35 |
| oco_stop_v1_primary_holdout | 17 | 17 | 100% | +2579 | +152 | 47% | 1.09 | +0.013 | -0.252 | 59% | 65/47/41 | 0 | 6/11 | 11/30/47 |
| oco_stop_v1_primary_ALL | 91 | 91 | 100% | -2836 | -31 | 48% | 0.96 | +0.045 | -0.193 | 56% | 77/54/35 | 3 | 49/42 | 6/14/22 |
| oco_stop_v1_stress_2tick_dev | 74 | 74 | 100% | -6154 | -83 | 49% | 0.88 | +0.037 | -0.153 | 55% | 80/55/34 | 3 | 43/31 | 9/23/35 |
| oco_stop_v1_stress_2tick_holdout | 17 | 17 | 100% | +2409 | +142 | 47% | 1.08 | +0.011 | -0.254 | 59% | 65/47/41 | 0 | 6/11 | 11/30/47 |
| oco_stop_v1_stress_2tick_ALL | 91 | 91 | 100% | -3746 | -41 | 48% | 0.95 | +0.032 | -0.204 | 56% | 77/54/35 | 3 | 49/42 | 6/14/22 |
| oco_stop_v1_stress_adverse_coll_dev | 74 | 74 | 100% | -5414 | -73 | 49% | 0.89 | +0.052 | -0.147 | 55% | 80/55/34 | 3 | 43/31 | 9/23/35 |
| oco_stop_v1_stress_adverse_coll_holdout | 17 | 17 | 100% | +2579 | +152 | 47% | 1.09 | +0.013 | -0.252 | 59% | 65/47/41 | 0 | 6/11 | 11/30/47 |
| oco_stop_v1_stress_adverse_coll_ALL | 91 | 91 | 100% | -2836 | -31 | 48% | 0.96 | +0.045 | -0.193 | 56% | 77/54/35 | 3 | 49/42 | 6/14/22 |

### Prior limit-retest hub (frozen)

| primary_limit_retest_dev | 74 | 53 | 72% | +23880 | +451 | 57% | 1.90 | +0.177 | +0.249 | 55% | 75/55/34 | 7 | 33/20 | 11/25/39 |
| primary_limit_retest_holdout | 17 | 14 | 82% | +5467 | +390 | 43% | 1.27 | -0.036 | -0.250 | 64% | 64/43/36 | 0 | 7/7 | 14/39/58 |
| primary_limit_retest_ALL | 91 | 67 | 74% | +29346 | +438 | 54% | 1.62 | +0.132 | +0.249 | 57% | 73/52/34 | 7 | 40/27 | 7/17/26 |
| ctrl_immediate_break_dev | 74 | 74 | 100% | +7182 | +97 | 54% | 1.19 | +0.015 | +0.089 | 46% | 86/69/42 | 7 | 46/28 | 7/20/31 |
| ctrl_immediate_break_holdout | 17 | 17 | 100% | -3107 | -183 | 53% | 0.89 | -0.096 | +0.041 | 53% | 71/53/47 | 0 | 9/8 | 14/34/49 |
| ctrl_immediate_break_ALL | 91 | 91 | 100% | +4074 | +45 | 54% | 1.06 | -0.005 | +0.045 | 47% | 84/66/43 | 7 | 55/36 | 6/14/22 |
| ctrl_marketable_boundary_dev | 74 | 74 | 100% | +37767 | +510 | 69% | 2.37 | +0.347 | +0.676 | 46% | 86/69/42 | 7 | 46/28 | 9/21/33 |
| ctrl_marketable_boundary_holdout | 17 | 17 | 100% | +16128 | +949 | 53% | 1.75 | +0.146 | +0.250 | 53% | 71/53/47 | 0 | 9/8 | 11/31/49 |
| ctrl_marketable_boundary_ALL | 91 | 91 | 100% | +53894 | +592 | 66% | 2.10 | +0.309 | +0.664 | 47% | 84/66/43 | 7 | 55/36 | 5/14/21 |

## Long vs short

| Side | n | net $ | avg $ | WR | PF | avg R | med R | stop% | gap_entry | gap_stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| LONG | 49 | +21712 | +443 | 53% | 1.80 | +0.133 | +0.183 | 47% | 15 | 2 |
| SHORT | 42 | -24547 | -584 | 43% | 0.54 | -0.058 | -0.257 | 67% | 8 | 1 |

## First high-break vs first low-break

_For OCO, first boundary fill **is** the directional break (HIGH→LONG, LOW→SHORT). Same table as Long vs short above._

## Seed width quartiles (descriptive only)

| Quartile | n | width med | avg R | net $ | WR |
|---|---:|---:|---:|---:|---:|
| Q1 | 23 | 18.50 | +0.127 | +510 | 48% |
| Q2 | 23 | 37.25 | -0.026 | -1404 | 43% |
| Q3 | 22 | 93.00 | +0.099 | +3588 | 55% |
| Q4 | 23 | 287.25 | -0.019 | -5529 | 48% |

## Seed → break duration (OCO: available → fill)

| Stat | minutes |
|---|---:|
| n | 91 |
| mean | 454.3 |
| median | 28.0 |
| p25 | 1.0 |
| p75 | 138.5 |
| max | 5620.0 |


## Gap-through frequency

| Event | n | rate among fills |
|---|---:|---:|
| Entry gap-through | 23 | 25.3% |
| Stop exit gap-through | 3 | 3.3% |

## Concentration (primary ALL fills)

Top1 / Top3 / Top5 |net| share: **5.6% / 14.2% / 22.2%**.

## Development / holdout timing parity

| Slice | seeds | fills | ambig | expired | med seed→fill min | med fill→exit min |
|---|---:|---:|---:|---:|---:|---:|
| dev | 74 | 74 | 0 | 0 | 23.5 | 3013.0 |
| holdout | 17 | 17 | 0 | 0 | 84.0 | 4147.0 |

## 2-tick adverse entry stress (clean fills; collisions still excluded)

| oco_stop_v1_stress_2tick_ALL | 91 | 91 | 100% | -3746 | -41 | 48% | 0.95 | +0.032 | -0.204 | 56% | 77/54/35 | 3 | 49/42 | 6/14/22 |

## Every OCO collision + resolution

See `AMBIGUITY_AUDIT.md`, `oco_collisions_primary_excluded.csv`,
`oco_collisions_stress_adverse.csv`. Primary excluded count: **0**.

## Decision rule checklist

- PASS: Development and holdout both positive avg campaign R
- FAIL: Holdout PF materially above 1 after costs (PF>1.15)
- FAIL: OCO primary remains positive under 2-tick adverse entry stress
- PASS: No hidden favorable resolution of same-minute two-sided breaks
- FAIL: Results not dominated by few campaigns / 2W runners (top5 |net| share=22%, TP3 win share=79%)
- PASS: Campaign count sufficient; long and short paths present

## Honest read

OCO fails under ordinary stop-entry friction on locked **dev** (net=-5414, avgR=+0.052). The synthetic marketable-at-boundary control was an **execution assumption**, not a tradeable edge under stop fills.
Frozen synthetic marketable ALL: net=+53894 avgR=+0.309 (not tradable as-stated).
