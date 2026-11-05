# NAS100 clean-break — ma_aligned HP size-up (arm-asof default)

STATUS: Engine+PaperBroker 1m-fill unit tape with **weighted** HP size-up.
**Default contract:** arm-asof `ma_aligned` at resting-entry `live_after_ts`
(no qty refresh until fill). Default mult ×1.5; also swept 2× / 4× / 6× for MTM DD.

Source fills: `live/state/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation/states/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill/fills.csv`
HA campaigns: `live/state/nas100_clean_break_ha_conditions/profile/all_campaigns.csv`
Frozen variant: `trail06_m4_e2_out_be` (OANDA practice / Index Momentum).
HP contract: `arm_asof_no_qty_refresh`
DSR: `TRL-2026-00201` (parent `TRL-2026-00199`)

## Arm-asof HP set

| Metric | Value |
|---|---:|
| Campaigns | 1166 |
| HP arm-asof | 647 |
| HP fill-stored | 710 |
| Arm↔fill label flips | 135 |

## Result (intrabar Engine stress)

| Book | Net | Closed DD | Intrabar MTM stress | N/S | Max open (wtd) | HP units |
|---|---:|---:|---:|---:|---:|---:|
| Baseline 1.0× | $12,252.95 | $-1,893.85 | $-1,965.85 | 6.23 | 4.0 | — |
| Arm-asof HP ×1.5 | $17,007.23 | $-2,425.57 | $-2,497.57 | 6.81 | 6.0 | 1150 |
| Arm-asof HP ×2 | $21,761.50 | $-2,957.30 | $-3,029.30 | 7.18 | 8.0 | 1150 |
| Arm-asof HP ×4 | $40,778.60 | $-5,139.55 | $-5,339.55 | 7.64 | 16.0 | 1150 |
| Arm-asof HP ×6 | $59,795.70 | $-7,982.15 | $-8,282.15 | 7.22 | 24.0 | 1150 |

Default ×1.5: Δnet=$+4754.28  ΔN/S=+0.58

## MTM DD scale sensitivity

| Mult | MTM DD | vs baseline | vs ×1.5 | vs linear-from-×1.5 | Net | N/S |
|---:|---:|---:|---:|---:|---:|---:|
| ×1.5 | $-2,497.57 | 1.270× | 1.000× | 1.000× | $17,007.23 | 6.81 |
| ×2 | $-3,029.30 | 1.541× | 1.213× | 1.000× | $21,761.50 | 7.18 |
| ×4 | $-5,339.55 | 2.716× | 2.138× | 1.036× | $40,778.60 | 7.64 |
| ×6 | $-8,282.15 | 4.213× | 3.316× | 1.137× | $59,795.70 | 7.22 |

Linear-from-×1.5 expect = baseline_MTM + (mult−1)/(1.5−1) × (MTM_1.5 − baseline_MTM).
Only the HP slice is upsized; non-HP units stay ×1, so whole-book MTM is **not**
expected to scale as mult×baseline.

**MTM DD read:** MTM DD shows material non-linearity vs ×1.5 interpolation (max |ratio-1|=14%) — size extremes change path DD, not just scale.

## Campaign overlay cross-check @ ×1.5

| | Net | Stress | N/S |
|---|---:|---:|---:|
| Overlay baseline | $12253 | $1866 | 6.57 |
| Overlay sized | $17007 | $2378 | 7.15 |

Overlay Δnet=$+4754 ΔN/S=+0.58 (hp=55% n=647)

## Stance

**REJECT / no paper demo** for arm-asof `ma_aligned` HP size-up (including ×4).

- Engine tape confirms higher whole-book N/S at ×1.5–×4, but matched-added-
  exposure nulls @ ×4 are **NOT VALIDATED** (`p_master_ΔNS`=0.860, HP coverage
  55%; hub `nulls_x4/`, DSR `TRL-2026-00202`). Fails size-up gates and does
  **not** qualify as a discretionary paper sleeve either.
- Paper demo `nas100_v2b_clean_break_trail_ma_aligned_hp_x4_paper` **removed**
  2026-09-13 — see `live/demo/.../REMOVED.md`. Do not restart or route to OANDA.
- Live Index Momentum plugin stays default clean-break base 10× (no ma_aligned HP).

Hub: `/home/tester/hsm/potions/live/state/nas100_clean_break_ma_aligned_size15_broker`
