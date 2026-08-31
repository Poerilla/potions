# ES quarterly breakout — Yearly ORB **up** causal broker-like

HP coupon: Yearly ORB up n=33 +4.1pp +$1.4k NOT VALIDATED (ΔN/S +0.15, p_master 1.00)

Plugin gate: `require_yor_dirs=["yor_up"]` on `quarterly_range_breakout` (causal Jan–Mar Yearly ORB; ready Apr 1; next-open fills via `live_after_ts`).

Decision-bar Yearly ORB matches close→next-open causality. HP coupon uses a +1 session asof shift, so gated trade count may differ from n=33.

## Comparison

| Book | Trades | Net | Stress DD | N/S |
|---|---:|---:|---:|---:|
| Baseline (ungated) | 60 | $1,258,367.50 | $-225,184.00 | 5.59 |
| **yor_up gated** | **40** | **$939,517.50** | **$-225,184.00** | **4.17** |

## Stance

research — plugin-gated yor_up book; HP size-up stays NOT VALIDATED

## Hubs

- Gated: `live/state/es_quarterly_breakout_yor_up_broker/`
- Baseline: `live/state/es_quarterly_range_breakout_broker/`
- HP nulls: `live/state/es_quarterly_breakout_hp_nulls/`
