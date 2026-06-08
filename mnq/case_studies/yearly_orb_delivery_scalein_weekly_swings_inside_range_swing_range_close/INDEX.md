# MNQ yearly ORB weekly delivery scale-in study

Base strategy: current yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close candidate. Jan-Mar defines the yearly ORB; Apr-Dec trades boundary retests after daily closes outside the ORB; stop is the latest confirmed inside-range swing; range-close exit is enabled.

Scale-in rule tested here: while a base trade is active and before the base yearly ORB TP is reached, place one scale-in at a time after a daily close breaks the highest recent weekly swing high above the yearly range for longs, or the lowest recent weekly swing low below the yearly range for shorts. The add-on limit is the signal close, the stop is the low/high of the leg that formed the broken swing, and the target is 2R.

Causality note: add-on orders are placed after the signal close and cannot fill until a later daily candle. Daily OHLC sequencing is conservative and cannot prove intraday ordering.

Base trades: 26  ·  Wins: 8  ·  Losses: 18  ·  Win rate: 30.8%
Total: +33830.56 pts ($+67,661)  ·  Base: +34040.81 pts ($+68,082)  ·  Scale add-ons: -210.25 pts ($-420)
Max DD on combined trade ledger: -2240.69 pts ($-4,481)
Scale attempts: 8  ·  Fills: 8  ·  Wins: 3  ·  Losses: 5
Avg base position MAE: 397.79 pts ($796)  ·  Worst base position MAE: 1106.25 pts ($2,212)
Avg filled scale MAE: 857.00 pts ($1,714)  ·  Worst filled scale MAE: 1283.50 pts ($2,567)

Trade CSV: [mnq_yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close.csv](/home/tester/hsm/potions/mnq/mnq_yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close.csv)
Add-on CSV: [mnq_yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close_addons.csv](/home/tester/hsm/potions/mnq/mnq_yearly_orb_delivery_scalein_weekly_swings_inside_range_swing_range_close_addons.csv)

| Year | Symbol | Range Days | Trade Days | Range | Pattern | Base trades | Base pts | Scale pts | Total pts | Folder |
|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| 2020 | MNQH0 | 78 | 234 | 3134.25 | LL+LW | 2 | +6787.06 | +1811.25 | +8598.31 | [2020/](2020/INDEX.md) |
| 2021 | MNQH1 | 76 | 235 | 1693.25 | LL+LL+LL+LL+LW | 5 | +3628.31 | -885.25 | +2743.06 | [2021/](2021/INDEX.md) |
| 2022 | MNQH2 | 77 | 233 | 3622.25 | SL+SL+SL+SL+SL+SW | 6 | +3688.38 | -1221.50 | +2466.88 | [2022/](2022/INDEX.md) |
| 2023 | MNQH3 | 77 | 233 | 2560.50 | LL+LL+LW | 3 | +6772.38 | -1158.75 | +5613.62 | [2023/](2023/INDEX.md) |
| 2024 | MNQH4 | 77 | 236 | 2374.25 | LL+LL+LL+LL+LL+LW | 6 | +4980.69 | +642.75 | +5623.44 | [2024/](2024/INDEX.md) |
| 2025 | MNQH5 | 77 | 235 | 3343.25 | SW+SW+SL+LW | 4 | +8184.00 | +601.25 | +8785.25 | [2025/](2025/INDEX.md) |
