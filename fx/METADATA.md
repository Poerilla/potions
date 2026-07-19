# FX data manifest

Source: Histdata-style 1m files in `raw/` (`<TICKER>,<DTYYYYMMDD>,<TIME>,<OPEN>,<HIGH>,<LOW>,<CLOSE>,<VOL>`),
timestamps naive America/New_York (DST-aware localization via `live/fx_data.py`).

## Derivation / resolution ordering

Everything is aggregated **upward from 1m** — OHLC ordering per bucket:
`open = first 1m open`, `high = max 1m high`, `low = min 1m low`,
`close = last 1m close`, `volume = sum`.

| Timeframe | File pattern | Bucketing |
|---|---|---|
| 1m | `{pair}_1m.csv` | native (ts_event UTC ISO) |
| 1h | `{pair}_1h.csv` | UTC clock hours, from 1m |
| 4h | `{pair}_4h.csv` | UTC 4-hour blocks (00/04/08/12/16/20), from 1m |
| daily | `{pair}_daily.csv` | **NY calendar date**, from 1m |
| monthly | `{pair}_monthly.csv` | NY calendar month, from daily |
| yearly | `{pair}_yearly.csv` | NY calendar year, from daily |

Columns: intraday `ts_event,open,high,low,close,volume,symbol`;
daily+ `date,open,high,low,close,volume,symbol` (`date` = first session of bucket).

## Coverage (see `conversion_manifest.json`)

| Pair | 1m rows | Daily bars | Range |
|---|---:|---:|---|
| EURUSD | ~8.6M | 7,163 | 2003-05-06 → 2026-03-31 |
| GBPUSD | 8,554,337 | 7,163 | 2003-05-06 → 2026-03-31 |
| USDJPY | 8,519,395 | 7,155 | 2003-05-06 → 2026-03-31 |
| AUDJPY | 8,345,352 | 6,979 | 2003-12-02 → 2026-03-31 |
| XAUUSD | 7,768,796 | 7,128 | 2003-05-06 → 2026-03-31 |
| XAGUSD | 7,159,149 | 7,042 | 2003-05-06 → 2026-03-31 |

Note: JPY-quoted pairs (USDJPY, AUDJPY) have P&L per 100k unit in **JPY**
(point value 100,000 quote units). Convert by spot USDJPY for USD figures.
Metals (XAUUSD/XAGUSD) use futures-style sizing in gambit runs: gold PV=100
(100oz), silver PV=1000 (1000oz mini); tick 0.01 / 0.001.

**Data fix (2026-07-19):** XAGUSD 2011-01-20 had 25 one-minute bars scaled ~100× (prices ~2820 instead of ~28.20). Divided those OHLC by 100 and rebuilt 1h/4h/daily/monthly/yearly.
