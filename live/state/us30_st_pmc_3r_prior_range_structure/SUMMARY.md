# US30 ST+PMC 3R — prior-day range structure (locked bands)

Study: `us30_st_pmc_3r_prior_range_structure`

Engine: broker-realistic `us30_hourly_st_pmc_sl50_tp150_3r_1mfill` (1m fill tape,
stop-first / gap-through, lot-correct MTM). Filters are causal sit-outs on the
same campaign tape — not a separate idealized simulator.

Locked bands (pre-specified): 25–75%, 33–66%, 40–60%; overlay diagnostic 1.25× on 33–66%.

## Baseline (all signals @ 1.00×)

| metric | value |
|---|---:|
| campaigns | 575 |
| net P&L | $+18582 |
| gross profit / loss | $+36086 / $17503 |
| profit factor | 2.06 |
| win rate | 42.3% |
| avg / median campaign | $+32 / $-52 |
| closed DD | $1210 |
| intrabar MTM stress | $1210 |
| Net / Stress | 15.36 |
| CAGR ( $100k start ) | 2.0% |
| worst month / year | 2020-01 ($-309) / 2020 ($+676) |
| max consecutive losses | 8 |
| long / short | n=335 $+9536 WR=40% · n=240 $+9046 WR=45% |

## Variant matrix

| variant | status | n | net | PF | WR | avg | closed DD | intrabar stress | N/S | CAGR |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| baseline_all | primary | 575 | $+18582 | 2.06 | 42% | $+32 | $1210 | $1210 | 15.36 | 2.0% |
| broad_central_filter | primary | 283 | $+12366 | 2.61 | 48% | $+44 | $590 | $590 | 20.95 | 1.4% |
| original_tercile_filter | primary | 181 | $+8852 | 2.90 | 50% | $+49 | $550 | $550 | 16.08 | 1.0% |
| narrow_central_diagnostic | diagnostic | 108 | $+4815 | 2.66 | 48% | $+45 | $639 | $639 | 7.54 | 0.6% |
| original_overlay | diagnostic | 575 | $+20795 | 2.11 | 42% | $+36 | $1210 | $1210 | 17.19 | 2.3% |

## Opportunity-cost buckets (baseline tape)

Tercile buckets on 252d rolling prior-day range percentile (same feature as HP profile).

| bucket     |   n |     net |   stress |    ns |   wr |   share_net |   share_stress |
|:-----------|----:|--------:|---------:|------:|-----:|------------:|---------------:|
| compressed | 195 | 5132.70 |   413.72 | 12.41 | 0.39 |        0.28 |           0.96 |
| normal     | 181 | 8851.78 |   275.72 | 32.10 | 0.50 |        0.48 |           0.64 |
| expanded   | 199 | 4597.59 |   566.88 |  8.11 | 0.38 |        0.25 |           1.32 |

## Decision read

- Mixed primary-variant ranking — see yearly / 3-year block CSVs per variant.
- **40–60% diagnostic collapses vs 33–66%** — reinforces narrow-band fragility.

## Artifacts

- `variants/<slug>/RESULT.json`, `yearly.csv`, `blocks_3y.csv`
- `opportunity_buckets.csv`
- `SUMMARY.md` / `EMAIL.txt`
