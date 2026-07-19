# EURUSD FX baseline + DCA

**Verdict: DCA does not boost the FX baseline.** Keep single-unit promoted sleeve.

Promoted sleeve `sl25_tp75_3r_ma_bull_prior` with optional ST-retest DCA adds
(each add = own 25/75 bracket at current SuperTrend, while thesis holds).

| max_adds | Net | Stress DD | Net/Stress | Units | WR | Max open | vs baseline net |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | $23,533.68 | $-15,745.46 | 1.495 | 1148 | 27.4% | 1 | $+0 |
| 2 | $20,940.16 | $-26,247.25 | 0.798 | 1570 | 26.8% | 2 | $-2594 |
| 3 | $17,315.66 | $-30,837.25 | 0.562 | 1735 | 26.5% | 3 | $-6218 |
| 5 | $14,331.16 | $-32,893.25 | 0.436 | 1838 | 26.2% | 5 | $-9203 |

Promoted pack reference: net **$23533.68** / stress **−$15745.46** / Net/Stress **1.49**.
FX half-spread: **off**. Fee $1.50/unit.

Control (max_adds=1) should be near the promoted tape; DCA rows test scale-in.

This-run control: net $23533.68 / stress $-15745.46 / Net/Stress 1.495.
