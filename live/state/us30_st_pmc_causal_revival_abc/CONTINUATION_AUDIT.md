# CONTINUATION_AUDIT — US30 ST+PMC completed-hour continuation v1

**Created before further path-C variation.**

- Contract: [`RESEARCH_CONTRACT.md`](RESEARCH_CONTRACT.md)
- Preferred cell: `path_c_continuation_break_2r_10r`
- Strategy id (contract): `us30_st_pmc_completed_hour_continuation_v1`
- Board: net $25371 / stress $-13783 → **N/S 1.84**
- Campaigns CSV: `continuation_audit/campaigns.csv`

## 0. Path A/B freeze

| Path | Status |
|---|---|
| A pre-posted PMC | **rejected** — no more work |
| B post-hour retest | **rejected** — no more work |
| C continuation 2R→10R | **research_candidate** — demo=false |

## 1. Campaign reconstruction + reconcile

- Independent campaigns (trade_id): **1736**
- Arms (hourly signals): **3632** (fill rate 47.8%)
- Sum unit exits: **5207** vs reported units **5207** → match=True
- Sum campaign gross USD: **$33181.10** vs unit_fills USD **$33181.10** → match=True
- Unique signals with entry: **1736**
- Multi-entry signals: **0** (max entries/signal=1)
- Campaigns with >1 distinct entry timestamp (pyramid): **0**

Board net ($25,371) is fee-adjusted audit net; campaign table uses gross unit points×$1 before fees.

Each filled campaign maps to **one** causal `path_c_continuation_arm` via asof(signal ≤ entry).
Every unit exits exactly once in `unit_fills.csv` (by construction of the audit tape).

### Wait after signal (minutes)

- median=11.0  p90=49.0  max=4712.0
- wait>60m: 78  >240m: 21  >1d: 19

## 2. Trade-frequency / exposure rule

| Rule | Observed on preferred 2R→10R tape |
|---|---|
| One continuation entry per hourly signal | **PASS** (0 multi-entry signals) |
| Max open = initial bundle (3) | **PASS** (board max_open=3; no pyramid) |
| No re-entry after stop under same signal | **PASS** (1:1 signal→campaign) |
| After TP1: runner only | **PASS** (bundle entered together; no fresh continuation) |
| EOD flat | **NOT ENFORCED** in current config |

No one-entry rerun required for the preferred cell. (Sibling fair-3R cell had 2 multi-entry signal anomalies — not used for N/S claims.)

Plugin note: Path C re-arms on every completed-hour thesis while flat; it does **not** yet store `path_c_last_signal_ts` the way Path B does.  empirically the 2R→10R tape still shows 1 entry/signal because a fill disarms until the next hour. Contract still requires an explicit `max_entries_per_signal=1` guard before demo.

## 3. Attribution by exit

| exit class | units | usd (gross) |
|---|---:|---:|
| target_10r_runner | 289 | $129756.3 |
| target_2r_or_tp1 | 327 | $47826.5 |
| target_mid_runner | 151 | $44818.3 |
| target_other | 3 | $-439.3 |
| stop | 1263 | $-62456.7 |
| runner_stop | 3174 | $-126324.0 |

- Long campaigns: 789 net $33137
- Short campaigns: 947 net $44
- Campaigns with any target fill: 473
- Campaigns with ≥9R target unit (10R-like): 56
- Those 56 campaigns' combined gross net ≈ **3.27×** total book net (remaining campaigns are net-negative) — tail concentration, not a ≤100% "share"
- First vs later break: **all filled campaigns are first-break entries** (engine enters on first touch after arm; no later-break scanner on this tape)

### Key question — does N/S 1.84 survive if profit capped?

Using **same board stress** ($13,783) and fee haircut scaled from board_net/gross:

| Cap rule | Approx net | Approx N/S vs board stress |
|---|---:|---:|
| Uncapped board | $25371 | **1.84** |
| Campaign profit cap **2R** (1R=$150 bundle) | $-64236 | -4.66 |
| Campaign profit cap **3R** | $-39021 | -2.83 |
| Per-unit profit cap **2R** ($100) | $-86448 | -6.27 |
| Per-unit profit cap **3R** ($150) | $-59799 | -4.34 |

**Verdict:** N/S **collapses under 2R/3R profit caps** → this expression is a **sparse runner/tail strategy**. Valid research class, but must be reported honestly and needs a larger forward sample before any demo discussion.

## 4. Temporal robustness (campaign statistics)

### Calendar year

