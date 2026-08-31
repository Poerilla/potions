# Futures yearly ORB — pre-causal vs causal next-open close

Same pass as FX/metals (`yearly_orb_sizing_sweep_fx_metals_causal_close`):
range-close / year-change flatten uses `live_after_ts=decision_bar.ts`, so
PaperBroker fills the **next daily open**, not the completed bar's open.

The NQ mixed-MA / wide-OR / ATR-q4 charts were drawn on the **pre-causal**
`L_4_1_1` tape. Those tiny green scratches are same-bar-open range-closes.

## Headline books

| Book | Tape | n | WR | Net | Stress | N/S |
|---|---|---:|---:|---:|---:|---:|
| NQ `L_4_1_1` | pre-causal | 68 | **86.8%** | $1,417,383 | -$128,766 | **11.01** |
| NQ `L_4_1_1` | causal | 68 | **29.4%** | $764,503 | -$159,309 | **4.80** |
| ES `L_4_2_1` | pre-causal | 73 | 76.7% | $657,146 | -$66,346 | **9.90** |
| ES `L_4_2_1` | causal | 73 | **20.5%** | $68,396 | -$170,343 | **0.40** |
| YM `L_4_1_1` | pre-causal | 81 | 90.1% | $515,736 | -$67,525 | **7.64** |
| YM `L_4_1_1` | causal | 81 | **22.2%** | $157,766 | -$88,868 | **1.78** |
| NQ `O_4_2_1_rc20` | pre-causal | 46 | 54.3% | $1,426,707 | -$211,815 | 6.74 |
| NQ `O_4_2_1_rc20` | causal | 46 | 47.8% | $1,258,237 | -$216,356 | **5.82** |

OCO + 20% range-close barely moved: fewer same-bar-open scratches (entry is
not a limit at the boundary that also closes back inside). Default
limit-retest + full-range close is where the WR was fake.

## NQ HP buckets (`L_4_1_1`)

Pre-causal: 28/68 campaigns (41%) were same-bar `close` fills; 17/68 were
favorable scratches (`$0 < net < $5k`). Causal tape: **0** same-bar closes
(min flatten lag = 1 session).

| Bucket | Pre n / WR / avg | Causal n / WR / avg | Causal wins/losses |
|---|---|---|---|
| Mixed MA stack | 18 / **100%** / $36,240 | 18 / **33.3%** / $16,859 | 6 / 12 |
| Wide OR | 20 / **95.0%** / $53,733 | 20 / **40.0%** / $35,492 | 8 / 12 |
| ATR q4 | 24 / **95.8%** / $32,188 | 24 / **41.7%** / $19,023 | 10 / 14 |

Buckets still lift vs the new 29.4% book WR, but they are ordinary
trend-following sleeves — not 95–100% WR. Mixed-MA median causal net is
**-$3,714**. The old $51 / $291 / $531 mixed-MA "wins" are now losses
(-$2.2k / -$3.2k / similar).

## FX/metals analog

| Market | Pre N/S | Causal N/S | Read |
|---|---:|---:|---|
| AUDJPY `4/1/1` | 24.87 | -0.51 | died |
| XAUUSD `4/2/1` | 15.32 | 1.86 | survived weak |
| XAGUSD `5/2/1` | 8.58 | 1.33 | survived weak |
| NQ `4/1/1` | 11.01 | **4.80** | survives; WR myth gone |
| ES `4/2/1` | 9.90 | **0.40** | died (AUDJPY-class) |
| YM `4/1/1` | 7.64 | **1.78** | weak survive |

## Stance

- **Do not promote** from pre-causal futures yearly-ORB N/S (11.01 / 9.90 / 7.64)
  or from the 86.8% / 76.7% / 90.1% WR recount.
- Causal NQ `L_4_1_1` N/S 4.80 is still a book; treat it as a 29% WR trend
  system. Causal NQ `O_4_2_1_rc20` N/S **5.82** is the most stable cell.
- ES limit-retest ladders are **not** yearly-ORB quality under causal close.
- HP size-up on mixed-MA / wide-OR / ATR-q4 remains **not validated** — the
  100%/95% bucket WRs were scratch-inflated.

Hub: `live/state/yearly_orb_sizing_sweep_futures_causal_close/`
Driver: `python -m live.yearly_orb_sizing_sweep --markets nq,es,ym --output-root live/state/yearly_orb_sizing_sweep_futures_causal_close --email`
