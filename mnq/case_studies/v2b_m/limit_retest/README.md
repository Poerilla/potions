# v2b_m limit retest (boundary limit)

Runs **`run_limit_retest.py`**: same **v2b_m** qualification as `../engine.py` (long-only, default `bullish_break`, PM-high geometry). Execution is **not** the tier‑1 OCO breakout:

1. **Signal:** first **5 m** close **≥ RH + 1 tick** after OR **[09:30, 09:45)** (RTH bars, anchor 09:30).
2. **Fill:** **limit at RH** once price trades there **after** the signal bar closes (1 m path).
3. **Risk/reward:** stop **RL**, target **RH + Range** (canonical v2b bracket).

```bash
cd potions/mnq/case_studies/v2b_m/limit_retest
python3 run_limit_retest.py --out ./v2b_m_limit_retest_legs.csv
```

Optional: `--include-hemisphere` to match hemisphere-long allowance on the filter side only.
