# v2b_m_so — scale-out runner (2 MNQ)

Experimental execution on the **v2b_m** universe: same qualified **Long** sessions as the main case study, but **two contracts** at entry with **partial at TP1** and a **runner** to **TP2**.

This document states **every rule** needed to reproduce the numbers **without opening Python** (instrument assumptions and discrete choices are explicit). For automation, run `run_v2b_m_so.py` with the same inputs.

---

## 1. Instrument and accounting

| Parameter | Value |
|-----------|--------|
| Symbol | **MNQ** (micro E-mini Nasdaq-100 futures) |
| Tick size | **0.25** index points |
| PnL multiplier | **\$2** per index point **per contract** (MNQ notional convention used throughout this repo) |
| Commission | **\$1.50** round-trip **per contract** closed (applied each time a contract is fully exited; scale-out closes twice on TP1+TP2 path → **\$3.00** fees that day from two partial exits) |

---

## 2. Session clock (New York)

All times are **America/New_York**.

| Concept | Time |
|---------|------|
| Regular trading hours (RTH) for simulation | **[09:30, 16:00)** — first minute ≥ 09:30, last minute with time **before** 16:00 |
| Opening range (OR) | **09:30–09:45** inclusive start, exclusive end of “after OR” logic: signals/fills use bars **from 09:45 onward** |
| Intraday flatten cutoff | No new TP/SL logic after bar timestamp **≥ 15:59**. If still open, **EOD exit** at **last RTH 1-minute bar’s close** for that session day **before** 16:00 |

---

## 3. Data inputs (reproducibility)

Reproduction requires:

1. **Tier‑1 legs CSV** — default `potions/mnq/mnq_orb_results_stops.csv`  
   - One row per simulated leg in the **canonical v2b** book (OCO bracket long/short from opening range; see workspace `case_studies/STRATEGY_TRACKER.md`).  
   - Columns used here include at minimum: **`Date`**, **`Trade_Direction`**, **`Range_High`**, **`Range_Low`**, **`Range`**, **`Net_$`**, **`Result`** (the last two **only** for the “CSV reference” column — **not** for live signals).

2. **MNQ daily bars (front contract)** — default DBN  
   `potions/mnq/raw/glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst`  
   - **Highest volume** MNQ symbol per **calendar day** (same loader as `plot_daily_prior_month_levels.load_mnq_front_daily`).

3. **MNQ 1-minute bars** — default CSV  
   `potions/mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv`  
   - Session filter and **front-month-by-volume** per calendar day match `annotate_mnq_v2b_range_context` usage in `run_v2b_m_so.py`.

**Overlap requirement:** The script only scores sessions present in **both** the qualified leg list **and** the 1-minute file date range. Published snapshot used **363** sessions (all qualified v2b_m legs in range had a tier‑1 sim fill).

---

## 4. v2b_m filter — which sessions are in the book

A session **qualifies** if **all** of the following hold:

### 4.1 Monthly bias (`bullish_break` only — default)

Classification uses **completed calendar months only** (causal at the start of the session’s month). Implementation: `potions/mnq/rules/monthly_opening_range_bias.py` → `monthly_orb_bias_for_session_date`.

Summary of buckets used elsewhere in v2b; **v2b_m default** requires **`bucket == bullish_break`**:

- **bullish_break:** Prior month **took out** (high **>** two-months-ago high, tick-aware epsilon) **and** prior month **closed above** that older high → long ORB allowed for this script’s universe.

Other buckets (`bearish_break`, `hemisphere_*`, `ambiguous`, `insufficient_data`) → **excluded** unless you change engine flags (this study does **not** use `--include-hemisphere`).

Tick epsilon for monthly extremes: **0.0025** index points (`0.01 × 0.25` tick).

### 4.2 Row from tier‑1 CSV

- **`Trade_Direction == Long`** (short sleeves discarded for v2b_m).

### 4.3 Opening range vs **prior calendar month high** (geometry)

Let:

- **RH** = `Range_High`, **RL** = `Range_Low` from the tier‑1 CSV row (opening range for that session as recorded in that book).
- **pm_high** = high of the **prior completed calendar month** on the **same** MNQ daily continuous series (see `prior_month_levels_series`).

