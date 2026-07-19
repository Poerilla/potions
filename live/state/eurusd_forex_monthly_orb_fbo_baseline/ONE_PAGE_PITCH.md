# EURUSD Monthly ORB First-Break Opposite — One-pager

**Promoted:** 2026-07-18 · Plugin `monthly_orb_v2b_oco`

## Edge in one sentence

After the monthly opening range forms, **fade the first break** (arm the opposite boundary), scale out at 0.25R / 1R / 2R, move stop to BE after the first skim, and only exit risk on a daily close beyond the stop.

## Headline (broker stress)

| | 1/1/3 | 1/2/3 |
|---|---:|---:|
| Net | **+$77.3k** | **+$90.6k** |
| Stress DD | −$74.0k | −$88.8k |
| Net/Stress | **1.04** | **1.02** |
| Campaign WR | 50.3% | 50.3% |
| Hit 1R / 2R | 34.7% / 15.6% | 34.7% / 15.6% |

## Why it works

- First-break opposite filters chasing the initial OR expansion.
- Close-only SL survives wicks that wreck wick-stop books.
- BE after TP25 protects the book on the common “skim then fail” path.
- Capping the runner at 2R banks extension without month-end giveback.

## Risks

- Absolute stress DD is large (~$74–89k) vs the intraday sleeve.
- Only ~35% of campaigns reach 1R; edge is asymmetric payoff, not high frequency of runners.
- After TP2, path is mixed (~42% hold d+1; ~42% convert to 2R) — see post-TP2 study.
