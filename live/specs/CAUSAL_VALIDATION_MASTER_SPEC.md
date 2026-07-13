# Causal Validation & Backtesting Master Design Specification

**Version**: 1.0  
**Date**: 2026-06-26  
**Scope**: NQ/MNQ/ES/YM/MYM v2b prior-opposed ST+PMC strategy — engine correctness, statistical inference, false-discovery control, backtesting methodology, causal discovery.  
**Status**: Design & Audit Reference — no implementation until approved.

---

## Preamble

This document synthesises four primary sources into a unified design and audit guide:

1. **Löw, Maier-Paape & Platen (2015)** — *Correctness of Backtest Engines* (arXiv:1509.08248)  
2. **López de Prado, Lipton & Zoonekynd (2026)** — *Sharpe Ratio Inference: A New Standard* (JPM)  
3. **Harvey & Liu (2020)** — *False (and Missed) Discoveries in Financial Economics* (arXiv:2006.04269)  
4. **Joubert, Sestovic, Barziy, Distaso & López de Prado (2024)** — *Enhanced Backtesting for Practitioners / The Three Types of Backtests* (JPM)

Each section contains: the core idea, Python-oriented pseudocode or design, and an explicit audit checklist. A final section covers causal discovery methods and how to keep causal ordering clean in the potions stack.

---

## PART I — BACKTEST ENGINE CORRECTNESS
### Source: Löw, Maier-Paape & Platen (2015)

---

### 1.1 Core Framework

The paper's central insight: a backtest engine operating on OHLC candle data cannot know the intra-period price path. This creates **non-uniqueness** — for a given (open, close, high, low) candle and a given order setup, there may be multiple valid outcomes (entry and exit prices), depending on which intra-period price function (IPF) actually occurred. The engine must pick one outcome deterministically via a **decision mode**: `best_case`, `worst_case`, or `ignore`.

**Key definitions translated to Python types:**

```python
# ── Data structures ──────────────────────────────────────────────────────────

from dataclasses import dataclass
from enum import Enum
from typing import Optional

class DecisionMode(Enum):
    BEST_CASE  = "best_case"   # maximises P&L for the trader
    WORST_CASE = "worst_case"  # minimises P&L for the trader (conservative)
    IGNORE     = "ignore"      # trade is skipped when non-unique

@dataclass(frozen=True)
class Candle:
    open:  float
    close: float
    high:  float
    low:   float

    def __post_init__(self):
        # Invariant: low ≤ min(open,close) ≤ max(open,close) ≤ high
        assert self.low  <= min(self.open, self.close), "low > min(open,close)"
        assert max(self.open, self.close) <= self.high, "max(open,close) > high"
        assert self.low  <= self.high,                  "low > high"

@dataclass(frozen=True)
class OrderSetup:
    """
    Represents the order state entering a candle.
    levels: list of price levels, sorted ascending.
    position: -1 short, 0 flat, 1 long.
    entry_type: EnterLongStop | EnterShortStop | EnterLongLimit | EnterShortLimit
    exit_type:  StopLoss | ProfitTarget
    """
    levels:     tuple[float, ...]   # (stop_loss_level, entry_level) ascending
    position:   int                 # -1, 0, 1
    entry_type: str
    exit_type:  str

@dataclass
class BacktestResult:
    entry_price: Optional[float]   # None = no entry
    exit_price:  Optional[float]   # None = no exit
    mode_used:   DecisionMode
```

---

### 1.2 Model Candles — The Correctness Probe Set

The paper proves that correctness on a **finite** set of "model candles" implies correctness for all possible candles (under the stability-under-transformations assumption). The construction:

For a setup with m order levels L₁ < … < Lₘ:
1. Define 2m+1 representative price levels: l₀ < L₁ < l₂ < L₂ < … < Lₘ < l₂ₘ (where lₑᵥₑₙ are intermediate fill-in values).
2. Add 4 sub-levels between each consecutive pair of representative levels to catch "generic" candles (candle range does not span any order level).
3. Total model candle count: at most (2m+1+4m)⁴ — finite and exhaustive.

```python
# ── Model candle generator ────────────────────────────────────────────────────

import itertools
from typing import Iterator

def generate_representative_levels(order_levels: list[float],
                                   tick: float = 0.25) -> list[float]:
    """
    Build the extended level set {l₀, L₁, l₂, L₂, …, Lₘ, l₂ₘ}
    plus 4 sub-levels between each consecutive pair.
    tick: minimum price increment for the instrument.
    """
    levels = []
    sentinel_low  = order_levels[0] - 4 * tick
    sentinel_high = order_levels[-1] + 4 * tick
    all_anchors = [sentinel_low] + order_levels + [sentinel_high]

    for i, anchor in enumerate(all_anchors):
        levels.append(anchor)
        if i < len(all_anchors) - 1:
            next_anchor = all_anchors[i + 1]
            gap = (next_anchor - anchor) / 5.0
            for j in range(1, 5):          # 4 sub-levels
                levels.append(round(anchor + j * gap, 10))
    return sorted(set(levels))


def generate_model_candles(rep_levels: list[float]) -> Iterator[Candle]:
    """
    Enumerate every (open, close, high, low) combination over rep_levels
    that satisfies the OHLC constraint:
        low ≤ min(open, close) ≤ max(open, close) ≤ high
    """
    for o, c, h, l in itertools.product(rep_levels, repeat=4):
        if l <= min(o, c) and max(o, c) <= h and l <= h:
            yield Candle(open=o, close=c, high=h, low=l)
```

---

### 1.3 The Correctness Test Harness

```python
# ── Correctness test harness ──────────────────────────────────────────────────

class BacktestEngineUnderTest:
    """
    Adapter interface — wrap your actual engine here.
    Implement evaluate() to call potions' backtest logic on a single candle.
    """
    def evaluate(self, candle: Candle, setup: OrderSetup,
                 mode: DecisionMode) -> BacktestResult:
        raise NotImplementedError


class ReferenceEngine:
    """
    Ground-truth decision tree implementation derived from the paper's
    decision trees (Maier-Paape & Platen 2014, Section 2.2–2.5).
    Implements worst_case and best_case for:
      - EnterLongStop  + StopLoss
      - EnterShortStop + StopLoss
      - EnterLongLimit + ProfitTarget
      - EnterShortLimit + ProfitTarget
    Extend as needed for additional order combinations.
    """

    def evaluate(self, candle: Candle, setup: OrderSetup,
                 mode: DecisionMode) -> BacktestResult:
        """
        PSEUDOCODE — implement the actual decision trees from the paper.

        For EnterLongStop (entry fires if price rises to L_entry):
          entry triggered if candle.high >= L_entry
          IF entry triggered:
            exit (StopLoss) triggered if candle.low <= L_stop
            CASE: both triggered in same candle → non-unique
              WORST_CASE → entry=L_entry, exit=L_stop  (entered, hit stop)
              BEST_CASE  → entry=L_entry, exit=None     (entered, no stop hit)
            CASE: only entry triggered → entry=L_entry, exit=None
          ELSE:
            entry=None, exit=None

        For EnterShortStop (entry fires if price falls to L_entry):
          entry triggered if candle.low <= L_entry
          ... symmetric to above ...

        Return BacktestResult with mode_used set.
        """
        raise NotImplementedError("Implement decision tree per paper §2.2–2.5")


def run_correctness_suite(engine_under_test: BacktestEngineUnderTest,
                          reference_engine:  ReferenceEngine,
                          setup:             OrderSetup,
                          tick:              float = 0.25) -> dict:
    """
    Full correctness proof for one order setup.

    Returns:
        {
          "total_candles_tested": int,
          "failures": list[dict],   # each has candle, mode, expected, got
          "non_unique_candles": int,
          "passed": bool,
        }
    """
    rep_levels = generate_representative_levels(
        list(setup.levels), tick=tick
    )
    failures = []
    non_unique = 0
    total = 0

    for candle in generate_model_candles(rep_levels):
        for mode in [DecisionMode.WORST_CASE, DecisionMode.BEST_CASE]:
            total += 1
            expected = reference_engine.evaluate(candle, setup, mode)
            actual   = engine_under_test.evaluate(candle, setup, mode)

            if expected.entry_price != actual.entry_price or \
               expected.exit_price  != actual.exit_price:
                failures.append({
                    "candle":   candle,
                    "mode":     mode,
                    "expected": expected,
                    "got":      actual,
                })

            # Count candles where best≠worst (non-unique situations)
            best  = reference_engine.evaluate(candle, setup, DecisionMode.BEST_CASE)
            worst = reference_engine.evaluate(candle, setup, DecisionMode.WORST_CASE)
            if (best.entry_price != worst.entry_price or
                    best.exit_price != worst.exit_price):
                non_unique += 1

    return {
        "total_candles_tested": total,
        "failures":             failures,
        "non_unique_candles":   non_unique // 2,   # counted twice above
        "passed":               len(failures) == 0,
    }
```

---

### 1.4 Stability Under Transformations — Invariance Test

The paper requires that a correct engine is **stable under transformations**: applying any strictly monotone price scaling T to all levels and candle values must produce correspondingly scaled results.

