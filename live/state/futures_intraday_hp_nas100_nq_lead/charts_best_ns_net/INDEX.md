# NAS100 HP — best ΔN/S & best Δnet charts

Best ΔN/S and best Δnet among null pairs are **the same sleeve** (94 campaigns):

| | |
|---|---|
| Condition | Hourly RSI vs trade = `rsi_against_side` @ **1.25×** |
| Identical mask | ST-event direction = `st_opposed_proxy` |
| ΔN/S | **+1.60** (17.94 → 19.54) |
| Δnet | **+$3,093** |
| Decision | **RISK THROTTLE** (p_master ΔNS ≈ 0.70) — not SIZE-UP VALIDATED |

## Broker / 1m fill check

| Layer | Verified? |
|---|---|
| Baseline `nas100_nq_lead_prior_opposed` campaigns | **Yes** — Engine + PaperBroker + StrategyPlugin on **NAS100 1m** (`live/state/nas100_v2b_nq_lead_synced_broker_like`, fills minute-aligned) |
| 1.25× HP size-up itself | **No separate Engine re-replay** — matched-added-exposure campaign reweight + null suite on that tape |

Charts: `equity_baseline_vs_1p25_rsi_against.png`, `yearly_net_baseline_vs_1p25_rsi_against.png`, `hp_boosted_extreme_trades.png`
