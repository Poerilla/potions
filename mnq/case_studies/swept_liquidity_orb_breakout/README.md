# Swept liquidity ORB breakout (MNQ)

**Canonical simulator:** [`resim_scale_in_ladder.py`](./resim_scale_in_ladder.py) — child-based scale-in (first limit L0±15, further adds at qualifying “child” candle closes), per-lot stops (tier-1 **L0±`sl_pts`**; adds use **RH−`child_or_edge`** long / **RL+`child_or_edge`** short), **full exit at TP1**.

**Batch charts** (random sample days with at least one `replay_row` `ok`): from `potions/mnq/case_studies/` run:

```bash
python3 build_random_samples_ladder.py -n 100 --seed 42
```

Output: [`child_ladder_trade_samples/`](./child_ladder_trade_samples/) (`*.png` + `INDEX.md`).  
Input CSV: [`mnq_swept_orb_breakout.csv`](./mnq_swept_orb_breakout.csv).

**Scaling depth:** replay defaults to **`--max-contracts 5`** (tier1 @ L0±15 plus up to four child-based adds). For a 3 vs 5 money/DD comparison (no charts):  
`python3 compare_max_contracts.py`

**All losing trades (`ok` + Net_$ &lt; 0), one chart each:** PNGs under `child_ladder_trade_samples/losses/` (+ `INDEX.md`). Regenerate:

`python3 generate_loss_charts.py`

The older `ladder_trade_samples/` folder (if present from prior runs) is not maintained for the current rules.
