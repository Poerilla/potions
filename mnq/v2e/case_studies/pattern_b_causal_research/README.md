# Fib-62 London-high pullback — filled trades (charts)

**Setup (causal 1 m):** First **RTH** touch of **London high**, limit buy at **Fib retracement** from **H toward L** (default φ⁻¹≈0.618), **no London low** before fill; **SL** = London low, **TP** = London high or **EOD** exit. See ``../scripts/study_rth_london_high_fib62_limit_long.py``.

**Charts:** **5 m** OHLC **RTH NY** only (**09:30–16:00** ET); London high/low + Fib limit as horizontal lines; markers for first RTH high touch, fill, exit.

Stratified sample: **50** sessions shown from **441** filled trades (fib ratio **0.618034**).

Generate:

```bash
cd potions/mnq/v2e/scripts
python3 build_fib62_filled_trade_charts.py --max-charts 50
```
