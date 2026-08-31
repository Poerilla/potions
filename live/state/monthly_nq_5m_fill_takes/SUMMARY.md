# NQ monthly systems — broker-like **5m fill** ranking

Signal TF unchanged per system; fills on shared full-session **5m** tape
(Engine `broker_fills=False` on HTF signals). DSR `TRL-2026-00144`.

| Rank | System | Signal | Net $ | Stress | N/S | Trades | Units |
|---:|---|---|---:|---:|---:|---:|---:|
| 1 | Band-max +0.5 · open TP + 2R runner | 1h | 897,107 | -445,475 | 2.01 | 57 | 570 |
| 2 | pct75 ladder 2/2/5 (no w4) | 1h | 761,492 | -410,423 | 1.86 | 71 | 639 |
| 3 | Monthly ORB restricted scaleout3 | D | 331,722 | -189,334 | 1.75 | 222 | 666 |
| 4 | pct75 ladder 1/1/7 (no w4) | 1h | 846,554 | -493,329 | 1.72 | 71 | 639 |
| 5 | Monthly ORB overlap daily-ST retest x5 (4h+5m) | 4H | 361,837 | -245,520 | 1.47 | 51 | 87 |
| 6 | Monthly ORB FBO 1/1/3 | D | 223,596 | -157,753 | 1.42 | 114 | 570 |
| 7 | Liq-run fade 1:1 reentry HP (5m) | 5m | 557,115 | -538,035 | 1.04 | 184 | 1840 |

## Stance

research — top 5m-fill sleeve by N/S is competitive

Hub: `/home/tester/hsm/potions/live/state/monthly_nq_5m_fill_takes`
