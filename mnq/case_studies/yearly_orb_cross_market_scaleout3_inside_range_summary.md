# Yearly ORB Scaleout3 Inside-Range Swing Range-Close Cross-Market Run

Variant: `yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close`

Rules:

- Jan-Mar defines the yearly ORB.
- Apr-Dec trades boundary retests after daily closes outside the yearly ORB.
- Stop source is the latest confirmed swing whose pivot candle is fully inside the yearly ORB.
- Range-close restriction is enabled.
- 3 units: Unit 1 exits at 25% to TP, Unit 2 exits at TP, Unit 3 is the runner.
- Runner stop moves to breakeven only after Unit 2 reaches TP.

## Results

| Market | Data Source | Sample | Trades | Win Rate | Net | Max DD | Avg MAE | Worst MAE |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| ES | ES daily CSV | 2011-2025 | 81 | 33.3% | $441,669 | -$27,525 | $3,447 | $16,050 |
| YM-equivalent | MYM-derived daily CSV | 2020-2025 | 30 | 56.7% | $169,491 | -$12,185 | $3,173 | $8,400 |
| MYM actual | MYM-derived daily CSV | 2020-2025 | 30 | 56.7% | $16,949 | -$1,218 | $317 | $840 |

## Read

Both ES and the Dow-family proxy support the higher-timeframe thesis, but the shape is different:

- ES has a long sample and very large absolute PnL, but a lower win rate and more early-year churn.
- The Dow-family run is much smoother on the available 2020-2025 MYM sample, but that sample is shorter.
- The YM-equivalent line uses MYM price history with the YM $5/point multiplier. For actual MYM sizing, use the MYM actual row.

## Files

- ES CSV: `potions/es/es_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv`
- ES charts: `potions/es/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/`
- MYM daily source generated from 1m DBN: `potions/mym/mym_daily.csv`
- Dow-family CSV: `potions/mym/mym_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv`
- Dow-family charts: `potions/mym/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/`
- Combined CSV summary: `potions/mnq/case_studies/yearly_orb_cross_market_scaleout3_inside_range_summary.csv`
