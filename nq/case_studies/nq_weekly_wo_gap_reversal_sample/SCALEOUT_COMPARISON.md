# WO gap reversal — scale-out exit comparison (2023+)

Entry rules unchanged.
- **2ct modes:** +50 on leg 1 → BE on runner; runner @ 300 or 600.
- **3ct mode:** +50 / +300 / +600 ladder; BE on remainder after +50.
- Initial stop: **50 pts** on all open contracts (stop-first intrabar).
- Week rule: no 2nd trade after +50 hit or full target (same as a win).

## Short Only

| Mode | Trades | Net pts | Win% | PF | Avg/trade | Max DD | Max loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline 1ct → 300 | 62 | +2356.8 | 27.4 | 2.05 | +38.0 | -450 | 9 |
| 2ct: +50 / runner 300 | 62 | +3040.5 | 69.4 | 2.60 | +49.0 | -700 | 6 |
| 2ct: +50 / runner 600 | 62 | +4124.2 | 69.4 | 3.17 | +66.5 | -700 | 6 |
| 3ct: +50 / +300 / +600 | 62 | +281.0 | 69.4 | 1.10 | +4.5 | -1400 | 6 |

- **2ct: +50 / runner 300** vs baseline: net +683.8 pts, max DD -250 pts, loss streak -3.
- **2ct: +50 / runner 600** vs baseline: net +1767.5 pts, max DD -250 pts, loss streak -3.
- **3ct: +50 / +300 / +600** vs baseline: net -2075.8 pts, max DD -950 pts, loss streak -3.

## Both

| Mode | Trades | Net pts | Win% | PF | Avg/trade | Max DD | Max loss streak |
|---|---:|---:|---:|---:|---:|---:|---:|
| Baseline 1ct → 300 | 114 | +2206.8 | 21.1 | 1.49 | +19.4 | -700 | 14 |
| 2ct: +50 / runner 300 | 100 | +3140.5 | 65.0 | 1.90 | +31.4 | -950 | 3 |
| 2ct: +50 / runner 600 | 100 | +3873.5 | 65.0 | 2.11 | +38.7 | -950 | 3 |
| 3ct: +50 / +300 / +600 | 100 | -469.8 | 65.0 | 0.91 | -4.7 | -1951 | 3 |

- **2ct: +50 / runner 300** vs baseline: net +933.8 pts, max DD -250 pts, loss streak -11.
- **2ct: +50 / runner 600** vs baseline: net +1666.8 pts, max DD -250 pts, loss streak -11.
- **3ct: +50 / +300 / +600** vs baseline: net -2676.5 pts, max DD -1251 pts, loss streak -11.
