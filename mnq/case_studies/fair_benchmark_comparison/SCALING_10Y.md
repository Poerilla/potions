# Fair Benchmark Scaling 10Y

Window: **2016-01-01 through 2025-12-31**. Futures use the yearly ORB scaleout3 inside-range swing/range-close CSVs.

Assumptions:

- Futures resize only at fresh trade entry.
- Required futures capital per bundle = **3 x full-sample open-heat stress DD**.
- ETF rows are fully invested for the whole period using adjusted close, so growth compounds. No ETF margin or leverage is assumed.
- MNQ is dormant before its first local trade in 2020, so its “10Y” row is really a 10-year account window with a 2020-2025 active strategy window.

## $50k Starting Capital

| Sleeve | End Capital | Net | Stress DD | Return | Net/DD | Required / Bundle | Peak Size |
|---|---:|---:|---:|---:|---:|---:|---:|
| Yearly ORB MNQ standalone entry-resized 3xDD | $1,279,916 | $1,229,916 | $-161,100 | 2459.8% | 7.63 | $13,812 | 135 contracts |
| Yearly ORB NQ standalone fixed 1 bundle | $786,134 | $736,134 | $-45,165 | 1472.3% | 16.30 | $45,165 | 3 contracts |
| QQQ fully invested | $301,589 | $251,589 | $-67,833 | 503.2% | 3.71 |  | full ETF capital |
| 50/50 QQQ+DIA fully invested | $236,500 | $186,500 | $-44,458 | 373.0% | 4.19 |  | full ETF capital |
| SPY fully invested | $200,127 | $150,127 | $-33,345 | 300.3% | 4.50 |  | full ETF capital |
| Yearly ORB MNQ standalone fixed 1 bundle | $118,082 | $68,082 | $-4,604 | 136.2% | 14.79 | $4,604 | 3 contracts |
| Yearly ORB NQ standalone entry-resized 3xDD | $50,000 | $0 | $0 | 0.0% | inf | $135,495 | 0 contracts |

## Capital Sensitivity

| Start Capital | Sleeve | End Capital | Net | Stress DD | Peak Size |
|---:|---|---:|---:|---:|---:|
| $50,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $1,279,916 | $1,229,916 | $-161,100 | 135 contracts |
| $50,000 | Yearly ORB NQ standalone entry-resized 3xDD | $50,000 | $0 | $0 | 0 contracts |
| $50,000 | QQQ fully invested | $301,589 | $251,589 | $-67,833 | full ETF capital |
| $50,000 | SPY fully invested | $200,127 | $150,127 | $-33,345 | full ETF capital |
| $100,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $2,674,488 | $2,574,488 | $-336,520 | 282 contracts |
| $100,000 | Yearly ORB NQ standalone entry-resized 3xDD | $100,000 | $0 | $0 | 0 contracts |
| $100,000 | QQQ fully invested | $603,178 | $503,178 | $-135,665 | full ETF capital |
| $100,000 | SPY fully invested | $400,253 | $300,253 | $-66,691 | full ETF capital |
| $150,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $4,387,186 | $4,237,186 | $-554,900 | 465 contracts |
| $150,000 | Yearly ORB NQ standalone entry-resized 3xDD | $5,346,325 | $5,196,325 | $-679,820 | 57 contracts |
| $150,000 | QQQ fully invested | $904,767 | $754,767 | $-203,498 | full ETF capital |
| $150,000 | SPY fully invested | $600,380 | $450,380 | $-100,036 | full ETF capital |
| $250,000 | Yearly ORB MNQ standalone entry-resized 3xDD | $7,387,529 | $7,137,529 | $-934,380 | 783 contracts |
| $250,000 | Yearly ORB NQ standalone entry-resized 3xDD | $7,627,895 | $7,377,895 | $-966,060 | 81 contracts |
| $250,000 | QQQ fully invested | $1,507,945 | $1,257,945 | $-339,164 | full ETF capital |
| $250,000 | SPY fully invested | $1,000,633 | $750,633 | $-166,727 | full ETF capital |

## Read

- With `$50k`, strict 3x-DD NQ cannot start because one NQ bundle needs about `$135k` of stress-DD capital.
- The fixed NQ row is a raw performance comparison, not a 3x-DD sizing recommendation; its stress DD is almost the whole `$50k` account.
- MNQ can start from `$50k` and wins the 10-year account-window test if we allow entry-by-entry resizing.
- QQQ is still a strong passive benchmark. It beats fixed MNQ over this window, but not entry-resized MNQ and not fixed NQ.
- At `$150k+`, NQ can participate under the same 3x-DD rule and becomes the largest winner, but the drawdowns and contract size become much less friendly for a small automation test account.
