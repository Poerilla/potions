# NQ liq-run fade 1:1 HP — broker-like **1m** fill tape

- Engine + PaperBroker; slip 1 tick + spread model
- Universe: lookback HP OR months (**118** plans)
- Structure: limit @ p_liq, SL=1R, target=month open, qty **10**
- Re-entry: **TP re-arms immediately**; stop → wait open-touch

## Results

| Metric | Value |
|---|---:|
| Entries | 183 |
| Units | 1830 |
| Net $ | +552318 |
| Stress DD $ | 538235 |
| N/S | 1.03 |

1h path sim HP: +$618k / N/S 2.24 (164 fills).

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_hp_1m_broker`

Stance: broker-like 1m (promote-gate candidate vs 1h path sim).