| year | campaigns | net_gross | stress_proxy | N/S_proxy |
|---:|---:|---:|---:|---:|
| 2016 | 7 | $2528 | $-458 | 5.522 |
| 2017 | 29 | $4564 | $-1811 | 2.52 |
| 2018 | 208 | $-1159 | $-4969 | -0.233 |
| 2019 | 107 | $3069 | $-3586 | 0.856 |
| 2020 | 356 | $-1625 | $-6848 | -0.237 |
| 2021 | 215 | $-457 | $-3625 | -0.126 |
| 2022 | 353 | $4899 | $-4130 | 1.186 |
| 2023 | 139 | $10258 | $-2795 | 3.67 |
| 2024 | 147 | $6078 | $-2940 | 2.067 |
| 2025 | 175 | $5026 | $-2850 | 1.764 |

### Blocks

| block | campaigns | net_gross | N/S_proxy |
|---|---:|---:|---:|
| 2016-2019 | 351 | $9002 | 1.812 |
| 2020-2022 | 924 | $2817 | 0.29 |
| 2023-2026 | 461 | $21362 | 4.976 |

- Rolling 25-campaign PF: median=1.06 p10=0.407
- Rolling 50-campaign PF: median=1.068 p10=0.644
- Long/short: {'long_n': 789, 'short_n': 947, 'long_net': 33137.4, 'short_net': 43.7}
- Top campaign share of gross net: {'top_1_share': 0.0604, 'top_3_share': 0.1804, 'top_5_share': 0.3001}

### Leave-one-year-out N/S_proxy

| left out | campaigns | net | N/S_proxy |
|---:|---:|---:|---:|
| 2016 | 1729 | $30653 | 3.158 |
| 2017 | 1707 | $28617 | 2.948 |
| 2018 | 1528 | $34340 | 3.538 |
| 2019 | 1629 | $30112 | 3.102 |
| 2020 | 1380 | $34806 | 4.68 |
| 2021 | 1521 | $33638 | 3.636 |
| 2022 | 1383 | $28282 | 3.63 |
| 2023 | 1597 | $22923 | 2.361 |
| 2024 | 1589 | $27103 | 2.792 |
| 2025 | 1561 | $28155 | 2.9 |

### Block bootstrap (2000 draws)

- By **week**: {'n_weeks': 276, 'mean': 33370.88, 'p05': 6569.05, 'p50': 32770.6, 'p95': 62554.13, 'frac_negative': 0.02}
- By **hourly signal/campaign**: {'mean': 32824.98, 'p05': 5949.35, 'p50': 32879.65, 'p95': 60087.12, 'frac_negative': 0.0245}

Stress_proxy here is campaign-equity drawdown (not Engine intrabar MTM). Use for relative temporal shape only; board N/S remains the Engine figure.

## 5. Execution stress

Method: **proxy_incremental_slippage_on_existing_tape_not_engine_rerun**

| extra adverse ticks (entry+exit) | incremental $ | gross after | N/S vs board stress |
|---:|---:|---:|---:|
| 0 | $0 | $33181 | 2.41 |
| 1 | $1041 | $32140 | 2.33 |
| 2 | $2083 | $31098 | 2.26 |
| 4 | $4166 | $29016 | 2.10 |
| 8 | $8331 | $24850 | 1.80 |

- Gap-like stops (>1.25R adverse): 406 units, $-32211

Continuation uses marketable entries; Engine stress re-run with slippage_ticks∈{2,4,8} and gap-through preserved is still required before demo.

## 5b. Engine adverse slippage (authoritative)

Full Engine re-run of preferred cell (DSR TRL-2026-00188). See `continuation_audit/execution_stress`.

| slippage_ticks | net | stress | N/S | units |
|---:|---:|---:|---:|---:|
| 1 | $25371 | $-13783 | 1.84 | 5207 |
| 2 | $24468 | $-14155 | 1.73 | 5207 |
| 4 | $22664 | $-14898 | 1.52 | 5207 |
| 8 | $19112 | $-16384 | 1.17 | 5207 |

## 6. Correct next decision

```yaml
path_C_continuation:
  status: research_candidate
  preferred_variant: 2R_to_10R
  demo: false
  independent_campaigns: 1736
  one_entry_per_signal: pass
  next_required:
    - engine_adverse_slippage_rerun  # ticks 2/4/8, gap-through on
    - explicit max_entries_per_signal guard in plugin
    - state EOD flatten NY timestamp in contract + code
    - forward sample / larger out-of-sample before demo
    - strict StrategyPlugin port only after stress + temporal clear
```

## Bottom line

Causal US30 ST+PMC continuation is a **research candidate**, not a demo. Unit count (5207) compresses to **1736 independent campaigns**. One-entry-per-signal holds on the preferred tape. Judge the family on campaign robustness + runner attribution + execution stress — not on raw units or the retired fair-3R model.

