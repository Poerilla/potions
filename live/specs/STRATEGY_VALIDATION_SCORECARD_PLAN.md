# Strategy Validation Scorecard Implementation Plan

## Summary

Build an allocator-facing validation scorecard for the NQ/MNQ/ES/YM/MYM prior-opposed strategy family and related top systems. The scorecard must show the strong headline metrics while also documenting the uncomfortable diligence questions: multiple testing, peer-score implausibility, random-gate controls, tick-level execution uncertainty, and the gap between hypothetical backtests and live audited performance.

The implementation contract is [`../../data/docs/DSR_PEER_TECHNICAL_SPEC.md`](../../data/docs/DSR_PEER_TECHNICAL_SPEC.md). That document governs the DSR trial ledger, peer comparison fallback protocol, z-score guards, warning codes, and scorecard input validation.

## V1 Implementation Note

The first static implementation is complete at [`../state/strategy_validation_scorecard/SCORECARD_REPORT.md`](../state/strategy_validation_scorecard/SCORECARD_REPORT.md). It includes:

- seeded validation inputs at `data/validation/dsr_trial_ledger.csv` and `data/validation/peer_comparison_table.csv`;
- the generator [`../../scripts/generate_strategy_validation_scorecard.py`](../../scripts/generate_strategy_validation_scorecard.py);
- DSR ledger validation, canonical JSON duplicate checks, N_eff calculation, peer N-count guards, and peer-benchmark suppression;
- NQ daily-return PSR / DSR-zero calculation, bootstrap Sharpe distribution, equity/drawdown charts, and a local strategy rank;
- an equal-count all-day v2b campaign sampling control.

The first pass is useful but not allocator-complete. Remaining blockers are direct sourced peer metrics, true randomized delayed-arming gate replays, tick reconstruction, block-bootstrap/stress scenarios, and live/paper execution parity. The detailed plan for the true random-gate replay layer is [`RANDOMIZED_DELAYED_ARMING_GATE_REPLAY_PLAN.md`](RANDOMIZED_DELAYED_ARMING_GATE_REPLAY_PLAN.md).

## Key Decisions

- Build a Python-generated static scorecard, not a new React/Vite app. Output goes to `live/state/strategy_validation_scorecard/`.
- Canonical scorecard inputs:
  - `data/validation/dsr_trial_ledger.csv`
  - `data/validation/peer_comparison_table.csv`
  - existing replay/equity files referenced by the ledger rows
  - `live/state/institutional_strategy_metrics/metrics.csv`
- Treat `DSR_PEER_TECHNICAL_SPEC.md` as normative, but patch these pre-implementation clarifications first:
  - Duplicate-trial checks must canonicalize `parameters_json` by parsing JSON, sorting keys, and stripping insignificant whitespace before comparison.
  - If `is_oos = TRUE` and `replay_type != OOS_HOLDOUT`, emit a non-blocking `OOS_REPLAY_TYPE_MISMATCH_WARNING`.
  - Promote the formal `span_years` definition to Section 3.3.1 so G-005 references a defined term.
  - Always compute two DSR views when possible: `DSR_ZERO_BENCHMARK` with `SR_0 = 0.0`, and `DSR_PEER_BENCHMARK` with `SR_0 = sourced peer median Sharpe`. If peer median is unavailable because of N-count guards, suppress the peer-benchmark DSR and show the guard reason.
- Peer z-scores are never computed with fewer than 3 sourced peer values, and values with `N=3-4` must carry `LOW_N_WARNING`.
- Investor-facing material must say **hypothetical/backtested, unaudited**. It must not imply a live CTA track record.

## Implementation Changes

### 1. Trial Ledger + Peer Table

- Add a ledger bootstrap script that creates `data/validation/dsr_trial_ledger.csv` from known research families:
  - v2b sizing sweeps
  - ST+PMC timing studies
  - prior-opposed delayed-arming replays
  - cross-market confirmations
  - robustness/filter/event/OR-width studies
  - ungated v2b comparisons
  - random/null controls once generated
- Use the technical spec's `trial_id`, `trial_class`, `parent_trial_id`, `dsr_weight`, `counts_toward_dsr`, and lock rules exactly.
- Start with conservative backfilled rows where exact old trial granularity is not reconstructable. Use `notes` to mark them as historical backfills and err toward higher effective N.
- Add `peer_comparison_table.csv` with the 12 CTA/managed-futures peers only when each row has direct source URLs or file references. Use the source hierarchy in the spec: factsheet/CFTC/ADV, then BarclayHedge/IASG/Morningstar/NilssonHedge, then clearly marked tertiary sources.
- If a peer metric is not sourced, store it as `NA` with source tier 4. Do not invent peer values.

### 2. Scorecard Generator

- Add `scripts/generate_strategy_validation_scorecard.py`.
- The generator validates the ledger and peer table before rendering. Blocking errors stop scorecard generation; warnings render visibly in the output.
- Outputs:
  - `index.html`
  - `scorecard_data.json`
  - `SCORECARD_REPORT.md`
  - `ONE_PAGE_NQ_VALIDATION_PITCH.md`
  - charts for peer comparison, DSR/PSR/Sharpe distribution, random-gate nulls, equity/drawdown, and scenario stress.
