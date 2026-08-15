# Canonical N/S boards (Phase 2 rerank)

Primary sort: `delta_NS` desc (overlays) or `candidate_NS` desc (baselines).

## 1. Cross-market finite core (top 25 by N/S)

_Eligible: finite 3R / 2R→10R / filters. Prior-opposed 10R addon + indefinite runners excluded._

| market | book | type | net | stress | N/S | source |
|---|---|---|---:|---:|---:|---|
| US30 | US30/sl50_tp150_3r_1mfill | baseline | +19028 | 907 | **20.97** | us30_st_pmc_runner_variants |
| NQ | NQ/sl50_tp150_3r_1mfill | baseline | +349517 | 17038 | **20.51** | futures_st_pmc_runner_variants |
| US30 | US30/sl50_tp150_runners_2r_10r | runner | +56111 | 2867 | **19.57** | us30_st_pmc_runner_variants |
| NAS100 | NAS100/sl50_tp150_3r_1mfill | baseline | +15219 | 778 | **19.56** | fx_index_metals_st_pmc_runner_variants |
| MNQ | MNQ/sl50_tp150_3r_1mfill | baseline | +23171 | 1195 | **19.38** | futures_st_pmc_runner_variants |
| YM | YM/sl50_tp150_3r_1mfill | baseline | +106425 | 6026 | **17.66** | futures_st_pmc_runner_variants |
| YM | YM/sl50_tp150_runners_2r_10r | runner | +313302 | 21424 | **14.62** | futures_st_pmc_runner_variants |
| NQ | NQ/sl50_tp150_runners_2r_10r | runner | +775763 | 58524 | **13.26** | futures_st_pmc_runner_variants |
| NAS100 | NAS100/sl50_tp150_runners_2r_10r | runner | +34065 | 3059 | **11.13** | fx_index_metals_st_pmc_runner_variants |
| MNQ | MNQ/sl50_tp150_runners_2r_10r | runner | +49899 | 4953 | **10.07** | futures_st_pmc_runner_variants |
| GBPUSD | GBPUSD/sl50_tp150_3r_1mfill | baseline | +108058 | 13310 | **8.12** | fx_index_metals_st_pmc_runner_variants |
| USDJPY | S_3_1_3_flt | filter | +178142 | 24627 | **7.23** | fx_v2b_asia_range_london_usdjpy_filters |
| USDJPY | S_3_3_3_flt | filter | +225075 | 31663 | **7.11** | fx_v2b_asia_range_london_usdjpy_filters |
| USDJPY | S_0_5_0_flt | filter | +113716 | 17057 | **6.67** | fx_v2b_asia_range_london_usdjpy_filters |
| MYM | MYM/sl50_tp150_3r_1mfill | baseline | +6516 | 1366 | **4.77** | futures_st_pmc_runner_variants |
| MYM | MYM/sl50_tp150_runners_2r_10r | runner | +20600 | 4468 | **4.61** | futures_st_pmc_runner_variants |
| EURUSD | EURUSD/sl50_tp150_3r_1mfill | baseline | +64449 | 21432 | **3.01** | fx_index_metals_st_pmc_runner_variants |
| GBPUSD | GBPUSD/sl50_tp150_runners_2r_10r | runner | +101445 | 41066 | **2.47** | fx_index_metals_st_pmc_runner_variants |
| USDJPY | S_3_3_3 | baseline | +196627 | 91767 | **2.14** | fx_v2b_asia_range_london_usdjpy_filters |
| EURUSD | EURUSD/sl50_tp150_runners_2r_10r | runner | +121157 | 67308 | **1.80** | fx_index_metals_st_pmc_runner_variants |
| XAUUSD | XAUUSD/sl50_tp150_runners_2r_10r | runner | +278071 | 167944 | **1.66** | fx_index_metals_st_pmc_runner_variants |
| XAUUSD | XAUUSD/sl50_tp150_3r_1mfill | baseline | +77327 | 92932 | **0.83** | fx_index_metals_st_pmc_runner_variants |

## 2. Overlay board (top 25 by ΔN/S)

