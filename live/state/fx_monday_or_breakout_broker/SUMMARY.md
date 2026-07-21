# FX Monday OR breakout — broker-like (StrategyPlugin)

Plugin: `monday_or_breakout` · Engine + PaperBroker · 15m bars · 1-tick slip · $1.50/unit fee.

**Progress log:** [`PROGRESS.md`](PROGRESS.md)  
**Research narrative:** [`../eurusd_monday_or_breakout_15m/RESEARCH.md`](../eurusd_monday_or_breakout_15m/RESEARCH.md)  
**Family CE ranking (pandas):** [`../eurusd_monday_or_breakout_15m/MONDAY_ORB_FAMILY.md`](../eurusd_monday_or_breakout_15m/MONDAY_ORB_FAMILY.md)  
**STRATEGY_TRACKER:** Forex section in `mnq/case_studies/STRATEGY_TRACKER.md`

## Rules

- Mon OR H/L → Tue–Fri close breakout; **3** lots; drop **2**@30% DD, cut **1**@50%; SL=1R TP=2R.
- **Shifted primary** after flat@50% (opposite Mon extreme, same structure).
- **HTF filter:** skip when last 1h MA50/150 and OBV×SMA20 both opposed.
- Max 2 primary trades/week.

## Results (ranked by Net/Stress; JPY pairs also show ≈USD @ 110)

| Rank | Pair | Units | Net | Stress DD | **N/S** | ≈USD net | ≈USD N/S |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | **USDJPY** | 7209 | ¥15191346 | ¥-3560066 | **4.27** | $138103 | **4.27** |
| 2 | **GBPUSD** | 7374 | 202248 | -108390 | **1.87** | $202248 | **1.87** |
| 3 | **AUDJPY** | 7116 | ¥6457606 | ¥-6036065 | **1.07** | $58706 | **1.07** |
| 4 | **XAUUSD** | 7133 | 259829 | -248813 | **1.04** | $259829 | **1.04** |
| 5 | **EURUSD** | 7422 | 76029 | -91668 | **0.83** | $76029 | **0.83** |
| 6 | **XAGUSD** | 6471 | -194820 | -195733 | **-1.00** | $-194820 | **-1.00** |

## vs STRATEGY_TRACKER FX intraday baseline

Promoted FX **intraday** sleeve today: Hourly ST+PMC MA-bull (EURUSD **+$23.5k / −$15.7k / 1.49** Net/Stress).
Monthly FBO sleeves are a different horizon ($7 fee pack).

Research pandas sim (EURUSD, not broker): shiftprim+HTF **+$124.6k / −$56.4k closed / 2.21** Net/|DD| — broker slip + next-open entry compresses EURUSD to **0.83**.

**Viability stance:** Do not replace EURUSD ST+PMC. Sleeve is **USDJPY / GBPUSD-first**.

## Sizing sweep Phase 1 (pandas; post-dates this broker book)

This broker book uses pre-sweep **`M1_S1_R1`** (main 3 / shifted 3 / max 2/week).  
Research winners (not yet broker-confirmed):

| Pair | Tag | Change vs this book |
|---|---|---|
| EURUSD | **`M1_S2_R2`** CE 3.28 | Lighter shifted (2); max primary/week **3** |
| USDJPY | **`M3_S3_R2`** CE 13.37 | Main **2**; shifted **4**; max **3**/week |

Hub: [`../monday_or_sizing_sweep/INDEX.md`](../monday_or_sizing_sweep/INDEX.md).

## Charts

- USDJPY 100 winners + 100 losers: [`charts_usdjpy/`](charts_usdjpy/) ([INDEX](charts_usdjpy/INDEX.md))

## Regen

```bash
python3 -m live.fx_monday_or_breakout_broker
python3 -m live.usdjpy_monday_or_broker_charts
```

State root: `/home/tester/hsm/potions/live/state/fx_monday_or_breakout_broker`