- Use pre-rendered matplotlib/PNG charts for reproducibility. Keep the HTML static with no external CDN dependency.
- Use `numpy.random.default_rng(seed)` everywhere for bootstrap and random gates.

### 3. Prior-Opposed Gate Validation

- Add a dedicated gate-validation audit for NQ first, then MNQ/ES/YM/MYM.
- Causality checks:
  - prior-month reference data was known before the ST+PMC gate fired;
  - hourly ST+PMC bar was completed before the v2b order became active;
  - v2b order activation time is after the prior-opposite gate recognition time;
  - no post-fill outcome labels participate in arming.
- Random-gate controls:
  - **Unconstrained random gate:** draw the same number of eligible gate events as the real strategy inside the same market/window.
  - **Stratified random gate:** match real campaign counts by year, side, time-of-day bucket, and opening-range-width quartile.
  - If exact stratum matching without replacement is impossible, sample with replacement inside that stratum and emit `STRATIFIED_WITH_REPLACEMENT_WARNING`. If a stratum has zero eligible rows, merge it into the nearest time-of-day bucket in the same year/side/OR-width group and emit `STRATUM_MERGE_WARNING`.
  - Report real strategy percentile and p-value versus null distributions for net, PF, Sharpe, Sortino, Calmar, max DD, and QQQ downside capture.
- Alternative simple-signal benchmarks are separate from nulls:
  - previous-day return sign;
  - opening-gap sign;
  - calendar/day-of-week quota gate;
  - shuffled ST+PMC side labels.
- Label shuffled ST+PMC side labels and true random gates as **null tests**. Label previous-day return, opening gap, and calendar gates as **simple-signal benchmarks**.

### 4. Stress, Monte Carlo, And Red Flags

- Bootstrap daily return paths and block-bootstrap paths using 1,000 iterations by default and 20,000 in final report mode.
- Compute PSR, `DSR_ZERO_BENCHMARK`, `DSR_PEER_BENCHMARK`, bootstrap Sharpe P5/P50/P95, max DD distribution, and recovery-time distribution.
- Add fat-tail scenarios:
  - actual 2020 COVID window where available;
  - actual 2022 rate-shock window;
  - synthetic 2008, 1987, dot-com, and 5-sigma shocks, all clearly labeled as synthetic.
- Red flags must include:
  - peer z-score implausibility;
  - DSR/peer-benchmark suppression or failure;
  - insufficient peer N-count;
  - stale or incomplete trial ledger;
  - same-minute/pre-arm-touch tick uncertainty;
  - top-winner concentration;
  - no audited live track record;
  - any generated sentence implying live performance.

### 5. Documentation Updates

- Update `mnq/case_studies/STRATEGY_TRACKER.md` with a short "Allocator Validation / Overfit Defense" section linking to the scorecard and summarizing DSR, random-gate nulls, peer-data guards, and execution-scrutiny state.
- Update the NQ one-page pitch so the validation box is visible on page 1 in PDF form. Keep it concise: headline metrics, peer context, null-test result, DSR result, tick-scrutiny status, and next live-validation milestone.
- Update funding-package docs to avoid "PSR proves alpha" language. Use: "PSR is supportive; DSR, random-gate controls, and live execution parity are the required next validation layers."
- Run a disclosure scan that flags:
  - `live record`
  - `track record` without `hypothetical` nearby
  - `audited`
  - `guaranteed`
  - `proves alpha`
  - `institutional-grade` applied to the strategy rather than the validation framework
  - any uncited peer claim
  - investor-facing AUM or dollar-return claims without a backtested/hypothetical qualifier

## Test Plan

- Unit tests:
  - ledger header, schema, enum, lock, parent-cycle, and state-transition validation;
  - JSON canonicalization for duplicate-trial detection;
  - DSR weight policy and `N_eff` calculation;
  - `DSR_ZERO_BENCHMARK` and `DSR_PEER_BENCHMARK` behavior;
  - peer table source-tier validation and per-metric z-score guards;
  - random-gate reproducibility from fixed seeds;
  - stratified random-gate shortfall warnings;
  - causality audit failure on injected lookahead timestamps.
- Integration checks:
  - regenerate scorecard from a clean checkout with one command;
  - scorecard fails closed if ledger or peer table headers are missing;
  - peer z-scores are suppressed when sourced N is below threshold;
  - all generated docs link to source artifacts;
  - markdown link check passes;
  - disclosure scan passes before any PDF/pitch output is considered shareable.

## Acceptance Criteria

- `SCORECARD_REPORT.md` states both what looks strong and what remains fragile.
- The NQ scorecard includes common-window and long-history NQ results as separate exhibits.
- The random-gate null report shows whether the real gate beats matched null gates, not merely whether it has positive performance.
- Peer comparisons show N-count and source-tier warnings instead of overstating precision.
- Strategy Tracker links to the scorecard and no longer relies only on Net/Stress for allocator-facing ranking.
- The one-page pitch can be shown to a sophisticated allocator without hiding the red flags.

## Assumptions

- Existing replay outputs remain the source of truth for strategy performance.
- Peer data collection may be incomplete; missing peer values are preferable to uncited values.
- Historical trial-ledger backfill will be imperfect, so the first implementation should be conservative and transparent.
- Tick reconstruction remains a separate live-readiness gate; this scorecard does not resolve same-minute execution ambiguity by itself.
