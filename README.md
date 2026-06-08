# Potions — Futures ORB Strategy Research

Opening Range Breakout research and execution models for CME micro index
futures (MNQ, MYM, MES, and related).

## Current canonical model: **v2 — pre-placed OCO stop entry**

At 9:45 ET (end of the 15-min opening range), place two resting stop
orders at the exchange:
- BUY STOP at `Range_High + 1 tick`
- SELL STOP at `Range_Low - 1 tick`

First one to trigger fills, the other auto-cancels (OCO). Attach bracket
exit: target = `Entry ± Range`, stop = opposite range boundary. Re-arm
after each trade closes (max 2 trades/day). Force-close at 15:55 ET.

See `scripts/validation.md` for the full rules, v1 → v2 migration
context, performance tables, and live-execution notes.

## Current research leader: **adaptive 50/150 v2b-only scaleout**

The current best execution-test candidate from the MNQ research track is
the **v2b-only adaptive scaleout**:

- Use prior-day **MA50 > MA150** as a causal gate.
- When true, trade the v2b breakout only; when false, skip the day.
- Trade **2 contracts**: one exits at TP1, one runner targets TP2 with
  stop moved to entry after TP1.
- No v2d fade arm and no child scale-ins.

Latest MNQ strict re-sim: **1,430 legs**, **$35,847.00 net**,
**-$5,190.00 max DD**, **55.03% win rate**, **1.19 PF**.
Longer NQ confirmation over 2010-2026: **4,739 legs**,
**$414,773.00 net**, **-$100,010.00 max DD**, **51.89% win rate**,
**1.13 PF**.

Read next:

- MNQ rules and candidate note: `mnq/v2d/README_adaptive_50_150_scaleout.md`
- NQ long-sample confirmation: `nq/v2d/NQ_ADAPTIVE_50_150_V2B_SCALEOUT.md`
- TradingView / Tradovate paper script: `pine/orb_adaptive_50_150_v2b_scaleout.pine`
- Strategy comparison tracker: `mnq/case_studies/STRATEGY_TRACKER.md`

## Monthly ORB research (higher timeframe)

- **Baseline + range-close restricted** monthly ORB (Python + Pine harness): `mnq/case_studies/monthly_orb/MONTHLY_ORB_RESTRICTED.md`, script `scripts/monthly_orb_restricted.py`.
- **Monthly ORB + weekly ATR Supertrend runner** (2-lot scale sim: scalp + runner, long-only, weekly filter): `scripts/monthly_orb_st_runner.py` → `mnq/mnq_monthly_orb_st_runner.csv`, `nq/nq_monthly_orb_st_runner.csv`. See `mnq/case_studies/STRATEGY_TRACKER.md` for latest headline numbers.
- **Monthly swing Fib retracement charts** (61.8% default from swing high after bullish context, first daily touch as green vertical, weekly Supertrend + yearly OR levels, **one PNG per calendar year**): `python mnq/case_studies/monthly_orb/build_monthly_fib_retrace_charts.py` (MNQ default); use `--daily nq/nq_daily.csv --out-root nq/case_studies/monthly_orb/fib_retrace_yearly --title-tag NQ` for NQ. Output index: `mnq/case_studies/monthly_orb/fib_retrace_yearly/INDEX.md`.

## Folder layout

| Path | Contents |
|---|---|
| `scripts/` | v2 canonical backtest + utilities (`step2_preplaced_stops.py`, `to_excel.py`, `validation.md`) |
| `mnq/` | MNQ 1-min DBN, 5-min RTH bars, v1 + v2 results, xlsx |
| `mym/` | MYM 1-min DBN, v1 + v2 results, xlsx |
| `ym/` | YM daily CSV + case studies; **MNQ + VX daily panel** chart — see `ym/README.md` |
| `vx/` | VX (CBF) Databento drops + `vx_front_daily.csv`; export script for the MNQ/VX panel — see `ym/README.md` |
| `nq/` | NQ NY v2b / v2d / adaptive 50/150 |
| `es/` | ES NY v2b / v2d / adaptive (`es/raw/*.ohlcv-1m*.dbn.zst`, `es/v2d/`) |
| `mes/` | MES 1m + legacy v1-style CSVs |
| `combined_orb/` | v2 London + NY session backtests; v2d session fades; **adaptive 50/150** CSV builder |
| `mnq/v2d/` | v2d fades, adaptive MNQ NY merge, regime chart script |
| `mnq/v1_limit/` | **Research:** v1b limit ORB from 5m bars + adaptive v1b+v2d merge (not live-canonical) |
| `mnq/v2e/` | **Research:** v2b levels + **London limit** 5-lot sim, per-leg CSV, **London-sweep** charts; see `mnq/v2e/README.md` |
| `orb-portfolio/` | v2 Monte Carlo; **`--adaptive`** triad (MNQ NY + MNQ London + MYM NY) |
| `pine/` | TradingView — **`orb_adaptive_50_150.pine`** (canonical live) |
| `case_studies/` | v2b per-year charts; **`adaptive_by_year/`** for adaptive 50/150 (v2b+v2d); **`mnq/case_studies/monthly_orb/fib_retrace_yearly/`** monthly-swing Fib + weekly ST yearly PNGs |
| `volatility/` | Range-size vs outcome analysis |
| `archived/` | v1 scripts and results preserved for history |

