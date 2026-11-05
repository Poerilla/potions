# TOP3 joint 1-minute portfolio — NAS100 NQ-lead prior-opposed add-on

The NQ-futures fourth sleeve is dropped. That OR-norm 2× book was ~85% of basket net.
This walk keeps Asia Range, Monday OR, and Clean Break ×10, and adds the banked
NAS100 NQ-lead sync prior-opposed tape (`S_1_1_1`, `nq_lead_sync`) at flat size.

At ×10 the NQ-lead sleeve raises basket N/S without taking more than half of net. Research add-on only — not a funded promote.

## Overlap window

Lead fills begin in 2021, so this is **not** the published 2016–2025 TOP3 window
(that book is N/S **10.61**). Every row below uses the same overlap.

| Scale | Basket net | Stress DD | Basket N/S | Δ N/S vs TOP3 | Lead share of net |
|---|---:|---:|---:|---:|---:|
| TOP3 | $243491.09 | $-33525.68 | **7.26** |  |  |
| TOP3 + lead 1× | $264659.93 | $-32082.66 | **8.25** | **+0.99** | 8% |
| TOP3 + lead 10× | $455179.48 | $-31565.36 | **14.42** | **+7.16** | 47% |
| TOP3 + lead 40× | $1090244.65 | $-64546.99 | **16.89** | **+9.63** | 78% |
| Lead alone 1× | $21168.84 | $-1380.57 | **15.33** |  |  |

Window 2021-03-04 → 2025-09-29. Lead alone is the native $1/pt book (N/S is scale-invariant; net and stress scale with size). Daily close-P&L correlation vs TOP3: **0.04**.

Full lead tape: 840 units / 280 trades. Overlap sleeve nets below are the ×10 basket.

## Sleeve nets at ×10 (overlap entries)

| Sleeve | Units | Trades | Net |
|---|---:|---:|---:|
| Asia Range | 3619 | 517 | $104736.06 |
| Monday OR | 1215 | 378 | $44081.52 |
| Clean Break ×10 | 1076 | 600 | $94673.50 |
| NAS100 NQ-lead ×10 | 837 | 279 | $211688.39 |

## Method

- Asia / Monday OR / Clean Break ×10: same Engine fills as `joint_1m_cb10x`
- NAS100 NQ-lead: `nas100_v2b_nq_lead_synced_S_1_1_1` fills, $1/pt, fee $1.50/unit, then ×1 / ×10 / ×40
- ×10 matches the Clean Break multiplier already in this basket
- ×40 is the published NQ-matched research reading (~$120 per index point at entry) and is shown because it recreates a dominant sleeve
- No HP multiplier. The 1.25× mill on this book was RISK THROTTLE / NOT VALIDATED
- Both NAS sleeves mark on the same NAS100 1m tape; lots stay sleeve-scoped
- Causality: the lead replay recorded 29 violations (`nas100_v2b_nq_lead_synced_broker_like`). Not tick-proven

Stance: live portfolio stays TOP3. NQ-lead is a research add-on candidate, not a demo wiring change.

