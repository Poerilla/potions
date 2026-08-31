# NQ HP envelope range-breakout fade + half-range SO (1m broker)

- Range = envelope of month open + up/dn bands + p_liq + 1R SL (known at t_liq)
- No signal during liq window; **4h close** outside → **fade** limit at boundary
- SL = **2x_liq**; **1/2** off at range mid; runner at opposite boundary; max **2** attempts
- Engine + PaperBroker 1m; slip 1 tick + spread

## Results

| Metric | Value |
|---|---:|
| Plans | 34 |
| Entries | 28 |
| Units | 280 |
| Net $ | -891505 |
| Stress DD $ | 1173635 |
| N/S | -0.76 |

Compare: base HP 1m liq@p_liq reentry ≈ +$552k / N/S 1.03 (183 entries).

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_range_breakout_fade_half_hp_1m_broker`

Stance: fade sidecar research (half-range scale-out)

See `CAUSALITY.md` for when bands / range / SL are live-known.
