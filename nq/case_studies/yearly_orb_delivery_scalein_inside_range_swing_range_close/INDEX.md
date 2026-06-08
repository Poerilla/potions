# NQ yearly ORB delivery scale-in study

Base strategy: current yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close candidate. Jan-Mar defines the yearly ORB; Apr-Dec trades boundary retests after daily closes outside the ORB; stop is the latest confirmed inside-range swing; range-close exit is enabled.

Scale-in rule tested here: while a base trade is active and before the base yearly ORB TP is reached, place one scale-in at a time after a daily close breaks the highest recent swing high above the yearly range for longs, or the lowest recent swing low below the yearly range for shorts. The add-on limit is the signal close, the stop is the low/high of the leg that formed the broken swing, and the target is 2R.

Causality note: add-on orders are placed after the signal close and cannot fill until a later daily candle. Daily OHLC sequencing is conservative and cannot prove intraday ordering.

Base trades: 71  ·  Wins: 21  ·  Losses: 50  ·  Win rate: 29.6%
Total: +42918.94 pts ($+858,379)  ·  Base: +37937.69 pts ($+758,754)  ·  Scale add-ons: +4981.25 pts ($+99,625)
Max DD on combined trade ledger: -2346.38 pts ($-46,928)
Scale attempts: 49  ·  Fills: 49  ·  Wins: 21  ·  Losses: 28
Avg base position MAE: 238.98 pts ($4,780)  ·  Worst base position MAE: 1103.25 pts ($22,065)
Avg filled scale MAE: 371.38 pts ($7,428)  ·  Worst filled scale MAE: 1572.00 pts ($31,440)

Trade CSV: [nq_yearly_orb_delivery_scalein_inside_range_swing_range_close.csv](/home/tester/hsm/potions/nq/nq_yearly_orb_delivery_scalein_inside_range_swing_range_close.csv)
Add-on CSV: [nq_yearly_orb_delivery_scalein_inside_range_swing_range_close_addons.csv](/home/tester/hsm/potions/nq/nq_yearly_orb_delivery_scalein_inside_range_swing_range_close_addons.csv)

| Year | Symbol | Range Days | Trade Days | Range | Pattern | Base trades | Base pts | Scale pts | Total pts | Folder |
|---:|---|---:|---:|---:|---|---:|---:|---:|---:|---|
| 2011 | NQH1 | 77 | 232 | 217.25 | LL+LL+LL+LL+SL+LL+LL+LL+SW+SL+SL+SW+SW+SL | 14 | -513.94 | +0.00 | -513.94 | [2011/](2011/INDEX.md) |
| 2012 | NQH2 | 76 | 235 | 487.75 | LL+LL+LL+LL | 4 | -94.50 | +0.00 | -94.50 | [2012/](2012/INDEX.md) |
| 2013 | NQH3 | 73 | 233 | 130.75 | LL+LL+LW | 3 | +812.62 | +146.00 | +958.62 | [2013/](2013/INDEX.md) |
| 2014 | NQH4 | 74 | 228 | 328.50 | LW+LW | 2 | +1362.50 | +648.50 | +2011.00 | [2014/](2014/INDEX.md) |
| 2015 | NQH5 | 77 | 235 | 441.75 | LL+LL+LL+LL+LL+LL+SL+LL+LW | 9 | -435.69 | -829.25 | -1264.94 | [2015/](2015/INDEX.md) |
| 2016 | NQH6 | 76 | 234 | 744.50 | LL+LW | 2 | +691.12 | -80.50 | +610.62 | [2016/](2016/INDEX.md) |
| 2017 | NQH7 | 77 | 232 | 576.00 | No-Op | 0 | +0.00 | +0.00 | +0.00 | [2017/](2017/INDEX.md) |
| 2018 | NQH8 | 76 | 236 | 1050.50 | LL+LW+LL+LL+SW | 5 | -361.38 | -442.75 | -804.12 | [2018/](2018/INDEX.md) |
| 2019 | NQH9 | 77 | 235 | 1408.25 | LL+LL+LL+LL+LL+LW | 6 | +2446.88 | +517.00 | +2963.88 | [2019/](2019/INDEX.md) |
| 2020 | NQH0 | 78 | 234 | 3134.25 | LL+LW | 2 | +6782.81 | +2265.25 | +9048.06 | [2020/](2020/INDEX.md) |
| 2021 | NQH1 | 76 | 235 | 1693.25 | LL+LL+LL+LL+LW | 5 | +3625.81 | +962.75 | +4588.56 | [2021/](2021/INDEX.md) |
| 2022 | NQH2 | 77 | 233 | 3621.50 | SL+SW+SL+SL+SL+SW | 6 | +3691.50 | -623.75 | +3067.75 | [2022/](2022/INDEX.md) |
| 2023 | NQH3 | 77 | 233 | 2560.50 | LL+LL+LW | 3 | +6770.62 | +452.50 | +7223.12 | [2023/](2023/INDEX.md) |
| 2024 | NQH4 | 77 | 236 | 2374.75 | LL+LL+LL+LW+LL+LW | 6 | +4976.31 | +841.75 | +5818.06 | [2024/](2024/INDEX.md) |
| 2025 | NQH5 | 77 | 235 | 3343.00 | SW+SW+SL+LW | 4 | +8183.00 | +1123.75 | +9306.75 | [2025/](2025/INDEX.md) |
