# NQ HP band-max fade 1:1 reentry (1m broker)

- Liq run sets **direction** only (first 2 NY days)
- Limit @ **dn max** (long) / **up max** (short)
- Target = month open; SL distance = **liq-run size**
- Re-entry: TP re-arms; stop → wait open-touch
- Engine + PaperBroker 1m; slip 1 tick + spread

## Results

| Metric | Value |
|---|---:|
| Plans | 34 |
| Entries | 23 |
| Units | 230 |
| Net $ | -252229 |
| Stress DD $ | 417500 |
| N/S | -0.60 |

Compare: base HP 1m liq@p_liq reentry ≈ +$552k / N/S 1.03 (183 entries).

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_bandmax_1r1_reentry_hp_1m_broker`

Stance: research vs p_liq entry baseline

See `CAUSALITY.md` for when bands / range / SL are live-known.
