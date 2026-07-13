# Fair Benchmark Scaling 10Y

Window: **2016-01-01 through 2025-12-31**. Futures include yearly ORB scaleout3 sleeves and the current prior-opposed intraday sleeves.

Assumptions:

- Yearly ORB futures resize only at fresh trade entry.
- Prior-opposed intraday rows use broker-like daily equity curves and resize at calendar-year start.
- Required futures capital per bundle = **3 x full-sample/window open-heat stress DD**.
- ETF rows are fully invested for the whole period using adjusted close, so growth compounds. No ETF margin or leverage is assumed.
- MNQ is dormant before its first local trade in 2020, so its “10Y” row is really a 10-year account window with a 2020-2025 active strategy window.
- MNQ prior-opposed is dormant before its 2021 local start; NQ prior-opposed is active across the 2016-2025 window.

## $50k Starting Capital

| Sleeve | End Capital | Net | Stress DD | Return | Net/DD | Required / Bundle | Peak Size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Prior-opposed intraday NQ fixed 1 base book | $1,632,101 | $1,582,101 | $-63,617 | 3164.2% | 24.87 | $63,617 | 5 units |
| Yearly ORB MNQ standalone entry-resized 3xDD | $1,279,916 | $1,229,916 | $-161,100 | 2459.8% | 7.63 | $13,812 | 135 contracts |
| Prior-opposed intraday MNQ 3xDD annual scale | $1,043,560 | $993,560 | $-114,408 | 1987.1% | 8.68 | $19,068 | 90 units |
| Yearly ORB NQ standalone fixed 1 bundle | $786,134 | $736,134 | $-45,165 | 1472.3% | 16.30 | $45,165 | 3 contracts |
| QQQ fully invested | $301,589 | $251,589 | $-67,833 | 503.2% | 3.71 |  | full ETF capital |
| 50/50 QQQ+DIA fully invested | $236,500 | $186,500 | $-44,458 | 373.0% | 4.19 |  | full ETF capital |
| SPY fully invested | $200,127 | $150,127 | $-33,345 | 300.3% | 4.50 |  | full ETF capital |
| Prior-opposed intraday MNQ fixed 1 base book | $150,578 | $100,578 | $-6,356 | 201.2% | 15.82 | $6,356 | 5 units |
| Yearly ORB MNQ standalone fixed 1 bundle | $118,082 | $68,082 | $-4,604 | 136.2% | 14.79 | $4,604 | 3 contracts |
| Yearly ORB NQ standalone entry-resized 3xDD | $50,000 | $0 | $0 | 0.0% | inf | $135,495 | 0 contracts |
| Prior-opposed intraday NQ 3xDD annual scale | $50,000 | $0 | $0 | 0.0% | inf | $190,851 | 0 units |

## Capital Sensitivity

| Start Capital | Sleeve | End Capital | Net | Stress DD | Peak Size |
|---:|---|---:|---:|---:|---:|
| $50,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $1,279,916 | $1,229,916 | $-161,100 | 135 contracts |
| $50,000 | Yearly ORB NQ standalone entry-resized 3xDD | $50,000 | $0 | $0 | 0 contracts |
| $50,000 | Prior-opposed intraday MNQ 3xDD annual scale | $1,043,560 | $993,560 | $-114,408 | 90 units |
| $50,000 | Prior-opposed intraday NQ 3xDD annual scale | $50,000 | $0 | $0 | 0 units |
| $50,000 | QQQ fully invested | $301,589 | $251,589 | $-67,833 | full ETF capital |
| $50,000 | SPY fully invested | $200,127 | $150,127 | $-33,345 | full ETF capital |
| $100,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $2,674,488 | $2,574,488 | $-336,520 | 282 contracts |
| $100,000 | Yearly ORB NQ standalone entry-resized 3xDD | $100,000 | $0 | $0 | 0 contracts |
| $100,000 | Prior-opposed intraday MNQ 3xDD annual scale | $2,584,692 | $2,484,692 | $-286,020 | 225 units |
| $100,000 | Prior-opposed intraday NQ 3xDD annual scale | $100,000 | $0 | $0 | 0 units |
| $100,000 | QQQ fully invested | $603,178 | $503,178 | $-135,665 | full ETF capital |
| $100,000 | SPY fully invested | $400,253 | $300,253 | $-66,691 | full ETF capital |
| $150,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $4,387,186 | $4,237,186 | $-554,900 | 465 contracts |
| $150,000 | Yearly ORB NQ standalone entry-resized 3xDD | $5,346,325 | $5,196,325 | $-679,820 | 57 contracts |
| $150,000 | Prior-opposed intraday MNQ 3xDD annual scale | $3,777,606 | $3,627,606 | $-419,496 | 330 units |
| $150,000 | Prior-opposed intraday NQ 3xDD annual scale | $150,000 | $0 | $0 | 0 units |
| $150,000 | QQQ fully invested | $904,767 | $754,767 | $-203,498 | full ETF capital |
| $150,000 | SPY fully invested | $600,380 | $450,380 | $-100,036 | full ETF capital |
| $250,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $7,387,529 | $7,137,529 | $-934,380 | 783 contracts |
| $250,000 | Yearly ORB NQ standalone entry-resized 3xDD | $7,627,895 | $7,377,895 | $-966,060 | 81 contracts |
| $250,000 | Prior-opposed intraday MNQ 3xDD annual scale | $6,708,060 | $6,458,060 | $-743,652 | 585 units |
| $250,000 | Prior-opposed intraday NQ 3xDD annual scale | $36,131,478 | $35,881,478 | $-3,880,637 | 305 units |
| $250,000 | QQQ fully invested | $1,507,945 | $1,257,945 | $-339,164 | full ETF capital |
| $250,000 | SPY fully invested | $1,000,633 | $750,633 | $-166,727 | full ETF capital |

## Read

- With `$50k`, strict 3x-DD NQ yearly ORB and NQ prior-opposed cannot start; their fixed one-book rows are raw comparisons, not $50k sizing recommendations.
- MNQ prior-opposed can start from `$50k` under the 3x-stress rule and is now part of this scaling report.
- Prior-opposed NQ becomes eligible around the `$190k` stress-capital area on this 2016-2025 window, so the `$250k` sensitivity row is the first strict 3x-DD NQ prior-opposed participation row here.
- QQQ is still a strong passive benchmark, but the current leading futures rows show materially higher historical capital efficiency when the 3x-stress scaling rule allows participation.
- The high contract/unit counts in resized rows are capital-efficiency math, not a live sizing recommendation for the build/test runway.
