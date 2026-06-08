# Adaptive 50/150 Inside-v2b Parent Entry Study

This study keeps the adaptive router and v2d implementation unchanged, but replaces v2b parent stop entries with a causal inside-opposite 5-minute limit entry.

v2b inside entry rules:

- Opening range remains 09:30-09:45 ET.
- A v2b setup arms only after a 5-minute candle closes beyond the opening range in the breakout direction.
- Parent limit price uses the selected inside opposing candle `close`.
- Longs use the most recent consecutive red 5-minute candle/run fully inside the opening range; shorts use the most recent consecutive green run.
- For a long run, the highest selected price in the run is used; for a short run, the lowest selected price is used.
- Initial parent stop remains v2b-style: range low for longs, range high for shorts.
- Target remains v2b-style: range high + range for longs, range low - range for shorts.
- Child adds and child partial stops use the same legacy v2b_child mechanics as the current adaptive child model.
- Pending parent limits are cancelled if TP1 trades before fill.

Max child adds: `2`.

| Variant | Legs | v2b legs | v2d legs | Net | Max DD | Win rate | PF | v2b net | v2d net | Child add rate | Parent cancels | CSV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| current adaptive v2b_child/v2d | 1920 | 1437 | 483 | $22,020.00 | $-5,411.50 | 49.69% | 1.14 | $19,063.00 | $2,957.00 | 43.65% | n/a | `/home/tester/hsm/potions/mnq/v2d/mnq_orb_results_adaptive_50_150_child_3max.csv` |
| adaptive inside-v2b close limit | 1254 | 771 | 483 | $15,144.50 | $-3,542.00 | 40.03% | 1.18 | $12,187.50 | $2,957.00 | 21.53% | 12824 | `potions/mnq/v2d/mnq_orb_results_adaptive_50_150_inside_v2b_close_child_3max.csv` |

## Outputs

- Study CSV: `potions/mnq/v2d/mnq_orb_results_adaptive_50_150_inside_v2b_close_child_3max.csv`
- Parent cancel CSV: `potions/mnq/v2d/mnq_orb_results_adaptive_50_150_inside_v2b_close_child_3max.csv.parent_cancels.csv`
