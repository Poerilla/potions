# Databento Market Data Feed Spec

## Purpose

Use Databento as an independent direct market-data feed for live-paper strategy bars while routing orders through Tradovate or another broker.

Databento is attractive for this runtime because our research already uses Databento-derived OHLCV files, and its live API supports the same schemas, datasets, and symbology family as historical data.

## Required Dataset

For CME Globex futures:

```text
dataset = "GLBX.MDP3"
```

For NQ/MNQ/ES/MES/YM/MYM-style futures, the adapter must map one of:

- exact raw contract symbol
- parent symbol such as `NQ.FUT` / `MNQ.FUT` style parent subscriptions where supported
- instrument id
- a separately resolved active front-month contract

Live configs must route orders to exact broker-tradable contracts. Continuous symbols are not acceptable for live order routing.

## Access And Cost Requirements

As of 2026-05-22, live Databento access is not just an API key on a free historical account.

Required:

- Databento account.
- Databento API key.
- A qualifying live-data subscription plan: Standard, Plus, or Unlimited.
- Live data activation for `GLBX.MDP3`.
- Completion of Databento's subscriber/status questionnaire.
- CME/venue licensing approval where required.

Current public pricing signals:

- Databento announced a CME Globex Standard plan at `$179/month` in April 2025.
- Databento states that usage-based live CME data is discontinued for new/non-grandfathered users; historical usage-based pricing remains.
- Databento portal docs state that a Standard, Plus, or Unlimited subscription is required for live data.
- Databento portal docs list CME personal access as included with the Standard plan up to 2 devices, but commercial or non-display classifications can create separate venue license fees.
- CME licensing can be much higher for non-display/automated use than simple display use. Databento's portal questionnaire is the source of truth for the account's exact classification.

Practical budgeting assumption for this runtime:

- If Databento classifies this as eligible personal/internal use: expect at least the Databento live subscription cost.
- If Databento/CME classifies the bot as non-display or commercial algorithmic use: expect additional monthly CME licensing fees, potentially hundreds of dollars per month depending on use category and exchange coverage.
- If we only need historical research data, this live subscription is not required; historical data can remain usage-based.

Before implementation, verify in the Databento portal:

- Whether `GLBX.MDP3` live is active.
- Whether the intended bot use is personal, commercial, display, or non-display.
- Whether CME fees are included in the chosen plan or passed through separately.
- Whether parent-symbol subscriptions such as `NQ.FUT` / `MNQ.FUT` are permitted on the selected plan.
- Whether `trades`, `ohlcv-1m`, and any desired depth schemas are available live on the plan.

## Required Schemas

Preferred first implementation:

- `trades` for local bar building

Possible later schemas:

- `ohlcv-1m` if available and licensed for live use
- `mbo` or `mbp-1` for depth/DOM-based filters
- `definition` for instrument mapping and contract metadata

Source notes:

- Databento Live supports the same schemas, datasets, and symbology as historical where available.
- Databento Python `Live` client uses API-key authentication and DBN records.
- The live API supports intraday replay from a specified start time, generally within the last 24 hours.

## Python Client Shape

Baseline:

```python
import databento as db

client = db.Live(key="$DATABENTO_API_KEY")
client.subscribe(
    dataset="GLBX.MDP3",
    schema="trades",
    stype_in="parent",
    symbols="NQ.FUT",
)

async for record in client:
    handle_record(record)
```

The production adapter should prefer async iteration or callbacks that do minimal work and hand records to an internal queue.

## Required Capabilities

The Databento adapter must support:

- API key loading from environment or config secret path.
- Live subscription for exact contract or parent symbol.
- Optional intraday replay start for reconnect/backfill.
- Reconnect callback or equivalent gap tracking.
- Symbol mapping from Databento record/instrument id to internal instrument.
- Raw DBN or JSONL archival.
- Trade-to-bar aggregation.
- Feed stale detection.
- Sequence/gap logging where available.

## Bar Builder Requirements

For v2b:

- Build 1m bars from trade records.
- Derive 5m bars from local 1m bars.
- Use RTH 09:30-16:00 New York session boundaries.
- Emit no partial bars.
- Keep `ts_event` as the exchange/event timestamp and `ts_recv` as provider receive timestamp.

For 4h/monthly overlap:

- Build 4h bars from 1m bars or a separately validated OHLCV stream.
- Define exact 4h anchor times in New York time and keep them stable.

For daily/yearly/monthly ORB:

- Prefer daily bars derived from the same intraday source if feasible.
- If using provider daily bars, compare them to locally aggregated bars and research daily CSVs.

## Backfill Strategy

On startup:

- Request replay from the last persisted event/bar timestamp if supported.
- If replay cannot cover the full gap, block new entries until manual approval or alternate backfill.
- Write gap metadata to `market_data_status.json` and `market_data_gaps.csv`.

On reconnect:

- Resume from last good event timestamp if supported.
- Rebuild any affected in-progress bars.
- Mark adjusted bars in `market_data_adjustments.jsonl`.

## Feed/Broker Mismatch Controls

Because Databento is not the broker feed:

- Store Databento contract, internal instrument, and broker contract on every normalized bar.
- Do not send live orders if broker contract mapping is missing or stale.
- Compare Databento 1m/5m high/low to broker/Tradovate chart high/low in daily reports when both are available.
- If Databento says breakout but Tradovate broker chart disagrees during paper validation, record the mismatch and keep the trade tagged as feed-driven.
- Broker fills, positions, and order statuses always override local assumptions.

## Acceptance Checklist

- Streams one exact MNQ or NQ contract in paper mode for a full RTH session.
- Writes raw records and completed 1m bars.
- Derives 5m bars and matches existing replay on a known historical day when using Databento historical/replay input.
- Produces feed status and stale alerts.
- Handles reconnect with replay or blocks entries on unrecoverable gaps.
- Produces a feed-vs-research daily bar audit.
- Produces a feed-vs-broker bar audit when Tradovate feed/chart is also enabled.

## Other Direct Feeds

Any future direct feed must implement the same `MarketDataAdapter` contract and pass the same acceptance tests.

Minimum required provider features:

- exact futures contract subscription
- event timestamps
- trade price and size
- historical or replay backfill for reconnect gaps
- stable entitlement/licensing for automated non-display use
- raw event persistence
- documented session/calendar behavior

Optional useful features:

- official 1m OHLCV bars
- depth of market
- sequence numbers
- instrument definition stream
- heartbeat/system messages
- latency metadata

## References

- `https://databento.com/docs/api-reference-live/client/subscribe`
- `https://databento.com/docs/quickstart`
- `https://databento.com/docs/knowledge-base/new-users/market-data-schemas`
