# Canonical N/S research policy

## Score (higher is better)

For each eligible flat / finite book:

```text
N/S = forced-flat net P&L / |reachable full-book stress|
```

For an overlay, filter, or size-up:

```text
ΔN/S = N/S_candidate − N/S_baseline
```

**Δnet is viability + reporting only.** Ranking, null winners, and promotion
use **ΔN/S** (then candidate N/S as secondary).

Example (NQ prior-opposed OR-normal @2×):

```text
24.06 → 36.26
ΔN/S = +12.20   (preferred over Δnet = +$581,952)
```

## Hard eligibility gates

Rank only after:

- finite / forced-flat accounting complete
- reachable full-stack stress available
- lot-correct where relevant
- USD-normalized for cross-market comparisons
- sufficient sample
- causal feature known before entry
- positive net P&L
- minimum absolute stress threshold
- no unresolved inventory / margin warning

## Boards

1. **Cross-market finite core** — USD-normalized, lot-correct, flat books.
2. **Overlay** — OOS ΔN/S by filter / condition / exact multiplier.
3. **Inventory** — forced-flat N/S for indefinite runners only (not ranked with flat).
4. **Sensitivity** — 1.5×/2×/3×/4× ladders; non-promotional until null-tested.

## Taxonomy

| Label | Meaning |
|---|---|
| SIZE-UP VALIDATED | Positive OOS ΔN/S + matched/shift/master ΔN/S nulls + WF/stress/overlap |
| PROVISIONAL PAPER | Local N/S tests pass; borderline or fails strict master ΔN/S |
| RISK THROTTLE | Lowers stress/DD / may raise N/S without superior incremental selection |
| SENSITIVITY ONLY | Historical N/S ladder without exact-multiplier null validation |
| NOT VALIDATED | Fails causal, sample, N/S placebo/shift/master, or risk gate |

## Ordering

```text
Primary:   OOS ΔN/S (higher better)
Secondary: OOS candidate N/S (higher better)
Viability: positive OOS net, DD/stress/margin, sample/coverage
```

## Portfolio

```text
Portfolio N/S = portfolio forced-flat net / |portfolio reachable joint stress|
```

HOLD_ONE: NQ/MNQ · YM/MYM · ES/MES — no simultaneous prior-opposed HP
multipliers until joint-stress validation passes.
