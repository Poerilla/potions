# Yearly ORB Scaleout3 - 20% Range-Close Test

Broker-like daily `StrategyPlugin` replay. This variant keeps the same yearly ORB scaleout3 mechanics, but does **not** close on the first close back inside the yearly range. It closes only after price closes 20% back into the range:

- Long: close at or below `year_or_high - 0.20 * range`
- Short: close at or above `year_or_low + 0.20 * range`

Orders still become active only after the confirming daily bar closes, and close intents still fill through the paper broker path.

## Result vs Baseline

| Instrument | Baseline Net | 20% Net | Net Delta | Baseline Stress DD | 20% Stress DD | Stress Delta | Baseline Trades | 20% Trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | $39,216.62 | $48,202.62 | $8,986.00 | -$13,378.50 | -$14,141.00 | -$762.50 | 24 | 12 |
| NQ | $403,571.25 | $517,583.75 | $114,012.50 | -$133,860.00 | -$141,210.00 | -$7,350.00 | 68 | 39 |
| ES | $41,684.38 | $94,275.00 | $52,590.62 | -$70,612.50 | -$64,737.50 | $5,875.00 | 73 | 39 |
| MES | -$3,465.00 | $2,060.62 | $5,525.62 | -$7,143.75 | -$6,536.25 | $607.50 | 12 | 7 |
| YM | $59,582.50 | $128,771.25 | $69,188.75 | -$75,305.00 | -$62,282.50 | $13,022.50 | 81 | 45 |
| MYM | $677.38 | $7,670.12 | $6,992.74 | -$5,407.50 | -$6,209.75 | -$802.25 | 27 | 13 |

## Read

The 20% threshold improves net across every tested market. MNQ and NQ gain profit but accept slightly more stress; ES, MES, and YM improve both net and stress. Trade count drops because shallow range-close churn no longer flattens and re-arms as often.

This is a promising hardening branch. The next useful check is to inspect the chart packs year by year and see whether the extra hold time is removing noise exits or simply concentrating risk into fewer campaigns.

## Artifacts

- Summary: [SUMMARY.md](SUMMARY.md)
- CSV: [summary.csv](summary.csv)
- Charts: [charts/detail/INDEX.md](charts/detail/INDEX.md)
- MNQ chart pack: [charts/detail/mnq_yearly_orb_scaleout3_range_close_20pct/INDEX.md](charts/detail/mnq_yearly_orb_scaleout3_range_close_20pct/INDEX.md)
- NQ chart pack: [charts/detail/nq_yearly_orb_scaleout3_range_close_20pct/INDEX.md](charts/detail/nq_yearly_orb_scaleout3_range_close_20pct/INDEX.md)
