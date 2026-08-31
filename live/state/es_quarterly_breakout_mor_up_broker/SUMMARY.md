# ES quarterly breakout — Monthly OR **up** causal broker-like

HP coupon (diagnostic): Monthly OR up n=26 +12.9pp +$10.9k **NOT VALIDATED**
(best ΔN/S +1.34, p_master 0.26).

## What ran

Plugin gate `require_mor_dirs=["mor_up"]` on `quarterly_range_breakout`
(Engine + PaperBroker, ES daily, next-open fills via `live_after_ts`).

Monthly OR = first 3 sessions; direction known after **decision bar close**
(same bar that arms the breakout). That matches causal close→next-open.

## Comparison

| Book | Trades | Net | Stress DD | N/S |
|---|---:|---:|---:|---:|
| Baseline (ungated) | 60 | $1,258,367.50 | $-225,184.00 | 5.59 |
| **mor_up gated** | **50** | **$1,172,655.00** | **$-268,912.00** | **4.36** |

## Why gated n≠26

HP profile tags `mor_dir` with a **+1 calendar-day** HTF availability shift.
For this daily close→next-open book, that lags the decision bar by one session
(example: 2023-05-18 arm is mor_up at decision close; HP asof labels it mor_down).
Plugin gate uses decision-bar-complete MOR → **50** arms, not the coupon's 26.

## Stance

**Reject mor_up as a sit-out / size-up gate.** Broker N/S **5.59 → 4.36**, net down,
stress worse. Matches null-suite **NOT VALIDATED**. Keep ungated quarterly breakout.

## Hubs

- Gated: `live/state/es_quarterly_breakout_mor_up_broker/`
- Baseline: `live/state/es_quarterly_range_breakout_broker/`
- HP nulls: `live/state/es_quarterly_breakout_hp_nulls/`

---
|---:|---:|---:|---:|
| Baseline (ungated) | 60 | $1,258,367.50 | $-225,184.00 | 5.59 |
| **mor_up gated** | **50** | **$1,172,655.00** | **$-268,912.00** | **4.36** |

## Stance

research — plugin-gated mor_up book; HP size-up stays NOT VALIDATED

## Hubs

- Gated: `live/state/es_quarterly_breakout_mor_up_broker/`
- Baseline: `live/state/es_quarterly_range_breakout_broker/`
- HP nulls: `live/state/es_quarterly_breakout_hp_nulls/`

---

# ES quarterly range honest breakout (broker-like)

Engine + PaperBroker on **ES daily**. Market entries fill next open (`live_after_ts`).

## Rules

- Breakout = daily **close** outside prior-quarter H/L → market **8**.
- **Allowed sides:** long, short
- **Monthly OR gate:** `require_mor_dirs=mor_up` (plugin arms only when causal mor_dir matches; stricter than post-filtering fills).
- **SL** fixed at prior-range **mid** (halfway). **No BE** move.
- Scale **2** contracts every **0.2 ×** prior width from entry (targets at 0.2 / 0.4 / 0.6 / 0.8).
- Multiple breakouts per quarter while flat; flatten at quarter end.

- Slippage: **1** tick · fee **$1.50**/unit · ES $50/pt · tick 0.25

## Results

- Trades: **50**
- Units: **400**
- Net: **$1,172,655.00**
- Closed DD: **$-265,012.00**
- Stress DD: **$-268,912.00**
- Net/|stress|: **4.36**
- Win units: **320** / Loss units: **80**

## Fill reasons

- `entry`: **50**
- `flatten`: **39**
- `tp1`: **39**
- `tp2`: **28**
- `tp3`: **15**
- `stop`: **6**
- `tp4`: **5**

## Files

- `states/es_quarterly_range_breakout_mor_up/fills.csv`
- `audits/`
