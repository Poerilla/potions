# MNQ **v2e** — London sweep baseline (**no ORB**)

This folder’s **canonical model** is a **long-only** playbook built only from the **London session box** and **post-box price structure**. Opening-range (ORB) logic is **not** part of this definition.

---

## Concept (bullish)

Named candles (1 m MNQ, **America/New_York**):

| Name | Meaning |
|------|--------|
| **London low** | Minimum ``low`` over **[02:00, 09:30)** (same causal window as legacy v2e London box). |
| **london_low_time** | **Earliest** London-window **[02:00, 09:30)** 1 m bar whose ``low`` tags ``London_low``. |
| **First London sweep** | **First** RTH **[09:30, 16:00)** bar with ``low <= London_low`` (segment anchor). |
| **stop_hunter** | Fixed-point: repeatedly set to the **deepest** ``low`` among **1 m** bars from **first sweep** **up to but not including** the piercer candle (tie → earliest); each move recomputes breaker (wider 5 m window) and piercer until stable (cap 30 passes). |
| **5 m swing** | ``high[i] > high[i-1]`` and ``high[i] > high[i+1]`` on consecutive session **5 m** bars (**02:00** NY grid). |
| **Breaker** | After each stop_hunter candidate: all strict **5 m** swing highs from **02:00** through the **5 m bar after** the bucket containing that SH (inclusive on that following candle’s ``bar_left``). Breaker = **last** swing chronologically. |
| **Piercer** | First **1 m** swing **after** ``stop_hunter`` with ``high > breaker_high`` (same neighbor rule). |
| **Entry** | **Limit buy** at **breaker_high**. Fill on the **first** bar **after** piercer confirmation with ``low <= breaker_high`` (fill price = ``breaker_high``). |

**Stop (pick one):** ``London_low``, **breaker** candle ``low``, or **stop_hunter** candle ``low`` — see ``--sl-at``.

**Take-profit:** ``stop_hunter_low + (piercer_high - stop_hunter_low) * 2``.

**Post-fill:** pessimistic **stop before TP** when both touch same 1 m bar; remainder flattened last **RTH close** before **16:00** after **15:59** cutoff.

**Economics:** **1 MNQ**; **\$2**/index point; **\$1.50** round-trip fee per trade.

---

## Causality, lookahead, and backtest interpretation

**What is *not* cheating**

- Setups use **only that calendar day’s** 1 m data — **no** future days, **no** labeled outcomes across sessions.
- **London box** ends before RTH; **London low / high** for **[02:00, 09:30)** are fixed before the first RTH bar at **09:30**.
- **Post-fill** simulation uses a **pessimistic** same-bar rule when stop and TP both touch (**stop wins**) — conservative, not oracle.

**Whole-session setup reconstruction**

- ``find_setup_long`` / ``find_setup_short`` resolve **stop_hunter ↔ breaker ↔ piercer** with a fixed-point loop over the **entire day’s** highs/lows until convergence (or cap).
- That matches the **written definition**, but it is **stronger information** than you have at an arbitrary clock time mid-session: you only know the **final** converged stop-hunter and piercer **after** enough later bars exist for the iteration to settle.
- Interpretation: the backtest answers “**if** we apply the rule to the **completed** session path, is there a trade and what are the levels?” — not a strict prefix-only, bar-by-bar discretionary simulator.

**Swing confirmation vs limit fill (intrabar)**

- **Piercer** is a **3-bar** swing (needs the bar **after** the pivot). Logical confirmation is at the **close** of that following bar.
- Code starts limit-fill search at bar index **`piercer_i + 1`** (same bar as the last bar needed to confirm the swing). If **`low <= breaker_high`** on that bar, the model can fill **during** the bar — **before** the bar closes — which may be **optimistic** vs “act only after the swing closes.” Tightening would mean: allow fills only from the **next** bar after confirmation (or model explicit intrabar sequence).

The **bearish** script mirrors the same structure; the same caveats apply.

---

## Run the backtest

```bash
cd potions/mnq/v2e/scripts
python3 backtest_london_sweep_breaker.py --all-sl
python3 backtest_london_sweep_breaker.py --sl-at stop_hunter_low --export-csv ../data/mnq_v2e_london_sweep_breaker.csv
```

**``--export-csv``** writes trades for **``--sl-at``** only (default ``stop_hunter_low``). Use ``--all-sl`` for printed comparison of all three stops.

**Inputs:** default ``mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv`` (override ``--1m``). Optional ``--start`` / ``--end`` (YYYY-MM-DD).

---

