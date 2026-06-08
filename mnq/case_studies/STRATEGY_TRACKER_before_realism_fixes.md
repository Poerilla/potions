# MNQ ORB — Strategy tracker (research notes)

Central index of execution variants explored in this workspace / chat threads.
**Canonical live model** for Production remains **`scripts/step2_preplaced_stops.py`** (OCO stops, bracket-then-reverse) — see `scripts/validation.md` and `potions/README.md`.

## Intraday ORB Research Leader

**Adaptive 50/150 v2b-only scaleout** remains the mature intraday ORB candidate, but the 2026-05 ordering/plugin audit demotes the headline `$83k` run from "live-real" to "scanner diagnostic."

- Rule: prior-day **MA50 > MA150** (causal `shift(1)` on MNQ daily closes) → trade **v2b breakout only**; otherwise **skip the day** (no v2d).
- Management: **2 MNQ**, 1 off at TP1, runner stop to range-boundary breakeven, runner target at TP2 (`mnq/v2d/README_adaptive_50_150_scaleout.md`).
- **Ordering audit** (`mnq/v2d/paper_replay_v2b_scaleout_ordering.py`, DBN through 2026-04): the published **$83,245 / -$3,130 MTM** row is reproducible, but it is a **Long-priority scanner**. It gives Long the whole-day first chance; if Long never fills, it can still accept a Short that may have occurred earlier. That is useful research, but not how a broker/Pine OCO book behaves.
- **True intraday StrategyPlugin replay** (`live/strategies/v2b_scaleout.py` through `Engine` + `PaperBroker`): the live-orderable OCO mode is now **1,406 trades / 2,806 unit exits**, **$34,444 net**, **-$5,842 closed DD**, **-$5,870 intrabar stress DD**, **46.2%** win, **1.19 PF**, **5.87 Net/Stress**. This is close to the older stitched-CSV snapshot (**1,430 legs / $35,847 / -$5,190 closed DD**) and replaces the `$83k` scanner as the automation number.
- **Literal Long-first executable StrategyPlugin replay** (only trade Short after a filled Long exits): **1,052 trades / 2,102 unit exits**, **$18,927 net**, **-$6,153 closed DD**, **-$6,163 intrabar stress DD**, **46.1%** win, **1.14 PF**, **3.07 Net/Stress**.
- Cross-market hardened OCO pass, common start **2021-03-04**: **NQ is the best V2B expression** with **2,809 unit exits / 1,407 campaigns**, **$389,026 net**, **-$58,840 intrabar stress DD**, **46.4%** win, **1.21 PF**, **6.61 Net/Stress**. MNQ remains the low-capital version at **$34,444 / -$5,870 stress / 5.87 Net/Stress**. YM, ES, MYM, and MES were positive but much weaker under this exact OCO rule. MES is partial coverage because the local MES DBN is corrupted and the fallback CSV ends in 2023-08.
- **Clean-break StrategyPlugin replay** (`live/strategies/v2b_clean_break.py` on completed 5m RTH bars): the broad bullish first-break version survives the broker-like pass, but is smaller than OCO: **MNQ 675 trades / $9,498 net / -$1,950 stress / 4.87 Net-Stress** and **NQ 2,039 trades / $112,027 net / -$19,115 stress / 5.86 Net-Stress**. The 09:45 boundary-stop and ladder variants cut some heat, but they remove too many winners to beat the broad clean-break or OCO rows.

**C3 calendar filter (diagnostic, 2026-05):** v2b scaleout on C3 days only (no MA filter) was **$57,396 / $4,412 MTM DD** — inflated vs tracker because it trades v2b on **v2d-regime** C3 days too. **C3 + MA50>MA150** (causal): **681 legs**, **$41,844 net**, **$4,412 MTM DD**. Neither beats the all-days v2b-only book. The separate **C3 hit + swing + opposite v2b break (×1)** branch remains a lower-frequency overlay (**445 trades**, **$5,556 net**, **$2,108 MTM DD**).

Pine paper-test: `pine/orb_adaptive_50_150_v2b_scaleout.pine`. MTM script: `mnq/v2d/mtm_v2b_scaleout.py`. Ordering audit report: `mnq/v2d/V2B_SCALEOUT_ORDERING_AUDIT.md`. Hardened plugin report: `live/state/v2b_strategy_plugin_replay/V2B_STRATEGY_PLUGIN_REPLAY.md`. Cross-market hardened report: `live/state/v2b_strategy_plugin_cross_market_requested/V2B_OCO_CROSS_MARKET_COMMON_WINDOW.md`; NQ chart pack: `live/state/v2b_strategy_plugin_cross_market_requested/charts/nq_v2b_scaleout_oco_then_reverse/INDEX.md`. Clean-break plugin report: `live/state/v2b_clean_break_broker_like/V2B_CLEAN_BREAK_BROKER_LIKE.md`.

## ATR Supertrend Pine-Parity Correction

The prior promotion of **MYM ATR Supertrend weekly-primary / 10 max / 3-initial / entry guard** is revoked pending a fresh causal validation pass.

What changed:

- A TradingView parity check on 2026-05-08 showed the Pine script was using actual completed-week ATR, while the local chart/result behaved like a daily ATR stop engine.
- Root cause: the Python weekly ATR mapper was called after daily ATR columns already existed, so `atr_stop` / `atr_trend` resolved to the daily columns. The old "weekly-primary" result was therefore mislabeled.
- The old weekly-primary loop also entered on the same daily bar whose close produced the daily flip, which is too early for live execution.
- The shared weekly ATR mapper has been fixed so future weekly-primary runs actually use completed-week ATR.

Corrected MYM comparison:

| Variant | Net | MTM DD | Closed DD | Win Rate | PF | Status |
|---|---:|---:|---:|---:|---:|---|
| Legacy mislabeled MYM "weekly" | $81,587 | -$7,292 | -$1,922 | 57.8% | 15.04 | Research artifact only; not live-promoted |
| Causal daily ATR, no weekly-flat filter | $11,725 | -$13,602 | -$6,942 | 20.6% | 1.45 | Pine default now targets this family |
| Actual completed-week ATR | $40,296 | -$26,958 | -$10,242 | 11.5% | 3.52 | Cleaner weekly concept, but much more heat |

