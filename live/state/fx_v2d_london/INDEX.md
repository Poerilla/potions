# FX / metals / CFD v2d fade — London session

StrategyPlugin: `v2d_fade` (fade OR break via stop retest; qty=1).

London clock (America/New_York):
- OR **03:00–03:15**
- Flatten **11:59**

JPY pairs reported with native P&L and ≈USD via `/110`.

| Rank | Symbol | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |
|---:|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | XAUUSD | 1929 | 3426 | $-69526 | $-103188 | -0.67 | 51.0 | 0.843 |
| 2 | NAS100 | 895 | 1592 | $-3170 | $-3484 | -0.91 | 50.8 | 0.854 |
| 3 | US30 | 836 | 1485 | $-4768 | $-5216 | -0.91 | 51.1 | 0.861 |
| 4 | XAGUSD | 1553 | 2728 | $-102143 | $-103487 | -0.99 | 31.0 | 0.400 |
| 5 | EURUSD | 1354 | 2505 | $-77302 | $-77662 | -1.00 | 34.7 | 0.227 |
| 6 | USDJPY | 1679 | 2966 | $-72278 | $-72576 | -1.00 | 43.3 | 0.478 |
| 7 | AUDJPY | 1429 | 2504 | $-67098 | $-67272 | -1.00 | 45.4 | 0.466 |
| 8 | GBPUSD | 1435 | 2660 | $-89478 | $-89593 | -1.00 | 40.5 | 0.272 |

Hub: `live/state/fx_v2d_london`
