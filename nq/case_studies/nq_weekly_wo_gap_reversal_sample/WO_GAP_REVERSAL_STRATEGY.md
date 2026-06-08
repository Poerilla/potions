# WO Gap Reversal — strategy master doc

This document ties together how the **weekly-open (WO) gap reversal** idea was found on NQ, how the rules were refined, and where every artifact lives — including the causal **StrategyPlugin** broker-like replay across six futures markets.

**Tracker placement:** ranks **27–35** in [`mnq/case_studies/STRATEGY_TRACKER.md`](../../../mnq/case_studies/STRATEGY_TRACKER.md) (Broker-Like Bar Replay Rankings + WO Gap subsection).

---

## Strategy summary (baseline)

**Timeframe:** 1-hour bars, **W-SUN** week (Sunday–Friday; Saturday omitted; Friday clipped after 16:00 NY).

**Anchor:** **WO** = current week’s open (first 1h bar of the week).

| Stage | Rule |
|--------|------|
| **Pre-gap** | ≥1 prior 1h bar with full body (O+C) on the exit side of WO (long: below WO; short: above WO). Wicks may touch WO. |
| **Gap candle** | Crosses WO with **≥55%** of open–close range on the exit side (long: open &lt; WO &lt; close; short: mirror). |
| **Entry** | Limit **@ WO** from the **next** bar only (not on the gap bar). |
| **Fill window** | 6 bars after gap; else no trade. |
| **Post-gap filter** | Skip if a 3-bar swing forms before WO retest, unless the gap bar is part of that swing. |
| **Exit** | **2 contracts** — +50 pts on leg 1, runner ±300 pts, initial stop ∓50 on both; move runner stop to **breakeven @ WO** after +50. |
| **Week caps** | Max **2** trades/week; no new trades after +50 / full target win; one gap signal per direction per week. |

**Implementation (live):** [`live/strategies/wo_gap_reversal.py`](../../../live/strategies/wo_gap_reversal.py) · **Replay driver:** [`live/wo_gap_reversal_broker_like.py`](../../../live/wo_gap_reversal_broker_like.py)

```bash
python3 -m live.wo_gap_reversal_broker_like \
  --market nq --market mnq --market es --market ym --market mes --market mym
```

---

## How we found it

### 1. Weekly 1h context charts

We started from **Sun–Fri 1h candles** with **prior-week levels** (PWH, PWL, PWC, PWO, PW 50%) and **current-week open (WO)** plus optional ATR bands. That framing made WO the natural “magnet” for the new week.

- **Level study builder:** `nq/case_studies/build_nq_weekly_1h_level_study.py`
- **PWC-focused charts:** [`nq_weekly_1h_pwc_levels/INDEX.md`](../nq_weekly_1h_pwc_levels/INDEX.md)
- **RTH shading reference (no trades):** [`nq_weekly_1h_rth_random_100/INDEX.md`](../nq_weekly_1h_rth_random_100/INDEX.md)

### 2. WO gap reversal hypothesis

On many weeks, price **gaps through WO** on a strong 1h candle after trading on one side, then **retests WO** — a classic fade-the-breakout / reclaim-level setup. We codified:

- A **minimum body share** (55%) through WO on the gap bar
- A **limit at WO** (not market on the gap bar)
- A **short fill window** and **swing filter** so we don’t chase retests after structure already shifted

### 3. Chart sample (NQ, 2023+)

**121 weeks** with at least one qualifying setup, annotated long/short gaps, fills, scale-out levels, and causal **Heikin Ashi pin** outlines.

- **Charts + rules:** [`INDEX.md`](INDEX.md) (this folder)
- **Builder:** `nq/case_studies/build_nq_wo_gap_reversal_sample.py`

### 4. HA pin weeks (parallel research)

To see pin bars in the same weekly layout, we charted **all weeks with ≥1 causal HA pin** (270 weeks) with levels, RTH bands, and later **15m Supertrend** overlay.

- [`nq_weekly_1h_ha_pin_weeks/INDEX.md`](../nq_weekly_1h_ha_pin_weeks/INDEX.md)

---

## Refinement work (research backtests)

All used the same entry logic unless noted; exit = **2ct +50 / runner 300**, SL **50 pts**, full history from **2010-06-06** unless the study says 2023+.

### Scale-out vs single target

Compared 1ct full target, 2ct +50/runner 300, 2ct +50/runner 600, and 3ct ladders.

| Doc | What it answers |
|-----|-----------------|
| [`SCALEOUT_COMPARISON.md`](SCALEOUT_COMPARISON.md) | 2023+ scale-out modes (short-only vs both sides) |
| [`SCALEOUT_FULL_HISTORY.md`](SCALEOUT_FULL_HISTORY.md) | Full-history best variants (~+7,862 pts both sides, 2ct +50/300) |

**Takeaway:** **2ct +50 / runner 300** is the chart-study default; runner 600 helps short-only 2023+ but not clearly on full-history both sides.

### Rule variants (five separate tests)

