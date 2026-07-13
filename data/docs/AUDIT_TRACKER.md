# Causal Validation Audit Tracker

**Last updated:** 2026-06-26  
**Normative design:** [`live/specs/CAUSAL_VALIDATION_MASTER_SPEC.md`](../live/specs/CAUSAL_VALIDATION_MASTER_SPEC.md)  
**Platform implementation truth:** [`live/Platform.md`](../live/Platform.md)  
**Mechanism hypotheses:** [`live/specs/CAUSAL_GRAPH.md`](../live/specs/CAUSAL_GRAPH.md)

Use this as the single run-control checklist before major milestones. Link pass/fail to artifacts; do not mark pass without a file path.

---

## P0 — Active misrepresentations (close first)

| Item | Status | Artifact / notes |
|---|---|---|
| STRATEGY_TRACKER gate-null table | **PASS** | [`mnq/case_studies/STRATEGY_TRACKER.md`](../mnq/case_studies/STRATEGY_TRACKER.md) § Allocator validation — 200-seed stratified NQ/MNQ/YM/MYM |
| IMPLEMENTATION_STATUS gate-null claim | **PASS** | [`IMPLEMENTATION_STATUS.md`](../live/state/strategy_validation_scorecard/IMPLEMENTATION_STATUS.md) — two-family NQ nulls documented |
| Scorecard primary null = gate replay | **PASS** | [`SCORECARD_REPORT.md`](../live/state/strategy_validation_scorecard/SCORECARD_REPORT.md) § Two-Family Permutation Nulls (NQ) |
| Campaign-level PSR/DSR primary | **PASS** | Scorecard § Trial Ledger / DSR (campaign-level primary) |

---

## Time-bucket stratification decision (FD5)

**Decision (2026-06-26):** Completed 200-seed runs use **`stratified_fine_buckets`** (implementation buckets in `v2b_prior_opposed_random_gate_replay._time_bucket`: `09:30-09:45`, `09:45-10:30`, `10:30-12:00`, `12:00-14:00`, `14:00-15:30`). This is **not** the master spec's coarser `09:30-10:30` … `14:00-15:55` set.

**Policy:** Report completed cross-market results as **`stratified_fine_buckets`**. Queue **`stratified_coarse_buckets`** (spec-aligned) as the next 200-seed batch before scaling to 2,000 seeds. Do not label fine-bucket runs as "per spec stratified" in allocator materials.

| Run | Family name | Seeds | Markets | Status |
|---|---|---:|---|---|
| Primary allocator null | `stratified_fine_buckets` | 200 | NQ, MNQ, YM, MYM | **DONE** — [`live/state/v2b_prior_opposed_random_gate_replays/INDEX.md`](../live/state/v2b_prior_opposed_random_gate_replays/INDEX.md) |
| Spec-aligned stratified | `stratified_coarse_buckets` | 0 | — | **DEFERRED** — runner stub in `v2b_prior_opposed_random_gate_replay.py`; queue 200-seed batch before 2,000-seed scale (not started 2026-06-26) |
| Unconstrained event count | `unconstrained_event_count` | 1 smoke (NQ) | NQ | **PENDING** 200-seed |
| Shuffled ST+PMC side (mechanistic) | `shuffled_stpmc_side` | 200 | NQ | **DONE** — null median $370,025, p=0.0050, ledger `TRL-2026-00061` |
| Shuffled ST+PMC side | `shuffled_stpmc_side` | 0 | MNQ, YM, MYM | **QUEUED** — before 2,000-seed scale |
| ES stratified | blocked | — | ES | **BLOCKED** — missing `es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst` |

---

## Part I — Engine correctness

