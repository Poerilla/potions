# EURUSD M1_S2_R2 — cluster / levels / skip

## Baseline (trade pts)
- n=2946 WR=29.0% net_pts=1.36 mean=0.0005 maxL=17 stress=-0.64 N/S_proxy=2.12

## Cluster verdict
- After exactly 1L, next WR=32.8 (≥≈baseline 29.0) → skip-after-1L likely toxic.
- After exactly 2L, next WR=29.7 (~baseline) → skip-after-2L may be near-neutral.
- After exactly 1W, next WR=25.2 (soft) → skip-1-after-W is a candidate.
- Top-5% heat weeks: n=138 WR=69.6 net=4.2 vs outside net=-2.9 — calendar concentration is structural.

## Calendar
- top week 2010-05-03 net=0.18 share=13.1%
- top 5% weeks share of gross + = 36.0%

## Skip grid (coverage ≥ 50%, ranked by N/S proxy)

| rule | n | WR | net | mean | maxL | cover | stress | N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| skip1_after_W | 2263 | 30.2 | 1.53 | 0.0007 | 16 | 76.8 | -0.45 | 3.38 |
| skip1_after_3L | 2550 | 29.5 | 1.6 | 0.0006 | 17 | 86.6 | -0.55 | 2.91 |
| skip2_after_2L | 1874 | 29.5 | 1.45 | 0.0008 | 16 | 63.6 | -0.5 | 2.9 |
| sitout_week_after_3L | 2718 | 29.1 | 1.48 | 0.0005 | 16 | 92.3 | -0.6 | 2.46 |
| skip1_after_2L | 2288 | 28.9 | 1.03 | 0.0004 | 16 | 77.7 | -0.43 | 2.41 |
| sitout_week_after_p50_pos_week(0.017648) | 2713 | 28.9 | 1.35 | 0.0005 | 17 | 92.1 | -0.59 | 2.29 |
| sitout_week_after_p25_pos_week(0.00813) | 2623 | 29.0 | 1.27 | 0.0005 | 17 | 89.0 | -0.55 | 2.29 |
| sitout_week_after_1.00x_p90(0.023295) | 2746 | 29.0 | 1.37 | 0.0005 | 17 | 93.2 | -0.6 | 2.27 |
