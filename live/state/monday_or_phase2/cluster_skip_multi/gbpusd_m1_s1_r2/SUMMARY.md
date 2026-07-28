# GBPUSD M1_S1_R2 — cluster / levels / skip

## Baseline (trade pts)
- n=2912 WR=28.5% net_pts=2.44 mean=0.0008 maxL=23 stress=-0.8 N/S_proxy=3.06

## Cluster verdict
- After exactly 1L, next WR=28.1 (≥≈baseline 28.5) → skip-after-1L likely toxic.
- After exactly 2L, next WR=29.1 (~baseline) → skip-after-2L may be near-neutral.
- After exactly 1W, next WR=26.6 (soft) → skip-1-after-W is a candidate.
- Top-5% heat weeks: n=134 WR=72.4 net=5.6 vs outside net=-3.2 — calendar concentration is structural.

## Calendar
- top week 2008-10-20 net=0.45 share=18.4%
- top 5% weeks share of gross + = 33.4%

## Skip grid (coverage ≥ 50%, ranked by N/S proxy)

| rule | n | WR | net | mean | maxL | cover | stress | N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| skip1_after_W | 2257 | 29.0 | 1.79 | 0.0008 | 22 | 77.5 | -0.48 | 3.74 |
| sitout_week_after_2.00x_p90(0.068622) | 2855 | 28.5 | 2.49 | 0.0009 | 23 | 98.0 | -0.77 | 3.24 |
| sitout_week_after_3L | 2670 | 28.5 | 2.67 | 0.001 | 18 | 91.7 | -0.83 | 3.23 |
| sitout_week_after_4L | 2861 | 28.4 | 2.46 | 0.0009 | 21 | 98.2 | -0.78 | 3.14 |
| take_all | 2912 | 28.5 | 2.44 | 0.0008 | 23 | 100.0 | -0.8 | 3.06 |
| sitout_week_after_p25_pos_week(0.0127812) | 2615 | 28.4 | 2.28 | 0.0009 | 21 | 89.8 | -0.76 | 3.01 |
| sitout_week_after_2.50x_p90(0.085778) | 2884 | 28.5 | 2.35 | 0.0008 | 23 | 99.0 | -0.8 | 2.95 |
| skip1_after_2W | 2746 | 28.6 | 2.41 | 0.0009 | 23 | 94.3 | -0.83 | 2.91 |
