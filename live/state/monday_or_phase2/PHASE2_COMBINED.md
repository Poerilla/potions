# Monday OR Phase 2 — Combined document (copy-paste)
Generated for convenience. **Originals are unchanged** in this folder.
Instruments: EURUSD, USDJPY, GBPUSD, AUDJPY, XAUUSD. **XAGUSD excluded**.

---


<!-- ===== SUMMARY.md ===== -->

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


---


<!-- ===== INDEX.md ===== -->

# Monday OR Phase 2 hub

See [`SUMMARY.md`](SUMMARY.md).

Pair defaults: `live/monday_or_phase2_tags.py` → {"AUDJPY": "M1_S2_R2", "EURUSD": "M1_S2_R2", "GBPUSD": "M1_S1_R2", "USDJPY": "M2_S3_R1", "XAUUSD": "M2_S2_R3"}


---


<!-- ===== DEPLOYMENT_RULES.md ===== -->

# Monday OR Phase 2 — live deployment rules

**Status:** Phase 2 complete — core + extended ex-silver (2026-07-21).  
**Excluded:** XAGUSD (Phase 1 reject).

## Funding gates (paper → live)

| Pair | Tag | Min Net/Stress | Min PF | Worst-year DD gate | Robustness / stance |
|---|---|---:|---:|---|---|
| **USDJPY** | `M2_S3_R1` | **≥ 4.0** | ≥ 1.15 | ≤ baseline worst year × 1.2 | Sub-periods **PASS** 3/3 → **live/paper eligible** |
| **USDJPY** | `M2_S3_R2` | ≥ 4.0 | ≥ 1.15 | same | Dollar alternate |
| **AUDJPY** | `M1_S2_R2` | ≥ 1.5 | ≥ 1.15 | same | Sub-periods **PASS** 3/3; clustering FLAG → **small satellite only** |
| **XAUUSD** | `M2_S2_R3` | ≥ 1.5 | ≥ 1.15 | same + **stress budget** | Sub-periods PASS 2/3; heat −$230k → **default do-not-fund** / opportunistic |
| **EURUSD** | `M1_S2_R2` | ≥ 1.5 | ≥ 1.15 | same | Sub-periods **FAIL** → **paper-only** |
| **GBPUSD** | `M1_S1_R2` | ≥ 1.5 | ≥ 1.15 | same | Sub-periods **FAIL** → **paper-only** |
| **XAGUSD** | — | — | — | — | **Excluded** |

### Operational read

- **Primary book:** USDJPY Monday OR under caps below.
- **Satellite (optional):** AUDJPY at small size if clustering concentration is accepted.
- **Paper-only:** EURUSD, GBPUSD until post-2019 slices recover.
- **Gold:** dollars exist but heat dominates — not a core sleeve; silver stays out.

## Initial capital caps

| Sleeve | Initial notional equiv. | Rationale |
|---|---|---|
| USDJPY Monday OR | **3–5M** | Strongest N/S (8.20) |
| AUDJPY Monday OR | **0.5–1.5M** | Satellite; smaller edge |
| EURUSD / GBPUSD | **1–2M / 2–3M paper band** | Reserved; live blocked on sub-period fail |
| XAUUSD | **≤1M** if ever | Stress-budget limited |
| XAGUSD | **0** | Excluded |
| Futures intraday | Separate book | Not fungible with FX Monday OR caps |

## Scaling rule

Increase notional by **1.5×** only after **6–12 months** live (or funded paper) performance stays within:

- Backtest Net/Stress band: ≥ 80% of Phase 1 broker N/S for that tag
- Drawdown band: live max DD ≤ 1.2 × backtest stress |DD|

If either band breaks: freeze size, review, do not scale.

## Do-not-cross-use

- EURUSD / AUDJPY → **`M1_S2_R2`** (light shifted) — pair-specific live decisions still apply.
- GBPUSD → **`M1_S1_R2`** (matched sidecar).
- USDJPY → **`M2_S3_R1` / `M2_S3_R2`** only.
- XAUUSD → **`M2_S2_R3`** only if stress-approved; never copy onto FX majors.
- Never transplant USDJPY heavy sizing onto EUR/GBP/AUD.

## Config source

Pair-tag knobs: [`live/monday_or_phase2_tags.py`](../../monday_or_phase2_tags.py).  
Broker driver: [`live/fx_monday_or_breakout_broker.py`](../../fx_monday_or_breakout_broker.py).  
Specs: `SPEC_*.md` in this folder.

