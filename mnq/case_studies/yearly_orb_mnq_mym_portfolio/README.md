# Yearly ORB Portfolio: 1 MNQ Unit + 4 MYM Units

Variant: yearly ORB scaleout3, inside-range swing stop, range-close exit.

Sizing note:

- 1 MNQ unit = the full 3-contract ladder, or 3 MNQ contracts.
- 1 MYM unit = the full 3-contract ladder, or 3 MYM contracts.
- This portfolio is 1 MNQ unit + 4 MYM units = 3 MNQ + 12 MYM.

Sample: 2020-2025 overlap.

## Summary

| Book | Trades | Win Rate | Net | Closed DD | Open-Heat Stress DD | Worst Trade MAE |
|---|---:|---:|---:|---:|---:|---:|
| 1 MNQ unit | 26 | 38.5% | $68,082 | -$3,026 | n/a | $2,212 |
| 4 MYM units | 30 | 56.7% | $67,796 | -$4,874 | n/a | $3,360 |
| Combined | 56 | 48.2% | $135,878 | -$3,292 | -$6,239 | $3,360 |

The combined closed-trade drawdown is only slightly worse than MNQ alone, but the open-heat stress drawdown is the more realistic number to respect.

## MAE

| Metric | Value |
|---|---:|
| Average trade MAE | $1,049 |
| Worst single-trade MAE | $3,360 |
| Worst overlapping open heat | $3,499 |
| Sum of all trade MAE, not simultaneous | $58,761 |

Worst overlapping heat occurred during the 2022 short sequence:

| Date | Active Trades | Approx Heat |
|---:|---|---:|
| 2022-09-13 through 2022-10-28 | MYM short + MNQ short runner | $3,499 |
| 2022-11-04 | MYM short + MNQ short runner | $2,947 |

## Worst Historical Period

Worst closed-equity drawdown episode:

- Peak date: 2022-07-29
- Trough date: 2022-11-04
- Closed drawdown: -$3,292
- Active open heat at trough: $2,947
- Open-heat stress drawdown: -$6,239

Trades in the episode:

| Market | Direction | Entry | Exit | Net | MAE | Reason |
|---|---|---:|---:|---:|---:|---|
| MNQ | Short | 2022-05-05 | 2022-07-29 | $1,680 | $283 | TP25+Range-Close |
| MNQ | Short | 2022-07-31 | 2022-08-01 | -$54 | $1,000 | Range-Close |
| MNQ | Short | 2022-08-02 | 2022-08-03 | -$1,755 | $2,212 | Range-Close |
| MNQ | Short | 2022-08-23 | 2022-08-25 | -$1,216 | $1,447 | Range-Close |
| MYM | Short | 2022-08-29 | 2022-09-09 | $2,010 | $1,110 | TP25+Range-Close |
| MYM | Short | 2022-09-13 | 2022-10-28 | -$981 | $3,360 | TP25+Range-Close |
| MYM | Short | 2022-11-03 | 2022-11-04 | -$1,296 | $2,808 | Range-Close |

## Permutation / Survival Stress

These are not forecasts. They are adversarial rearrangements of the observed trade outcomes and MAE.

| Stress Case | Drawdown |
|---|---:|
| Historical closed-trade order | -$3,292 |
| Historical closed equity minus active open heat | -$6,239 |
| All losing trades occur before any winners | -$17,954 |
| All losing trades first, then worst single open MAE | -$21,314 |
| All losing trades first, then worst winning-trade MAE before recovery | -$20,238 |
| Every losing trade also experiences its own MAE before closing | -$54,286 |
| Every losing trade MAE plus worst winner MAE before recovery | -$56,570 |

Practical read: the clean backtest curve says this combo is very smooth, but a serious execution-test account should respect at least the open-heat stress number, not just closed drawdown. A harsher capital buffer would be based on the all-losses-first line.

## Pine Sizing

Use `potions/pine/yearly_orb_scaleout3_range_close.pine` on separate daily charts:

| Symbol | Contracts per scaleout batch | Total contracts |
|---|---:|---:|
| MNQ | 1 | 3 |
| MYM | 4 | 12 |

This keeps the same 3-stage ladder but lets MYM trade four times the unit count, so the MYM leg exits in 4/4/4 batches.

## Files

- Combined trade list: `mnq1_mym4_trades.csv`
- Annual summary: `mnq1_mym4_annual.csv`
- Market stats: `mnq1_mym4_market_stats.csv`
- Worst closed-DD episode: `mnq1_mym4_worst_closed_dd_episode.csv`
- Worst overlap heat: `mnq1_mym4_worst_overlap_heat.csv`
- Daily stress equity: `mnq1_mym4_daily_stress_equity.csv`
- Summary CSV: `mnq1_mym4_summary.csv`
