# CONFIG — nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1

Frozen before execution. Descriptive only — not a trade model.

| Field | Value |
|-------|-------|
| study_id | `nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1` |
| instrument | NQ |
| timezone | America/New_York (DST-aware; no fixed UTC offset) |
| tick_size | 0.25 |
| status | RESEARCH / DESCRIPTIVE ONLY |
| data_session_policy | **POLICY A — FULL AVAILABLE FUTURES DATA** |
| source_data | `nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst` |

## Data session policy (POLICY A)

Use every valid 5-minute bar from the approved NQ dataset after a seed is
available and before seed expiry/inactivation.

Exclusions (recorded; never bridged):

- Documented exchange closures / holidays / early closes (via RTH early-close
  flags on the calendar day when relevant to seed construction)
- Daily CME maintenance halt (~17:00–18:00 ET) — detected as a data gap
- Weekend halt (Friday close → Sunday open) — detected as a data gap
- Any missing-data interval where consecutive 5m bar opens differ by > 5 minutes

Do not bridge pivots, protection horizons, or touch-response windows across gaps.

## Session segment labels (reporting strata only)

Boundaries frozen in America/New_York clock time of `structure_complete_at`
(or pivot_available_at for pivot rows). Not filters or selectors.

| Label | Clock (ET) |
|-------|------------|
| ASIA | 18:00–01:59 |
| EUROPE | 02:00–07:59 |
| PRE_NY | 08:00–09:29 |
| NY_OPEN | 09:30–10:59 |
| NY_MIDDAY | 11:00–13:59 |
| NY_PM | 14:00–15:59 |
| POST_CASH | 16:00–16:59 |
| OVERNIGHT | 17:00–17:59 (maintenance / thin; usually gap) |
| OTHER_OR_BOUNDARY | fallback |

Note: POST_CASH ends at 16:59; 17:00–17:59 is OVERNIGHT (halt window). Spec template
had POST_CASH 16:00–17:59; maintenance override → split documented here.

## Seed

| Field | Value |
|-------|-------|
| source | existing 4h WICK_REJECT ledger via `make_seeds_30` |
| seed_definition_changed | false |
| expiry | 30 completed 4h bars |
| selection | one candidate per seed (first qualifying after available) |

## Pivots / structure

| Field | Value |
|-------|-------|
| timeframe | 5m |
| left / right | 1 / 1 |
| strict_extrema | true |
| equal_level_policy | reject |
| bear | H1 → L1 → HH → LL |
| bull | L1 → H1 → LL → HH |
| structure_complete_at | P4.pivot_available_at |

## Horizons

| Field | Value |
|-------|-------|
| PRIMARY_OUTCOME_HORIZON | 180 minutes after structure_complete_at |
| TOUCH_RESPONSE_HORIZON | 60 minutes after touch_ts |
| failure_threshold | protected ± 1 NQ tick |
| response_distance_ticks | max(4, ceil(0.25 × break_distance_ticks)) |

## Parent context (unchanged archives)

- `nq_wick_reject_4h_ny_open_1m_protected_pivot_v1` — archived negative
- `nq_wick_reject_4h_ny_open_5m_protected_pivot_v2` — insufficient sample
- `nq_wick_reject_4h_ny_open_5m_protected_pivot_v2_no_cutoff` — one-sided descriptive

This study is a new all-session observational population, not a repair or selector.
