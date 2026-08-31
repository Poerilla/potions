# Quarterly ±4×ATR fade ladder (broker-like)

Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14).
10 lots; scale 2 off every +2 ATR through +8 ATR (tp1–tp4); then BE → EOQ (2 runners).
Mode / sides / risk come from per-market book (family default or best-path).

| Market | Path | Mode | Sides | Risk | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD |  | first_only | lower | 2.00×ATR | 36,962 | 47 | 470 | $97,584 | $-85,191 | 1.15 | 34.9% | 1.43 |
| GBPUSD |  | first_only | lower | 2.00×ATR | 36,960 | 51 | 510 | $404,130 | $-50,565 | 7.99 | 48.6% | 2.85 |
| USDJPY |  | first_only | lower | 2.00×ATR | 36,892 | 41 | 410 | $-13,357,794 | $-17,031,420 | -0.78 | 11.2% | 0.38 |
| AUDJPY |  | first_only | lower | 2.00×ATR | 36,022 | 36 | 360 | $-1,030,641 | $-10,817,189 | -0.10 | 28.3% | 0.95 |
| XAUUSD |  | first_only | lower | 2.00×ATR | 36,439 | 30 | 300 | $251,054 | $-61,551 | 4.08 | 42.7% | 2.47 |
| XAGUSD |  | first_only | lower | 2.00×ATR | 35,920 | 23 | 230 | $7,446 | $-41,580 | 0.18 | 29.6% | 1.12 |
| US30 |  | second_only | lower,upper | 0.50×ATR | 13,668 | 12 | 120 | $-3,335 | $-12,869 | -0.26 | 11.7% | 0.65 |
| NAS100 |  | second_only | lower,upper | 0.50×ATR | 13,767 | 9 | 90 | $8,680 | $-6,211 | 1.40 | 26.7% | 2.99 |
| NQ |  | second_only | lower,upper | 0.50×ATR | 25,531 | 17 | 170 | $215,139 | $-121,991 | 1.76 | 17.6% | 4.89 |
| YM |  | second_only | lower,upper | 0.50×ATR | 25,378 | 21 | 210 | $24,477 | $-49,397 | 0.50 | 19.0% | 1.43 |

Hub: `live/state/quarterly_atr4_fade_ladder`

Promote gate: research until causality audit + multi-year N/S hold.
