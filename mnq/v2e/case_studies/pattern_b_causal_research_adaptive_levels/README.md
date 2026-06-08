# Fib-62 adaptive levels — filled trades (charts)

**Rules:** Effective low ``L_eff = min(London_low, running RTH low from 09:30)``. Arm on first RTH touch of **London high**. **Fib limit** from adaptive ``H_ref`` (starts at arming-bar high; ratchets up on higher highs before fill) toward ``L_eff``. **SL** = ``L_eff`` each bar (dynamic). **TP** = **London high**. See ``../scripts/study_rth_london_high_fib62_adaptive_levels.py``.

**Charts:** **5 m RTH** candles; London high (TP), London low (dotted), snapshot **effective floor @ fill**, optional **H_ref @ fill** when above London high, limit fill level, event markers.

Stratified sample: **50** charts from **498** fills (fib **0.618034**).

```bash
cd potions/mnq/v2e/scripts
python3 build_fib62_adaptive_levels_charts.py --max-charts 50
```
