# OANDA practice sync

Fetched: `2026-09-11T20:09:15Z`
Account: `101-002-39860312-001` (practice)
NAV=99527.2822 balance=99527.2822 unreal=0.0 lastTx=1946
marginUsed=0.0 marginAvailable=99527.2822 marginCloseoutPercent=0.0 openTrades=0 pendingOrders=0

## Live positions

(flat)

## Owned by strategy (opening-order tag)

(none resolved)

## Demo local vs owned

| Demo | Focus | Local | Account focus | Owned by demo | Action |
|---|---|---|---|---|---|
| `audjpy_yearly_orb_oanda` | AUDJPY | `{}` | flat | flat | ok |
| `eurusd_hourly_st_pmc_sl50_tp150_3r_oanda` | EURUSD | `{}` | flat | flat | ok |
| `eurusd_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | EURUSD | `{}` | flat | flat | ok |
| `eurusd_v2b_ungated_oanda` | EURUSD | `{}` | flat | flat | ok |
| `eurusd_yearly_orb_oanda` | EURUSD | `{}` | flat | flat | ok |
| `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | NAS100 | `{}` | flat | flat | ok |
| `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | NAS100 | `{}` | flat | flat | ok |
| `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda` | NAS100 | `{}` | flat | flat | ok |
| `nas100_v2b_ungated_oanda` | NAS100 | `{}` | flat | flat | ok |
| `spx500_v2b_ungated_oanda` | SPX500 | `{}` | flat | flat | ok |
| `us30_hourly_st_pmc_sl50_tp150_3r_oanda` | US30 | `{}` | flat | flat | ok |
| `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | US30 | `{}` | flat | flat | ok |
| `us30_london_prior_opposed_oanda` | US30 | `{}` | flat | flat | ok |
| `us30_monday_or_m3_s3_r2_half_oanda` | US30 | `{}` | flat | flat | ok |
| `us30_v2b_ungated_oanda` | US30 | `{}` | flat | flat | ok |
| `us30_yearly_orb_oanda` | US30 | `{}` | flat | flat | ok |
| `usdjpy_asia_range_london_oanda` | USDJPY | `{}` | flat | flat | ok |
| `usdjpy_monday_or_ungated_oanda` | USDJPY | `{}` | flat | flat | ok |
| `xagusd_yearly_orb_oanda` | XAGUSD | `{}` | flat | flat | ok |
| `xauusd_yearly_orb_oanda` | XAUUSD | `{}` | flat | flat | ok |

## Notes

- Shared practice account: open risk is account-wide; each demo CSV mirrors **owned** focus qty only.
- Ownership = opening-order `clientExtensions.tag` on each open trade (not account instrument totals).
- Order CSVs are not rewritten here (daemon race). Compare LIVE pending orders above to each demo `state/orders.csv`.
- Snapshot JSON: `live/demo/oanda_practice_snapshot/account_snapshot.json`

