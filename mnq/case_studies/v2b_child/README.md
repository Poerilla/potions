# v2b_child — OCO tier‑1 (README canon) + optional child scale‑ins

## Rules

### Tier 1 (identical to `scripts/step2_preplaced_stops.py` MNQ path)

- **Opening range:** default **9:30–9:45** ET → RH, RL, Range.
- After range end: resting **buy stop RH + 1 tick**, **sell stop RL − 1 tick** (OCO behaviour in sim).
- **Fill:** trigger ± **`slip_ticks`** (default **1**) × tick size beyond trigger.
- **Bracket:** TP **RH + Range** (long) / **RL − Range** (short); stop **opposite OR boundary** (RL long / RH short).
- **Bracket‑then‑reverse**, max **2** directions/day, bars **before 15:55** for new arms.

### Child adds (optional)

After the **OCO fill**, scan **completed 5 m** bars with **start time strictly after** the fill timestamp:

- **Long:** green candle, entire OHLC **above RH**.
- **Short:** red candle, entire OHLC **below RL**.

Up to **`--max-child-adds`** sequential qualifying bars (default **1** ⇒ at most **2** MNQ; **`2`** ⇒ at most **3** MNQ). Each arms a **limit at that bar’s close**, active from **bar start + 5 minutes**. Fills on **1 m** data when price trades through.

**Split stops:** tier‑1 keeps the **canonical** wide stop (**RL** long / **RH** short). **Child** contracts use a **tighter** stop at the **near range edge** (**RH** long / **RL** short): only those contracts exit there; tier‑1 continues until shared TP or wide stop. **TP remains shared** for whatever contracts remain. After a partial child stop‑out, pending child limits are cancelled. Intrabar ordering: **target → wide stop → tight partial →** additional limit fills on that bar (conservative).

## Outputs

| File | CLI |
|------|-----|
| `mnq_orb_open_limit_v2b_child.csv` | `--max-child-adds 1` (default) |
| `mnq_orb_open_limit_v2b_child_3max.csv` | `--max-child-adds 2` |

Columns include **`Tier1_Entry`**, **`TP_Price`**, **`Stop_Price`**, **`Contracts`**, **`Child_*`**, **`Entry_Time`**, **`Exit_Time`** for charting.

## Performance (regenerated in-session; re‑run to refresh)

Using the same DB span as step2 (**1992 legs** on current extract):

| Mode | Σ **Net_$** | Peak→trough **Max DD** (cumulative Net_$) | Notes |
|------|-------------|-------------------------------------------|--------|
| `--max-child-adds 0` | **$16,283.50** | **−$4,716** | Pure tier‑1 (step2‑style); slip_ticks=1 |
| `--max-child-adds 1` | **$20,602.50** | **−$5,609.50** | ~58% of legs take ≥1 child |
| `--max-child-adds 2` | **$22,608.00** | **−$6,742** | Split stops on adds (see trade‑off note below) |

**PnL vs drawdown:** Expect a modest **trade‑off**: split stops improve **peak‑to‑trough** drawdown on cumulative Net_$ versus modelling **one shared wide stop** on the whole scaled position (older headline Σ Net_$ was higher in that regime, with deeper tails). Whether that trade‑off is acceptable is a portfolio/risk preference.

**Later research:** Putting **every** contract on the **tier‑1 wide stop only** (no tighter child exit at the near edge) remains a plausible variant to backtest—simpler risk semantics and potentially higher Σ Net at the cost of heavier DD paths.

Unified **adaptive 50/150** (`orb_adaptive_50_150_child.py`, **`--max-child-adds 2`**): **1920 legs**, Σ **$22,020**, Max DD **−$5,411.50** (same DB / slip).

Compare vs canon:

```bash
python3 compare_v2b_side_by_side.py --child mnq_orb_open_limit_v2b_child.csv
python3 compare_v2b_side_by_side.py --child mnq_orb_open_limit_v2b_child_3max.csv
```

### Adaptive 50/150 unified backtest (recommended)

