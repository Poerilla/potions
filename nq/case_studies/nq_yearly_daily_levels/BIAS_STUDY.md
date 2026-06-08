# NQ bias framework (notes only — not a strategy)

These rules describe how to **read** yearly/monthly opens and prior-year extremes. They are context for discretionary bias, not entry/exit rules.

## Yearly bias

- Trading **above the yearly open (YO)** → overall **bullish** bias.
- Trading **below YO** → overall **bearish** bias.

## Monthly bias (while above YO)

- Trading **above the monthly open (MO)** → **bullish** until a warning pattern appears.
- **Engulfing**, **three black crows**, or **widow** candles do **not** flip bias to bearish for taking trades — they mean bullishness is **tired** (exhaustion), not a signal to go short.
- We **do not** trade those exhaustion patterns; we only note that momentum may be fading.

## Temporary bias vs yearly (confirmed MO breakout)

- Yearly bias can be **overridden short-term** when price trades **below MO** with a **confirmed breakout candle** (same cross rule as the daily study: open on one side, close on the other).
- Example: bullish above YO → **bearish MO breakout** → switch to **temporary bearish** until context resets (e.g. back above MO or new month).
- Mirror for bearish yearly bias: trade above MO with bullish MO breakout → temporary bullish.

## Prior-year high / low (PYH / PYL)

- **PYH** and **PYL** are significant **support or resistance** depending on approach:
  - **PYH as support** when price is **coming from above** it.
  - **PYH as resistance** when price is **coming from below** it.
  - **PYL as support** when price is **coming from below** it.
  - **PYL as resistance** when price is **coming from above** it.

Use side-of-level and direction of approach, not the label alone.

## Related artifacts

- Quarterly daily levels + breakout marks: [`INDEX.md`](INDEX.md)
- Post-breakout intraday follow-through (15m, midnight–16:00 NY): [`../nq_breakout_followthrough/INDEX.md`](../nq_breakout_followthrough/INDEX.md)
  - Monthly MO bias folders: close **≥ MO** → bull streak; close **< MO** → bear streak; new folder on flip; new month parent on roll.
