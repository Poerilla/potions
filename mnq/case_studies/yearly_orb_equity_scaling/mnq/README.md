# MNQ Yearly ORB Equity Scaling

Variant: yearly ORB scaleout3 / inside-range swing stop / range-close exit.
One bundle is the full 3-contract scaleout ladder. Capital requirement uses 3x the base open-heat stress DD, not just closed DD.
Run cap: 250 bundles.

## Summary

| Metric | Value |
|---|---:|
| Base trades | 26 |
| Base net | $68,082 |
| Base closed DD | $-3,156 |
| Base open-heat stress DD | $-4,604 |
| Base worst MAE | $2,212 |
| Scaling start capital | $13,812 |
| Scaling end capital | $313,479 |
| Scaling net | $299,667 |
| Scaling closed DD | $-17,430 |
| Scaling stress DD | $-35,800 |
| Peak bundles | 10 |
| Peak contracts | 30 |

## Yearly Scaling

| Year | Start Capital | Bundles | Max Contracts | Required Capital | Year Net | Closed DD | Stress DD | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | $13,812 | 1 | 3 | $13,812 | $13,574 | $-506 | $-1,576 | $27,386 |
| 2021 | $27,386 | 1 | 3 | $13,812 | $7,257 | $-1,842 | $-2,638 | $34,643 |
| 2022 | $34,643 | 2 | 6 | $27,624 | $14,754 | $-6,313 | $-9,208 | $49,396 |
| 2023 | $49,396 | 3 | 9 | $41,436 | $40,634 | $-724 | $-1,845 | $90,030 |
| 2024 | $90,030 | 6 | 18 | $82,872 | $59,768 | $-7,944 | $-16,854 | $149,799 |
| 2025 | $149,799 | 10 | 30 | $138,120 | $163,680 | $-17,430 | $-35,800 | $313,479 |
