# V2B OCO Then Reverse Cross-Market StrategyPlugin Replay

Each row uses the same intraday `v2b_scaleout` StrategyPlugin path: prior-day MA50 > MA150 on that market's own daily close, 09:30-09:45 OR, OCO breakout stops, 2 contracts, TP1 plus runner to TP2, and same-bar pessimism from the PaperBroker/order ordering.

| Rank | Market | Instrument | Regime Days | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | NQ | NQ | 1164 | 2785 | 1394 | $299,477.50 | $-63,538.50 | $-63,828.50 | 2 | 4.69 | 45.9% | 1.16 |
| 2 | MNQ | MNQ | 1164 | 2780 | 1392 | $25,052.50 | $-6,290.00 | $-6,318.00 | 2 | 3.97 | 45.7% | 1.13 |
| 3 | YM | YM | 1182 | 2806 | 1408 | $26,929.75 | $-70,031.50 | $-70,071.50 | 2 | 0.38 | 44.9% | 1.03 |
| 4 | MYM | MYM | 1160 | 2748 | 1379 | $-198.12 | $-8,573.12 | $-8,577.12 | 2 | -0.02 | 44.7% | 1.00 |
| 5 | ES | ES | 1195 | 3061 | 1533 | $-27,929.00 | $-114,720.00 | $-115,020.00 | 2 | -0.24 | 41.7% | 0.97 |
| 6 | MES | MES | 517 | 1322 | 662 | $-2,796.75 | $-7,291.75 | $-7,294.25 | 2 | -0.38 | 42.5% | 0.94 |

## Read

- This is the live-orderable OCO version, not the long-priority scanner.
- Commission is modeled as `$1.50` per closed unit across markets for parity with the MNQ hardening pass.
- Markets have different available history windows because their local DBN extracts differ.
