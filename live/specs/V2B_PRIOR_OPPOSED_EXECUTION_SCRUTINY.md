# V2B Prior-Opposed ST+PMC Execution Scrutiny

Purpose: harden the cross-market v2b-after-prior-opposite-ST+PMC candidate without
optimizing its rules. The strategy edge stays frozen; this work audits whether
the replay can become a live signal generator and, later, broker-paper system.

**2026-07-16 gate-semantics note:** the scrutiny numbers below were computed on
the **legacy hourly left-label ST fill stamp** books. For NQ, that tape is now
**diagnostic / timestamp-inflated**. The NQ promotion candidate is
**resting-limit hour-complete**
(`live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/`) — arm when the
opposite ST entry limit is knowably posted (`available_at = live_after + 1h`),
not when it fills. MTM stress DD reference points: hour-complete resting-limit
**-$68,610** (net **$1,330,920**); strict 1m-touch fill **-$153,087**;
provisional invalidate 60m **-$131,315**. Re-run execution scrutiny on
hour-complete books before live funding. Timing autopsy:
`live/state/nq_v2b_prior_opposed_timing_study/INDEX.md`.

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

## NQ Full-History Rerun Status

The current promotion / execution-scrutiny baseline remains the **2021-03-04
through 2026-03-06** window so it stays aligned with the cross-market common
window. The restored long-history NQ raw file was separately replayed as a
standalone broker-like run using `--start 2010-06-06` and `--dbn-path
nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst`.

Output:
`live/state/nq_v2b_prior_opposed_stpmc_full_history_raw/INDEX.md`. The
supporting NQ daily regime file and NQ hourly ST+PMC gate fills currently run
through **2026-03-08 / 2026-03-05**, so the effective validated window is
2010-06-06 through early March 2026 even though the raw DBN extends to
2026-06-16.

Full-history broker-like result: **877 campaigns / 4,385 units**,
**$1,713,277.50 net**, **-$53,172 closed DD**, **-$53,847 intrabar stress DD**,
**64.77% win**, **2.427 PF**, **31.82 Net/Stress**, with **877 / 877**
prior-opposite entries and **0 causal violations**. Compared with the banked
2021-start row (**352 campaigns / $1,184,585 / -$53,847 stress / 22.00**), the
added pre-2021 section contributes **525 campaigns** and **$528,692.50 net**
without deepening the full-window closed or intrabar stress drawdown. The
earlier history is positive but less efficient than the post-2021 segment:
2013 and 2017 are the weakest pre-2021 years, while 2020 is the strongest.

A non-broker-like CSV diagnostic was run from the legacy full-history NQ v2b
scaleout tape and the existing full-history NQ hourly ST+PMC fills. It is only a
directional smell test, not a replacement for the delayed-arming
`Engine + PaperBroker` replay. Output:
`live/state/nq_v2b_prior_opposed_stpmc_full_history_csv_diagnostic/INDEX.md`.
That diagnostic finds **498 matching v2b rows from 2011-01-17 through
2026-03-02**, **$320,096 net**, **-$16,952 closed DD**, **61.7% row win**,
**2.00 PF**, and **18.88 Net/closed-DD**. The same-start 2021-03-04 slice is
**191 rows / $208,162 / -$16,952 / 12.28**, which should not be compared
directly to the 5-unit broker-like replay.

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
