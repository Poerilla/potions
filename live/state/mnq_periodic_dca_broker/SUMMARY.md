# MNQ periodic DCA (broker-like)

Engine + PaperBroker + StrategyPlugin `periodic_dca`.
Buy **1 MNQ** on the **open** of the first daily bar of each month or calendar quarter; hold to end.
Realism: slip 1 tick, spread model, fee $1.50/unit (entry-side in audit), MNQ $2/pt.
Bars: `mnq/mnq_daily.csv`.

| Cadence | Buys | Final qty | Net | Close MTM DD | Intrabar stress DD | N/S |
|---|---:|---:|---:|---:|---:|---:|
| monthly | 83 | 83 | $1,513,696 | $-788,002 | $-826,630 | 1.83 |
| quarterly | 28 | 28 | $526,323 | $-270,705 | $-284,118 | 1.85 |

## Notes

- Quarterly buys fire on first session of Jan / Apr / Jul / Oct.
- Net marks open inventory at last close; drawdowns are peak-to-trough on MTM equity.
- Diagnostic only — not a promotion gate.
