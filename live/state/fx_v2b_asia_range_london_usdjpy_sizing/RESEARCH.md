# USDJPY Asia-range London — sizing attribution sweep

Goal: find which scaleout bucket (TP1 / TP2 / runner) carries the edge on
USDJPY Asia OR → London v2b, and whether runner-heavy / TP1-heavy mixes beat
the prior `S_1_1_3` champ (N/S ≈ 2.03).

Driver: `python -m live.fx_v2b_asia_range_london` with dynamic `S_tp1_tp2_runner`.
Hub: `live/state/fx_v2b_asia_range_london_usdjpy_sizing/`.

## Result (unfiltered, 2026-08-11)

Edge is in **all three buckets**. Top N/S: `S_0_5_0` **2.18**, `S_3_1_3` **2.14**.
Filtered follow-up promoted **`S_3_1_3` + Jan + shadow roll50** → N/S **7.23**
(`live/state/fx_v2b_asia_range_london_usdjpy_filters/`).

## Lean grid (11 cells)

| Book | Entry | Intent |
|------|------:|--------|
| S_5_0_0 | 5 | Pure TP1 |
| S_0_5_0 | 5 | Pure TP2 |
| S_0_0_5 | 5 | Pure runner |
| S_3_1_1 | 5 | TP1-heavy mix |
| S_1_3_1 | 5 | TP2-heavy mix |
| S_1_1_3 | 5 | Runner-heavy (baseline champ) |
| S_0_2_3 | 5 | Skip TP1 |
| S_2_0_3 | 5 | Skip TP2 |
| S_2_3_0 | 5 | No runner |
| S_3_1_3 | 7 | TP1+runner stretch |
| S_1_1_1 | 3 | Equal small baseline |

Rank by Net/Stress. Pure buckets answer “where the bulk comes from”;
mixes answer “what we can boost.”
