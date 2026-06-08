# MNQ monthly ORB charts

Daily-candle annotations for the monthly ORB study. The shaded band is the first 3 trading days of the month.

## Current Realistic 4H Branch

The current realistic branch to keep optimizing is **monthly ORB 4h close entry + confirmed 4h swing stop**.

Why we moved here:

- The original daily boundary-entry restricted results were useful research, but too optimistic for live testing because they assumed a daily breakout could later fill at the opening-range boundary with favorable path knowledge.
- The first 4h rewrite fixed the entry by waiting for a 4h candle to close outside the monthly OR, but the range-close restriction choked many trades and made the strategy less natural to automate.
- The current 4h swing-stop branch keeps the causal 4h breakout entry and removes the close-back-inside exit. Risk is now controlled by a confirmed 4h swing low/high, with the OR midpoint used when the swing sits beyond the opposing OR boundary.
- This is easier to express in automation: wait for a 4h close outside the range, read the last confirmed 4h swing, place the trade, then exit by stop/target/period close.

Rules:

- Monthly OR = first 3 trading sessions of the month from the daily file.
- Entry = 4h candle close outside the monthly OR.
- Long stop = most recent confirmed 4h swing low; short stop = most recent confirmed 4h swing high.
- A 4h swing is causal only after the next 4h candle confirms it.
- If the swing stop is beyond the opposing OR boundary, use the OR midpoint.
- Target = monthly OR measured move.
- No close-back-inside restriction.
- One live trade at a time; max 2 completed attempts per month.
- After a completed trade, the next attempt must re-arm with a daily close back inside the monthly OR, then a fresh 4h close outside.

Latest MNQ results:

| Variant | Trades | Net USD | Max closed DD | Win rate | PF |
|---|---:|---:|---:|---:|---:|
| 4h swing-stop single | 131 | $7,879 | $-8,336 | 46.6% | 1.21 |
| 4h swing-stop scaleout3 | 131 | $16,891 | $-15,093 | 46.6% | 1.21 |

Artifacts:

- Report: [MONTHLY_ORB_4H_SWING_STOP.md](MONTHLY_ORB_4H_SWING_STOP.md)
- Single-leg charts: [baseline_4h_swing_stop/INDEX.md](baseline_4h_swing_stop/INDEX.md)
- Scaleout3 charts: [baseline_scaleout3_4h_swing_stop/INDEX.md](baseline_scaleout3_4h_swing_stop/INDEX.md)
- Daily-close breakout diagnostics: [MONTHLY_ORB_DAILY_CLOSE_BREAKOUT_DIAGNOSTICS.md](MONTHLY_ORB_DAILY_CLOSE_BREAKOUT_DIAGNOSTICS.md)
- 4h trade studies: [MONTHLY_ORB_4H_TRADE_STUDIES.md](MONTHLY_ORB_4H_TRADE_STUDIES.md)
- Daily-close breakout scaleout4: [MONTHLY_ORB_DAILY_CLOSE_SCALEOUT4.md](MONTHLY_ORB_DAILY_CLOSE_SCALEOUT4.md)
- Restricted stop-limit cycle: [MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md](MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md)
- Restricted stop-limit cycle charts: [restricted_stop_limit_cycle/INDEX.md](restricted_stop_limit_cycle/INDEX.md)
- Restricted stop-limit cycle 4h causal sim: [restricted_stop_limit_cycle_4h_causal/README.md](restricted_stop_limit_cycle_4h_causal/README.md)
- Restricted stop-limit cycle 4h hardened variants: [restricted_stop_limit_cycle_4h_causal/HARDENED_VARIANTS.md](restricted_stop_limit_cycle_4h_causal/HARDENED_VARIANTS.md)
- Restricted stop-limit cycle 4h causal charts: [MNQ close](restricted_stop_limit_cycle_4h_causal/charts_mnq_close/INDEX.md), [MNQ next-open](restricted_stop_limit_cycle_4h_causal/charts_mnq_next_open/INDEX.md), [NQ close](restricted_stop_limit_cycle_4h_causal/charts_nq_close/INDEX.md), [NQ next-open](restricted_stop_limit_cycle_4h_causal/charts_nq_next_open/INDEX.md)
- Restricted stop-limit cycle short: [MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md](MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md)
- Restricted stop-limit cycle short charts: [restricted_stop_limit_cycle_short/INDEX.md](restricted_stop_limit_cycle_short/INDEX.md)
- Overlap-range breakout study: [MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT.md](MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT.md)
- Overlap-range **MAE vs stop + 2-lot runner** sweep: [MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md](MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md) (`python scripts/monthly_orb_overlap_range_breakout.py --sensitivity`)
- Overlap-range breakout charts: [overlap_range_breakout/INDEX.md](overlap_range_breakout/INDEX.md)
- Overlap-range breakout 4h causal stop/limit-cycle rewrite: [overlap_range_breakout_4h_causal/README.md](overlap_range_breakout_4h_causal/README.md) (`python scripts/monthly_orb_overlap_range_breakout_4h_causal.py --market both --exit-fill-mode both`)
- Clean daily-close breakout month charts: [daily_close_breakout_diagnostics/clean_months/INDEX.md](daily_close_breakout_diagnostics/clean_months/INDEX.md)
- Yearly OR rail charts: [monthly_orb_yearly_range_lines/INDEX.md](monthly_orb_yearly_range_lines/INDEX.md) (overlap-range trades overlaid when `mnq/mnq_monthly_orb_overlap_range_breakout.csv` exists; quick rebuild: `python scripts/monthly_orb_4h_breakout_diagnostics.py --yearly-range-lines-only`)
- Cached 4h candles: `../../data/mnq_front_month_4h_from_1m.csv`
- Simulator: `../../../scripts/monthly_orb_4h_close_entry.py`
- Trade-study script: `../../../scripts/monthly_orb_4h_trade_studies.py`
- Daily-close scaleout4 script: `../../../scripts/monthly_orb_daily_close_scaleout4.py`
- Restricted stop-limit cycle script: `../../../scripts/monthly_orb_restricted_stop_limit_cycle.py`
- Restricted stop-limit cycle short script: `../../../scripts/monthly_orb_restricted_stop_limit_cycle_short.py`
- Overlap-range breakout script: `../../../scripts/monthly_orb_overlap_range_breakout.py`
- Overlap-range 4h causal script: `../../../scripts/monthly_orb_overlap_range_breakout_4h_causal.py`