[`mnq/v2d/orb_adaptive_50_150_child.py`](../../v2d/orb_adaptive_50_150_child.py) runs **one** intraday simulator per session: **MA50 vs MA150** (prior close, causal) selects **v2b OCO + children** or **v2d fade + children**. Child rules match this README on **both** arms.

```bash
cd "$(git rev-parse --show-toplevel)/potions/mnq/v2d"
python3 orb_adaptive_50_150_child.py --max-child-adds 1 --out mnq_orb_results_adaptive_50_150_child.csv
```

Latest snapshot on this DB (split stops, slip_ticks=1): **`max_child_adds=2`** → **1920 legs**, Σ **$22,020**, Max DD **−$5,411.50** (see Performance table). Re‑run `orb_adaptive_50_150_child.py` with desired `--max-child-adds` / `--out` to refresh; regime‑split totals move when simulation rules change—cross‑check CSV output rather than older attribution tables below without re‑running joins.

### Adaptive inside-v2b parent-entry study

[`mnq/v2d/orb_adaptive_50_150_inside_v2b_child.py`](../../v2d/orb_adaptive_50_150_inside_v2b_child.py) keeps the same adaptive 50/150 router and leaves **v2d unchanged**, but replaces the **v2b parent OCO stop** with a causal **inside opposing 5 m candle limit** after a 5 m breakout close. Child adds, v2b target, and v2b parent stop semantics remain aligned with this README.

Latest close-price run, `--max-child-adds 2`: **1254 legs**, Σ **$15,144.50**, Max DD **−$3,542**, PF **1.18**. This reduced drawdown but cut too much v2b trade flow versus the current adaptive child leader (**$22,020**, Max DD **−$5,411.50**). Treat it as a selectivity experiment, not the current best adaptive candidate. Full details: [`ADAPTIVE_INSIDE_V2B_STUDY.md`](ADAPTIVE_INSIDE_V2B_STUDY.md).

### Adaptive regime attribution (CSV join — diagnostic only)

Joins `Date` + `Trade_Direction` to `mnq/v2d/mnq_orb_results_adaptive_50_150.csv` so each **child** row inherits **`Regime`** (`v2b` vs `v2d`). **Does not** re‑simulate “adaptive + children” end‑to‑end — prefer **`orb_adaptive_50_150_child.py`** above for regime‑honest totals.

```bash
python3 report_adaptive_v2bc.py --child mnq_orb_open_limit_v2b_child.csv
python3 report_adaptive_v2bc.py --child mnq_orb_open_limit_v2b_child_3max.csv
```

Adaptive (~1,919 legs) and child (~1,991) **do not share the same calendar universe**: ~224 **`Trade_Direction`**+**`Date`** keys exist **only** in the child CSV (~152 only in adaptive). The script prints Σ Net_$ on **child‑only** legs in the warning line.

**Important:** Regime tables below use **only** the **intersection** (~1,767 legs). On that subset Σ Net_$ is **−$9,296** (+1 add) / **−$10,707** (+2 adds) while almost all headline child P&L sits on **child‑only** legs (no `Regime` label): **+$37,212** / **+$44,976** respectively. Read the regime split as **within‑intersection** attribution, not as explaining the **~$27.9k / ~$34.3k** totals.

**Latest printed totals — intersection only (re‑run script to refresh):**

| Child CSV | Regime | legs | Σ Net_$ (child) | Σ Net_$ (canon adaptive, same legs) |
|-----------|--------|------|-------------------|-------------------------------------|
| `...v2b_child.csv` (+1 add) | v2b | 1436 | **+$24,910** | +$15,928 |
| | v2d | 331 | **−$34,206** | +$28,003 |
| `..._3max.csv` (+2 adds) | v2b | 1436 | **+$27,983** | +$15,928 |
| | v2d | 331 | **−$38,689** | +$28,003 |

Within the intersection (labels pasted from adaptive CSV onto **`v2b_child`**‑only rows — **different universe** than [`orb_adaptive_50_150_child.py`](../../v2d/orb_adaptive_50_150_child.py)): scale‑ins **add** vs canon adaptive on **`v2b`‑labeled** legs but **subtract heavily** on **`v2d`‑labeled** legs — compare against unified sim if you need apples‑to‑apples **`Regime`** P&L.
