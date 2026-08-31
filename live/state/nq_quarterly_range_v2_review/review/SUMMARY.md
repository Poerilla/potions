# v2 ladder review

NQ quarterly v2 ladder review + 4H BB accumulate counterfactual.

Hub: live/state/nq_quarterly_range_v2_review/
Ledger: TRL-2026-00106
Canvas: nq-v2-ladder-review.canvas.tsx

V2 broker: 68 trades | net +$1.48M | N/S 2.94

Profit sources:
- Longs $1.46M / shorts ~$22k
- scaled_then_eoq +$1.91M (28) · scaled_full +$538k (10)
- Fill reasons: flatten + tp1-4 fund book; stops -$1.08M
- Top 5 winners = 38% of win $; 2025 alone ~31% of total net

Loss concentration:
- stop_only 10 trades -$869k
- Worst 5 = 63% of loss dollars (2024-07-04 -$266k largest)

4H BB mid accumulate (same signals, mid SL + 0.2W ladder):
- 2/day x 5d (cap 10): +$1.15M, avg qty 5.4, -$310k vs all-in
- 1/day x 10d: +$1.35M, avg qty 6.2, -$111k vs all-in
- Entry improve median ~5 pts — not enough vs delayed/undersized fills
- Stance: keep all-in entry for v2; accumulate does not help

Files: review/summary.json, counterfactual_trades.csv, by_*.csv
