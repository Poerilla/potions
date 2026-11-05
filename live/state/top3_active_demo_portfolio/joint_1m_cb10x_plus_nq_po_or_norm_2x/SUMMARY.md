# TOP4 joint 1-minute portfolio — TOP3 + NQ prior-opposed OR-norm 2×

**Dropped.** NQ was ~85% of this basket's net, so the live book stays TOP3.
The replacement candidate is NAS100 NQ-lead prior-opposed:
`live/state/top3_active_demo_portfolio/joint_1m_cb10x_plus_nas100_nq_lead/`.

Fourth sleeve is the best futures high-probability variant: NQ prior-opposed
resting-limit `S_1_1_3`, sized **2×** when the opening 15m range is `or_norm`
and **1×** otherwise (ΔN/S +12.20, provisional / highest-conviction controlled paper).

Adding NQ prior-opposed OR-norm 2× **raises** basket N/S on the overlap window.

## Overlap window

NQ fills begin in 2021, so this is **not** the published 2016–2025 TOP3 window
(that book is N/S **10.61**). Both columns below use the same four-sleeve overlap.

| | TOP3 on overlap | TOP4 (TOP3 + NQ) | NQ OR-norm 2× alone |
|---|---:|---:|---:|
| Net | $243491.09 | $1577113.59 | $1333622.50 |
| Close MTM DD | $-33438.40 | $-77334.07 | $-66135.00 |
| **Intrabar stress DD** | **$-33525.68** | **$-79739.07** | **$-67035.00** |
| **N/S** | **7.26** | **19.78** | **19.89** |
| Δ N/S vs TOP3 |  | **+12.52** |  |

Window 2021-03-04 → 2025-09-29. NQ is 85% of TOP4 net. Daily close-P&L correlation vs TOP3: **0.03**.

NQ size on the full fill tape: 129 trades at 2× (`or_norm`), 303 trades at 1×, 0 unmatched (kept at 1×).

## TOP4 sleeve nets (overlap entries)

| Sleeve | Units | Trades | Net |
|---|---:|---:|---:|
| Asia Range | 3619 | 517 | $104736.06 |
| Monday OR | 1215 | 378 | $44081.52 |
| Clean Break ×10 | 1076 | 600 | $94673.50 |
| NQ prior-opposed OR-norm 2× | 1905 | 381 | $1333622.50 |

## Method

- Asia / Monday OR / Clean Break ×10: same Engine fills as `joint_1m_cb10x`
- NQ: `nq_v2b_prior_opposed_stpmc_only_S_1_1_3` fills, point value $20, fee $1.50/contract
- HP map: `or15_width_pct == or_norm` → size ×2 on every unit of that trade
- Mark NQ on front-month RTH 1m; USDJPY and NAS100 tapes unchanged
- Lots stay sleeve-scoped (no cross-sleeve fill interference)

Stance: research basket add-on. NQ OR-norm @2× remains provisional controlled paper, not a funded promote.

