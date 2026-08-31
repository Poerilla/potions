# Prior width vs losses

ES quarterly breakout: prior-range width vs losses.

Hub: live/state/es_quarterly_range_breakout_broker/prior_width_study/
Canvas: es-prior-width-losses.canvas.tsx

What is large? Trade-sample p50=249, p75=447, p90=662 pts. Q4 (large) ~= W>=469.

Do losses congregate on large ranges?
- Dollar losses: YES — Q4 = 57% of loss $ (only 24% of loss trades).
- Edge/skip signal: NO — Q4 win rate 73%, and Q4 nets +$567k (best quartile).
- Width↔net Spearman +0.34 (larger W → more $ net on average).
- Mechanical: mid SL risk = 8*(W/2)*$50 (~$24k Q1 vs ~$136k Q4).

Skip counterfactual (causal pct or abs W): all destroy net (skip 75th → −$1.05M vs baseline).

Stance: do not hard-skip large prior ranges. Soft size-down possible for R smoothing (Q4 avg R 0.22 vs Q1 0.48), not expectancy.
