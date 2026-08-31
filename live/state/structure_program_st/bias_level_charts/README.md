# Structure bias-level charts (15m + 1h)

No trades — visual review of how price interacts with structure levels
after a **15m program/bias change**, until the next bias change.

## What's on each chart

- **Candles:** ~1 RTH week (5 sessions) of **15-minute** bars
- **Black vertical:** 15m bias flip (buy/sell program)
- **Shaded span:** bias episode (until next flip or week end)
- **Blue band / lines:** 15m active structure box + key (SL) + confirm
- **Orange lines:** 1h structure key / box / bull·bear keys
- **Yellow band:** 15m∩1h confluence (levels within 25 pts)

## Selection

Scored for dual-TF interaction (confluence hits weighted highest), then
time-diversified. **100 / 215** episodes charted.

## Legend scores (title)

| token | meaning |
|---|---|
| m15 touches/thru/reclaim | 15m key interactions in episode |
| h1 touches/thru | 1h key interactions |
| confluence hits/pairs | price in 15m∩1h band / close level-pairs at flip |

## Files

- `charts/` — PNGs ranked by chart id (time order of selected set)
- `episodes.csv` — full scored episode table
- `charted.csv` — the selected subset