```python
# ── Transformation invariance test ───────────────────────────────────────────

def test_transformation_stability(engine:    BacktestEngineUnderTest,
                                  candle:    Candle,
                                  setup:     OrderSetup,
                                  mode:      DecisionMode,
                                  transform: callable) -> bool:
    """
    T must be a strictly monotone increasing function R+ → R+.
    Examples: T(x) = 2x + 1,  T(x) = x * 1.5,  T(x) = x + 100

    Invariant: E(C(T∘f), mode) = T(E(C(f), mode))
    i.e., scaling prices scales results by the same factor.
    """
    original_result = engine.evaluate(candle, setup, mode)

    # Transform the candle
    t_candle = Candle(
        open  = transform(candle.open),
        close = transform(candle.close),
        high  = transform(candle.high),
        low   = transform(candle.low),
    )
    # Transform the setup levels
    t_setup = OrderSetup(
        levels     = tuple(transform(l) for l in setup.levels),
        position   = setup.position,
        entry_type = setup.entry_type,
        exit_type  = setup.exit_type,
    )

    transformed_result = engine.evaluate(t_candle, t_setup, mode)

    # The entry/exit prices of the transformed run must equal T(original prices)
    expected_entry = transform(original_result.entry_price) \
                     if original_result.entry_price is not None else None
    expected_exit  = transform(original_result.exit_price) \
                     if original_result.exit_price  is not None else None

    return (abs((transformed_result.entry_price or 0) - (expected_entry or 0)) < 1e-9 and
            abs((transformed_result.exit_price  or 0) - (expected_exit  or 0)) < 1e-9)
```

---

### 1.5 Mapping to Your System (v2b Prior-Opposed Gate)

The potions engine has additional complexity beyond basic entry/exit: the **arming gate** must fire before any fill. This adds a third level to the canonical two-level setup, making the model candle space larger but the framework identical.

```python
# ── v2b-specific setup registration ──────────────────────────────────────────

# Your order logic per campaign:
#   L1 = arming_gate_level     (opposing ST+PMC must print here first)
#   L2 = entry_level           (v2b entry stop)
#   L3 = stop_loss_level
#   L4 = tp1_level  (first profit target)
#   L5 = tp2_level  (second profit target)
#   L6 = runner_tp  (runner target)

# Ambiguous rows in your execution scrutiny report map to paper's non-unique candles:
#   same_1m_ambiguous  → entry and stop are both in [low, high] of same 1m bar
#   pre_arm_touch      → arming level is touched before entry in same bar

# Audit action:
#   For each ambiguous row, record which decision mode your engine used.
#   Tick reconstruction forces a unique IPF — it resolves non-uniqueness.
#   Until reconstruction is complete, flag these rows with tick_recon_status=PENDING
#   and exclude them from DSR weight (partial weight per WT-004).

V2B_SETUPS_TO_PROBE = [
    # (entry_type,    exit_type,  order_of_levels)
    ("EnterLongStop",  "StopLoss",    "arm < entry > stop"),
    ("EnterShortStop", "StopLoss",    "stop < entry < arm"),
    ("EnterLongStop",  "ProfitTarget","arm < entry < tp1"),
    ("EnterShortStop", "ProfitTarget","tp1 < entry < arm"),
    # Add OCO variants (TP1 + stop simultaneous) for each direction
]
```

---

### 1.6 Audit Checklist — Engine Correctness

```
ENGINE CORRECTNESS AUDIT
─────────────────────────────────────────────────────────────────────────────
[ ] 1. Reference engine implemented for all order types used by v2b
        (EnterLongStop, EnterShortStop, StopLoss, ProfitTarget, OCO)
[ ] 2. Model candle suite generated for each setup family above
[ ] 3. run_correctness_suite() passes (0 failures) for all setups
[ ] 4. Transformation stability confirmed for T(x)=2x+1 and T(x)=x+100
        on a representative sample (≥50 candles per setup)
[ ] 5. Same-1m ambiguous rows (45 NQ / 44 MNQ / 22 ES / 38 YM / 33 MYM)
        have their engine decision mode logged (best/worst/ignore)
[ ] 6. Pre-arm-touch rows (166 NQ / 167 MNQ / 128 ES / 122 YM / 123 MYM)
        have tick_recon_status set in DSR ledger
[ ] 7. Zero causal violations confirmed after any engine update
        (causal_violation_count field remains 0 in all ledger rows)
[ ] 8. Worst-case decision mode is the production mode
        (no best-case fills used in any non-simulated run)
[ ] 9. Gap-through stop rule verified: stop fills at max/min(stop, bar.open)
        — this is a non-trivial IPF assumption; confirm it matches paper §2.1
[ ] 10. OCO-collapse logic verified: when TP1 and stop are both in bar range,
         the engine's decision mode is documented and consistent
─────────────────────────────────────────────────────────────────────────────
```

---

## PART II — SHARPE RATIO INFERENCE: FIVE PITFALLS & MITIGATIONS
### Source: López de Prado, Lipton & Zoonekynd (2026)

---

### 2.1 Overview

The paper identifies five recurring pitfalls in Sharpe ratio inference that produce false discoveries even when the underlying engine is correct. Each maps to a concrete Python mitigation.

---

### Pitfall 1 — Reporting Point Estimates Without Statistical Significance

**Problem**: Reporting SR = 3.29 without a confidence interval or p-value tells the reader nothing about whether this is distinguishable from luck given the sample size.

**Mitigation**: Always report the PSR (Probabilistic Sharpe Ratio) and its p-value alongside the point estimate.

```python
# ── Pitfall 1 mitigation: PSR computation ────────────────────────────────────

import numpy as np
from scipy import stats

def compute_psr(returns:      np.ndarray,
                sr_benchmark: float = 0.0,
                annualise:    bool  = True,
                periods_per_year: int = 252) -> dict:
    """
    Probabilistic Sharpe Ratio: probability that true SR > sr_benchmark,
    corrected for skewness, kurtosis, and sample length.
    Bailey & López de Prado (2012).

    Returns dict with: SR_hat, PSR, p_value, se, n, skew, kurt
    """
    n    = len(returns)
    mu   = returns.mean()
    sig  = returns.std(ddof=1)

    if sig == 0:
        raise ValueError("Zero variance in returns — cannot compute SR.")

    sr_hat = mu / sig
    if annualise:
        sr_hat_ann = sr_hat * np.sqrt(periods_per_year)
    else:
        sr_hat_ann = sr_hat

    skew = stats.skew(returns)
    kurt = stats.kurtosis(returns, fisher=False)   # excess + 3

    # Standard error of SR under non-normality (Christie 2005 / López de Prado 2018)
    # Var(SR_hat) ≈ (1 + SR²/2 - SR*γ₃/2 + (γ₄-3)/4 * SR²) / n
    # where γ₃ = skewness, γ₄ = kurtosis (raw, not excess)
    var_sr = (1.0 + (sr_hat**2) / 2.0
              - sr_hat * skew / 2.0
              + (kurt - 3.0) / 4.0 * sr_hat**2) / n
    se = np.sqrt(max(var_sr, 1e-12))

    # PSR: z-score of (SR_hat - SR_benchmark) / SE
    z   = (sr_hat - sr_benchmark) / se
    psr = stats.norm.cdf(z)       # one-tailed: P(true SR > benchmark)
    p   = 1 - psr                 # p-value for H0: true SR ≤ benchmark

    return {
        "SR_hat":        round(sr_hat_ann, 4),
        "PSR":           round(psr, 6),
        "p_value":       round(p, 6),
        "SE":            round(se, 6),
        "n_obs":         n,
        "skewness":      round(skew, 4),
        "kurtosis_raw":  round(kurt, 4),
        "sr_benchmark":  sr_benchmark,
    }


# ── Reporting convention ──────────────────────────────────────────────────────
# NEVER report: "Sharpe = 3.29"
# ALWAYS report: "SR = 3.29 (PSR = 99.97%, p = 0.0003, n = 352 campaigns)"
# Store all four values in the DSR ledger row.
```

---

### Pitfall 2 — Biased Inference from IID Normal Assumption

**Problem**: Standard Sharpe inference assumes returns are IID Normal. Campaign-level P&L for a rule-based intraday system is neither: it has fat tails (gap-through events) and serial correlation (consecutive campaigns in same regime).

**Mitigation**: Use the non-normal, serially correlated variance estimator from the paper (López de Prado 2026, building on Newey-West). The PSR formula above (Pitfall 1) already handles non-normality through skew and kurtosis. Add autocorrelation correction for the Sharpe denominator.

