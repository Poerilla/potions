# FX Monday OR breakout — broker-like (StrategyPlugin)

Plugin: `monday_or_breakout` · Engine + PaperBroker · 15m bars · 1-tick slip · $1.50/unit fee.

## Rules

- Mon OR H/L → Tue–Fri close breakout; **3** lots; drop **2**@30% DD, cut **1**@50%; SL=1R TP=2R.
- **Shifted primary** after flat@50% (opposite Mon extreme, same structure).
- **HTF filter:** skip when last 1h MA50/150 and OBV×SMA20 both opposed.
- Max 2 primary trades/week.

## Results (ranked by Net/Stress; JPY pairs also show ≈USD @ 110)

| Rank | Pair | Units | Net | Stress DD | **N/S** | ≈USD net | ≈USD N/S |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | **US30** | 2784 | 14910 | -28124 | **0.53** | $14910 | **0.53** |

## vs STRATEGY_TRACKER FX intraday baseline

Promoted FX **intraday** sleeve today: Hourly ST+PMC MA-bull (EURUSD **+$23.5k / −$15.7k / 1.49** Net/Stress).
Monthly FBO sleeves are a different horizon ($7 fee pack).

Research pandas sim (EURUSD, not broker): shiftprim+HTF **+$124.6k / −$56.4k closed / 2.21** Net/|DD| — expect broker slip + next-open entry to compress that.

State root: `/home/tester/hsm/potions/live/state/fx_monday_or_breakout_broker`
