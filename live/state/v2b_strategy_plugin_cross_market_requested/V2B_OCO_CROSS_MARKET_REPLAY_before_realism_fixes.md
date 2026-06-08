# V2B OCO Then Reverse Cross-Market StrategyPlugin Replay

Each row uses the same intraday `v2b_scaleout` StrategyPlugin path: prior-day MA50 > MA150 on that market's own daily close, 09:30-09:45 OR, OCO breakout stops, 2 contracts, TP1 plus runner to TP2, and same-bar pessimism from the PaperBroker/order ordering.

| Rank | Market | Instrument | Regime Days | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ | NQ | 1164 | 2809 | 1407 | $389,026.50 | $-58,550.00 | $-58,840.00 | 2 | 6.61 | 46.4% | 1.21 |
| 2 | YM | YM | 1182 | 2835 | 1425 | $76,271.25 | $-51,893.25 | $-51,933.25 | 2 | 1.47 | 45.4% | 1.10 |
| 3 | ES | ES | 1195 | 3082 | 1544 | $63,239.50 | $-72,905.00 | $-73,105.00 | 2 | 0.87 | 42.2% | 1.06 |
| 4 | MYM | MYM | 1160 | 2777 | 1396 | $4,092.25 | $-6,801.62 | $-6,805.62 | 2 | 0.60 | 44.7% | 1.05 |

## Read

- This is the live-orderable OCO version, not the long-priority scanner.
- Commission is modeled as `$1.50` per closed unit across markets for parity with the MNQ hardening pass.
- Markets have different available history windows because their local DBN extracts differ.