Slack constant **`EPS_IDX_PT = 1.0`** index points (`potions/mnq/case_studies/v2b_m/engine.py`).

Geometry passes if **either**:

1. **Floor at/above prior-month high:** `RL >= pm_high − EPS_IDX_PT`, **or**  
2. **Ceiling at/below prior-month high:** `RH <= pm_high + EPS_IDX_PT`.

If neither tag applies → session **excluded**.

---

## 5. Simulated execution — tier‑1 fill (both baseline and scale-out)

These rules define **first fill**; they intentionally **do not** mirror every micro-detail of historical CSV generation (e.g. full OCO bracket-then-reverse), which is why **CSV Net_$** and **sim baseline Net_$** can differ slightly.

- **Trigger price:** **RH + 1 tick** = **RH + 0.25**.
- **Fill time:** First **1-minute RTH bar** with **`high >= RH + 0.25`**, scanning bars **from 09:45 NY onward** through session.
- **Fill price:** **RH + 0.25** (no additional slippage beyond stop price).
- **Initial stop (both contracts):** **RL** (full opening-range low).

---

## 6. Baseline — 1 contract (comparison arm)

- **Qty:** 1 MNQ from fill until flat.
- **Take-profit:** **RH + Range** (one full measured move up from RH).
- **Stop:** **RL**.
- **Bar-resolution ordering (pessimistic):** On each minute, if **both** stop and target could trade inside the range, **stop is assumed first** (worst case).
- **Fees:** **\$1.50** RT once when position closes.
- **EOD:** If neither hit before cutoff per **Section 2**, flatten at last RTH close before **16:00**; **\$1.50** RT still applies.

---

## 7. Scale-out — `v2b_m_so` (2 contracts)

- **Qty at entry:** **2 MNQ** at the same fill (**RH + 0.25**).
- **Initial stop:** **RL** for **both** until first exit.

**After fill:**

1. **TP1:** **RH + Range** — exit **one** contract (take profit = classic tier‑1 target).
2. Immediately model runner stop **raised** to **RH + 1 tick** (= **RH + 0.25**, breakeven vs tier‑1 fill price).
3. **TP2:** **RH + 2 × Range** — runner limit/stop target.

**Ordering (pessimistic, per minute):**

- While **2 contracts** remain: if both **RL** and **TP1** touch the bar, **RL first** → full **2-lot** loss.
- On the **same bar** as TP1 fills **one** lot: evaluate runner **before** TP2 on that bar — if **RH + tick** and TP2 both trade in one minute, **runner stop first**.

**Fees:** **\$1.50** per **each** contract closed (partial at TP1 pays once; runner exit pays once).

**EOD:** Any remaining size flattened at last RTH close before **16:00** with **\$1.50** per contract still open.

