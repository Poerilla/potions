# NQ first-hour follow 3R strong + sweep_with_side (broker-like)

Engine + PaperBroker + StrategyPlugin `first_hour_follow`.
Gate: **fh_body=strong** AND **sweep_with_side** (follow a PDH/PWH/London-high sweep or a PDL/PWL/London-low sweep).
Entry: `market_close` on last FH bar (10:25); initial SL = FH open; TP = 3× body; flatten 15:59.
ST trail book: hour-complete ATR SuperTrend 14×3 ratchets the stop when trend is aligned; 3R TP + EOD retained.
Realism: slip 1 tick, spread model, fee $1.50/unit, NQ $20/pt.

| Book | Trades | WR | Net | Stress DD | N/S |
|---|---:|---:|---:|---:|---:|
| follow 3R strong + sweep_with_side | 53 | 54.7% | $3,086 | $-19,099 | 0.16 |
| follow 3R strong + sweep_with_side + 1h ST trail | 53 | 54.7% | $3,288 | $-18,652 | 0.18 |

## Trail vs fixed stop

- Improved (net or N/S): **yes**
- ΔN/S = +0.01, Δnet = $+202, ΔWR = +0.0 pp

## How price meets the ST trail

- Trail modifies: 55
- Approach bars (within 8 pts): 7 across 8 trades
- Bounce bars (close away ≥12 pts without hitting): 5; trades with a bounce: 5 (rate given approach **62%**)
- Aggressive bounces (close away ≥25 pts): 3 bars / 3 trades (**9%** of trail trades)
- Median bounce size: **34.8 pts**
- Trail level significant for a future bounce play: **no**
- No bounce charts — trail touches did not bounce hard/often enough to treat as a level.

Stance: diagnostic / research. Do not promote from this sleeve alone.
