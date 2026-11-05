# OANDA practice books — health, adherence, drawdown context (2026-10-30)

Books: NAS100 clean-break `trail06_m4_e2_out_be` (-003), USDJPY Asia-range London `S_3_1_3_flt` (-004),
USDJPY Monday OR `M2_S3_R1` (-005).

## Verdict

**Drawdowns are a bad patch, not an error.** All three books trade exactly what the plugin says on the
same ticks/bars; live execution is slightly *better* than replay. The drawdowns sit inside each book's
research distribution (Asia ≈ 5th-percentile 40-campaign window, clean-break ≈ 7th–12th, Monday OR ≈ 32nd).

**Clean-break beats v2b-with-stop-at-opposite-side** on risk-adjusted terms in every out-of-sample slice
(see table). Keep clean-break.

## Health

- 3 daemons up, 0 causality violations, ~10–13 stream reconnects / 24h (recovered; 17:00 NY rollover).
- Asia: short −700k @157.115 with wide_stop / tp1 / tp2 working (MTM ≈ −$620 at 157.25).
- NAS100: long 10 @28681.6, no broker-side stop (by design for `pyramid_outside` until trail arms;
  exits are 5m-close rules).
- Monday OR: flat.

## Adherence

| Book | Live vs replay on stored bars | Tick-fed demo vs plugin |
|---|---|---|
| Monday OR | 9/9 exact | 40/40 fills, identical P&L |
| Asia-range | 6/6 within 2m since Oct 22 restart | 124/124 fills, identical P&L |
| NAS100 clean-break | 14/14 in same 5m signal bar | 34/34 (tick archive Jul 24–Aug 19 only) |

Exit-reason mix identical live vs sim on all three. Oct 29 NAS100: live ask triggered in the 14:00 bar vs
sim 14:05 (live −7.5 pts vs sim −65 pts).

Asia live vs tick replay since Sep 3: replay +$2,623, live −$3,638. The whole gap is Sep 3
(live sized 7 units, replay 700k: +$6,905 missed — known pre-scaling stub). Every other trade live is
$50–190 better than replay (≈ +$1.9k total).

## Live performance vs research

| Book | Live | Research context (same size) |
|---|---|---|
| Asia-range | 40 campaigns, −$3,638; peak +$12,307 (Sep 28) → −$15,946 realized, ≈ −$16.6k with open MTM; Sep +$8,905 / Oct −$12,543; WR 50%, avg win $1,269 / avg loss $1,451 | Live is effectively the unfiltered Jan-skip book (shadow gate frozen open). `S_3_1_3_jan` 2015–2026-03: WR 49.7%, PF 1.18, max DD −$53k, 2018/2019/2021/2026 losing years. Rolling-40 net ≤ −$3,638: **20.5%** of windows. Within-40 DD ≤ −$15.9k: **5.5%**; ≤ −$20k: 2.5%. Filtered `_flt`: 2.1% / 0% |
| NAS100 clean-break | 22 trades, −$4,049; peak $2,660 → −$6,709; WR 9% | Research (×10 live size): rolling-22 ≤ −$4,049 **7.3%**; within-22 DD ≤ −$6,709 **12.5%**; WR ≤ 9% over 22 trades **45%** of windows; full max DD −$18.7k |
| Monday OR | full size since Oct 1: 9 trades, −$1,379 (15 incl. July stubs); max DD −$3,387 | WR 30.7%; rolling-15 ≤ −$1,379 **32.5%**; max DD −$22.6k |

USDJPY regime: London 03:00–12:00 median range since Sep 3 = 70 pips (Sep 86, Oct 62) — above 77% of
research days. Larger swings both ways; October is choppy two-sided chop that stops out the reversal book.

Asia gate counterfactual (Oct 22 report): a live roll50 gate would have sat out 14 of 15 sessions from
Oct 2, saving ≈ $1.45k — it would not have prevented most of the drawdown. Gate stays frozen per operator.

## Clean-break vs v2b (stop at opposite OR side)

Same harness (1m quote fills, 1 tick slippage, AUDIT causality). cb = live `trail06_m4_e2_out_be`
(research size 1→4); v2b = `v2b_scaleout` 3/1/1, `oco_then_reverse`, init stop at opposite OR side;
v2b_long = same, long-only. Dollar nets differ in size; compare N/S, PF.

| Dataset | cb N/S | v2b N/S | v2b_long N/S | cb PF | v2b PF | v2b_long PF |
|---|---|---|---|---|---|---|
| research NAS100 2016-11 → 2025-09 | **6.20** | 0.90 | 2.12 | 1.43 | 1.04 | 1.09 |
| NQ 2025-10 → 2026-10 (post-research) | **1.15** | −0.47 | −0.17 | 1.43 | 0.91 | 0.96 |
| OANDA demo bars 2026-08-31 → 10-30 | −0.58 | −0.66 | **+0.07** | 0.44 | 0.74 | 1.03 |

- cb research N/S 6.20 reproduces the recorded 6.23 → harness is sound.
- Over the 2-month demo window v2b_long is ≈ flat and cb is down; 24 trades is noise vs a 9-year /
  1-year out-of-sample edge where cb is consistently the better book. Two-way v2b loses in every slice.
- cb demo-bar replay at live size = −$5,065 vs live −$4,049 (live better).

Hub: `live/state/nas100_clean_break_vs_v2b_20261030/` (`summary.csv`, per-run `RESULT.json`, `trades.csv`).
Script: `scripts/nas100_clean_break_vs_v2b.py`.

## Watch items (no action taken)

- Asia: next ~20 campaigns; a realized DD past ≈ −$20k would be a 2.5%-tail event for the unfiltered book.
- NAS100: tick archive for parity still ends Aug 19 — extend if a tick-level check is wanted for Sep/Oct.
