# ST+PMC sl50_tp150_3r — cross-market 1m fill tape

StrategyPlugin (`hourly_st_pmc_retest`) + Engine + PaperBroker.
Hourly ST+PMC signals; **1m bars resolve fills** (same method as US30 fair control).

| Market | Instrument | Units | Net $ | Stress | N/S | WR% | Stop/TP |
|---|---|---:|---:|---:|---:|---:|---|
| `ym` | YM | 1993 | 101191.37 | -12900.6 | 7.844 | 30.9 | 50.0 / 150.0 |
| `mym` | MYM | 1078 | 8969.43 | -1292.0 | 6.942 | 35.3 | 50.0 / 150.0 |
| `nq` | NQ | 1210 | 209283.62 | -40535.58 | 5.163 | 29.6 | 50.0 / 150.0 |
| `mnq` | MNQ | 686 | 19621.11 | -2648.57 | 7.408 | 32.8 | 50.0 / 150.0 |
| `nas100` | NAS100 | 930 | 9459.79 | -2059.6 | 4.593 | 31.6 | 50.0 / 150.0 |
| `us30` | US30 | 578 | 19027.57 | -907.27 | **20.972** | 42.6 | 50.0 / 150.0 |
| `xauusd` | XAUUSD | 179 | 27205.56 | -169371.44 | 0.161 | 26.8 | 50.0 / 150.0 |
| `xagusd` | XAGUSD | 0 | 0.0 | 0.0 | 0.0 | 0.0 | 50.0 / 150.0 |
| `eurusd` | EURUSD | 1423 | -5124.89 | -36433.01 | -0.141 | 25.0 | 50/150 pips |
| `usdjpy` | USDJPY | 1411 | see note | see note | -0.879 | 23.5 | 50/150 pips |

## Skipped

- **MES** — `mes_daily.csv` exists but no 1m archive (`mes_1min_raw.csv` missing; only `mes_5min_rth.csv`).
- **SPX500** — no `fx/spx500_1m.csv` historical archive (live demo bars only).

## Live demos (paper + OANDA)

See lot-correct runner hubs for current ranks (2026-08-08):
`us30_st_pmc_runner_variants/`, `fx_index_metals_st_pmc_runner_variants/`.

| Market | Why | CLI |
|---|---|---|
| **US30** fair 3R | lot-correct N/S **29.4** | `demo-us30-hourly-st-pmc-{paper,oanda}` |
| **US30** 2R→10R | lot-correct N/S **24.1** | `demo-us30-hourly-st-pmc-2r10r-{paper,oanda}` |
| **NAS100** fair 3R | lot-correct N/S **19.6** | `demo-nas100-hourly-st-pmc-{paper,oanda}` |
| **NAS100** 2R→10R | lot-correct N/S **11.1** | `demo-nas100-hourly-st-pmc-2r10r-{paper,oanda}` |

**Trade charts (200 each, 100W/100L):** [`charts/INDEX.md`](charts/INDEX.md) · driver `live/st_pmc_1mfill_trade_charts.py`.

**Not live:** EURUSD/USDJPY (negative N/S); XAUUSD (net +$27k but N/S **0.16** / stress −$169k — keep metals on MA-bull / yearly ORB); XAGUSD (50/150 pts unusable vs silver price scale → 0 closed units).

## Notes

- FX stops are **50/150 pips** (EURUSD 0.0050/0.0150, USDJPY 0.50/1.50).
- Metals use **50/150 price points** (XAUUSD PV 100, XAGUSD PV 1000).
- USDJPY audit uses `POINT_VALUES=100000` (JPY notional); raw $ are not USD-comparable — use N/S.
- **2026-08-07:** HTF lookahead fill bug fixed (`broker_fills=False` on 1h signal bars). US30 re-run: 1197→578 units, N/S 10.34→**20.97**. Other markets in this table still use pre-fix 1mfill states until re-run.
- US30 fair control hub: `live/state/us30_st_pmc_retest_add_experiment`.
- Runner: `live/st_pmc_1mfill_cross_market.py`.
