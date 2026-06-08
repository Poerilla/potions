# ORB Strategy — Backtest Validation & Execution Models

> **⚠️ MAJOR REVISION 2026-04-25**: The v2 backtest contained a
> same-direction re-entry bug that inflated reported P/L by ~7×.
> The corrected version (v2b) shows the strategy is **only marginally
> profitable on MNQ NY** and **net negative on the other three
> session/instrument combinations**. See Section 2 below for the
> v2a→v2b correction history; see Section 3 for honest numbers.

This document covers the four distinct backtest models built for the
15-minute Opening Range Breakout strategy on MNQ and MYM. v2b is
the canonical live-execution model.

---

## 1. Strategy Rules (common to all models)

1. **Opening range**: 15-minute window (9:30–9:45 AM New York time
   for the NY session; 2:00–2:15 AM for the London session) defines
   `Range_High`, `Range_Low`, and `Range = Range_High - Range_Low`.
2. **Target**: `Entry ± Range` (1R reward).
3. **Stop**: opposite range boundary, strict inequality.
4. **Max 2 trades per day** per session per product.
5. **EOD close**: any open position at 16:00 ET (or session end for
   London) is closed at the last bar's close.

The four model variants differ only in **how and when entries are placed**.

---

## 2. The four backtest variants

### v1a — Original close-based + same-bar limit fill (BUGGY)

- Bar must CLOSE above `RH` (Long) or below `RL` (Short) to confirm.
- If the breakout bar's low touched `RH`, the simulator credits a fill
  at `RH` *during* that same bar.
- Bug: a limit at `RH` could not have existed before the bar's close,
  so this fill is physically impossible.
- Archived. See `archived/v1_results/mnq_orb_results.v1.csv`.

### v1b — Close-based + limit fill on subsequent bars only (HONEST close-based)

- Same close-based confirmation rule as v1a.
- Fills only on bars STRICTLY AFTER the confirmation bar.
- ~10% of would-be trades miss because price never retraces to `RH`/`RL`.
- The honest implementation of "close-based + limit" — but it can't
  capture the runaway breakouts.

### v2a — Pre-placed OCO stop with re-arm on both sides (BUGGY)

- At 9:45 ET, place buy-stop at `RH+1tick` and sell-stop at `RL-1tick`.
- After ANY trade closes, re-arms BOTH stops at original prices.
- Bug: after a winning trade in one direction, the SAME-direction stop
  is "re-fired" at the original trigger even though current market
  price is far past it. In live execution this fill is impossible
  (broker rejects or fills at much worse market price).
- ~86% of v2a's reported P/L came from these phantom re-entry trades.
- Archived. See `archived/v2a_results/`.

### v2b — Pre-placed OCO stop with bracket-then-reverse

- At 9:45 ET, place OCO stop pair (same as v2a).
- After ANY trade closes (Win/Loss/EOD), only the OPPOSITE-direction
  stop is re-armed. Same-direction stop is canceled.
- Maximum 1 Long and 1 Short per day, in either order.

### v2d — Fade-the-breakout (chop-regime variant)

- Inverse logic: once a breakout occurs (price ≥ RH+1 tick or ≤ RL−1 tick),
  arm a fade entry inside the range:
  - After long breakout: SELL STOP at RH−1 tick → fade short
  - After short breakout: BUY STOP at RL+1 tick → fade long
- Target = opposite range boundary; Stop = RH+Range or RL−Range.
- Bracket-then-reverse: max 1 fade-long + 1 fade-short per day.
- **Standalone**: net negative in trending regimes, profitable in chop.

### CANONICAL LIVE STRATEGY: v2b/v2d adaptive 50/150 MA cross

