# v2 short path profile + accumulate refresh

Hub: `/home/tester/hsm/potions/live/state/nq_quarterly_range_v2_review`

## Short path (14 trades)
- Net **$21,962** · WR 43% · avg $1,569
- Median MFE before done: **0.39×W** (0.61R vs mid-stop)
- Median MFE *before mid hit*: **0.39×W** (0.61R)
- Reach ladder rungs: 0.2W 64% · 0.4W 50% · 0.6W 29% · 0.8W 14%
- Hit mid rate 50% · median days-to-MFE 3 · days-to-mid 10.0
- Winners median MFE 0.70W · losers median MFE 0.18W (before mid 0.18W)
- Stop-only shorts: 3 · $-192,052

## Long path (contrast)
- Net **$1,462,088** · WR 70% · median MFE 0.41W / 0.68R · reach 0.4W 52%

## Short policy diagnostics
- Skip all shorts (longs only): **$1,462,088** (Δ $-21,962 vs baseline $1,484,050)
- Short early-fail if <0.2W MFE by day 3 (flatten 8 @ close): **$1,305,306** (Δ $-178,744) — coarse, no ladder
- Same @ day 5: **$1,336,744** (Δ $-147,306)
- Hindsight skip shorts with path MFE<0.2W: **$1,747,590** (Δ $+263,540) — not tradeable

## BB accumulate refresh
Pandas all-in 8: $1,455,738
- **2w_1perd_cap10**: $1,345,096 · avg qty 6.2 · vs all-in $-110,642 · no-fill 1 · better/worse 34/34
- **1w_2contracts_per_week**: $368,299 · avg qty 1.8 · vs all-in $-1,087,439 · no-fill 6 · better/worse 25/43
- **2w_2contracts_per_week**: $671,906 · avg qty 3.7 · vs all-in $-783,832 · no-fill 1 · better/worse 27/41
- **1w_1perd_cap10**: $643,133 · avg qty 2.7 · vs all-in $-812,605 · no-fill 6 · better/worse 26/42

By side (new variants):
- 2w_1perd: longs $1,215,190 (avg qty 5.9) · shorts $129,906 (avg qty 7.0)
- 1w_2perweek: longs $277,827 (avg qty 1.8) · shorts $90,472 (avg qty 2.0)
- 2w_2perweek: longs $573,050 (avg qty 3.7) · shorts $98,856 (avg qty 4.0)

## Stance
- Short path depth is mixed; policy deltas below drive the call.
- Skipping shorts is ~flat to slightly better (Δ $-21,962) — shorts are not earning their keep.
- Best new accum **2w_1perd_cap10** at $1,345,096 vs all-in $1,455,738 — accumulate still lags all-in.

Files: `review/short_path_profile.csv`, `path_profile_all.csv`, `counterfactual_trades_v2.csv`, `short_policy_accum_summary.json`
