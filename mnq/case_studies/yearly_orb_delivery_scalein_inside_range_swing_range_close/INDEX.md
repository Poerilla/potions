# MNQ yearly ORB delivery scale-in study

Base strategy: current yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close candidate. Jan-Mar defines the yearly ORB; Apr-Dec trades boundary retests after daily closes outside the ORB; stop is the latest confirmed inside-range swing; range-close exit is enabled.

Scale-in rule tested here: while a base trade is active and before the base yearly ORB TP is reached, place one scale-in at a time after a daily close breaks the highest recent swing high above the yearly range for longs, or the lowest recent swing low below the yearly range for shorts. The add-on limit is the signal close, the stop is the low/high of the leg that formed the broken swing, and the target is 2R.

Causality note: add-on orders are placed after the signal close and cannot fill until a later daily candle. Daily OHLC sequencing is conservative and cannot prove intraday ordering.

Base trades: 26  ·  Wins: 10  ·  Losses: 16  ·  Win rate: 38.5%
Total: +39549.06 pts ($+79,098)  ·  Base: +34040.81 pts ($+68,082)  ·  Scale add-ons: +5508.25 pts ($+11,016)
Max DD on combined trade ledger: -1923.62 pts ($-3,847)
Scale attempts: 29  ·  Fills: 29  ·  Wins: 14  ·  Losses: 15
Avg base position MAE: 397.79 pts ($796)  ·  Worst base position MAE: 1106.25 pts ($2,212)
Avg filled scale MAE: 539.46 pts ($1,079)  ·  Worst filled scale MAE: 1576.00 pts ($3,152)

Trade CSV: [mnq_yearly_orb_delivery_scalein_inside_range_swing_range_close.csv](/home/tester/hsm/potions/mnq/mnq_yearly_orb_delivery_scalein_inside_range_swing_range_close.csv)
Add-on CSV: [mnq_yearly_orb_delivery_scalein_inside_range_swing_range_close_addons.csv](/home/tester/hsm/potions/mnq/mnq_yearly_orb_delivery_scalein_inside_range_swing_range_close_addons.csv)

| Year | Symbol | Range Days | Trade Days | Range | Pattern | Base trades | Base pts | Scale pts | Total pts | Folder |
|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| 2020 | MNQH0 | 78 | 234 | 3134.25 | LL+LW | 2 | +6787.06 | +2104.00 | +8891.06 | [2020/](2020/INDEX.md) |
| 2021 | MNQH1 | 76 | 235 | 1693.25 | LL+LL+LL+LL+LW | 5 | +3628.31 | +963.50 | +4591.81 | [2021/](2021/INDEX.md) |
| 2022 | MNQH2 | 77 | 233 | 3622.25 | SL+SW+SL+SL+SL+SW | 6 | +3688.38 | -617.75 | +3070.62 | [2022/](2022/INDEX.md) |
| 2023 | MNQH3 | 77 | 233 | 2560.50 | LL+LL+LW | 3 | +6772.38 | +460.00 | +7232.38 | [2023/](2023/INDEX.md) |
| 2024 | MNQH4 | 77 | 236 | 2374.25 | LL+LL+LL+LW+LL+LW | 6 | +4980.69 | +840.50 | +5821.19 | [2024/](2024/INDEX.md) |
| 2025 | MNQH5 | 77 | 235 | 3343.25 | SW+SW+SL+LW | 4 | +8184.00 | +1758.00 | +9942.00 | [2025/](2025/INDEX.md) |
