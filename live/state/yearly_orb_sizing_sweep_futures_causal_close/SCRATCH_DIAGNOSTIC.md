# Pre-causal NQ L_4_1_1 same-bar close scratches

Source tape: `live/state/yearly_orb_sizing_sweep/states/nq_yorb_sizing_L_4_1_1/fills.csv`
(the tape behind the mixed-MA / wide-OR / ATR-q4 charts).

This is the same lookahead FX/metals hit: range-close / year-change **market**
flatten decided on a completed daily bar, then PaperBroker filled on that
bar's **open**. Plugin now sets `live_after_ts=decision_bar.ts` so the fill
waits for the **next** daily open.

## Book

| | n | WR | net |
|---|---:|---:|---:|
| All campaigns | 68 | 86.8% | $1,416,771 |
| Same-bar `close` (lookahead) | 28 | 92.9% | $130,266 |
| Not same-bar close | 40 | 82.5% | $1,286,505 |

Favorable scratches (same-ts close, `$0 < net < $5k`): **17 / 68 (25%)**.

Dropping those campaigns is **not** the causal test — they still trade, just
at next open (and the sequence can shift). FX/metals AUDJPY flipped from
N/S 24.87 to **negative** under that fill.

## HP buckets (pre-causal)

| Bucket | n | WR | same-bar close | same-bar avg | not same-bar avg |
|---|---:|---:|---:|---:|---:|
| Mixed MA stack | 18 | 100% | 7 (39%) | $8,588 | $53,837 |
| Wide OR | 20 | 95.0% | 8 (40%) | $1,776 | $88,371 |
| ATR q4 | 24 | 95.8% | 11 (46%) | $5,683 | $54,615 |

The $51 / $291 / $531 / $921 mixed-MA "wins" are same-bar-open range-closes.

## Replay

`python -m live.yearly_orb_sizing_sweep --markets nq,es,ym --output-root live/state/yearly_orb_sizing_sweep_futures_causal_close --email`