## Phase 3

USDJPY-first track-record; optional AUDJPY satellite; EUR/GBP re-entry only after regime pass; gold opportunistic only; silver out.


---


<!-- ===== PERTURBATIONS.md ===== -->

# Monday OR Phase 2 — local perturbations

Narrow cells only (not a full re-sweep). Metrics from Phase 1 broker CSV.

| Pair | Tag | Role | ≈USD Net | Stress | **N/S** | Δ vs anchor N/S |
|---|---|---|---:|---:|---:|---:|
| EURUSD | `M1_S2_R2` | anchor | $+123271 | $-70858 | **1.74** | +0.00 |
| EURUSD | `M1_S2_R1` | EURUSD tighter R | $+78069 | $-82778 | **0.94** | -0.80 |
| USDJPY | `M2_S3_R1` | anchor | $+218890 | $-26688 | **8.20** | +0.00 |
| USDJPY | `M2_S3_R2` | USDJPY alt | $+227564 | $-27802 | **8.19** | -0.02 |
| USDJPY | `M2_S2_R1` | robustness | $+151778 | $-26801 | **5.66** | -2.54 |

## Read

- EURUSD `M1_S2_R1` (max 2/week) **hurts** N/S vs locked `R2` — keep max 3/week.
- USDJPY `M2_S3_R1` ≈ `M2_S3_R2` (8.20 vs 8.19) — retain R1 primary, R2 as dollar alt.
- USDJPY lighter sidecar `M2_S2_R1` (5.66) is weaker but still strong — heavy sidecar is the edge amplifier, not the whole edge.

*Generated from Phase 1 broker results.*


---


<!-- ===== SUBPERIODS.md ===== -->

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


---


<!-- ===== CLUSTERING.md ===== -->

# Monday OR Phase 2 — Monday / week clustering

Contribution of calendar weeks (Mon-start NY) to lifetime unit PnL.
Flag if any single week > 8% of lifetime |net| or top 5% of weeks capture >50% of gross positive week PnL.
Scope: core + extended (ex-silver).

## EURUSD `M1_S2_R2`

| Metric | Value |
|---|---|
| Weeks with PnL | 1179 |
| Lifetime ≈USD net | $+135706 |
| Top week | 2010-05-03 ($+17797, **13.1%**) |
| Top 5% weeks (n=59) share of gross + | **36.0%** |
| Abs-PnL HHI | 0.0016 |
| Concentration flag | YES — review |

Top 10 weeks:

| Week | ≈USD Net | Share |
|---|---:|---:|
| 2010-05-03 | $+17797 | 13.11% |
| 2009-05-18 | $+13254 | 9.77% |
| 2008-09-29 | $+13100 | 9.65% |
| 2008-10-20 | $+12223 | 9.01% |
| 2009-03-16 | $+12072 | 8.90% |
| 2020-03-16 | $+10466 | 7.71% |
| 2010-05-10 | $+10437 | 7.69% |
| 2010-11-22 | $+10200 | 7.52% |
| 2025-03-03 | $+10185 | 7.51% |
| 2009-12-14 | $+9783 | 7.21% |

## USDJPY `M2_S3_R1`

| Metric | Value |
|---|---|
| Weeks with PnL | 1175 |
| Lifetime ≈USD net | $+218995 |
| Top week | 2022-11-07 ($+13112, **6.0%**) |
| Top 5% weeks (n=59) share of gross + | **29.8%** |
| Abs-PnL HHI | 0.0014 |
| Concentration flag | no |

Top 10 weeks:

| Week | ≈USD Net | Share |
|---|---:|---:|
| 2022-11-07 | $+13112 | 5.99% |
| 2008-10-20 | $+11564 | 5.28% |
| 2023-01-09 | $+10491 | 4.79% |
| 2008-10-27 | $+10316 | 4.71% |
| 2022-08-15 | $+8924 | 4.07% |
| 2005-12-12 | $+8597 | 3.93% |
| 2008-02-25 | $+8313 | 3.80% |
| 2024-09-30 | $+8086 | 3.69% |
| 2025-03-31 | $+7682 | 3.51% |
| 2023-07-10 | $+7654 | 3.50% |

## USDJPY `M2_S3_R2`