Combines v2b and v2d under a daily 50/150 MA cross regime indicator
(read at session open, uses prior day's MA values for causal honesty):

- 50d MA > 150d MA  → arm v2b OCO breakout pair
- 50d MA ≤ 150d MA  → enter v2d mode (wait for breakout, then fade)
- Trade exactly one variant per day

Validated on:
- **MNQ 5-yr in-sample**: 8 of 18 MA pairs in the family beat v2b alone.
- **NQ 16-yr walk-forward**: stitched OOS adaptive picks beat v2b alone
  by **+$63,684** over 13 years.
- **50/150 was the most robust pair** (slowest signal, fewest false flips).

**MNQ adaptive performance (1 contract, 5-yr):**

| Metric | Adaptive | v2b alone | Δ |
|---|---|---|---|
| Trades | 1,919 | 1,991 | similar |
| Win rate | 54.1% | 54.0% | identical |
| Net P/L | **+$18,885** | +$15,877 | **+$3,008 (+19%)** |
| Annual avg | **~$3,690/yr** | ~$3,020/yr | +22% |
| Max realized DD | **−$3,542** | −$4,716 | **−25%** |
| Calmar | **1.05** | 0.64 | +64% |
| Days in v2b regime | 74.4% | — | — |
| Days in v2d regime | 25.6% | — | — |

**Year-by-year (MNQ, adaptive):**

| Year | v2b alone | Adaptive | Δ |
|---|---|---|---|
| 2021 | +$2,992 | +$2,992 | $0 |
| **2022** | **−$458** | **+$3,646** | **+$4,104** ⭐ |
| 2023 | +$12 | −$298 | −$310 |
| 2024 | +$3,516 | +$3,516 | $0 |
| 2025 | +$5,029 | +$4,950 | −$79 |
| 2026 YTD | +$4,786 | +$4,081 | −$705 |

The adaptive rule's edge comes almost entirely from rescuing 2022 (the
worst v2b chop year) with minimal disruption to trending years.

### Adaptive **v1b** + v2d (same 50/150 rule, limit pullback instead of stops)

For comparison only: the **trend** arm uses the archived **v1b** model
(5-minute bars, 5m close confirms breakout, **limit** entry on a later
bar at the range boundary — `mnq/v1_limit/run_v1b_from_5min.py`). The
**chop** arm is still **v2d** (1-minute pre-placed fade logic, unchanged).

| Metric | Adaptive v2b+v2d | Adaptive v1b+v2d |
|---|---|---|
| Trades | 1,919 | 1,792 |
| Win rate | 54.1% | 52.7% |
| Net P/L | **+$18,885** | +$14,120 |
| Max realized DD | −$3,542 | −$3,542 |

v1b underperforms v2b in the trend arm (missed / delayed fills vs
stop-through), so the combined adaptive curve is lower **even though**
2022 is still rescued by v2d. **Live execution** remains aligned with
**v2b + v2d** (pre-placed stops); adaptive v1b is a research baseline
for “what if I insisted on limits.”

Reproduce:

```bash
python mnq/v1_limit/run_v1b_from_5min.py
python mnq/v1_limit/build_adaptive_v1_50_150.py
```

---

## 3. v2b stand-alone performance — per-strategy by year

### MNQ NY (the only positive strategy)

| Year | Trades | Win % | Net $ |
|---|---|---|---|
| 2021 | 309 | 56.0% | +$2,992 |
| 2022 | 397 | 52.0% | −$458 |
| 2023 | 394 | 51.0% | +$12 |
| 2024 | 396 | 55.0% | +$3,516 |
| 2025 | 381 | 54.0% | +$5,029 |
| **2026 YTD** | 114 | **59.0%** | **+$4,786** |
| **5-yr total** | **1,991** | **54.0%** | **+$15,877** |

Average: **~$3,100/yr per MNQ contract.** Max realized DD: **−$4,716.**

### MNQ London

| Year | Trades | Win % | Net $ |
|---|---|---|---|
| 2021 | 397 | 55.0% | +$332 |
| 2022 | 480 | 48.0% | **−$3,492** |
| 2023 | 471 | 57.0% | +$718 |
| 2024 | 489 | 49.0% | −$1,143 |
| 2025 | 480 | 55.0% | +$1,440 |
| 2026 YTD | 156 | 53.0% | +$408 |
| **5-yr total** | **2,473** | **52%** | **−$1,738** |

