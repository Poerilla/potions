# CHART_PACK_SUMMARY — nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1

STATUS: VISUAL REVIEW / DESCRIPTIVE ONLY
smoke=True

## Source records
- Parent study ID: `nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1`
- Parent config hash: `402795e0a05e2fbc`
- Against-seed remap source: `nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1_against_seed_bias`
- Source-data version: `nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst`
- Generation configuration hash: `095bd7b9948b4a1f`
- Generator version: `seed_bias_review_charts_v1.0`

## Population
- Eligible seeds: 91
- Parent selected candidates: 90
- Valid contact reactions: 63
- Charts generated (OK): 27
- Missing/failed chart count: 0
- Data-gap / incomplete candidate rows: 27

## Coverage
- Bullish seed-bias candidates: 46
- Bearish seed-bias candidates: 44
- Aligned seed/structure: 50
- Opposed seed/structure: 40
- NO_AREA_CONTACT: 7
- TOUCH_ONLY: 0
- SHALLOW_TRADE_THROUGH: 3
- DEEP_TRADE_THROUGH: 61
- INSUFFICIENT_DATA_OR_SESSION_GAP: 19

## Audit integrity
- Parent-ledger match: **PASS**
- Candidate uniqueness: **PASS**
- Seed-bias remap match: **PASS**
- MFE/MAE label-swap assertion: **PASS**
- Horizon match: **PASS**
- Structure-complete == P4 available: **PASS**
- Chart metadata completeness: **PASS**
- No-trade-annotation scan: **PASS**

## Artifacts
- Hub: `/home/tester/hsm/potions/live/state/nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_seed_bias_review_v1`
- `chart_manifest.csv`
- `manual_chart_review_ledger.csv` (empty template)
- Packs under `charts/pack_{a..g}/`

## Final language

This chart pack is a descriptive visual review of frozen 4-hour wick-reject
seed bias, causal one-minute structure, protected-area interaction, and
post-contact excursions. It provides no entry, exit, stop, target, position
size, P&L, or strategy recommendation. Visual review must not be used to
retroactively select or alter the study population.