Cache note: reruns use `mnq/data/mnq_front_month_4h_from_1m.csv` by default so the 1-minute DBN does not need to be reread. Use `--rebuild-4h-cache` only when the raw 1-minute history changes.

Breakout-quality read from the corrected daily-close diagnostics:

- Total non-overlapping daily-close breaks: **107**
- False breaks, defined as touching the opposing OR boundary before TP1: **29** (**27.1%**)
- Wide-berth TP1 before opposing boundary: **63** (**58.9%**)
- Clean 1R, defined as TP1 before any daily close back inside and before any 4h trade back into the OR: **36** (**33.6%**)
- Hit TP2: **30** (**28.0%**)
- Clean and hit TP2: **18** (**16.8%**)

This says the monthly OR daily-close breakout has a real directional pulse, but it is not the ultra-clean edge implied by repeated 4h outside-close counts. The edge needs a selective entry/risk wrapper rather than a naive chase.

Latest clean-break trade test:

- Clean-break rank<=3 3-unit runner: **29 trades**, **$35,960** marked net, **-$7,100** max closed DD, **44.8%** win rate, **3.31 PF**.
- That result is runner-sensitive: excluding the two marked-final open runners, the same model is **-$12,169** with **-$12,691** max closed DD.
- Simple 4h close + opposing OR stop: **139 trades**, **$7,292** net, **-$8,648** max DD, **61.2%** win rate, **1.14 PF**.
- Takeaway: the clean-break idea is not dead, but the current version is not a standalone live candidate. It needs a defined runner exit and/or stronger loss filter before it can compete with the restricted inside-candle candidate.

Daily-close scaleout4 test:

- Entry at first daily close outside the monthly OR, 4 units: 1 off halfway to TP1, 2 off at TP1, 1 off at TP2, close all before TP1 on a daily close back inside, and move the runner stop to the breakout-side range boundary after TP1.
- MNQ result: **80 trades**, **$11,144** net, **-$19,777** max DD, **47.5%** win rate, **1.18 PF**.
- The long side carried nearly all edge: **$11,477** long net versus **-$333** short net. The short-side drawdown was much worse.
- Takeaway: this validates that daily close breakouts can extend, but the close-back-inside loss can be too large without an initial hard stop or better “do not chase stretched close” rule.

Restricted stop-limit cycle test:

