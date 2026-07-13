# Causal Graph — Tier-1 Strategy Families

**Version:** 0.1  
**Date:** 2026-06-26  
**Purpose:** Document hypothesized mechanisms and **falsification conditions** before parameter sweeps enter the DSR ledger (Joubert et al. 2024). This is not a proof of edge — it states what would disprove each family's claimed mechanism.

**Engine vs statistical causality:** Engine causality (no lookahead) is enforced by `live_after_ts`, plugin gating, and broker fill rules — see [`Platform.md`](../Platform.md). This document addresses **why** the edge might exist, not **whether** fills are temporally ordered.

---

## 1. v2b prior-opposed delayed arming gate

### Hypothesized mechanism

1. Prior-session opposing ST+PMC campaign prints (directional regime signal).
2. Delayed arming gate requires that opposing event before v2b can arm.
3. v2b entry captures mean-reversion or continuation only when the opposing context is already established.
4. Edge comes from **conditional entry timing**, not from raw ST+PMC alone.

### Confounders (must be matched in null tests)

- Calendar year / regime (2022 weak year)
- Gate side (long vs short)
- Time-of-day bucket
- Opening-range width quartile

### Falsification conditions

| # | Observation that falsifies the mechanism | Test |
|---|---|---|
| F1 | Stratified random gate events (matched strata) reproduce real net at p ≥ 0.05 | **Not falsified** — 200-seed `stratified_fine_buckets`, p=0.005 all markets (NQ/MNQ/YM/MYM) |
| F2 | Shuffling opposing ST+PMC side labels preserves edge | Pending 200-seed `shuffled_stpmc_side` |
| F3 | Edge disappears when same-minute/pre-arm-touch rows included without tick proof | Execution scrutiny — large ambiguous buckets unresolved |
| F4 | `causality_violations` > 0 after engine change | **Not falsified** — 0 across null batch |

### Evidence links

- [`live/state/v2b_prior_opposed_random_gate_replays/INDEX.md`](../state/v2b_prior_opposed_random_gate_replays/INDEX.md)
- [`live/v2b_prior_opposed_execution_scrutiny.py`](../v2b_prior_opposed_execution_scrutiny.py)

---

## 2. Yearly ORB scaleout3 (limit-retest)

### Hypothesized mechanism (empirical regularity, not structural)

1. Jan–Mar builds a yearly opening range (OR).
2. Post-Apr breakout closes outside OR signal directional bias for the rest of the year.
3. Limit retest at OR boundary offers favorable entry vs chasing breakout close.
4. Scaleout3 + swing stop manages lumpy, low-frequency trend capture.

**Caution:** The link from year-boundary breakout to persistent trend is an **empirical regularity**, not a microstructural causal chain like the v2b gate.

### Confounders

- Which year's OR (calendar)
- Breakout direction vs retest fill quality
- Gap risk at year open / roll windows
- Cross-market correlation (NQ/ES/YM)

### Falsification conditions

| # | Observation that falsifies the mechanism | Test |
|---|---|---|
| F1 | Shuffled breakout-direction labels match real net | **Not run** |
| F2 | Random calendar entry dates (matched trade count) match real Sharpe | **Not run** |
| F3 | Edge is artifact of daily-OHLC sim, not broker-like replay | Partially addressed — broker_like rows exist; scrutiny nulls missing |
| F4 | OCO+20% branch dominates limit-retest under realism | **Not falsified** — limit-retest leads broker_like table post-realism |

### Evidence links

- [`live/broker_like_replays.py`](../broker_like_replays.py) — `yearly_orb_scaleout3`
- [`mnq/case_studies/STRATEGY_TRACKER.md`](../../mnq/case_studies/STRATEGY_TRACKER.md) — yearly ORB ranks

---

## 3. ATR Supertrend DCA (daily-primary biweekly ladder)

### Hypothesized mechanism (agnostic trend following)

1. Supertrend flip on primary timeframe defines regime direction.
2. DCA adds on pullbacks within trend, capped by max units and entry guard.
3. Edge comes from **trend persistence** minus cost of false flips and add clustering.

**Caution:** No structural claim that ST "causes" future returns — Granger/PCMCI evidence not yet collected.

### Confounders

- Weekly vs daily bar alignment (MYM parity correction history)
- Volatility regime (ATR level)
- Ladder sizing vs stress capacity

### Falsification conditions

| # | Observation that falsifies the mechanism | Test |
|---|---|---|
| F1 | Shuffled ST flip labels preserve net | **Not run** |
| F2 | Plugin replay diverges from Pine reference on same bars | MYM mislabeled weekly **falsified** prior promotion; causal corrections required |
| F3 | Biweekly ladder underperforms simple 1-unit trend on same market | Case-study rank — ladder competitive on MNQ/NQ in tracker |
| F4 | Broker-like replay net negative after realism | YM/MYM weak; MNQ/NQ positive in broker_like table |

### Evidence links

- [`live/strategies/atr_supertrend_dca.py`](../strategies/atr_supertrend_dca.py)
- [`pine/atr_supertrend_dca_10max_entry_guard_3initial.pine`](../../pine/atr_supertrend_dca_10max_entry_guard_3initial.pine)
- MYM demotion: [`mnq/case_studies/STRATEGY_TRACKER.md`](../../mnq/case_studies/STRATEGY_TRACKER.md) § ATR Supertrend Pine-Parity Correction

---

## Update policy

- Any new DSR ledger sweep for a family above **must** cite the falsification row it is designed to survive.
- If a falsification test runs and fails, update status here before updating promotion language in STRATEGY_TRACKER.
