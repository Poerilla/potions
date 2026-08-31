# Quarterly ±4×ATR fade ladder (broker-like)

Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14).
10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).
Mode / sides / risk come from per-market book (family default or best-path).

| Market | Path | Mode | Sides | Risk | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GBPUSD | first_lower | first_only | lower | 2.00×ATR | 36,960 | 51 | 510 | $404,130 | $-50,565 | 7.99 | 48.6% | 2.85 |
| XAUUSD | nan | first_only | lower | 2.00×ATR | 36,439 | 30 | 300 | $251,054 | $-61,551 | 4.08 | 42.7% | 2.47 |
| NAS100 | first_lower | first_only | lower | 2.00×ATR | 13,767 | 9 | 90 | $33,127 | $-7,471 | 4.43 | 40.0% | 5.54 |
| EURUSD | second_after_upper | second_only | lower | 2.00×ATR | 36,962 | 16 | 160 | $84,627 | $-34,662 | 2.44 | 35.0% | 2.56 |
| NQ | second_after_upper | second_only | lower | 1.50×ATR | 25,531 | 8 | 80 | $306,962 | $-121,108 | 2.53 | 45.0% | 11.95 |

Hub: `live/state/quarterly_atr4_fade_ladder_promising`

Promote gate: research until causality audit + multi-year N/S hold.
