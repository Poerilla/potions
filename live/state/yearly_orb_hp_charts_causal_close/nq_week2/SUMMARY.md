# NQ yearly ORB week_of_month=2 — is incN/S 34.32 real?

Coupon (nulls EMAIL line, **NOT VALIDATED**):

`nq_yorb week_of_month=2 @1.25× hp32% incN/S=34.32 p_plac=0.176`

Hubs:

- Nulls: `live/state/yearly_orb_hp_sizeup_nulls_causal_close/pairs/nq_yorb__week_of_month__2/`
- Tape: NQ `L_4_1_1` causal next-open close
- Charts (this folder): 5 largest week-2 wins + 5 worst week-2 losses

## Verdict

The **34.32 is real arithmetic** on the incremental 0.25× campaign-flat path.
It is **not** a whole-book N/S, **not** broker MTM stress, and **not** a
validated size-up. Drop the three multi-month year-flatten winners and the
sleeve N/S collapses to **2.64**.

Decision on the pair remains **NOT VALIDATED** (canonical ΔN/S placebo p=0.365,
master p=0.210). Walk-forward was empty (`wf_segments=0`).

## What the coupon actually measures

| Number | Meaning |
|---|---|
| hp32% | 22 / 68 campaigns (32.4%) entered in week-of-month 2 |
| incN/S=34.32 | extra 0.25× P&L of those 22, divided by the max DD of that **sparse extra path** ($133,733 / $3,897) |
| p_plac=0.176 | placebo p on **incremental sleeve N/S**, not on ΔN/S |
| Whole-book ΔN/S | +2.21 (12.63 → 14.85 on campaign-flat score_nets) |
| p_plac ΔN/S | 0.365 (matched-placebo median ΔN/S is 2.07 vs actual 2.21) |
| Broker L_4_1_1 N/S | **4.80** (net $764,503 / MTM stress −$159,309) |

The HP suite `score_nets` uses **forced-flat campaign P&L**, not intra-trade
MAE. That is why baseline N/S is 12.63 here vs 4.80 on the sizing-sweep board.
Whole-book stress does not rise at 1.25× (`Δstress=0`) because the book’s
worst campaign-flat DD is not on these 22 days.

Placebo median incremental N/S is already **13.98**. Random 22-boost sleeves
on this fat-tailed book look “crazy good” too; 34.32 is only the 82nd
percentile of that null.

## Concentration (the actual story)

Week-2 sleeve: 22 campaigns, 10 wins (45.5% WR), net **$534,932** (avg $24,315).

| Rank | Session | Side | Hold | Net | Role |
|---:|---|---|---:|---:|---|
| 1 | 2023-05-12 | long | 235d | +176,776 | year-change flatten |
| 2 | 2022-09-13 | short | 112d | +148,021 | year-change flatten |
| 3 | 2024-09-10 | long | 114d | +146,126 | year-change flatten |
| 4 | 2025-04-15 | short | 10d | +49,401 | |
| 5 | 2016-11-09 | long | 55d | +26,131 | |

Top 3 = **88%** of week-2 net ($470,923 / $534,932). All three are wide-OR
trend holds into January flatten, not “week-2 edge” scratches.

Without those three, incremental 0.25× sleeve: net +$16,002, stress $6,062,
**N/S 2.64**, ΔN/S +0.26.

Most week-2 losses are 0–3 day failed retests (−$3.5k to −$13.6k). Incremental
stress of $3,897 is 0.25× a modest cluster of those scratches (0.25×$13,599 ≈
$3,400, plus a bit of path stacking).

Paired fail-then-hit in the same week (visible on the charts):

- 2023-05-09 long −$4,449 (1d) then 2023-05-12 long +$176,776 (235d)
- 2025-04-13 short −$4,209 (1d) then 2025-04-15 short +$49,401 (10d)

## Stance

Do **not** size up NQ yearly ORB on week_of_month=2. The 34.32 coupon is a
tiny-denominator incremental path on three year-flatten outliers. Same HP
pair is already tagged NOT VALIDATED in
`live/state/yearly_orb_hp_live_plan_causal_close/`.
