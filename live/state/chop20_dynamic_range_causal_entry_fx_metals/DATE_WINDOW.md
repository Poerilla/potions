# CHOP20 causal FX/metals — date-window post filter

Generated: 2026-08-28T22:37:43

Method: subset the finished baseline `trades.csv` by entry year.
This is a **post-run filter** — recommended windows need a fresh re-sim
before promotion (do not cherry-pick mid-stream).

## US30 / close_to_globex baseline

Full: n=70 net=-18334 USD N/S=-0.81

### Year blocks

| block | n | net | WR | share_net |
|---|---:|---:|---:|---:|
| 2003–2010 | 0 | — | — | — |
| 2011–2015 | 0 | — | — | — |
| 2016–2019 | 16 | -3766 | 19% | 21% |
| 2020–2022 | 45 | -3155 | 13% | 17% |
| 2023–2026 | 9 | -11412 | 33% | 62% |

### Start-date trims (keep entry_ts ≥ year-start)

| start | n | net | vs full |
|---|---:|---:|---:|
| 2017 | 70 | -18334 | +0 |
| 2018 | 69 | -20441 | -2108 |
| 2019 | 59 | -15738 | +2596 |
| 2020 | 54 | -14567 | +3766 |
| 2021 | 47 | -12522 | +5812 |
| 2022 | 22 | -10220 | +8114 |

**Window stance:** weak full-sample — optional research window from 2022

## GBPUSD / close_to_globex baseline

Full: n=197 net=-117526 USD N/S=-0.73

### Year blocks

| block | n | net | WR | share_net |
|---|---:|---:|---:|---:|
| 2003–2010 | 86 | -41060 | 19% | 35% |
| 2011–2015 | 28 | -48276 | 7% | 41% |
| 2016–2019 | 26 | -9789 | 12% | 8% |
| 2020–2022 | 25 | -11203 | 44% | 10% |
| 2023–2026 | 32 | -7200 | 25% | 6% |

### Start-date trims (keep entry_ts ≥ year-start)

| start | n | net | vs full |
|---|---:|---:|---:|
| 2004 | 197 | -117526 | +0 |
| 2005 | 188 | -110749 | +6778 |
| 2006 | 173 | -83116 | +34410 |
| 2007 | 159 | -91324 | +26203 |
| 2008 | 133 | -72074 | +45453 |
| 2009 | 125 | -87852 | +29675 |
| 2010 | 114 | -73892 | +43634 |
| 2014 | 111 | -76467 | +41060 |
| 2015 | 101 | -72313 | +45214 |
| 2016 | 83 | -28191 | +89335 |
| 2017 | 75 | -22948 | +94579 |
| 2019 | 64 | -14808 | +102719 |
| 2020 | 57 | -18403 | +99124 |
| 2021 | 40 | +19387 | +136913 |
| 2022 | 39 | +16507 | +134034 |

**Window stance:** weak full-sample — optional research window from 2021

## XAGUSD / close_to_globex baseline

Full: n=208 net=+7758 USD N/S=0.15

### Year blocks

| block | n | net | WR | share_net |
|---|---:|---:|---:|---:|
| 2003–2010 | 122 | -27834 | 16% | -359% |
| 2011–2015 | 45 | +7373 | 20% | 95% |
| 2016–2019 | 10 | -9263 | 20% | -119% |
| 2020–2022 | 4 | +54 | 50% | 1% |
| 2023–2026 | 27 | +37428 | 44% | 482% |

### Start-date trims (keep entry_ts ≥ year-start)

| start | n | net | vs full |
|---|---:|---:|---:|
| 2004 | 208 | +7758 | +0 |
| 2005 | 198 | +11063 | +3306 |
| 2006 | 178 | +10824 | +3066 |
| 2007 | 159 | +22651 | +14893 |
| 2008 | 125 | +36895 | +29137 |
| 2009 | 108 | +39352 | +31595 |
| 2010 | 105 | +47751 | +39993 |
| 2011 | 86 | +35592 | +27834 |
| 2012 | 82 | +27716 | +19959 |
| 2013 | 65 | +38979 | +31221 |
| 2014 | 62 | +25347 | +17590 |
| 2015 | 58 | +23172 | +15415 |
| 2016 | 41 | +28219 | +20462 |

**Window stance:** research re-sim from 2010-01-01 (post-filter lift +39993)

## SPX500 / close_to_globex baseline

Full: n=56 net=+1812 USD N/S=1.17

### Year blocks

| block | n | net | WR | share_net |
|---|---:|---:|---:|---:|
| 2003–2010 | 0 | — | — | — |
| 2011–2015 | 0 | — | — | — |
| 2016–2019 | 29 | +207 | 34% | 11% |
| 2020–2022 | 13 | +245 | 31% | 14% |
| 2023–2026 | 14 | +1360 | 29% | 75% |

### Start-date trims (keep entry_ts ≥ year-start)

| start | n | net | vs full |
|---|---:|---:|---:|
| 2016 | 56 | +1812 | +0 |
| 2017 | 43 | +1872 | +59 |
| 2018 | 41 | +1342 | -471 |
| 2019 | 35 | +1680 | -133 |
| 2021 | 27 | +1605 | -207 |
| 2022 | 18 | +1420 | -392 |
| 2023 | 14 | +1360 | -453 |

**Window stance:** keep full history

Hub: `/home/tester/hsm/potions/live/state/chop20_dynamic_range_causal_entry_fx_metals`