| market | book | condition | mult | ΔN/S | Δnet | cand N/S | notes |
|---|---|---|---:|---:|---:|---:|---|
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 2.00× | **+12.20** | +581952 | 36.26 | decision=BORDERLINE PAPER p_master_ΔNS=0 |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 3.00× | **+10.90** | +1163905 | 34.96 | SENSITIVITY ONLY — not promotional until |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 4.00× | **+10.14** | +1745858 | 34.19 | SENSITIVITY ONLY — not promotional until |
| YM | ym_st_pmc_3r | Day of week=Thursday | 4.00× | **+10.03** | +111898 | 28.08 | SENSITIVITY ONLY — not promotional until |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 4.00× | **+8.38** | +191246 | 29.85 | SENSITIVITY ONLY — not promotional until |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 3.00× | **+8.15** | +127498 | 29.62 | SENSITIVITY ONLY — not promotional until |
| YM | ym_st_pmc_3r | Day of week=Thursday | 3.00× | **+7.87** | +74599 | 25.92 | SENSITIVITY ONLY — not promotional until |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 4.00× | **+7.71** | +474532 | 20.19 | SENSITIVITY ONLY — not promotional until |
| NQ | nq_st_pmc_3r | Entry hour (NY)=11 | 2.00× | **+7.10** | +63749 | 28.57 | ladder row; prefer null-suite RESULT.jso |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 3.00× | **+6.15** | +316355 | 18.63 | SENSITIVITY ONLY — not promotional until |
| USDJPY | S_3_1_3_flt | skip_months+roll50_wr40_pf1 | 1.00× | **+5.09** | -18485 | 7.23 | Jan/roll filters are risk-throttle until |
| USDJPY | S_3_3_3_flt | skip_months+roll50_wr40_pf1 | 1.00× | **+4.97** | +28447 | 7.11 | Jan/roll filters are risk-throttle until |
| NQ | nq_prior_opposed_rl | Opening 15m range vs ATR=or_norm | 1.25× | **+4.70** | +145488 | 28.75 | decision=BORDERLINE PAPER p_master_ΔNS=0 |
| USDJPY | S_0_5_0_flt | skip_months+roll50_wr40_pf1 | 1.00× | **+4.52** | -82911 | 6.67 | Jan/roll filters are risk-throttle until |
| YM | ym_st_pmc_3r | Day of week=Thursday | 2.00× | **+4.30** | +37299 | 22.36 | ladder row; prefer null-suite RESULT.jso |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 4.00× | **+4.14** | +353618 | 13.88 | SENSITIVITY ONLY — not promotional until |
| ES | es_prior_opposed_legacy | ST-event age=st_age_gt180m | 2.00× | **+4.08** | +158178 | 16.55 | decision=NOT VALIDATED p_master_ΔNS=0.61 |
| NQ | nq_prior_opposed_rl | ST-event age=st_age_30_90m | 1.25× | **+3.49** | +125654 | 27.55 | decision=NOT VALIDATED p_master_ΔNS=0.65 |
| NQ | nq_st_pmc_3r | Overnight compression=on_comp | 1.25× | **+3.27** | +34984 | 24.75 | decision=NOT VALIDATED p_master_ΔNS=0.22 |
| YM | ym_prior_opposed_rl | Overnight range third=on_middle | 3.00× | **+3.14** | +235745 | 12.88 | SENSITIVITY ONLY — not promotional until |
| YM | ym_prior_opposed_rl | Prior RTH range percentile=prior_ran | 4.00× | **+2.42** | +334230 | 12.16 | SENSITIVITY ONLY — not promotional until |
| USDJPY | usdjpy_asia_range | Hourly RSI bucket=rsi_gt70 | 2.00× | **+2.37** | +57638 | 11.02 | decision=RISK-BUDGET PROFILE p_master_ΔN |
| NQ | nq_st_pmc_3r | Hourly RSI bucket=rsi_55_70 | 1.25× | **+2.25** | +42846 | 23.72 | decision=NOT VALIDATED p_master_ΔNS=0.49 |
| USDJPY | usdjpy_monday_or | Entry hour (NY)=5 | 2.00× | **+2.23** | +47502 | 16.70 | decision=NOT VALIDATED p_master_ΔNS=0.81 |
| YM | ym_prior_opposed_rl | Prior RTH range percentile=prior_ran | 3.00× | **+1.93** | +222820 | 11.67 | SENSITIVITY ONLY — not promotional until |

## 1b. Prior-opposed 10R addon (not cross-ranked with core)

| market | book | net | stress | N/S | source |
|---|---|---:|---:|---:|---|
| NQ | NQ_10r_addon | +1576969 | 69965 | 22.54 | prior_opposed_10r_addon |
| MNQ | MNQ_10r_addon | +152588 | 7094 | 21.51 | prior_opposed_10r_addon |
| US30 | US30_10r_addon | +7432 | 10807 | 0.69 | prior_opposed_10r_addon |
| NAS100 | NAS100_10r_addon | +1736 | 7957 | 0.22 | prior_opposed_10r_addon |

## 3. Inventory board (indefinite runners — not cross-ranked)

