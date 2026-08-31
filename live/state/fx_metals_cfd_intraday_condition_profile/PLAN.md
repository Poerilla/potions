# FX / metals / CFD HP size-up — research plan

Study: `fx_metals_cfd_intraday_condition_profile_v1`

Futures received a full **width-aware condition profile → HP shortlist → matched-null
validation** pipeline. This plan brings FX, index CFDs, metals, and **quarterly
range breakout** to the same standard.

Hub layout:

| Phase | Hub | Driver |
|-------|-----|--------|
| 1 — profile | `live/state/fx_metals_cfd_intraday_condition_profile/` | `fx_metals_cfd_intraday_condition_profile_v1` |
| 2 — nulls | `live/state/fx_metals_cfd_intraday_hp_sizeup_nulls/` | `fx_metals_cfd_intraday_hp_sizeup_nulls` |
| 3 — deploy | `live/state/fx_metals_cfd_intraday_hp_live_plan/` | LIVE_PLAN after null pass |

## Book universe

| Family | Books | Width / structure features |
|--------|-------|---------------------------|
| Monday OR | EURUSD, USDJPY, US30, GBPUSD, AUDJPY, XAUUSD | Monday range vs 60d pct; prior-day range pct |
| v2b / London | EURUSD, NAS100, US30 prior-opposed | London OR width vs ATR; prior-day range pct |
| Asia-range | USDJPY S_3_1_3 | London OR width; prior-day range pct |
| ST+PMC 3R | EURUSD, GBPUSD, USDJPY, AUDJPY, NAS100, US30, XAUUSD, XAGUSD | Prior-day range pct; rolling ATR pct |
| **Quarterly breakout** | EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD, US30, NAS100 | **Prior-quarter range width Q1–Q4**; YOR/MOR/prior-Q type; weekly ATR align |

Baseline tapes: broker-like research fills under `live/state/` (not thin live demo tapes).

## Phase 1 — width-aware condition profile ✅

```bash
python -m live.fx_metals_cfd_intraday_condition_profile_v1 --email
```

Deliverables:

- Annotated `*_campaigns.csv` with calendar + width + HTF columns
- `condition_matrix.csv`, `shortlist.csv` (≤3/book, cov 5–35%, dual lift)
- `COND_COL` map in `fx_metals_cfd_intraday_condition_profile_lib.py`

**Quarterly breakout** is first-class in Phase 1 (not a siloed prior_width_study only).
Existing Q4_large toxicity on EURUSD is a hypothesis to test under nulls — not a live gate.

## Phase 2 — HP nulls on width shortlist

Same ΔN/S gate stack as `intraday_hp_sizeup_nulls.py`:

- Matched placebo (never stratify on test feature)
- Clustered timing shift
- Selection-aware master null
- Nested walk-forward; coverage ≤35%

Priority pairs (analogous to futures NQ `or_norm`):

| Family | First null candidates |
|--------|----------------------|
| Monday OR | `Monday session range vs ATR` narrow/norm/wide |
| ST+PMC | `Prior-day range percentile` + `ATR causal rolling percentile` |
| v2b / London | `London OR width vs ATR` |
| **Quarterly breakout** | `Prior-quarter range width` Q4_large / Q1_small; `Monthly OR direction`; `Prior quarter type` |

```bash
# Phase 2 (after shortlist review)
python -m live.fx_metals_cfd_intraday_hp_sizeup_nulls --priority-1-25 --email
```

## Phase 3 — deployment plan

Only after nulls pass — same tier rules as futures:

- **Tier A** — SIZE-UP VALIDATED @ 1.25×
- **Tier B** — provisional paper (0.05 < p_master ≤ 0.10)
- **Tier C** — shadow / risk throttle only

Do **not** promote from profile lift alone. Quarterly breakout baseline books may stay
ungated even when width filters look good in-sample (see ES MOR-up NOT VALIDATED precedent).

Portfolio rules (draft):

- At most one HP multiplier per symbol sleeve per session/day.
- Quarterly breakout: no stacking with intraday HP on same symbol without overlap pass.
- Metals ST+PMC books may be thin — require n≥40 in profile bucket before null queue.

## Expectations

- Width can help (futures NQ `or_norm`) or fail strict nulls (ES/YM width demoted).
- EURUSD quarterly Q4_large loses money on baseline tape — width is book-specific.
- XAGUSD ST+PMC is very thin; profile may not clear n≥40.

## References

- Futures pipeline: `live/state/futures_intraday_condition_profile/`
- Quarterly baseline: `live/state/quarterly_range_breakout_fx_metals_cfd/`
- ES quarterly HP precedent: `live/state/es_quarterly_breakout_hp_profile/`
