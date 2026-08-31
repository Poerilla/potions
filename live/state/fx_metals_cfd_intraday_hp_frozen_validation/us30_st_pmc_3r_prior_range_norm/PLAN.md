# Frozen validation — US30 ST+PMC 3R · prior-day range = normal

**Stance: hypothesis test only — do NOT promote, no 1.25× live authorization.**

Pre-registered after adversarial audit (`…/pairs/us30_st_pmc_3r__Prior-day_range_percentile__prior_range_norm/ADVERSARIAL_AUDIT.md`).

## Frozen rule

| Field | Value |
|-------|-------|
| Book | `us30_st_pmc_3r` |
| Condition | Prior-day range percentile |
| Bucket | `prior_range_norm` (middle tercile) |
| Band | **33–66%** rolling 252d pct rank (min 60 obs) — **not re-cut** |
| Feature | Prior calendar day H−L; feature ts = start of entry day |
| Causality | `live_ready` (0 entry-before-feature violations in audit) |

## Selection risk (explicit)

- Master-null on the Phase 2 priority queue already **failed** (p(ΔN/S)≈0.97, rank #16 / 75 on inc N/S).
- This run accepts table-wide discovery risk and reruns matched-added-exposure nulls on the **frozen** band only.

## Run

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
python -m live.fx_metals_cfd_intraday_hp_sizeup_nulls \
  --hub live/state/fx_metals_cfd_intraday_hp_frozen_validation/us30_st_pmc_3r_prior_range_norm \
  --pair "us30_st_pmc_3r:Prior-day range percentile:prior_range_norm" \
  --email
```

Outputs: full null suite @ 1.25× incremental, `COMPARE.md` (1.00× vs 1.25× sensitivity), `pairs/…/RESULT.json`.
