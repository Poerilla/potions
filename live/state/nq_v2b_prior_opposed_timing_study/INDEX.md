# NQ Prior-Opposed Timing Autopsy

Compares the banked hourly left-label ST gate tape to the 1m first-touch gate tape.

**Follow-on (2026-07-15):** NQ promotion candidate is **resting-limit** (arm on opposite ST limit posted), not the strict 1m-touch fill gate. Proxy comparison with MTM stress DD: [`../nq_v2b_prior_opposed_causal_proxies/INDEX.md`](../nq_v2b_prior_opposed_causal_proxies/INDEX.md).

## Sources

- Banked hourly stamp: `live/state/nq_v2b_prior_opposed_stpmc_broker_like`
- 1m first-touch: `live/state/nq_v2b_prior_opposed_stpmc_1m_touch`

## Edge attribution (overlapping campaign days)

- Overlapping campaigns: **350**
- Banked net: **$1,171,675.00**
- 1m-touch net: **$225,825.00**

| Sleeve | N | Banked net | Banked win % | Notes |
|---|---:|---:|---:|---|
| Lookahead victims (`entry_banked <= gate_1m`) | 225 | $918,232.50 | 76.0 | 78.4% of banked net |
| Timing-valid (`entry_banked > gate_1m`) | 125 | $253,442.50 | 56.8 | 1m-touch net on same days $263,967.50 / 56.0% win |
| Same entry minute | 123 | $274,967.50 |  | identical PnL under both stamps |
| Delayed entries | 227 | $896,707.50 |  | 1m-touch $-49,142.50 |

## Honest baselines

1. **Strict causal prior-opposed:** 1m first-touch fill gate (nq_v2b_prior_opposed_stpmc_1m_touch) — full-book net **$225,825.00** on overlapping days.
2. **Timing-valid banked subset:** banked campaigns with `entry > true 1m gate` — **125** campaigns / **$253,442.50** net / **56.8%** win. This is the diagnostic upper bound on “same rule, no lookahead.”

Read: most of the banked headline was early arming inside `[hourly_stamp, first_1m_touch)`, not a durable day filter.

## Files

- `campaign_timing_tape.csv`
- `honest_baselines.csv`
- `lookahead_victims.csv`
- `timing_valid_banked_subset.csv`
