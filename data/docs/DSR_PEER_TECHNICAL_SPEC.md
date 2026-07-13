# DSR Trial Ledger & Peer Comparison Fallback Protocol
## Technical Specification

| Field | Value |
|---|---|
| **Document** | DSR Trial Ledger + Peer Comparison Fallback Protocol Technical Specification |
| **Version** | v1.0 |
| **Date** | 2026-06-26 |
| **Status** | DRAFT |
| **Reference** | Bailey & López de Prado (2014), SSRN 2460551 |

---

## Table of Contents

1. [Introduction & Motivation](#1-introduction--motivation)
2. [System 1: DSR Trial Ledger](#2-system-1-dsr-trial-ledger)
   - [2.1 CSV Schema — dsr_trial_ledger.csv](#21-csv-schema)
   - [2.2 DSR Calculation Rules](#22-dsr-calculation-rules)
   - [2.3 DSR Input Parameters](#23-dsr-input-parameters-beyond-n)
3. [System 2: Peer Comparison Fallback Protocol](#3-system-2-peer-comparison-fallback-protocol)
   - [3.1 Source Hierarchy](#31-source-hierarchy)
   - [3.2 Per-Metric Fallback Map](#32-per-metric-fallback-map)
   - [3.3 N-Count Guard Logic](#33-n-count-guard-logic)
   - [3.4 Peer Table Schema](#34-peer-table-schema)
   - [3.5 Scorecard Integration Rules](#35-scorecard-integration-rules)
4. [Worked Examples](#4-worked-examples)
5. [Appendix A: Enum Master List](#5-appendix-a-enum-master-list)
6. [Appendix B: Error & Warning Code Reference](#6-appendix-b-error--warning-code-reference)
7. [Appendix C: Revision History](#7-appendix-c-revision-history)

---

## 1. Introduction & Motivation

> **Reviewer Notes (non-technical summary):**
> Every time an analyst tests a new rule, parameter, or market variant during strategy research, it constitutes a "trial." The Deflated Sharpe Ratio (DSR) adjusts the reported Sharpe Ratio downward to account for the fact that the best result from many trials is statistically lucky. Without a complete, auditable count of all trials, the DSR cannot be computed correctly — and any reported Sharpe could be inflated by hidden data-snooping bias. This document defines (1) how to record every trial in a machine-readable ledger, and (2) how to compare the resulting strategy against peers using a rigorous, source-validated fallback protocol.

### 1.1 Background

The Deflated Sharpe Ratio (DSR), introduced by Bailey & López de Prado (2014, SSRN 2460551), answers a fundamental question in quantitative strategy evaluation: given that a researcher ran N strategies or parameter sweeps and selected the best one, what is the probability that the observed Sharpe Ratio (SR*) exceeds a benchmark SR_0 purely by chance?

The DSR is extremely sensitive to N, the total number of independent trials conducted during research. Omitting trials — whether because they produced poor results, were deemed "exploratory," or were simply not recorded — systematically inflates the DSR. A single missed trial batch can render the entire DSR calculation meaningless.

This specification addresses that problem by mandating a comprehensive trial ledger that:

1. Captures every parameter sweep, market variant, model iteration, and sub-exploration.
2. Provides a principled, auditable method for computing an **effective N** that accounts for the partial independence of related trials.
3. Locks historical entries once they appear in investor-facing materials, preserving the integrity of the audit trail.

### 1.2 Scope

This specification covers:

- The schema and governance rules for `dsr_trial_ledger.csv` (Section 2).
- The source-waterfall protocol for populating `peer_comparison_table.csv` (Section 3).
- The integration rules that connect both files to a downstream scorecard generator (Section 3.5).

This specification does **not** cover:

- Implementation of the scorecard generator itself (code-level).
- Portfolio-level aggregation across multiple strategies.
- Live trading performance attribution.

### 1.3 Normative Language

The key words "MUST," "MUST NOT," "REQUIRED," "SHALL," "SHALL NOT," "SHOULD," "SHOULD NOT," "RECOMMENDED," "MAY," and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

---

## 2. System 1: DSR Trial Ledger

> **Reviewer Notes (non-technical summary):**
> This section defines the exact format and rules for the trial ledger — a running log of every strategy test conducted. Think of it as a lab notebook for quantitative research, but machine-readable and subject to strict governance. The ledger is the sole authoritative source of N for all DSR calculations. Completeness is not optional: any trial that was run but not logged will cause the DSR to be understated (the N will be too low, making the DSR appear falsely high).

---

### 2.1 CSV Schema

#### 2.1.1 File-Level Requirements

- **Encoding:** UTF-8, no BOM.
- **Line endings:** LF (`\n`). CRLF is rejected by the validator.
- **Header comment:** The first line of the file MUST be a comment of the form:

  ```
  # generated_at=<ISO-8601 datetime>; schema_version=1.0
  ```

  Example: `# generated_at=2026-06-26T09:00:00Z; schema_version=1.0`

- **Column header row:** The second line of the file is the CSV header row.
- **Quoting:** All string fields that may contain commas or newlines MUST be double-quoted. Boolean fields MUST be stored as the literals `TRUE` or `FALSE` (case-sensitive). NULL values MUST be stored as an empty string (two consecutive delimiters with no whitespace).
- **Delimiter:** Comma (`,`).
- **Date format:** All date-only fields use `YYYY-MM-DD`. All datetime fields use `YYYY-MM-DDTHH:MM:SSZ` (UTC).

#### 2.1.2 Identity Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `trial_id` | STRING | REQUIRED | Format `TRL-YYYY-NNNNN`. `YYYY` = year of first log entry; `NNNNN` = zero-padded integer, auto-incremented within the year, never reused or reassigned. Once assigned, immutable. | Globally unique identifier for this trial. Example: `TRL-2026-00001`. |
| `entry_date` | DATE | REQUIRED | ISO 8601 (`YYYY-MM-DD`). Represents the date the row was first written to the ledger, not the date the trial was run. If the trial was run before being logged, the gap MUST be noted in `notes`. | Date the trial was logged. |
| `analyst` | STRING | REQUIRED | Maximum 32 characters. MUST NOT be empty. Initials, username, or system identifier. | Person or automated process that initiated and logged the trial. |
| `trial_class` | ENUM | REQUIRED | One of: `SIZING_SWEEP`, `TIMING_STUDY`, `FILTER_EXPLORATION`, `GATE_VARIANT`, `CROSS_MARKET`, `STRUCTURAL_CHANGE`, `CONTROL_NULL`, `REJECTED_CONCEPT`. See Appendix A for definitions. | High-level classification of what type of hypothesis or search this trial represents. |
| `trial_subclass` | STRING | REQUIRED | Free text, maximum 128 characters. MUST be descriptive enough to identify the trial without reference to other fields. | Human-readable label for the specific variant. Examples: `v2b_target_multiplier`, `ST+PMC_lookback_days`, `OR_width_quartile_cutoff`. |
| `parent_trial_id` | STRING | OPTIONAL | If non-NULL, MUST reference a `trial_id` that already exists in the ledger. Self-reference is forbidden. Circular references are forbidden (validator must check). | References the parent trial if this trial is a sub-sweep or variant. NULL for top-level independent hypotheses. |
| `is_independent` | BOOLEAN | REQUIRED | `TRUE` or `FALSE`. See Decision Rules below. | `FALSE` if this trial shares both (a) the same core gate logic AND (b) the same training window as its parent. `TRUE` if it introduces a genuinely new hypothesis, changes the gate logic, or uses a different training window. |

**is_independent Decision Rules (first matching rule wins):**

A trial MUST be set `is_independent = TRUE` if ANY of the following apply:

1. It has no `parent_trial_id` (it is a root-level hypothesis).
2. It introduces new gate logic not present in the parent (e.g., adding a momentum filter that did not exist).
3. It uses a training window whose start or end date differs from the parent's training window by more than 30 calendar days.
4. It belongs to `trial_class = STRUCTURAL_CHANGE`.

A trial MUST be set `is_independent = FALSE` if ALL of the following apply:

1. It has a `parent_trial_id`.
2. It changes only numeric parameter values within an existing gate structure.
3. Its training window is identical to the parent's (within 30 calendar days).

> **Note:** `is_independent` informs DSR weighting but does NOT override it. The `dsr_weight` field is the operative value for N_eff computation (see Section 2.2).

---

#### 2.1.3 Scope Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `market` | ENUM | REQUIRED | One of: `NQ`, `MNQ`, `ES`, `MES`, `YM`, `MYM`, `RTY`, `MBT`, `GC`, `CL`, `ZN`, `6E`, `MULTI`, `OTHER`. If `OTHER`, document in `notes`. | Primary market/instrument traded in this trial. `MULTI` for strategies simultaneously trading two or more instruments. |
| `replay_window_start` | DATE | REQUIRED | ISO date. MUST be ≤ `replay_window_end`. | Start date (inclusive) of the historical replay or live window used to generate results. |
| `replay_window_end` | DATE | REQUIRED | ISO date. MUST be ≥ `replay_window_start`. | End date (inclusive) of the historical replay or live window. |
| `replay_type` | ENUM | REQUIRED | One of: `COMMON_WINDOW`, `FULL_HISTORY`, `OOS_HOLDOUT`, `LIVE`. See Appendix A. | Describes the relationship between this replay window and the broader data history. |
| `is_oos` | BOOLEAN | REQUIRED | `TRUE` only if the replay window was designated as out-of-sample BEFORE the trial was designed. If in any doubt, use `FALSE`. Setting `TRUE` on a window that was inspected during design is a data integrity violation. | Indicates whether this window was strictly held out before trial design. |
| `training_window_start` | DATE | OPTIONAL | ISO date or NULL. MUST be ≤ `training_window_end` when non-NULL. | Start date of the in-sample training window. NULL if no training/test split was performed. |
| `training_window_end` | DATE | OPTIONAL | ISO date or NULL. | End date of the in-sample training window. NULL if no training/test split was performed. |

---

#### 2.1.4 Parameter Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `parameters_json` | JSON STRING | REQUIRED | Must be valid JSON. Must be a flat key-value object (no nested objects) for machine parseability. Keys are parameter names (snake_case strings); values are numbers, booleans, or strings. Example: `{"v2b_target_mult": 1.5, "st_lookback_days": 20}` | Complete set of parameter values varied in this trial relative to the fixed baseline. |
| `fixed_parameters_ref` | STRING | REQUIRED | File path relative to project root (e.g., `configs/baseline_v3.yaml`) or SHA-256 hash prefixed with `sha256:`. This reference MUST resolve to a file that fully specifies all parameters not listed in `parameters_json`. | Pointer to the configuration file defining all parameters held constant for this trial. Makes the trial fully reproducible. |
| `num_params_varied` | INTEGER | REQUIRED | Non-negative integer. MUST equal the count of keys in `parameters_json`. Validator enforces consistency. | Number of parameters changed from the fixed baseline. Used as input to `dsr_weight` assignment. |

---

#### 2.1.5 Result Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `sharpe_ratio` | FLOAT | CONDITIONAL | NULL if `status` ∈ {`LOGGED`, `RUNNING`, `FAILED`}. MUST be non-NULL if `status = COMPLETE` and `counts_toward_dsr = TRUE`. Annualized. | Annualized Sharpe Ratio of this trial's equity curve. Computed from the full replay window return series. |
| `sortino_ratio` | FLOAT | OPTIONAL | NULL allowed. Annualized. Uses 0% MAR unless documented in `notes`. | Annualized Sortino Ratio. |
| `cagr_pct` | FLOAT | OPTIONAL | NULL allowed. Expressed as a percentage (e.g., 18.5 means 18.5%). | Compound Annual Growth Rate over the replay window. |
| `calmar_ratio` | FLOAT | OPTIONAL | NULL allowed. Computed as `cagr_pct / |max_drawdown_pct|`. If computed manually, document in `notes`. | Calmar Ratio. |
| `max_drawdown_pct` | FLOAT | OPTIONAL | NULL allowed. Stored as a **negative** number by convention (e.g., -23.4 means 23.4% drawdown). Validator rejects positive values for this field. | Maximum peak-to-trough drawdown as a percentage of peak equity. |
| `trade_count` | INTEGER | OPTIONAL | NULL allowed. Non-negative integer. Total completed round-trip trades in the replay window. | Total completed trades. Used as T in DSR computation when daily return series is unavailable. |
| `pf` | FLOAT | OPTIONAL | NULL allowed. MUST be ≥ 0. Gross profit divided by gross loss. | Profit factor. |
| `net_pnl` | FLOAT | OPTIONAL | NULL allowed. Denominated in USD. May be negative. | Net profit and loss for the replay window, in USD. |
| `qqq_correlation` | FLOAT | OPTIONAL | NULL allowed. Range [-1.0, 1.0]. Pearson correlation of daily strategy returns vs. QQQ daily returns over the same replay window. | Correlation of strategy returns with QQQ (Nasdaq 100 ETF proxy). |
| `qqq_downside_capture` | FLOAT | OPTIONAL | NULL allowed. Expressed as a decimal ratio (e.g., 0.30 means 30% downside capture). Computed only over days when QQQ was negative. | Downside capture ratio vs. QQQ. |

---

#### 2.1.6 DSR Accounting Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `counts_toward_dsr` | BOOLEAN | REQUIRED | `TRUE` or `FALSE`. Default is `TRUE` for all trials except `REJECTED_CONCEPT` (never run) and `CONTROL_NULL`. See Section 2.2.1 for the complete exclusion logic. | Whether this trial contributes to the effective trial count N used in DSR calculations. |
| `dsr_weight` | FLOAT | REQUIRED | Range [0.0, 1.0]. MUST be 0.0 when `counts_toward_dsr = FALSE`. MUST be > 0.0 when `counts_toward_dsr = TRUE`. Assigned per Section 2.2.2. | Fractional weight representing the degree of independence of this trial. Summed to produce N_eff. |
| `dsr_exclusion_reason` | STRING | CONDITIONAL | NULL when `counts_toward_dsr = TRUE`. REQUIRED when `counts_toward_dsr = FALSE`. MUST be one of: `REJECTED_BEFORE_RUN`, `CONTROL_NULL`, `DUPLICATE_RUN`, `AUDIT_EXCLUSION`. | Documents why this trial does not count toward N. A `counts_toward_dsr = FALSE` row with NULL exclusion reason MUST fail validation. |

---

#### 2.1.7 Status and Audit Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `status` | ENUM | REQUIRED | One of: `LOGGED`, `RUNNING`, `COMPLETE`, `FAILED`, `SUPERSEDED`. See Appendix A for state transition rules. | Current lifecycle state of the trial. |
| `superseded_by` | STRING | CONDITIONAL | NULL unless `status = SUPERSEDED`. When non-NULL, MUST reference a valid `trial_id` in the same ledger. The referenced trial MUST NOT itself have `status = SUPERSEDED`. | When this row has been corrected, points to the replacement trial_id. No chains of supersession permitted. |
| `run_hash` | STRING | OPTIONAL | SHA-256 hex string (64 lowercase hex characters) or NULL. Computed from the canonical bytes of the output equity curve file (CSV). | Reproducibility fingerprint. Allows verification that a replayed run produces byte-identical output. |
| `notes` | STRING | OPTIONAL | Free text, maximum 1024 characters. Double-quoted if it contains commas. | Analyst commentary, caveats, or references. |
| `disclosure_review` | BOOLEAN | REQUIRED | Default `FALSE`. Set to `TRUE` only when this trial's results have been included in any investor-facing document. Once set to `TRUE`, this field is immutable. | Disclosure lock flag. See Ledger Lock Rule in Section 2.2.4. |

---

### 2.2 DSR Calculation Rules

> **Reviewer Notes (non-technical summary):**
> This section defines the exact arithmetic for turning the trial ledger into a single number N — the effective trial count — and then computing the DSR. The weighting system means that minor parameter tweaks count as a fraction of a trial rather than a full trial, which is more statistically honest. The lock rule ensures that once results are shared with investors, the historical record cannot be quietly altered.

#### 2.2.1 counts_toward_dsr Assignment Rules

The following decision rules MUST be applied in order. The first matching rule wins.

**Rule DSR-001:** If `trial_class = REJECTED_CONCEPT` AND `status = LOGGED` AND no run has been initiated (no `run_hash`, `sharpe_ratio`, or other result field is populated), set `counts_toward_dsr = FALSE` with `dsr_exclusion_reason = REJECTED_BEFORE_RUN`.

**Rule DSR-002:** If `trial_class = CONTROL_NULL`, set `counts_toward_dsr = FALSE` with `dsr_exclusion_reason = CONTROL_NULL`. Control null trials are baseline sanity checks (e.g., random entry, buy-and-hold) and are not strategy searches.

**Rule DSR-003:** If this row is a duplicate of another row (identical `fixed_parameters_ref` AND identical canonicalized `parameters_json` AND identical `market` AND identical `replay_window_start` AND identical `replay_window_end`) and both rows have `status = COMPLETE`, the later-entered row MUST be set `counts_toward_dsr = FALSE` with `dsr_exclusion_reason = DUPLICATE_RUN`.

For duplicate detection, `parameters_json` MUST be canonicalized by parsing the JSON object, sorting keys lexicographically, and serializing without insignificant whitespace. For example, `{"a":1,"b":2}` and `{ "b": 2, "a": 1 }` are identical for Rule DSR-003.

**Rule DSR-004:** If `counts_toward_dsr` is manually set to `FALSE` by a designated audit authority (e.g., a compliance review determines a trial was methodologically flawed), set `dsr_exclusion_reason = AUDIT_EXCLUSION`. This action MUST be accompanied by a non-NULL `notes` entry explaining the rationale.

**Rule DSR-005:** All other trials MUST have `counts_toward_dsr = TRUE`, including trials that produced losses, extremely low Sharpes, or were abandoned mid-sweep. The core DSR principle is that the attempt counts, not only the successes.

#### 2.2.2 dsr_weight Weighting Policy

The `dsr_weight` field is assigned according to the following policy. Rules are applied in order; the first matching rule determines the weight.

**Rule WT-001 — Excluded trial:** If `counts_toward_dsr = FALSE`, then `dsr_weight = 0.0`.

**Rule WT-002 — Top-level independent hypothesis (no parent):** If `parent_trial_id` is NULL, then `dsr_weight = 1.0`.

**Rule WT-003 — New gate logic or structural change:** If `parent_trial_id` is non-NULL AND (`trial_class = STRUCTURAL_CHANGE` OR (`is_independent = TRUE` AND `num_params_varied ≥ 4`)), then `dsr_weight = 1.0`.

**Rule WT-004 — Minor variant (single-parameter nudge):** If `parent_trial_id` is non-NULL AND `num_params_varied ≤ 1`, then `dsr_weight = 0.25`.

**Rule WT-005 — Moderate variant:** If `parent_trial_id` is non-NULL AND `num_params_varied` ∈ {2, 3}, then `dsr_weight = 0.5`.

**Rule WT-006 — Major variant (≥4 parameters, same gate structure):** If `parent_trial_id` is non-NULL AND `num_params_varied ≥ 4` AND `trial_class ≠ STRUCTURAL_CHANGE`, then `dsr_weight = 1.0`.

**Rule WT-007 — Cross-market replication:** If `trial_class = CROSS_MARKET` (same logic, different ticker), then `dsr_weight = 0.5`, regardless of `num_params_varied`, UNLESS the cross-market trial also satisfies Rule WT-003, in which case Rule WT-003 takes precedence.

**Override:** Any analyst-assigned `dsr_weight` that deviates from the rules above MUST be accompanied by a non-NULL `notes` entry beginning with the prefix `WEIGHT_OVERRIDE:`. The scorecard generator MUST log a `WEIGHT_OVERRIDE_DETECTED` warning when this occurs.

**Rationale for fractional weights:** The DSR literature treats N as an integer count of fully independent trials. In practice, a researcher who runs 20 variants of a single parameter sweep has not conducted 20 independent experiments. Fractional weighting compresses correlated trials into a fractional N contribution, providing a more honest (higher) denominator for the DSR penalty, which in turn produces a more conservative (lower) DSR estimate. This errs on the side of caution.

#### 2.2.3 Effective N Formula

The effective trial count is defined as:

```
N_eff = SUM(dsr_weight) for all rows WHERE counts_toward_dsr = TRUE
```

N_eff is a floating-point number and need not be an integer.

**Minimum N floor (Rule N-001):** If `N_eff < 3.0`, the scorecard generator MUST NOT compute the DSR. Instead, it MUST emit a `DATA_INTEGRITY_BLOCK` error with the message:

```
INSUFFICIENT_TRIAL_COUNT: N_eff={N_eff:.2f} (minimum required: 3.0).
DSR computation suppressed. Log additional trials before generating a scorecard.
```

**Rationale for the floor of 3:** Bailey & López de Prado (2014) require N ≥ 2 for the formula to be defined, but with N = 2 the DSR is highly unstable. A floor of 3 ensures at minimum two independent hypotheses plus one variant have been evaluated, providing a defensible minimum basis for the multiple-testing correction.

#### 2.2.4 Ledger Lock Rule

Once `disclosure_review = TRUE` on any row, the following fields on that row become **immutable**:

- `sharpe_ratio`
- `counts_toward_dsr`
- `dsr_weight`
- `dsr_exclusion_reason`
- `status`

Any correction to a locked row MUST follow this protocol:

1. Set `status = SUPERSEDED` and `superseded_by = <new_trial_id>` on the locked row. (The only permitted status transition for a locked row is to `SUPERSEDED`, and only via this protocol.)
2. Create a new row with a new `trial_id` and corrected values, referencing the superseded row in `notes`.
3. The new row inherits `disclosure_review = FALSE` initially; if it is subsequently included in an investor document, it must be set to `TRUE` independently.

**Validator enforcement:** The ledger validator MUST reject any modification attempt to the locked fields on a row where `disclosure_review = TRUE`. This check MUST occur at write time, not only at scorecard generation time.

#### 2.2.5 N Staleness Rule

**Rule STL-001:** If the `entry_date` of the most recent row in the ledger where `status` ∈ {`COMPLETE`, `RUNNING`} is more than 30 calendar days before the scorecard generation date, the scorecard generator MUST emit a non-blocking `STALE_LEDGER_WARNING`:

```
STALE_LEDGER_WARNING: Most recent active trial entry_date={date}
is {days} days before scorecard generation date={gen_date}.
Verify that no unlogged trials exist.
```

This warning does not block scorecard generation but MUST appear prominently in the scorecard output and MUST be logged.

---

### 2.3 DSR Input Parameters (Beyond N)

> **Reviewer Notes (non-technical summary):**
> The DSR formula requires several inputs beyond just N. This section pins down exactly where each input comes from so there is no ambiguity in the calculation. The most important rule is that the best Sharpe Ratio must come from the same ledger that defines N — it is not permissible to use a Sharpe from an external source that is not tied to a logged trial.

The DSR formula from Bailey & López de Prado (2014) requires the following inputs. Each is defined precisely below.

#### 2.3.1 SR* — Sharpe of the Best Trial

- **Source:** The row in `dsr_trial_ledger.csv` with the highest `sharpe_ratio` value among all rows where BOTH conditions hold: `counts_toward_dsr = TRUE` AND `status = COMPLETE`.
- **Tie-breaking:** If multiple rows share the highest `sharpe_ratio` (to four decimal places), select the row with the earliest `entry_date`.
- **Constraint:** SR* MUST NOT be sourced from outside the ledger. If an external result must be used, it MUST be logged in the ledger first.

#### 2.3.2 SR_0 — Benchmark Sharpe Ratio

- **Primary definition:** `DSR_ZERO_BENCHMARK` uses SR_0 = **0.0** (the null hypothesis of "no edge").
- **Secondary definition:** `DSR_PEER_BENCHMARK` uses SR_0 = the sourced peer median Sharpe from System 2, when the peer median is available after N-count guards.
- **Peer suppression:** If the peer median is unavailable because `N_peers_with_metric(sharpe_ratio) < 3`, source-tier validation fails, or all peer Sharpe values are `NA`, the scorecard MUST suppress `DSR_PEER_BENCHMARK` and emit `DSR_PEER_BENCHMARK_SUPPRESSED`.
- **Custom benchmarks:** If another non-zero SR_0 is desired, it MUST be documented in scorecard metadata with full justification, and the resulting output MUST be labeled `DSR_CUSTOM_BENCHMARK`.

#### 2.3.3 Skewness (γ₃) and Kurtosis (γ₄)

- **Source:** Computed from the **daily return series** of the specific trial being evaluated (the trial that produced SR*). NOT assumed from a parametric distribution.
- **Return series definition:** Daily returns = percentage change in strategy equity from close of day t−1 to close of day t, for every trading day in the replay window.
- **Minimum observations:** If the daily return series has fewer than 30 observations, the generator MUST emit `LOW_OBSERVATIONS_WARNING` and MAY fall back to γ₃ = 0, γ₄ = 3 (normal distribution). When the fallback is used, the scorecard MUST label the result `DSR_NORMAL_ASSUMPTION`.
- **Storage:** Computed γ₃ and γ₄ values used in DSR MUST be stored in the scorecard metadata.

#### 2.3.4 T — Number of Observations

- **Preferred source:** Number of **trading days** in the replay window of the SR* trial, computed as the count of weekdays in [`replay_window_start`, `replay_window_end`] excluding US federal market holidays.
- **Fallback:** If daily return data is unavailable, use `trade_count` from the SR* trial's ledger row as T. When this fallback is used, the scorecard MUST label the result `DSR_TRADE_BASED_T`.
- **Minimum T:** If T < 30, emit `INSUFFICIENT_OBSERVATIONS_ERROR` and suppress DSR computation.
## 3. System 2: Peer Comparison Fallback Protocol

> **Reviewer Notes (non-technical summary):**
> To contextualize the strategy's performance, we compare it to a peer group of similar funds. But peer data is often incomplete, stale, or sourced from unreliable outlets. This section defines a strict hierarchy of data sources (most trustworthy to least) and precise rules for when we have enough peers to make a valid comparison. If the peer data is too thin or too inconsistent, the system suppresses the z-score rather than reporting a potentially misleading number.

---

### 3.1 Source Hierarchy

Each metric value in the peer table is tagged with a source tier (1–4) indicating the trustworthiness and provenance of the data.

#### Tier 1 — Primary Sources (Highest Trust)

Tier 1 sources are direct disclosures from the fund itself, subject to regulatory oversight.

| Source | Description | Metrics Covered |
|---|---|---|
| Fund factsheet | Published by the fund manager, current within 18 months of the retrieval date. Must be the official factsheet (not a third-party summary). | `sharpe_ratio`, `sortino_ratio`, `cagr_pct`, `calmar_ratio`, `max_drawdown_pct`, `annualized_vol`, `upside_capture`, `downside_capture` |
| SEC Form ADV Part 2 | For US-registered investment advisers and CTAs. Most recent filing used. Retrieved directly from SEC EDGAR. | `cagr_pct`, `max_drawdown_pct`, `annualized_vol` (when disclosed) |
| CFTC Disclosure Document | For commodity pool operators and commodity trading advisors. Regulated disclosure. | `cagr_pct`, `max_drawdown_pct`, `sharpe_ratio` (when disclosed) |

**Tier 1 Requirements:**

1. The source document MUST be retrieved directly (URL or file download), not summarized by a third party.
2. The retrieval date MUST be recorded in `{metric}_source_date`.
3. If the factsheet is older than 18 months from the retrieval date, it is downgraded to Tier 2.

#### Tier 2 — Secondary Sources (Moderate Trust, Derived or Aggregated)

Tier 2 sources are third-party databases that aggregate fund disclosures.

| Source | Description | Metrics Covered |
|---|---|---|
| BarclayHedge CTA Database (`barclayhedge.com`) | One of the largest independent CTA performance databases. Covers most US and international CTAs with > $10M AUM. | `sharpe_ratio`, `cagr_pct` (as annual return), `max_drawdown_pct` |
| IASG (`iasg.com`) | Independent CTA performance database with monthly NAV history available for download. Allows derivation of metrics from NAV series. | Monthly returns → allows derivation of `sharpe_ratio`, `sortino_ratio`, `cagr_pct`, `max_drawdown_pct`, `annualized_vol` |
| Morningstar Direct | For funds structured as US mutual funds or ETF wrappers. Provides standardized risk/return metrics. | Full metric set |
| NilssonHedge (free tier) | Covers top ~50 CTAs by AUM with basic performance statistics. No raw NAV history on free tier. | `sharpe_ratio`, `cagr_pct`, `max_drawdown_pct` |

**Tier 2 Requirements:**

1. Source URL MUST be recorded. If data was downloaded as a file, record `file://{filename}@{timestamp}` in `{metric}_source_url`.
2. If a metric is derived by the analyst from a Tier 2 NAV series, `{metric}_derivation_method` MUST be populated and `{metric}_is_derived` MUST be `TRUE`. The source tier of a derived metric remains Tier 2 (not elevated).

#### Tier 3 — Tertiary Sources (Low Trust, Use with Caution)

Tier 3 sources are acceptable only when Tiers 1 and 2 are exhausted. All Tier 3 data MUST be marked `[UNVERIFIED]` in the scorecard display.

| Source | Description | Metrics Covered |
|---|---|---|
| Academic paper citations | Papers reporting historical peer performance (e.g., Hurst, Ooi & Pedersen AQR papers). Often cover specific historical periods and may be several years stale. | `sharpe_ratio`, `cagr_pct` — period-specific and typically not current |
| News articles / investor letters | Bloomberg, FT, Reuters, or fund-published investor letters that cite performance statistics. High risk of transcription error, selective reporting, or non-standard computation. | Any metric, with extreme caution |
| Analyst-computed from public monthly return series | When a public monthly return series exists (e.g., from a fund's public NAV history or IASG free tier), an analyst computes the metric manually. | Depends on available series |

**Tier 3 Requirements:**

1. `{metric}_is_derived` MUST be `TRUE` for analyst-computed values.
2. All Tier 3 values MUST be accompanied by a non-NULL `{metric}_period_notes` explaining the time period and any known limitations.
3. The scorecard MUST display a `[UNVERIFIED]` badge next to any metric sourced from Tier 3.

#### Tier 4 — No Data Available

When a metric cannot be sourced from any Tier 1–3 source:

1. The metric cell is set to `NA` in the CSV.
2. `{metric}_source_tier` is set to `4`.
3. The metric is excluded from all z-score calculations for that peer.
4. The scorecard MUST display a visual `NA` indicator for the cell.
5. The peer row is NOT excluded from the peer table unless ALL metrics are `NA`, in which case `exclude_from_zscore = TRUE` and `exclusion_reason = ALL_METRICS_NA`.

---

### 3.2 Per-Metric Fallback Map

The following table defines the complete fallback sequence across tiers, derivability rules, and cross-period flag behavior for each tracked metric.

| Metric | Tier 1 Coverage | Tier 2 Coverage | Tier 3 Coverage | Can Be Derived? | Derivation Method | Derived-Value Tier | Cross-Period Flag Applies? |
|---|---|---|---|---|---|---|---|
| `sharpe_ratio` | Factsheet, CFTC | BarclayHedge, IASG (monthly NAV), NilssonHedge | Academic papers, news | YES | `mean(r) / std(r) × sqrt(annualization_factor)` from monthly or daily return series | Inherits source tier of underlying NAV data | YES — Sharpe is highly regime-dependent |
| `sortino_ratio` | Factsheet | IASG (monthly NAV), Morningstar | Academic papers | YES | From monthly returns using downside deviation below 0% MAR | Inherits source tier | YES |
| `cagr_pct` | Factsheet, ADV, CFTC | BarclayHedge, IASG, NilssonHedge, Morningstar | News, investor letters | YES | `(NAV_end / NAV_start)^(1/years) - 1` from NAV series | Inherits source tier | YES — strongly period-dependent |
| `calmar_ratio` | Factsheet | Morningstar | Analyst-computed | YES — preferred derivation | `cagr_pct / |max_drawdown_pct|`. If components are from different source tiers, derived tier = `max(tier_cagr, tier_max_dd)` | Derived tier = max of component tiers | PARTIAL — if components are from different periods, emit `PERIOD_MISMATCH_WARNING` |
| `max_drawdown_pct` | Factsheet, ADV, CFTC | BarclayHedge, IASG, NilssonHedge, Morningstar | Academic papers, news | YES | Running maximum drawdown from NAV or equity curve | Inherits source tier | YES — max DD is strongly window-dependent |
| `annualized_vol` | Factsheet | IASG (monthly NAV), Morningstar | Analyst-computed | YES | `std(daily_returns) × sqrt(252)` or `std(monthly_returns) × sqrt(12)` | Inherits source tier | MODERATE |
| `upside_capture` | Factsheet | Morningstar | Analyst-computed vs. chosen benchmark | YES | Requires defining a benchmark; specify in `{metric}_period_notes` | Inherits source tier | YES — benchmark choice and period both affect value |
| `downside_capture` | Factsheet | Morningstar | Analyst-computed vs. chosen benchmark | YES | Same as upside_capture restricted to benchmark-negative periods | Inherits source tier | YES |

**Derivation Trust-Tier Rule:** When a metric is derived from components, the trust tier of the derived metric is the **maximum (least favorable) tier** of its inputs. Example: if `cagr_pct` is Tier 2 and `max_drawdown_pct` is Tier 1, derived `calmar_ratio` is Tier 2.

**Cross-Period Inconsistency Rule:** If two peer rows for the same metric have `metric_date_start` or `metric_date_end` values that differ by more than 5 years from each other, the z-score computation MUST emit `PERIOD_MISMATCH_WARNING` for that metric (see Section 3.3.2 Rule G-005).

**Tier 3 Failure Protocol:** If a metric cannot be sourced from Tier 1, 2, or 3 for a given peer, the metric is set to `NA` (Tier 4) and excluded from z-score computation for that peer row.

---

### 3.3 N-Count Guard Logic

> **Reviewer Notes (non-technical summary):**
> A z-score is only meaningful if computed from enough peers. This section defines exact thresholds below which the z-score is suppressed or flagged. The intent is to prevent a z-score of "top 5th percentile" — computed from only two peers — from being misrepresented as a robust statistical ranking.

The N-count guard is evaluated **per metric**, not per peer row. A peer row that has no value for metric M does not contribute to the N count for metric M.

#### 3.3.1 Definitions

- **`N_peers_with_metric(M)`** = count of rows in `peer_comparison_table.csv` where the metric value for M is not `NA` AND `exclude_from_zscore = FALSE`.
- **`peer_mean(M)`** = arithmetic mean of metric M across all non-NA, non-excluded peers.
- **`peer_sd(M)`** = sample standard deviation (ddof=1) of metric M across all non-NA, non-excluded peers.
- **`our_value(M)`** = the strategy's own value for metric M, sourced from the DSR trial ledger (SR*) or the scorecard's computed metrics.
- **`span_years(M)`** = `MAX(metric_date_end)` minus `MIN(metric_date_start)`, expressed in years, across all non-NA, non-excluded peers contributing metric M.

#### 3.3.2 Guard Decision Rules (Applied in Order)

**Guard Rule G-001 — Suppress z-score (insufficient peers):**
If `N_peers_with_metric(M) < 3`, then:
- Do NOT compute z-score.
- Emit `Z_SCORE_SUPPRESSED` for this metric.
- Display in scorecard: `"Insufficient peer data (N={N_peers_with_metric(M)})"`.

**Guard Rule G-002 — Degenerate standard deviation:**
If `N_peers_with_metric(M) >= 3` AND `peer_sd(M) < 0.01`, then:
- Do NOT compute z-score.
- Emit `DEGENERATE_PEER_SD` warning.
- Display in scorecard: `"Peer SD too small to rank (SD={peer_sd(M):.4f})"`.

**Guard Rule G-003 — Low-N warning:**
If `N_peers_with_metric(M) >= 3` AND `N_peers_with_metric(M) < 5`, then:
- Compute z-score (proceed to Section 3.3.3).
- Attach `LOW_N_WARNING` flag to this metric's z-score output.
- Display a caution banner: `"Low peer count (N={N_peers_with_metric(M)}). Z-score has limited statistical power."`.

**Guard Rule G-004 — Normal computation:**
If `N_peers_with_metric(M) >= 5`, compute z-score normally (Section 3.3.3). No warning flag attached.

**Guard Rule G-005 — Cross-period contamination:**
After z-score computation (if it proceeds), evaluate the date range spread:
- Let `span_years(M)` be defined as in Section 3.3.1.
- If `span_years(M) > 5`, emit `PERIOD_MISMATCH_WARNING` for this metric:

  ```
  PERIOD_MISMATCH_WARNING: metric={M}, date span={span_years:.1f} years across contributing peers.
  Performance periods are structurally dissimilar. Z-score may not be valid.
  ```

- `PERIOD_MISMATCH_WARNING` is non-blocking but MUST be displayed prominently in the scorecard.

**Rationale for the 5-year span threshold:** For trend-following CTAs, the 2010s represented a structurally different volatility and correlation regime from the 2000s or 2020s. A Sharpe Ratio computed from 2005–2015 data is not directly comparable to one from 2015–2025. Five years is chosen as the threshold because it spans approximately two full market cycles and captures meaningful structural regime differences.

#### 3.3.3 Z-Score Computation (When Permitted by Guards)

**Formula:**

```
z_score(M) = (our_value(M) − peer_mean(M)) / peer_sd(M)
```

**Z-score cap:**
- The raw z-score is stored in the scorecard metadata without capping.
- For display purposes only, the z-score is clipped to [−5.0, +5.0].
- If the raw z-score exceeds ±5.0, the display shows `>+5.0` or `<−5.0` respectively.

**Percentile rank:**
- Formula: `percentile = (count of peers with M < our_value(M)) / N_peers_with_metric(M) × 100`
- Ties: use fractional ranking (average of tied ranks).
- The percentile reflects rank among the N non-NA peers; our own strategy is not included in the denominator.

**Scorecard MUST report per metric (when z-score is computed):**

1. `peer_mean(M)` — rounded to 2 decimal places
2. `peer_sd(M)` — rounded to 3 decimal places
3. `N_peers_with_metric(M)` — integer
4. `z_score(M)` — display-capped value
5. `percentile_rank(M)` — rounded to 1 decimal place
6. All active warning flags for this metric

---

### 3.4 Peer Table Schema

#### 3.4.1 File-Level Requirements

Same encoding and header-comment requirements as the trial ledger (Section 2.1.1). The `generated_at` header comment applies. Delimiter is comma. Boolean literals are `TRUE`/`FALSE`. NA values are empty strings.

#### 3.4.2 Tracked Metrics

The eight tracked metrics are: `sharpe_ratio`, `sortino_ratio`, `cagr_pct`, `calmar_ratio`, `max_drawdown_pct`, `annualized_vol`, `upside_capture`, `downside_capture`.

For each metric `{M}`, the following seven paired columns exist: `{M}`, `{M}_source_tier`, `{M}_source_url`, `{M}_source_date`, `{M}_is_derived`, `{M}_derivation_method`, `{M}_period_notes`.

#### 3.4.3 Identity and Classification Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `peer_id` | STRING | REQUIRED | Format: `PEER_{SHORT_NAME}_{NN}`, e.g. `PEER_WINTON_01`. Maximum 32 characters. Only uppercase letters, digits, and underscores. Stable across file versions. | Stable, unique identifier for this peer entry. |
| `fund_name` | STRING | REQUIRED | Maximum 128 characters. | Full legal or common name of the fund or manager. |
| `strategy_type` | STRING | REQUIRED | Free text, maximum 64 characters. Examples: `Trend-Following CTA`, `Systematic Macro`, `Volatility Arbitrage`, `Multi-Strategy`. | Classification of the fund's primary strategy. |
| `aum_usd_mm` | FLOAT | OPTIONAL | NULL allowed. Non-negative. Denominated in millions of USD. | Assets under management in USD millions, as of the most recent available date. |
| `inception_year` | INTEGER | OPTIONAL | NULL allowed. 4-digit year. | Year the fund or the relevant track record commenced. |
| `metric_date_start` | DATE | REQUIRED | ISO date. Start of the period over which all metrics in this row are measured. If different metrics cover different periods, use the EARLIEST start date and document exceptions in per-metric `{M}_period_notes`. | Start date of the performance measurement period for this row. |
| `metric_date_end` | DATE | REQUIRED | ISO date. | End date of the performance measurement period for this row. |

#### 3.4.4 Per-Metric Fields (Repeated for Each Metric M)

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `{M}` | FLOAT or NA | CONDITIONAL | NULL/NA if unavailable. For `max_drawdown_pct`, stored as a negative number (same convention as the trial ledger). | The metric value for this peer. |
| `{M}_source_tier` | INTEGER | REQUIRED | 1, 2, 3, or 4. Set to 4 when `{M}` is NA. | Source trust tier for this metric value. |
| `{M}_source_url` | STRING | CONDITIONAL | REQUIRED when `{M}_source_tier` ∈ {1, 2, 3}. NULL only when `{M}_source_tier = 4`. Must be a valid URL or a file reference in format `file://{filename}@{ISO-datetime}`. | Direct URL or file reference for the source document or database. |
| `{M}_source_date` | DATE | CONDITIONAL | REQUIRED when `{M}_source_tier` ∈ {1, 2, 3}. NULL only when `{M}_source_tier = 4`. | Date the source was retrieved or the document was published. |
| `{M}_is_derived` | BOOLEAN | REQUIRED | `TRUE` if the metric was computed by the analyst from underlying data. `FALSE` if directly quoted from the source. | Derivation flag. |
| `{M}_derivation_method` | STRING | CONDITIONAL | NULL when `{M}_is_derived = FALSE`. Required when `{M}_is_derived = TRUE`. Maximum 256 characters. | Description of the computation used to derive the metric value. |
| `{M}_period_notes` | STRING | OPTIONAL | NULL allowed. Free text, maximum 256 characters. | Notes on the measurement period, benchmark used, or any known deviation from the row-level date range. |

#### 3.4.5 Quality Control Fields

| Field Name | Type | Required | Constraints | Description |
|---|---|---|---|---|
| `exclude_from_zscore` | BOOLEAN | REQUIRED | Default `FALSE`. Set to `TRUE` when any CRITICAL data quality issue is present. | Whether this peer row is excluded from all z-score computations. |
| `exclusion_reason` | STRING | CONDITIONAL | NULL when `exclude_from_zscore = FALSE`. Required when `exclude_from_zscore = TRUE`. | Explanation for exclusion. |

**Conditions that MUST trigger `exclude_from_zscore = TRUE`:**

1. All tracked metrics are NA → `exclusion_reason = ALL_METRICS_NA`.
2. `metric_date_end < metric_date_start` (data error) → `exclusion_reason = INVALID_DATE_RANGE`.
3. Analyst has manually flagged the row as suspect → `exclusion_reason` begins with `MANUAL_EXCLUSION:`.

---

### 3.5 Scorecard Integration Rules

> **Reviewer Notes (non-technical summary):**
> This section ties the two systems together. The scorecard generator reads both CSV files and produces the investor-facing performance summary. It has hard stops (blocking errors that prevent scorecard generation) and soft warnings (which appear on the scorecard but don't prevent it from rendering). No scorecard can be generated from incomplete or stale data without the analyst being explicitly informed.

#### 3.5.1 Input Requirements

The scorecard generator MUST accept exactly two input files:

1. `dsr_trial_ledger.csv` — the trial ledger defined in Section 2.1.
2. `peer_comparison_table.csv` — the peer table defined in Section 3.4.

Both files MUST contain a valid `generated_at` header comment. If either header comment is missing or malformed, the generator MUST emit `DATA_INTEGRITY_BLOCK: MISSING_HEADER_COMMENT` and halt.

#### 3.5.2 Blocking Errors (DATA_INTEGRITY_BLOCK)

The scorecard generator MUST refuse to render and MUST emit `DATA_INTEGRITY_BLOCK` if ANY of the following conditions are true. Conditions are evaluated in order.

**Block Rule B-001 — Insufficient trial count:**
`N_eff < 3.0` (as computed per Section 2.2.3).

**Block Rule B-002 — Completed trial missing Sharpe:**
Any row exists in the trial ledger where ALL of the following hold simultaneously:
- `counts_toward_dsr = TRUE`
- `status = COMPLETE`
- `sharpe_ratio` is NULL

A completed trial that counts toward DSR MUST have a Sharpe Ratio result.

**Block Rule B-003 — Invalid dsr_weight sum:**
`N_eff` is negative or contains NaN due to invalid weight values.

**Block Rule B-004 — Ledger validation failure:**
The ledger validator rejects the file (e.g., malformed `trial_id`, duplicate `trial_id`, invalid enum values, `counts_toward_dsr=FALSE` with NULL `dsr_exclusion_reason`).

**Block Rule B-005 — Circular parent references:**
Any `parent_trial_id` chain in the ledger contains a cycle.

#### 3.5.3 Non-Blocking Warnings (Emitted on Scorecard)

The following conditions MUST produce visible warnings on the rendered scorecard but MUST NOT prevent generation:

| Warning Code | Trigger Condition |
|---|---|
| `LOW_N_WARNING` | `N_peers_with_metric(M) >= 3` AND `< 5` for any metric M |
| `PERIOD_MISMATCH_WARNING` | Date span > 5 years across contributing peers for any metric M (Rule G-005) |
| `STALE_LEDGER_WARNING` | Most recent active trial entry_date > 30 days before scorecard generation date (Rule STL-001) |
| `ALL_METRICS_NA_PEER` | Any peer row where all tracked metrics are NA |
| `WEIGHT_OVERRIDE_DETECTED` | Any ledger row has a `dsr_weight` deviating from the policy in Section 2.2.2 |
| `DSR_NORMAL_ASSUMPTION` | Skewness/kurtosis fell back to normal assumption (Section 2.3.3) |
| `DSR_TRADE_BASED_T` | `trade_count` was used as T instead of trading-day count (Section 2.3.4) |
| `LOW_OBSERVATIONS_WARNING` | Daily return series for SR* trial has < 30 observations |
| `DEGENERATE_PEER_SD` | `peer_sd(M) < 0.01` for any metric M |
| `Z_SCORE_SUPPRESSED` | `N_peers_with_metric(M) < 3` for any metric M |
| `OOS_REPLAY_TYPE_MISMATCH_WARNING` | `is_oos = TRUE` while `replay_type != OOS_HOLDOUT` |
| `DSR_PEER_BENCHMARK_SUPPRESSED` | Sourced peer median Sharpe is unavailable after peer N-count/source guards |

#### 3.5.4 Versioning

Both input files MUST be versioned using the `generated_at` timestamp in their header comment. The scorecard output MUST record the `generated_at` timestamps of both input files and the scorecard generation timestamp in its metadata block.

Example scorecard metadata block (non-normative):

```
# SCORECARD METADATA
# scorecard_generated_at: 2026-06-26T10:00:00Z
# ledger_version: 2026-06-25T16:42:00Z
# peer_table_version: 2026-06-20T11:00:00Z
# N_eff: 7.25
# SR_star: 1.42 (TRL-2026-00007)
# SR_0: 0.0
# DSR: 0.89
# DSR_flags: []
```
## 4. Worked Examples

> **Reviewer Notes (non-technical summary):**
> This section provides minimal but complete examples of both CSV files and walks through the key computations to verify that an implementation produces the expected outputs. The examples are intentionally small to make the logic traceable by hand.

---

### 4.1 Minimal `dsr_trial_ledger.csv` (5 Rows)

The header comment and column headers are included. The file below uses abbreviated notation for readability; the actual file is a single continuous CSV with one data row per line.

```csv
# generated_at=2026-06-26T09:00:00Z; schema_version=1.0
trial_id,entry_date,analyst,trial_class,trial_subclass,parent_trial_id,is_independent,market,replay_window_start,replay_window_end,replay_type,is_oos,training_window_start,training_window_end,parameters_json,fixed_parameters_ref,num_params_varied,sharpe_ratio,sortino_ratio,cagr_pct,calmar_ratio,max_drawdown_pct,trade_count,pf,net_pnl,qqq_correlation,qqq_downside_capture,counts_toward_dsr,dsr_weight,dsr_exclusion_reason,status,superseded_by,run_hash,notes,disclosure_review
TRL-2026-00001,2026-01-10,JRB,TIMING_STUDY,base_OR_timing_v1,,TRUE,NQ,2023-01-02,2025-12-31,COMMON_WINDOW,FALSE,2023-01-02,2024-06-30,"{}",configs/baseline_v1.yaml,0,1.21,1.65,18.4,1.02,-18.1,312,1.43,24800.00,0.31,0.22,TRUE,1.0,,COMPLETE,,a3f2b1c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2,Base timing hypothesis; no parent.,FALSE
TRL-2026-00002,2026-01-15,JRB,SIZING_SWEEP,v2b_target_multiplier_sweep,TRL-2026-00001,FALSE,NQ,2023-01-02,2025-12-31,COMMON_WINDOW,FALSE,2023-01-02,2024-06-30,"{""v2b_target_mult"": 1.5}",configs/baseline_v1.yaml,1,1.35,1.80,21.2,1.14,-18.6,309,1.51,27300.00,0.30,0.21,TRUE,0.25,,COMPLETE,,b4e3c2d1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c3,Single-param variant: increased v2b target mult.,FALSE
TRL-2026-00003,2026-02-01,JRB,FILTER_EXPLORATION,ST_lookback_days_PMC_combo,TRL-2026-00001,FALSE,NQ,2023-01-02,2025-12-31,COMMON_WINDOW,FALSE,2023-01-02,2024-06-30,"{""st_lookback_days"": 20, ""pmc_lookback_days"": 15}",configs/baseline_v1.yaml,2,1.42,1.91,22.7,1.20,-18.9,298,1.56,29100.00,0.29,0.20,TRUE,0.5,,COMPLETE,,c5f4d3e2a1b0c9d8e7f6a5b4c3d2e1f0a9b8c7d6e5f4a3b2c1d0e9f8a7b6c5d4,Two-param variant: ST and PMC lookback combined.,FALSE
TRL-2026-00004,2026-02-20,KPL,CONTROL_NULL,buy_and_hold_NQ_control,,FALSE,NQ,2023-01-02,2025-12-31,COMMON_WINDOW,FALSE,,,{},configs/baseline_v1.yaml,0,0.88,1.10,14.2,,,-1,,18200.00,1.00,,FALSE,0.0,CONTROL_NULL,COMPLETE,,,Null control: buy-and-hold NQ benchmark. Not a strategy search.,FALSE
TRL-2026-00005,2026-03-05,JRB,REJECTED_CONCEPT,OR_width_quartile_cutoff_v1,,FALSE,NQ,,,,,,,{},configs/baseline_v1.yaml,0,,,,,,,,,,FALSE,0.0,REJECTED_BEFORE_RUN,LOGGED,,,Rejected before running: OR width quartile cutoff concept deemed structurally unsound in design review.,FALSE
```

**Row-by-Row Annotation:**

| Row | trial_id | counts_toward_dsr | dsr_weight | Rule Applied | Reason |
|---|---|---|---|---|---|
| 1 | TRL-2026-00001 | TRUE | 1.0 | WT-002 | No parent; root hypothesis |
| 2 | TRL-2026-00002 | TRUE | 0.25 | WT-004 | Has parent; num_params_varied = 1 |
| 3 | TRL-2026-00003 | TRUE | 0.5 | WT-005 | Has parent; num_params_varied = 2 |
| 4 | TRL-2026-00004 | FALSE | 0.0 | WT-001 + DSR-002 | CONTROL_NULL; excluded |
| 5 | TRL-2026-00005 | FALSE | 0.0 | WT-001 + DSR-001 | REJECTED_BEFORE_RUN; never run |

**N_eff = 1.0 + 0.25 + 0.5 + 0.0 + 0.0 = 1.75**

> **Expected outcome:** N_eff = 1.75 < 3.0. The scorecard generator fires Block Rule B-001 and emits:
> ```
> DATA_INTEGRITY_BLOCK: INSUFFICIENT_TRIAL_COUNT: N_eff=1.75 (minimum required: 3.0).
> DSR computation suppressed. Log additional trials before generating a scorecard.
> ```
> This is intentional. A realistic production ledger would contain multiple root-level hypotheses. The example illustrates guard behavior on a minimal ledger.

**SR* identification (hypothetical, ignoring N_eff block):** Among `counts_toward_dsr = TRUE` and `status = COMPLETE` rows:

| trial_id | sharpe_ratio |
|---|---|
| TRL-2026-00001 | 1.21 |
| TRL-2026-00002 | 1.35 |
| TRL-2026-00003 | 1.42 ← **SR*** |

SR* = 1.42, sourced from TRL-2026-00003.

---

### 4.2 Minimal `peer_comparison_table.csv` (3 Rows)

One peer (PEER_ALPHATREND_01) has `sharpe_ratio = NA`, which triggers `Z_SCORE_SUPPRESSED` for that metric because `N_peers_with_metric(sharpe_ratio) = 2 < 3`.

The CSV below is abbreviated to three metrics (`sharpe_ratio`, `max_drawdown_pct`, `cagr_pct`) for readability. A production file would include all eight tracked metrics and their seven paired columns each.

```csv
# generated_at=2026-06-20T11:00:00Z; schema_version=1.0
peer_id,fund_name,strategy_type,aum_usd_mm,inception_year,metric_date_start,metric_date_end,sharpe_ratio,sharpe_ratio_source_tier,sharpe_ratio_source_url,sharpe_ratio_source_date,sharpe_ratio_is_derived,sharpe_ratio_derivation_method,sharpe_ratio_period_notes,max_drawdown_pct,max_drawdown_pct_source_tier,max_drawdown_pct_source_url,max_drawdown_pct_source_date,max_drawdown_pct_is_derived,max_drawdown_pct_derivation_method,max_drawdown_pct_period_notes,cagr_pct,cagr_pct_source_tier,cagr_pct_source_url,cagr_pct_source_date,cagr_pct_is_derived,cagr_pct_derivation_method,cagr_pct_period_notes,exclude_from_zscore,exclusion_reason
PEER_WINTON_01,Winton Group,Trend-Following CTA,7200.0,1997,2015-01-01,2024-12-31,0.72,1,https://www.winton.com/literature/factsheet-2024.pdf,2025-02-15,FALSE,,,-19.4,1,https://www.winton.com/literature/factsheet-2024.pdf,2025-02-15,FALSE,,,12.1,1,https://www.winton.com/literature/factsheet-2024.pdf,2025-02-15,FALSE,,,FALSE,
PEER_MILLBURN_01,Millburn Ridgefield,Trend-Following CTA,3100.0,1971,2015-01-01,2024-12-31,0.65,2,https://www.barclayhedge.com/databases/cta-fund/millburn,2026-05-01,FALSE,,,-22.1,2,https://www.barclayhedge.com/databases/cta-fund/millburn,2026-05-01,FALSE,,,10.8,2,https://www.barclayhedge.com/databases/cta-fund/millburn,2026-05-01,FALSE,,,FALSE,
PEER_ALPHATREND_01,AlphaTrend Capital,Trend-Following CTA,85.0,2018,2020-01-01,2024-12-31,,4,,,FALSE,,,-17.2,3,https://iasg.com/alphatrend,2026-04-10,TRUE,Computed from IASG monthly NAV series: running max DD,Period 2020–2024 only; shorter track record,8.3,3,https://iasg.com/alphatrend,2026-04-10,TRUE,"CAGR computed from IASG monthly NAV: (NAV_end/NAV_start)^(1/years)-1",Period 2020–2024 only,FALSE,
```

**Row-by-Row Annotation:**

| peer_id | sharpe_ratio | sharpe_ratio_source_tier | max_drawdown_pct | cagr_pct |
|---|---|---|---|---|
| PEER_WINTON_01 | 0.72 | Tier 1 (factsheet) | -19.4 (Tier 1) | 12.1% (Tier 1) |
| PEER_MILLBURN_01 | 0.65 | Tier 2 (BarclayHedge) | -22.1 (Tier 2) | 10.8% (Tier 2) |
| PEER_ALPHATREND_01 | NA | Tier 4 (not found) | -17.2 (Tier 3, derived) | 8.3% (Tier 3, derived) |

---

### 4.3 Walkthrough — N_eff Computation

**Input ledger (from Section 4.1):**

| trial_id | counts_toward_dsr | dsr_weight |
|---|---|---|
| TRL-2026-00001 | TRUE | 1.00 |
| TRL-2026-00002 | TRUE | 0.25 |
| TRL-2026-00003 | TRUE | 0.50 |
| TRL-2026-00004 | FALSE | 0.00 |
| TRL-2026-00005 | FALSE | 0.00 |

**Step 1:** Filter to `counts_toward_dsr = TRUE`: rows 1, 2, 3.

**Step 2:** Sum `dsr_weight`: `1.00 + 0.25 + 0.50 = 1.75`.

**Step 3:** N_eff = 1.75.

**Step 4:** Apply Rule N-001 (minimum floor): 1.75 < 3.0 → emit `DATA_INTEGRITY_BLOCK: INSUFFICIENT_TRIAL_COUNT`. Halt.

**Hypothetical extended ledger** (if three more independent root hypotheses TRL-2026-00006, 00007, 00008 are added, each with `dsr_weight = 1.0`):

| trial_id | dsr_weight |
|---|---|
| TRL-2026-00001 | 1.00 |
| TRL-2026-00002 | 0.25 |
| TRL-2026-00003 | 0.50 |
| TRL-2026-00006 | 1.00 |
| TRL-2026-00007 | 1.00 |
| TRL-2026-00008 | 1.00 |

**Extended N_eff = 1.00 + 0.25 + 0.50 + 1.00 + 1.00 + 1.00 = 4.75**

4.75 ≥ 3.0 → N_eff check passes. DSR computation proceeds with N = 4.75.

---

### 4.4 Walkthrough — Z-Score Guard Evaluation

Using the peer table from Section 4.2 and the hypothetical strategy values.

#### 4.4.1 Metric: `sharpe_ratio` (our strategy SR* = 1.42)

**Step 1: Count valid peers.**

| peer_id | sharpe_ratio | exclude_from_zscore | Contributes? |
|---|---|---|---|
| PEER_WINTON_01 | 0.72 | FALSE | YES |
| PEER_MILLBURN_01 | 0.65 | FALSE | YES |
| PEER_ALPHATREND_01 | NA | FALSE | NO (NA) |

`N_peers_with_metric(sharpe_ratio)` = 2.

**Step 2: Apply Guard Rule G-001.**
2 < 3 → `Z_SCORE_SUPPRESSED`. Do not compute z-score.

**Scorecard display:**
```
sharpe_ratio: 1.42
Peer z-score: Insufficient peer data (N=2)
[Z_SCORE_SUPPRESSED]
```

---

#### 4.4.2 Metric: `cagr_pct` (our strategy CAGR = 22.7%)

**Step 1: Count valid peers.**

| peer_id | cagr_pct | Contributes? |
|---|---|---|
| PEER_WINTON_01 | 12.1 | YES |
| PEER_MILLBURN_01 | 10.8 | YES |
| PEER_ALPHATREND_01 | 8.3 | YES |

`N_peers_with_metric(cagr_pct)` = 3.

**Step 2: Apply Guard Rule G-001.** 3 ≥ 3 → does not trigger.

**Step 3: Apply Guard Rule G-003.** 3 ≥ 3 AND 3 < 5 → attach `LOW_N_WARNING`. Proceed.

**Step 4: Compute peer statistics.**

```
peer_mean = (12.1 + 10.8 + 8.3) / 3 = 31.2 / 3 = 10.40

deviations from mean:
  12.1 − 10.40 = +1.70 → squared: 2.89
  10.8 − 10.40 = +0.40 → squared: 0.16
   8.3 − 10.40 = −2.10 → squared: 4.41

sum of squared deviations = 2.89 + 0.16 + 4.41 = 7.46
peer_sd = sqrt(7.46 / (3−1)) = sqrt(3.73) ≈ 1.932
```

**Step 5: Apply Guard Rule G-002 (SD floor).** 1.932 ≥ 0.01 → OK, continue.

**Step 6: Apply Guard Rule G-004.** N < 5 → Guard G-003 already triggered. No further guard action.

**Step 7: Compute z-score.**

```
z_score = (22.7 − 10.40) / 1.932 = 12.30 / 1.932 ≈ 6.37
```

**Step 8: Apply display cap.** Raw z = 6.37 > 5.0 → display value = `>+5.0`. Store raw 6.37 in metadata.

**Step 9: Compute percentile rank.**

Count of peers with cagr_pct < 22.7: 3 (12.1 < 22.7 ✓, 10.8 < 22.7 ✓, 8.3 < 22.7 ✓).

```
percentile = 3 / 3 × 100 = 100.0%
```

**Step 10: Apply Guard Rule G-005 (cross-period contamination).**

```
MIN(metric_date_start) = 2015-01-01  (Winton and Millburn)
MAX(metric_date_end)   = 2024-12-31

span_years = 2024.99 − 2015.00 ≈ 10.0 years > 5 years
→ emit PERIOD_MISMATCH_WARNING
```

**Final scorecard output for `cagr_pct`:**
```
cagr_pct: 22.7%
Peer mean: 10.40% | Peer SD: 1.932 | N=3
Z-score: >+5.0 (raw: 6.37) | Percentile: 100.0%
Flags: [LOW_N_WARNING] [PERIOD_MISMATCH_WARNING]
```

---

#### 4.4.3 Metric: `max_drawdown_pct` (our strategy MDD = −18.9%)

**Step 1: Count valid peers.**

| peer_id | max_drawdown_pct | Contributes? |
|---|---|---|
| PEER_WINTON_01 | -19.4 | YES |
| PEER_MILLBURN_01 | -22.1 | YES |
| PEER_ALPHATREND_01 | -17.2 | YES (Tier 3, derived — not excluded) |

`N_peers_with_metric(max_drawdown_pct)` = 3.

**Step 2: Guard Rules.** G-001: 3 ≥ 3 → does not trigger. G-003: 3 < 5 → attach `LOW_N_WARNING`.

**Step 3: Compute statistics.**

```
peer_mean = (−19.4 + −22.1 + −17.2) / 3 = −58.7 / 3 = −19.567

deviations:
  −19.4 − (−19.567) = +0.167 → squared: 0.028
  −22.1 − (−19.567) = −2.533 → squared: 6.416
  −17.2 − (−19.567) = +2.367 → squared: 5.602

sum = 0.028 + 6.416 + 5.602 = 12.046
peer_sd = sqrt(12.046 / 2) = sqrt(6.023) ≈ 2.454
```

**Step 4: Z-score.**

```
z_score = (−18.9 − (−19.567)) / 2.454 = 0.667 / 2.454 ≈ 0.27
```

(A higher — less negative — drawdown is better; a positive z-score here means lower drawdown than peer mean.)

**Step 5: Percentile rank.**

Count of peers with max_drawdown_pct < −18.9 (i.e., worse drawdown): -19.4 < -18.9 ✓, -22.1 < -18.9 ✓. Count = 2.

```
percentile = 2 / 3 × 100 = 66.7%
```

**Step 6: Period mismatch check.**

Span: 2024-12-31 − 2015-01-01 ≈ 10 years > 5 → `PERIOD_MISMATCH_WARNING`.

**Final scorecard output for `max_drawdown_pct`:**
```
max_drawdown_pct: −18.9%
Peer mean: −19.57% | Peer SD: 2.454 | N=3
Z-score: +0.27 | Percentile: 66.7%
Flags: [LOW_N_WARNING] [PERIOD_MISMATCH_WARNING]
Note: PEER_ALPHATREND_01 max_drawdown_pct is UNVERIFIED (Tier 3, derived from IASG NAV series)
```

---

## 5. Appendix A: Enum Master List

### trial_class Definitions

| Value | Description |
|---|---|
| `SIZING_SWEEP` | Trials varying position sizing, target multipliers, risk-per-trade, or capital allocation parameters. |
| `TIMING_STUDY` | Trials varying entry/exit timing logic, session filters, bar-type choices, or time-of-day constraints. |
| `FILTER_EXPLORATION` | Trials adding, removing, or varying signal filters (momentum, volatility, regime, volume, etc.). |
| `GATE_VARIANT` | Trials that modify an existing gate condition (e.g., changing the conditions under which a strategy is allowed to trade). |
| `CROSS_MARKET` | Trials applying the same (or nearly the same) logic to a different market or instrument. MUST reference the source strategy via `parent_trial_id`. |
| `STRUCTURAL_CHANGE` | Trials introducing a fundamentally new mechanism: new entry logic type, new exit paradigm, new model architecture. Always `is_independent = TRUE`. |
| `CONTROL_NULL` | Null benchmark trials: buy-and-hold, random entry, passive index replication. Not strategy searches. Always excluded from N. |
| `REJECTED_CONCEPT` | Concepts logged for completeness but rejected before running (design review failure, known data issue, etc.). Excluded from N only if never run; if run before rejection is logged, they count. |

### replay_type Definitions

| Value | Description |
|---|---|
| `COMMON_WINDOW` | Replay window is the same standardized window used across most trials for comparability. |
| `FULL_HISTORY` | Replay window spans the full available history for the instrument. |
| `OOS_HOLDOUT` | Replay window was strictly designated as out-of-sample before trial design began. Implies `is_oos = TRUE`. |
| `LIVE` | Results from live trading (real money or paper trading in real-time market conditions). |

### status State Transitions

**Valid transitions:**

```
LOGGED   → RUNNING     (trial is dispatched to the execution engine)
RUNNING  → COMPLETE    (trial finished successfully; results available)
RUNNING  → FAILED      (trial finished with an error; no valid results)
LOGGED   → FAILED      (configuration error discovered before run)
COMPLETE → SUPERSEDED  (via Ledger Lock Rule, Section 2.2.4)
RUNNING  → SUPERSEDED  (analyst cancels and replaces)
FAILED   → LOGGED      (analyst corrects configuration and re-queues)
```

**Invalid transitions (MUST be rejected by validator):**

- Any transition FROM `COMPLETE` to any state other than `SUPERSEDED`.
- Any transition FROM `SUPERSEDED` to any state.
- Setting `SUPERSEDED` without a valid non-NULL `superseded_by` value.
- Setting `COMPLETE` without a `sharpe_ratio` value when `counts_toward_dsr = TRUE`.

### market Enum Values

| Value | Instrument |
|---|---|
| `NQ` | E-mini Nasdaq 100 Futures |
| `MNQ` | Micro E-mini Nasdaq 100 Futures |
| `ES` | E-mini S&P 500 Futures |
| `MES` | Micro E-mini S&P 500 Futures |
| `YM` | E-mini Dow Jones Futures |
| `MYM` | Micro E-mini Dow Jones Futures |
| `RTY` | E-mini Russell 2000 Futures |
| `MBT` | Micro Bitcoin Futures |
| `GC` | Gold Futures |
| `CL` | Crude Oil Futures (WTI) |
| `ZN` | 10-Year T-Note Futures |
| `6E` | Euro FX Futures |
| `MULTI` | Multi-instrument strategy (two or more of the above traded simultaneously) |
| `OTHER` | Any instrument not listed above; document ticker in `notes` |

### dsr_exclusion_reason Enum Values

| Value | Applicable Rule | Description |
|---|---|---|
| `REJECTED_BEFORE_RUN` | DSR-001 | Trial was logged as a concept but rejected before any run was initiated. |
| `CONTROL_NULL` | DSR-002 | Trial is a null/benchmark control, not a strategy search. |
| `DUPLICATE_RUN` | DSR-003 | Trial is an exact duplicate (same params, market, window) of another COMPLETE trial. |
| `AUDIT_EXCLUSION` | DSR-004 | Trial was excluded by designated audit authority with documented rationale. |

---

## 6. Appendix B: Error & Warning Code Reference

| Code | Type | Blocking? | Section | Description |
|---|---|---|---|---|
| `DATA_INTEGRITY_BLOCK` | ERROR | YES | 3.5.2 | Generic prefix for all blocking errors. Always followed by a colon and a specific sub-code. |
| `DATA_INTEGRITY_BLOCK: MISSING_HEADER_COMMENT` | ERROR | YES | 3.5.1 | Input file lacks the required `generated_at` header comment. |
| `DATA_INTEGRITY_BLOCK: INSUFFICIENT_TRIAL_COUNT` | ERROR | YES | 2.2.3 | `N_eff < 3.0`. Scorecard generation suppressed. |
| `DATA_INTEGRITY_BLOCK: COMPLETED_TRIAL_MISSING_SHARPE` | ERROR | YES | 3.5.2 B-002 | A COMPLETE trial with `counts_toward_dsr=TRUE` has `sharpe_ratio = NULL`. |
| `DATA_INTEGRITY_BLOCK: INVALID_LEDGER` | ERROR | YES | 3.5.2 B-004 | Ledger schema validation failed (malformed fields, invalid enums, etc.). |
| `DATA_INTEGRITY_BLOCK: CIRCULAR_PARENT_REFERENCE` | ERROR | YES | 3.5.2 B-005 | Circular `parent_trial_id` chain detected. |
| `INSUFFICIENT_OBSERVATIONS_ERROR` | ERROR | YES | 2.3.4 | T < 30. DSR computation suppressed due to insufficient return observations. |
| `Z_SCORE_SUPPRESSED` | WARNING | NO | 3.3.2 G-001 | `N_peers_with_metric(M) < 3`. Z-score not computed for metric M. |
| `DEGENERATE_PEER_SD` | WARNING | NO | 3.3.2 G-002 | `peer_sd(M) < 0.01`. Z-score computation suppressed due to degenerate standard deviation. |
| `LOW_N_WARNING` | WARNING | NO | 3.3.2 G-003 | `3 ≤ N_peers_with_metric(M) < 5`. Z-score computed but statistically weak. |
| `PERIOD_MISMATCH_WARNING` | WARNING | NO | 3.3.2 G-005 | Date span across contributing peers > 5 years for metric M. Cross-period comparability risk. |
| `STALE_LEDGER_WARNING` | WARNING | NO | 2.2.5 STL-001 | Most recent active trial entry_date > 30 days before generation date. |
| `ALL_METRICS_NA_PEER` | WARNING | NO | 3.5.3 | A peer row has all tracked metrics as NA. |
| `WEIGHT_OVERRIDE_DETECTED` | WARNING | NO | 2.2.2 | A ledger row has a `dsr_weight` inconsistent with the policy rules. |
| `DSR_NORMAL_ASSUMPTION` | WARNING | NO | 2.3.3 | Normal distribution was assumed for skewness/kurtosis in DSR computation. |
| `DSR_TRADE_BASED_T` | WARNING | NO | 2.3.4 | `trade_count` used as T instead of trading-day count. |
| `LOW_OBSERVATIONS_WARNING` | WARNING | NO | 2.3.3 | Fewer than 30 daily return observations for the SR* trial. |
| `OOS_REPLAY_TYPE_MISMATCH_WARNING` | WARNING | NO | 2.1.3 | `is_oos = TRUE` while `replay_type != OOS_HOLDOUT`. |
| `DSR_PEER_BENCHMARK_SUPPRESSED` | WARNING | NO | 2.3.2 | Peer-median Sharpe benchmark unavailable after N-count/source guards. |

**Error Severity Hierarchy:**

1. `DATA_INTEGRITY_BLOCK` — Scorecard generation halted. No output produced.
2. `INSUFFICIENT_OBSERVATIONS_ERROR` — DSR computation suppressed; rest of scorecard may render.
3. WARNING codes — Scorecard renders with flags displayed.

---

## 7. Appendix C: Revision History

| Version | Date | Author | Changes |
|---|---|---|---|
| v1.1 | 2026-06-26 | Codex | Added canonicalized `parameters_json` duplicate detection, `DSR_ZERO_BENCHMARK` / `DSR_PEER_BENCHMARK` split, peer-benchmark suppression warning, OOS replay-type warning, and formal `span_years(M)` definition. |
| v1.0 | 2026-06-26 | — | Initial DRAFT. All sections complete: System 1 (DSR Trial Ledger schema, calculation rules, DSR input parameters), System 2 (Peer Comparison Fallback Protocol, source hierarchy, per-metric fallback map, N-count guard logic, peer table schema, scorecard integration rules), Worked Examples, and Appendices. |

---

*End of Document — DSR Trial Ledger & Peer Comparison Fallback Protocol Technical Specification v1.0*