```python
# ── Pitfall 2 mitigation: autocorrelation-corrected SR ───────────────────────

def compute_sr_autocorr_corrected(returns:   np.ndarray,
                                   max_lags:  int = 10) -> dict:
    """
    Corrects SR denominator for serial autocorrelation using a
    Newey-West-style HAC variance estimator.

    SR_AC = mean(r) / sqrt(HAC_variance(r))

    HAC variance: V_HAC = γ₀ + 2 * Σ_{k=1}^{max_lags} w_k * γ_k
    where γ_k = autocovariance at lag k
          w_k = Bartlett kernel weight = 1 - k/(max_lags+1)
    """
    n      = len(returns)
    mu     = returns.mean()
    # Autocovariance at each lag
    gamma0 = np.var(returns, ddof=1)
    hac_var = gamma0
    for k in range(1, max_lags + 1):
        w_k   = 1.0 - k / (max_lags + 1.0)   # Bartlett kernel
        gamma_k = np.cov(returns[k:], returns[:-k], ddof=1)[0, 1]
        hac_var += 2.0 * w_k * gamma_k

    hac_var = max(hac_var, 1e-12)
    sr_ac   = mu / np.sqrt(hac_var)

    return {
        "SR_unadjusted": round(mu / np.sqrt(gamma0), 4),
        "SR_AC_corrected": round(sr_ac, 4),
        "HAC_variance":  round(hac_var, 8),
        "max_lags_used": max_lags,
        "n_obs":         n,
    }


# ── Audit rule ────────────────────────────────────────────────────────────────
# If SR_AC_corrected differs from SR_unadjusted by > 10%,
# report both in the scorecard and flag the autocorrelation discrepancy.
# For your system: campaign P&L are not daily returns — check autocorrelation
# at lag 1 and lag 5 for each market separately.
```

---

### Pitfall 3 — Ignoring Test Power and Minimum Sample Length

**Problem**: A Sharpe of 3.29 from 352 campaigns sounds large, but the required sample length to distinguish it from zero at a given power depends on the SR variance. If the required minimum backtest length (MinBTL) is larger than your sample, you cannot claim statistical significance at the desired power.

**Mitigation**: Compute MinBTL before reporting. If N < MinBTL, increase power caveat in disclosure.

```python
# ── Pitfall 3 mitigation: Minimum Backtest Length ────────────────────────────

from scipy.special import ndtri   # inverse normal

def minimum_backtest_length(target_sr:     float,
                             alpha:         float = 0.05,
                             power:         float = 0.80,
                             skewness:      float = 0.0,
                             kurtosis_raw:  float = 3.0) -> int:
    """
    Minimum number of observations (campaigns / periods) needed to
    detect target_sr > 0 at significance alpha with given power.
    Based on Bailey & López de Prado (2012) MinBTL formula.

    MinBTL = (z_α + z_β)² * Var(SR) / SR²

    where Var(SR) ≈ 1 + SR²/2 - SR*γ₃/2 + (γ₄-3)/4 * SR²
    """
    z_alpha = ndtri(1 - alpha)
    z_beta  = ndtri(power)

    var_sr_per_n = (1.0
                    + target_sr**2 / 2.0
                    - target_sr * skewness / 2.0
                    + (kurtosis_raw - 3.0) / 4.0 * target_sr**2)

    minbtl = ((z_alpha + z_beta) / target_sr) ** 2 * var_sr_per_n
    return int(np.ceil(minbtl))


# ── Usage for your NQ common window ──────────────────────────────────────────
# minbtl = minimum_backtest_length(target_sr=3.29/sqrt(252), ...)
# Note: your "returns" are campaign-level P&L, not daily.
# Adjust periods_per_year accordingly (≈ 352 campaigns / 5.0 years ≈ 70/yr).
# Report: "N=352 campaigns vs MinBTL=XX — [sufficient/insufficient]"
```

---

### Pitfall 4 — Misinterpreting p-values as P(null is true)

**Problem**: A p-value of 0.0003 does NOT mean "there is a 0.03% chance the strategy has no edge." It means "if the strategy had no edge, we would observe a result this extreme or more in 0.03% of samples." Misinterpretation leads to overconfidence.

**Mitigation**: This is a disclosure and documentation issue, not a code issue. Enforce the correct language throughout.

```python
# ── Pitfall 4 mitigation: enforced disclosure strings ────────────────────────

def format_pvalue_disclosure(p_value: float, metric_name: str = "SR") -> str:
    """
    Returns a disclosure string that cannot be misinterpreted.
    Use this function for ALL p-value reporting in scorecard outputs.
    """
    return (
        f"p = {p_value:.4f} — under the null hypothesis of no edge, "
        f"the probability of observing a {metric_name} this extreme "
        f"or greater by chance alone is {p_value*100:.2f}%. "
        f"This is NOT the probability that the strategy has no edge."
    )

# ── Code audit rule ───────────────────────────────────────────────────────────
# Grep all output templates and markdown generators for:
#   "probability that" — flag any that claim p = P(H0 true)
#   "confidence that"  — same issue
#   "proven"           — remove; replace with "consistent with" or "supportive"
# These strings must not appear in any investor-facing document.

BANNED_PVALUE_PHRASES = [
    "probability that the strategy works",
    "probability that the edge is real",
    "99% confident the strategy is profitable",
    "proven by the p-value",
    "statistically proven",
]
```

---

### Pitfall 5 — Failing to Correct for Multiple Testing and Selection Effects

**Problem**: Running N parameter variants, N market/sizing combinations, or N null families and then reporting the best result inflates the Type I error rate. With N=53 DSR rows, the expected maximum Sharpe by chance alone is non-trivial.

**Mitigation**: The DSR is the primary tool. Additionally, apply the Deflated Sharpe Ratio and optionally the haircut Sharpe for the number of effective trials.

```python
# ── Pitfall 5 mitigation: Deflated Sharpe Ratio ──────────────────────────────

from scipy.stats import norm

def deflated_sharpe_ratio(sr_hat:       float,
                           n_obs:        int,
                           n_trials:     float,    # N_eff from DSR ledger
                           skewness:     float = 0.0,
                           kurtosis_raw: float = 3.0,
                           sr_benchmark: float = 0.0) -> dict:
    """
    DSR: probability that the observed SR is a true discovery after
    correcting for selection bias from N_eff trials.

    Steps:
    1. Compute expected maximum SR under null across N_eff IID trials.
    2. Deflate: SR* = E[max SR | N_eff trials, SR_true=0]
    3. Compute PSR vs. deflated benchmark SR*.

    E[max SR_N] ≈ (1 - γ) * Φ⁻¹(1 - 1/N) + γ * Φ⁻¹(1 - 1/(N*e))
    where γ = Euler-Mascheroni constant ≈ 0.5772
    """
    EULER_MASCHERONI = 0.5772156649

    if n_trials < 1:
        raise ValueError("n_trials must be >= 1")

    # Expected maximum Sharpe under null (no edge) across n_trials IID trials
    z1  = norm.ppf(1 - 1.0 / n_trials) if n_trials > 1 else 0.0
    z2  = norm.ppf(1 - 1.0 / (n_trials * np.e)) if n_trials > 1 else 0.0
    sr_star = ((1 - EULER_MASCHERONI) * z1 + EULER_MASCHERONI * z2)

    # Variance of SR estimate adjusted for non-normality
    var_sr = (1.0
              + sr_hat**2 / 2.0
              - sr_hat * skewness / 2.0
              + (kurtosis_raw - 3.0) / 4.0 * sr_hat**2) / n_obs
    se = np.sqrt(max(var_sr, 1e-12))

    # DSR = PSR vs. deflated benchmark
    z_dsr = (sr_hat - sr_star) / se
    dsr   = norm.cdf(z_dsr)

    return {
        "SR_hat":       round(sr_hat, 4),
        "SR_star":      round(sr_star, 4),    # deflated benchmark
        "DSR":          round(dsr, 6),
        "p_dsr":        round(1 - dsr, 6),
        "N_eff_trials": round(n_trials, 2),
        "n_obs":        n_obs,
    }


def haircut_sharpe(sr_hat:    float,
                   n_trials:  int,
                   n_obs:     int,
                   method:    str = "BHY") -> dict:
    """
    Sharpe ratio haircut for multiple testing.
    Converts SR → t-stat → adjusted p-value → adjusted t-stat → haircut SR.

    method: "bonferroni" | "holm" | "BHY" (Benjamini-Hochberg-Yekutieli)

    PSEUDOCODE — full implementation requires distributional assumptions
    about the n_trials t-statistics (model from Harvey, Liu & Zhu 2016).
    """
    import math

    # Step 1: SR → t-stat
    t_stat = sr_hat * math.sqrt(n_obs)

    # Step 2: single-test p-value
    p_single = 1 - norm.cdf(t_stat)

    # Step 3: multiple testing adjustment (illustrative — Bonferroni)
    if method == "bonferroni":
        p_adjusted = min(p_single * n_trials, 1.0)
    elif method == "holm":
        # Holm: p_adjusted = p_single * (n_trials - rank + 1)
        # For the maximum SR (rank=1): p_adjusted = p_single * n_trials
        p_adjusted = min(p_single * n_trials, 1.0)
    else:   # BHY — less conservative, controls FDR not FWER
        # Simplified: p_adjusted ≈ p_single * n_trials / rank
        p_adjusted = min(p_single * n_trials, 1.0)

    # Step 4: adjusted p → adjusted t-stat → haircut SR
    if p_adjusted >= 1.0:
        t_adjusted = 0.0
    else:
        t_adjusted = norm.ppf(1 - p_adjusted)

    sr_adjusted = t_adjusted / math.sqrt(n_obs)
    haircut_pct = (1 - sr_adjusted / sr_hat) * 100 if sr_hat > 0 else 100.0

    return {
        "SR_reported":  round(sr_hat, 4),
        "SR_haircut":   round(sr_adjusted, 4),
        "haircut_pct":  round(haircut_pct, 1),
        "t_original":   round(t_stat, 4),
        "t_adjusted":   round(t_adjusted, 4),
        "p_single":     round(p_single, 6),
        "p_adjusted":   round(p_adjusted, 6),
        "n_trials":     n_trials,
        "method":       method,
    }
```

