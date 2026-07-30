# Trend–momentum StrategyPlugin

Reddit-style trend + momentum bar + pullback trail, implemented as a StrategyPlugin.

- Plugin: [`live/strategies/trend_momentum.py`](../../strategies/trend_momentum.py)
- TF study: [`live/trend_momentum_tf_study.py`](../../trend_momentum_tf_study.py) → [`../trend_momentum_tf_study/`](../trend_momentum_tf_study/)
- Sweep: [`live/trend_momentum_sweep.py`](../../trend_momentum_sweep.py) → [`../trend_momentum_sweep/`](../trend_momentum_sweep/)

## Locked assumptions (v1)

| # | Assumption | v1 default | Fine-tune later |
|---|---|---|---|
| A1 | Signal timeframe | Study `5m/15m/1h/4h/D`; sweep uses recommended intraday + `15m` | Drop losers |
| A2 | Trend | Last 2 confirmed swing highs/lows → HH+HL / LH+LL | SMA200 / ADX / HTF |
| A3 | Swing lookback | `2` bars each side | 3–5 |
| A4 | Momentum bar | Body ≥ `1.0 × ATR(14)`, with-trend color | Percentile / body÷range |
| A5 | Pullback gate | ≥2 opposite closes before momentum | Retrace % ATR |
| A6 | Entry | Stop 1 tick beyond mom bar; `live_after_ts=bar.ts` | Market / limit retest |
| A7 | Initial stop | Mid bar; if range &lt; `0.5×ATR`, far side of bar | Always beyond bar |
| A8 | Trail | Tighten only to completed pullback extreme after resume | ATR / BE after 1R |
| A9 | Trend-end | Default `trend_end_mode=opposite` (not `none` — too chatty) | `opposite_or_none` |
| A10 | Sizing | Fixed `entry_qty=1` | `risk_pct=0.01` |
| A11 | Max positions | 1; cancel entry if trend invalid | Scaleout |
| A12 | Sessions | FX/metals all bars; index/CME intraday **RTH** | FX session filters |
| A13 | Economics | 1-tick slip, $1.50/unit; JPY ÷110 | Per-instrument fees |
| A14 | Universe | FX, metals, US30, NAS100, NQ, YM, MNQ, MYM | ES/MES/SPX500 when 1m exists |
| A15 | SMA helpers | Off (`require_above_sma200`, `momentum_near_sma10`) | Phase-2 grid |

## Commands

```bash
export PYTHONPATH=/home/tester/hsm
python3 -m potions.live.trend_momentum_tf_study
python3 -m potions.live.trend_momentum_sweep
python3 -m pytest potions/live/tests/test_trend_momentum.py -q
```

## Results

### TF study (ranked by N/S)

See [`../trend_momentum_tf_study/SUMMARY.md`](../trend_momentum_tf_study/SUMMARY.md).

**Recommended intraday TF:** `1h` (mean N/S across USDJPY / XAUUSD / US30 / NQ among `{5m,15m,1h}`).

Notes from the study:
- Fast intraday (`5m`/`15m`) was broadly negative on FX/metals under v1 knobs.
- HTF diagnostics: **NQ 4h** and **XAUUSD D** led absolute N/S (few trades).
- **US30 5m** was the only strong positive among primary intraday cells.

Intraday `5m`/`15m` windows use **2018-01-01+** for runtime; `1h`/`4h`/`D` use full history.

### Sweep

Recommended TF (`1h`) + `15m` across A14 universe: [`../trend_momentum_sweep/SUMMARY.md`](../trend_momentum_sweep/SUMMARY.md).

**1h leaders (N/S > 0):** NAS100 0.62 · MNQ 0.26 · NQ 0.21 · XAUUSD 0.19 · US30 0.13.

**15m:** broadly negative under v1 knobs (best among losers: USDJPY −0.36).

v1 edge looks concentrated in **index/CME 1h** sleeves; FX majors need knob work (momentum ATR mult, pullback depth, SMA filters).
