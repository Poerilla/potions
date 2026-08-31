# Monthly ±4×ATR fade ladder (broker-like, 1h)

Engine + PaperBroker on **1h** bars. Calendar-month open-week mid ±4×ATR(14).
10 lots; scale 2 off @ +2/+4/+6/+8 ATR; then BE → EOM (2 runners).
Mode / sides / risk come from family default or monthly best-path.

| Market | Path | Mode | Sides | Risk | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |
|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD |  | first_only | lower | 2.00×ATR | 142,988 | 135 | 1350 | $-115,794 | $-183,879 | -0.63 | 18.5% | 0.67 |
| GBPUSD |  | first_only | lower | 2.00×ATR | 142,979 | 152 | 1520 | $-56,492 | $-106,700 | -0.53 | 23.3% | 0.88 |
| USDJPY |  | first_only | lower | 2.00×ATR | 142,657 | 131 | 1310 | $-1,015,397 | $-5,227,612 | -0.19 | 25.0% | 0.97 |
| AUDJPY |  | first_only | lower | 2.00×ATR | 139,327 | 107 | 1070 | $6,711,160 | $-6,775,293 | 0.99 | 27.3% | 1.22 |
| XAUUSD |  | first_only | lower | 2.00×ATR | 138,745 | 113 | 1130 | $75,968 | $-224,203 | 0.34 | 25.1% | 1.12 |
| XAGUSD |  | first_only | lower | 2.00×ATR | 135,759 | 93 | 930 | $3,330 | $-45,647 | 0.07 | 29.5% | 1.01 |
| US30 |  | second_only | lower,upper | 0.50×ATR | 49,325 | 33 | 330 | $-4,702 | $-13,238 | -0.36 | 10.9% | 0.59 |
| NAS100 |  | second_only | lower,upper | 0.50×ATR | 51,889 | 32 | 320 | $-3,855 | $-7,949 | -0.48 | 8.8% | 0.59 |
| NQ |  | second_only | lower,upper | 0.50×ATR | 95,471 | 61 | 610 | $11,795 | $-166,997 | 0.07 | 8.5% | 1.07 |
| YM |  | second_only | lower,upper | 0.50×ATR | 94,906 | 58 | 580 | $-50,051 | $-79,761 | -0.63 | 10.7% | 0.56 |

Hub: `live/state/monthly_atr4_fade_ladder`

Promote gate: research until causality audit + multi-year N/S hold.