Current practical read: do **not** fund MYM ATR from the old $81k expectation. For MNQ, the first flat-file `StrategyPlugin` ATR signal replays are now banked below; those rows supersede the older ATR artifact leaderboard for live-test ranking. MYM still needs the same plugin pass before it is promoted again.

Key files:

- Legacy artifact and warning: `mym/case_studies/atr_supertrend_fixed_no_scaling/weekly_3initial/README.md`
- Causal daily correction: `mym/case_studies/atr_supertrend_daily_primary_no_weekly_flat_3initial_causal/README.md`
- Actual weekly correction: `mym/case_studies/atr_supertrend_actual_weekly_primary_3initial_causal/README.md`
- Pine parity script: `pine/atr_supertrend_dca_10max_entry_guard_3initial.pine`

## Broker-Like Bar Replay Rankings

This is the current **new standard** table. Rows here are generated by `StrategyPlugin` logic through the flat-file `Engine` + `PaperBroker`: orders become active only after the confirming bar closes, fills come from later bars, positions are persisted, and open units are marked at the final replay close. Full output: `live/state/broker_like_replays/SUMMARY.md`. Summary charts: `live/state/broker_like_replays/charts/INDEX.md`. Detail chart packs: `live/state/broker_like_replays/charts/detail/INDEX.md`. Targeted yearly ORB OCO branch output: `live/state/yearly_orb_range_close_20pct_test/SUMMARY.md` and `live/state/yearly_orb_range_close_20pct_test/charts/detail/INDEX.md`. Targeted monthly overlap ST-retest output: `live/state/monthly_overlap_st_retest_broker_like/SUMMARY.md`; MNQ/NQ validation charts: `live/state/monthly_overlap_st_retest_broker_like/charts/detail/INDEX.md`.

| Rank | Candidate | Instrument | Net | Intrabar Stress DD | Max Open Units | Net / Stress DD | Current Read |
|---:|---|---|---:|---:|---:|---:|---|
| 1 | **Monthly ORB overlap daily-ST retest x5** | NQ | **$787,811** | **-$108,655** | 12 | **7.25** | New strongest targeted plugin row; compelling, but operationally heavier than yearly ORB because retest adds can take exposure to 12 units. |
| 2 | **ATR daily ladder 1/1/2/2/2 10-max** | NQ | **$1,576,610** | **-$255,950** | 10 | **6.16** | Best broad cross-market broker-like row; large account requirement, but cleanest ATR efficiency. |
| 3 | **ATR daily ladder 1/1/2/2/2 10-max** | MNQ | **$147,280** | **-$25,610** | 10 | **5.75** | Best MNQ broker-like row among ATR variants. |
| 4 | **ATR daily 3-initial 10-max** | NQ | **$1,723,980** | **-$308,655** | 10 | **5.59** | Highest NQ net, but more heat than ladder. |
| 5 | **ATR daily 3-initial 10-max** | MNQ | **$160,402** | **-$29,264** | 10 | **5.48** | Highest MNQ net, but ladder remains more capital efficient. |
| 6 | **Yearly ORB scaleout3 20% range-close (OCO entry)** | NQ | **$743,876** | **-$141,210** | 3 | **5.27** | Strongest low-frequency ORB row after OCO-stop entry hardening. |
| 7 | **Yearly ORB scaleout3 20% range-close (OCO entry)** | MNQ | **$66,913** | **-$14,141** | 3 | **4.73** | Promoted low-frequency MNQ ORB branch; materially stronger than prior limit-retest replay. |
| 8 | **Monthly ORB overlap daily-ST retest x5** | YM | **$247,382** | **-$54,030** | 10 | **4.58** | New non-NQ confirmation; cleaner than the older YM monthly restricted branch. |
| 9 | **ATR weekly 2-initial / 3-add / 6-max** | ES | **$857,100** | **-$199,638** | 6 | **4.29** | Weekly sweet-spot sizing translates best to ES, not MNQ. |
| 10 | **Yearly ORB scaleout3 20% range-close (OCO entry)** | ES | **$366,594** | **-$85,700** | 3 | **4.28** | OCO yearly ORB also upgrades ES and now rivals ATR weekly efficiency. |
| 11 | **Monthly ORB overlap daily-ST retest x5** | ES | **$322,847** | **-$76,882** | 12 | **4.20** | ES confirms the overlap branch, but with heavier stress than YM. |
| 12 | **Monthly ORB overlap daily-ST retest x5** | MNQ | **$73,523** | **-$18,348** | 12 | **4.01** | MNQ version survives hardening, but NQ/YM/ES are better expressions. |
| 13 | **Monthly ORB restricted scaleout3** | ES | **$246,453** | **-$66,163** | 3 | **3.72** | Strong monthly ES row, but now behind OCO yearly ORB and overlap-ST replay. |
| 14 | **Monthly ORB restricted scaleout3** | NQ | **$430,465** | **-$122,080** | 3 | **3.53** | NQ survives broker-like timing cut better than MNQ. |
| 15 | **ATR weekly 2-initial / 3-add / 6-max** | NQ | **$1,444,735** | **-$428,375** | 6 | **3.37** | Good net, but more heat than daily ATR variants. |
| 16 | **Monthly ORB restricted scaleout3** | YM | **$179,659** | **-$56,795** | 3 | **3.16** | Possible non-NQ monthly sleeve; now below the overlap-ST YM row. |

Main changes from the theoretical/research tables:

