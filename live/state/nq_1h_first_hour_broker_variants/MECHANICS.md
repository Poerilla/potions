# RTH first-hour follow — how and why

Plugin: `live/strategies/first_hour_follow.py`  
Drivers: `live/nq_1h_first_hour_broker_variants.py`, `live/nas100_1h_first_hour_broker_variants.py`

## What it does

Every NY RTH session:

1. Build the **first-hour candle** from 5m bars **09:30–10:30** (open = 09:30 open, high/low extremes, close = last FH bar close).
2. At the **10:25** bar close (last FH left-label), take the candle’s direction:
   - long if close > open, short if close < open
3. Enter with a broker order (`market_close` on that bar, or a resting retrace **limit**).
4. Hold through the rest of RTH with a protective **stop** and take-profit **limit(s)**; flatten ~15:59.

Canonical promote-shaped book:

- **Entry:** `market_close` at FH close  
- **Stop:** FH **open** (risk ≈ first-hour body)  
- **Target:** **3 × body** from entry (same geometry as “follow 3R” when R = body and SL = open)

## Why it works (economic intuition)

RTH open is when overnight inventory and cash equity flow meet. The first hour often **sets the day’s directional bias**: once that hour closes with a clear body, the rest of the session tends to **continue** more often than it fully reverses through the FH open.

The edge is **not** a high win rate. Broker-like baseline is ~**37% WR**. It works because:

- Wins at **3× body** pay enough to cover many stops at ~1× body.
- Risk is **session-defined** (FH open → FH close body) rather than an arbitrary ATR multiple.
- Trade frequency is high (~every RTH day with a non-doji FH), so small PF compounds.

Fade (fade the FH close) **dies** under the same contract — continuation is the asymmetry.

## Why 3× body TP is the sweet spot

| Idea | Broker read |
|------|-------------|
| **SL = open, TP = 3× body** | Best **risk-adjusted** book on NQ and NAS100 among tested variants. Simple one-lot OCO. |
| Half-body SL + 3R | Still green, but tighter stops get clipped more under slip/spread → lower N/S than baseline. |
| Retrace 72% → SL extreme → 3R | Worse geometry + partial fills; N/S collapses (~0.33). **Reject.** |
| 0.75-body + 1R/2R/3R 3-lot ladder | Highest **dollar** net (3× size), lower N/S than 1-lot baseline. Useful if seeking absolute P&L, not efficiency. |
| Strong + sweep + ST trail | Collapsed sample; **reject.** |

Diagnostic (pandas) overstated N/S (~9.3 on NQ baseline). Broker Engine+PaperBroker (1-tick slip, spread, $1.50/unit) cuts that to **~5.6 NQ / ~4.1 NAS100** — still a clean mid-tier sleeve.

## How it fits the book

- **Below** prior-opposed v2b, index ST+PMC, Asia-range USDJPY, Monday OR leaders on N/S and allocator metrics.
- **Above** many failed intraday curiosities (retrace, sweep+trail, unconditional fade).
- Role: **capital-efficient daily RTH sleeve** — simple rules, high sample, no HTF gate dependency. Good “keep around” book when capacity remains after better sleeves.

Stance: **RETAIN** (broker-confirmed). Not funded-production until demo parity + portfolio slot. Do **not** demote the 3×body baseline because stronger systems exist — it is a solid standalone expression of open continuation.

## Execution contract (broker-like)

- Orders: entry `market_close` or resting **limit**; exits = reduce-only **stop** + TP **limit** (ladder: three 1-lot limits @ 1R/2R/3R, no shared OCO across rungs).
- Realism: slip 1 tick, spread model, fee $1.50/unit.
- NQ: $20/pt, tick 0.25. NAS100 CFD: $1/pt, tick 0.1.

## Hubs

| Market | Hub |
|--------|-----|
| NQ | [`../nq_1h_first_hour_broker_variants/`](../nq_1h_first_hour_broker_variants/SUMMARY.md) |
| NAS100 | [`../nas100_1h_first_hour_broker_variants/`](../nas100_1h_first_hour_broker_variants/SUMMARY.md) |

Diagnostic precursors: `nq_1h_first_hour_ha/`, `nq_1h_first_hour_broker/`, half-body / retrace diagnostic hubs under `live/state/nq_1h_first_hour_*`.
