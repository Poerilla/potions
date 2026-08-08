# Runner risk accounting — us30_st_pmc_runner_variants

> **2026-08-08:** Indefinite rows below used legacy cross-trade FIFO / unclipped stress and are **not rankable**.
> Use [`LOT_CORRECT_ACCOUNTING.md`](LOT_CORRECT_ACCOUNTING.md) for trade-matched forced-flat + reachable stress.
> Fair 3R and 2R→10R remain valid.

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
| `us30` | `sl50_tp150_3r_1mfill` | $19028 | $-907 | $-466 | $-431 | $468 | 1 | $44952 | $500 | $-50 | 20.97 | 40.85 |
| `us30` | `sl50_tp150_runners_2r_10r` | $56111 | $-2867 | $-2057 | $-1907 | $2277 | 3 | $134857 | $1500 | $-150 | 19.57 | 27.28 |
| `us30` | `sl50_tp150_runners_2r_indef` | $191517 | $-73531 | $-87645 | $-87095 | $35260 | 65 | $2840731 | $32500 | $-2450 | 2.60 | 2.19 |

## Runner vs base (`sl50_tp150_3r_1mfill`)

| market | runner | Δ net | Δ MTM DD | Δ floor DD | Δ realized DD | Δ giveback | Δ max units | base N/S | runner N/S | floor N/S |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `us30` | `runners_2r_10r` | +$37083 | $-1960 | $-1591 | $-1476 | +$1809 | +2 | 20.97 | 19.57 | 27.28 |
| `us30` | `runners_2r_indef` | +$172490 | $-72624 | $-87179 | $-86664 | +$34792 | +64 | 20.97 | 2.60 | 2.19 |

## Artifacts

- `RUNNER_RISK_ACCOUNTING.csv`
- Per-variant `audits/*/reports/MTM_AUDIT.md` (headline MTM DD)

