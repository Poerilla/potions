# Monthly ORB Restricted

Restricted rule: after a monthly ORB breakout position is open, close it at the daily close if that close returns inside the monthly opening range. Max 2 trades per month and all other monthly ORB mechanics stay the same.

| Instrument | Variant | Periods | Trades | Range-close exits | Net pts | Net $ | Max DD pts | Max DD $ | Win rate | PF | Avg/trade pts |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | baseline | 83 | 128 | 0 | 15,751.25 | $31,502.50 | -2,722.25 | $-5,444.50 | 66.41% | 1.80 | 123.06 |
| MNQ | restricted | 83 | 141 | 66 | 22,019.50 | $44,039.00 | -1,197.00 | $-2,394.00 | 50.35% | 3.58 | 156.17 |
| NQ | baseline | 190 | 305 | 0 | 22,315.00 | $446,300.00 | -2,718.00 | $-54,360.00 | 67.54% | 1.95 | 73.16 |
| NQ | restricted | 190 | 325 | 150 | 27,897.00 | $557,940.00 | -1,197.75 | $-23,955.00 | 50.46% | 3.56 | 85.84 |

## Effect Versus Baseline

| Instrument | Trade change | Net change pts | Net change $ | Max DD reduction pts | Max DD reduction $ | Win-rate change | PF change |
|---|---:|---:|---:|---:|---:|---:|---:|
| MNQ | +13 | +6,268.25 | $12,536.50 | +1,525.25 | $3,050.50 | -16.05% | +1.78 |
| NQ | +20 | +5,582.00 | $111,640.00 | +1,520.25 | $30,405.00 | -17.08% | +1.61 |

## Restricted scaleout3 (3-unit ladder)

**Simulator:** [`scripts/monthly_orb_restricted_scaleout3.py`](../../../scripts/monthly_orb_restricted_scaleout3.py) — same entry / range-close / flip rules as single-leg restricted, with **3 units** at the boundary: **U1** off at **25%** to the 1R TP, **U2** at full TP, **U3** runner; **opposite-range** initial stop; **breakeven** after U2 TP; daily bar ordering matches `yearly_orb_swing_stop_scaleout3` (stop before partials, then range-close).

**Outputs:** `mnq/mnq_monthly_orb_restricted_scaleout3.csv`, `nq/nq_monthly_orb_restricted_scaleout3.csv` (regenerate with `--also-nq` on MNQ run, or rerun the script for NQ paths).

### PnL, MAE, closed DD, stress (MTM) DD — vs single-leg restricted

**Stress DD** is the open-heat proxy from `yearly_orb_equity_scaling.base_stats`: each calendar day take cumulative **realized** PnL from exits so far, minus the sum of **MAE stress** for every bundle still open that day (`MAE_Position_Pts` × $/pt for scaleout3; **path** adverse excursion from daily highs/lows × $/pt × 1 contract for single-leg). Detail and regeneration: [`METRICS_SCALEOUT3.md`](METRICS_SCALEOUT3.md).

| Metric | MNQ single-leg | MNQ scaleout3 | NQ single-leg | NQ scaleout3 |
|---|---:|---:|---:|---:|
| Trades / bundles | 141 | 139 | 325 | 313 |
| Net pts | 22,019.50 | 52,577.00 | 27,897.00 | 66,154.62 |
| Net USD | $44,039.00 | $105,154.00 | $557,940.00 | $1,323,092.50 |
| Max MAE price (pts) — path (leg) / sim (so3) | 1,039.25 | 1,039.25 | 1,038.00 | 1,038.00 |
| Avg MAE price (pts) — path / sim | 194.88 | 137.04 | 109.37 | 75.66 |
| Worst bundle MAE stress (USD) | $2,078.50 | $4,157.00 | $20,760.00 | $41,520.00 |
| Avg bundle MAE stress (USD) | $389.76 | $625.14 | $2,187.37 | $3,445.77 |
| Max DD — **closed** realized (USD) | $-2,394.00 | $-3,722.75 | $-23,955.00 | $-37,277.50 |
| Max DD — **stress / MTM** proxy (USD) | $-4,713.50 | $-6,410.00 | $-47,120.00 | $-64,050.00 |

