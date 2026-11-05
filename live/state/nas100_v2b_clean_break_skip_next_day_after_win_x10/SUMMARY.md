# NAS100 clean-break — skip next day after win (×10)

STATUS: diagnostic post-hoc filter on frozen 1m-fill validation (not a re-sim).

Parent: `brl_21741b260a28` · `live/state/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation`
Size: research unit ×10 (demo entry 10 / max 40).

## Rule

- Win = campaign/trade `net_usd > 0` (one trade per RTH session in this book).
- After a **taken** win on session D, sit out the **next RTH session** in the replay calendar.
- Skipped days do not arm further skips (causal).
- Dollars scaled ×10 from research unit tape; stress rebuilt by zeroing equity-path deltas on skipped traded sessions.

## Results (×10)

| Book | Trades | Units (1×) | Net | Closed DD | Stress DD | Win% | PF | N/S |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline | 1166 | 2070 | $122,529.50 | $-18,938.50 | $-19,658.50 | 12.9% | 1.43 | 6.23 |
| Skip next day after win | 1107 | 1953 | $110,500.00 | $-18,794.00 | $-19,554.00 | 12.5% | 1.41 | 5.68 |

## Sit-out tape

- Skip dates armed: **138** (empty/no-signal: 79)
- Baseline trades skipped: **59**
- Skipped tape net (×10): **$12,029.50** (12 wins / 47 losses left on table)
- Net delta vs baseline: **$-12,029.50**
- N/S delta: **-0.55**

## Yearly net (×10)

| Year | Base trades | Base net | Filt trades | Filt net |
|---:|---:|---:|---:|---:|
| 2016 | 19 | $-1,406 | 18 | $-1,361 |
| 2017 | 125 | $-907 | 123 | $-2,399 |
| 2018 | 134 | $-2,341 | 129 | $-2,942 |
| 2019 | 131 | $10,602 | 121 | $12,106 |
| 2020 | 135 | $13,933 | 129 | $14,276 |
| 2021 | 146 | $25,399 | 138 | $19,317 |
| 2022 | 121 | $24,968 | 116 | $29,114 |
| 2023 | 140 | $12,747 | 133 | $7,664 |
| 2024 | 123 | $16,420 | 116 | $14,178 |
| 2025 | 92 | $23,113 | 84 | $20,547 |

**Stance:** reject as promotion filter (hurts vs baseline).

Artifacts: `summary.csv`, `trade_decisions.csv`, `yearly_compare.csv`, `SUMMARY.json`, `EMAIL.txt`.