---

### 2.2 Audit Checklist — Sharpe Inference

```
SHARPE INFERENCE AUDIT
─────────────────────────────────────────────────────────────────────────────
[ ] P1. PSR reported alongside every SR point estimate in scorecard output.
        p-value and SE included. No SR reported without significance context.
[ ] P2. Autocorrelation-corrected SR computed for each market.
        If |SR_AC - SR_naive| > 10%, both reported with explanation.
        Campaign return autocorrelation at lag 1 and 5 checked and logged.
[ ] P3. MinBTL computed for each market at α=0.05, power=0.80.
        n_campaigns vs MinBTL table included in SCORECARD_REPORT.md.
[ ] P4. All scorecard templates scanned for banned p-value phrases (see list).
        Disclosure strings use format_pvalue_disclosure() or equivalent.
[ ] P5. DSR computed with N_eff=53 from ledger. SR* (deflated benchmark)
        reported alongside DSR value. Haircut SR computed with BHY method
        for investor-facing pitch, reported as a conservative bound.
        N_eff re-audited after each new ledger entry (§DSR ledger §1.6).
─────────────────────────────────────────────────────────────────────────────
```

---

## PART III — FALSE DISCOVERY CONTROL: DOUBLE-BOOTSTRAP & PERMUTATION DESIGN
### Source: Harvey & Liu (2020)

---

### 3.1 Core Idea

Harvey & Liu propose calibrating *both* Type I (false discovery) and Type II (missed discovery) errors simultaneously, not just controlling FDR at a threshold. The key tool is a **double-bootstrap**: one bootstrap to simulate the distribution of test statistics under the null, a second to calibrate the hurdle at a desired FDR while also tracking power (missed discoveries).

For your system, the randomized delayed-arming gate replay already constructs the empirical null distribution directly from the data — which is the *stronger* approach because it makes no parametric assumption about the distribution of t-statistics across strategies. The design notes below show how to integrate the Harvey & Liu ideas as formal Type I/II calibration on top of that empirical null.

---

### 3.2 Design: Empirical Null + Double-Bootstrap Integration

```python
# ── Type I / Type II calibration on empirical null ───────────────────────────

import numpy as np
from dataclasses import dataclass
from typing import Callable

@dataclass
class GateReplayResult:
    """
    Single result from v2b_prior_opposed_random_gate_replay.
    Populated for BOTH real run and each null-family run.
    """
    seed:          int
    null_family:   str      # "real" | "unconstrained" | "stratified" | "shuffled_labels"
    net_pnl:       float
    sharpe:        float
    sortino:       float
    max_dd:        float
    win_rate:      float
    counts_toward_permutation_test: bool


def compute_empirical_pvalue(real_result:  GateReplayResult,
                              null_results: list[GateReplayResult],
                              metric:       str = "sharpe") -> dict:
    """
    One-tailed empirical p-value: fraction of null runs ≥ real result.

    This IS your primary test — do not replace with a parametric test.
    """
    null_vals  = [getattr(r, metric) for r in null_results
                  if r.counts_toward_permutation_test]
    real_val   = getattr(real_result, metric)
    n_null     = len(null_vals)

    if n_null == 0:
        raise ValueError("No null results with counts_toward_permutation_test=True")

    p_empirical = np.mean(np.array(null_vals) >= real_val)
    percentile  = np.mean(np.array(null_vals) < real_val) * 100

    return {
        "metric":       metric,
        "real_value":   real_val,
        "null_n":       n_null,
        "null_mean":    round(np.mean(null_vals), 4),
        "null_p95":     round(np.percentile(null_vals, 95), 4),
        "null_p99":     round(np.percentile(null_vals, 99), 4),
        "p_empirical":  round(p_empirical, 4),
        "percentile":   round(percentile, 2),
        "passed_p05":   p_empirical <= 0.05,
    }


def double_bootstrap_fdr_calibration(
        null_results:   list[GateReplayResult],
        real_result:    GateReplayResult,
        target_fdr:     float = 0.05,
        n_bootstrap:    int   = 1000,
        metric:         str   = "sharpe") -> dict:
    """
    Harvey & Liu double-bootstrap FDR calibration.

    Outer bootstrap: resample null_results with replacement → simulate
      what p-values look like under repeated experiments.
    Inner bootstrap: derive t-hurdle that achieves target_fdr.

    Returns the t-hurdle (metric threshold) and associated Type II error estimate.

    NOTE: For a rule-based deterministic system, this supplements (not replaces)
    the empirical p-value. Use it to communicate the hurdle to allocators who
    expect FDR-controlled results.
    """
    null_vals = np.array([getattr(r, metric) for r in null_results
                          if r.counts_toward_permutation_test])
    real_val  = getattr(real_result, metric)
    rng = np.random.default_rng(seed=42)

    # Outer bootstrap: simulate p-values across repeated experiments
    bootstrap_pvalues = []
    for _ in range(n_bootstrap):
        # Resample null distribution with replacement
        resampled_null = rng.choice(null_vals, size=len(null_vals), replace=True)
        p_boot = np.mean(resampled_null >= real_val)
        bootstrap_pvalues.append(p_boot)

    bootstrap_pvalues = np.array(bootstrap_pvalues)

    # The hurdle: choose threshold so that E[FDR] ≤ target_fdr
    # Simple calibration: hurdle is the target_fdr quantile of the null distribution
    hurdle_value = np.percentile(null_vals, (1 - target_fdr) * 100)

    # Type II error estimate: fraction of "true" signals (real_val)
    # that fall below the hurdle
    type2_error = float(real_val < hurdle_value)

    # Power estimate: 1 - Type II error
    power = 1.0 - type2_error

    return {
        "metric":           metric,
        "target_fdr":       target_fdr,
        "hurdle_value":     round(hurdle_value, 4),
        "real_value":       real_val,
        "real_clears_hurdle": real_val >= hurdle_value,
        "type1_error":      target_fdr,
        "type2_error_est":  round(type2_error, 4),
        "power_est":        round(power, 4),
        "bootstrap_p_mean": round(bootstrap_pvalues.mean(), 4),
        "bootstrap_p_p05":  round(np.percentile(bootstrap_pvalues, 5), 4),
        "n_bootstrap":      n_bootstrap,
        "n_null":           len(null_vals),
    }
```

---

### 3.3 Null Family Architecture — Design Rules

```python
# ── Null family registry ──────────────────────────────────────────────────────

NULL_FAMILY_REGISTRY = {
    "UNCONSTRAINED_EVENT_COUNT": {
        "description": "Random gate events sampled uniformly from all-day NQ universe. "
                       "Event count matched to real gate-event count (NOT filled-campaign count).",
        "is_true_null": True,
        "counts_toward_permutation_test": True,
        "primary_match_quantity": "gate_event_count",  # not filled_campaign_count
    },
    "STRATIFIED_BY_YEAR_SIDE_TIME_BUCKET_OR_WIDTH": {
        "description": "Same as UNCONSTRAINED but sampled within strata to preserve "
                       "year, direction (long/short), time-bucket, and OR-width quartile distributions.",
        "is_true_null": True,
        "counts_toward_permutation_test": True,
        "stratum_definition": {
            "or_width_quartile_breakpoints": "FREEZE before first run, from NQ universe only",
            "time_buckets": ["09:30-10:30", "10:30-12:30", "12:30-14:00", "14:00-15:55"],
            "year_bins":    "calendar year of gate event",
            "side":         "long | short",
        },
    },
    "SHUFFLED_SIDE_LABELS": {
        "description": "Strongest null: shuffle the direction (long/short) labels of "
                       "real ST+PMC signals while preserving timing and count. "
                       "Destroys any edge from the opposing-campaign mechanic.",
        "is_true_null": True,
        "counts_toward_permutation_test": True,
    },
    "CALENDAR_BENCHMARK": {
        "description": "Fixed calendar entries (e.g., first hour of each day). NOT a true null "
                       "— these have non-zero expected SR under market conditions.",
        "is_true_null": False,
        "counts_toward_permutation_test": False,
    },
    "SIMPLE_SIGNAL_BENCHMARK": {
        "description": "A single-indicator entry rule without the opposing gate. NOT a true null.",
        "is_true_null": False,
        "counts_toward_permutation_test": False,
    },
    "FILL_COUNT_MATCHED_DIAGNOSTIC": {
        "description": "Matched to filled-campaign count (not gate-event count). Secondary diagnostic only. "
                       "Reported separately — never combined with true null distribution.",
        "is_true_null": False,
        "counts_toward_permutation_test": False,
    },
}

# ── Anti-leakage enforcement ──────────────────────────────────────────────────
# CRITICAL: The null generator must not read outcome fields (net_pnl, win_rate, etc.)
# from the results before seeds are fixed. Enforce this at the module boundary:

class NullReplayGuard:
    """
    Context manager that enforces anti-leakage protocol.
    Seeds must be fixed before entering this context.
    Within this context, reading outcome fields from live results raises an error.
    """
    def __init__(self, seeds: list[int]):
        self._seeds = tuple(sorted(seeds))
        self._seeds_frozen_hash = hash(self._seeds)

    def __enter__(self):
        # Log seed hash to DSR ledger before any run
        print(f"[GUARD] Seeds frozen: hash={self._seeds_frozen_hash}, n={len(self._seeds)}")
        return self

    def __exit__(self, *args):
        print(f"[GUARD] Null replay complete. Seeds: {self._seeds_frozen_hash}")

    @staticmethod
    def assert_no_outcome_read(field_name: str):
        OUTCOME_FIELDS = {"net_pnl", "sharpe", "sortino", "win_rate",
                          "max_dd", "calmar", "profit_factor"}
        if field_name in OUTCOME_FIELDS:
            raise PermissionError(
                f"[GUARD] Reading outcome field '{field_name}' before seeds are fixed "
                f"violates anti-leakage protocol."
            )
```

