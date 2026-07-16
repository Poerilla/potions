# NQ resting-limit left-label diagnostic (lookahead)

Preserved copy of the pre-2026-07-16 resting-limit book that used
`live_after_ts` (hour open) as gate availability.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 434 | 2170 | $1,321,745.00 | $-68,110.00 | $-68,610.00 | 65.67 | 2.300 | 19.26 |

**Demoted.** Use hour-complete baseline instead:
[`../resting_limit/INDEX.md`](../resting_limit/INDEX.md).

Early-arm attribution: `early_arm_attribution.csv` (**104** strict-early /
**$569,015**). Recovery analysis:
[`../early_pnl_recovery/INDEX.md`](../early_pnl_recovery/INDEX.md).
