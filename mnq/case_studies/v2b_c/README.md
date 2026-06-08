# v2b_c — Annotated charts for **v2b_child**

Not a separate simulator: PNGs are generated from the **`v2b_child`** CSV (default: **3‑contract cap** run). Tier‑1 matches **README canon OCO** (`step2_preplaced_stops.py`); children arm after the OCO fill per `orb_open_limit_v2b_child.py`.

## What the charts show

- **5 m** candles, RH / RL band, RH±tick guide ticks  
- **Gold** marker: tier‑1 **OCO stop fill** (`Tier1_Entry`)  
- **Cyan**: first child limit segment + fill (`Child_*`)  
- **Magenta**: second child (when `--max-child-adds 2`)  
- **Green / red** spans: TP (`TP_Price`) / stop (`Stop_Price`) from CSV  

Footer text reflects **README canon** stops at RL/RH — **not** session‑open ± range.

## Generate

Requires CSV from sibling folder:

```bash
cd ../v2b_child
python3 orb_open_limit_v2b_child.py --max-child-adds 2 --out mnq_orb_open_limit_v2b_child_3max.csv

cd ../v2b_c
python3 build_case_studies.py -n 36 --seed 43 --start 2024-01-01
python3 build_case_studies.py --dates 2025-03-31   # specific days
```

Outputs **`INDEX.md`** unless `--dates` only.

## Adaptive (50/150 + **v2b** & **v2d** children)

Unified simulator output → PNG/s default to **`../adaptive_c/`** when using **`--adaptive`**:

```bash
cd ../../v2d
python3 orb_adaptive_50_150_child.py --max-child-adds 2 --out mnq_orb_results_adaptive_50_150_child_3max.csv

cd ../case_studies/v2b_c
python3 build_case_studies.py --adaptive --stratify-regimes -n 36 --seed 43 --start 2024-01-01
```

See **`../adaptive_c/README.md`**.

See also: **`../STRATEGY_TRACKER.md`**.