---

### 3.4 Audit Checklist — False Discovery Control

```
FALSE DISCOVERY CONTROL AUDIT
─────────────────────────────────────────────────────────────────────────────
[ ] FD1. Seeds for all null runs are fixed and logged to DSR ledger BEFORE
          any outcome fields are read. seed_hash logged per run.
[ ] FD2. Null family labels are set in the ledger row BEFORE the run executes.
          No relabelling after observing results.
[ ] FD3. counts_toward_permutation_test=FALSE for CALENDAR_BENCHMARK,
          SIMPLE_SIGNAL_BENCHMARK, FILL_COUNT_MATCHED_DIAGNOSTIC.
          These are never mixed into the true null distribution.
[ ] FD4. Primary match quantity is gate_event_count, not filled_campaign_count.
          Pre-run assertion: |gate_events - filled_campaigns| checked and logged.
[ ] FD5. OR-width quartile breakpoints and time-bucket definitions frozen
          before first stratified run and stored in the null-run CSV metadata.
[ ] FD6. Pass threshold: real result ≥ 95th percentile null on BOTH net_pnl
          AND sharpe/sortino, for BOTH unconstrained AND stratified families.
          AND p_empirical ≤ 0.05. AND no hidden increase in stress_dd vs real run.
[ ] FD7. double_bootstrap_fdr_calibration() run after 2000-seed completion.
          Results reported as FDR-controlled hurdle alongside empirical p-value.
[ ] FD8. Type II error estimate documented for each market.
          "Strategy passes but you missed 0% of true signals" type framing
          used in allocator materials.
[ ] FD9. All null results logged to DSR ledger with counts_toward_dsr=FALSE.
[ ] FD10. NullReplayGuard (or equivalent) active during all null runs.
─────────────────────────────────────────────────────────────────────────────
```

---

## PART IV — THREE TYPES OF BACKTESTS: DESIGN SPEC & AUDIT
### Source: Joubert, Sestovic, Barziy, Distaso & López de Prado (2024)

---

### 4.1 The Three Types and Their Roles in Your System

| Type | Method | Role in v2b System | Status |
|---|---|---|---|
| **Walk-Forward** | Test on held-out future data sequentially | Common-window vs long-history split; OOS holdout post-2026-03-06 | Partial — long-history acts as pseudo-WF |
| **Resampling** | Resample historical paths (bootstrap, CPCV) | Block-bootstrap stress tests; CPCV for Sharpe distribution | Missing — listed in IMPLEMENTATION_STATUS.md |
| **Monte Carlo** | Simulate new paths from a fitted DGP | Parametric stress scenarios; gap-through frequency calibration | Missing |

**Key principle from Joubert et al.**: Walk-forward is necessary but not sufficient. The strategy must also survive resampling (to rule out path-specific luck) and be grounded by a causal explanation for *why* it works (causal graph before backtesting — not after).

---

### 4.2 Walk-Forward Design

```python
# ── Walk-Forward implementation pseudocode ────────────────────────────────────

def walk_forward_split(all_campaigns:  list,
                       n_splits:       int = 5,
                       train_fraction: float = 0.7) -> list[tuple]:
    """
    Split the campaign timeline into n_splits non-overlapping folds.
    Each fold: [train_start, train_end] → [test_start, test_end]
    No lookahead: test is always strictly after train.

    Returns list of (train_campaigns, test_campaigns) tuples.
    """
    n = len(all_campaigns)
    fold_size = n // n_splits
    splits = []
    for i in range(n_splits):
        test_start = i * fold_size
        test_end   = test_start + fold_size if i < n_splits - 1 else n
        train      = all_campaigns[:test_start]       # expanding window
        test       = all_campaigns[test_start:test_end]
        if len(train) == 0:
            continue   # skip first fold if no training data
        splits.append((train, test))
    return splits


def walk_forward_sharpe_distribution(splits: list[tuple]) -> dict:
    """
    For each split, compute IS and OOS Sharpe.
    Return distribution of OOS Sharpes and IS/OOS degradation ratio.

    Degradation ratio > 1 (IS >> OOS) is the primary overfitting signal.
    """
    is_sharpes  = []
    oos_sharpes = []

    for train_campaigns, test_campaigns in splits:
        is_pnl  = [c.net_pnl for c in train_campaigns]
        oos_pnl = [c.net_pnl for c in test_campaigns]

        is_sr  = compute_psr(np.array(is_pnl))["SR_hat"]  if is_pnl  else None
        oos_sr = compute_psr(np.array(oos_pnl))["SR_hat"] if oos_pnl else None

        if is_sr is not None:  is_sharpes.append(is_sr)
        if oos_sr is not None: oos_sharpes.append(oos_sr)

    return {
        "IS_sharpes_by_fold":    is_sharpes,
        "OOS_sharpes_by_fold":   oos_sharpes,
        "IS_mean":               np.mean(is_sharpes)  if is_sharpes  else None,
        "OOS_mean":              np.mean(oos_sharpes) if oos_sharpes else None,
        "degradation_ratio":     (np.mean(is_sharpes) / np.mean(oos_sharpes)
                                  if oos_sharpes and np.mean(oos_sharpes) != 0 else None),
    }
```

---

### 4.3 Resampling (CPCV / Block-Bootstrap) Design

```python
# ── Combinatorial Purged Cross-Validation pseudocode ─────────────────────────

def combinatorial_purged_cv(campaigns:   list,
                             n_splits:    int = 10,
                             n_test:      int = 2,
                             embargo_n:   int = 5) -> list[dict]:
    """
    CPCV (López de Prado 2018):
    1. Divide campaigns into n_splits groups.
    2. Enumerate C(n_splits, n_test) combinations of test groups.
    3. For each combination, train on remaining groups (minus embargo buffer).
    4. Embargo: exclude embargo_n campaigns adjacent to test period from training.

    Returns a list of {train_idx, test_idx, embargo_removed} dicts.

    Key output: distribution of OOS Sharpe ratios (one per combination).
    PBO = fraction of combinations where selected strategy ranks below median OOS.
    """
    import itertools

    n = len(campaigns)
    group_size = n // n_splits
    groups = [list(range(i * group_size,
                         (i + 1) * group_size if i < n_splits - 1 else n))
              for i in range(n_splits)]

    result_sets = []
    for test_groups in itertools.combinations(range(n_splits), n_test):
        test_idx  = [i for g in test_groups for i in groups[g]]
        train_idx = [i for g in range(n_splits) if g not in test_groups
                     for i in groups[g]]

        # Embargo: remove training indices within embargo_n of any test index
        test_set   = set(test_idx)
        embargoed  = set()
        for ti in test_idx:
            for offset in range(-embargo_n, embargo_n + 1):
                embargoed.add(ti + offset)
        train_idx_clean = [i for i in train_idx if i not in embargoed]

        result_sets.append({
            "test_idx":        test_idx,
            "train_idx":       train_idx_clean,
            "embargo_removed": len(train_idx) - len(train_idx_clean),
        })
    return result_sets


def block_bootstrap_sharpe(pnl_series:  np.ndarray,
                            n_boot:      int  = 1000,
                            block_size:  int  = 20,
                            seed:        int  = 42) -> dict:
    """
    Block bootstrap preserving serial dependence structure.
    Each bootstrap sample is constructed from randomly drawn
    consecutive blocks of length block_size.

    Returns bootstrap distribution of annualised Sharpe.
    """
    rng = np.random.default_rng(seed)
    n   = len(pnl_series)
    boot_sharpes = []

    for _ in range(n_boot):
        # Draw random block starts with replacement
        n_blocks   = int(np.ceil(n / block_size))
        block_starts = rng.integers(0, n - block_size + 1, size=n_blocks)
        boot_sample  = np.concatenate([
            pnl_series[s:s + block_size] for s in block_starts
        ])[:n]   # trim to original length

        mu   = boot_sample.mean()
        sig  = boot_sample.std(ddof=1)
        boot_sharpes.append(mu / sig if sig > 0 else 0.0)

    boot_arr = np.array(boot_sharpes)
    return {
        "sharpe_mean":      round(boot_arr.mean(), 4),
        "sharpe_p05":       round(np.percentile(boot_arr, 5), 4),
        "sharpe_p25":       round(np.percentile(boot_arr, 25), 4),
        "sharpe_p50":       round(np.percentile(boot_arr, 50), 4),
        "sharpe_p95":       round(np.percentile(boot_arr, 95), 4),
        "n_bootstrap":      n_boot,
        "block_size":       block_size,
        "pct_positive_sr":  round(np.mean(boot_arr > 0) * 100, 1),
    }
```

