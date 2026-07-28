# USDJPY M2_S3_R2 — cluster / levels / skip

## Baseline (trade pts)
- n=2879 WR=30.7% net_pts=250.46 mean=0.087 maxL=14 stress=-27.89 N/S_proxy=8.98

## Cluster verdict
- After exactly 1L, next WR=32.1 (≥≈baseline 30.7) → skip-after-1L likely toxic.
- After exactly 2L, next WR=31.6 (~baseline) → skip-after-2L may be near-neutral.
- After exactly 1W, next WR=26.9 (soft) → skip-1-after-W is a candidate.
- Top-5% heat weeks: n=146 WR=67.8 net=427.1 vs outside net=-176.7 — calendar concentration is structural.

## Calendar
- top week 2022-11-07 net=12.49 share=5.0%
- top 5% weeks share of gross + = 30.2%

## Skip grid (coverage ≥ 50%, ranked by N/S proxy)

| rule | n | WR | net | mean | maxL | cover | stress | N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| skip1_after_2W | 2702 | 31.1 | 281.73 | 0.1043 | 13 | 93.9 | -23.64 | 11.92 |
| sitout_week_after_2.00x_p90(5.63864) | 2823 | 30.9 | 279.98 | 0.0992 | 14 | 98.1 | -24.75 | 11.31 |
| sitout_week_after_p75_pos_week(3.4981) | 2716 | 30.9 | 282.31 | 0.1039 | 14 | 94.3 | -25.32 | 11.15 |
| sitout_week_after_2.50x_p90(7.0483) | 2848 | 30.8 | 273.19 | 0.0959 | 14 | 98.9 | -27.28 | 10.02 |
| sitout_week_after_1.50x_p90(4.22898) | 2768 | 30.9 | 278.81 | 0.1007 | 14 | 96.1 | -27.98 | 9.96 |
| sitout_week_after_4L | 2839 | 30.8 | 248.38 | 0.0875 | 15 | 98.6 | -25.76 | 9.64 |
| sitout_week_after_3.00x_p90(8.45796) | 2865 | 30.8 | 264.72 | 0.0924 | 14 | 99.5 | -27.89 | 9.49 |
| skip1_after_W | 2188 | 31.6 | 260.64 | 0.1191 | 14 | 76.0 | -27.63 | 9.43 |
