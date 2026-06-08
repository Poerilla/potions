# V2B Prior-Opposed ST+PMC Execution Scrutiny

Purpose: harden the cross-market v2b-after-prior-opposite-ST+PMC candidate without
optimizing its rules. The strategy edge stays frozen; this work audits whether
the replay can become a live signal generator and, later, broker-paper system.

## Current Implementation

- Historical timing audit: `potions.live.v2b_prior_opposed_execution_scrutiny`
- Output: `live/state/v2b_prior_opposed_execution_scrutiny/INDEX.md`
- Live feed boundary: `live/live_feed.py`
- Focused tests:
  - `live/tests/test_v2b_prior_opposed_execution_scrutiny.py`
  - `live/tests/test_live_feed.py`

## First Audit Read

| Market | Campaigns | Net | Causal violations | Bar-safe | Same-1m ambiguous | Pre-arm touch | Later level retest | Trigger-only later touch | No later 1m touch |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NQ | 352 | $1,184,585.00 | 0 | 141 | 45 | 166 | 146 | 64 | 1 |
| MNQ | 353 | $113,547.50 | 0 | 142 | 44 | 167 | 147 | 63 | 1 |
| ES | 245 | $348,687.50 | 0 | 95 | 22 | 128 | 113 | 36 | 1 |
| YM | 347 | $320,190.00 | 0 | 187 | 38 | 122 | 114 | 44 | 2 |
| MYM | 333 | $26,053.62 | 0 | 177 | 33 | 123 | 111 | 44 | 1 |

NQ, MNQ, ES, YM, and MYM all pass the fill-book causal check: every gated v2b
entry found a prior opposite ST+PMC fill. None is tick-proven yet. The large
open item is sequencing: every market has a material set of same-1m ambiguous
or pre-arm-touch campaigns. Those are not automatic failures, but they must be
reconstructed from tick/trade data before live funding.

The coarse 1m retest estimate is better than the raw not-bar-safe count
implies. NQ's 211 not-bar-safe campaigns split into 146 later level retests,
64 trigger-side-only touches, and 1 complete 1m miss. MNQ's 211 split into
147 / 63 / 1; ES's 150 split into 113 / 36 / 1; YM's 160 split into
114 / 44 / 2; MYM's 156 split into 111 / 44 / 1. This does not prove 200ms
safety, but it says the bar-level "complete miss" bucket is currently tiny
across the family.

ES/YM/MYM use the same strict delayed-arming replay as NQ/MNQ and add a
full-RTH-session filter after the YM/MYM first pass exposed two early-close /
holiday entries with no normal 15:55 flatten. The cleaned ES/YM/MYM fill books
have zero entry-without-exit campaigns.

## Live Feed Boundary

`PersistedLiveFeedAdapter` is the new provider-neutral boundary for websocket
or streamed bars. It:

- persists raw feed events before strategy processing;
- emits only completed supported bars (`1m`, `5m`, `15m`, `1h`);
- tracks duplicate, out-of-order, missing, incomplete, unsupported, and stale
  bars;
- writes completed bars into the same flat-file store shape used by replay;
- exposes a health object suitable for a stale-feed kill switch.

This is not a broker adapter and does not place orders. It is the first layer
needed for signal-only live shadow mode.

## Promotion Gates

Before broker-paper:

1. Tick-reconstruct all rows in each market's `tick_replay_manifest.csv`.
2. Prove the same-minute and pre-arm-touch campaigns are still valid under
   actual event order, or mark their contribution as untrusted.
3. Run signal-only websocket shadow mode and replay the persisted feed at EOD.
4. Require exact replay/live parity for signal side, size, level, active time,
   expiry, cancel, and flatten behavior.
5. Run broker-paper with one-contract-equivalent sizing only after parity holds.

Do not tune the strategy during this phase. Q4 OR-width sizing reduction remains
a future risk-control candidate, not part of execution scrutiny.
