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