- **MNQ monthly restricted scaleout3 is demoted hard**: research artifact was attractive, but broker-like replay is only **$3,082 net / -$20,809 stress DD**. Same-bar/close assumptions were doing too much work.
- **MNQ monthly restricted boundary-stop entry remains a meaningful repair candidate**: targeted broker-like replay with standing boundary stop entries and the same scaleout/range-close logic improved MNQ to **$40,931 net / -$16,881 stress DD / 2.42 Net-DD**. Output: `live/state/broker_like_replays_monthly_boundary_stop_test/SUMMARY.md`; charts: `live/state/broker_like_replays_monthly_boundary_stop_test/charts/detail/INDEX.md`.
- **Yearly ORB 20% range-close with OCO stop entry is promoted**: targeted replay across all six futures now posts **NQ $743,876 / -$141,210 stress / 5.27 Net-DD**, **MNQ $66,913 / -$14,141 / 4.73**, **ES $366,594 / -$85,700 / 4.28**, **YM $187,615 / -$63,535 / 2.95**, **MYM $12,197 / -$6,093 / 2.00**, **MES $10,495 / -$8,498 / 1.24**. Output: `live/state/yearly_orb_range_close_20pct_test/SUMMARY.md`; charts: `live/state/yearly_orb_range_close_20pct_test/charts/detail/INDEX.md`.
- **MNQ ATR daily ladder is now the top local automation candidate** by broker-like efficiency. The old weekly ATR emphasis does not survive this stricter replay as the leader.
- **NQ is the strongest capital-efficient market**, but it requires much larger capital because stress DD is six figures.
- **MES/MYM did not provide the hoped-for micro diversification** in this broker-like set. MYM weekly 2/3/6 is positive but only **$24,931 / -$18,930 stress**; MES is mostly weak except weekly 2/3/6.
- **Monthly overlap daily-ST retest x5 is now plugin-replayed across all six markets**: the broker-like 4h pass is **NQ $787,811 / -$108,655 stress / 7.25 Net-DD**, **YM $247,382 / -$54,030 / 4.58**, **ES $322,847 / -$76,882 / 4.20**, **MNQ $73,523 / -$18,348 / 4.01**, **MYM $14,043 / -$5,053 / 2.78**, and **MES $8,744 / -$7,828 / 1.12**. This upgrades the branch from “promising research” to “serious targeted candidate,” especially for NQ/YM/ES. New 4h caches were built for ES/MES/YM/MYM; MES used `mes/mes_1min_raw.csv` because the local `.dbn.zst` source reported zstd corruption.
- **v2b MA50>MA150 scaleout now has a true 1m StrategyPlugin replay**. MNQ live-orderable OCO is **$34,444 / -$5,870 stress / 5.87 Net-Stress**; the cross-market pass promotes **NQ OCO** as the stronger V2B expression at **$389,026 / -$58,840 stress / 6.61 Net-Stress**. The `$83k` MNQ long-priority scanner remains diagnostic only. Clean-break variants now have a 5m StrategyPlugin pass; child variants still need their own plugins before ranking under the new standard.

## Research / Artifact Simulation Top 3

These remain useful for idea ranking and sizing hypotheses, but they are not all live-runtime signal replays.

| Rank | Candidate | Market / Size | Net | DD / MTM Heat | Net/DD | Why it is here | Replay Status |
|---:|---|---:|---:|---:|---:|---|---|
| 1 | **Yearly ORB scaleout3 inside-range swing stop, range-close portfolio** | 1 MNQ bundle + 4 MYM bundles = 3 MNQ + 12 MYM units | **$135,878** | **-$6,239 open-heat stress** | **21.78** | Best low-frequency blend found so far; MYM offsets MNQ enough to smooth the equity curve while preserving strong alpha. | Research portfolio sim; MNQ standalone has plugin replay, MYM portfolio plugin replay still needed. |
| 2 | **Yearly ORB scaleout3 inside-range swing stop, range-close standalone** | MNQ, 3-unit bundle | **$68,082** | **-$3,026 closed DD** / **-$4,604 stress** | **22.50 closed** / **14.79 stress** | Cleanest single-market low-frequency sleeve in the research sim. | Plugin replay exists; baseline stricter runtime row is **$39,217 / -$13,379 stress**, and the OCO+20% branch improves to **$66,913 / -$14,141 stress**. |
| 3 | **Monthly ORB overlap range breakout, 4h causal, daily ST limit-retest x5** | MNQ, 3-unit breakout + 5-unit ST retest add | **$87,586** | **-$17,995 4h MTM DD** / **-$18,175 pess. intrabar** | **4.87 MTM** | Research baseline for the overlap continuation branch; uses 4h causal entries and a daily Supertrend retest add to catch trend continuation. | Plugin replay now exists for all six markets; strongest rows are **NQ $787,811 / -$108,655**, **YM $247,382 / -$54,030**, **ES $322,847 / -$76,882**, and **MNQ $73,523 / -$18,348**. |

Runner-up intraday book: true StrategyPlugin OCO v2b-only scaleout on MNQ (**$34,444 net / -$5,870 intrabar stress DD**) and the stronger NQ mirror (**$389,026 / -$58,840 stress**) — mature enough for paper/live parity work, but not the $83k scanner headline.

### Live-Runtime Replay / MTM Audit

The cross-candidate artifact MTM audit is banked at `live/state/candidate_mtm_audits/SUMMARY.md`. It validates execution books and heat for older CSV/unit artifacts, but only the `StrategyPlugin Signal Replay Rankings` table above should be treated as live-runtime signal generation.

## Volume / Participation Overlays

Databento source files and the derived front-month caches are **OHLCV**, so volume is available for participation studies. Confirmed local sources include `mnq/mnq_daily.csv`, `nq/nq_daily.csv`, and `mnq/data/mnq_front_month_4h_from_1m.csv`, all with a `volume` column.

Fresh sidecar charts for the current leaders:

- Yearly ORB inside-range swing/range-close, weekly candles with weekly volume + 20-week average:
  - MNQ: [`yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md`](yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md)
  - NQ: [`../../nq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md`](../../nq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/weekly_candles_volume/INDEX.md)
- ATR Supertrend weekly-primary 10max / 3-initial / entry guard, daily candles with daily volume + 20-day average:
  - MNQ: [`atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md`](atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md)
  - NQ: [`../../nq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md`](../../nq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/volume_charts/INDEX.md)

First read: use these as visual false-breakout research, not as an execution filter yet. A real filter should be tested causally with features such as breakout-week volume vs 20-week average, breakout-day volume vs 20-day average, and whether losing trades cluster on low-volume breaks or exhaustion-volume spikes.

## Fair Passive Benchmark

