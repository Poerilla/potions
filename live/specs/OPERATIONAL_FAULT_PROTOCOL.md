# Operational Fault Protocol

Status: first implementation scaffold added through `live/supervisor.py` and Tradovate adapter hooks. This protocol applies to all strategies, not only v2b.

## Runtime Principle

The strategy engine is not allowed to treat local state as truth when the broker disagrees. The broker ledger is authoritative for orders, fills, positions, and account state. Local CSV/JSON files are an audit mirror and restart aid.

Runtime modes:

- `running`
- `entry_frozen`
- `reconciling`
- `emergency_flatten`
- `blocked`

New entries are allowed only in `running`. Reduce-only exits, protective broker-side exits, reconciliation, and emergency flattening remain allowed outside `running`.

## Persisted State

The supervisor writes:

- `runtime_status.json`
- `events/runtime_faults.jsonl`
- `events/reconciliation_events.jsonl`

Provider adapters may also write:

- provider session events,
- provider order events,
- market-data status,
- feed/broker bar audits.

## Default Thresholds

- Entry freeze threshold: **1000 ms** missing required provider/feed/broker heartbeat.
- Order ambiguity threshold: **4000 ms** unresolved order-placement ambiguity.
- Tradovate WebSocket protocol heartbeat: send `[]` according to the spec's roughly **2.5 second** heartbeat cadence.

The protocol heartbeat keeps the socket alive. The runtime thresholds decide whether strategies may arm new entries.

## Failure Matrix

| Event | Detection | Automated Response |
| --- | --- | --- |
| WebSocket/feed loss | missing heartbeat or stale feed | Freeze new entries, reconnect with backoff, reconcile before resume |
| In-flight order ambiguity | HTTP 5xx, socket drop, or no ack during order placement | Freeze secondary orders, query broker order state, block if unresolved after threshold |
| Local vs broker divergence | position/order mismatch | Halt trading loops, archive local state, query broker ledger, overwrite local mirror |
| Manual kill switch | operator command | Cancel working orders, liquidate open positions, remain in `emergency_flatten` until reset |

## Tradovate-Specific Notes

Tradovate is first adapter priority. The adapter must prove:

- `user/syncrequest` before order routing,
- `placeoso`/`placeoco` protective behavior in demo,
- restart reconciliation during RTH,
- `liquidateposition`/`liquidatepositions` emergency behavior,
- no duplicate entries after reconnect.

Live entries are blocked until those checks pass.

## CTA / Investor Reporting Read

This protocol is part of the operational risk story. It should be summarized in investor materials as:

- isolated API adapter,
- broker ledger as ground truth,
- server-side protective orders required before live,
- freeze/reconnect/reconcile/resume lifecycle,
- independent manual kill switch.
