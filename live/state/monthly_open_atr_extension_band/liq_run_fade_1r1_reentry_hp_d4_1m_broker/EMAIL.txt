# NQ liq-run fade 1:1 HP — broker-like **1m** (liq first **4** days)

- Engine + PaperBroker; slip 1 tick + spread model
- Universe: lookback HP OR months (**118** plans)
- Liq run: largest |ext| from month open over first **4** NY trading days
- Structure: limit @ p_liq, SL=1R, target=month open, qty **10**
- Re-entry: **TP re-arms immediately**; stop → wait open-touch

## Results

| Metric | Value |
|---|---:|
| Entries | 124 |
| Units | 1240 |
| Net $ | -990385 |
| Stress DD $ | 1642815 |
| N/S | -0.60 |

2d 1m broker HP: +$552k / N/S 1.03 (183 entries).

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_d4_1m_broker`

Stance: broker-like 1m (liq-days sensitivity).