TradingView's buy-and-hold benchmark is useful, but it is not an apples-to-apples capital comparison for these futures sleeves because TV assumes the full initial capital is passively invested in the chart symbol for the full test. For our purposes, compare against a fixed ETF exposure from the same starting capital, then separately compare futures sleeves using the same account and explicit risk sizing.

First-pass `$50k` benchmark report: [`fair_benchmark_comparison/README.md`](fair_benchmark_comparison/README.md). Builder: [`../../scripts/fair_benchmark_comparison.py`](../../scripts/fair_benchmark_comparison.py).

10-year scaling proxy: [`fair_benchmark_comparison/SCALING_10Y.md`](fair_benchmark_comparison/SCALING_10Y.md). Builder: [`../../scripts/fair_benchmark_scaling_10y.py`](../../scripts/fair_benchmark_scaling_10y.py). This variant lets futures resize only at fresh trade entry, while ETF rows remain fully invested and compounded.

Window: **2020-01-01 through 2025-12-31**. ETF rows use Yahoo adjusted close. Futures rows include both a fixed one-bundle sleeve and a 3x open-heat stress-DD annual scaling model.

| Sleeve | End Capital | Net | Max DD / Stress DD | Return | Net/DD | Peak Size |
|---|---:|---:|---:|---:|---:|---:|
| Yearly ORB MNQ standalone, 1 bundle fixed | $118,082 | $68,082 | -$4,604 | 136.2% | 14.79 | 3 contracts |
| Yearly ORB MNQ+MYM portfolio, 1 bundle fixed | $185,878 | $135,878 | -$6,240 | 271.8% | 21.78 | 3 MNQ + 12 MYM |
| QQQ buy-and-hold | $147,260 | $97,260 | -$33,121 | 194.5% | 2.94 | full ETF capital |
| SPY buy-and-hold | $114,532 | $64,532 | -$19,083 | 129.1% | 3.38 | full ETF capital |
| 50/50 QQQ+DIA buy-and-hold | $120,093 | $70,093 | -$22,327 | 140.2% | 3.14 | full ETF capital |

Initial read: the fixed MNQ+MYM yearly ORB sleeve beats the passive ETF rows on both net and drawdown efficiency over this window, while fixed MNQ standalone has lower net than QQQ but much lower stress DD. The annual 3x-DD scaling rows show the compounding upside, but ending sizes become operationally large, so treat them as capital-efficiency math rather than a live sizing recommendation.

10-year proxy read: QQQ is a strong passive benchmark, ending near **$302k** from `$50k` over 2016-2025. Entry-resized MNQ yearly ORB wins the account-window test at about **$1.28M**, but it reaches **135 contracts**, so it is a scaling-theory result, not a suggested live route. NQ is the biggest winner once starting capital reaches roughly the 3x-DD requirement, but a `$50k` account cannot start NQ under that rule.

## Live-Test Leaderboard

Legacy mixed-source table. Use the **StrategyPlugin Signal Replay Rankings** section above for current automation-runtime ranking. Rows below are retained for historical comparison across research families and may include research artifacts rather than plugin-generated fills.

Capital efficiency here uses **Net / MTM DD** when mark-to-market equity is available. For older ORB studies, use the listed open-heat / closed-DD caveat in the linked study before treating the number as directly comparable.