| market | book | net | stress | forced-flat N/S |
|---|---|---:|---:|---:|
| US30 | US30/sl50_tp150_runners_2r_indef | +191517 | 73531 | 2.60 |
| NAS100 | NAS100/sl50_tp150_runners_2r_indef | +54331 | 22598 | 2.40 |
| NQ | NQ/sl50_tp150_runners_2r_indef | +4573429 | 1948591 | 2.35 |
| MNQ | MNQ/sl50_tp150_runners_2r_indef | +96683 | 52542 | 1.84 |
| MYM | MYM/sl50_tp150_runners_2r_indef | +53167 | 31777 | 1.67 |
| EURUSD | EURUSD/sl50_tp150_runners_2r_indef | +339774 | 228429 | 1.49 |
| YM | YM/sl50_tp150_runners_2r_indef | +970818 | 715046 | 1.36 |
| GBPUSD | GBPUSD/sl50_tp150_runners_2r_indef | +220821 | 267644 | 0.83 |
| AUDJPY | AUDJPY/sl50_tp150_runners_2r_indef | +16400247 | 24697107 | 0.66 |
| XAUUSD | XAUUSD/sl50_tp150_runners_2r_indef | +995971 | 2006322 | 0.50 |
| USDJPY | USDJPY/sl50_tp150_runners_2r_indef | +14374713 | 42280000 | 0.34 |
| XAGUSD | XAGUSD/sl50_tp150_runners_2r_indef | +15132 | 175800 | 0.09 |

## 4. Sensitivity board (non-promotional)

| market | book | mult | cand N/S | notes |
|---|---|---:|---:|---|
| NQ | nq_prior_opposed_rl | 3.00× | 34.96 | SENSITIVITY ONLY — not promotional until exact-m |
| NQ | nq_prior_opposed_rl | 4.00× | 34.19 | SENSITIVITY ONLY — not promotional until exact-m |
| YM | ym_st_pmc_3r | 4.00× | 28.08 | SENSITIVITY ONLY — not promotional until exact-m |
| NQ | nq_st_pmc_3r | 4.00× | 29.85 | SENSITIVITY ONLY — not promotional until exact-m |
| NQ | nq_st_pmc_3r | 3.00× | 29.62 | SENSITIVITY ONLY — not promotional until exact-m |
| YM | ym_st_pmc_3r | 3.00× | 25.92 | SENSITIVITY ONLY — not promotional until exact-m |
| ES | es_prior_opposed_legacy | 4.00× | 20.19 | SENSITIVITY ONLY — not promotional until exact-m |
| ES | es_prior_opposed_legacy | 3.00× | 18.63 | SENSITIVITY ONLY — not promotional until exact-m |
| YM | ym_prior_opposed_rl | 4.00× | 13.88 | SENSITIVITY ONLY — not promotional until exact-m |
| YM | ym_prior_opposed_rl | 3.00× | 12.88 | SENSITIVITY ONLY — not promotional until exact-m |
| YM | ym_prior_opposed_rl | 4.00× | 12.16 | SENSITIVITY ONLY — not promotional until exact-m |
| YM | ym_prior_opposed_rl | 3.00× | 11.67 | SENSITIVITY ONLY — not promotional until exact-m |
| NQ | nq_v2b_s113 | 3.00× | 7.80 | SENSITIVITY ONLY — not promotional until exact-m |
| NQ | nq_v2b_s113 | 4.00× | 7.37 | SENSITIVITY ONLY — not promotional until exact-m |

## 5. $250k standalone boards (common risk budget)

Built by `python -m live.canonical_250k_board [--email]`.

| Board | Score | Notes |
|---|---|---|
| [`INDIVIDUAL_250K_STANDALONE_RANKING.md`](INDIVIDUAL_250K_STANDALONE_RANKING.md) | annualized_net_on_250k | capital=$250k, stress=$25k, max MTM DD=$37.5k, max margin=$125k; no 3×/4× |
| [`INDIVIDUAL_250K_RESEARCH_EFFICIENCY.md`](INDIVIDUAL_250K_RESEARCH_EFFICIENCY.md) | candidate_NS | research ranking (selection-aware status retained) |
| [`INDIVIDUAL_250K_LEVERAGE_LADDER.md`](INDIVIDUAL_250K_LEVERAGE_LADDER.md) | ladder | sensitivity 3×/4× — **not** deployable |

## 6. FX sleeve-overlap & joint-stress

Built by `python -m live.fx_sleeve_overlap_board [--email]`.

| Board | Path |
|---|---|
| Pairwise overlap / joint stress / max margin | [`fx_sleeve_overlap/BOARD.md`](fx_sleeve_overlap/BOARD.md) |

