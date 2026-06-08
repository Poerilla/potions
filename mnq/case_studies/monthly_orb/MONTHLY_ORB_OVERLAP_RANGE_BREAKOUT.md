# MNQ Monthly ORB Overlap-Range Breakout

Update: a long-only 4-hour causal stop/limit-cycle rewrite now lives at
[overlap_range_breakout_4h_causal/README.md](overlap_range_breakout_4h_causal/README.md).
The older results below are the daily-close overlap study and are kept as the
research baseline.

Latest 4h causal pass:

| Variant | Fill | MNQ Net / DD | MNQ Win / PF | NQ Net / DD | NQ Win / PF |
|---|---|---:|---:|---:|---:|
| Breakout only, 1 active max | next-open | $45,856 / -$5,060 | 61.5% / 5.79 | $615,450 / -$50,538 | 68.4% / 6.83 |
| Breakout only, 2 active max | next-open | $51,960 / -$5,632 | 57.9% / 5.36 | $716,052 / -$50,538 | 67.4% / 6.72 |
| Full cycle, 2 active max | next-open | $55,887 / -$7,155 | 59.1% / 4.93 | $700,062 / -$71,520 | 58.3% / 5.39 |

Latest risk-on MNQ branch:

| Variant | Fill | MNQ Net / DD | MNQ Win / PF | Note |
|---|---|---:|---:|---|
| Breakout only, 2 active, daily ST filter | close | $50,386 / -$4,775 | 62.5% / 5.62 | Skips long breakouts unless confirmed daily Supertrend is bullish. |
| Same + daily ST bearish-reclaim scale-in x5 | close | $58,061 / -$4,775 | 57.1% / 5.72 | Adds 5 contracts after a confirmed daily bearish ST flip if a later 4h candle closes back over that stored bearish stop; scale-ins close with the runner or on a 4h close below that level. |
| Same + daily ST limit-retest x5 | close | $87,586 / -$4,775 | 60.9% / 8.26 | Adds 5 contracts at the confirmed daily Supertrend stop while an original runner is open; exits the add with the runner or on a 4h close below the current confirmed daily Supertrend stop. |

4h mark-to-market heat check:

| Variant | 4h MTM DD | Pessimistic 4h intrabar DD | Max open units |
|---|---:|---:|---:|
| Daily ST filter | -$10,020 | -$10,843 | 6 |
| Daily ST bearish-reclaim scale-in x5 | -$10,020 | -$10,843 | 7 |
| Daily ST limit-retest x5 | -$17,995 | -$18,175 | 12 |

Read: the first causal full-cycle pass is banked, but the cleaner branch is
still **breakout only**: long-only, 3-contract stop-breakout package, no bottom
reclaims, no top refills. Allowing **2 active max** fixes the missed-overlap
issue where one older runner blocked a newer overlap cluster. It added about
$6.1k on MNQ and $100.6k on NQ with only a small MNQ drawdown increase and no
NQ drawdown increase in this sample.

Winner drawdown profile for breakout-only 2-active next-open:

- MNQ: 11 winners, average pullback **22.0%** back into the combined range, worst winner **43.0%**. No winner went more than halfway back into the range.
- NQ: 31 winners, average pullback **14.8%**, worst winner **44.0%**. No winner went more than halfway back into the range.
- MNQ losers averaged **48.7%** range-depth and maxed at **74.5%**. NQ losers averaged **56.5%** and maxed at **114.0%**.
- This suggests the next hardening test should be an intraday/4h catastrophe stop around **50% back into the combined range**. It may cut the worst losses without killing historical winners, but it needs a causal replay because 4h intrabar ordering can still matter.
- Catastrophe-stop sweep is now documented in [CATASTROPHE_STOP_SWEEP.md](CATASTROPHE_STOP_SWEEP.md). 45% was best in-sample; 50% is the cleaner practical hardening candidate because it preserves more room and still improved net/DD without reducing baseline winners.

Older daily-close baseline rules:

- Build monthly ORs from the first 3 daily rows of each calendar month.
- If adjacent monthly ORs overlap, combine them into one range.
- If later monthly ORs overlap the active combined range, expand the range.
- If a later monthly OR gaps away, the active cluster is done and the engine waits for the next adjacent overlap.
- Entry is the daily close that breaks out of the active combined range.
- Stop is at fraction ``stop_frac`` of the combined range from the wrong side for the breakout (default **0.5** = midpoint). Smaller ``stop_frac`` places the stop **deeper** (wider).
- Target is one combined range beyond the breakout-side boundary (1R).
- Default **one contract**; optional **two contracts** with one lot off at 1R and one runner to **2R** or **3R**, runner stop to breakeven after 1R fills (conservative same-bar: full stop before TP when both touch).
- One live trade at a time, max two entries per overlap cluster.
- One favorable extension is allowed if a later overlapping month expands the range and price breaks the expanded range in the trade direction.

Dollar figures use MNQ point value of $2/point per contract.

## Summary

| Trades | Net pts | Net USD | Max DD USD | Win rate | PF | Avg MAE pts | Max MAE pts | Avg MAE / risk |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 23 | 7,371.4 | $14,743 | $-2,569 | 56.5% | 2.42 | 382.9 | 842.8 | 0.74 |

## Direction Split

| Direction | Trades | Net pts | Net USD | Max DD USD | Win rate | PF |
|---|---:|---:|---:|---:|---:|---:|
| Long | 12 | 7,001.9 | $14,004 | $-2,445 | 66.7% | 4.36 |
| Short | 11 | 369.5 | $739 | $-3,218 | 45.5% | 1.12 |

## Exit Mix

- Target: **13**
- Midpoint-Stop: **10**

## Cluster Events

- entry: **23**
- expand: **19**
- start: **18**
- skip_overextended: **3**

## Yearly Split

| Year | Trades | Net pts | Wins | Losses | Avg MAE pts | Max MAE pts |
|---:|---:|---:|---:|---:|---:|---:|
| 2019 | 3 | -107.2 | 1 | 2 | 175.2 | 244.8 |
| 2020 | 3 | 2,012.0 | 2 | 1 | 393.5 | 656.0 |
| 2021 | 1 | -571.9 | 0 | 1 | 842.8 | 842.8 |
| 2022 | 3 | 923.2 | 2 | 1 | 303.5 | 703.8 |
| 2023 | 4 | 1,397.5 | 3 | 1 | 358.3 | 754.2 |
| 2024 | 3 | 3,280.8 | 3 | 0 | 228.0 | 480.0 |
| 2025 | 5 | 1,050.4 | 2 | 3 | 521.2 | 826.5 |
| 2026 | 1 | -613.4 | 0 | 1 | 623.5 | 623.5 |

## Outputs

- `mnq/mnq_monthly_orb_overlap_range_breakout.csv`
- `mnq/mnq_monthly_orb_overlap_range_breakout_events.csv`
- Charts: `case_studies/monthly_orb/overlap_range_breakout/INDEX.md`
- Stop / MAE / 2-lot runner sweep: `case_studies/monthly_orb/MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md` (regenerate: `python scripts/monthly_orb_overlap_range_breakout.py --sensitivity`)
