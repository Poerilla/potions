# MYM Yearly ORB Equity Scaling

Variant: yearly ORB scaleout3 / inside-range swing stop / range-close exit.
One bundle is the full 3-contract scaleout ladder. Capital requirement uses 3x the base open-heat stress DD, not just closed DD.
Run cap: 250 bundles.

## Summary

| Metric | Value |
|---|---:|
| Base trades | 30 |
| Base net | $16,949 |
| Base closed DD | $-1,802 |
| Base open-heat stress DD | $-2,357 |
| Base worst MAE | $840 |
| Scaling start capital | $7,071 |
| Scaling end capital | $36,824 |
| Scaling net | $29,752 |
| Scaling closed DD | $-2,751 |
| Scaling stress DD | $-3,786 |
| Peak bundles | 3 |
| Peak contracts | 9 |

## Yearly Scaling

| Year | Start Capital | Bundles | Max Contracts | Required Capital | Year Net | Closed DD | Stress DD | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | $7,071 | 1 | 3 | $7,071 | $1,162 | $-260 | $-620 | $8,234 |
| 2021 | $8,234 | 1 | 3 | $7,071 | $3,948 | $-70 | $-140 | $12,182 |
| 2022 | $12,182 | 1 | 3 | $7,071 | $300 | $-1,153 | $-1,855 | $12,482 |
| 2023 | $12,482 | 1 | 3 | $7,071 | $3,090 | $-755 | $-1,310 | $15,572 |
| 2024 | $15,572 | 2 | 6 | $14,143 | $8,190 | $-330 | $-1,044 | $23,762 |
| 2025 | $23,762 | 3 | 9 | $21,214 | $13,062 | $-2,751 | $-3,786 | $36,824 |