- Long-only daily-OHLC study extending the restricted branch: stop-entry breakout attempts at the OR high, false breakout close-out, post-TP1 top-boundary retests, and bottom-boundary limits after failed confirmed breakouts.
- MNQ result after allowing 2-contract top-boundary refills while a runner remains open, allowing fresh breakout attempts before a bottom-limit reclaim fills, replacing the close-back-inside/hard-stop exits with 25% daily-close thresholds, and closing top refills on any daily close at/below the OR high: **148 packages**, **$51,288** net, **-$13,144** max DD, **52.0%** win rate, **1.63 PF**.
- Most edge came from stop-breakouts and bottom-limit reclaims: stop-breakouts added **$28,405** net, bottom-limit reclaims added **$18,412** net, and top refills added **$4,470**.
- The mirrored short-only version is not viable in this form: **130 packages**, **-$7,680** net, **-$23,710** max DD, **33.8%** win rate, **0.92 PF**. Stop-breakdowns and bottom refills were modestly positive, but top-limit reclaims lost **-$16,098**.
- Causal 4h sidecar completed using front-month 1-minute data resampled to 4h, with orders live only after the confirming bar closes. MNQ close-fill: **141 packages**, **$54,780** net, **-$10,330** DD, **51.1%** win rate, **1.69 PF**. MNQ next-open daily-close exits: **143 packages**, **$52,637** net, **-$14,906** DD, **50.3%** win rate, **1.61 PF**. NQ next-open exits remained positive too: **$613,818** net, **-$148,712** DD, **44.7%** win rate, **1.55 PF**.
- Takeaway: this is promising enough to keep and is no longer only a daily-bar artifact, but next-open exits add real drawdown. The next execution pass should use 1-minute bars for fills/ordering before porting to Pine or MultiCharts.

Overlap-range breakout test:

- Treat adjacent overlapping monthly ORs as one combined range, then trade a daily-close breakout of that combined range with a midpoint stop and one measured-move target.
- MNQ result: **23 trades**, **$14,743** net, **-$2,569** max DD, **56.5%** win rate, **2.42 PF**.
- The long side is the real signal: **$14,004** long net versus **$739** short net. Shorts were nearly flat and much less efficient.
- Takeaway: this is one of the cleaner monthly OR observations so far. It uses fewer trades, has low closed DD, and appears to capture stacked monthly ranges as support/resistance clusters. Next work should test long-only, stop alternatives, and 4h execution timing before treating it as a live candidate.

## Current Best Candidate Note

Best current monthly ORB execution candidate: **restricted inside-candle source-stop ladder + monthly range targets + stale-limit cancellation**.

Why it is the lead candidate as of the latest study pass:

- It is causal on the available data: the monthly OR is known after the first 3 daily bars, the breakout is known after a daily close, and the inside-candle limit is live after that signal.
- It uses the selected inside opposite candle/run as a more selective pullback entry, then keeps the efficient source-stop logic.
- The stale-limit rule cancels the setup if TP1 already traded before the limit filled, avoiding late entries after the measured move has already paid.
- Among the intraday-validated variants tested so far, it has the best blend of net, drawdown, and profit factor: **$19,069.50 net**, **-$5,902.00 max DD**, **48.48% win rate**, **2.16 PF** on 3-contract MNQ ladder assumptions.

Reference files:

- Study report: [INSIDE_RANGE_TARGET_LADDER_CANCEL_STALE_LIMIT_STUDY.md](INSIDE_RANGE_TARGET_LADDER_CANCEL_STALE_LIMIT_STUDY.md)
- Charts: [inside_source_stop_ladder3_range_targets_cancel_stale_restricted_intraday/INDEX.md](inside_source_stop_ladder3_range_targets_cancel_stale_restricted_intraday/INDEX.md)
- Main CSV: `../../mnq_monthly_orb_inside_restricted_source_stop_ladder3_range_targets_cancel_stale_intraday.csv`

Conservative backup candidate: **restricted 2-contract source-stop scaleout 2R**, which has lower gross DD and simpler management, but lower total net.

## Adaptive 50/150 Scaleout Bias Check

Tested monthly ORB as a causal filter against the **adaptive 50/150 2-contract scaleout** book. The broad monthly outside-only filter reduced drawdown but also cut net/points: baseline **$30,218.50 net / -$7,498.00 DD** versus outside-only **$24,568.50 net / -$6,357.00 DD**. The strongest actionable split was more specific: keep all v2b scaleout rows, but require v2d rows to align with the monthly bias. In the stricter re-sim, that version improved to **$35,903.00 net / -$5,190.00 DD**, because the v2d monthly-aligned subset was roughly flat/slightly positive while the full v2d scaleout subset was negative.

