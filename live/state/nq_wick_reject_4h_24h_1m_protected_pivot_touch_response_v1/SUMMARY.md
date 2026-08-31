# NQ 4H WICK-REJECT -> 24H 1M PROTECTED-AREA REACTION STUDY V1

STATUS: DESCRIPTIVE ONLY
CONFIG HASH: 402795e0a05e2fbc
DATA SESSION POLICY: POLICY_A_FULL_AVAILABLE_FUTURES_DATA
CAUSALITY: PASS
STANCE: ONE-SIDED DESCRIPTIVE ASYMMETRY ONLY
DECISION: ONE_SIDED_ASYMMETRY

## Population
- 4h wick-reject seeds (eligible with post-seed 1m): 91
- Excluded seeds: 0

## Formation
- Bear H1-L1-HH-LL candidates: 52
- Bull L1-H1-LL-HH candidates: 38
- Total candidates: 90
- Candidate rate: 90 / 91 = 98.9%
- Median minutes from seed available to completion: 44.0
- Median sequence duration minutes: 7.5
- Candidate counts by session segment: NY_MIDDAY=56, NY_OPEN=24, NY_PM=9, ASIA=1

## Primary question (contact reaction)
- Bear mean(MFE)>mean(MAE) and mean RR>1: True
- Bull mean(MFE)>mean(MAE) and mean RR>1: False

## Excursion by direction

### Bearish
- Candidates / evaluable / gap-incomplete: 52 / 39 / 13
- Contact depth (evaluable): NO_AREA_CONTACT=4 / TOUCH_ONLY=0 / SHALLOW_TRADE_THROUGH=2 / DEEP_TRADE_THROUGH=33
- First-contact evaluable: 34
- Structure mean MFE / MAE / RR: 115.69 / 342.05 / 0.338
- Structure median MFE / MAE / indiv RR: 21.00 / 129.00 / 0.224
- Contact mean MFE / MAE / RR: 144.35 / 137.03 / 1.053
- Contact median MFE / MAE / indiv RR: 61.00 / 45.00 / 0.826
- Path order fav / outer / same-bar-adv / neither: 18 / 3 / 13 / 0
- Top-1 / top-3 contact MFE contribution: 31.7% / 44.6%
- Zero-MAE contact count: 1
- Interpretation: MEAN_MFE_GT_MEAN_MAE

### Bullish
- Candidates / evaluable / gap-incomplete: 38 / 32 / 6
- Contact depth (evaluable): NO_AREA_CONTACT=3 / TOUCH_ONLY=0 / SHALLOW_TRADE_THROUGH=1 / DEEP_TRADE_THROUGH=28
- First-contact evaluable: 29
- Structure mean MFE / MAE / RR: 156.62 / 233.31 / 0.671
- Structure median MFE / MAE / indiv RR: 69.50 / 82.00 / 0.747
- Contact mean MFE / MAE / RR: 104.14 / 106.14 / 0.981
- Contact median MFE / MAE / indiv RR: 52.00 / 44.00 / 1.268
- Path order fav / outer / same-bar-adv / neither: 14 / 3 / 12 / 0
- Top-1 / top-3 contact MFE contribution: 15.0% / 38.1%
- Zero-MAE contact count: 0
- Interpretation: MEAN_MFE_NOT_GT_MEAN_MAE

### Pooled (descriptive only)
- Structure mean MFE / MAE / RR: 134.14 / 293.04 / 0.458
- Contact mean MFE / MAE / RR: 125.84 / 122.81 / 1.025

## Integrity
- Causality: PASS
- Sample thresholds met: True

## Disposition
- DESCRIPTIVE ONLY.
- No entry/P&L claim.
- Excursion R-to-R is asymmetry only, not tradable reward/risk.
- No session, direction, area-depth, or seed-context selector.
- No plugin or promotion.
- Preserve all ledgers, configuration, and charts unchanged.

## Final disposition language

This is a descriptive all-session structural study. It measures whether causally confirmed 1-minute bearish H1-L1-HH-LL and bullish L1-H1-LL-HH structures form after active 4-hour wick-reject seeds, and whether price reacts from a bounded protected-pivot AREA such that average favorable excursion exceeds average adverse excursion over fixed horizons. A touch or trade-through is classified, not auto-failed. It does not define an entry, stop, target, position size, trade, expected return, or plugin.
