# NQ liq-run fade 1:1 HP — broker-like **1m** fill tape

- Engine + PaperBroker; slip 1 tick + spread model
- Universe: lookback HP OR months (**2** plans)
- Structure: limit @ p_liq, SL=1R, target=month open, qty **10**
- Re-entry: **TP re-arms immediately**; stop → wait open-touch

## Results

| Metric | Value |
|---|---:|
| Trades | 1 |
| Units | 10 |
| Net $ | +5060 |
| Stress DD $ | 3450 |
| N/S | 1.47 |

1h path sim HP: +$618k / N/S 2.24 (164 fills).

Hub: `live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_1m_broker_smoke`

Stance: broker-like 1m (promote-gate candidate vs 1h path sim).
