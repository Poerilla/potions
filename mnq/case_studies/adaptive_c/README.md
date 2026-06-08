# adaptive_c — Case studies (**50/150 adaptive + children**, **v2b & v2d**)

Annotated PNGs (same renderer as `../v2b_c/build_case_studies.py` with **`--adaptive`**):

- Legs come from [`mnq/v2d/mnq_orb_results_adaptive_50_150_child_3max.csv`](../../v2d/mnq_orb_results_adaptive_50_150_child_3max.csv) (rerun [`orb_adaptive_50_150_child.py`](../../v2d/orb_adaptive_50_150_child.py) with `--max-child-adds 2`).
- Chart titles label **`Regime=v2b`** as tier‑1 **OCO** fills vs **`Regime=v2d`** as tier‑1 **fade** fills; cyan/magenta segments are child limits when present.

See **`INDEX.md`** in this folder for the batch listing.

Regenerate (stratified **v2b / v2d** days):

```bash
cd ../v2b_c
python3 build_case_studies.py --adaptive --stratify-regimes -n 36 --seed 43 --start 2024-01-01
```
