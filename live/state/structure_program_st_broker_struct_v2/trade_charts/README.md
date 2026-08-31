# Structure-only resting — trade charts

Sampled **200** of 493 campaigns (seed=42): **57** winners · **143** losers.

- [`winners/`](winners/) — 57 charts
- [`losers/`](losers/) — 143 charts
- [`charted_trades.csv`](charted_trades.csv)

Each chart: **1m candles**, **OR high/low/mid**, **1m ST trailing stop**, **structure bull LL / bear HH** (latest + recent), **original entry level** (filled limit = structure key), fill if slipped, risk stop ±8, scale +22/+50/+200.