| Metric | Value |
|---|---|
| Weeks with PnL | 1175 |
| Lifetime ≈USD net | $+227688 |
| Top week | 2022-11-07 ($+11352, **5.0%**) |
| Top 5% weeks (n=59) share of gross + | **30.2%** |
| Abs-PnL HHI | 0.0015 |
| Concentration flag | no |

Top 10 weeks:

| Week | ≈USD Net | Share |
|---|---:|---:|
| 2022-11-07 | $+11352 | 4.99% |
| 2016-02-01 | $+10875 | 4.78% |
| 2023-01-09 | $+10491 | 4.61% |
| 2008-10-20 | $+10308 | 4.53% |
| 2010-05-03 | $+9840 | 4.32% |
| 2013-06-10 | $+9740 | 4.28% |
| 2022-08-15 | $+8924 | 3.92% |
| 2007-08-13 | $+8655 | 3.80% |
| 2005-12-12 | $+8597 | 3.78% |
| 2008-02-25 | $+8313 | 3.65% |

## GBPUSD `M1_S1_R2`

| Metric | Value |
|---|---|
| Weeks with PnL | 1187 |
| Lifetime ≈USD net | $+244388 |
| Top week | 2008-10-20 ($+44960, **18.4%**) |
| Top 5% weeks (n=60) share of gross + | **33.8%** |
| Abs-PnL HHI | 0.0016 |
| Concentration flag | YES — review |

Top 10 weeks:

| Week | ≈USD Net | Share |
|---|---:|---:|
| 2008-10-20 | $+44960 | 18.40% |
| 2009-01-19 | $+18744 | 7.67% |
| 2020-03-23 | $+15809 | 6.47% |
| 2009-05-18 | $+15518 | 6.35% |
| 2009-03-30 | $+15204 | 6.22% |
| 2009-01-05 | $+13344 | 5.46% |
| 2004-05-24 | $+12608 | 5.16% |
| 2008-08-04 | $+11964 | 4.90% |
| 2004-01-05 | $+11817 | 4.84% |
| 2008-08-11 | $+11688 | 4.78% |

## AUDJPY `M1_S2_R2`

| Metric | Value |
|---|---|
| Weeks with PnL | 1153 |
| Lifetime ≈USD net | $+95932 |
| Top week | 2008-10-20 ($+19171, **20.0%**) |
| Top 5% weeks (n=58) share of gross + | **38.6%** |
| Abs-PnL HHI | 0.0018 |
| Concentration flag | YES — review |

Top 10 weeks:

| Week | ≈USD Net | Share |
|---|---:|---:|
| 2008-10-20 | $+19171 | 19.98% |
| 2010-05-17 | $+17536 | 18.28% |
| 2008-10-06 | $+13126 | 13.68% |
| 2008-10-27 | $+13019 | 13.57% |
| 2009-11-23 | $+11591 | 12.08% |
| 2008-09-01 | $+11533 | 12.02% |
| 2005-12-12 | $+11209 | 11.68% |
| 2015-12-07 | $+10144 | 10.57% |
| 2020-06-01 | $+9185 | 9.57% |
| 2025-03-31 | $+9122 | 9.51% |

## XAUUSD `M2_S2_R3`

| Metric | Value |
|---|---|
| Weeks with PnL | 1169 |
| Lifetime ≈USD net | $+456148 |
| Top week | 2026-03-16 ($+88031, **19.3%**) |
| Top 5% weeks (n=59) share of gross + | **39.9%** |
| Abs-PnL HHI | 0.0023 |
| Concentration flag | YES — review |

Top 10 weeks:

| Week | ≈USD Net | Share |
|---|---:|---:|
| 2026-03-16 | $+88031 | 19.30% |
| 2026-01-19 | $+86334 | 18.93% |
| 2025-04-07 | $+54915 | 12.04% |
| 2025-04-14 | $+35568 | 7.80% |
| 2020-08-10 | $+32529 | 7.13% |
| 2011-09-19 | $+31883 | 6.99% |
| 2025-05-19 | $+29655 | 6.50% |
| 2026-03-02 | $+29541 | 6.48% |
| 2008-09-15 | $+28795 | 6.31% |
| 2024-11-18 | $+25794 | 5.65% |


---


<!-- ===== SENSITIVITY.md ===== -->

# Monday OR Phase 2 — DD threshold sensitivity

Nudges around 30%/50% on locked size tags only. Pass if net > 0 and N/S drop ≤ ~30% vs anchor.

