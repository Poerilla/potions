# Quarterly ±4×ATR fade ladder (broker-like)

Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14).
10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).
Mode / sides / risk come from per-market book (family default or best-path).

| Market | Path | Mode | Sides | Risk | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | second_after_upper | second_only | lower | 2.00×ATR | 36,962 | 16 | 160 | $84,627 | $-34,662 | 2.44 | 35.0% | 2.56 |
| GBPUSD | first_lower | first_only | lower | 2.00×ATR | 36,960 | 51 | 510 | $404,130 | $-50,565 | 7.99 | 48.6% | 2.85 |
| USDJPY | second_after_lower | second_only | upper | 1.50×ATR | 36,892 | 8 | 80 | $2,184,107 | $-2,304,586 | 0.95 | 27.5% | 2.00 |
| AUDJPY | second_after_lower | second_only | upper | 2.50×ATR | 36,022 | 11 | 110 | $1,586,851 | $-5,459,348 | 0.29 | 36.4% | 1.23 |
| XAUUSD | second_after_upper | second_only | lower | 0.50×ATR | 36,439 | 15 | 150 | $-36,023 | $-77,273 | -0.47 | 9.3% | 0.35 |
| XAGUSD | second_after_lower | second_only | upper | 1.50×ATR | 35,920 | 9 | 90 | $-2,386 | $-14,716 | -0.16 | 24.4% | 0.89 |
| US30 | first_lower | first_only | lower | 0.50×ATR | 13,668 | 11 | 110 | $6,016 | $-7,127 | 0.84 | 18.2% | 1.92 |
| NAS100 | first_lower | first_only | lower | 2.00×ATR | 13,767 | 9 | 90 | $33,127 | $-7,471 | 4.43 | 40.0% | 5.54 |
| NQ | second_after_upper | second_only | lower | 1.50×ATR | 25,531 | 8 | 80 | $306,962 | $-121,108 | 2.53 | 45.0% | 11.95 |
| YM | second_after_upper | second_only | lower | 1.00×ATR | 25,378 | 8 | 80 | $29,245 | $-37,259 | 0.78 | 35.0% | 2.10 |

Hub: `live/state/quarterly_atr4_fade_ladder_best_path`

Promote gate: research until causality audit + multi-year N/S hold.
