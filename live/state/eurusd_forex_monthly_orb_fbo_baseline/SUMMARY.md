# EURUSD Forex Monthly ORB FBO Baseline (promoted)

**Status:** Promoted FX monthly sleeve (2026-07-18)
**Plugin:** `MonthlyOrbV2bOcoStrategy` (`live/strategies/monthly_orb_v2b_oco.py`)
**Family:** Monthly ORB · first-break opposite · close-SL · runner@2R · BE after TP25

## Rules

- OR = first **3** daily sessions of the month
- Ignore first OR break; arm stop in the **opposite** direction
- Max **2** fills/month; flatten month-end
- Ladder: **TP1 = 0.25R**, **TP2 = 1R**, **runner TP = 2R**
- After TP1 (TP25): remaining stop → **breakeven**
- Protective exit: daily **close** beyond stop (wicks ignored)
- Fee $7/unit, Engine + PaperBroker, 1-tick slippage

## Promoted variants

| Structure | Qty | Campaigns | WR | Hit 1R | Hit 2R | Net | Stress DD | Net/Stress |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| **1/1/3** | 1/1/3 (entry 5) | 173 | 50.3% | 34.7% | 15.6% | **$77,282** | $-74,027 | **1.04** |
| **1/2/3** | 1/2/3 (entry 6) | 173 | 50.3% | 34.7% | 15.6% | **$90,640** | $-88,758 | **1.02** |

**Primary (efficiency):** `1/1/3` at **1.04** Net/Stress.
**Primary (absolute net):** `1/2/3` at **+$90.6k**.

## Pack contents

- [`ONE_PAGE_PITCH.md`](ONE_PAGE_PITCH.md)
- [`variant_1_1_3/`](variant_1_1_3/) · [`variant_1_2_3/`](variant_1_2_3/)
- Post-TP2 path study: [`../eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/post_tp2_study/SUMMARY.md`](../eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/post_tp2_study/SUMMARY.md)
- Source stress: [`../eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/SUMMARY.md`](../eurusd_monthly_orb_fbo_runner2r_be_tp1_broker/SUMMARY.md)

## vs FX intraday sleeve

| Sleeve | Net | Stress DD | Net/Stress |
|---|---:|---:|---:|
| Hourly ST+PMC (intraday baseline) | +$23.5k | −$15.7k | 1.49 |
| Monthly FBO 1/1/3 | +$77.3k | −$74.0k | 1.04 |
| Monthly FBO 1/2/3 | +$90.6k | −$88.8k | 1.02 |

Monthly FBO is the higher-net / higher-heat monthly sleeve; intraday ST+PMC remains the tighter Net/Stress day book.
