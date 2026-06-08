# MNQ **v2e daily** — prior-month sweep on **daily** bars

Structural sibling of **v2e** (`scripts/backtest_london_sweep_breaker.py`), using:

| Intraday v2e | Daily variant |
|--------------|----------------|
| London **[02:00, 09:30)** low / high | **Prior calendar month** low (long) / high (short), stepped like ``potions/mnq/scripts/plot_daily_prior_month_levels.py`` |
| Session = one **RTH day** | Session = one **calendar month** |
| 1 m bars + 5 m breaker swings | **Daily** bars + strict **daily** swing highs/lows |
| Flat same **day** by **15:59** / TP / SL | Flat by **last trading day of the fill month** / TP / SL on **daily** ranges |

## Bullish (long)

- **Sweep:** first daily in the **current** month with ``low <= prior_month_low``.
- **Ordering:** some daily in the **prior** month must tag that same ``prior_month_low`` **before** that sweep (by row index).
- **Stop hunter / piercer / breaker / TP:** same fixed-point story as v2e, on **daily** indices.
- **Entry:** limit buy at **breaker_high** when ``low <= breaker_high`` on a **later** daily after piercer.

Script: ``scripts/backtest_prior_month_sweep_daily_long.py``

Stops (``--sl-at``): ``prior_month_low``, ``breaker_low``, ``stop_hunter_low``.

## Bearish (short)

Mirror using **prior_month_high**, breaker swing **lows**, limit **sell** at ``breaker_low``.

Script: ``bearish/scripts/backtest_prior_month_sweep_daily_short.py``

Stops: ``prior_month_high``, ``breaker_high``, ``stop_hunter_high``.

## Data

Default input: ``mnq/raw/glbx-mdp3-20100606-20260426.ohlcv-1d.dbn.zst`` (**Databento daily**, front contract per day — same as the daily/monthly chart script). Override with ``--daily-dbn``.

Requires Python package **databento**.

```bash
cd potions/mnq/v2e/daily/scripts
python3 backtest_prior_month_sweep_daily_long.py --all-sl

cd ../bearish/scripts
python3 backtest_prior_month_sweep_daily_short.py --all-sl
```

## Research charts

Script: ``scripts/build_daily_research_charts.py`` writes ``charts/research/``:

- Cumulative equity (long / short, **stop hunter** SL).
- Stratified sample of **winner** and **loser** months (**daily OHLC candlesticks**: teal bodies up, red down — prior month + session month, levels, SH / piercer / fill markers).

By default **clears** existing PNGs in that folder; use ``--no-clean`` to keep them. Options: ``--max-per-side``, ``--seed``, ``--start`` / ``--end``, ``--out``.

```bash
cd potions/mnq/v2e/daily/scripts
python3 build_daily_research_charts.py
```

## Caveats (same family as v2e)

Setup is resolved with knowledge of the **full month’s** daily path for labeling (see **Causality** in ``../README.md``). Post-fill uses **pessimistic** stop-before-TP when both touch one daily bar.

Shared helpers: ``scripts/prior_month_sweep_daily_common.py``.