Net negative. Drawdown −$5,328.

### MYM NY

| Year | Trades | Win % | Net $ |
|---|---|---|---|
| 2019 | 254 | 56.0% | +$762 |
| 2020 | 383 | 56.0% | −$121 |
| 2021 | 367 | 56.0% | +$1,170 |
| 2022 | 408 | 47.0% | **−$2,173** |
| 2023 | 383 | 49.0% | −$769 |
| 2024 | 387 | 49.0% | −$1,654 |
| 2025 | 385 | 53.0% | +$578 |
| 2026 YTD | 60 | 55.0% | +$587 |
| **6.8-yr total** | **2,627** | **52.0%** | **−$1,620** |

Net negative. Drawdown −$6,564.

### MYM London

| Year | Trades | Win % | Net $ |
|---|---|---|---|
| 2019 | 317 | 58.0% | −$387 |
| 2020 | 453 | 54.0% | +$272 |
| 2021 | 471 | 52.0% | −$650 |
| 2022 | 472 | 51.0% | −$542 |
| 2023 | 496 | 55.0% | −$532 |
| 2024 | 484 | 58.0% | −$314 |
| 2025 | 484 | 49.0% | **−$1,490** |
| 2026 YTD | 88 | 47.0% | −$197 |
| **6.8-yr total** | **3,265** | **53%** | **−$3,840** |

Net negative. Drawdown −$4,381.

---

## 4. v1a/v1b/v2a/v2b side-by-side (MNQ NY, 2021-03-04 → 2026-04-23)

| Model | Trades | Win % | Gross (pts) | Net $ | Max DD | Status |
|---|---|---|---|---|---|---|
| v1a (buggy same-bar fill) | 2,056 | 60.4% | 32,858 | $62,631 | −$2,442 | **Archived (impossible fills)** |
| v1b (honest close+limit) | 1,817 | 52.8% | 7,783 | $12,840 | −$4,709 | Archived (still valid as reference) |
| v2a (buggy stop re-arm) | 2,511 | 65.2% | 60,756 | $117,746 | −$2,197 | **Archived (impossible re-entries)** |
| **v2b (bracket-then-reverse)** | **1,991** | **54.0%** | **9,432** | **$15,877** | **−$4,716** | **Live model** |

**v2b vs v1b** (the two honest models):
- v2b has slightly more trades (1,991 vs 1,817) and slightly higher
  win rate (54% vs 53%).
- v2b net P/L is ~24% higher ($15,877 vs $12,840).
- Max DDs are essentially identical (~−$4,700).
- v2b's pre-placed stops simply give marginally better fill timing
  than v1b's close-based limits — about $600/yr in the strategy's
  favor. Not a transformative difference.

The takeaway: **the strategy's edge is small, regardless of entry
mechanism.** Both honest backtests show roughly 54% win rate and
~$3,000/yr per MNQ contract on the NY session.

---

## 5. v2b portfolio (1×1×1×1, all four strategies)

| Metric | Value |
|---|---|
| Total trades | 10,364 |
| Realized net P/L | **+$8,683** over 5 years |
| Annual avg | ~$1,690/yr |
| Max realized DD | **−$8,536** |
| 99th-pct MC DD | −$13,936 |
| 99th-pct capital (3× DD) | $41,808 |
| Annual ROI on capital | **~4.0%** |

**The four-strategy portfolio at 1×1×1×1 is worse than MNQ NY alone.**
The three losing strategies (MNQ London, MYM NY, MYM London) drag
down the only profitable one. Net P/L drops from $15,877 (MNQ NY
alone) to $8,683 (combined).

---

## 6. Implications for the live test plan

### What changes from the v2a numbers

| | v2a claimed | v2b honest |
|---|---|---|
| 1×1×1×1 annual P/L | $40,000/yr | **~$1,700/yr** |
| MNQ NY only annual P/L | $23,000/yr | **~$3,100/yr** |
| Statistically-safe min account (1×1×1×1) | $8,100 | **$15,000** (3× the 99th pct DD) |
| Annualized ROI on min capital | 489% | **~10%** (MNQ NY only) |

