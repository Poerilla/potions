# Yearly ORB Scaleout3 - One-Page Rundown

Source: `mnq/mnq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv` through 2025. One bundle = **3 MNQ units**: 1 off at 25% to TP1, 1 off at TP1, 1 runner. Jan-Mar sets the yearly ORB; Apr-Dec trades retests using the inside-range swing stop and daily range-close rule.

## Current Profile

| Metric | Value |
|---|---:|
| Trade packages | 26 |
| Profitable breakouts | 10 |
| Win rate | 38.5% |
| Net P/L | **$68,082** |
| Closed DD, unit-exit equity | **-$3,157** |
| MTM/open-heat stress DD | **-$4,604** |
| Net / MTM DD | **14.79** |
| Avg position MAE | $796 |
| Worst position MAE | $2,212 |
| 3x MTM-DD capital rule | **$13,812** |
| 5x MTM-DD conservative cushion | **$23,020** |

Practical read: the strict math says one bundle can be tested around **$14k**, but **$15k-$20k** is the more realistic automation-test zone because it leaves room for margin changes, commissions, slippage, roll noise, and broker/platform mistakes.

## Year-by-Year

| Year | Trades | Profitable | Net | Closed DD | MTM Stress DD | Bad-Year Read |
|---:|---:|---:|---:|---:|---:|---|
| 2020 | 2 | 1 | $13,574 | -$506 | -$1,577 | One huge winner pays for one small miss. |
| 2021 | 5 | 1 | $7,257 | -$1,842 | -$2,639 | Lowest hit rate year: 1 win, 4 losses. |
| 2022 | 6 | 2 | $7,377 | -$3,157 | -$4,604 | Worst stress year; widest heat and largest MAE. |
| 2023 | 3 | 1 | $13,545 | -$242 | -$615 | Cleanest year; one large winner with little heat. |
| 2024 | 6 | 2 | $9,961 | -$1,324 | -$2,809 | Churn year: repeated failed breakouts, still net positive. |
| 2025 | 4 | 3 | $16,368 | -$1,743 | -$3,580 | Best hit rate, but still needed room for open heat. |

Bad-year profile: there are no net-negative calendar years in this MNQ sample, but 2021, 2022, and 2024 are the years to respect. They are not "system broke" years; they are **low hit-rate churn years** where one runner has to pay for several failed breakouts. The dangerous condition is a wide yearly ORB plus repeated closes back into the range before a clean continuation.

## Half-Profit Lifestyle Plan

Assumption: start with the **3x MTM-DD requirement** and resize only at year start. Half of positive annual profit is withdrawn for lifestyle, half is retained for growth. Negative years would reduce capital with no withdrawal. No fees, tax, margin hikes, or roll slippage are included.

| Year | Start Capital | Bundles | Max Units | Net | Withdraw 50% | Retained | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 2020 | $13,812 | 1 | 3 | $13,574 | $6,787 | $6,787 | $20,599 |
| 2021 | $20,599 | 1 | 3 | $7,257 | $3,628 | $3,628 | $24,227 |
| 2022 | $24,227 | 1 | 3 | $7,377 | $3,688 | $3,688 | $27,916 |
| 2023 | $27,916 | 2 | 6 | $27,090 | $13,545 | $13,545 | $41,461 |
| 2024 | $41,461 | 3 | 9 | $29,884 | $14,942 | $14,942 | $56,403 |
| 2025 | $56,403 | 4 | 12 | $65,472 | $32,736 | $32,736 | $89,139 |

This path would withdraw about **$75,327** and still grow the account to about **$89,139** by the end of 2025, with capacity for **6 bundles / 18 MNQ units** the following year under the same 3x rule. Treat that as a sizing model, not a promise: the edge is concentrated in a small number of outsized continuation years, and the next true bad year may be worse than 2022.

## Operating Notes

- Use MTM stress DD, not just closed DD, for capitalization.
- Scale only after closed yearly profit exists; do not pre-size off expected profit.
- This is a low-frequency sleeve. The main automation risks are contract roll, stale/duplicate alerts, and executing the daily close / next-open behavior consistently.
- The best live-test stance is one bundle first, then scale after the account has actually absorbed a full year of fills and open heat.
