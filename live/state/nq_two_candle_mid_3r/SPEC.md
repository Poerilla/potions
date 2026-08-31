# NQ two-candle midpoint 3R — SPEC (v1.1 morning)

## Setup
- Instrument: **NQ** front-month, **RTH morning only** (entries **09:30–11:59** America/New_York; flatten open risk at **12:00**)
- Signal / management TF: **15m** (`resample` left/left on RTH 1m)
- Economics: $20/pt, $1.50/contract/trade, 1-tick stop slippage; conservative same-bar stop-before-target

## Bias
1. Wait for the first two RTH 15m candles (09:30 & 09:45).
2. If candle 2 is **green** (close > open) → **long** bias; if **red** → **short**; doji → no trades that day.
3. Candle 2 is the initial **entry-defining** candle.

## Entry / risk
- Enter **limit** at defining candle **midpoint** `(H+L)/2` on a **later** morning bar that trades through it.
- Long: SL = defining **low**; Short: SL = defining **high**.
- Target = **3R** (`entry ± 3 × |entry − SL|`).
- Max **1** open position; max **2** trades per morning; **no new entries at/after 12:00**; flatten at noon if still open.

## Redefine / re-entry
- While **flat** and bias unchanged (morning only), each new same-color candle becomes the new defining candle.
- After a **stop**, the stop bar is **excluded**; wait for the next same-color candle (if bias unchanged).
- **Bias flip (long→short):** a 15m **close below** the current defining candle’s **low**.
- **Bias flip (short→long):** a 15m **close above** the current defining candle’s **high**.
- After a flip, wait for the first candle of the **new** bias color, then arm mid entry.

## Notes / assumptions
- “Closes over the low” on the long side is implemented as **close below the low** (symmetric to short-side close above high).
- Filling uses 15m OHLC touch (not 1m pathing).
- No pyramiding; wins (target/noon) also require a fresh defining candle to re-enter.
