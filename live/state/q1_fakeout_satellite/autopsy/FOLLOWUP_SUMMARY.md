# Q1 fakeout structure follow-up (close5 fade + invalidation add-on)

Part A signals (independent q1 scan, close5 out->in sequence): **203 sessions**.

Part B universe: the satellite's 447 touch-failure signals. Unconditional first touch after the failure confirm:

| First touch | N | % |
|---|---:|---:|
| orig_1r_first | 152 | 34.0 |
| opp_boundary_first | 281 | 62.9 |
| same_bar_both | 0 | 0.0 |
| neither | 14 | 3.1 |

| variant | sessions | fills | fill_rate_pct | tp | sl | eod | tp_rate_of_fills_pct | net_usd_1unit | usd_per_fill | usd_per_session | profit_factor | avg_risk_pts |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A1_close5_fade_stop_extreme | 203 | 187 | 92.1 | 68 | 116 | 3 | 36.4 | 13074.5 | 69.92 | 64.41 | 1.741 | 8.72 |
| A2_close5_fade_stop_invalidation | 203 | 187 | 92.1 | 99 | 75 | 13 | 52.9 | 15444.5 | 82.59 | 76.08 | 1.491 | 22.14 |
| B1_addon_mid_tp_orig1r_stop_oppbound | 447 | 402 | 89.9 | 82 | 301 | 19 | 20.4 | -3523.0 | -8.76 | -7.88 | 0.947 | 11.3 |
| B2_addon_mid_tp_broken_boundary | 447 | 402 | 89.9 | 185 | 215 | 2 | 46.0 | -1308.0 | -3.25 | -2.93 | 0.971 | 11.3 |

A1/A2 = limit fade at the broken boundary after touch-break -> 5m close outside (<10:30) -> 5m close back inside within 2 candles; stop at failed extreme (A1) or original-break 1R (A2); TP opposite boundary.
B1/B2 = limit add at OR mid in the ORIGINAL break direction after the satellite failure signal; stop past the opposite boundary; TP at original-break 1R (B1) or at the broken boundary (B2). 1 unit shown; the proposed 2-contract add scales linearly.
## Verdict (2026-08-02) — both structures invalidated, satellite stays binned

**A (close5-confirmed boundary fade):** headline PF 1.74 (A1) is real but regime-concentrated:
2021+2023+2024 contribute more than 100% of the 16-year net; 6/16 years negative (incl. 2025,
the most recent); 2010-2020 is ~flat over 113 trades. Fails the repo stability bar (sign >= 70%
of years). The close-outside confirmation IS the right filter direction (PF 1.74 vs 1.17 touch
version) but the residual edge is a post-2021 volatility artifact, ~12 thin trades/year.

**B (invalidation add-on at OR mid):** REJECTED, and the premise contained a conditioning error:
57.7% invalidation was measured on LOSERS after the tight stop was hit. Unconditionally from the
failure confirm, the OPPOSITE boundary is touched first 62.9% vs the original 1R first 34.0% —
the add-on fights the majority path and loses under both TP choices (PF 0.947 / 0.971).

Per protocol: moving on to the queued plans (runner ladder, reverse_only_when).
