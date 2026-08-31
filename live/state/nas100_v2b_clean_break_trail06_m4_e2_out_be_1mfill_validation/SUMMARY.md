# NAS100 Clean-Break Best-N/S 1m-Fill Validation

STATUS: validation replay, not a new optimization sweep.

Ledger row: `brl_21741b260a28`

## Frozen candidate

- Candidate: `trail06_m4_e2_out_be`.
- Source family: clean-break pyramid trail sizing validation.
- Signal bars: completed 5m candles, signal-only through `Engine.process_bar(..., broker_fills=False)`.
- Signal timestamps: final 1m row in each 5m bucket, with the left-label retained in `signal_delivery_audit.csv`.
- Fill bars: local NAS100 1m OHLC with synthetic bid/ask fields.
- Quote caveat: this is finer broker-style proxy data, **not** true historical tick/bid-ask quote history.

## Result

| Sessions | Trades | Units | Net | Closed DD | Intrabar stress DD | Max units | Win% | PF | N/S |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2277 | 1166 | 2070 | $12,252.95 | $-1,893.85 | $-1,965.85 | 4 | 27.1% | 1.43 | 6.23 |

## Causality and timing

| Check | Result |
|---|---:|
| Feature snapshots | 22558 |
| Causality violations | 0 |
| Non-MOC fills at/before activation | 0 |
| MOC fills before activation | 0 |
| Entry fills at/before activation | 0 |
| 1m bars replayed | 871129 |
| 5m signal bars delivered | 174371 |

## Interpretation

This run removes the known high-timeframe fill hazard: the 5m candles never fill orders. They only generate strategy decisions after each bucket's 1m rows have already been processed, and fills are matched on the 1m broker-style proxy tape.

The run is still not tick-proven. Synthetic bid/ask fields make fills more broker-like than mid-only OHLC, but they cannot prove sub-minute queue position or true historical spread.

Artifacts:

- `summary.csv`
- `signal_delivery_audit.csv`
- `order_timing_audit.csv`
- `states/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill/feature_snapshots.csv`
- `states/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill/causality_violations.csv`
- `states/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill/equity_curve.csv`
- `run_manifest.json` / `run_manifest.sha256`

Config:

```json
{
  "broker_style_fill_source": "1m_proxy_synthetic_bid_ask",
  "entry_offset_ticks": 2,
  "entry_qty": 1,
  "fill_signal_bucket_end": true,
  "fill_to_signal_minutes": 5,
  "market": "nas100",
  "max_pyramid_qty": 4,
  "pyramid_add_every_n": 2,
  "pyramid_add_mode": "outside",
  "pyramid_place_2r_target": true,
  "record_levels": false,
  "required_break_num": 0,
  "size_model": "pyramid_outside",
  "stop_mode": "opposite",
  "synthetic_half_spread_ticks": 0.5,
  "tick_size": 0.1,
  "trail_at_frac": 0.6,
  "trail_to": "entry",
  "variant": "trail06_m4_e2_out_be"
}
```
