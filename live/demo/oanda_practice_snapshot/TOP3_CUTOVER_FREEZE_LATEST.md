# OANDA top-3 cutover freeze (2026-08-20T15:06:01Z)

> **Superseded active map:** on 2026-08-24, account `-004` was rotated from
> NAS100 ST+PMC 2R->10R to USDJPY Asia Range `S_3_1_3`. Use
> `live/demo/oanda_account_configs/TOP3_ACCOUNT_MAP.md` for the current map.
> This file remains the historical freeze snapshot.

Shared-primary fleet stopped so validation focuses on three dedicated practice accounts.

## Primary `101-002-39860312-001` (will go dormant)
- NAV **99537.75** balance **99690.54** UPL **-152.79** cum PL **-132.85**
- Open trades: **1** pending: **1**
  - trade 1941 NAS100_USD units=-3.0 uPL=-154.88
  - pending 1937 STOP NAS100_USD px=29400.0

## Planned dedicated map

- `us30_hourly_st_pmc_sl50_tp150_3r_oanda` → `101-002-39860312-003`
- `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` → `101-002-39860312-004`
- `usdjpy_monday_or_ungated_oanda` → `101-002-39860312-005`

## OANDA demos at freeze

| Demo | Alive | Fills | Account | Last progress |
|---|:---:|---:|---|---|
| `audjpy_yearly_orb_oanda` | True | 0 | `101-002-39860312-002` | [2026-08-20T11:05:53] heartbeat bars=7080 last_day=2026-08-19 open_positions=0 orders=0 ro |
| `eurusd_hourly_st_pmc_sl50_tp150_3r_oanda` | True | 0 | `101-002-39860312-001` | [2026-08-20T11:03:03] heartbeat ticks=121626 bars_1m=2687 bars_1h=47 orders=0 open_positio |
| `eurusd_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | True | 0 | `101-002-39860312-001` | [2026-08-20T11:01:47] heartbeat ticks=126484 bars_1m=2800 bars_1h=48 orders=0 open_positio |
| `eurusd_yearly_orb_oanda` | True | 0 | `101-002-39860312-002` | [2026-08-20T11:01:05] heartbeat bars=7264 last_day=2026-08-19 open_positions=0 orders=0 ro |
| `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` | True | 8 | `101-002-39860312-001` | [2026-08-20T11:02:23] heartbeat ticks=215759 bars_1m=1202 bars_1h=20 orders=0 open_positio |
| `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | True | 6 | `101-002-39860312-001` | [2026-08-20T11:02:08] heartbeat ticks=498240 bars_1m=2703 bars_1h=46 orders=0 open_positio |
| `nas100_v2b_ungated_oanda` | True | 48 | `101-002-39860312-001` | [2026-08-19T14:00:42] DAEMON spawned pid=2729869 run_log=live/demo/nas100_v2b_ungated_oand |
| `spx500_v2b_ungated_oanda` | True | 60 | `101-002-39860312-001` | [2026-08-20T11:05:36] heartbeat ticks_logged=29951 bars_persisted=2154 bars_engine=485 ord |
| `us30_hourly_st_pmc_sl50_tp150_3r_oanda` | True | 5 | `101-002-39860312-001` | [2026-08-20T11:04:21] heartbeat ticks=185147 bars_1m=2705 bars_1h=46 orders=0 open_positio |
| `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda` | True | 8 | `101-002-39860312-001` | [2026-08-20T11:02:06] heartbeat ticks=143150 bars_1m=2315 bars_1h=41 orders=0 open_positio |
| `us30_london_prior_opposed_oanda` | True | 0 | `101-002-39860312-001` | [2026-08-20T11:05:02] heartbeat ticks=0 bars=1080 st_injects=0 orders=0 position_qty=0 siz |
| `us30_monday_or_m3_s3_r2_half_oanda` | True | 1 | `101-002-39860312-001` | [2026-08-20T11:05:31] containment bracket_watchdog class=orphan_protective actions=detect: |
| `us30_yearly_orb_oanda` | True | 0 | `101-002-39860312-002` | [2026-08-20T11:03:12] heartbeat bars=2727 last_day=2026-08-19 open_positions=0 orders=0 ro |
| `usdjpy_asia_range_london_oanda` | True | 0 | `101-002-39860312-001` | [2026-08-20T11:04:46] heartbeat ticks=156299 bars_1m=1880 orders=0 open_positions=0 asia_b |
| `usdjpy_monday_or_ungated_oanda` | True | 15 | `101-002-39860312-001` | [2026-08-20T11:05:03] heartbeat ticks=230273 bars_1m=2811 bars_15m=189 orders=0 open_posit |
| `xagusd_yearly_orb_oanda` | True | 0 | `101-002-39860312-002` | [2026-08-20T11:02:59] heartbeat bars=7142 last_day=2026-08-19 open_positions=0 orders=0 ro |
| `xauusd_yearly_orb_oanda` | True | 0 | `101-002-39860312-002` | [2026-08-20T11:05:52] heartbeat bars=7228 last_day=2026-08-19 open_positions=0 orders=0 ro |

JSON: `live/demo/oanda_practice_snapshot/TOP3_CUTOVER_FREEZE_20260820_150601Z.json`

**Token:** lists dedicated accounts but REST GET is **403** — regenerate practice API token before starting the three daemons.
