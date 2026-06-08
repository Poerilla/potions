# Monthly ORB Restricted Stop-Limit Cycle: 4H Hardened Variants

This compares the baseline 4h causal restricted stop-limit cycle against two
rule tweaks:

- **Bottom confirmed:** a bottom-limit reclaim can only be armed after a prior
  stop-breakout package has produced at least one 4h close above the monthly OR
  high. Wick-only breakout failures no longer unlock the bottom limit.
- **TP50x2:** stop-breakout packages use 4 contracts instead of 3, with 2
  contracts off at TP50, 1 at TP1, and 1 runner to TP2. Bottom-limit and
  top-refill packages are unchanged.

The `next_open` exit mode is the more live-like daily-close exit assumption.

## Summary

| Variant | Market | Exit | Packages | Net USD | Max DD | Win | PF | Bottoms | Stop Net | Bottom Net | Top Net |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | MNQ | close | 141 | $54,780 | $-10,330 | 51.1% | 1.69 | 20 | $32,971 | $22,091 | $-282 |
| Baseline | MNQ | next_open | 143 | $52,637 | $-14,906 | 50.3% | 1.61 | 27 | $32,386 | $20,436 | $-186 |
| Bottom confirmed | MNQ | close | 139 | $57,180 | $-10,330 | 51.8% | 1.74 | 18 | $32,971 | $24,491 | $-282 |
| Bottom confirmed | MNQ | next_open | 141 | $55,034 | $-14,906 | 51.1% | 1.66 | 25 | $32,386 | $22,834 | $-186 |
| TP50x2 only | MNQ | close | 141 | $62,894 | $-13,447 | 55.3% | 1.68 | 20 | $41,086 | $22,091 | $-282 |
| TP50x2 only | MNQ | next_open | 143 | $59,993 | $-15,703 | 54.5% | 1.61 | 27 | $39,742 | $20,436 | $-186 |
| Bottom confirmed + TP50x2 | MNQ | close | 139 | $65,294 | $-13,447 | 56.1% | 1.73 | 18 | $41,086 | $24,491 | $-282 |
| Bottom confirmed + TP50x2 | MNQ | next_open | 141 | $62,390 | $-15,703 | 55.3% | 1.65 | 25 | $39,742 | $22,834 | $-186 |
| Baseline | NQ | close | 338 | $649,642 | $-103,068 | 45.0% | 1.63 | 55 | $457,542 | $207,430 | $-15,330 |
| Baseline | NQ | next_open | 342 | $613,818 | $-148,712 | 44.7% | 1.55 | 66 | $444,598 | $183,840 | $-14,620 |
| Bottom confirmed | NQ | close | 335 | $662,420 | $-103,068 | 45.4% | 1.65 | 49 | $449,575 | $228,175 | $-15,330 |
| Bottom confirmed | NQ | next_open | 338 | $641,802 | $-148,712 | 45.3% | 1.59 | 61 | $441,132 | $215,290 | $-14,620 |
| TP50x2 only | NQ | close | 338 | $748,700 | $-127,200 | 49.1% | 1.62 | 55 | $556,600 | $207,430 | $-15,330 |
| TP50x2 only | NQ | next_open | 342 | $704,265 | $-156,622 | 48.2% | 1.55 | 66 | $535,045 | $183,840 | $-14,620 |
| Bottom confirmed + TP50x2 | NQ | close | 335 | $759,850 | $-127,200 | 49.6% | 1.64 | 49 | $547,005 | $228,175 | $-15,330 |
| Bottom confirmed + TP50x2 | NQ | next_open | 338 | $731,095 | $-156,622 | 48.8% | 1.58 | 61 | $530,425 | $215,290 | $-14,620 |

## Read

The bottom-confirmed rule is a clean hardening improvement. It removes a small
number of bottom-limit attempts, increases net/PF, and does not worsen max DD in
this run. It supports the visual read that bottom reclaims work best after price
has already proven it can close above the range, not after a wick-only failed
break.

The TP50x2 rule confirms the observation that many losing breakout packages
first trade to TP50. It meaningfully lifts net and win rate on both MNQ and NQ,
but increases max DD because the initial breakout package is larger. It is
better as a sizing variant than as pure edge hardening.

Current practical preference for further testing:

1. **Bottom confirmed + TP50x2** if accepting the larger initial breakout
   package and DD.
2. **Bottom confirmed only** if prioritizing robustness and cleaner logic.

## Rebuild Commands

```bash
python3 scripts/monthly_orb_restricted_stop_limit_cycle_4h_causal.py \
  --market both --exit-fill-mode both \
  --bottom-limit-require-4h-close-above-range \
  --out-dir mnq/case_studies/monthly_orb/restricted_stop_limit_cycle_4h_causal_variants/bottom_confirmed

python3 scripts/monthly_orb_restricted_stop_limit_cycle_4h_causal.py \
  --market both --exit-fill-mode both \
  --breakout-tp50-units 2 \
  --out-dir mnq/case_studies/monthly_orb/restricted_stop_limit_cycle_4h_causal_variants/tp50x2_only

python3 scripts/monthly_orb_restricted_stop_limit_cycle_4h_causal.py \
  --market both --exit-fill-mode both \
  --bottom-limit-require-4h-close-above-range \
  --breakout-tp50-units 2 \
  --out-dir mnq/case_studies/monthly_orb/restricted_stop_limit_cycle_4h_causal_variants/bottom_confirmed_tp50x2
```