| Candidate | Market / Size | Net | MTM DD / Stress DD | Net/DD | Why it matters | Live-test caveat |
|---|---:|---:|---:|---:|---|---|
| ATR legacy mislabeled weekly-primary DCA | MYM, max 10 | $81,587 | -$7,292 MTM | 11.19 | Research artifact that exposed the daily/weekly ATR bug | **Not live-promoted**; use corrected causal runs below |
| Corrected daily ATR, no weekly-flat filter | MYM, max 10 | $11,725 | -$13,602 MTM | 0.86 | Closest tradable interpretation of the daily-stop behavior seen on charts | Pine default now targets this family; needs paper parity before funding |
| Corrected actual completed-week ATR | MYM, max 10 | $40,296 | -$26,958 MTM | 1.49 | True weekly ATR concept after mapper fix | High heat and low hit rate; not currently the top live-test candidate |
| **ATR weekly-primary DCA, 10 max, 3 initial, entry guard** | MNQ, max 10 | **$303,214** | **-$16,524 MTM** | **18.35** | Highest MNQ net found so far with good capital efficiency; NQ confirms strongly at **$3.64M / -$123k MTM** | More moving parts than yearly ORB; needs reliable daily/weekly Supertrend state, Friday 15:50 adds, and close-based guard/re-entry automation |
| **Yearly ORB + 1 MNQ unit / 4 MYM units** | 3 MNQ + 12 MYM scaleout units | **$135,878** | **-$6,239 open-heat stress** | **21.78** | Best low-frequency portfolio smoothness found so far; MYM helps diversify MNQ drawdowns | Cross-market execution and larger total order count; yearly ORB samples are smaller |
| **Yearly ORB MNQ standalone** | 3 MNQ scaleout units | **$68,082** | **-$3,026 DD** | **22.50** | Very capital efficient and low-frequency | Smaller sample and less absolute profit than ATR DCA |
| **Monthly ORB overlap range breakout, daily ST limit-retest x5** | NQ/YM/ES/MNQ/MYM/MES, 3-unit breakout + 5-unit retest add | **NQ $787,811 / YM $247,382 / ES $322,847 / MNQ $73,523** | **NQ -$108,655 / YM -$54,030 / ES -$76,882 / MNQ -$18,348 stress** | **NQ 7.25 / YM 4.58 / ES 4.20 / MNQ 4.01** | New 4h StrategyPlugin replay keeps the daily Supertrend filter and turns the retest into a real resting limit order | Riskier exposure profile: max 12 open units; MYM/MES are positive but weaker (**MYM 2.78**, **MES 1.12 Net/DD**) |
| **Monthly ORB overlap range breakout, daily ST filter** | MNQ, 3-unit breakout only | **$50,386** | **-$10,020 4h MTM / -$10,843 pess. intrabar** | **5.03 MTM** | Cleaner version of overlap breakout; skips long breakouts against confirmed daily Supertrend | Lower net than retest branch, but simpler and lower heat |
| **Monthly ORB overlap range breakout, daily ST bearish-reclaim scale-in x5** | MNQ, 3-unit breakout + 5-unit reclaim add | **$58,061** | **-$10,020 4h MTM / -$10,843 pess. intrabar** | **5.79 MTM** | Adds after a confirmed bearish ST flip is reclaimed; improved net without worsening 4h MTM DD in this sample | Less upside than retest branch; only 5 add fills so far |
| **ATR daily-primary DCA, 10 max, 3 initial, entry guard** | MNQ, max 10 | **$235,057** | **-$15,606 MTM** | **15.06** | Strong growth variant; entry guard limits some bad early drift | Worse than weekly-primary on NQ and MNQ; higher churn |
| **ATR daily weekly-flat, 10 max, no entry guard** | MNQ, max 10 | **$188,414** | **-$11,331 MTM** | **16.63** | Cleaner than guard variant; fewest ATR DCA restarts among high-net variants | More exposed during early pullbacks; lower net than weekly-primary |
| **ATR daily weekly-flat, 5 max** | MNQ, max 5 | **$155,056** | **-$10,588 MTM** | **14.65** | Conservative ATR automation baseline; lower execution burden | Gives up upside versus 10 max and weekly-primary |
| **Adaptive 50/150 v2b-only scaleout, StrategyPlugin OCO** | MNQ, 2 contracts | **$34,444** | **-$5,870 stress** | **5.87** | Most mature intraday Pine-style candidate; current plugin arms both sides OCO, then reverses after the first campaign closes | More trades, fee/slippage sensitivity, smaller edge per trade; the $83k long-priority scanner is not the live/Pine parity number |
| **Monthly ORB restricted scaleout3** | MNQ, 3-unit daily bundle | **$105,154** | **-$6,410 stress / -$3,723 closed** | **28.3** | Same monthly OR + range-close rules as 1-lot restricted, with **yearly-style** TP25 / full TP / runner + BE; **~2.4×** the gross pts of 1-lot restricted on this sample | **Worse** heat than 1-lot restricted; **not** the same sample window as yearly ORB (2020–2025) row; daily OHLC; no fees in CSV |
| **Monthly ORB restricted scaleout3** | NQ, 3-unit daily bundle | **$1,323,093** | **-$64,050 stress / -$37,278 closed** | **35.5** | NQ mirror of MNQ scaleout3; very large nominal $ from pt mult | Same caveats as MNQ row; do not rank next to intraday legs without normalizing horizon and contract-equivalents |
| **Monthly ORB restricted stop-limit cycle** | MNQ, 3-unit breakout/bottom + 2-unit refill | **$51,288** | **-$13,144 DD** | **3.90** | New long-only state-machine study: breakout stop, 25% close-stop, bottom-limit reclaim, and post-TP1 top-boundary refills | Daily OHLC only; wide/high-vol ranges can create large losses; needs 4h/1m causal rebuild before live testing |
| **Monthly ORB restricted stop-limit cycle** | NQ, 3-unit breakout/bottom + 2-unit refill | **$612,935** | **-$139,060 DD** | **4.41** | NQ confirms the long-side directional pulse, with similar PF and drawdown behavior | Same daily-OHLC caveat; not yet Pine/Tradovate ready |

Monthly ORB **baseline + range-close restricted** is **about $44k on 1 MNQ** with **about −$2.4k** max equity DD and very sparse fills — intentionally **not** a row-vs-row match to pyramid ATR sizing. Charts and side-by-side read vs these ATR lines: [`monthly_orb/MONTHLY_ORB_RESTRICTED.md`](monthly_orb/MONTHLY_ORB_RESTRICTED.md).

### Monthly ORB restricted — scaleout3 (research)

**Simulator:** [`scripts/monthly_orb_restricted_scaleout3.py`](../../scripts/monthly_orb_restricted_scaleout3.py) · **CSV:** `mnq/mnq_monthly_orb_restricted_scaleout3.csv` (NQ: `nq/nq_monthly_orb_restricted_scaleout3.csv`).

**Stack rank vs this doc (plain read):**

- **vs 1-lot monthly restricted** (~$44k / ~−$2.4k closed in the table above): scaleout3 pushes **much higher gross** on the **bundle point sum** (three units), but **closed DD and stress DD both deepen** versus the single-position book — it trades **capital for expectancy** in the monthly sleeve, not a free lunch.
- **vs Yearly ORB MNQ standalone** ($68k / −$3k on a shorter 2020–2025 yearly sample): scaleout3 shows **higher headline $** on the **full monthly-CSV horizon**, but the windows and rules differ (monthly OR vs Jan–Mar yearly OR, **boundary stop** vs swing stop), so treat as **directional**, not a strict horse race.
- **vs Adaptive v2b-only scaleout** (~$36k / −$5.2k): monthly scaleout3 has **higher Net/closed-DD** on the numbers here, but **far fewer** “trades,” **daily** bar fidelity only, and a **different** economic exposure (three overlapping unit exits per bundle vs 2-lot intraday path).
- **vs ATR DCA 10-max rows**: monthly scaleout3 is **orders of magnitude smaller** in absolute dollars and operational surface than pyramided ATR; it belongs in the **low-touch / low-frequency** bucket with yearly ORB and 1-lot monthly restricted, not next to 10-lot ATR without a sizing bridge.

**Metrics, MAE, stress DD methodology:** [`monthly_orb/METRICS_SCALEOUT3.md`](monthly_orb/METRICS_SCALEOUT3.md). **Charts:** [`monthly_orb/baseline_restricted_scaleout3/INDEX.md`](monthly_orb/baseline_restricted_scaleout3/INDEX.md).

**Broker-like replay update:** the new daily `StrategyPlugin` / `PaperBroker` version demotes the MNQ research row sharply: **MNQ $2,426 net / -$34,398 stress DD**. NQ, ES, and YM survive the stricter timing better (**NQ $430,465 / -$122,080**, **ES $246,453 / -$66,163**, **YM $179,659 / -$56,795**), so this is no longer a blanket MNQ live-test candidate. The monthly idea may still be useful on larger contracts, but the MNQ edge was heavily dependent on optimistic daily same-bar/close behavior.

