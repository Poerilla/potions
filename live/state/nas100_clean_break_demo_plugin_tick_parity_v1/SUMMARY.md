# NAS100 clean-break: OANDA practice ticks → demo vs StrategyPlugin

STATUS: **MATCH**

## Data (OANDA only)

- Source: `/home/tester/hsm/potions/live/demo/nas100_v2b_ungated_oanda/state/events/rth_ticks`
- Kind: stored OANDA practice pricing-stream ticks (`rth_ticks/*.jsonl`).
- **Not used:** `fx/nas100_1m.csv` / research OHLC.
- Days (17): 2026-07-24, 2026-07-27, 2026-07-28, 2026-07-29, 2026-07-30, 2026-07-31, 2026-08-03, 2026-08-04, 2026-08-05, 2026-08-06, 2026-08-07, 2026-08-10, 2026-08-11, 2026-08-12, 2026-08-13, 2026-08-14, 2026-08-19
- Frozen variant: `trail06_m4_e2_out_be`

## Demo path (live/demo wiring)

- ticks=1477252 bars_1m=6509 bars_5m=1303 fills=34
- range: 2026-07-24T13:30:00+00:00 → 2026-08-19T18:00:00+00:00

## Plugin path (same 5m bars, fresh Engine)

- bars_5m=1303 fills=34

## Compare

```json
{
  "match": true,
  "a_n": 34,
  "b_n": 34,
  "a_only": [],
  "b_only": [],
  "first_diff_a": null,
  "first_diff_b": null
}
```

## Stance

- MATCH → live/demo aggregation+Engine wiring equals non-live StrategyPlugin on identical OANDA-derived bars.
- MISMATCH → investigate demo aggregator / Engine wiring before trusting the OANDA daemon.
- Practice wiring check only; not a funded promote gate.