| Pair | Tag | Slug | DD | ≈USD Net | Stress | **N/S** | Δ N/S | Pass |
|---|---|---|---|---:|---:|---:|---:|---|
| AUDJPY | `M1_S2_R2` | anchor_30_50 | 30/50 | $+95822 | $-52242 | **1.83** | +0% | yes |
| AUDJPY | `M1_S2_R2` | dd25_45 | 25/45 | $+78231 | $-49063 | **1.59** | -13% | yes |
| AUDJPY | `M1_S2_R2` | dd35_55 | 35/55 | $+128457 | $-55485 | **2.32** | +26% | yes |
| EURUSD | `M1_S2_R2` | anchor_30_50 | 30/50 | $+123271 | $-70858 | **1.74** | +0% | yes |
| EURUSD | `M1_S2_R2` | dd25_45 | 25/45 | $+142361 | $-60563 | **2.35** | +35% | yes |
| EURUSD | `M1_S2_R2` | dd35_55 | 35/55 | $+102368 | $-54702 | **1.87** | +8% | yes |
| GBPUSD | `M1_S1_R2` | anchor_30_50 | 30/50 | $+231279 | $-86616 | **2.67** | +0% | yes |
| GBPUSD | `M1_S1_R2` | dd25_45 | 25/45 | $+234107 | $-95723 | **2.45** | -8% | yes |
| GBPUSD | `M1_S1_R2` | dd35_55 | 35/55 | $+259305 | $-93915 | **2.76** | +3% | yes |
| USDJPY | `M2_S3_R1` | anchor_30_50 | 30/50 | $+218890 | $-26688 | **8.20** | +0% | yes |
| USDJPY | `M2_S3_R1` | dd25_45 | 25/45 | $+208999 | $-31757 | **6.58** | -20% | yes |
| USDJPY | `M2_S3_R1` | dd35_55 | 35/55 | $+225419 | $-27240 | **8.28** | +1% | yes |
| XAUUSD | `M2_S2_R3` | anchor_30_50 | 30/50 | $+437940 | $-230359 | **1.90** | +0% | yes |
| XAUUSD | `M2_S2_R3` | dd25_45 | 25/45 | $+382005 | $-246558 | **1.55** | -19% | yes |
| XAUUSD | `M2_S2_R3` | dd35_55 | 35/55 | $+402718 | $-243249 | **1.66** | -13% | yes |

*Driver: `live/monday_or_phase2_robustness.py`.*


---


<!-- ===== SPEC_USDJPY_M2_S3_R1.md ===== -->

# SPEC — USDJPY Monday OR `M2_S3_R1`

**Status:** Phase 2 default candidate · eligible for limited live / funded paper under caps.  
**Alternate:** `M2_S3_R2` (max 3/week) — near-tie N/S 8.19, slightly higher dollars.  
**Plugin:** `monday_or_breakout` · `live/monday_or_phase2_tags.py`.

## Logic (plain English)

Same Monday OR framework as EURUSD: Mon H/L → Tue–Fri 15m close breakout → SL 1R / TP 2R → DD ladder → shifted primary at opposite Mon extreme after flat@50% → HTF both-opposed skip. USDJPY uses a **runner-heavier main** (cut only 1 at 30%, hold 2 to 50%) and a **heavier shifted sidecar** (4 units), with a tighter weekly cap (max 2 primaries).

## Parameter tags

| Tag | Meaning |
|---|---|
| `M2` | Main 3 = 1@30% DD, 2@50% DD |
| `S3` | Shifted 4 = 2@30% DD, 2@50% DD |
| `R1` | Max **2** primary trades/week (primary) |
| `R2` | Max **3**/week (alternate `M2_S3_R2`) |

## Key metrics (broker Phase 1)

| Metric | `M2_S3_R1` | `M2_S3_R2` alt |
|---|---:|---:|
| ≈USD Net | +$218.9k | +$227.6k |
| Stress DD | −$26.7k | −$27.8k |
| **Net/Stress** | **8.20** | **8.19** |
| Baseline `M1_S1_R1` N/S | 4.27 | 4.27 |

Pandas pick `M3_S3_R2` is broker #3 (7.54) — research-only.

## Behaviour summary

USDJPY rewards thrust + stop-run / opposite-extreme follow-through: keep more size deeper into the DD ladder on the main leg and size up the shifted sidecar. EURUSD’s light-sidecar recipe ranks near the bottom on this pair.

