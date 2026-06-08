# Experiment: child partial stop at range midpoint

## Hypothesis

Default **`--child-partial-stop edge`**: child-only contracts flat on partial when price reaches **RH** (long children) or **RL** (short children).

This run uses **`mid`**: partial at **(RH + RL) / 2** — halfway between opening-range boundaries. Tier‑1 wide stop and shared TP are unchanged.

Effect: children need a **deeper** pullback against them before the partial fires vs edge mode (wider child stop in price terms).

## Reproduce

From `potions/mnq/case_studies/v2b_child`:

```bash
python3 orb_open_limit_v2b_child.py \
  --max-child-adds 2 \
  --child-partial-stop mid \
  --out ../v2b_c/experiments/child_stop_midrange/mnq_orb_open_limit_v2b_child_3max_mid.csv
```

Baseline (edge) for comparison:

```bash
python3 orb_open_limit_v2b_child.py \
  --max-child-adds 2 \
  --child-partial-stop edge \
  --out mnq_orb_open_limit_v2b_child_3max.csv
```

Adaptive unified sim (**v2b regime only** uses this flag; v2d still uses edge semantics):

```bash
cd "$(git rev-parse --show-toplevel)/potions/mnq/v2d"
python3 orb_adaptive_50_150_child.py --max-child-adds 2 --child-partial-stop mid --out /tmp/adaptive_mid.csv
```

## Latest snapshot (same DB extract)

Run on `extracted_new/glbx-mdp3-20100606-20260423` MNQ 1m — **1,992 legs**, `--max-child-adds 2`, `slip_ticks=1`:

| `--child-partial-stop` | Σ Net_$ | Win rate (Net_$>0) | Max DD (cum Net_$) |
|------------------------|---------|---------------------|---------------------|
| `edge` (default) | **22,608.00** | 48.4% | **−6,742.00** |
| `mid` | **26,284.75** | 48.3% | **−8,761.00** |

Mid partials **raised** cumulative P/L here but **deepened** peak→trough drawdown vs edge — re‑run after DB updates before trading conclusions.

## Outputs

Written by the commands above, e.g. `mnq_orb_open_limit_v2b_child_3max_mid.csv` in this folder when using the `--out` path from `../v2b_child/`.
