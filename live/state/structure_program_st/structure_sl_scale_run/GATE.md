# Gate: favourable ST-flip forward hold (BE only)

Counterfactual on **structure_sl_scale** favourable ST-flip exits: after the flip bar,
hold with stop at entry (BE). No new scales — path-touch only.

| metric | value |
|---|---|
| favourable ST-flip exits | 137 |
| hit +25 before BE | 84 (61.3%) |
| hit +100 before BE | 56 (40.9%) |
| hit +200 before BE | 32 (23.4%) |
| stopped at BE | 105 (76.6%) |
| fwd MFE mean / median | 92.5 / 72.8 |

**Verdict:** ST-flip *does* cut winners that would otherwise extend — proceed with
`structure_sl_scale_run` (5@22/50/200, fav ST→BE).