References: [ADAPTIVE_SCALEOUT_MONTHLY_BIAS_RESIM.md](ADAPTIVE_SCALEOUT_MONTHLY_BIAS_RESIM.md), [ADAPTIVE_SCALEOUT_MONTHLY_BIAS.md](ADAPTIVE_SCALEOUT_MONTHLY_BIAS.md)

Periods charted: 81  ·  Net: +15751.25 pts ($+31,502 / 1 MNQ gross)

| Year | Periods | Net pts | Folder |
|---:|---:|---:|---|
| 2019 | 8 | +2003.00 | [2019/](2019/INDEX.md) |
| 2020 | 12 | +4415.50 | [2020/](2020/INDEX.md) |
| 2021 | 12 | +316.50 | [2021/](2021/INDEX.md) |
| 2022 | 12 | +1797.00 | [2022/](2022/INDEX.md) |
| 2023 | 11 | +3160.75 | [2023/](2023/INDEX.md) |
| 2024 | 12 | +166.00 | [2024/](2024/INDEX.md) |
| 2025 | 11 | +3887.00 | [2025/](2025/INDEX.md) |
| 2026 | 3 | +5.50 | [2026/](2026/INDEX.md) |

## All Periods

| Period | Symbol | Range | Pattern | Trades | Net pts | Chart |
|---|---|---:|---|---:|---:|---|
| 2019-05 | MNQM9 | 236.00 | SW+SW | 2 | +472.00 | [2019/2019-05.png](2019/2019-05.png) |
| 2019-06 | MNQM9 | 270.75 | LW | 1 | +270.75 | [2019/2019-06.png](2019/2019-06.png) |
| 2019-07 | MNQU9 | 142.00 | LL+LW | 2 | +0.00 | [2019/2019-07.png](2019/2019-07.png) |
| 2019-08 | MNQU9 | 364.50 | SW+SP | 2 | +338.50 | [2019/2019-08.png](2019/2019-08.png) |
| 2019-09 | MNQU9 | 114.25 | LW+LW | 2 | +228.50 | [2019/2019-09.png](2019/2019-09.png) |
| 2019-10 | MNQZ9 | 366.75 | LP | 1 | +248.00 | [2019/2019-10.png](2019/2019-10.png) |
| 2019-11 | MNQZ9 | 157.00 | LW | 1 | +157.00 | [2019/2019-11.png](2019/2019-11.png) |
| 2019-12 | MNQZ9 | 288.25 | LW | 1 | +288.25 | [2019/2019-12.png](2019/2019-12.png) |
| 2020-01 | MNQH0 | 172.50 | LW | 1 | +172.50 | [2020/2020-01.png](2020/2020-01.png) |
| 2020-02 | MNQH0 | 394.00 | LW+LL | 2 | +0.00 | [2020/2020-02.png](2020/2020-02.png) |
| 2020-03 | MNQH0 | 754.50 | SW | 1 | +754.50 | [2020/2020-03.png](2020/2020-03.png) |
| 2020-04 | MNQM0 | 368.75 | LW | 1 | +368.75 | [2020/2020-04.png](2020/2020-04.png) |
| 2020-05 | MNQM0 | 321.75 | LW+LW | 2 | +643.50 | [2020/2020-05.png](2020/2020-05.png) |
| 2020-06 | MNQM0 | 247.00 | LW+LW | 2 | +494.00 | [2020/2020-06.png](2020/2020-06.png) |
| 2020-07 | MNQU0 | 346.75 | LW+LW | 2 | +693.50 | [2020/2020-07.png](2020/2020-07.png) |
| 2020-08 | MNQU0 | 218.50 | LL+LW | 2 | +0.00 | [2020/2020-08.png](2020/2020-08.png) |
| 2020-09 | MNQU0 | 883.75 | SW | 1 | +883.75 | [2020/2020-09.png](2020/2020-09.png) |
| 2020-10 | MNQZ0 | 399.75 | LW+LL | 2 | +0.00 | [2020/2020-10.png](2020/2020-10.png) |
| 2020-11 | MNQZ0 | 405.00 | LW | 1 | +405.00 | [2020/2020-11.png](2020/2020-11.png) |
| 2020-12 | MNQZ0 | 226.50 | LL+LW | 2 | +0.00 | [2020/2020-12.png](2020/2020-12.png) |
| 2021-01 | MNQH1 | 438.00 | LW+LW | 2 | +876.00 | [2021/2021-01.png](2021/2021-01.png) |
| 2021-02 | MNQH1 | 800.75 | LL+SP | 2 | -1021.50 | [2021/2021-02.png](2021/2021-02.png) |
| 2021-03 | MNQH1 | 745.25 | SP | 1 | -538.50 | [2021/2021-03.png](2021/2021-03.png) |
| 2021-04 | MNQM1 | 286.50 | LW | 1 | +286.50 | [2021/2021-04.png](2021/2021-04.png) |
| 2021-05 | MNQM1 | 566.75 | SP | 1 | -305.50 | [2021/2021-05.png](2021/2021-05.png) |
| 2021-06 | MNQM1 | 310.75 | LW | 1 | +310.75 | [2021/2021-06.png](2021/2021-06.png) |
| 2021-07 | MNQU1 | 258.00 | LW+LL | 2 | +0.00 | [2021/2021-07.png](2021/2021-07.png) |
| 2021-08 | MNQU1 | 207.25 | LL+SL | 2 | -414.50 | [2021/2021-08.png](2021/2021-08.png) |
| 2021-09 | MNQU1 | 146.75 | SW+SW | 2 | +293.50 | [2021/2021-09.png](2021/2021-09.png) |
| 2021-10 | MNQZ1 | 468.00 | LW | 1 | +468.00 | [2021/2021-10.png](2021/2021-10.png) |
| 2021-11 | MNQZ1 | 418.25 | LW+LP | 2 | +456.00 | [2021/2021-11.png](2021/2021-11.png) |
| 2021-12 | MNQZ1 | 889.75 | LP | 1 | -94.25 | [2021/2021-12.png](2021/2021-12.png) |
| 2022-01 | MNQH2 | 424.25 | SW | 1 | +424.25 | [2022/2022-01.png](2022/2022-01.png) |
| 2022-02 | MNQH2 | 805.00 | SW | 1 | +805.00 | [2022/2022-02.png](2022/2022-02.png) |
| 2022-03 | MNQH2 | 491.25 | SW+SL | 2 | +0.00 | [2022/2022-03.png](2022/2022-03.png) |
| 2022-04 | MNQM2 | 448.50 | SW | 1 | +448.50 | [2022/2022-04.png](2022/2022-04.png) |
| 2022-05 | MNQM2 | 474.50 | LL+SW | 2 | +0.00 | [2022/2022-05.png](2022/2022-05.png) |
| 2022-06 | MNQM2 | 502.75 | SW | 1 | +502.75 | [2022/2022-06.png](2022/2022-06.png) |
| 2022-07 | MNQU2 | 367.00 | LW+LW | 2 | +734.00 | [2022/2022-07.png](2022/2022-07.png) |
| 2022-08 | MNQU2 | 494.25 | LL+SW | 2 | +0.00 | [2022/2022-08.png](2022/2022-08.png) |
| 2022-09 | MNQU2 | 443.75 | SL+LW | 2 | +0.00 | [2022/2022-09.png](2022/2022-09.png) |
| 2022-10 | MNQZ2 | 785.75 | LL+SL | 2 | -1571.50 | [2022/2022-10.png](2022/2022-10.png) |
| 2022-11 | MNQZ2 | 926.25 | LP | 1 | +454.00 | [2022/2022-11.png](2022/2022-11.png) |
| 2022-12 | MNQZ2 | 404.50 | SL+SW | 2 | +0.00 | [2022/2022-12.png](2022/2022-12.png) |
| 2023-01 | MNQH3 | 337.50 | SL+LW | 2 | +0.00 | [2023/2023-01.png](2023/2023-01.png) |
| 2023-02 | MNQH3 | 895.00 | SP | 1 | +32.75 | [2023/2023-02.png](2023/2023-02.png) |
| 2023-03 | MNQH3 | 498.25 | LL+LW | 2 | +0.00 | [2023/2023-03.png](2023/2023-03.png) |
| 2023-04 | MNQM3 | 194.50 | SW+SW | 2 | +389.00 | [2023/2023-04.png](2023/2023-04.png) |
| 2023-05 | MNQM3 | 324.25 | LW | 1 | +324.25 | [2023/2023-05.png](2023/2023-05.png) |
| 2023-07 | MNQU3 | 84.50 | SW+SW | 2 | +169.00 | [2023/2023-07.png](2023/2023-07.png) |
| 2023-08 | MNQU3 | 549.75 | SW+SW | 2 | +1099.50 | [2023/2023-08.png](2023/2023-08.png) |
| 2023-09 | MNQU3 | 207.75 | SW+SL | 2 | +0.00 | [2023/2023-09.png](2023/2023-09.png) |
| 2023-10 | MNQZ3 | 394.75 | LW+LL | 2 | +0.00 | [2023/2023-10.png](2023/2023-10.png) |
| 2023-11 | MNQZ3 | 817.50 | LW | 1 | +817.50 | [2023/2023-11.png](2023/2023-11.png) |
| 2023-12 | MNQZ3 | 328.75 | LW | 1 | +328.75 | [2023/2023-12.png](2023/2023-12.png) |
| 2024-01 | MNQH4 | 516.25 | SL+LW | 2 | +0.00 | [2024/2024-01.png](2024/2024-01.png) |
| 2024-02 | MNQH4 | 512.75 | LP | 1 | +284.00 | [2024/2024-02.png](2024/2024-02.png) |
| 2024-03 | MNQH4 | 348.00 | SL+LL | 2 | -696.00 | [2024/2024-03.png](2024/2024-03.png) |
| 2024-04 | MNQM4 | 410.25 | SW | 1 | +410.25 | [2024/2024-04.png](2024/2024-04.png) |
| 2024-05 | MNQM4 | 664.00 | LW | 1 | +664.00 | [2024/2024-05.png](2024/2024-05.png) |
| 2024-06 | MNQM4 | 319.50 | LW | 1 | +319.50 | [2024/2024-06.png](2024/2024-06.png) |
| 2024-07 | MNQU4 | 624.00 | LL+SW | 2 | +0.00 | [2024/2024-07.png](2024/2024-07.png) |
| 2024-08 | MNQU4 | 1502.50 | SL+LP | 2 | -1625.25 | [2024/2024-08.png](2024/2024-08.png) |
| 2024-09 | MNQU4 | 772.00 | SL+LW | 2 | +0.00 | [2024/2024-09.png](2024/2024-09.png) |
| 2024-10 | MNQZ4 | 513.50 | LP | 1 | -257.50 | [2024/2024-10.png](2024/2024-10.png) |
| 2024-11 | MNQZ4 | 274.00 | LW | 1 | +274.00 | [2024/2024-11.png](2024/2024-11.png) |
| 2024-12 | MNQZ4 | 396.50 | LW+LW | 2 | +793.00 | [2024/2024-12.png](2024/2024-12.png) |
| 2025-01 | MNQH5 | 576.00 | LL+SL | 2 | -1152.00 | [2025/2025-01.png](2025/2025-01.png) |
| 2025-02 | MNQH5 | 754.50 | LL+SP | 2 | -724.25 | [2025/2025-02.png](2025/2025-02.png) |
| 2025-03 | MNQH5 | 1045.00 | SW | 1 | +1045.00 | [2025/2025-03.png](2025/2025-03.png) |
| 2025-04 | MNQM5 | 1454.00 | SW+SW | 2 | +2908.00 | [2025/2025-04.png](2025/2025-04.png) |
| 2025-06 | MNQM5 | 596.75 | LW | 1 | +596.75 | [2025/2025-06.png](2025/2025-06.png) |
| 2025-07 | MNQU5 | 516.50 | LW | 1 | +516.50 | [2025/2025-07.png](2025/2025-07.png) |
| 2025-08 | MNQU5 | 575.00 | LW+LP | 2 | +749.75 | [2025/2025-08.png](2025/2025-08.png) |
| 2025-09 | MNQU5 | 530.25 | LW | 1 | +530.25 | [2025/2025-09.png](2025/2025-09.png) |
| 2025-10 | MNQZ5 | 563.25 | LL+SL | 2 | -1126.50 | [2025/2025-10.png](2025/2025-10.png) |
| 2025-11 | MNQZ5 | 764.00 | SW+SW | 2 | +1528.00 | [2025/2025-11.png](2025/2025-11.png) |
| 2025-12 | MNQZ5 | 492.25 | LL+SL | 2 | -984.50 | [2025/2025-12.png](2025/2025-12.png) |
| 2026-01 | MNQH6 | 538.25 | LL+SL | 2 | -1076.50 | [2026/2026-01.png](2026/2026-01.png) |
| 2026-02 | MNQH6 | 847.50 | SW+SW | 2 | +1695.00 | [2026/2026-02.png](2026/2026-02.png) |
| 2026-03 | MNQH6 | 749.25 | LL+SP | 2 | -613.00 | [2026/2026-03.png](2026/2026-03.png) |
