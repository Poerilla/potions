# NQ opening-candle close-limit 3R

Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.
Realism: slip 1 tick, spread, fee $1.50/unit, NQ $20/pt.

**Contract:** green → buy limit @ close; red → sell limit @ close; SL = open (R = body); TP = 3R; cancel if SL swept before fill.

| Book | Trades | WR | Net | Stress | N/S | entries | stop | tp | eod |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 30m open candle: limit@close SL=open TP=3R | 3904 | 34.3% | $81,395 | $-42,430 | **1.92** | 3959 | 2385 | 683 | 847 |
| 1h open candle: limit@close SL=open TP=3R | 3906 | 38.5% | $144,018 | $-36,866 | **3.91** | 3985 | 2081 | 563 | 1276 |
| 30m open candle: market_close SL=open TP=3R | 3958 | 32.2% | $162,050 | $-30,787 | **5.26** | 4014 | 2497 | 607 | 866 |
| 1h open candle: market_close SL=open TP=3R | 3943 | 37.2% | $176,743 | $-31,718 | **5.57** | 4028 | 2143 | 518 | 1296 |

## Stance

- WORKS — best limit book N/S 3.91; proceed to HP analysis
- HP candidate: `open1h_close_limit_3r`
- **HP mill done:** [`hp/SUMMARY.md`](hp/SUMMARY.md) — strongest lift **strong FH body** (+12.7pp WR); PO-current HP buckets mostly **do not transfer** (Friday does). Diagnostic only — no size-up without nulls.
- Prefer retained **market_close** 1h sleeve (N/S 5.57) for dollars/efficiency; this limit book is the fill-discipline twin.

## Notes

- 30m books use `fh_end=10:00` / `min_fh_bars=6` (signal 09:55).
- 1h books use `fh_end=10:30` / `min_fh_bars=10` (signal 10:25).
- Market-close twins isolate the limit-fill haircut vs the retained 1h sleeve.

Hub: `/home/tester/hsm/potions/live/state/nq_opening_candle_close_limit`
