# MNQ periodic DCA (broker-like) — ST bullish gate

Engine + PaperBroker + StrategyPlugin `periodic_dca`.
Buy **1 MNQ** on the **open** of the first daily bar of each month or calendar quarter; hold to end.
Gate: **prior-close** daily ATR Supertrend 14×3.0 must be **bullish** on period-open; else skip that period (no mid-period catch-up).
Realism: slip 1 tick, spread model, fee $1.50/unit (entry-side in audit), MNQ $2/pt.
Bars: `mnq/mnq_daily.csv`.

| Cadence | Buys | Skips | Final qty | Net | Close MTM DD | Intrabar stress DD | N/S |
|---|---:|---:|---:|---:|---:|---:|---:|
| monthly | 52 | 31 | 52 | $882,598 | $-475,614 | $-498,683 | 1.77 |
| quarterly | 17 | 11 | 17 | $281,675 | $-155,498 | $-163,009 | 1.73 |

## vs ungated (prior hub)

| Cadence | Ungated net | ST-gated net | Δ net | Ungated stress | ST stress |
|---|---:|---:|---:|---:|---:|
| monthly | $1,513,696 | $882,598 | $-631,098 | $-826,630 | $-498,683 |
| quarterly | $526,323 | $281,675 | $-244,648 | $-284,118 | $-163,009 |

## Notes

- Quarterly buys fire on first session of Jan / Apr / Jul / Oct.
- Net marks open inventory at last close; drawdowns are peak-to-trough on MTM equity.
- Diagnostic only — not a promotion gate.