---

### 4.4 Monte Carlo Design (Parametric Stress)

```python
# ── Parametric Monte Carlo stress pseudocode ─────────────────────────────────

def fit_campaign_dgp(pnl_series: np.ndarray) -> dict:
    """
    Fit a simple DGP to campaign P&L for Monte Carlo simulation.
    Returns parameters for a fat-tailed distribution.

    Use Student-t for fat tails (captures gap-through events).
    Estimate autocorrelation at lag 1 for sequential dependence.
    """
    from scipy.stats import t as t_dist

    # Fit Student-t via MLE
    df, loc, scale = t_dist.fit(pnl_series)

    # Autocorrelation at lag 1
    ac1 = np.corrcoef(pnl_series[:-1], pnl_series[1:])[0, 1]

    return {
        "distribution": "student_t",
        "df":           round(df, 2),        # degrees of freedom (fat tails ↓ df)
        "loc":          round(loc, 2),
        "scale":        round(scale, 2),
        "ac1":          round(ac1, 4),       # lag-1 autocorrelation
    }


def monte_carlo_stress_paths(dgp_params:    dict,
                              n_campaigns:   int  = 352,
                              n_paths:       int  = 10_000,
                              seed:          int  = 42) -> dict:
    """
    Simulate n_paths of n_campaigns campaign P&L from fitted DGP.
    Compute Sharpe, MaxDD, and Net/StressDD for each path.

    Scenarios to run:
      1. Baseline: fitted params (same regime)
      2. Fat-tail shock: df reduced by 50% (heavier tails)
      3. Mean-shift: loc reduced by 50% (regime deterioration)
      4. Gap-through: inject 5% of paths with a single extreme loss
    """
    from scipy.stats import t as t_dist
    rng = np.random.default_rng(seed)

    results = {"baseline": [], "fat_tail": [], "mean_shift": [], "gap_shock": []}

    for scenario, params in [
        ("baseline",   {"df": dgp_params["df"], "loc": dgp_params["loc"],
                        "scale": dgp_params["scale"]}),
        ("fat_tail",   {"df": dgp_params["df"] * 0.5, "loc": dgp_params["loc"],
                        "scale": dgp_params["scale"]}),
        ("mean_shift", {"df": dgp_params["df"], "loc": dgp_params["loc"] * 0.5,
                        "scale": dgp_params["scale"]}),
    ]:
        for _ in range(n_paths):
            path = t_dist.rvs(
                df=params["df"], loc=params["loc"], scale=params["scale"],
                size=n_campaigns, random_state=rng
            )
            # Inject gap-through shock in gap_shock scenario
            if scenario == "gap_shock" and rng.random() < 0.05:
                path[rng.integers(0, n_campaigns)] -= 5 * abs(params["loc"])

            mu   = path.mean()
            sig  = path.std(ddof=1)
            sr   = mu / sig if sig > 0 else 0.0
            # Max drawdown (simplified — intrabar not available in Monte Carlo)
            cum_pnl = np.cumsum(path)
            mdd  = (cum_pnl - np.maximum.accumulate(cum_pnl)).min()
            results[scenario].append({"sharpe": sr, "max_dd": mdd,
                                      "net_pnl": path.sum()})

    return {
        k: {
            "sharpe_p05":  round(np.percentile([r["sharpe"] for r in v], 5), 4),
            "sharpe_p50":  round(np.percentile([r["sharpe"] for r in v], 50), 4),
            "max_dd_p95":  round(np.percentile([r["max_dd"]  for r in v], 95), 4),
            "pct_positive_net": round(np.mean([r["net_pnl"] > 0 for r in v]) * 100, 1),
        }
        for k, v in results.items() if v
    }
```

---

### 4.5 Selection Bias Under Multiple Testing — Sharpe Haircut Schedule

Per Joubert et al. and Harvey & Liu, the reported Sharpe should be presented with a haircut schedule as a function of the effective number of trials. Key finding: haircut is nonlinear — high SRs receive modest haircuts; low SRs receive heavy ones.

```python
# ── Sharpe haircut schedule table generator ───────────────────────────────────

def generate_haircut_schedule(sr_hat:    float,
                               n_obs:     int,
                               trial_range: list[int] = None) -> list[dict]:
    """
    For a given observed SR and sample size, tabulate the haircut SR
    across a range of assumed prior trial counts.
    Use Bonferroni (conservative) and BHY (FDR-controlling) side by side.
    """
    if trial_range is None:
        trial_range = [1, 5, 10, 20, 53, 100, 200]

    rows = []
    for n_trials in trial_range:
        bonf = haircut_sharpe(sr_hat, n_trials, n_obs, method="bonferroni")
        bhy  = haircut_sharpe(sr_hat, n_trials, n_obs, method="BHY")
        rows.append({
            "n_trials_assumed":    n_trials,
            "SR_bonferroni":       bonf["SR_haircut"],
            "haircut_pct_bonf":    bonf["haircut_pct"],
            "SR_BHY":              bhy["SR_haircut"],
            "haircut_pct_BHY":     bhy["haircut_pct"],
        })
    return rows


# ── Causal graph requirement (Joubert et al. 2024) ────────────────────────────
# Before ANY backtesting run, document:
#   1. Why does the opposing-campaign mechanic create an edge?
#      (causal chain: prior session ST+PMC → regime bias → v2b arm → v2b fill → edge)
#   2. What market condition makes the edge disappear?
#      (e.g., low-OR-width days, Q4 regime, correlated stops cluster)
#   3. Which variables are the confounders?
#      (time-of-day, calendar regime, OR width)
# This causal graph is stored in: live/specs/CAUSAL_GRAPH.md
# It must predate every new parameter sweep in the DSR ledger.
```

---

### 4.6 Audit Checklist — Three Types of Backtests

```
BACKTESTING METHODOLOGY AUDIT
─────────────────────────────────────────────────────────────────────────────
[ ] WF1. Walk-forward split defined: long-history (2010-2021) as pseudo-train,
          common-window (2021-2026) as pseudo-test. No parameter re-optimisation
          on common window after this split is established.
[ ] WF2. Year-by-year equity table included in scorecard (not just aggregate SR).
          2022 drawdown and recovery annotated with market context.
[ ] WF3. IS/OOS degradation ratio computed and logged. If ratio > 2.0, flag.
[ ] RS1. Block-bootstrap Sharpe distribution computed (n=1000, block=20 campaigns).
          p05 Sharpe reported as conservative bound in scorecard.
[ ] RS2. CPCV run with n_splits=10, n_test=2, embargo=5.
          PBO reported. If PBO > 20%, investigate before live allocation.
[ ] RS3. Recovery-time distribution computed across bootstrap paths.
          Median recovery time and p95 recovery time logged.
[ ] MC1. Student-t DGP fitted to NQ campaign P&L. df and ac1 logged.
[ ] MC2. Four scenario paths run: baseline, fat_tail, mean_shift, gap_shock.
          Results tabulated in SCORECARD_REPORT.md.
[ ] MC3. Gap-through cost sensitivity: NQ $116k+ edge erosion scenario
          explicitly modelled. P&L distribution under 100% gap-through exposure shown.
[ ] ST1. Causal graph documented in live/specs/CAUSAL_GRAPH.md before next
          parameter sweep. Graph must predate DSR ledger entry for that sweep.
[ ] ST2. Haircut Sharpe schedule (n_trials = 1, 5, 10, 20, 53, 100) generated
          and included in investor-facing materials.
[ ] ST3. "Asymptotically, the distribution of SR_hat is N(0, Var(SR))" —
          confirm this approximation is valid for n_campaigns ≥ 352.
          Log the normality check (Jarque-Bera or equivalent) on the P&L series.
─────────────────────────────────────────────────────────────────────────────
```

---

## PART V — CAUSAL DISCOVERY: MARKET RELATIONSHIPS & CAUSAL ORDERING
### Sources: Multiple (Tang 2024, Polakow et al. 2024, Oliveira et al. 2024, Kolonin et al. 2022)

---

### 5.1 Two Meanings of "Causality" — Keep Them Separate

| Layer | Meaning | Your system | Tools |
|---|---|---|---|
| **Engine causality** | Temporal ordering — no action on future data | v2b gate fires only after prior session signal; causal_violation_count = 0 | Part I of this spec |
| **Statistical causality** | Do market signals have genuine predictive content, not spurious correlation? | Does ST+PMC in the opposing direction actually cause a favourable price regime for v2b? | Granger test, PCMCI, Transfer Entropy |

Both layers must be clean. Engine causality is a correctness property (Part I). Statistical causality is an evidence property — it tells you whether the mechanism is real or coincidental.

---

### 5.2 Granger Causality — Testing the Opposing-Campaign Mechanism