### Practical recommendations

1. **Drop MYM and MNQ London from the live plan.** All three are net
   negative in the honest backtest.
2. **Trade only MNQ NY.** Fund **$8,000-$12,000** for 1 MNQ contract
   (covers the −$4,716 max DD with healthy buffer + IM).
3. **Expected return: $3,000-$5,000/yr per MNQ.** Recent 2024-2026
   years have been better (+$3,500 to +$5,000), but 2022-2023 was
   essentially flat.
4. **Re-evaluate before scaling.** The strategy's edge is small enough
   that at 3 MNQ NY contracts (~$9,000-$15,000/yr expected), execution
   slippage worse than 1 tick could erase the edge.
5. **Consider the strategy paper-only until re-validated.** The
   discovery of two material bugs in successive backtest models is
   itself a reason to be cautious. Run live for 30 days at 1 MNQ
   before committing real risk capital.

---

## 7. Real-world case studies

Six annotated charts of real backtest days. **NOTE**: the charts were
generated against the v2b CSV, but the case-study titles still refer
to v2a-era pattern frequencies. Treat the charts as accurate and
ignore the "47% trend day" and "double-win" claims — they reflect the
v2a buggy distribution. Honest v2b distributions:

| Pattern (v2b) | % of days |
|---|---|
| Single-trade Win | ~50% |
| Single-trade Loss | ~5% |
| Loss-then-Win | ~17% |
| Loss-then-Loss (whipsaw) | ~15% |
| EOD-Close | ~13% |

See `../mnq/case_studies/README.md`.

**Adaptive 50/150:** per-year annotated charts (regime-correct v2b vs v2d
entry logic) live under `../mnq/case_studies/adaptive_by_year/`. Generate
with `python mnq/v2d/build_adaptive_year_samples.py`.

---

## 8. Pipeline / artifacts

| File | Description |
|---|---|
| `step2_preplaced_stops.py` | **v2b canonical** backtest |
| `to_excel.py` | v2b Excel writer |
| `archived/v1_scripts/` | v1a + v1b scripts |
| `archived/v1_results/` | v1a CSVs |
| `archived/v2a_results/` | v2a CSVs (pre-bug-fix snapshot) |
| `mnq/mnq_orb_results_stops.csv` | MNQ NY v2b results |
| `mym/mym_orb_results_stops.csv` | MYM NY v2b results |
| `combined_orb/{london,ny}_orb_results_stops.csv` | MNQ London + NY v2b |
| `combined_orb/mym_{london,ny}_orb_results_stops.csv` | MYM London + NY v2b |
| `mnq/raw/extracted_new/glbx-mdp3-20100606-20260423.ohlcv-1m.dbn.zst` | Latest MNQ 1-min OHLCV |
| `mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst` | MYM 1-min OHLCV |
| `mnq/v2d/build_adaptive_year_samples.py` | Adaptive case-study PNGs → `mnq/case_studies/adaptive_by_year/` |
| `es/v2d/build_adaptive_es_50_150.py` | ES adaptive 50/150 → `es/v2d/es_orb_results_adaptive_50_150.csv` |
| `es/raw/glbx-mdp3-20100606-20260425.ohlcv-1m.dbn.zst` | ES 1m OHLCV (Databento may warn if truncated) |

---

## 9. Live execution notes (still valid)

- **Chart timeframe**: 1-minute (for intrabar stop trigger accuracy).
- **Order type**: stop-market (not stop-limit).
- **Platform**: TradingView Pine Script → Tradovate via broker panel.
- **OCO handling**: Pine doesn't natively support OCO; implement
  manually with `strategy.cancel()` when one stop fires.
- **Bracket-then-reverse**: after a trade closes, cancel the
  same-direction entry stop and only re-arm the opposite side.
- **Session window**: 9:30–15:55 ET (force-close any open position).
- **Minimum live sample before scaling**: 30 trading days with stable
  fill-price distribution and no systematic mismatch vs the v2b backtest.
