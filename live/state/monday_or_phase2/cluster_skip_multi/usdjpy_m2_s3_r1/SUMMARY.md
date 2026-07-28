# USDJPY M2_S3_R1 — cluster / levels / skip

## Baseline (trade pts)
- n=2402 WR=30.8% net_pts=240.89 mean=0.1003 maxL=13 stress=-24.71 N/S_proxy=9.75

## Cluster verdict
- After exactly 2L, next WR=28.7 (soft vs 30.8) → skip-1-after-2L is a candidate.
- After exactly 1W, next WR=28.3 (soft) → skip-1-after-W is a candidate.
- Top-5% heat weeks: n=112 WR=68.8 net=405.9 vs outside net=-165.0 — calendar concentration is structural.

## Calendar
- top week 2022-11-07 net=14.42 share=6.0%
- top 5% weeks share of gross + = 29.8%

## Skip grid (coverage ≥ 50%, ranked by N/S proxy)

| rule | n | WR | net | mean | maxL | cover | stress | N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| sitout_week_after_1.00x_p90(2.97578) | 2298 | 30.9 | 264.96 | 0.1153 | 12 | 95.7 | -24.61 | 10.77 |
| sitout_week_after_p75_pos_week(3.4393) | 2318 | 30.9 | 263.46 | 0.1137 | 12 | 96.5 | -24.61 | 10.71 |
| skip1_after_W | 1831 | 31.2 | 228.82 | 0.125 | 13 | 76.2 | -21.98 | 10.41 |
| sitout_week_after_p25_pos_week(0.9338) | 2209 | 30.8 | 254.1 | 0.115 | 12 | 92.0 | -24.61 | 10.33 |
| sitout_week_after_2.50x_p90(7.43945) | 2389 | 30.8 | 255.33 | 0.1069 | 13 | 99.5 | -24.71 | 10.33 |
| sitout_week_after_1.50x_p90(4.46367) | 2357 | 30.9 | 254.53 | 0.108 | 13 | 98.1 | -24.71 | 10.3 |
| sitout_week_after_2.00x_p90(5.95156) | 2379 | 30.9 | 254.39 | 0.1069 | 13 | 99.0 | -24.71 | 10.3 |
| sitout_week_after_p50_pos_week(1.88405) | 2240 | 30.7 | 252.12 | 0.1126 | 12 | 93.3 | -24.61 | 10.25 |
