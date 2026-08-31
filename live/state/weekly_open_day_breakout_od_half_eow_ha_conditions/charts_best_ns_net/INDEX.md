# Full trade charts — half+EOW HA best overlays

Source tape: Engine+PaperBroker 1m (`nas100_wod_od_half_eow_bull_hivol`).
4h weekly PNGs with OD H/L, ATR bands, entry/stop/TP + fill markers.

| Sleeve | Role | Campaigns | Week charts | Path |
|---|---|---:|---:|---|
| Week-of-month=1 FILTER | Best ΔN/S (5.51 / +4.06) | 45 | 43 | [week1_filter/nas100/charts/](week1_filter/nas100/charts/) |
| RSI 55–70 (trade path) | Best Δnet sleeve (@1.5× size-up) | 74 | 67 | [rsi55_70/nas100/charts/](rsi55_70/nas100/charts/) |

Notes:
- RSI charts show the **same trade path** as baseline for those campaigns; 1.5× is size-only (not redrawn).
- Shadow-only — no size-up promote (nulls RISK THROTTLE / NOT VALIDATED).
