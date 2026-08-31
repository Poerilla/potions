# Quarterly ±4×ATR first-touch fade (broker-like)

Engine + PaperBroker on **4h** bars. Open-week mid ±4×ATR(14); first touch fades;
2 contracts; 1@mid + runner@opposite ±4×ATR; reverse once on runner fill;
max 2 trades/quarter; risk = 0.5× open-week range.

| Market | Bars | Trades | Units | Net | Stress DD | N/S | WR | PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GBPUSD | 36,960 | 107 | 214 | $7,751 | $-25,825 | 0.30 | 26.2% | 1.06 |
| US30 | 13,668 | 41 | 82 | $3,468 | $-5,790 | 0.60 | 28.0% | 1.18 |
| NAS100 | 13,767 | 36 | 72 | $-2,714 | $-5,838 | -0.46 | 13.9% | 0.74 |

Hub: `/home/tester/hsm/potions/live/state/quarterly_atr4_fade_broker`

Promote gate: treat as research until causality audit + multi-year N/S hold.
