# MYM ATR Supertrend Equity Scaling

Rule: at each calendar-year start, choose the largest bump level where current capital is at least **3x the full-sample MTM DD** for that bump level. Level 0 is the existing 10-max study. Level 1 bumps every scale event by one contract and max stack from 10 to 11, and so on.

This is a yearly capital-allocation model. It keeps the ATR entries, exits, Friday 15:50 adds, entry guard, and weekly filters unchanged.

Run note: this pass used `--max-bump 40`, so the largest allowed stack is 50 contracts/units. If peak bump equals 40, treat the final years as a capped practical-sizing run, not an uncapped compounding forecast.

## Summary

| Variant | Start Capital | End Capital | Dynamic Net | Dynamic MTM DD | End/Start | Peak Bump | Peak Max Contracts |
|---|---:|---:|---:|---:|---:|---:|---:|
| Daily primary, 3-initial | $27,669 | $126,675 | $99,006 | $-27,305 | 4.58x | 19 | 29 |
| Daily primary, ladder 1/1/2/2/2 | $31,798 | $109,581 | $77,782 | $-25,340 | 3.45x | 17 | 27 |
| Weekly primary, 3-initial | $21,874 | $582,135 | $560,260 | $-50,546 | 26.61x | 40 | 50 |
| Weekly primary, ladder 1/1/2/2/2 | $24,690 | $458,808 | $434,118 | $-48,196 | 18.58x | 40 | 50 |

## Yearly Tables

### Daily primary, 3-initial

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $27,669 | 0 | 10 | $27,669 | $0 | $3,006 | $-2,455 | 7 | $30,676 |
| 2020 | $30,676 | 0 | 10 | $27,669 | $3,006 | $15,710 | $-3,592 | 7 | $46,386 |
| 2021 | $46,386 | 3 | 13 | $43,971 | $2,415 | $6,484 | $-9,054 | 13 | $52,870 |
| 2022 | $52,870 | 5 | 15 | $52,734 | $136 | $3,613 | $-13,365 | 15 | $56,483 |
| 2023 | $56,483 | 5 | 15 | $52,734 | $3,749 | $30,233 | $-6,646 | 15 | $86,716 |
| 2024 | $86,716 | 11 | 21 | $82,750 | $3,966 | $19,316 | $-19,470 | 21 | $106,032 |
| 2025 | $106,032 | 15 | 25 | $103,258 | $2,774 | $18,163 | $-27,305 | 25 | $124,196 |
| 2026 | $124,196 | 19 | 29 | $123,766 | $429 | $2,480 | $-27,216 | 29 | $126,675 |

### Daily primary, ladder 1/1/2/2/2

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $31,798 | 0 | 10 | $31,798 | $0 | $598 | $-2,394 | 8 | $32,397 |
| 2020 | $32,397 | 0 | 10 | $31,798 | $598 | $10,662 | $-3,560 | 8 | $43,059 |
| 2021 | $43,059 | 3 | 13 | $42,500 | $560 | $4,462 | $-8,706 | 13 | $47,521 |
| 2022 | $47,521 | 4 | 14 | $44,076 | $3,445 | $1,172 | $-8,618 | 14 | $48,692 |
| 2023 | $48,692 | 4 | 14 | $44,076 | $4,616 | $24,630 | $-5,717 | 14 | $73,323 |
| 2024 | $73,323 | 10 | 20 | $73,062 | $261 | $16,736 | $-19,248 | 20 | $90,060 |
| 2025 | $90,060 | 13 | 23 | $85,886 | $4,174 | $17,213 | $-24,263 | 23 | $107,272 |
| 2026 | $107,272 | 17 | 27 | $106,394 | $879 | $2,308 | $-25,340 | 27 | $109,581 |

### Weekly primary, 3-initial

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $21,874 | 0 | 10 | $21,874 | $0 | $4,640 | $-1,803 | 7 | $26,515 |
| 2020 | $26,515 | 0 | 10 | $21,874 | $4,640 | $17,311 | $-3,592 | 7 | $43,826 |
| 2021 | $43,826 | 5 | 15 | $42,232 | $1,594 | $23,431 | $-10,114 | 15 | $67,257 |
| 2022 | $67,257 | 13 | 23 | $64,756 | $2,500 | $31,484 | $-18,816 | 23 | $98,741 |
| 2023 | $98,741 | 24 | 34 | $95,727 | $3,014 | $104,233 | $-13,595 | 34 | $202,974 |
| 2024 | $202,974 | 40 | 50 | $151,640 | $51,334 | $142,140 | $-27,600 | 50 | $345,114 |
| 2025 | $345,114 | 40 | 50 | $151,640 | $193,474 | $232,746 | $-50,546 | 50 | $577,860 |
| 2026 | $577,860 | 40 | 50 | $151,640 | $426,220 | $4,275 | $-46,925 | 50 | $582,135 |

### Weekly primary, ladder 1/1/2/2/2

| Year | Start Capital | Bump | Max Contracts | Required Capital | Headroom | Year Net | Year MTM DD | Max Open Units | End Capital |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2019 | $24,690 | 0 | 10 | $24,690 | $0 | $1,188 | $-2,153 | 8 | $25,878 |
| 2020 | $25,878 | 0 | 10 | $24,690 | $1,188 | $10,650 | $-3,560 | 8 | $36,528 |
| 2021 | $36,528 | 2 | 12 | $33,786 | $2,742 | $9,843 | $-7,406 | 12 | $46,370 |
| 2022 | $46,370 | 6 | 16 | $45,048 | $1,322 | $13,423 | $-9,656 | 16 | $59,794 |
| 2023 | $59,794 | 11 | 21 | $59,126 | $668 | $56,570 | $-8,280 | 21 | $116,363 |
| 2024 | $116,363 | 31 | 41 | $115,436 | $928 | $110,274 | $-22,632 | 41 | $226,637 |
| 2025 | $226,637 | 40 | 50 | $144,586 | $82,050 | $227,896 | $-48,196 | 50 | $454,532 |
| 2026 | $454,532 | 40 | 50 | $144,586 | $309,946 | $4,275 | $-46,925 | 50 | $458,808 |
