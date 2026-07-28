# Monday OR cluster/skip — cross-instrument

Sitout thresholds are **instrument-scaled** (trade |net| p90 multiples + pos-week quantiles).
XAUUSD also keeps absolute +50/+100 pts; **+100 is core** on `M2_S2_R3`.

> **Important:** fill-proxy N/S ≠ StrategyPlugin broker. Broker-confirmed core:
> USDJPY R1 sitout+3 / R2 skip-1-after-2W; **XAUUSD sitout+100 + skip Jul/Sep/Dec
> (N/S 3.37)**. EUR/GBP skip-1-after-W rejected. See `CORE_WEEK_SITOUT.md` /
> `tuneup_broker/SUMMARY.md`.

| pair | tag | base N/S | best rule | best N/S | ΔN/S | cover | Δnet |
|---|---|---:|---|---:|---:|---:|---:|
| USDJPY | M2_S3_R1 | 9.75 | sitout_week_after_1.00x_p90(2.97578) | 10.77 | 1.02 | 95.7 | 24.07 |
| USDJPY | M2_S3_R2 | 8.98 | skip1_after_2W | 11.92 | 2.94 | 93.9 | 31.27 |
| EURUSD | M1_S2_R2 | 2.12 | skip1_after_W | 3.38 | 1.26 | 76.8 | 0.17 |
| GBPUSD | M1_S1_R2 | 3.06 | skip1_after_W | 3.74 | 0.68 | 77.5 | -0.65 |
| AUDJPY | M1_S2_R2 | 1.88 | skip1_after_2W | 2.73 | 0.85 | 94.3 | 37.25 |
| XAUUSD | M2_S2_R3 | 2.35 | sitout_week_after_+100pts | 3.09 | 0.74 | 92.7 | 525.59 |

## Core note (XAUUSD)

- `week_sitout_after_pts=100` is part of Monday OR core for `M2_S2_R3`
  (`live/strategies/monday_or_breakout.py` + `FOOTNOTE_TAGS`).
- Do **not** copy +100 onto FX majors without per-pair threshold selection.
