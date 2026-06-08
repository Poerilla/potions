# V2B OCO Then Reverse Cross-Market StrategyPlugin Replay

Each row uses the same intraday `v2b_scaleout` StrategyPlugin path: prior-day MA50 > MA150 on that market's own daily close, 09:30-09:45 OR, OCO breakout stops, 2 contracts, TP1 plus runner to TP2, and same-bar pessimism from the PaperBroker/order ordering.

| Rank | Market | Instrument | Regime Days | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Units | Net / Stress | Win % | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | MES | MES | 517 | 1338 | 670 | $1,466.75 | $-5,507.75 | $-5,517.75 | 2 | 0.27 | 42.8% | 1.04 |

## Read

- This is the live-orderable OCO version, not the long-priority scanner.
- Commission is modeled as `$1.50` per closed unit across markets for parity with the MNQ hardening pass.
- Markets have different available history windows because their local DBN extracts differ.
