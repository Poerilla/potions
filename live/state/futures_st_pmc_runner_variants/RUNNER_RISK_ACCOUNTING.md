# Runner risk accounting — futures_st_pmc_runner_variants

> **2026-08-08:** Indefinite rows (and any NQ indef +$4.57M / N/S 2.35 headline) are **invalid** under cross-trade FIFO.
> Canonical replacement: [`LOT_CORRECT_ACCOUNTING.md`](LOT_CORRECT_ACCOUNTING.md).
> Fair 3R and 2R→10R remain the rankable candidates.

Post-process from fills + equity curves (no re-replay).

## Definitions

| Metric | Meaning |
|---|---|
| **Max MTM drawdown** | Investor/economic drawdown (intrabar stress); conservative headline |
| **Max protected-floor drawdown** | Equity if every open unit were stopped at its current stop (hard SL or BE after TP1 for runners) |
| **Max realized-equity drawdown** | Drawdown on closed P&L only |
| **Peak open profit giveback** | Max(peak MTM equity − protected-floor equity) — open paper profit above the stop floor |
| **Open exposure** | Max units; gross notional (= Σ\|entry\|×point_value); est. initial margin; worst concurrent stop loss |

Margins (approx CME day / CFD proxy): `{"ES": 14000.0, "MES": 1400.0, "MNQ": 2200.0, "MYM": 990.0, "NAS100": 500.0, "NQ": 22000.0, "US30": 500.0, "YM": 9900.0}`

## Per-system report

| market | variant | net | MTM DD | floor DD | realized DD | giveback | max units | max notional | max margin | worst stop | N/S MTM | N/S floor |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `ym` | `sl50_tp150_3r_1mfill` | $106425 | $-6026 | $-6144 | $-5894 | $6144 | 1 | $248053 | $9900 | $-250 | 17.66 | 17.32 |
| `ym` | `sl50_tp150_runners_2r_10r` | $313302 | $-21424 | $-18454 | $-17704 | $20298 | 3 | $744160 | $29700 | $-750 | 14.62 | 16.98 |
| `ym` | `sl50_tp150_runners_2r_indef` | $970818 | $-715046 | $-1171589 | $-1167589 | $147660 | 108 | $23642775 | $1069200 | $-21250 | 1.36 | 0.83 |
| `mym` | `sl50_tp150_3r_1mfill` | $6516 | $-1366 | $-634 | $-634 | $634 | 1 | $24804 | $990 | $-25 | 4.77 | 10.28 |
| `mym` | `sl50_tp150_runners_2r_10r` | $20600 | $-4468 | $-1905 | $-1905 | $2091 | 3 | $74411 | $2970 | $-75 | 4.61 | 10.82 |
| `mym` | `sl50_tp150_runners_2r_indef` | $53167 | $-31777 | $-44768 | $-44968 | $8546 | 46 | $1011584 | $45540 | $-925 | 1.67 | 1.19 |
| `mnq` | `sl50_tp150_3r_1mfill` | $23171 | $-1195 | $-1230 | $-1130 | $1237 | 1 | $52334 | $2200 | $-100 | 19.38 | 18.85 |
| `mnq` | `sl50_tp150_runners_2r_10r` | $49899 | $-4953 | $-4347 | $-4296 | $4347 | 3 | $157003 | $6600 | $-300 | 10.07 | 11.48 |
| `mnq` | `sl50_tp150_runners_2r_indef` | $96683 | $-52542 | $-160467 | $-162913 | $19870 | 45 | $2214362 | $99000 | $-4100 | 1.84 | 0.60 |
| `nq` | `sl50_tp150_3r_1mfill` | $349517 | $-17038 | $-17277 | $-16277 | $17277 | 1 | $546133 | $22000 | $-1000 | 20.51 | 20.23 |
| `nq` | `sl50_tp150_runners_2r_10r` | $775763 | $-58524 | $-55420 | $-52420 | $55420 | 3 | $1578685 | $66000 | $-3000 | 13.26 | 14.00 |
| `nq` | `sl50_tp150_runners_2r_indef` | $4573429 | $-1948591 | $-3901895 | $-3885895 | $1047604 | 137 | $54973380 | $3014000 | $-106000 | 2.35 | 1.17 |

## Runner vs base (`sl50_tp150_3r_1mfill`)

| market | runner | Δ net | Δ MTM DD | Δ floor DD | Δ realized DD | Δ giveback | Δ max units | base N/S | runner N/S | floor N/S |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `mnq` | `runners_2r_10r` | +$26728 | $-3758 | $-3118 | $-3166 | +$3110 | +2 | 19.38 | 10.07 | 11.48 |
| `mnq` | `runners_2r_indef` | +$73512 | $-51347 | $-159237 | $-161784 | +$18633 | +44 | 19.38 | 1.84 | 0.60 |
| `mym` | `runners_2r_10r` | +$14084 | $-3102 | $-1271 | $-1271 | +$1457 | +2 | 4.77 | 4.61 | 10.82 |
| `mym` | `runners_2r_indef` | +$46652 | $-30412 | $-44134 | $-44334 | +$7912 | +45 | 4.77 | 1.67 | 1.19 |
| `nq` | `runners_2r_10r` | +$426247 | $-41485 | $-38143 | $-36143 | +$38143 | +2 | 20.51 | 13.26 | 14.00 |
| `nq` | `runners_2r_indef` | +$4223912 | $-1931552 | $-3884618 | $-3869618 | +$1030326 | +136 | 20.51 | 2.35 | 1.17 |
| `ym` | `runners_2r_10r` | +$206877 | $-15398 | $-12310 | $-11810 | +$14154 | +2 | 17.66 | 14.62 | 16.98 |
| `ym` | `runners_2r_indef` | +$864392 | $-709020 | $-1165444 | $-1161694 | +$141516 | +107 | 17.66 | 1.36 | 0.83 |

## Artifacts

- `RUNNER_RISK_ACCOUNTING.csv`
- Per-variant `audits/*/reports/MTM_AUDIT.md` (headline MTM DD)