**Labels (printed WR):** Full TP2 → **Win**; EOD wins/labeled **EOD-Win** etc.; **Runner-BE** mapped to **Win**/**Loss** by **net_usd > 0** for TP-style consistency where applicable.

### 7b. Scale-out — **3 MNQ** (1 @ TP1, 2 @ TP2)

Same pessimistic ordering and fee convention as Section 7, but:

- **Entry:** **3** contracts at **RH + 0.25**, initial stop **RL** on all three.
- **TP1:** exit **one** lot at **RH + Range**; pay **\$1.50** RT for that fill.
- **Runners:** **two** contracts remain; stop raised to **RH + one tick**; target **RH + 2×Range** for **both** (they flat together at TP2 or runner stop).
- **Worst case before TP1:** full **3-lot** loss to **RL** (three round-trip fees).

The driver script also prints **Σ Net / |max DD (leg cumulative)|** across the **1ct / 2ct / 3ct** arms on the **same** 363 sessions for a crude efficiency comparison (not annualized).

---

## 8. Published snapshot (same inputs as defaults in script)

Run:

```bash
cd potions/mnq/case_studies/v2b_m/v2b_m_so
python3 run_v2b_m_so.py
```

Optional export of per-day sim vs baseline:

```bash
python3 run_v2b_m_so.py --export-csv ./v2b_m_so_compare.csv
```

**Results (363 overlapping sessions, tier‑1 sim fill on all):**

| Book | Σ Net USD | TP-style WR (Win \| EOD-Win) | Positive-net WR | Max DD (leg cumulative) | Max DD (daily sum) |
|------|-----------|------------------------------|-----------------|-------------------------|---------------------|
| **CSV reference** — `mnq_orb_results_stops` filtered to v2b_m Long legs | **\$3,936.00** | 54.82% | 54.55% | −\$1,106.00 | −\$511.00 |
| **Sim baseline** — 1 MNQ, Section 6 | **\$3,795.00** | 54.27% | 54.27% | −\$1,089.50 | −\$649.50 |
| **Sim v2b_m_so** — 2 MNQ, Section 7 | **\$9,418.00** | 54.27% | 54.27% | −\$2,193.00 | −\$899.00 |
| **Sim v2b_m_so** — 3 MNQ, Section 7b | **\$15,041.00** | 54.27% | 54.27% | −\$3,381.50 | −\$1,299.50 |

**Risk efficiency (Σ Net / |max DD leg|, same 363 legs):** baseline **1ct ≈ 3.48**, **2ct ≈ 4.30**, **3ct ≈ 4.45** — larger scale-out improves dollars **and** this simple efficiency ratio on this sample, while **absolute** drawdown deepens with position count.

**Scale-out path counts (2ct and 3ct share the same TP1/TP2 touch logic):** TP1 hit (≥1 lot): **166 / 363**; TP2 runner(s) hit: **61 / 363**.

---

## 9. Is the tier‑1 CSV / `v2b_m_legs` usable for **live** testing?

**Signals (whether you may place the trade)** — **yes, if you follow causality:**

| Information | Knowable at execution time? |
|-------------|-------------------------------|
| Monthly bias (`bullish_break`) | **Yes** — uses **prior completed months** only on daily closes. |
| Prior-month **high** for geometry | **Yes** — prior **completed** calendar month levels. |
| **RH, RL, Range** | **Yes** — after OR ends (**09:45** NY), same as strategy definition. |
| Bracket prices (buy stop RH+tick, SL RL, TP RH+R, etc.) | **Yes** — arithmetic from RH/RL/Range. |

**What you must *not* use for real-time decisions**

- **`Result`**, **`Net_$`**, **`Entry_Price`**, **`Exit_Price`** (and similar) in `mnq_orb_results_stops.csv` are **outcomes of an offline replay** of the full **OCO / bracket-then-reverse** engine. They are valid for **historical benchmarking**, not as **inputs** to whether today’s setup qualifies.  
- **`tp_hit`** / any column derived from realized PnL — **exclude** from filters.

**Executable live playbook (conceptual)**

1. After **09:45 NY**, compute RH/RL/Range for MNQ from your feed (same OR definition as research).  
2. From daily history through **yesterday**, compute monthly bias; require **`bullish_break`**.  
3. Compute **pm_high** for the **prior completed calendar month**; apply geometry **Section 4.3** with **EPS_IDX_PT = 1.0**.  
4. If qualified, arm **Long**: buy stop **RH + 0.25**, stop **RL**, targets per baseline or scale-out (**Sections 6–7b**).

**Caveats**

- **CSV vs sim mismatch:** Canonical CSV includes short bracket legs, re-arming, slip/cutoff rules documented in `STRATEGY_TRACKER.md`; this folder’s **sim** uses the simplified **Sections 5–7** path — expect **different dollars** from CSV even on the same calendar filter.  
- **Liquidity / partially filled stops / broker ordering** can diverge from **1-minute pessimistic** assumptions.  
- **Front-month rolls** must match your data policy (`annotate_mnq_v2b_range_context` logic for replication).

---

## 10. Related files

| File | Role |
|------|------|
| `run_v2b_m_so.py` | Loads legs; baseline **1ct**, scale-out **2ct** + **3ct**; prints Section 8 tables + efficiency |
| `../engine.py` | v2b_m qualification |
| `../run_v2b_m.py` | Export `v2b_m_legs.csv` from same rules |
| `../../rules/monthly_opening_range_bias.py` | Monthly bucket definitions |
