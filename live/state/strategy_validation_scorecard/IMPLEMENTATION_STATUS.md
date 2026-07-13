# Strategy Validation Implementation Status

Generated: 2026-06-26 (manual sync)

**Gate null replay: implemented.** Two-family NQ permutation nulls (stratified cross-market + shuffled-label NQ) are complete and wired to the scorecard, ledger, and STRATEGY_TRACKER.

## Missing Data

- Direct, source-cited peer metrics for the 12 peer managers. Without those, peer z-scores and peer-benchmark DSR stay suppressed.
- Shuffled-label 200-seed on MNQ, YM, MYM (NQ complete).
- Spec-aligned `stratified_coarse_buckets` 200-seed NQ run.
- ES stratified null — blocked until `es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst` is restored.
- Tick-level order sequencing for same-minute and pre-arm-touch prior-opposed campaigns.
- Block-bootstrap and synthetic macro stress calibration for final allocator mode.

## Implemented As Is

- Validation input contracts in `data/validation/dsr_trial_ledger.csv` and `data/validation/peer_comparison_table.csv`.
- DSR ledger validation, canonical JSON duplicate handling, N_eff calculation, OOS warning hook, and peer N-count guard behavior.
- **Two-family NQ permutation nulls (200 seeds each):**
  - Stratified `stratified_fine_buckets` — NQ/MNQ/YM/MYM, p = 0.0050, 0 causality violations.
  - Shuffled `shuffled_stpmc_side` — NQ only, p = 0.0050, null median $370,025, 0 causality violations.
- Ledger rows TRL-2026-00057–00060 (stratified) and TRL-2026-00061 (shuffled NQ) with `counts_toward_permutation_test=TRUE`.
- Scorecard two-family exhibit, edge decomposition table, stratified + shuffled NQ charts.
- Campaign-level PSR/DSR primary in scorecard; sampling control demoted to secondary.
- Governance docs: [`../../data/docs/AUDIT_TRACKER.md`](../../data/docs/AUDIT_TRACKER.md), [`../specs/CAUSAL_GRAPH.md`](../specs/CAUSAL_GRAPH.md), [`../Platform.md`](../Platform.md).

## Left Over (scale queue — resolution-only after mechanistic cross-market)

1. Shuffled-label 200-seed MNQ, YM, MYM.
2. `stratified_coarse_buckets` 200-seed NQ.
3. 2,000-seed `stratified_fine_buckets` on all five markets (after ES DBN).
4. Populate peer table from direct sources; tick reconstruction; block-bootstrap final-report mode.
