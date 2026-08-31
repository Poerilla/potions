# Research contract — US30 ST+PMC completed-hour continuation

**strategy_id:** `us30_st_pmc_completed_hour_continuation_v1`

**Status:** frozen for campaign audit (no further path C variation until `CONTINUATION_AUDIT.md` completes).

**Preferred expression:** 2R→10R runner cell (`path_c_continuation_break_2r_10r` board label).  
**Not demo-promote.** Paths A/B rejected; no more work.

**Parent hub:** `live/state/us30_st_pmc_causal_revival_abc/`  
**DSR (A/B/C matrix):** `TRL-2026-00186`  
**Control ref:** completed-hour ST-limit 2R→10R N/S 1.47 (not re-run).

---

## signal

```yaml
hourly_ST_PMC:
  only_completed_hourly_bar: true
  available_at: hourly_bar_end   # causal; no forming-hour ST/PMC
```

## continuation

```yaml
side: same_as_completed_hourly_signal
trigger: "first 1m break of signal-hour high (long) / low (short) after available_at"
confirmation: touch   # bar.high >= hour_high or bar.low <= hour_low; NOT completed 1m close
max_wait: until_next_hourly_signal_overwrite
  # Engine today: armed state is overwritten by the next completed-hour thesis.
  # No fixed minute expiry yet — audit must quantify wait distribution.
max_entries_per_signal: 1
reentry_after_stop: false
```

## entry

```yaml
first_executable_bar_after_trigger: true   # break bar observes; next 1m bar submits market
adverse_fill: "current model"              # PaperBroker default slippage_ticks (1) + fee_per_unit
order_type: market
```

## risk

```yaml
initial_stop: fixed_50_pts_from_entry_ref_open   # NOT structural hour extreme
gap_through: true
max_open_units: 3   # initial bundle = tp1_qty(1) + runners(1+1); no pyramiding / no retest adds
```

## exits

```yaml
primary:
  - 2R   # board label; configured tp1_pts=150 with stop_pts=50 → 3× stop distance on TP1 unit
         # runner ladder: (1 @ 300 pts), (1 @ 1500 pts); BE stop after TP1
runner:
  - 10R  # board / control naming; see CONTINUATION_AUDIT for realized R attribution
eod_flatten: none_in_current_config
  # year_end_flatten_runners=false; no NY session EOD flatten in this cell.
  # Contract target for v1 honesty: state exact NY flatten if/when enforced.
```

## Exposure rule (must hold before any N/S is trusted)

| Rule | Required |
|---|---|
| Maximum entries | **One** continuation break per completed hourly ST+PMC signal |
| Maximum open | One initial bundle; **no pyramiding** |
| After stop | **No** re-entry under the same hourly signal |
| After TP1 | Runner only; **no** fresh continuation entry |
| After EOD | Flat (contract target; not yet enforced in replay config) |

If historical engine allows repeated intra-signal entries, **rerun with one-entry rule** before citing N/S.

## Decision freeze

| Path | Status |
|---|---|
| `path_A_preposted_PMC` | **rejected** — `no_more_work: true` |
| `path_B_post_hour_retest` | **rejected** — `no_more_work: true` |
| `path_C_continuation` | **research_candidate** — preferred `2R_to_10R`; `demo: false` |

### next_required

1. Campaign-level audit (`CONTINUATION_AUDIT.md`)
2. One-entry-per-signal confirmation (or rerun)
3. Tail/runner attribution + capped 2R/3R survival
4. Temporal robustness (campaign stats)
5. Adverse-execution stress
6. Strict Engine StrategyPlugin port under this contract (only after 1–5)

## Explicit non-goals

- Do **not** use the old fair-3R model / retired N/S 29.39.
- Do **not** treat unit count as independence.
- Do **not** demo-promote on board N/S alone.