## Quick start

```bash
# Run the v2 backtest end-to-end (1-min DBN → trade-by-trade results CSV)
python scripts/step2_preplaced_stops.py --product MNQ
python scripts/step2_preplaced_stops.py --product MNQ --open-range-minutes 5  # 5m ORB -> mnq/mnq_orb_results_stops_5m.csv
python scripts/step2_preplaced_stops.py --product MYM
python scripts/step2_preplaced_stops.py --product ES   # needs es/raw 1m DBN
python es/v2d/build_adaptive_es_50_150.py

# Render formatted Excel workbooks from the v2 CSVs
python scripts/to_excel.py           # both products
python scripts/to_excel.py --product MNQ
```

## CANONICAL LIVE STRATEGY: v2b/v2d adaptive 50/150 MA cross

> **2026-04-25**: discovered that the v2b "breakout" strategy can be
> meaningfully improved by switching to v2d ("fade the breakout") when
> the daily 50-day MA crosses below the 150-day MA. This regime indicator
> survives 16-year walk-forward on NQ and beats v2b alone in MNQ
> in-sample. See `mnq/v2d/` for the detailed analysis.

| | v2b alone | **v2b/v2d 50/150 adaptive** | Δ |
|---|---|---|---|
| MNQ trades (5 yr) | 1,991 | 1,919 | similar |
| Win rate | 54.0% | **54.1%** | identical |
| Net P/L | $15,877 | **$18,885** | **+19%** |
| Annual avg | $3,020 | **$3,690** | +22% |
| Max DD | $4,716 | **$3,542** | **−25%** |
| Calmar | 0.64 | **1.05** | +64% |

The Pine implementation is `pine/orb_adaptive_50_150.pine`.

**Multi-session adaptive (Python):** after `combined_orb/scripts/london_ny_orb_v2d_fade.py` and `build_adaptive_50_150_portfolio.py`, see `orb-portfolio/README.md` (~**+$20.5k** combined 1×1×1 vs raw v2b-only portfolio).

## v2b honest performance summary (1 contract, net of $1.50 RT fee)

> **2026-04-25 revision**: the previously-reported v2 numbers were
> inflated ~7× by a same-direction re-entry bug. Honest v2b numbers
> below show the strategy is only marginally profitable on MNQ NY
> and **net negative on the other three strategies**. See
> `scripts/validation.md` for the full v2a→v2b correction context.

| Strategy | History | Trades | Win% | Net $ | Annual | Max DD |
|---|---|---|---|---|---|---|
| **MNQ NY** | 2021-03 → 2026-04 | **1,991** | **54.0%** | **+$15,877** | **~$3.1k/yr** | **−$4,716** |
| MNQ London | 2021-03 → 2026-04 | 2,473 | 52% | −$1,738 | net loss | −$5,328 |
| MYM NY | 2019-05 → 2026-03 | 2,627 | 52.0% | −$1,620 | net loss | −$6,564 |
| MYM London | 2019-05 → 2026-03 | 3,265 | 53% | −$3,840 | net loss | −$4,381 |
| Portfolio: 1 of each | 2021-03 → 2026-04 | 10,364 | ~53% | +$8,683 | ~$1.7k/yr | −$8,536 |

**Under raw v2b-only**, only MNQ NY is net positive; the other three
sessions add trades but drag dollar P/L (`orb-portfolio/README.md`).
Under **adaptive 50/150** (same MNQ daily regime for each leg), MNQ
London + MYM NY flip to v2d in chop and the **combined triad** is
net-positive in backtest — still higher variance and more operational
complexity than MNQ NY alone.

## v1 status

- **Archived v1a** (`archived/`) used an unrealistic same-bar limit fill;
  do not use those numbers for sizing.
- **v1b** (honest next-bar limit) lives in `archived/v1_scripts/`; the
  active **retest** pipeline is `mnq/v1_limit/` (5m bars, `Net_$`, optional
  adaptive v1b+v2d). That path is for comparison only; **live canonical**
  remains v2b+v2d adaptive in Pine.

See `archived/README.md` for the detailed v1→v2 diff.
# vorlage
# potions
