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
