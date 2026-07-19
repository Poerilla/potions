# f30 week — winner / loser profile

Honest (break-fixed) f30-week research trades. n=620 · wins=96 · losses=524 · net=$-4,073.

## Entry weekday

| Weekday | n | Wins | Losses | WR | % of all wins | % of all losses | Net $ |
|---|---:|---:|---:|---:|---:|---:|---:|
| Mon | 234 | 4 | 230 | 1.7% | 4.2% | 43.9% | $-5,027 |
| Tue | 106 | 17 | 89 | 16.0% | 17.7% | 17.0% | $-2,645 |
| Wed | 90 | 16 | 74 | 17.8% | 16.7% | 14.1% | $1,045 |
| Thu | 70 | 18 | 52 | 25.7% | 18.8% | 9.9% | $3,159 |
| Fri | 69 | 24 | 45 | 34.8% | 25.0% | 8.6% | $391 |

**Monday is the dumpster:** 1.7% WR, **44% of all losses**, −$5.0k alone.  
Tue–Fri net ≈ **+$0.95k**; Wed–Fri ≈ **+$3.6k**. Winners concentrate later in the week (Fri = 25% of wins).

## Do winners share prior-week structure?

| Feature | Among winners | Among losers |
|---|---:|---:|
| Prior week **new high** (vs prior 4w) | 29.2% | 27.7% |
| Prior week **new low** (vs prior 4w) | 30.2% | 28.2% |
| Prior week **inline** with bias | 51.0% | 55.7% |
| Prior week **opposed** to bias | 49.0% | 44.1% |

### Conditional win rates

| Slice | n | WR | Net $ |
|---|---:|---:|---:|
| Prior week new high (vs prior 4w) = yes | 173 | 16.2% | $-805 |
| Prior week new high (vs prior 4w) = no | 447 | 15.2% | $-3,268 |
| Prior week new low (vs prior 4w) = yes | 177 | 16.4% | $-2,227 |
| Prior week new low (vs prior 4w) = no | 443 | 15.1% | $-1,846 |
| Prior week dir INLINE with bias = yes | 341 | 14.4% | $-1,797 |
| Prior week dir INLINE with bias = no | 279 | 16.8% | $-2,276 |
| Prior week dir OPPOSED to bias = yes | 278 | 16.9% | $-2,227 |
| Prior week dir OPPOSED to bias = no | 342 | 14.3% | $-1,846 |

## Yearly daily charts

See [`charts_yearly_daily/INDEX.md`](charts_yearly_daily/INDEX.md) (5 years).

CSV: `weekday_profile.csv`, `prior_week_features.csv`, `trades_enriched.csv`

## No Mon/Tue entries (re-sim)

Blocked entry weekdays; same rules otherwise (break-fixed wick SL).

| Variant | Net | Closed DD | Net/DD | Camps | WR | Entries |
|---|---:|---:|---:|---:|---:|---:|
| All days (baseline) | $-4,073 | $-9,637 | -0.42 | 620 | 15.5% | 675 |
| No Mon/Tue (Sun still allowed) | $-1,358 | $-8,848 | -0.15 | 584 | 24.5% | 635 |
| **Wed–Fri only** | $-661 | $-8,741 | -0.08 | 556 | 22.7% | 608 |

Note: dropping Mon/Tue from the *existing* baseline trade list (no re-fill) was ~+$3.6k — but a true re-sim reuses monthly capacity on later days, which eats that edge. Sunday FX sessions also absorbed 84 entries when only Mon/Tue were blocked.

Trades: `trades_f30_week_no_mon_tue.csv`, `trades_f30_week_wed_fri_only.csv`

