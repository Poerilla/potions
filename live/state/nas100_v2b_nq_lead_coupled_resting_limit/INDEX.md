# NAS100 v2b Prior-Opposed / Provisional ST+PMC Broker-Like Replay (nq_lead_coupled_resting_limit)

True `Engine + PaperBroker + StrategyPlugin` replay.

| Trades | Units | Net | Closed DD | Intrabar Stress DD | Win % | PF | Net/Stress |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 193 | 579 | $7474.39 | $-3086.08 | $-3113.08 | 61.14 | 1.483 | 2.40 |

## Causality / gate

- Regime sessions replayed: **371**
- Replay start: **2021-03-04**
- Gate mode: **nq_lead_coupled_resting_limit**
- Prior-opposite entries found: **193 / 193**
- Causal violations: **0**
- Direction mix: **79 long / 114 short**

Files:

- `summary.csv`
- `states/nas100_v2b_nq_lead_coupled_S_1_1_1/`
## Coupled NQ stream

- Lead book: `/home/tester/hsm/potions/live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit` (hour-complete resting-limit, not the left-label fill-stamp book)
- A campaign is ingested only after its NQ entry bar is complete (`available_at = fill bar + 1m`).
- The NAS decision bar must be **strictly after** that timestamp.
- TP1 / stop / EOD are separate milestone events. They are not stored on the campaign at entry time.
- Mapped OR uses the prior completed NAS close at reveal, not the NQ entry minute.
- Sync ceiling after bar-complete: **60s**. Early window forced to **0s**.
- Entered campaigns: **193**
- Skipped campaigns: **188**
- Lookahead violations (entry on or before NQ bar complete): **0**

Files: `summary.csv`, `sync_audit.csv`, `coupled_causality.csv`, `states/nas100_v2b_nq_lead_coupled_S_1_1_1/`

## Why the skips miss NQ winners

Lookahead diagnostic, not a second causal book: `winner_miss_lookahead/SUMMARY.md`.

The 116 skipped NQ winners are not a later NAS breakout and not a different opening range. On 88 of them the first NAS close through the mapped range is the NQ fill minute or the completion minute. The only legal bar is the next one, and its close is back inside by a median 6.5 points while the wick still tags the level (99%). Mapped vs NAS 15m range width ratio is 1.01. A lookahead entry on the later close would have won 106 of those 116. Research only.
