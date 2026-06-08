# Adaptive 50/150 scaleout vs monthly ORB bias

This applies the causal monthly ORB state to the exported 2-contract adaptive 50/150 scaleout legs.

- Monthly OR = first 3 daily bars of the calendar month.
- Trade-day state uses the prior daily close only.
- `outside only` means prior close was above the monthly OR high or below the monthly OR low; direction alignment is not required.
- `aligned only` means Long only in bullish monthly state and Short only in bearish monthly state.

## Headline

- Baseline scaleout: 1,831 legs, $30,218.50, trade DD $-7,498.00, daily DD $-7,470.50.
- Monthly outside-only: kept 1,079 legs and removed 752; net changed by $-5,650.00 and gross contract-points changed by -3,953.00.
- Outside-only trade DD changed by $1,141.00; daily DD is $-6,278.00.
- Direction-aligned-only net changed by $-21,140.00.
- Filtering only v2b by outside state while leaving v2d unchanged changed net by $-7,984.00.
- Filtering only v2d to monthly-aligned rows while leaving v2b unchanged changed net by $6,590.00.
- Diagnostic regime-specific state selection, v2b opposed plus v2d aligned, changed net by $-9,511.00.

## Metrics

| Segment | Trades | Days | Net | Gross pts | Net pt equiv | Trade DD | Daily DD | Win rate | PF | TP1 | TP2 | Avg/trade |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| full adaptive scaleout baseline | 1831 | 1281 | $30,218.50 | 17,855.75 | 15,109.25 | $-7,498.00 | $-7,470.50 | 53.69% | 1.12 | 46.04% | 18.02% | $16.50 |
| full scaleout, monthly outside only | 1079 | 762 | $24,568.50 | 13,902.75 | 12,284.25 | $-6,357.00 | $-6,278.00 | 55.42% | 1.17 | 47.08% | 19.37% | $22.77 |
| full scaleout, monthly aligned only | 529 | 529 | $9,078.50 | 5,332.75 | 4,539.25 | $-8,111.50 | $-8,111.50 | 56.52% | 1.13 | 47.07% | 17.20% | $17.16 |
| full scaleout, monthly opposed only | 550 | 550 | $15,490.00 | 8,570.00 | 7,745.00 | $-6,391.00 | $-6,391.00 | 54.36% | 1.21 | 47.09% | 21.45% | $28.16 |
| full scaleout, monthly neutral/building only | 752 | 519 | $5,650.00 | 3,953.00 | 2,825.00 | $-10,677.50 | $-10,677.50 | 51.20% | 1.05 | 44.55% | 16.09% | $7.51 |
| full scaleout, v2b outside only; v2d unchanged | 1242 | 892 | $22,234.50 | 12,980.25 | 11,117.25 | $-7,063.00 | $-7,063.00 | 54.59% | 1.13 | 46.94% | 18.60% | $17.90 |
| full scaleout, v2b aligned only; v2d unchanged | 815 | 737 | $2,488.50 | 2,466.75 | 1,244.25 | $-10,006.00 | $-10,006.00 | 53.13% | 1.02 | 45.64% | 16.44% | $3.05 |
| full scaleout, v2b opposed only; v2d unchanged | 828 | 750 | $14,117.50 | 8,300.75 | 7,058.75 | $-7,063.00 | $-7,063.00 | 53.26% | 1.12 | 46.74% | 19.32% | $17.05 |
| full scaleout, v2d outside only; v2b unchanged | 1668 | 1151 | $32,552.50 | 18,778.25 | 16,276.25 | $-6,800.00 | $-6,449.50 | 54.14% | 1.14 | 46.04% | 18.47% | $19.52 |
| full scaleout, v2d aligned only; v2b unchanged | 1545 | 1073 | $36,808.50 | 20,721.75 | 18,404.25 | $-5,190.00 | $-4,958.00 | 54.95% | 1.18 | 46.60% | 18.58% | $23.82 |
| full scaleout, v2d opposed only; v2b unchanged | 1553 | 1081 | $31,591.00 | 18,125.00 | 15,795.50 | $-7,243.50 | $-7,077.00 | 54.15% | 1.15 | 46.04% | 18.54% | $20.34 |
| diagnostic: v2b opposed only + v2d aligned only | 542 | 542 | $20,707.50 | 11,166.75 | 10,353.75 | $-3,452.00 | $-3,452.00 | 56.64% | 1.29 | 48.71% | 21.59% | $38.21 |
| v2b baseline | 1430 | 958 | $35,847.00 | 20,068.50 | 17,923.50 | $-5,190.00 | $-4,958.00 | 55.03% | 1.19 | 46.64% | 18.67% | $25.07 |
| v2b monthly outside only | 841 | 569 | $27,863.00 | 15,193.00 | 13,931.50 | $-5,699.00 | $-5,686.00 | 57.31% | 1.28 | 48.39% | 19.98% | $33.13 |
| v2b monthly aligned only | 414 | 414 | $8,117.00 | 4,679.50 | 4,058.50 | $-7,127.00 | $-7,127.00 | 57.25% | 1.17 | 47.34% | 17.15% | $19.61 |
| v2b monthly opposed only | 427 | 427 | $19,746.00 | 10,513.50 | 9,873.00 | $-2,755.00 | $-2,755.00 | 57.38% | 1.39 | 49.41% | 22.72% | $46.24 |
| v2d baseline | 401 | 323 | $-5,628.50 | -2,212.75 | -2,814.25 | $-12,127.00 | $-12,099.50 | 48.88% | 0.92 | 43.89% | 15.71% | $-14.04 |
| v2d monthly outside only | 238 | 193 | $-3,294.50 | -1,290.25 | -1,647.25 | $-9,577.50 | $-9,402.50 | 48.74% | 0.92 | 42.44% | 17.23% | $-13.84 |
| v2d monthly aligned only | 115 | 115 | $961.50 | 653.25 | 480.75 | $-3,945.50 | $-3,945.50 | 53.91% | 1.05 | 46.09% | 17.39% | $8.36 |
| v2d monthly opposed only | 123 | 123 | $-4,256.00 | -1,943.50 | -2,128.00 | $-7,460.00 | $-7,460.00 | 43.90% | 0.82 | 39.02% | 17.07% | $-34.60 |

