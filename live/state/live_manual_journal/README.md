# Live Manual Trading Journal

Structured fill export for parity audits against headless DBN replay.

## Purpose

When you manually trade V2B-style setups on Tradovate demo/paper, export fills here so
`potions.live.execution_parity_audit` can compare live execution to simulated replay.

## File layout

| File | Role |
|---|---|
| `fills.csv` | One row per exchange fill (primary audit input) |
| `sessions.json` | Optional metadata per session (notes, DBN date, strategy variant) |

## Required columns (`fills.csv`)

Mirrors [`FlatFileStore` fills table](../../store.py) plus manual-session fields:

| Column | Description |
|---|---|
| `fill_id` | Unique fill id (Tradovate fill id or generated) |
| `broker_order_id` | Broker order id |
| `intent_id` | Optional strategy intent id |
| `strategy_id` | Strategy tag, e.g. `manual_v2b_session` |
| `trade_id` | Campaign id grouping entry/exit fills |
| `instrument` | `MNQ`, `NQ`, etc. |
| `account_mode` | `paper` or `live` |
| `side` | `buy` or `sell` |
| `quantity` | Contracts filled |
| `price` | Fill price |
| `ts` | Exchange fill timestamp in **America/New_York** ISO format |
| `reason` | `entry`, `runner_entry`, `stop`, `wide_stop`, `runner_stop`, `tp1`, `tp2`, `target`, `eod_close`, `market_close`, `manual_exit` |
| `session_date` | NY calendar date (`YYYY-MM-DD`) |
| `order_type` | `market`, `limit`, `stop`, etc. |
| `source` | e.g. `tradovate_demo` |
| `notes` | Free text |

## Tradovate export workflow

1. Trade one or more full RTH sessions on demo with a consistent `strategy_id` / `trade_id` tag in order text if possible.
2. Export fills from Tradovate sync or saved `events/tradovate_session_events.jsonl`.
3. Map each fill to a journal row using `potions.live.manual_journal.tradovate_fill_to_journal_row`.
4. Validate: `python -m potions.live.manual_journal --validate live/state/live_manual_journal/fills.csv`
5. Run parity audit against replay fills for the same session dates.

## Sample

See `fills.csv` for a single-row template. Replace with real demo fills before running parity gates.

## Parity pass criteria

See [`execution_parity_audit.py`](../../execution_parity_audit.py):

- Median `(live_price - sim_price) >= 0` for entries and exits (sim same or worse)
- >=95% of matched trades within 2 ticks slippage (MNQ/NQ RTH)
- No systematic positive skew in fill delta histograms
