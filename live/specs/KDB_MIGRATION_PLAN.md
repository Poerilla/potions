# KDB+ Migration Plan

Purpose: document how to migrate replay and live market-data storage from the
current flat-file system to KDB+ without changing strategy semantics or making
KDB a pre-paper-trading dependency.

Current rule: flat files remain authoritative until KDB parity is proven.

## Why KDB+

KDB+ is valuable for this platform mainly because of:

- fast time-series scans across ticks, bars, orders, fills, and events
- natural as-of joins for point-in-time feature construction
- compact storage for high-frequency futures data
- live write/read patterns that match streaming market data

The migration is not intended to improve alpha. It is intended to improve
replay speed, point-in-time query discipline, and long-term auditability.

## Phase 0 - Flat Files With Institutional Discipline

Keep the current `FlatFileStore` as the execution and audit source of truth.

Required before KDB:

- `run_manifest.json` and `run_manifest.sha256` for major replays
- explicit table schemas for bars, events, orders, fills, feature snapshots,
  causality violations, promotion status, and execution scrutiny
- instrument/session/roll master
- flat-file as-of helper using:

```text
latest row where available_at_ts <= current_bar.ts
```

This phase makes the later KDB migration a backend change, not a semantic
change.

## Phase 1 - Write-Through KDB Mirror

Add a KDB write-through mirror while the engine still reads flat files.

Mirror tables:

- raw provider events / ticks
- completed 1m bars
- derived 5m bars
- contract references
- feed status
- strategy order intents
- broker orders
- fills
- positions
- run manifests
- feature snapshots
- causality violations

Rules:

- KDB writes are best-effort in this phase.
- Flat-file writes must not depend on KDB success.
- KDB mirror lag/failure is reported but does not alter trading/replay behavior.
- Raw events retain provider event time, provider receive time, and local ingest
  time.

## Phase 2 - Historical Data Store Interface

Introduce a provider-neutral historical read boundary:

```text
HistoricalDataStore
  - read_bars(instrument, timeframe, start, end)
  - read_events(stream, start, end)
  - asof_feature(feature_name, instrument, current_bar_ts)
  - read_contract_refs(instrument, start, end)
```

Implementations:

- `FlatFileHistoricalStore`: current behavior plus as-of semantics.
- `KdbHistoricalStore`: future implementation using KDB queries.

Both stores must return identical normalized `Bar` objects for the same query.

## Phase 3 - Live Feed Writes To KDB

Live market-data adapters write to both flat files and KDB:

- raw tick/event table
- normalized 1m bars
- derived 5m bars
- contract refs
- feed health/status
- feed gaps and adjustments

Broker adapters write:

- order intents
- submitted broker orders
- order events
- fills
- positions
- reconciliation events

KDB is still a mirror unless the parity tests in Phase 4 pass.

## Phase 4 - Replay Read Cutover

Replay may read from KDB only after parity is proven.

Required parity tests:

- same 1m bars as flat files for known RTH days
- same 5m bars derived from 1m bars
- same strategy order intents
- same fills
- same equity curves
- same summaries
- same execution scrutiny
- same promotion status
- same run manifest output hashes except expected backend metadata fields

Cutover rule:

```text
If KDB replay output differs from flat-file replay output, flat files remain
authoritative and the KDB path is blocked.
```

## As-Of Join Semantics

Every auxiliary feature lookup must use:

```text
feature.available_at_ts <= current_bar.ts
```

In flat files this is implemented by scanning for the latest prior row. In KDB
this maps to an as-of join. The semantics must be identical.

Invalid query behavior:

- returning a row with `available_at_ts > current_bar.ts`
- joining on event timestamp when availability timestamp is later
- using revised data without recording the revision availability time

These conditions must be logged as causality violations.

## Suggested Table Shape

KDB table names should mirror existing concepts:

- `raw_events`
- `ticks`
- `bars`
- `contract_refs`
- `feed_status`
- `order_intents`
- `orders`
- `fills`
- `positions`
- `feature_snapshots`
- `causality_violations`
- `execution_scrutiny`
- `run_manifests`

Minimum common columns:

- `instrument`
- `broker_instrument` when available
- `timeframe` for bars
- `event_ts`
- `available_at_ts` where applicable
- `ingested_at`
- `source`
- `run_id`

## Python Bridge

Preferred future bridge: PyKX, if licensing is available.

Fallback bridge:

- append CSV/JSONL from Python
- periodic q process imports
- IPC export for replay windows

No KDB dependency should be required for pre-paper hardening tests.

## Rollback And Operations

- Flat files remain the fallback and audit mirror.
- KDB outages block KDB-backed research queries but do not block protective
  broker exits.
- Live entries may use KDB reads only after KDB is promoted from mirror to
  read-authoritative through parity.
- KDB schema/version changes require a manifest entry and replay parity rerun.

