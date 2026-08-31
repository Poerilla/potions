# STUDY_SPEC — nq_wick_reject_4h_ny_open_5m_protected_pivot_v2

**STATUS:** RESEARCH / DESCRIPTIVE ONLY  
**PARENT:** `nq_wick_reject_4h_ny_open_1m_protected_pivot_v1` (archived negative)

## Purpose

After a completed active 4-hour WICK_REJECT seed, test whether a **five-minute**
NY-open four-pivot change-of-structure sequence creates a protected high or low
through 13:00 ET.

This is an independent predeclared V2 study. It does **not** revise V1.

## Frozen rules (only timeframe differs from V1)

- Same seed population / eligibility / first NY open / 09:30–10:30 / 13:00 horizon
- Same H1→L1→HH→LL / L1→H1→LL→HH consecutive sequences
- Same one-tick failure definition (evaluated on **5m** highs/lows)
- Pivots: 1-left / 1-right strict 5m; available only after subsequent 5m close

## Hard stop / decision tree

1. Candidates < 40 → insufficient sample; archive; no widening/tuning
2. Both hold rates < 55% (with adequate n) → negative; archive family
3. One side ≥55% only → one-sided descriptive observation only
4. Both sides ≥55% with n/causality/concentration screens → preserve; separate execution hypothesis only on untouched data later

## Non-goals

No entries, stops, targets, P&L, plugins, S1/S2 coupling, or timeframe chooser.
