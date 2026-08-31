# ES quarterly breakout — Weekly ATR **aligned** causal broker-like

HP coupon: Weekly ATR aligned n=49 +1.8pp +$0.7k NOT VALIDATED (ΔN/S −0.81, p_master 1.00)

Plugin gate: `require_w_atr_aligns=["w_atr_aligned"]` on `quarterly_range_breakout` (Weekly ATR SuperTrend 14×3 vs trade side; next-open fills via `live_after_ts`).

Decision-bar weekly ATR uses completed W-FRI bars (Friday close finalizes that week). HP coupon uses a +1 calendar-day asof shift, so gated trade count may differ from n=49.

## Comparison

| Book | Trades | Net | Stress DD | N/S |
|---|---:|---:|---:|---:|
| Baseline (ungated) | 60 | $1,258,367.50 | $-225,184.00 | 5.59 |
| **w_atr_aligned gated** | **58** | **$1,169,911.50** | **$-235,924.50** | **4.96** |

## Stance

research — plugin-gated w_atr_aligned book; HP size-up stays NOT VALIDATED

## Hubs

- Gated: `live/state/es_quarterly_breakout_w_atr_aligned_broker/`
- Baseline: `live/state/es_quarterly_range_breakout_broker/`
- HP nulls: `live/state/es_quarterly_breakout_hp_nulls/`

---

# ES quarterly range honest breakout (broker-like)

Engine + PaperBroker on **ES daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Monthly OR gate:** none
- **Yearly ORB gate:** none
- **Weekly ATR align gate:** `require_w_atr_aligns=w_atr_aligned` (plugin arms only when causal weekly ATR SuperTrend aligns with trade side).
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · ES $50/pt · tick 0.25

## Results

- Trades: **58**
- Units: **464**
- Net: **$1,169,911.50**
- Closed DD: **$-233,599.50**
- Stress DD: **$-235,924.50**
- Net/|stress|: **4.96**
- Win units: **338** / Loss units: **126**

## Fill reasons

- `entry`: **58**
- `tp1`: **50**
- `flatten`: **36**
- `tp2`: **30**
- `tp3`: **17**
- `stop`: **11**
- `tp4`: **11**

## Files

- `states/es_quarterly_range_breakout_w_atr_aligned/fills.csv`
- `audits/`