### Monthly ORB restricted — stop-limit cycle (research)

**Simulator:** [`scripts/monthly_orb_restricted_stop_limit_cycle.py`](../../scripts/monthly_orb_restricted_stop_limit_cycle.py) · **CSV:** `mnq/mnq_monthly_orb_restricted_stop_limit_cycle.csv` (NQ: `nq/nq_monthly_orb_restricted_stop_limit_cycle.csv`). **Charts:** [`monthly_orb/restricted_stop_limit_cycle/INDEX.md`](monthly_orb/restricted_stop_limit_cycle/INDEX.md). **Report:** [`monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md`](monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md).

Current long-only rule state:

- Monthly OR = first 3 daily rows.
- Primary order is a buy stop at the OR high.
- Breakout packages use 3 contracts: 1 off halfway to TP1, 1 off at TP1, 1 runner to TP2.
- Breakouts are invalidated only by a daily close more than **25% back inside** the OR.
- After a failed breakout before TP1, the bottom-limit reclaim becomes available, but a fresh breakout may still fire before the bottom limit fills.
- Bottom-limit reclaim enters at OR low, uses a **daily-close** stop at `OR low - 0.25 * range`, takes 1 off at OR high, and exits the other 2 at TP1.
- After TP1, a 2-contract top-boundary refill can fill while an earlier runner is still open. The refill now closes before TP1 on any daily close **at or below OR high**, including a close below the full range.

Latest long-only results after the 25% close-stop and top-refill fix:

| Market | Packages | Net | Max DD | Win Rate | PF | Avg MAE | Max MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 148 | $51,288 | -$13,144 | 52.0% | 1.63 | 213.2 pts | 1,039.2 pts |
| NQ | 338 | $612,935 | -$139,060 | 49.1% | 1.58 | 120.0 pts | 1,038.0 pts |

The worst months are not simply high trade-count months. The pattern is **failed expansion in wide/high-volatility ranges**: repeated stop-breakouts close 25% back into the OR before TP1, sometimes followed by a bottom-limit daily-close stop, and no TP2 runner to pay for the churn.

**Short mirror:** [`scripts/monthly_orb_restricted_stop_limit_cycle_short.py`](../../scripts/monthly_orb_restricted_stop_limit_cycle_short.py), reports at [`monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md`](monthly_orb/MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md) and NQ mirror. The flipped short-only system is **not viable as-is**: MNQ **-$7,680 / -$23,710 DD / 0.92 PF**, NQ **-$99,092 / -$229,472 DD / 0.92 PF**. Stop-breakdowns and bottom refills were modestly positive, but the top-limit reclaim branch dominated losses.

Practical status: keep this as a promising long-side monthly ORB research branch. It is **not** a live-test candidate yet because the entries, stop invalidations, refills, and same-day sequencing are still daily-OHLC approximations. Next serious step is a 4h or 1m causal rebuild.

### Monthly ORB + weekly Supertrend (scalp + runner, long-only)

Research sim: **`scripts/monthly_orb_st_runner.py`** (weekly ATR Supertrend on daily, causal mapper). Two conceptual lots per qualifying monthly long: **scalp** follows the usual restricted OR exits; **runner** skips the range-close rule while weekly trend stays bullish and exits on monthly RL, weekly bearish flip, or restrictive settle when weekly is not confirming.

**Last batch CSV headline (re-run script for your data window):**

| Instrument | Combined net | $ / pt mult | Max DD (leg-exit equity) | Scalp exits | Runner exits |
|---|---:|---:|---:|---:|---:|
| MNQ | +40,871.75 pts | $2 | −$12,888 | 66 | 85 |
| NQ | +52,941.50 pts | $20 | −$128,705 | 138 | 179 |

Outputs: `mnq/mnq_monthly_orb_st_runner.csv`, `nq/nq_monthly_orb_st_runner.csv`.

### Monthly swing Fib + context charts

Yearly daily PNGs: **monthly fractal swing low → swing high**, default **61.8%** retracement from **H** toward **L** (`H − 0.618×(H−L)`), **green vertical** on the first daily session that trades through that price after pivot confirmation; **weekly Supertrend** stop overlaid; **Jan–Mar yearly OR** high/low for that calendar year. Builder: [`monthly_orb/build_monthly_fib_retrace_charts.py`](monthly_orb/build_monthly_fib_retrace_charts.py) → [`monthly_orb/fib_retrace_yearly/INDEX.md`](monthly_orb/fib_retrace_yearly/INDEX.md) (NQ mirror under `nq/case_studies/monthly_orb/fib_retrace_yearly/` when built with `--daily nq/nq_daily.csv`).

Current practical read: the old ATR weekly-primary leaderboard remains historical context only. The newer **StrategyPlugin signal replay** section above is the live-runtime ranking source for MNQ ATR. MYM/NQ/ES/MES still need equivalent plugin passes before they are used for funding decisions.

## Higher Timeframe ORB Candidate

**Yearly ORB scaleout3 with inside-range swing stop is still the core low-frequency ORB family, and the current broker-like leader branch is the OCO-stop entry + 20% range-close variant.**

