# Asia-range live sizing (performance reviews)

**Live/paper size (from 2026-09-03):** `S_3_1_3` × **100k OANDA units/lot**

| Leg | Research lots | OANDA units |
|-----|--------------:|------------:|
| entry | 7 | 700,000 |
| tp1 | 3 | 300,000 |
| tp2 | 1 | 100,000 |

**Why:** Unscaled research qtys (7 units) made practice PnL ~cents (e.g. 2026-09-03 short ≈ **$0.07**). Lot sizing makes account moves readable.

**Review rule:** research hub `net_usd` uses `POINT_VALUES[USDJPY]=100000` and is **not** OANDA cash PnL. Convert before comparing to `-004` balance. Shadow / candle-sim stay on research book qtys so roll50 stays on the research tape scale.

See also `PERFORMANCE_REVIEW_SIZING_NOTE` in `live/demo/usdjpy_asia_range_london_common.py` and hub `FILTERS.md`.
