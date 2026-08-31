# NQ HP envelope range breakout sidecar (1m broker)

- Range = envelope of month open + up/dn bands + p_liq + 1R SL (known at t_liq)
- No signal during liq window; **4h close** outside → limit at boundary
- SL = **2x_liq**; target = range size; max **2** attempts
- Session-gap void: no fill if open gaps through/adverse (esp. near SL); retag required
- Engine + PaperBroker 1m; slip 1 tick + spread

## Results

| Metric | Value |
|---|---:|
| Plans | 34 |
| Entries | 20 |
| Units | 200 |
| Net $ | +278730 |
| Stress DD $ | 197065 |
| N/S | 1.41 |

Compare: base HP 1m liq@p_liq reentry ≈ +$552k / N/S 1.03 (183 entries).

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_range_breakout_hp_1m_broker`

Stance: sidecar research (separate from fade book)

See `CAUSALITY.md` for when bands / range / SL are live-known.
