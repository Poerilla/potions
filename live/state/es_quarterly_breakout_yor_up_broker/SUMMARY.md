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

---

# ES quarterly range honest breakout (broker-like)

Engine + PaperBroker on **ES daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Monthly OR gate:** none
- **Yearly ORB gate:** `require_yor_dirs=yor_up` (plugin arms only when causal yor_dir matches).
- **Weekly ATR align gate:** none
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · ES $50/pt · tick 0.25

## Results

- Trades: **40**
- Units: **320**
- Net: **$939,517.50**
- Closed DD: **$-221,284.00**
- Stress DD: **$-225,184.00**
- Net/|stress|: **4.17**
- Win units: **254** / Loss units: **66**

## Fill reasons

- `entry`: **40**
- `tp1`: **37**
- `flatten`: **26**
- `tp2`: **21**
- `tp3`: **12**
- `tp4`: **8**
- `stop`: **6**

## Files

- `states/es_quarterly_range_breakout_yor_up/fills.csv`
- `audits/`