## Snapshot (workspace defaults, regenerate anytime)

| SL anchor | Occurrences | Σ Net USD | Win rate (Net > 0) | Max DD (leg cum.) | Mean MAE (pts) |
|-----------|------------:|----------:|-------------------:|------------------:|---------------:|
| ``london_low`` | 390 | −\$726.00 | 35.13% | −\$3,932.00 | 46.00 |
| ``breaker_low`` | 456 | +\$4,554.00 | 35.31% | −\$1,511.50 | 37.47 |
| ``stop_hunter_low`` | 456 | +\$13,580.00 | 56.36% | −\$1,330.00 | 57.39 |

Date span scanned: **2021-03-03 → 2026-03-03**. Stop hunter is refined to the **deepest** low before piercer (fixed-point with breaker repick); trade counts can differ by ``--sl-at`` when ``entry <= stop`` rejects a session.

Trade log (default SL export): ``data/mnq_v2e_london_sweep_breaker.csv`` (columns include ``mae_pts``, ``mfe_pts``, levels, ``result``, ``breaker_5m_left``).

---

## Legacy ORB-era files

Older **strict-clean ORB**, **v2b replay**, and **Monte Carlo** tooling still live under ``scripts/``, ``case_studies/``, and ``data/`` from prior research. They are **not** the definition of **v2e** going forward; treat them as archival unless ported to this London sweep spec.

---

## Bearish mirror (short)

The **short** playbook mirrors the bullish definition (London **high**, sweep **up**, breaker from swing **lows**, piercer **below** breaker, limit **sell** at breaker **low**, stop at **stop_hunter_high**, symmetric TP). Implementation: ``bearish/scripts/backtest_london_sweep_breaker_short.py``.

---

## Research: R-multiples, scale-out, and combining both sides

**Script:** ``scripts/study_r_multiple_scaleout.py`` (research only; does not regenerate chart PNGs).

**Definitions (aligned with the live backtests):**

- **R** = ``|entry − stop_hunter|`` (long: ``entry − stop_hunter_low``; short: ``stop_hunter_high − entry``).
- **Same-bar priority:** if stop and target both touch one **1 m** bar, **stop wins** (pessimistic).
- **EOD runner:** last **RTH** close before **16:00** after the usual post-fill cutoff (matches bull module).
- **Scale-out:** enter **2 MNQ** at the model fill; exit **1** at **+1R**; runner stop to **breakeven at entry**; compare runner flat at **2R** vs **EOD**.
- **Economics in the study:** **\$2**/point/contract; **\$3** fees per completed trade (simple **2-lot** assumption — refine with per-fill fees if needed).

**Dataset:** default MNQ 1 m CSV; span **2021-03-03 → 2026-03-03** (workspace default at time of study).

### 3×R before stop (among valid setups)

| Side | n | Hit 3R before SL |
|------|--:|-----------------:|
| Bullish | 456 | **12.06%** |
| Bearish | 486 | **18.93%** |

### 2 MNQ scale-out vs hold to model TP

| Side | Rule | Σ Net (study) | WR (net > 0) | Max DD (study) |
|------|------|--------------:|-------------:|---------------:|
| Bull | Scale-out, runner **@ 2R** | \$23,409.50 | 60.75% | −\$3,074.50 |
| Bull | Scale-out, runner **→ EOD** | \$24,640.00 | 60.75% | −\$2,577.00 |
| Bull | **Hold 2 @ model TP** | **\$27,160.00** | 56.36% | −\$2,660.00 |
| Bear | Scale-out, runner **@ 2R** | \$6,340.00 | 55.35% | −\$6,851.50 |
| Bear | Scale-out, runner **→ EOD** | **\$12,449.50** | 55.35% | −\$4,898.00 |
| Bear | Hold 2 @ model TP | \$7,560.00 | 50.21% | −\$6,275.00 |

**Takeaways:**

- **Runner EOD beats runner @ 2R** for total net and for **max DD** on **both** bull and bear in this study.
- **Bull:** **holding 2 contracts to the model TP** beats both scale-out variants on **Σ Net** (scale-out still raises **win rate** via the +1R peel).
- **Bear:** **scale-out with runner to EOD** beats **holding 2 to model TP** on **Σ Net** and **max DD**.

### Best combination when running **both** strategies together

Treat the two playbooks as **separate edges on the same instrument**: take a **long** when the bull setup validates; take a **short** when the bear setup validates (same session calendar rules as each backtest).

Under the study’s assumptions, the **hybrid that maximizes modeled Σ Net** is:

| Leg | Suggested management |
|-----|----------------------|
| **Bullish fills** | **2 MNQ**, hold both to **model TP** (same pessimistic bar rule as ``backtest_london_sweep_breaker.py``). |
| **Bearish fills** | **2 MNQ** scale-out: **−1 at +1R**, runner stop to **BE at entry**, runner exit **EOD** (not capped at 2R). |

Rough **additive** headline from the same study window (not accounting for same-day overlap, margin stacking, or correlated DD paths): **\$27,160 + \$12,449.50 ≈ \$39,610** vs **\$27,160 + \$7,560 ≈ \$34,720** if both sides used “hold 2 to TP.” **Portfolio max drawdown is not the sum of leg DDs** — use a combined equity simulation if you need a single DD number.

Re-run or extend dates:

```bash
cd potions/mnq/v2e/scripts
python3 study_r_multiple_scaleout.py
```

---

## Porting to Pine Script (brainstorm)

TradingView **Pine** can approximate this playbook, but several Python conveniences do not map one-to-one. Treat the items below as a checklist, not a spec.

**Time and symbol**

- Align **chart timezone** with **America/New_York** (or convert all session boundaries explicitly).
- Prefer **MNQ1!** (continuous) or the front contract your broker mirrors; roll logic on TV differs from CSV stitched history.

**Chart timeframe vs model timeframe**

- Reference logic is **1 m** bars with **5 m** swings anchored **02:00** NY. Options:
  - Run the indicator on **1 m** and **``request.security``** a **5 m** series for swing/breaker logic (mind **lookahead**: use **`lookahead=barmerge.lookahead_off`** and accept **one-bar delay** where TV repaints vs CSV unless you carefully gate updates).
  - Or implement swing/breaker on **5 m** only on-chart and accept **small** divergence from Python’s “5 m built from 1 m aggregate.”

**Sessions**

- Use **`time()`` / session strings** for London **[02:00, 09:30)** and RTH **[09:30, 16:00)**.
- Track **London low** (bull) / **London high** (bear) with **`var`** highs/lows reset per session boundary.

**Stop hunter fixed-point**

- In Pine, implement as **state machine per session**: on each **1 m** close, update candidate SH, recompute breaker slice, scan forward for piercer, repeat until stable **using only bars ≤ current bar** — this matches **live** causality better than the Python “full day” snapshot (results may **differ** slightly from the CSV backtest).
- Cap iterations (e.g. 30) as in Python; **`for`** loops are bounded by Pine limits — keep inner scans modest or precompute incrementally.

**Swings and breaker**

- **Strict** highs (equivalent to Python’s 3-bar swing): e.g. pivot at **prior** bar when ``high[1] > high[2] && high[1] > high`` (confirmed on the **current** bar), or ``ta.pivothigh(high, 1, 1)`` (confirmed **1** bar after the pivot).
- **Breaker** = **last** qualifying **5 m** swing high (bull) from London **02:00** through the **5 m bucket after** stop-hunter’s bucket — reproduce ``pick_breaker_5m_last_swing_through_after_sh_bucket`` with timestamps/bucket math.

**Entry, TP, SL**

- **Limit** at **breaker_high** (bull): Pine **`strategy.entry(..., limit=)`** or indicator alerts; no native partial “touch” without **intrabar** **`process_orders_on_close`** trade-offs.
- **TP** formula uses **final** stop-hunter extreme and **piercer** extreme — update only when those labels are **committed** in your state machine.
- Same-bar **stop vs TP**: use **`strategy.*`** with explicit **`priority`** / bar assumptions to mirror pessimistic stop-first (or document divergence).

**Alerts and orders**

- Prefer **`strategy()`** for backtest parity tests; **`indicator()`** + alerts if you only signal manually.
- **EOD flat**: session-close exit or **`strategy.close_all`** with NY **16:00** rule consistent with **`EOD_CUTOFF`** in Python.

**Validation path**

- Export a **small set** of session dates from ``backtest_london_sweep_breaker.py`` (levels + fill bar) and **manually** compare to Pine on 1 m for those days — fastest way to catch timezone, swing, and bucket bugs.

---

## Related

- **Daily / prior-month variant:** ``daily/README.md`` (daily bars + prior calendar month box).
- Implementation (long): ``scripts/backtest_london_sweep_breaker.py``
- Implementation (short): ``bearish/scripts/backtest_london_sweep_breaker_short.py``
- Study: ``scripts/study_r_multiple_scaleout.py``
- London box clock matches ``v2e/scripts/sim_london_limit_scaleout.py`` (**02:00–09:30** ET).