```python
# ── Granger causality: does prior-session opposing signal predict v2b outcome? ──

import pandas as pd
from statsmodels.tsa.stattools import grangercausalitytests

def test_granger_causality(
        campaign_df:    pd.DataFrame,
        cause_col:      str = "opposing_session_pnl",   # ST+PMC prior session P&L
        effect_col:     str = "v2b_campaign_pnl",       # v2b fill P&L
        max_lags:       int = 5,
        significance:   float = 0.05) -> dict:
    """
    Granger causality test: does cause_col at lags 1..max_lags
    have statistically significant predictive content for effect_col?

    NOTE: Granger causality ≠ true causality. It tests predictability, not mechanism.
    Use as a screening test only. Back up with PCMCI or Transfer Entropy.

    campaign_df columns required:
        campaign_id, date, cause_col, effect_col
    Sorted chronologically — NO LOOKAHEAD.
    """
    data = campaign_df[[cause_col, effect_col]].dropna()

    if len(data) < 30:
        return {"error": "Insufficient observations for Granger test (n < 30)"}

    results = grangercausalitytests(data, maxlag=max_lags, verbose=False)

    output = {}
    for lag, result in results.items():
        # F-test p-value (most common)
        pval_f = result[0]["ssr_ftest"][1]
        output[f"lag_{lag}"] = {
            "p_value_F_test": round(pval_f, 4),
            "significant":    pval_f < significance,
        }

    any_significant = any(v["significant"] for v in output.values())

    return {
        "cause_col":      cause_col,
        "effect_col":     effect_col,
        "max_lags":       max_lags,
        "significance":   significance,
        "results_by_lag": output,
        "any_lag_significant": any_significant,
        "caution": ("Granger causality tests temporal precedence, not mechanism. "
                    "Confirm with PCMCI and economic rationale."),
    }
```

---

### 5.3 PCMCI — Conditional Independence for Multivariate Causal Discovery

```python
# ── PCMCI pseudocode (requires tigramite library) ────────────────────────────
# pip install tigramite

def run_pcmci_causal_discovery(campaign_df: pd.DataFrame,
                                feature_cols: list[str],
                                target_col:   str,
                                max_lag:      int = 5,
                                alpha:        float = 0.05) -> dict:
    """
    PCMCI (Peter-Clark Momentary Conditional Independence):
    Identifies causal parents of target_col among feature_cols
    while conditioning on all other variables (avoids spurious links).

    feature_cols candidates for v2b system:
        - opposing_session_pnl    (prior session ST+PMC P&L)
        - or_width_pct            (opening range width as % of ATR)
        - time_bucket             (session time bucket index)
        - vix_level               (market regime indicator)
        - day_of_week             (calendar effect)
        - consecutive_losses      (streak — momentum in outcome space)

    PSEUDOCODE — actual tigramite call:
    """
    try:
        from tigramite import data_processing as pp
        from tigramite.pcmci import PCMCI
        from tigramite.independence_tests.parcorr import ParCorr
    except ImportError:
        return {"error": "tigramite not installed. pip install tigramite"}

    data_array = campaign_df[feature_cols + [target_col]].dropna().values

    # Standardise
    data_array = (data_array - data_array.mean(axis=0)) / data_array.std(axis=0)

    dataframe = pp.DataFrame(data_array,
                              var_names=feature_cols + [target_col])
    pcmci     = PCMCI(dataframe=dataframe, cond_ind_test=ParCorr(), verbosity=0)

    results = pcmci.run_pcmci(tau_max=max_lag, pc_alpha=alpha)

    # Extract significant causal parents of target (last variable)
    target_idx    = len(feature_cols)
    sig_parents   = []
    p_matrix      = results["p_matrix"]
    val_matrix    = results["val_matrix"]

    for var_idx, var_name in enumerate(feature_cols):
        for lag in range(1, max_lag + 1):
            p = p_matrix[var_idx, target_idx, lag]
            v = val_matrix[var_idx, target_idx, lag]
            if p < alpha:
                sig_parents.append({
                    "variable": var_name,
                    "lag":      lag,
                    "p_value":  round(p, 4),
                    "strength": round(v, 4),
                })

    return {
        "target":          target_col,
        "significant_parents": sig_parents,
        "alpha":           alpha,
        "max_lag":         max_lag,
        "n_obs":           len(data_array),
        "note": ("PCMCI conditions on all observed variables. "
                 "Unobserved confounders (e.g., market maker positioning) "
                 "cannot be ruled out."),
    }
```

---

### 5.4 Transfer Entropy — Non-Linear Causal Strength

```python
# ── Transfer Entropy pseudocode ───────────────────────────────────────────────
# Measures information flow from X at time t-k to Y at time t,
# beyond what Y's own past already provides.
# Non-parametric: no distribution assumption required.

def compute_transfer_entropy(x_series:   np.ndarray,
                              y_series:   np.ndarray,
                              lag:        int   = 1,
                              n_bins:     int   = 10,
                              n_shuffle:  int   = 100,
                              seed:       int   = 42) -> dict:
    """
    Effective Transfer Entropy (ETE): TE(X→Y) minus TE under shuffled X.
    Shuffling X destroys temporal structure but preserves marginal distribution,
    giving an estimate of spurious TE from finite-sample bias.

    ETE = TE(X→Y, real) - median(TE(X_shuffled→Y))
    """
    rng = np.random.default_rng(seed)

    def _te(x_lagged: np.ndarray, y_current: np.ndarray,
             y_lagged: np.ndarray, bins: int) -> float:
        """Discrete approximation to TE using histogram binning."""
        # Bin all series jointly
        x_b = np.digitize(x_lagged, np.percentile(x_lagged,
                           np.linspace(0, 100, bins + 1)[1:-1]))
        y_b = np.digitize(y_current, np.percentile(y_current,
                           np.linspace(0, 100, bins + 1)[1:-1]))
        yp_b = np.digitize(y_lagged, np.percentile(y_lagged,
                           np.linspace(0, 100, bins + 1)[1:-1]))

        # TE = H(Y_t | Y_{t-1}) - H(Y_t | Y_{t-1}, X_{t-lag})
        # Approximate via joint frequency tables
        # PSEUDOCODE — use pyinform or jpype/JIDT for production
        raise NotImplementedError("Use pyinform.transfer_entropy() in production")

    n = min(len(x_series), len(y_series))
    x_lag = x_series[:n - lag]
    y_cur = y_series[lag:n]
    y_lag = y_series[:n - lag]

    # Real TE
    # te_real = _te(x_lag, y_cur, y_lag, n_bins)  # enable when _te implemented

    # Shuffle TE (null distribution)
    te_shuffled = []
    for _ in range(n_shuffle):
        x_shuf = rng.permutation(x_lag)
        # te_shuffled.append(_te(x_shuf, y_cur, y_lag, n_bins))

    return {
        "lag":            lag,
        "note":           "Implement _te() with pyinform.transfer_entropy() in production",
        "ete_formula":    "ETE = TE_real - median(TE_shuffled)",
        "interpretation": "ETE > 0 indicates genuine information transfer from X to Y at this lag",
    }
```

---

### 5.5 Causal Ordering Integrity — Runtime Enforcement

```python
# ── Causal ordering guard for potions pipeline ────────────────────────────────

import functools
from datetime import datetime

def assert_causal_ordering(signal_timestamp: datetime,
                            action_timestamp: datetime,
                            label:            str = "") -> None:
    """
    Hard assertion: a signal can only cause an action that happens AFTER it.
    Raises CausalViolationError if action precedes or equals signal.

    Call this at every point where a signal field is read and an order is placed.
    Log all calls to the causal_audit table in the DSR ledger database.
    """
    class CausalViolationError(Exception): pass

    if action_timestamp <= signal_timestamp:
        raise CausalViolationError(
            f"CAUSAL VIOLATION [{label}]: "
            f"Action at {action_timestamp} ≤ Signal at {signal_timestamp}. "
            f"Future data was used. Replay must be halted and investigated."
        )


def causal_audit_decorator(func):
    """
    Decorator for replay functions that must not read future data.
    Tracks the 'current_bar_time' context and raises on any field access
    whose timestamp is > current_bar_time.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # In a full implementation:
        # 1. Set a thread-local "current_bar_time" from the bar being processed.
        # 2. Wrap the data access layer to check every field's bar_time.
        # 3. Raise CausalViolationError on any access where field.bar_time > current.
        # 4. Log the access attempt to causal_audit_log table.
        return func(*args, **kwargs)
    return wrapper


# ── Same-minute ambiguity resolution ─────────────────────────────────────────

def resolve_same_minute_ambiguity(campaign_row: dict,
                                   resolution:   str = "worst_case") -> dict:
    """
    For campaigns where both the arming gate and entry/exit fall within
    the same 1-minute bar, the temporal ordering is ambiguous from OHLC data alone.

    resolution options:
        "worst_case"    → assume entry filled last (least favourable)
        "best_case"     → assume entry filled first (most favourable)
        "exclude"       → exclude campaign from DSR (safest for fundraising)
        "tick_recon"    → require tick data to resolve (only auditable option)

    For investor-facing materials, ONLY tick_recon results are fully defensible.
    """
    assert resolution in ("worst_case", "best_case", "exclude", "tick_recon"), \
        f"Unknown resolution: {resolution}"

    if resolution == "tick_recon":
        if not campaign_row.get("tick_recon_status") == "COMPLETE":
            raise ValueError(
                f"Campaign {campaign_row.get('campaign_id')} requires tick reconstruction "
                f"but tick_recon_status={campaign_row.get('tick_recon_status')}. "
                f"Cannot use tick_recon resolution without completed reconstruction."
            )

    return {
        **campaign_row,
        "same_minute_resolution": resolution,
        "causal_confidence":       "HIGH" if resolution == "tick_recon" else
                                   "MEDIUM" if resolution == "worst_case" else
                                   "LOW",
    }
```

