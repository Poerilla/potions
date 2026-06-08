# Archived — ORB v1 (pre-April 2026)

This folder preserves the **v1 Opening Range Breakout** artifacts.
They are retained for historical reference and auditability only.
**Do not use for live trading or forward analysis.** The v2 model
(pre-placed OCO stop entry) supersedes everything here.

See `../scripts/validation.md` for the full v1 vs v2 comparison and
the v2 live-execution model.

---

## What changed between v1 and v2

### v1 — close-based signal + limit order entry

Two sub-variants were built under v1:

| Variant | Entry model | Problem |
|---|---|---|
| v1a (original) | Close-based breakout + limit at `RH` / `RL`. Same-bar fill allowed whenever the breakout bar's low touched `RH` (or high touched `RL`). | **Same-bar fill is physically impossible** — a limit at `RH` could not have existed before the bar closed, since the close-based breakout signal was the trigger to place it. v1a silently modeled a pre-placed limit fill while claiming close-based signaling. |
| v1b (fixed limit) | Close-based breakout + limit at `RH` / `RL`. Confirmation bar read-only; fills only on subsequent bars via pullback. | Honest implementation of the v1 rule, but ~10% of "would-be" trades never fill because price runs away and never retouches the range boundary. Those missed trades are disproportionately the best winners. |

### v2a — pre-placed OCO stop with re-arm on both sides (BUGGY, archived)

| Variant | Entry model | Bug |
|---|---|---|
| v2a | At 9:45 ET place OCO stop pair. After ANY trade closes, re-arm **both** stops at original prices. | After a winning trade in one direction, the same-direction stop "fires again" at the original trigger price even though current market price is far past it. ~86% of v2a P/L came from these phantom re-entries. |

### v2b — pre-placed OCO stop with bracket-then-reverse (canonical live model)

| Variant | Entry model | Status |
|---|---|---|
| v2b | At 9:45 ET place OCO stop pair. After ANY trade closes, only the OPPOSITE-direction stop is re-armed. Maximum 1 Long and 1 Short per day. | Live model. Honest about the strategy's true profitability. |

### Performance delta (MNQ NY, 2021-03-04 → 2026-04-23, 1 contract)

| Model | Trades | Win % | Net $ | Max DD | Status |
|---|---|---|---|---|---|
| v1a (buggy same-bar fill) | 2,056 | 60.4% | $62,631 | −$2,442 | Archived — impossible fills |
| v1b (honest close-based limit) | 1,817 | 52.8% | $12,840 | −$4,709 | Archived — honest reference |
| v2a (buggy stop re-arm) | 2,517 | 65.3% | $122,172 | −$2,197 | **Archived — impossible re-entries** |
| **v2b (bracket-then-reverse)** | **1,991** | **54.0%** | **$15,877** | **−$4,716** | **Live model — honest** |

The canonical reality: **MNQ NY ORB nets ~$3,100/yr per contract** with
~$4,700 max drawdown. v1b and v2b agree closely (the entry mechanism
makes only ~$600/yr difference). The two buggy models (v1a, v2a) had
inflated P/L by 4-7×.

---

## Archived contents

### `v1_scripts/`

| File | Role in v1 |
|---|---|
| `step1_to_5min.py` | DBN → 5-min RTH CSV (still used by v1b, kept) |
| `step2_range_trades.py` | **v1a buggy** close-based + same-bar fill backtest |
| `step2_fixed_next_bar_entry.py` | **v1b** close-based + limit (confirmation bar read-only) |
| `update_mnq_15min_orb.py` | Old end-to-end pipeline using v1a |
| `process_nq_15min_orb.py` | Combined NQ pipeline using v1a logic |
| `london_ny_orb.py` | v1 London + NY session script |
| `monte_carlo.py` | v1 portfolio monte-carlo (3 MNQ 15-min + 2 MYM 15-min + 1 MNQ Monthly) |
| `to_excel.py` | Converts v1 CSVs → Excel workbooks |

### `v1_results/`

| File | Source |
|---|---|
| `mnq_orb_results.v1.csv` | MNQ v1a results (2021-03-04 → 2026-04-23) |
| `mnq_orb_results.v1.xlsx` | Formatted Excel of above |
| `mnq_orb_results_fixed_limit.v1.csv` | MNQ v1b (honest close+limit) |
| `mnq_orb_results.pre_april_update.v1.csv` | Snapshot before the 2026-04-23 data extension |
| `mym_orb_results.v1.csv` | MYM v1a results |
| `nq_orb_results.v1.csv` | NQ v1a results |
| `mes_orb_results.v1.csv` | MES v1a results |
| `london_orb_results.v1.csv` | London session v1 results |
| `ny_orb_results.v1.csv` | NY session v1 results |
| `combined_orb_results.v1.csv` | Both sessions merged (v1) |

### `v2a_results/` — pre-2026-04-25 v2 results (buggy stop re-arm)

| File | Source |
|---|---|
| `mnq_ny_orb_results.v2a.csv` + `.xlsx` | MNQ NY v2a (claimed $117,746) |
| `mym_ny_orb_results.v2a.csv` + `.xlsx` | MYM NY v2a (claimed $45,401) |
| `mnq_london_orb_results.v2a.csv` | MNQ London v2a (claimed $30,414) |
| `mym_london_orb_results.v2a.csv` | MYM London v2a (claimed $12,281) |
| `mnq_ny_combined_orb_results.v2a.csv` | MNQ NY (from combined script) v2a |
| `mym_ny_combined_orb_results.v2a.csv` | MYM NY (from combined script) v2a |

---

## v2 canonical artifacts (live models)

Located at their normal paths, not archived:

| File | Role |
|---|---|
| `../scripts/step2_preplaced_stops.py` | v2 backtest (supports `--product MNQ` and `--product MYM`) |
| `../scripts/validation.md` | Strategy rules, v1 vs v2 comparison, sizing tables |
| `../mnq/mnq_orb_results_stops.csv` | MNQ v2 results |
| `../mym/mym_orb_results_stops.csv` | MYM v2 results |
| `../combined_orb/scripts/london_ny_orb_stops.py` | v2 London + NY backtest |
| `../combined_orb/london_orb_results_stops.csv` | London v2 results |
| `../combined_orb/ny_orb_results_stops.csv` | NY v2 results (MNQ) |
| `../combined_orb/combined_orb_results_stops.csv` | London + NY merged |
| `../orb-portfolio/monte_carlo.py` | v2 portfolio monte-carlo |

---

## Migration notes (dates are calendar references for future me)

- **Apr 24, 2026**: v1a archived. v2 promoted to canonical live model.
  Initial v2 numbers showed $117k/5yr net at 1 MNQ NY (apparent ~7×
  improvement over v1b).
- **Apr 25, 2026**: User-reported visual anomaly in case-study chart
  led to discovery of the v2 same-direction re-entry bug. The original
  v2 implementation re-armed both stops after a trade closed; on
  winning days it would "fire" the same-direction stop again at a
  price the broker could never have given. Fix renamed v2a (buggy) to
  archived; corrected v2b (bracket-then-reverse) is now canonical.
- **Honest v2b numbers**: MNQ NY $15,877/5yr (~$3,100/yr); MNQ
  London/MYM NY/MYM London all net-negative. Entire 4-strategy
  portfolio drops from claimed $193,562 to honest $8,683.
- The v1b (honest close+limit) and v2b (honest stop) results agree to
  within ~$3k/5yr — confirming both honest models converge on the same
  reality and the gaps in v1a/v2a were purely artifacts of impossible
  fill assumptions.
