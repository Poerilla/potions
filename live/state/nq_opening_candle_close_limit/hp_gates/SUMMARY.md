# NQ opening-candle close-limit — top HP broker gates

Engine + PaperBroker + `first_hour_follow` on RTH 5m.
Contract: 1h open candle → **limit @ close** → SL=open → TP=3R.
Realism: slip 1 tick, spread, fee $1.50/unit, NQ $20/pt.

Parent mill: [`../hp/SUMMARY.md`](../hp/SUMMARY.md).

| Book | Trades | WR | Net | Stress | N/S | works |
|---|---:|---:|---:|---:|---:|---|
| 1h limit@close baseline (ungated) | 3906 | 38.5% | $144,018 | $-36,866 | **3.91** | yes |
| HP: first-hour body=strong | 1087 | 51.2% | $116,280 | $-35,184 | **3.30** | yes |
| HP: trade_with_po | 238 | 48.3% | $67,573 | $-23,408 | **2.89** | yes |
| HP: during_counter_with_po | 221 | 48.4% | $54,988 | $-23,952 | **2.30** | yes |
| HP: first-hour range fh_p90 | 603 | 43.6% | $57,650 | $-16,216 | **3.56** | yes |
| HP: hourly RSI > 70 | 394 | 44.4% | $15,064 | $-13,314 | **1.13** | no |

## Stance

- SURVIVE — 4/5 HP gates clear N/S≥2; best `hp_fh_p90` N/S 3.56
- Survivors: `hp_strong_body`, `hp_trade_with_po`, `hp_during_counter_with_po`, `hp_fh_p90`

## Notes

- `hp_strong_body` uses native plugin body gate.
- PO / RSI gates use mill campaign session allowlists (filled-day set).
- `hp_fh_p90` allowlist is from first-hour candles (all p90 sessions).
- Survive = N/S ≥ 2, net > 0, trades ≥ 80 (HP) / 200 (baseline).

Hub: `/home/tester/hsm/potions/live/state/nq_opening_candle_close_limit/hp_gates`