---

### 5.6 Epistemic Limits — Reflexivity Note

Per Polakow, Gebbie & Flint (2024): at scale, strategies become part of the price-generating process. For a system with 352 NQ campaigns over 5 years, this is not yet a practical concern — the fill sizes do not move the market. But it sets a ceiling on how far backtesting can take you:

```python
# ── Reflexivity threshold estimate ───────────────────────────────────────────

def estimate_capacity_limit(avg_fill_size_contracts: float,
                              market_avg_volume_contracts: float,
                              threshold_pct: float = 0.01) -> dict:
    """
    Estimate the AUM at which the strategy's fills begin to affect
    the market it is trying to trade (reflexivity threshold).

    For NQ: if the strategy exceeds ~1% of average bar volume,
    slippage will increase non-linearly and the backtest diverges from reality.
    """
    capacity_ratio = avg_fill_size_contracts / market_avg_volume_contracts
    is_reflexive   = capacity_ratio >= threshold_pct

    return {
        "fill_size_contracts":    avg_fill_size_contracts,
        "market_avg_volume":      market_avg_volume_contracts,
        "capacity_ratio_pct":     round(capacity_ratio * 100, 4),
        "reflexivity_threshold":  threshold_pct * 100,
        "below_reflexivity_limit": not is_reflexive,
        "note": ("Below threshold: backtest is a valid oracle. "
                 "Above threshold: strategy impacts the market it trades — "
                 "backtested edge will decay faster than modelled."),
    }
```

---

### 5.7 Audit Checklist — Causal Discovery & Ordering

```
CAUSAL DISCOVERY & ORDERING AUDIT
─────────────────────────────────────────────────────────────────────────────
[ ] CO1. causal_violation_count = 0 confirmed in all DSR ledger rows.
          Any new replay run re-confirms this before results are logged.
[ ] CO2. assert_causal_ordering() called at every bar-level signal→order step
          in the potions replay engine. Log stored in causal_audit_log.
[ ] CO3. Same-minute ambiguous rows (45/44/22/38/33 per market) have
          same_minute_resolution and causal_confidence fields set.
          Tick reconstruction plan documented with target completion date.
[ ] CO4. Pre-arm-touch rows: tick_recon_status = PENDING until resolved.
          These rows carry partial DSR weight (per WT-004).
[ ] CO5. Granger causality test run: opposing_session_pnl → v2b_campaign_pnl
          at lags 1-5. Results logged in CAUSAL_GRAPH.md.
[ ] CO6. PCMCI run with feature set: opposing_session_pnl, or_width_pct,
          time_bucket, vix_level, day_of_week. Significant parents documented.
[ ] CO7. ETE computed for the primary causal pair at lag 1.
          ETE > 0 required to claim genuine information transfer.
[ ] CO8. CAUSAL_GRAPH.md exists and predates all DSR ledger entries it covers.
          No new parameter sweep begins without updating the causal graph.
[ ] CO9. Reflexivity estimate computed for current fill size vs. NQ average volume.
          Result: below_reflexivity_limit = True at current sizing.
[ ] CO10. Spurious correlation test: run PCMCI with randomised target labels
           (shuffled v2b_campaign_pnl). Confirm significant parents disappear.
           If they do not, the features are confounded — investigate.
─────────────────────────────────────────────────────────────────────────────
```

---

## PART VI — MASTER AUDIT TRACKER

Use this as the single run-control checklist before each major milestone.

### Pre-Smoke-Run Gate (5 seeds, NQ, unconstrained)

```
BEFORE FIRST SMOKE RUN
─────────────────────────────────────────────────────────────────────────────
ENGINE:
[ ] 1.6 Engine correctness suite passing for all v2b order types
[ ] 1.6 Worst-case decision mode confirmed as production mode
[ ] 5.5 assert_causal_ordering() active in replay engine

DSR LEDGER:
[ ] 2.1 PSR computed and stored for all 55 existing ledger rows
[ ] 2.2 Autocorrelation-corrected SR stored for all 55 rows
[ ] 5.5 tick_recon_status field added to schema
[ ] 3.3 span_years formal definition implemented (MAX(end)-MIN(start)/365.25)
[ ] 3.3 DSR-003 JSON canonicalization implemented and tested on existing rows
[ ] 3.3 is_oos cross-field rule implemented

NULL RUNS:
[ ] 3.3 OR-width quartile breakpoints frozen from NQ universe, logged to CSV
[ ] 3.3 Time-bucket definitions locked (09:30/10:30/12:30/14:00/15:55)
[ ] 3.3 counts_toward_permutation_test field added to null-run CSV schema
[ ] 3.3 NullReplayGuard (or equivalent) active
[ ] 3.4 Pre-run assertion: gate_event_count vs filled_campaign_count checked

INFERENCE:
[ ] 2.2 Pitfall 1-5 mitigations implemented in scorecard generator
[ ] 4.6 Causal graph exists in live/specs/CAUSAL_GRAPH.md
─────────────────────────────────────────────────────────────────────────────
```

### Pre-Full-Run Gate (2,000 seeds per market)

```
BEFORE FULL 2000-SEED RUN
─────────────────────────────────────────────────────────────────────────────
[ ] Smoke run (5 seeds NQ) passed all gates above
[ ] NQ 200-seed run: real result ≥ p95 null on net AND Sharpe/Sortino
    for BOTH unconstrained AND stratified families
[ ] MNQ 200-seed run complete (MNQ is start-small priority)
[ ] MNQ 200-seed: same gate pass as NQ
[ ] Block-bootstrap Sharpe p05 > 0 for NQ and MNQ
[ ] CPCV PBO < 20% for NQ and MNQ
[ ] Recovery-time logged for NQ and MNQ block-bootstrap paths
[ ] gap_shock Monte Carlo scenario run: P50 net_pnl still positive
[ ] Haircut Sharpe schedule generated for investor-facing materials
[ ] DSR_PEER_BENCHMARK display decision resolved (recommend: show SR_0=0.67)
─────────────────────────────────────────────────────────────────────────────
```

---

## Appendix A — Reference Mapping

| Concept | Source | Section in this doc |
|---|---|---|
| Model candles & engine correctness proof | Löw et al. 2015 | Part I |
| PSR formula | Bailey & López de Prado 2012 | §2.1 |
| DSR formula | Bailey & López de Prado 2014 | §2.2 / Pitfall 5 |
| HAC variance estimator | Newey-West; López de Prado 2026 | §2.2 / Pitfall 2 |
| MinBTL formula | Bailey & López de Prado 2012 | §2.2 / Pitfall 3 |
| Sharpe haircut | Harvey, Liu & Zhu 2015 | §2.2 / Pitfall 5 |
| Double-bootstrap FDR | Harvey & Liu 2020 | Part III |
| Null family anti-leakage | This spec + gate replay plan | §3.3 |
| Walk-forward / CPCV / Monte Carlo | Joubert et al. 2024 | Part IV |
| Granger causality | Tang 2024; Kolonin et al. 2022 | §5.2 |
| PCMCI | Letteri 2025; Oliveira et al. 2024 | §5.3 |
| Transfer entropy | Letteri 2025 | §5.4 |
| Reflexivity limits | Polakow, Gebbie & Flint 2024 | §5.6 |
| Causal graph before backtesting | Joubert et al. 2024; López de Prado 2024 | §4.5, §5.8 |

---

## Appendix B — File Integration Map

| This spec section | Your file | Action |
|---|---|---|
| Part I engine test | `scripts/generate_strategy_validation_scorecard.py` | Add `run_correctness_suite()` call in CI |
| Part I ambiguous rows | `data/validation/dsr_trial_ledger.csv` | Add `tick_recon_status` column |
| Part II PSR/DSR | `scripts/generate_strategy_validation_scorecard.py` | Replace raw SR with `compute_psr()` output |
| Part III null runs | `live/v2b_prior_opposed_random_gate_replay.py` | Wrap with `NullReplayGuard` |
| Part III null CSV | `live/state/v2b_prior_opposed_random_gate_replays/` | Add `counts_toward_permutation_test` column |
| Part IV CPCV | New: `scripts/cpcv_validation.py` | Implement after 200-seed run |
| Part IV Monte Carlo | New: `scripts/mc_stress_scenarios.py` | Implement after 200-seed run |
| Part V causal graph | New: `live/specs/CAUSAL_GRAPH.md` | Required before next sweep |
| Part V Granger/PCMCI | New: `scripts/causal_discovery.py` | Run once on full campaign history |
| Master audit tracker | New: `data/docs/AUDIT_TRACKER.md` | Maintain as a living checklist |

---

*End of document — Version 1.0 — 2026-06-26*  
*Sources: arXiv:1509.08248 · JPM 2026 (López de Prado et al.) · arXiv:2006.04269 · JPM 2024 (Joubert et al.)*
