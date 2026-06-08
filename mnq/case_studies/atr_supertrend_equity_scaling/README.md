# MNQ ATR Supertrend Equity Scaling

Rule: at each calendar-year start, choose the largest bump level where current capital is at least **3x the full-sample MTM DD** for that bump level. Level 0 is the existing 10-max study. Level 1 bumps every scale event by one contract and max stack from 10 to 11, and so on.

This is a yearly capital-allocation model. It keeps the ATR entries, exits, Friday 15:50 adds, entry guard, and weekly filters unchanged.

Run note: this pass used `--max-bump 40`, so the largest allowed stack is 50 contracts/units. If peak bump equals 40, treat the final years as a capped practical-sizing run, not an uncapped compounding forecast.

## Summary

| Variant | Start Capital | End Capital | Dynamic Net | Dynamic MTM DD | End/Start | Peak Bump | Peak Max Contracts |
|---|---:|---:|---:|---:|---:|---:|---:|
| Daily primary, 3-initial | $71,270 | $112,142 | $40,872 | $-39,878 | 1.57x | 2 | 12 |
| Daily primary, ladder 1/1/2/2/2 | $58,580 | $92,822 | $34,242 | $-29,742 | 1.58x | 1 | 11 |
| Weekly primary, 3-initial | $235,566 | $447,881 | $212,315 | $-134,260 | 1.90x | 10 | 20 |
| Weekly primary, ladder 1/1/2/2/2 | $226,428 | $453,990 | $227,562 | $-131,739 | 2.01x | 11 | 21 |

## Yearly Tables

### Daily primary, 3-initial

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $71,270 | 0 | 10 | $71,270 | $0 | $5,866 | $-5,564 | 7 | $77,135 |
| 2020 | $77,135 | 0 | 10 | $71,270 | $5,866 | $17,129 | $-10,320 | 10 | $94,264 |
| 2021 | $94,264 | 0 | 10 | $71,270 | $22,994 | $10,826 | $-17,473 | 10 | $105,090 |
| 2022 | $105,090 | 0 | 10 | $71,270 | $33,820 | $0 | $0 | 0 | $105,090 |
| 2023 | $105,090 | 0 | 10 | $71,270 | $33,820 | $12,828 | $-3,098 | 7 | $117,918 |
| 2024 | $117,918 | 1 | 11 | $106,858 | $11,060 | $15,978 | $-18,122 | 11 | $133,896 |
| 2025 | $133,896 | 2 | 12 | $127,620 | $6,276 | $-17,695 | $-27,466 | 11 | $116,202 |
| 2026 | $116,202 | 1 | 11 | $106,858 | $9,343 | $-4,060 | $-4,060 | 4 | $112,142 |

### Daily primary, ladder 1/1/2/2/2

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $58,580 | 0 | 10 | $58,580 | $0 | $4,680 | $-4,350 | 8 | $63,259 |
| 2020 | $63,259 | 0 | 10 | $58,580 | $4,680 | $15,756 | $-9,240 | 10 | $79,014 |
| 2021 | $79,014 | 0 | 10 | $58,580 | $20,435 | $7,954 | $-16,129 | 10 | $86,968 |
| 2022 | $86,968 | 0 | 10 | $58,580 | $28,388 | $0 | $0 | 0 | $86,968 |
| 2023 | $86,968 | 0 | 10 | $58,580 | $28,388 | $9,588 | $-2,592 | 8 | $96,556 |
| 2024 | $96,556 | 1 | 11 | $89,226 | $7,330 | $7,885 | $-18,122 | 11 | $104,441 |
| 2025 | $104,441 | 1 | 11 | $89,226 | $15,215 | $-9,590 | $-16,670 | 7 | $94,852 |
| 2026 | $94,852 | 1 | 11 | $89,226 | $5,626 | $-2,030 | $-2,030 | 2 | $92,822 |

### Weekly primary, 3-initial

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $235,566 | 0 | 10 | $235,566 | $0 | $0 | $0 | 0 | $235,566 |
| 2020 | $235,566 | 0 | 10 | $235,566 | $0 | $54,492 | $-33,455 | 10 | $290,058 |
| 2021 | $290,058 | 2 | 12 | $271,486 | $18,572 | $82,764 | $-35,682 | 12 | $372,822 |
| 2022 | $372,822 | 6 | 16 | $364,132 | $8,690 | $-61,560 | $-66,376 | 16 | $311,262 |
| 2023 | $311,262 | 3 | 13 | $290,967 | $20,296 | $82,088 | $-43,946 | 13 | $393,350 |
| 2024 | $393,350 | 7 | 17 | $391,665 | $1,685 | $52,998 | $-103,690 | 17 | $446,348 |
| 2025 | $446,348 | 8 | 18 | $419,198 | $27,151 | $50,332 | $-91,990 | 18 | $496,681 |
| 2026 | $496,681 | 10 | 20 | $474,262 | $22,418 | $-48,800 | $-78,220 | 20 | $447,881 |

### Weekly primary, ladder 1/1/2/2/2

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $226,428 | 0 | 10 | $226,428 | $0 | $0 | $0 | 0 | $226,428 |
| 2020 | $226,428 | 0 | 10 | $226,428 | $0 | $54,966 | $-33,455 | 10 | $281,394 |
| 2021 | $281,394 | 3 | 13 | $275,430 | $5,964 | $89,661 | $-38,656 | 13 | $371,054 |
| 2022 | $371,054 | 6 | 16 | $348,596 | $22,459 | $-61,560 | $-66,376 | 16 | $309,494 |
| 2023 | $309,494 | 4 | 14 | $299,818 | $9,676 | $86,158 | $-47,327 | 14 | $395,653 |
| 2024 | $395,653 | 7 | 17 | $372,984 | $22,669 | $56,006 | $-99,707 | 17 | $451,660 |
| 2025 | $451,660 | 9 | 19 | $424,905 | $26,754 | $53,571 | $-94,508 | 19 | $505,230 |
| 2026 | $505,230 | 11 | 21 | $479,970 | $25,260 | $-51,240 | $-82,131 | 21 | $453,990 |
