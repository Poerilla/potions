# wide_2x runner + flip-on-stop path study

Diagnostic pandas walk on broker fills (NQ, pct75, wide_2x). Not Engine-promotable.

- Broker baseline net: **$593,461** (N/S 1.06, 73 trades)
- Study campaigns from fills: **64** (net $464,494)

## Flip opposite on stop (continuation)

After fade SL, reverse into the breakout direction from the stop fill.

| Variant | Add $ | Win% | Combined book $ |
|---|---:|---:|---:|
| EOM no stop | -344,593 | 57% | 248,868 |
| 1R tgt / 1R stop | -132,097 | 61% | 461,364 |
| 2R tgt / 1R stop | 35,989 | 61% | 629,450 |

**Read:** only 2R/1R flip is slightly positive (+$36k); EOM and 1R destroy capital. Flip-to-month-open is not a valid continuation target.

## Runners past month open (after target fill)

Incremental PnL if the target fill is kept as a new entry and held with various stops/targets until month end.

| Runner | Add $ | Win% | Stop% |
|---|---:|---:|---:|
| be_eom | -2,320 | 0% | 100% |
| fullR_1R | 285,834 | 48% | 38% |
| fullR_2R | 630,269 | 48% | 38% |
| fullR_eom | 308,321 | 45% | 41% |
| halfR_1R | 134,980 | 34% | 59% |
| halfR_eom | 58,611 | 31% | 62% |
| naked_eom | 219,080 | 48% | 0% |

**Read:** BE / half-R stops get wicked out immediately (price reclaims through open).
Giving the runner **full R** back to original entry unlocks value; naked EOM is best $ but unstopped.
Half-size **fullR→1R** add ~**$142,917**; half-size **fullR→2R** ~**$315,134**.

## Stance

- Flip-on-stop: **reject** as a default (weak / negative EV except thin 2R sleeve).
- Runners: **research** only — full-R giveback + 1R/2R extension has edge on this tape; needs broker-like + stress before promote.

Artifacts: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/broker_pct75_compare/wide_2x/runner_flip_study`

