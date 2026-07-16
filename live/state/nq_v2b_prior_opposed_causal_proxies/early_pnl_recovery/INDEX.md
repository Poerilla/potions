# Early PnL Recovery (after removing left-label lookahead)

## Question

The left-label resting-limit book had **104 strict-early** campaigns
(**$569,015**, 43% of net). Post-hoc dropping them left **$752,730**. How do we
keep that PnL without lookahead?

## Answer

**Wait for ST hour-complete, then arm.** Do not drop those days.

| Book | Trades | Net | Stress DD | Net/Stress |
|---|---:|---:|---:|---:|
| Left-label (lookahead diagnostic) | 434 | $1,321,745 | -$68,610 | 19.26 |
| **Causal hour-complete (new baseline)** | **432** | **$1,330,920** | **-$68,610** | **19.40** |
| Provisional + confirm resting ST in 60m | 1,279 | $878,900 | -$97,692 | 9.00 |

### Delayed-arm recovery of the early sleeve

- Old strict-early sessions: **104** / **$569,015**
- Still traded under causal gate: **103 / 104**
- New net on those sessions: **$573,183** (≈ full recovery)
- Lost session: **1** (old early net **-$6,833** — a loser)
- Median **arm** delay: **60 minutes** (hour-complete)
- Median **entry** delay: **0 minutes** — breakout often had not fired yet, so fill time unchanged

Post-hoc “drop early” understated the honest book. The early edge was mostly
**same-day / same-breakout** economics, not a free option on unfinished ST hours.

### What does *not* help

Ungated provisional + invalidate-if-no-opposite-ST-in-60m (**$878,900 / 9.00**)
is weaker than the causal resting-limit gate. Extra PnL is not recovered by
trading more days; it is recovered by **delaying the gate to hour-complete**.

## Files

- `summary.csv`
- `recovered_early_sessions.csv`
- `missed_early_sessions.csv`
