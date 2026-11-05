# FX / metals / CFD ungated v2b — London session

StrategyPlugin: `v2b_scaleout` (OCO, no prior-opposed gate).

London clock (America/New_York):
- OR **03:00–03:15** (not ~02:00 / 02:30)
- Flatten **11:59**

JPY pairs reported with native P&L and ≈USD via `/110`.

| Rank | Symbol | Book | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 6J | S_1_1_3 | 1254 | 2162 | $-257856 | $-259235 | -0.99 | 24.6 | 0.679 |

- Hub: `/home/tester/hsm/potions/live/state/6j_v2b_london_ungated_S_1_1_3`
- Fee: FX/metals $7/unit; US30/NAS100 $1.50/unit; 1-tick slip + ETH-aware spread.