| # | Change | Both-sides result (vs baseline) |
|---|--------|----------------------------------|
| 1 | Remove swing filter | **No change** (filter never blocked a fill) |
| 2a/2b | 45% / 50% gap candle | +15 trades, **−43 pts** net |
| 3 | 3 trades/week | **No change** (cap never binding) |
| 4 | Unlimited trades | +46 trades, **−2,854 pts** (stop-after-win matters) |
| 5 | RTH-only entries | −212 trades, **−4,667 pts** |

Full tables: [`VARIANT_COMPARISON.md`](VARIANT_COMPARISON.md) · Script: `nq/case_studies/backtest_nq_wo_gap_variants.py`

---

## Broker-like replay (StrategyPlugin)

Causal replay through **Engine + PaperBroker** (1-tick slippage, $1.50/unit fee, stop-first same-bar, orders live only after bar close). This is **stricter** than the research simulator and is the hardening step before live use.

**Output:** [`live/state/wo_gap_reversal_broker_like/INDEX.md`](../../../live/state/wo_gap_reversal_broker_like/INDEX.md)

| Market | Trades | Net USD | PF | Notes |
|--------|-------:|--------:|-----|--------|
| NQ | 486 | +$80,472 | 1.20 | Largest $ PnL (×$20/pt) |
| ES | 451 | +$120,647 | 1.19 | Strongest trade count / $ |
| MNQ | 171 | +$5,932 | 1.43 | Best PF among equity index minis |
| MES | 123 | +$7,395 | 1.35 | Fewer bars (MES CSV history) |
| YM | 513 | +$9,651 | 1.09 | Positive but weak Net/Stress |
| MYM | 238 | −$1,146 | 0.93 | Only market net negative |

Per-market audits: `live/state/wo_gap_reversal_broker_like/audits/{market}_wo_gap_reversal/reports/MTM_AUDIT.md`

**Why broker PnL ≠ research points:** Research sums **index points** per week in isolation; broker replay uses **fills, fees, slippage**, full calendar, and **week-roll flatten** if still in a position. Treat research CSVs as rule discovery and broker INDEX as execution realism.

---

## File map

| Artifact | Path |
|----------|------|
| Master doc (this file) | `nq/case_studies/nq_weekly_wo_gap_reversal_sample/WO_GAP_REVERSAL_STRATEGY.md` |
| NQ chart study INDEX | [`INDEX.md`](INDEX.md) |
| Variant comparison | [`VARIANT_COMPARISON.md`](VARIANT_COMPARISON.md) |
| Scale-out 2023+ | [`SCALEOUT_COMPARISON.md`](SCALEOUT_COMPARISON.md) |
| Scale-out full history | [`SCALEOUT_FULL_HISTORY.md`](SCALEOUT_FULL_HISTORY.md) |
| HA pin weeks | [`../nq_weekly_1h_ha_pin_weeks/INDEX.md`](../nq_weekly_1h_ha_pin_weeks/INDEX.md) |
| RTH random 100 | [`../nq_weekly_1h_rth_random_100/INDEX.md`](../nq_weekly_1h_rth_random_100/INDEX.md) |
| PWC levels | [`../nq_weekly_1h_pwc_levels/INDEX.md`](../nq_weekly_1h_pwc_levels/INDEX.md) |
| Broker-like cross-market | [`../../../live/state/wo_gap_reversal_broker_like/INDEX.md`](../../../live/state/wo_gap_reversal_broker_like/INDEX.md) |
| Strategy plugin | [`../../../live/strategies/wo_gap_reversal.py`](../../../live/strategies/wo_gap_reversal.py) |
| Replay driver | [`../../../live/wo_gap_reversal_broker_like.py`](../../../live/wo_gap_reversal_broker_like.py) |
| Research backtest (variants) | `nq/case_studies/backtest_nq_wo_gap_variants.py` |
| Research backtest (scale-out) | `nq/case_studies/backtest_nq_wo_gap_scaleout.py` |
| Chart builder | `nq/case_studies/build_nq_wo_gap_reversal_sample.py` |

---

## Suggested reading order

1. [`INDEX.md`](INDEX.md) — visual rules + 2023+ sample weeks  
2. [`SCALEOUT_FULL_HISTORY.md`](SCALEOUT_FULL_HISTORY.md) — exit choice  
3. [`VARIANT_COMPARISON.md`](VARIANT_COMPARISON.md) — what *not* to loosen  
4. [`live/state/wo_gap_reversal_broker_like/INDEX.md`](../../../live/state/wo_gap_reversal_broker_like/INDEX.md) — cross-market causal replay  

---

## Open questions

- **MYM / YM:** Broker replay is weak or negative on dow minis — worth separate point-value / volatility scaling or side filter before production.
- **Swing filter:** Research showed zero marginal trades removed; kept in plugin for parity with charts.
- **RTH-only entries:** Large research drag; not enabled in plugin default.
- **HA pins:** Documented on charts but **not** an entry filter in baseline or plugin.
