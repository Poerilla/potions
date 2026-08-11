# USDJPY Asia-range London — month + rolling WR/PF filter study

## Stance

**PROMOTE** USDJPY **`S_3_1_3`** with January blackout + shadow roll50 (WR≥40%, PF≥1)
for research / paper+OANDA practice.

**Funded sleeve: NOT YET** — see [`VALIDATION_GATES.md`](VALIDATION_GATES.md)
(frozen OOS, walk-forward, attribution, path-aware risk scrape, live-parity, margin ops).
Offline gates PASS; filter nulls = **RETAIN AS RISK THROTTLE** ([`FILTER_NULLS.md`](FILTER_NULLS.md));
open = live parity row-compare after London campaigns fire + sit-out candle-sim.

Broker-like filtered hub N/S **7.23** (+$178k / −$25k stress, 861 trades). Live demos:
`demo-usdjpy-asia-range-{paper,oanda}` (shadow last-50 seeded — no cold 50-campaign warmup).

Mechanics: [`FILTERS.md`](FILTERS.md) (shadow book = unfiltered campaign outcomes).

## Filters

1. **Skip consistently negative months** (audit on sizing tapes; locked to **January**).
2. **Rolling 50-campaign shadow gate**: sit out when prior-50 WR < 40% or PF < 1.
   Shadow = unfiltered campaign tape so the window keeps advancing.
   First 50 campaigns are roll-gate warmup (demos seed last-50).

## Books tested

| Book | Role | Filtered N/S |
|---|---|---:|
| `S_3_1_3` | #2 sizing N/S → **promoted filtered** | **7.23** |
| `S_3_3_3` | Equal 3/3/3 curiosity | 7.11 |
| `S_0_5_0` | #1 sizing N/S | 6.67 |
| `S_3_3_3` unfiltered | baseline | 2.14 |

## Prior hubs (2026-08-10/11)

- Multi-pair Asia-range smoke + majors: `live/state/fx_v2b_asia_range_london/` (USDJPY only green).
- USDJPY sizing sweep: `live/state/fx_v2b_asia_range_london_usdjpy_sizing/` (`S_0_5_0` 2.18, `S_3_1_3` 2.14 unfiltered).
- Deep-check / win-loss charts on baseline `S_1_1_3` under asia hub `deep_check/`.

Drivers:
- Filters: `python -m live.fx_v2b_asia_range_london_usdjpy_filters --email`
- Funded-sleeve gates: `python -m live.fx_v2b_asia_range_london_usdjpy_validation --email`
- Filter nulls: `python -m live.fx_v2b_asia_range_london_usdjpy_filter_nulls --email`
