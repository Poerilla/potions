# MNQ v2b Scaleout Ordering Audit

Source: full MNQ 1-minute DBN `raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst`.
Regime: prior-day daily MA50 > MA150, shifted one day. Sizing: 2 MNQ, TP1/runner/TP2.

| Scenario | Days | Legs | Net | Closed DD | MTM DD | Net/MTM | Win% | PF | Median |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| long_priority_scanner | 961 | 1302 | $83,245 | $2,730 | $3,130 | 26.60 | 59.7% | 1.60 | $101 |
| oco_bracket_reverse | 961 | 1441 | $35,210 | $5,190 | $5,482 | 6.42 | 54.8% | 1.19 | $73 |
| long_then_short_strict | 737 | 1078 | $19,600 | $6,330 | $6,672 | 2.94 | 53.3% | 1.15 | $54 |

## Read

- `long_priority_scanner` reproduces the current tracker row, but it is a scanner convention rather than a normal live OCO order book.
- `oco_bracket_reverse` is closest to the Pine/TradingView harness: both sides can arm after the opening range, first fill owns the campaign, then only the opposite side can re-arm after exit.
- `long_then_short_strict` is the literal executable version of "try Long first, then Short after Long exits"; it intentionally skips Short-only days where Long never filled.

If the strategy is routed through TradingView/Tradovate using the current Pine, compare live paper fills to `oco_bracket_reverse`, not to the long-priority scanner.
