# Canonical portfolio N/S (Phase 4)

Hub: `live/state/canonical_ns_research/portfolio/`

```text
Portfolio N/S = sum(sleeve nets) / |sum(sleeve reachable stresses)|
```

Joint stress is a **conservative additive upper bound**. Simultaneous
prior-opposed HP still requires the overlap gate
(`HOLD_ONE_HP_PER_SESSION`) before stacking.

## Constraints

- One book per HOLD_ONE group (NQ/MNQ · YM/MYM · ES/MES · FX sleeves).
- At most **one** prior-opposed HP size-up across ES/YM/NQ.
- Overlays admitted only from null hubs with SIZE-UP VALIDATED /
  PROVISIONAL PAPER / BORDERLINE PAPER.

## Core baselines (one per HOLD_ONE)

| hold_one | market | book | N/S | net | stress |
|---|---|---|---:|---:|---:|
| YM/MYM | US30 | US30/sl50_tp150_3r_1mfill | **20.97** | +19028 | 907 |
| NQ/MNQ | NQ | NQ/sl50_tp150_3r_1mfill | **20.51** | +349517 | 17038 |
| GBPUSD | GBPUSD | GBPUSD/sl50_tp150_3r_1mfill | **8.12** | +108058 | 13310 |
| USDJPY | USDJPY | S_3_1_3_flt | **7.23** | +178142 | 24627 |
| EURUSD | EURUSD | EURUSD/sl50_tp150_3r_1mfill | **3.01** | +64449 | 21432 |
| XAUUSD | XAUUSD | XAUUSD/sl50_tp150_3r_1mfill | **0.83** | +77327 | 92932 |

## Admitted overlays

| market | book | mult | ΔN/S | decision |
|---|---|---:|---:|---|
| NQ | nq_prior_opposed_rl | 2.00× | **+12.20** | BORDERLINE PAPER |
| NQ | nq_prior_opposed_rl | 1.25× | **+4.70** | BORDERLINE PAPER |
| EURUSD | eurusd_st_pmc_3r | 1.50× | **+0.67** | BORDERLINE PAPER |
| US30 | us30_monday_or | 1.50× | **+0.40** | BORDERLINE PAPER |
| EURUSD | eurusd_st_pmc_3r | 1.25× | **+0.34** | SIZE-UP VALIDATED |
| US30 | us30_monday_or | 1.25× | **+0.20** | SIZE-UP VALIDATED |

## Portfolio ranking (HOLD_ONE legal)

| rank | net | stress | **N/S** | ΔN/S vs core | overlays |
|---:|---:|---:|---:|---:|---|
| 1 | +2377654 | 205894 | **11.55** | +6.87 | nq_prior_opposed_rl@2.00×(BORDERLINE PAPER); eurusd_st_pmc_3r@1.50×(BO |
| 2 | +2368900 | 205378 | **11.53** | +6.86 | nq_prior_opposed_rl@2.00×(BORDERLINE PAPER); eurusd_st_pmc_3r@1.25×(SI |
| 3 | +2359875 | 205960 | **11.46** | +6.78 | nq_prior_opposed_rl@2.00×(BORDERLINE PAPER) |
| 4 | +2376302 | 221432 | **10.73** | +6.05 | nq_prior_opposed_rl@2.00×(BORDERLINE PAPER); us30_monday_or@1.25×(SIZE |
| 5 | +2380427 | 221830 | **10.73** | +6.05 | nq_prior_opposed_rl@2.00×(BORDERLINE PAPER); us30_monday_or@1.50×(BORD |
| 6 | +1941190 | 204487 | **9.49** | +4.81 | nq_prior_opposed_rl@1.25×(BORDERLINE PAPER); eurusd_st_pmc_3r@1.50×(BO |
| 7 | +1932436 | 203971 | **9.47** | +4.80 | nq_prior_opposed_rl@1.25×(BORDERLINE PAPER); eurusd_st_pmc_3r@1.25×(SI |
| 8 | +1923411 | 204553 | **9.40** | +4.72 | nq_prior_opposed_rl@1.25×(BORDERLINE PAPER) |
| 9 | +1943963 | 220422 | **8.82** | +4.14 | nq_prior_opposed_rl@1.25×(BORDERLINE PAPER); us30_monday_or@1.50×(BORD |
| 10 | +1939838 | 220025 | **8.82** | +4.14 | nq_prior_opposed_rl@1.25×(BORDERLINE PAPER); us30_monday_or@1.25×(SIZE |
| 11 | +814299 | 170180 | **4.78** | +0.11 | eurusd_st_pmc_3r@1.50×(BORDERLINE PAPER) |
| 12 | +805544 | 169664 | **4.75** | +0.07 | eurusd_st_pmc_3r@1.25×(SIZE-UP VALIDATED) |
| 13 | +796519 | 170246 | **4.68** | +0.00 | _(core only)_ |
| 14 | +834851 | 186050 | **4.49** | -0.19 | eurusd_st_pmc_3r@1.50×(BORDERLINE PAPER); us30_monday_or@1.50×(BORDERL |
| 15 | +830726 | 185652 | **4.47** | -0.20 | eurusd_st_pmc_3r@1.50×(BORDERLINE PAPER); us30_monday_or@1.25×(SIZE-UP |

## Stance

Best HOLD_ONE portfolio N/S **11.55** (net +2377654 / stress 205894).
Overlays: `nq_prior_opposed_rl@2.00×(BORDERLINE PAPER); eurusd_st_pmc_3r@1.50×(BORDERLINE PAPER)`.
Prior-opposed HP stacking remains blocked (`prior_opposed_hp_n≤1`); NQ OR-norm provisional @1.25×/@2× is the only futures HP overlay currently admissible.
