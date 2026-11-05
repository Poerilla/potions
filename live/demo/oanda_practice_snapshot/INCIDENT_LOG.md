# OANDA practice incident log

- **2026-08-18T16:34:18Z** `2026-08-18_oanda_orphan_limit_mass_cancel` — cancelled 53 pending (flat account); see ORPHAN_LIMIT_CANCEL.md

- **2026-08-19** `2026-08-19_oanda_orphan_4_cancel` — cancelled 1719/1756/1758/1760 (NAS100 cross-book); see ORPHAN_4_CANCEL.md
- **2026-08-19T21:36:00Z** `2026-08-19_us30_stale_arm_dedupe` — cancelled 16 stale US30 LIMITs; kept paper-inline 1773–1776 + NAS100 protectives; see PENDING_AUDIT_CLEANUP.md
- **2026-08-21T16:07:00Z** `2026-08-21_us30_stale_arm_dedupe_r3` — `-003` stacked ST+PMC LIMITs (orders=1→5) from `working` status filter bug; cancelled remote 5/6/7/8, kept 11 @52945.2; `OPEN_ORDER_STATUSES` patch + daemon restart → orders=1. See STALE_ARM_DEDUPE_R3.md

## 2026-08-20T15:08:23Z — Top-3 dedicated-account cutover (fleet stop)

- Froze shared-primary OANDA fleet performance → `TOP3_CUTOVER_FREEZE_LATEST.md`
- Stopped **all** OANDA daemons (paper left running). Primary `-001` dormant.
- Cancelled primary pending STOP 1937; closed NAS100 short 1941 (shortUnits=ALL).
- Dedicated map: Fair US30 → `-003`, NAS100 2R→10R → `-004`, USDJPY M2_S3_R1 → `-005`
  (`live/demo/oanda_account_configs/TOP3_ACCOUNT_MAP.md`).
- **Blocked restart:** current practice token GET on `-003/-004/-005` returns **403**
  (list accounts works). Need regenerated OANDA practice API token in `live/demo/.env`.
