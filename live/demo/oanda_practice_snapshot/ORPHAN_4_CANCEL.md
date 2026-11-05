# OANDA orphan 4-cancel — 2026-08-19

**Incident id:** `2026-08-19_oanda_orphan_4_cancel`
**Cancelled at:** `2026-08-19T17:46:13Z` UTC
**Account:** practice `101-002-39860312-001`

## Cancelled

| OANDA id | Demo | Local cid | Status |
|---|---|---|---|
| 1719 | `nas100_v2b_ungated_oanda` | `ord_911e574f9526` | cancelled |
| 1756 | `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | `ord_d6dc0c5d4eff` | cancelled |
| 1758 | `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | `ord_7a190b98e111` | cancelled |
| 1760 | `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | `ord_75fa2902fd76` | cancelled |

## Notes

- Local `orders.csv` rows marked cancelled for matching client ids.
- **1720** (v2b sell STOP pair of 1719) still pending: `False`.
- 3r book may **re-arm** entry LIMITs on the next hour until cross-book / classifier fix lands.
- Containment false-positive plan: exclude intentional `bracket_role=entry` arms from `orphan_protective` when flat; reserve that class for true SL/TP / reduce-only / closed-trade-linked protectives.

See `ORPHAN_4_CANCEL.json`.
