# TOP3 active demo portfolio (one-book view)

Investor framing: **Asia Range + Monday OR + NAS100 Clean Break** as one strategy.

Research/broker-like Engine+PaperBroker tapes (not practice-account cash). USDJPY USD-normalized at `/110`.

## Active demos

| Sleeve | Demo | Account | Book |
|---|---|---|---|
| Asia Range | `usdjpy_asia_range_london_oanda` | `-004` | `S_3_1_3_flt` |
| Monday OR | `usdjpy_monday_or_ungated_oanda` | `-005` | `M2_S3_R1` Phase-2 tuneup |
| Clean Break | `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda` | `-003` | `trail06_m4_e2_out_be` |

## Combined scorecard

| Combined net | $484361.25 |
| Joint MTM stress DD | $-31597.48 |
| **Combined N/S (joint MTM)** | **15.33** |
| Additive stress (sum of sleeve |stress|) | $-54319.12 |
| Combined N/S (additive, no diversification) | 8.92 |
| Trades | 3934 |
| Win rate | 30.3% |
| Profit factor | 1.28 |
| Common window | 2016-11-15 → 2025-09-29 |
| Common-window net / stress / N/S | $245089.11 / $-31597.48 / 7.76 |

## Sleeve board (published broker metrics)

| Sleeve | Net | Stress | N/S | Trades | WR | PF | % of net |
|---|---:|---:|---:|---:|---:|---:|---:|
| asia_range | $178141.92 | $-24627.15 | 7.23 | 861 | 50.4% | 1.29 | 36.8% |
| monday_or | $293966.39 | $-27726.13 | 10.60 | 1907 | 31.9% | 1.27 | 60.7% |
| clean_break | $12252.95 | $-1965.85 | 6.23 | 1166 | 12.9% | 1.43 | 2.5% |

## Sell notes

- Headline book: **$484361.25** net, joint N/S **15.33** (diversification vs additive 8.92).
- FX sleeves dominate dollars (Asia ~37%, Monday OR ~61%); Clean Break is a small NAS100 diversifier (~2.5% net at research 1-lot pyramid).
- Clocks are complementary: Asia London morning, Monday OR weekly FX, Clean Break US cash index RTH.
- Both FX sleeves are USDJPY — joint MTM already credits only partial diversification; do not double-count risk.

Deep-check: `deep_check/top3_asia_monday_cleanbreak/`.