- Rule family: Jan-Mar yearly ORB, Apr-Dec retest entries, stop source is the latest confirmed daily swing whose pivot candle is fully inside the yearly ORB, 3 units, Unit 1 off at 25% to TP, Unit 2 off at TP, runner stop to breakeven only after TP, and close remaining units on a daily close back inside the yearly range.
- Targeted broker-like hardening branch (2026-05): OCO stop entries at both yearly boundaries (`oco_stop` entry mode), same scaleout/inside-range swing stop stack, and close only after a daily close reaches **20% back inside** the yearly range (`range_close_inside_frac=0.20`).
- OCO 20% replay snapshot (`live/state/yearly_orb_range_close_20pct_test/SUMMARY.md`): **NQ $743,876 / -$141,210 stress / 5.27**, **MNQ $66,913 / -$14,141 / 4.73**, **ES $366,594 / -$85,700 / 4.28**, **YM $187,615 / -$63,535 / 2.95**, **MYM $12,197 / -$6,093 / 2.00**, **MES $10,495 / -$8,498 / 1.24**.
- MNQ 2020-2025: **26 trades**, **$68,082 gross**, **-$3,026 DD**, **38.5%** win rate, **22.50 Net/DD**.
- NQ 2011-2025: **71 trades**, **$758,754 gross**, **-$30,210 DD**, **32.4%** win rate, **25.12 Net/DD**.
- Portfolio note: the current cross-market test to preserve is **1 MNQ unit + 4 MYM units**, where each unit is the full 3-contract scaleout ladder. That means **3 MNQ + 12 MYM**, with combined 2020-2025 net **$135,878**, closed DD **-$3,292**, and open-heat stress DD **-$6,239**. Details: `mnq/case_studies/yearly_orb_mnq_mym_portfolio/README.md`.
- Pine paper-test harness: `pine/yearly_orb_scaleout3_range_close.pine` (strategy only, no `request.security`; causal defaults: `calc_on_order_fills=false`). Optional weekly Supertrend line: `pine/yearly_orb_weekly_st_overlay.pine` on the same daily chart. Set **Contracts per scaleout batch = 1** for MNQ and **4** for MYM.
- One-page standalone MNQ capital/risk sheet: `mnq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/ONE_PAGE_RUNDOWN.md`.
- Read the study path and caveats here: `mnq/case_studies/YEARLY_ORB_RESEARCH_NOTES.md`.

## ATR Supertrend DCA Correction Notes

The old **ATR Supertrend DCA weekly-primary / 10 max / 3 initial / entry guard** promotion is paused. The following historical notes are retained for audit, but the figures that depended on weekly-primary ATR must be rerun after the weekly mapper fix before they are used for live sizing.

- Rule family: **long only**, completed weekly Supertrend-style **ATR(14) × 3** flip enters at the next available daily open, starts with **3 contracts**, adds **1 contract every 2 eligible Fridays at 15:50 ET**, max **10 contracts**, exits the stack at the next available daily open after the weekly ATR flips bearish.
- Initial-entry guard: if a daily close falls below the original first-entry price, flatten at the next daily open. If the completed weekly trend remains bullish, re-enter after a daily close back above that original entry guard and restart scaling.
- Legacy MNQ/NQ weekly-primary figures in older folders may have inherited the same daily/weekly ATR collision and should be treated as stale until rerun.
- Corrected MYM checks on 2026-05-08: causal daily/no-weekly-flat produced **$11,725 net / -$13,602 MTM DD**; actual completed-week ATR produced **$40,296 net / -$26,958 MTM DD**.
- Capitalization guideline for ATR is temporarily suspended: recalculate from corrected causal outputs, not the legacy weekly-primary tables.
- Charts show **solid daily ATR stops** and **dashed completed-week ATR stops** on the same yearly chart. The weekly-primary variant uses the dashed weekly layer as the actual trend engine; the daily layer is context.
- Study folders: `mnq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/README.md` and `nq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial/README.md`. Conservative benchmark: `mnq/case_studies/atr_supertrend_dca_long_biweekly_5max_weekly_flat/README.md`.
- Sizing sensitivity: the **1,1,2,2,2, then 1s** ladder reduced heat but gave up upside. MNQ weekly-primary ladder: **$263,784 net**, **-$12,808 MTM DD**, **-$3,209 worst MAE**, **20.60 Net/MTM**. NQ weekly-primary ladder: **$3,044,840 net**, **-$128,200 MTM DD**, **-$32,030 worst MAE**, **23.75 Net/MTM**. It is a viable lower-heat alternative, but the **3-initial** version remains the promoted high-profit candidate because NQ confirmation is stronger.
- Yearly ORB alignment test: first long stacks/restarts were allowed only after a prior daily close above the Jan-Mar yearly ORB high; adds/exits stayed unchanged. This **did not beat the base ATR candidates**. MNQ weekly-primary 3-initial fell to **$93,640 net / -$11,207 MTM DD** from **$303,214 / -$16,524**; NQ weekly-primary 3-initial fell to **$1.36M / -$112k** from **$3.64M / -$123k**. The filter reduced MAE and trade count, but gave up too much trend participation. Study folders use the `_yorb` suffix, e.g. `mnq/case_studies/atr_supertrend_weekly_primary_biweekly_10max_entry_guard_3initial_yorb/README.md`.