**Read:** Scaleout3 lifts **gross index pts** (sum of three unit legs per bundle) but increases **closed** and **stress** drawdowns versus 1-lot restricted. Bundle count can differ slightly from single-leg trade count (edge-of-month / open bundle handling). Dollar columns use **$2/pt** (MNQ) and **$20/pt** (NQ) on the **bundle point sum** — fees/slippage not modeled.

### Charts (restricted scaleout3)

Per-month annotated dailies (same layout family as baseline+restricted): **`baseline_restricted_scaleout3/`** — [`baseline_restricted_scaleout3/INDEX.md`](baseline_restricted_scaleout3/INDEX.md). NQ mirror: [`nq/case_studies/monthly_orb/baseline_restricted_scaleout3/INDEX.md`](../../../nq/case_studies/monthly_orb/baseline_restricted_scaleout3/INDEX.md).

Regenerate:

```bash
python3 mnq/case_studies/monthly_orb/build_baseline_restricted_scaleout3_charts.py
python3 mnq/case_studies/monthly_orb/build_baseline_restricted_scaleout3_charts.py --nq
```

## Charts (baseline + restricted)

Per-period annotated daily charts live under **`baseline_restricted/`** (see [`baseline_restricted/INDEX.md`](baseline_restricted/INDEX.md)). Regenerate with [`build_baseline_restricted_charts.py`](build_baseline_restricted_charts.py); marks are taken from `mnq_monthly_orb_restricted.csv` (not re-simulated on the chart pass).

**Related:** monthly swing **Fib retracement** study (61.8% default, weekly Supertrend + yearly OR, yearly PNGs) — [`fib_retrace_yearly/INDEX.md`](fib_retrace_yearly/INDEX.md), builder [`build_monthly_fib_retrace_charts.py`](build_monthly_fib_retrace_charts.py). Monthly ORB + weekly ST **runner** sim: `scripts/monthly_orb_st_runner.py` (see `STRATEGY_TRACKER.md`).

### TradingView Pine (paper / visual harness)

- Strategy script: [`pine/monthly_orb_restricted.pine`](../../../pine/monthly_orb_restricted.pine) — use a **daily** chart matching your research series. **Sizing** is the **Contracts per entry** input (1–500). This is a causal FSM mirror of the Python rules, not a guaranteed fill-for-fill match to the CSV (see header comments in the script).

## Rough stack rank vs top ATR DCA (`STRATEGY_TRACKER.md`)

`mnq/case_studies/STRATEGY_TRACKER.md` lists **MNQ ATR Supertrend DCA** ideas scaled up to **10 contracts** with MTM drawdown. This monthly-ORB variant is **1 MNQ**, far fewer trades, and a different execution tax model.

| Idea | MNQ headline (this sheet vs tracker) |
|---|---|
| Monthly ORB baseline + restricted | **~$44k** net · **about −$2.4k** max equity DD · high PF · **single-lot**, monthly cadence |
| ATR weekly-primary DCA · 10 max · 3 initial · entry guard | **~$303k** net · **about −$16.5k** MTM DD (see tracker; **may need causal rerun** after weekly ATR mapper fix) |
| ATR daily-primary DCA · 10 max · 3 initial · entry guard | **~$235k** net · **about −$15.6k** MTM DD |

**Read:** ATR DCA wins on **absolute dollars** when pyramiding is allowed. Restricted monthly ORB is a **smaller, low-touch** sleeve with much lower nominal heat and far less total expectancy.

## Output CSVs

- MNQ restricted (single-leg): `/home/tester/hsm/potions/mnq/mnq_monthly_orb_restricted.csv`
- NQ restricted (single-leg): `/home/tester/hsm/potions/nq/nq_monthly_orb_restricted.csv`
- MNQ restricted **scaleout3**: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_restricted_scaleout3.csv`
- NQ restricted **scaleout3**: `/home/tester/hsm/potions/nq/nq_monthly_orb_restricted_scaleout3.csv`