## Kept outside-only rows

| regime | bias_alignment | monthly_bias | direction | trades | days | net_usd | gross_contract_points | win_rate | avg_trade_usd | tp2_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2b | opposed | bullish | Short | 293 | 293 | $14,062.00 | 7,470.50 | 58.36% | $47.99 | 24.91% |
| v2b | aligned | bullish | Long | 295 | 295 | $8,857.00 | 4,871.00 | 57.97% | $30.02 | 17.97% |
| v2b | opposed | bearish | Long | 134 | 134 | $5,684.00 | 3,043.00 | 55.22% | $42.42 | 17.91% |
| v2d | aligned | bullish | Long | 61 | 61 | $1,634.00 | 908.50 | 54.10% | $26.79 | 16.39% |
| v2d | opposed | bearish | Long | 60 | 60 | $514.00 | 347.00 | 48.33% | $8.57 | 18.33% |
| v2d | aligned | bearish | Short | 54 | 54 | $-672.50 | -255.25 | 53.70% | $-12.45 | 18.52% |
| v2b | aligned | bearish | Short | 119 | 119 | $-740.00 | -191.50 | 55.46% | $-6.22 | 15.13% |
| v2d | opposed | bullish | Short | 63 | 63 | $-4,770.00 | -2,290.50 | 39.68% | $-75.71 | 15.87% |

## Dropped by outside-only filter

| regime | bias_alignment | monthly_bias | direction | trades | days | net_usd | gross_contract_points | win_rate | avg_trade_usd | tp2_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2b | neutral | neutral | Long | 216 | 216 | $4,503.50 | 2,575.75 | 52.31% | $20.85 | 17.13% |
| v2b | neutral | neutral | Short | 213 | 213 | $2,854.00 | 1,746.50 | 52.11% | $13.40 | 18.78% |
| v2b | building_range | building_range | Short | 76 | 76 | $1,019.00 | 623.50 | 50.00% | $13.41 | 22.37% |
| v2d | neutral | neutral | Long | 63 | 63 | $812.50 | 500.75 | 49.21% | $12.90 | 17.46% |
| v2b | building_range | building_range | Long | 84 | 84 | $-392.50 | -70.25 | 51.19% | $-4.67 | 5.95% |
| v2d | building_range | building_range | Long | 19 | 19 | $-724.50 | -333.75 | 47.37% | $-38.13 | 10.53% |
| v2d | neutral | neutral | Short | 55 | 55 | $-744.50 | -289.75 | 47.27% | $-13.54 | 12.73% |
| v2d | building_range | building_range | Short | 26 | 26 | $-1,677.50 | -799.75 | 53.85% | $-64.52 | 7.69% |

## All rows by regime and monthly state

| regime | bias_alignment | monthly_bias | trades | days | net_usd | gross_contract_points | win_rate | avg_trade_usd | tp2_rate |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| v2b | opposed | bullish | 293 | 293 | $14,062.00 | 7,470.50 | 58.36% | $47.99 | 24.91% |
| v2b | aligned | bullish | 295 | 295 | $8,857.00 | 4,871.00 | 57.97% | $30.02 | 17.97% |
| v2b | neutral | neutral | 429 | 285 | $7,357.50 | 4,322.25 | 52.21% | $17.15 | 17.95% |
| v2b | opposed | bearish | 134 | 134 | $5,684.00 | 3,043.00 | 55.22% | $42.42 | 17.91% |
| v2d | aligned | bullish | 61 | 61 | $1,634.00 | 908.50 | 54.10% | $26.79 | 16.39% |
| v2b | building_range | building_range | 160 | 104 | $626.50 | 553.25 | 50.62% | $3.92 | 13.75% |
| v2d | opposed | bearish | 60 | 60 | $514.00 | 347.00 | 48.33% | $8.57 | 18.33% |
| v2d | neutral | neutral | 118 | 94 | $68.00 | 211.00 | 48.31% | $0.58 | 15.25% |
| v2d | aligned | bearish | 54 | 54 | $-672.50 | -255.25 | 53.70% | $-12.45 | 18.52% |
| v2b | aligned | bearish | 119 | 119 | $-740.00 | -191.50 | 55.46% | $-6.22 | 15.13% |
| v2d | building_range | building_range | 45 | 36 | $-2,402.00 | -1,133.50 | 51.11% | $-53.38 | 8.89% |
| v2d | opposed | bullish | 63 | 63 | $-4,770.00 | -2,290.50 | 39.68% | $-75.71 | 15.87% |

## Outputs

- Annotated trades: [adaptive_scaleout_monthly_bias_annotated.csv](adaptive_scaleout_monthly_bias_annotated.csv)
- Summary CSV: [adaptive_scaleout_monthly_bias_summary.csv](adaptive_scaleout_monthly_bias_summary.csv)
- Daily monthly-bias table: [monthly_bias_by_day.csv](monthly_bias_by_day.csv)

## Notes

- Gross contract-points are reconstructed from the scaleout net using the known $3 total fee per 2-contract leg.
- This is a session-level filter study. It does not alter the intraday scaleout mechanics or rerun fills after removing earlier same-day legs.
