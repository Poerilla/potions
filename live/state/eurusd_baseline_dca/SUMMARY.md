# EURUSD FX baseline + DCA

Promoted sleeve `sl25_tp75_3r_ma_bull_prior` with optional ST-retest DCA adds
(each add = own 25/75 bracket at current SuperTrend, while thesis holds).

| max_adds | Net | Stress DD | Net/Stress | Units | WR | Max open | vs baseline net |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $-4,815.82 | $-22,589.46 | -0.213 | 1127 | 26.4% | 1 | $-28350 |
| 2 | $-14,675.34 | $-36,839.31 | -0.398 | 1511 | 25.9% | 2 | $-38209 |
| 3 | $-22,858.84 | $-43,419.31 | -0.526 | 1650 | 25.4% | 3 | $-46393 |
| 5 | $-26,424.34 | $-46,230.81 | -0.572 | 1727 | 25.3% | 5 | $-49958 |

Promoted pack reference: net **$23533.68** / stress **−$15745.46** / Net/Stress **1.49**.
FX half-spread: **on**. Fee $1.50/unit.

Control (max_adds=1) should be near the promoted tape; DCA rows test scale-in.

This-run control: net $-4815.82 / stress $-22589.46 / Net/Stress -0.213.
