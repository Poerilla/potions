# CONFIG — nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1

Frozen before execution. Descriptive only — not a trade model.

| Field | Value |
|-------|-------|
| study_id | `nq_wick_reject_4h_24h_1m_protected_pivot_touch_response_v1` |
| instrument | NQ |
| timezone | America/New_York (DST-aware; no fixed UTC offset) |
| tick_size | 0.25 |
| status | RESEARCH / DESCRIPTIVE ONLY |
| data_session_policy | **POLICY A — FULL AVAILABLE FUTURES DATA** |
| source_data | `nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst` |

## Data session policy (POLICY A)

Use every valid one-minute bar from the approved NQ dataset after a seed is
available and before seed expiry/inactivation.

Exclusions (recorded; never bridged):

- Documented exchange closures / holidays / early closes (via RTH early-close
  flags on the calendar day when relevant to seed construction)
- Daily CME maintenance halt (~17:00–18:00 ET) — detected as a data gap
- Weekend halt (Friday close → Sunday open) — detected as a data gap
- Any missing-data interval where consecutive 1m bar opens differ by > 1 minute

Do not bridge pivots, structure horizons, or reaction windows across gaps.

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
| timeframe | 1m |
| left / right | 1 / 1 |
| strict_extrema | true |
| equal_level_policy | reject |
| min_pivot_separation_bars | 1 |
| bear | H1 → L1 → HH → LL |
| bull | L1 → H1 → LL → HH |
| structure_complete_at | P4.pivot_available_at |

## Protected area (measurement zone only)

| Field | Value |
|-------|-------|
| area_width_ticks | `min(12, max(4, ceil(0.25 * break_distance_ticks)))` |
| bear area | `[protected_HH, HH + area_width]` |
| bull area | `[LL - area_width, protected_LL]` |
| NOT | stop size / risk / entry zone |

## Horizons

| Field | Value |
|-------|-------|
| STRUCTURE_HORIZON | 180 minutes after structure_complete_at |
| REACTION_HORIZON | 60 minutes after first_contact_ts |
| response_distance_ticks | `max(4, ceil(0.25 × break_distance_ticks))` |

## Primary question (descriptive)

After first area contact, does mean(MFE_contact) > mean(MAE_contact) and
mean(MFE)/mean(MAE) > 1.00? Report bear and bull separately. Ratio-of-averages
is primary; also median MFE/MAE, median individual RR (excl. zero-MAE),
P25/P75, top-1/top-3 MFE contribution.

## Parent context (unchanged archives)

- `nq_wick_reject_4h_ny_open_1m_protected_pivot_v1`
- `nq_wick_reject_4h_ny_open_5m_protected_pivot_v2`
- `nq_wick_reject_4h_ny_open_5m_protected_pivot_v2_no_cutoff`
- `nq_wick_reject_4h_24h_5m_protected_pivot_touch_response_v1`

This study is a new all-session observational population (area reaction, not
strict line-hold). Not a repair or 1m-vs-5m selector.
