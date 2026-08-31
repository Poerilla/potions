# HP size lock v1 — research capital package

Locked: **2026-08-17**.

This is a **research capital lock** (linear HP scaling for planning / $250k paths).
It does **not** rewrite null-suite deployment authorization:

- Futures deploy: NQ OR-norm provisional **≤2×**; ES ST-age **NOT VALIDATED**
- FX deploy: EURUSD Thu + US30 h11 **SIZE-UP VALIDATED @1.25×** only

## Locked sleeves

| Sleeve | Mult | qty | Net | Stress | N/S | $250k→ | ≈IM | Deploy auth |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| NQ OR-norm | 4× | 20 | $3,076,778 | $89,978 | 34.19 | $3,326,778 | $400,000 | provisional ≤2× |
| ES ST-age>180m | 4× | 20 | $823,220 | $40,780 | 20.19 | $1,073,220 | $300,000 | NOT VALIDATED research |
| EURUSD ST+PMC Thu | 40× | 40 | $1,430,374 | $168,355 | 8.50 | $1,680,374 | $100,000 | VALIDATED @1.25× only |

### Notes

- **NQ OR-norm:** best futures HP; liq OK @4×; deploy auth still provisional ≤2×
- **ES ST-age>180m:** next-best non-NQ futures; NOT VALIDATED under ΔN/S — research capital only
- **EURUSD ST+PMC Thu:** best non-CFD/non-futures; locked research size 40×; deploy auth still 1.25×

### Explicitly not locked at high size

- **US30 Monday OR hour 11:** CFD. At 80× YM-proxy med/p90 risk-eq entry-bar **8.1%/16.9%**, 32% of days >10% — liquidity problem. Keep **1.25×** deploy auth.

## Artifacts

- `LOCKED_SLEEVES.csv` / `LOCKED.json`
- Per-sleeve yearly `$250k` CSVs + liq JSON
- Extreme research hubs: `hp_extreme_20x_us30_nq/`, `hp_extreme_80x_us30_eurusd/`

Hub: `live/state/hp_size_lock_v1/`