## Robustness (Phase 2)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 3/3 (pre-2020, 2020–22, 2023+) |
| Clustering | OK — top week ~6%; top 5% weeks ~30% of gross positive |
| Lighter sidecar `M2_S2_R1` | N/S 5.66 — still strong; heavy sidecar amplifies |
| DD sensitivity | **PASS** — 25/45 N/S 6.58 (−20%); 35/55 N/S 8.28 |

## Capacity sketch

Initial **3–5M** notional equivalent. USDJPY is among the deepest FX markets; at this sleeve size, liquidity is not the binding constraint — operational DD and live tracking are.

## Do-not-cross-use

Do not deploy EURUSD `M1_S2_R2` sizing on USDJPY.

## Deployment

See [`DEPLOYMENT_RULES.md`](DEPLOYMENT_RULES.md). Scale +1.5× after 6–12 months within BT N/S and DD bands.


---


<!-- ===== SPEC_EURUSD_M1_S2_R2.md ===== -->

# SPEC — EURUSD Monday OR `M1_S2_R2`

**Status:** Phase 2 candidate · **paper-only** until sub-period gate passes.  
**Plugin:** `monday_or_breakout` · config via `live/monday_or_phase2_tags.py`.

## Logic (plain English)

Each Monday defines an opening range (high/low). Tue–Fri, on 15m close, trade breakouts of that range (long above Mon high, short below Mon low). Enter 3 units with SL = 1R and TP = 2R. Cut 2 units at 30% of the way to the stop and flatten the last unit at 50% (no runner past 50% DD). After a primary flats at 50% DD, arm a **shifted primary** at the **opposite** Monday extreme (same DD ladder, lighter size). Skip entries when the last completed 1h bar has both MA50/150 and OBV vs OBV-SMA20 opposed to the trade. Cap at 3 primary entries per week.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M1` | Main 3 = 2@30% DD, 1@50% DD |
| `S2` | Shifted 2 = 1@30% DD, 1@50% DD (lighter sidecar) |
| `R2` | Max **3** primary trades/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$123.3k |
| Stress DD | −$70.9k |
| **Net/Stress** | **1.74** |
| Baseline `M1_S1_R1` N/S | 0.83 |
| vs ST+PMC EURUSD | Beats 1.49 on full-sample N/S |

PF / win rate / worst year: see Phase 1 audit under `live/state/monday_or_sizing_sweep_broker/audits/eurusd_m1_s2_r2/`.

## Behaviour summary

Exploits Monday OR breakouts with early risk truncation and a light opposite-extreme second chance. EURUSD does **not** reward heavy runner or heavy sidecar sizing (those lag in Phase 1).

## Robustness (Phase 2)

| Check | Result |
|---|---|
| Sub-periods | **FAIL** — pre-2020 strong; 2020–2022 and 2023+ negative unit net |
| Clustering | FLAG — top week ~13% of lifetime |net| (2010-05-03) |
| Local R tweak | `M1_S2_R1` N/S 0.94 — worse; keep R2 |
| DD sensitivity | **PASS** — 25/45 N/S 2.35; 35/55 N/S 1.87 (vs 1.74) |

## Capacity sketch

Initial paper band **1–2M** notional equivalent. Major-pair FX liquidity is ample at this size; impact risk is secondary to **regime fragility** documented above.

## Do-not-cross-use

Do not use USDJPY `M2_S3_*` sizing on EURUSD.

## Deployment

See [`DEPLOYMENT_RULES.md`](DEPLOYMENT_RULES.md). Fund live only after restoring ≥2/3 positive sub-period slices (filter or re-validation).


---


<!-- ===== SPEC_GBPUSD_M1_S1_R2.md ===== -->

# SPEC — GBPUSD Monday OR `M1_S1_R2`

**Status:** Phase 2 extended · **paper-only** (sub-period FAIL).  
**Plugin:** `monday_or_breakout` · `live/monday_or_phase2_tags.py`.

## Logic (plain English)

Monday OR → Tue–Fri 15m close breakout → main 3 lots with DD ladder (2@30%, 1@50%) → shifted primary at opposite Mon extreme after flat@50% with **matched** 3-lot structure → HTF both-opposed skip → max **3** primary entries/week.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M1` | Main 3 = 2@30%, 1@50% |
| `S1` | Shifted 3 = same as main |
| `R2` | Max **3** primary/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$231k |
| Stress DD | −$87k |
| **Net/Stress** | **2.67** |
| Baseline `M1_S1_R1` | 1.87 |

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **FAIL** (1/3) — same pattern as EURUSD: pre-2020 carries the book |
| Clustering | FLAG — top week ~18% of lifetime \|net\| |
| DD sensitivity | **PASS** — 25/45 N/S 2.45; 35/55 N/S 2.76 |