| ID | Check | Status | Evidence |
|---|---|---|---|
| 1.1 | Reference engine / model candles | **FAIL** | Not implemented |
| 1.2 | Broker realism known-answer cases | **PASS** | [`live/broker_realism_validation.py`](../live/broker_realism_validation.py), [`live/tests/test_broker_realism.py`](../live/tests/test_broker_realism.py) |
| 1.3 | Worst-case production fill mode | **PARTIAL** | Gap-through stops, stop-first OCO — implicit, not `DecisionMode` enum |
| 1.4 | Same-1m / pre-arm-touch classified | **PASS** | [`live/v2b_prior_opposed_execution_scrutiny.py`](../live/v2b_prior_opposed_execution_scrutiny.py) |
| 1.5 | `tick_recon_status` in ledger | **FAIL** | Column not in [`data/validation/dsr_trial_ledger.csv`](../data/validation/dsr_trial_ledger.csv) |
| 1.6 | Tick reconstruction executed | **FAIL** | Manifests only; [`live/tick_replay_audit.py`](../live/tick_replay_audit.py) synthetic smoke |

---

## Part II — Sharpe inference

| ID | Check | Status | Evidence |
|---|---|---|---|
| P1 | PSR reported with SR | **PARTIAL** | Daily-return PSR in scorecard only |
| P2 | Campaign-level primary inference | **FAIL** | Phase 1a |
| P3 | HAC / MinBTL / haircut schedule | **FAIL** | Phase 3 |
| P4 | Banned p-value phrase scan | **FAIL** | — |
| P5 | DSR with N_eff | **PASS** | N_eff=53 backfill; peer DSR suppressed |

---

## Part III — False discovery control

| ID | Check | Status | Evidence |
|---|---|---|---|
| FD1 | True engine null replay exists | **PASS** | [`live/v2b_prior_opposed_random_gate_replay.py`](../live/v2b_prior_opposed_random_gate_replay.py) |
| FD2 | 200-seed stratified cross-market | **PASS** | INDEX — all p=0.0050, 0 causality violations |
| FD3 | Null wired to scorecard | **PASS** | [`SCORECARD_REPORT.md`](../live/state/strategy_validation_scorecard/SCORECARD_REPORT.md) |
| FD4 | `counts_toward_permutation_test` in null CSV | **PASS** | `summary_by_seed.csv` column + ledger rows |
| FD5 | Time-bucket policy documented | **PASS** | This file § Time-bucket decision |
| FD6 | `NullReplayGuard` / seed hash | **PASS** | `run_metadata.json` + ledger `run_hash` |
| FD7 | 2,000-seed formal run | **FAIL** | Resolution-only; queue below |

---

## Part V — Causal ordering (CO1 / CO2)

| ID | Check | Status | Evidence |
|---|---|---|---|
| CO1 | Prior-opposed rule audit | **PARTIAL** | `causality_violations` = post-hoc campaign-level check in `validate_prior_opposite_entries()` — not bar-level |
| CO2 | `assert_causal_ordering()` at signal→order | **FAIL** | Not implemented |
| CO2b | `live_after_ts` bar fill guard | **PASS** | [`live/broker.py`](../live/broker.py) |

---

## Strategy-family validation parity

| Family | Broker-like | Execution scrutiny | Primary null | Scorecard section | Causal graph |
|---|---|---|---|---|---|
| v2b prior-opposed | **PASS** | **PASS** | **PASS** (stratified cross-market + shuffled NQ) | **PASS** (two-family exhibit) | **PASS** (see CAUSAL_GRAPH) |
| Yearly ORB scaleout3 | **PASS** | **FAIL** | **FAIL** | **FAIL** | **PARTIAL** |
| ATR supertrend DCA | **PASS** | **FAIL** | **FAIL** | **FAIL** | **PARTIAL** |

---

## Pre-2000-seed gate (summary)

- [x] Phase 0 docs: Platform.md, this tracker, CAUSAL_GRAPH.md
- [x] Phase 1a: scorecard two-family null wiring + campaign PSR
- [x] Ledger CONTROL_NULL rows for stratified gate null (NQ/MNQ/YM/MYM) and shuffled NQ (`TRL-2026-00061`)
- [ ] **Scale queue (resolution-only after mechanistic cross-market):**
  1. Shuffled-label 200-seed MNQ, YM, MYM
  2. `stratified_coarse_buckets` 200-seed NQ
  3. 2,000-seed `stratified_fine_buckets` all five markets (after ES DBN)
- [ ] ES 1m DBN restored or ES excluded with documented reason
- [ ] Block-bootstrap p05 Sharpe > 0 (Phase 4)
- [ ] CPCV PBO < 20% (Phase 4)
