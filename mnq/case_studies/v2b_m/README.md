# v2b_m (MNQ case study)

## Main model (basis)

**v2b_m** is the **primary MNQ case-study model** in this folder: tier‑1 **`mnq_orb_results_stops.csv`** legs filtered to **long-only** setups with **`bullish_break`** monthly bias (no hemisphere by default), **prior-calendar-month-high OR geometry** (`engine.EPS_IDX_PT`), and **no bearish short sleeve**. Exported **`v2b_m_legs.csv`** and **`run_v2b_m.py`** stats describe this book.

Other folders are **variants or experiments** built off the same qualification unless noted (e.g. `limit_retest/`, `../v2b_m_child/`, **`v2b_m_so/`**).

### `v2b_m_so/` — 2-lot scale-out + runner

After the same **v2b_m** filter: enter **2 MNQ** at **RH + tick**, stop **RL**; take **1** at **TP1 = RH + Range**; move runner stop to **RH + 1 tick**; runner targets **TP2 = RH + 2×Range**. Baseline **1-lot** sim included for comparison.

**Full rules, data paths, causality notes for live-style execution, and the published Σ Net / DD snapshot** (363 sessions) are in **`v2b_m_so/README.md`** — written so another operator can reproduce numbers **without reading source code**.

---

**Filter checklist:**

1. **Long-only** — opening-range **Long** legs aligned with the **prior calendar month high** (see `engine.EPS_IDX_PT` slack).
2. **Monthly bias** — default **`bullish_break`** only; **`hemisphere_long`** is optional via `--include-hemisphere` on `run_v2b_m.py` / `build_v2b_m_charts.py`. Pure hemisphere months stay **flat** when that flag is off.
3. **No bearish shorts** — the bearish_break / PM-low short sleeve was dropped from this definition (marginal vs the long book).

Scripts live in this folder:

- **`engine.py`** — qualification rules and summary stats.
- **`run_v2b_m.py`** — print stats and export **`v2b_m_legs.csv`**.
- **`build_v2b_m_charts.py`** — RTH 5 m PNGs under **`charts/`**.
- **`annotate_monthly_interaction_flags.py`** — add causal vs full-session MI cross columns (needs 1 m).
- **`limit_retest/`** — limit-buy-at-RH retest after a **5 m close** breakout (same v2b_m filter); see `limit_retest/README.md`.
- **`../v2b_m_child/`** — tier‑1 sim + optional **child** scale-in (see sibling README).
- **`v2b_m_so/`** — tier‑1 sim **2 MNQ** scale-out + runner to TP2; see **`v2b_m_so/README.md`**.

Typical workflow:

```bash
cd potions/mnq/case_studies/v2b_m
python3 run_v2b_m.py --export-csv ./v2b_m_legs.csv
python3 build_v2b_m_charts.py --from-csv ./v2b_m_legs.csv --max-charts 0
```

`--max-charts 0` plots every row in the CSV. Charts are named `{date}_Long.png`.

## Monthly interaction crosses (causal vs full session)

The monthly-interactions PNG study flags sessions where prior-month **high** or **low** is **crossed**
on **5 m** bars **00:00–16:00 NY**. That end-of-window test is **oracle** if you treat it as an entry filter.

Shared logic: `potions/mnq/rules/monthly_interaction_cross.py`.

To label each leg with:

- **full-session** 5 m crosses (intraday rule only — monthly-interaction PNGs **also** use a **daily-touch**
  pre-filter), and
- **causal** crosses using only bars **before** an NY cutoff (default **09:45**, i.e. end of ORB):

```bash
python3 annotate_monthly_interaction_flags.py \
  --legs ./v2b_m_legs.csv \
  --output ./v2b_m_legs_mi.csv \
  --cutoff 09:45
```

Use `mi_cross_*_thru_cutoff` columns for non-oracle filters at that clock time.