| Code / folder | What it is | Tier‑1 entry | Exit / risk | Snapshot performance (MNQ NY, ~2021→)** |
|----------------|------------|--------------|-------------|-------------------------------------------|
| **step2 / `mnq_orb_results_stops.csv`** | README canon **v2b** | OCO **buy stop RH+tick** / **sell stop RL−tick** after OR; slip ticks; bracket TP **RH±Range**, stop **opposite boundary** | Bracket‑then‑reverse; max 2 legs/day; 15:55 cutoff | **~1,991 legs**, Σ Net **~+$15,877**, Max DD **~−$4,716** (see fresh CSV / validation.md) |
| **`open_limit/orb_open_limit_v2b.py` → `mnq_orb_open_limit.csv`** | Research fork (**not** README canon) | First **5 m close** beyond RH/RL; **limit @ 09:30 session open** after breakout bar | Same measured-move idea but **different fills** than OCO | Was used for early charts; **superseded** for canon comparisons by step2 |
| **`v2b_child/orb_open_limit_v2b_child.py`** | Canon **v2b tier‑1** + optional **child** scale‑ins | Same as step2 for tier‑1 | After OCO fill: up to **N** qualifying **5 m** “child” bars → limit @ bar **close**; **flat everyone** at same TP/SL | **max_child_adds=0** reproduces step2 exactly (**Σ Net $15,877**). **+1 add** Σ Net **~+$27,916**; **+2 adds** Σ Net **~+$34,269** (higher risk — deeper DD) — see `v2b_child/README.md` |
| **`v2b_c/`** (`build_case_studies.py`) | **Charts only** for v2b_child (**3‑contract cap** CSV by default) | — | Annotates tier‑1 OCO fill + add1/add2 limits | Batch PNGs + `INDEX.md`; rules identical to `v2b_child` |
| **`swept_liquidity_orb_breakout/resim_scale_in_ladder.py`** | Different playbook on **`mnq_swept_orb_breakout.csv`** legs | L0±15 scale + child candles; TP1‑only sim | Tier‑1 stop **L0±sl_pts**; child stops **RH−edge / RL+edge** | Full CSV replay **~−$573** cumulative Net with ladder defaults; **387** loss charts folder — **not** comparable $‑wise to step2 |
| **`v2d/mnq_orb_results_adaptive_50_150.csv`** | **Adaptive 50/150**: prior‑day **MA50 vs MA150** chooses **v2b vs v2d** per session | v2b arm = OCO breakout; v2d arm = fade per `validation.md` | Mixed | **~1,919 legs**, Σ Net **~+$18,885**, Max DD **~−$3,542** |
| **`v2d/benchmark_v2b_scaleout_candidates.py`** | **Long-priority scanner** for v2b-only scaleout on **1 m** (MA50>MA150 filter); useful diagnostic, not broker OCO | v2b breakout **RH+tick** / **RL−tick**; TP1/TP2 scaleout | Reproducible scanner headline: **1,302** legs, **+$83,245**, closed **−$2,730**, **MTM −$3,130** |
| **`v2d/paper_replay_v2b_scaleout_ordering.py`** | **Execution-ordering audit** for the v2b-only scaleout book | compares long-priority scanner vs Pine-like OCO vs strict long-first | Live/Pine parity OCO: **1,441** legs, **+$35,210**, closed **−$5,190**, **MTM −$5,482** |
| **`v2d/run_adaptive_50_150_scaleout.py`** | Stitched adaptive CSV replay (legacy) | v2b + v2d arms | v2b-only CSV snapshot: **1,430** legs, **+$35,847**, DD **−$5,190**; now best treated as close to the OCO parity row |
| **`v2d/orb_adaptive_50_150_child.py`** | **Unified combined sim:** same routing as rows above + **`v2b_child`** scale‑ins on **both** arms (v2d fade tier‑1 gets the same 5 m child logic as OCO tier‑1) | v2b: OCO + children; v2d: fade + children; shared TP/SL per leg | **`max_child_adds=0`** → **$18,885** / **1,919 legs** (matches stitched adaptive). **`=1`** Σ **~+$27,867**, DD **~−$5,424**. **`=2`** Σ **~+$30,940**, DD **~−$8,757** |
| **`potions/scripts/monthly_orb_restricted_scaleout3.py`** | **Monthly OR** (3 sessions) + range-close + **3-unit** TP25/TP/runner, **boundary** stop | Daily close breakout; retest **limit** at RH/RL; same FSM as 1-lot restricted | MNQ **~$105k** / **−$3.7k** closed DD / **−$6.4k** stress (see `monthly_orb/METRICS_SCALEOUT3.md`); NQ mirror | Daily OHLC; not Pine-parity checked; fees not in CSV |
| **`case_studies/v2b_m/`** | **Filtered research book:** tier‑1 CSV rows restricted to **Long**, **`bullish_break`**, prior‑month‑high OR geometry (`EPS_IDX_PT`) | Same tier‑1 **long** idea as canon on those rows | Stats via `run_v2b_m.py`; optional **2‑lot scale‑out** (**`v2b_m_so/`**): TP1 **RH+R**, runner SL **RH+tick**, TP2 **RH+2R** — **363** overlapping sessions default sample: baseline sim Σ **~+$3,795**, SO Σ **~+$9,418** (see **`v2b_m_so/README.md`** for full discrete rules) |
| **`mnq/v2e/`** (2026 London base) | **London sweep long only** — **no ORB**: ``stop_hunter`` vs **[02:00–09:30)** low → fractal **breaker** → **piercer** → limit pullback | Limit @ **breaker_high** | SL options **London_low / breaker_low / stop_hunter_low**; TP ``SH_low + 3×(piercer_high−SH_low)`` | **~250** setups / default 1 m span; Σ Net **negative** on current defaults — see **`mnq/v2e/README.md`** + ``scripts/backtest_london_sweep_breaker.py`` |

**Note:** Numbers drift slightly when DB end‑date moves; always re‑run the listed script and read CSV totals.

## Where to read full rules

| Topic | Path |
|-------|------|
| Monthly ORB restricted + **scaleout3** (daily sim + charts) | `mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED.md` · `potions/scripts/monthly_orb_restricted_scaleout3.py` |
| Canon v2 / v2b / v2d definitions | `potions/scripts/validation.md` |
| Portfolio README stats | `potions/README.md` |
| Swept ladder (child OR boundary stops, TP1) | `case_studies/swept_liquidity_orb_breakout/README.md` |
| v2b + child backtest (OCO tier‑1) | `case_studies/v2b_child/README.md` |
| v2b_c PNG workflow | `case_studies/v2b_c/README.md` |
| Adaptive **50/150 + children** (single simulator) | `mnq/v2d/orb_adaptive_50_150_child.py` |
| v2d regime **winners / losers** case PNGs | `case_studies/v2d_regime_case_studies/` (`build_v2d_winners_losers.py`) |
| **v2e London sweep (breaker / piercer)** | `mnq/v2e/README.md` |

## Adaptive 50/150 + **v2b_child**

- **Unified sim:** `mnq/v2d/orb_adaptive_50_150_child.py` runs **one** intraday path per session: prior‑day **MA50 vs MA150** selects **v2b OCO + children** or **v2d fade + children** (same 5 m RH/RL child rules and shared TP/SL as `orb_open_limit_v2b_child.py`). **`--max-child-adds 0`** reproduces stitched adaptive totals (**~$18,885** Σ Net on **1,919** legs on this DB snapshot).
- **CSV join (legacy / diagnostic):** `v2b_child/report_adaptive_v2bc.py` pastes **`Regime`** labels onto **`v2b_child`**‑only CSV legs — **different universe** than the unified sim; useful only if you understand overlap (**~224** child‑only keys vs adaptive). See `v2b_child/README.md`.