## Capacity sketch

Reserve **2–3M** notional for paper; do not fund live until ≥2/3 positive sub-period slices.

## Do-not-cross-use

Do not use USDJPY `M2_S3_*` or EURUSD light-sidecar sizing on GBPUSD without a fresh sweep.


---


<!-- ===== SPEC_AUDJPY_M1_S2_R2.md ===== -->

# SPEC — AUDJPY Monday OR `M1_S2_R2`

**Status:** Phase 2 extended · sub-periods **PASS** (3/3).  
**Plugin:** `monday_or_breakout` · same light-sidecar recipe as EURUSD.

## Logic (plain English)

Same Monday OR + shifted-primary framework. Sizing matches EURUSD: main 3=(2@30,1@50), shifted 2=(1@30,1@50), max 3 primary/week, HTF both-opposed skip.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M1` | Main 3 = 2@30%, 1@50% |
| `S2` | Shifted 2 = 1@30%, 1@50% |
| `R2` | Max **3** primary/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$96k |
| Stress DD | −$52k |
| **Net/Stress** | **1.83** |
| Baseline `M1_S1_R1` | 1.07 |

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 3/3 |
| Clustering | FLAG — top week ~20% of lifetime \|net\| (concentration review) |
| DD sensitivity | **PASS** — 25/45 N/S 1.59 (−13%); 35/55 N/S 2.32 |

## Capacity sketch

Initial **1–2M** notional equivalent (JPY cross; use ≈USD @ 110 for risk reporting). Smaller absolute edge than USDJPY — size below GBP/USDJPY.

## Do-not-cross-use

Shares EURUSD’s light-sidecar tag but **not** interchangeable with USDJPY `M2_S3_*`. Treat as a satellite sleeve, not a USDJPY substitute.

## Deployment

Eligible for limited paper / small live under EURUSD-like gates (N/S ≥ 1.5) **if** clustering FLAG is accepted and live DD stays in band. Prefer USDJPY as primary FX Monday OR book.


---


<!-- ===== SPEC_XAUUSD_M2_S2_R3.md ===== -->

# SPEC — XAUUSD Monday OR `M2_S2_R3`

**Status:** Phase 2 extended · sub-periods **PASS** (2/3) · **heat caution**.  
**Plugin:** `monday_or_breakout` · silver (**XAGUSD**) explicitly **excluded**.

## Logic (plain English)

Monday OR breakout + shifted primary on gold. Runner-heavier main (1@30, 2@50), light shifted sidecar (2), **unlimited** primary/week (`R3`). HTF both-opposed skip.

## Parameter tags

| Tag | Meaning |
|---|---|
| `M2` | Main 3 = 1@30%, 2@50% |
| `S2` | Shifted 2 = 1@30%, 1@50% |
| `R3` | Unlimited primary/week |

## Key metrics (broker Phase 1)

| Metric | Value |
|---|---|
| ≈USD Net | +$438k |
| Stress DD | −$230k |
| **Net/Stress** | **1.90** |
| Baseline `M1_S1_R1` | 1.04 |

## Robustness (Phase 2 extended)

| Check | Result |
|---|---|
| Sub-periods | **PASS** 2/3 |
| Clustering | FLAG — top week ~19%; fat-tail weeks |
| Heat | Stress ~−$230k — CE fragile despite dollars |
| DD sensitivity | **PASS** — 25/45 N/S 1.55 (−19%); 35/55 N/S 1.66 (−13%) |

## Capacity sketch

Not a clean FX sleeve. If funded at all: **≤1M** notional equivalent, stress-budget limited, separate from FX Monday OR caps. Prefer treating as research / opportunistic, not core CTA allocation.

## Do-not-cross-use

Do not copy `M2_S2_R3` onto FX majors. Do not revive XAGUSD under this tag (Phase 1 reject).

## Deployment

Gate: N/S ≥ 1.5 **and** explicit stress budget approval. Default stance: **do not fund** alongside USDJPY core until heat is reduced (size cut or filter).


---
