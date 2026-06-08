# Start-Small Broker Execution Plan

## Purpose

Use **MNQ v2b TP1-only** as the first small, feedback-rich live/paper execution test before deploying larger ladders or slower higher-timeframe systems.

The goal of the first six months is **not** to maximize PnL. The goal is to prove that the runtime can:

- ingest live 1m data,
- build correct 5m/RTH state,
- generate the expected v2b OCO orders,
- place and manage broker orders,
- reconcile fills and positions,
- alert reliably,
- recover from restarts/outages,
- and produce a complete audit trail.

If we can execute cleanly on the 5-minute level, the higher-timeframe ORB and ATR systems become much easier to trust.

## Starting Candidate

Strategy: **MNQ v2b OCO then reverse, TP1-only**

Rules:

- Market: `MNQ`
- Prior-day regime: MA50 > MA150
- Session: RTH 09:30-16:00 New York
- Opening range: 09:30-09:45
- Entry: OCO stop at OR high + tick / OR low - tick
- Size: 1 MNQ contract
- Exit: TP1 only, no TP2 bucket, no runner
- Max position: 1 contract
- Same-day behavior: no overnight holds; flatten at configured EOD cutoff

Broker-like replay snapshot:

| Market | Sessions | Trades | Net | Closed DD | Stress DD | Win % | PF | Net / Stress |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | 1,164 | 1,306 | $10,084.50 | -$3,095.00 | -$3,109.00 | 54.5% | 1.11 | 3.24 |

Source: `live/state/v2b_tp1_only_quick_study/SUMMARY.md`

Cloud bootstrap: `live/specs/START_SMALL_CLOUD_BOOTSTRAP.md` and
`live/deploy/README.md`.

## Six-Month Budget

Base experiment budget:

| Item | Amount |
|---|---:|
| Trading risk/account allocation | $7,500 |
| Databento live feed estimate | $179/month |
| Six months of data fees | $1,074 |
| Minimum planned commitment | $8,574 plus broker/exchange/commission/slippage costs |

Important: `$7,500` is the planned account-risk allocation, not a guarantee that losses cannot exceed that amount. Futures can move fast, stops can gap, platforms can fail, and fees/slippage compound. The broker account must have independent loss limits, flatten controls, and a human kill switch.

## Deployment Ladder

### Phase 0 - Dry-Run Feed Rehearsal

Duration: 2-4 weeks.

Capital: none.

Mode:

- Use live Databento or Tradovate data.
- Do not place broker orders.
- Strategy generates order intents and alerts only.
- Compare generated signals against same-day replay after close.

Required output:

- `bars/MNQ_1m.csv`
- derived `MNQ_5m.csv`
- order intents
- alerts
- market-close execution report
- feed health report
- feed-vs-replay audit

Exit criteria:

- 1m and 5m bars are complete and deduplicated.
- Opening range levels match expected RTH construction.
- No strategy uses partial bars.
- All would-be entries/exits are explainable from stored bars.
- Feed stale alerts fire correctly.
- Restart during RTH does not duplicate orders.

### Phase 1 - Broker Paper Trading

Duration: 4-8 weeks.

Capital: broker paper/demo only.

Mode:

- Same live feed path.
- Tradovate or chosen broker paper account receives real paper orders.
- Size remains 1 MNQ.
- Strategy remains TP1-only.

Exit criteria:

- Every entry has a corresponding broker order id.
- Every fill maps to `strategy_id`, `trade_id`, `intent_id`, and broker order id.
- Local position matches broker position after every fill.
- Broker-side stops/targets are present whenever a position is open.
- EOD flatten works.
- Manual kill switch works.
- Daily report reconciles orders, fills, positions, and alerts.
- No unplanned live/paper order is created.

### Phase 2 - Small Live or Funded-Paper Trial

Duration: 6 months.

Capital/risk allocation: `$7,500`.

Mode:

- 1 MNQ contract.
- TP1-only.
- No TP2.
- No runner.
- No pyramiding.
- No strategy changes mid-phase except bug fixes.

What counts as success:

- Execution fidelity, not PnL.
- All trades are reconstructable from bars, orders, fills, alerts, and reports.
- No unresolved broker/local position mismatch.
- No missed flatten.
- No duplicate entries.
- No stale-feed entries.
- No bracket/protective-order gaps after entry.
- Error handling is tested by real disconnects/restarts.

What does not count as success by itself:

- Good PnL.
- A short lucky streak.
- A backtest matching the paper/live PnL exactly.

## Risk Controls

Hard controls:

- Max open position: 1 MNQ.
- Max active entry order group: one OCO pair.
- No new entries when feed stale.
- No new entries if broker position cannot be reconciled.
- No new entries if current contract mapping is stale or unresolved.
- No new entries after EOD cutoff.
- EOD flatten required.
- Manual kill switch required.
- Broker-native protective order required after entry.

Suggested loss controls:

- Daily realized loss alert.
- Weekly loss alert.
- Monthly loss alert.
- Manual review after any day with broker/local mismatch.
- Manual review after any stop gap-through event larger than expected.
- Pause after any unexplained order, fill, or flatten failure.

## Reports To Generate

Daily:

- feed status
- bar completeness
- OR high/low
- eligible regime state
- order intents
- broker orders
- fills
- realized PnL
- open/flat confirmation
- stale feed events
- discrepancies
- next expected action

Weekly:

- execution fidelity score
- missed/duplicate orders
- broker/local mismatch count
- feed outage count
- average alert latency
- realized vs expected fill slippage
- whether any manual intervention occurred

Monthly:

- PnL summary
- drawdown/stress summary
- fee/slippage total
- feed cost total
- operational incidents
- decision: continue, pause, or promote

## Promotion Gate After Six Months

Do not promote based on PnL alone.

Promote only if:

- runtime had no unresolved position mismatches,
- every trade is auditable,
- feed outages were handled without unsafe orders,
- all EOD flats worked,
- broker-side protective orders were present when required,
- order mapping survived restarts,
- alerts/reports were timely enough to operate from,
- and the operator is comfortable with the full trade lifecycle.

If promoted:

1. Add more capital.
2. Turn on the next v2b exit bucket:
   - TP1 + TP2, or
   - TP1 + TP2 + runner if explicitly chosen.
3. Run another 3-month paper/live-small trial.
4. Keep max contracts low until the new exit logic has the same audit confidence as TP1-only.

Note: "TP25" is a yearly-ORB naming convention. For v2b, the natural next buckets are TP1 and TP2 based on opening-range multiples. If a TP25-style partial is desired for v2b, it should be implemented as a separate sizing variant and replayed before live use.

## Three-Month Expansion Trial

After six-month TP1-only confidence:

- Add capital before adding exposure.
- Enable TP2 bucket with a small size.
- Keep total open exposure capped.
- Compare live/paper behavior to broker-like replay.
- Track whether TP2 management creates new operational risk:
  - cancel/replace errors
  - runner stop movement errors
  - partial fill handling
  - OCO peer cancellation issues

Success means the expanded order lifecycle is clean, not merely profitable.

## Why v2b First

v2b is a good first deployment candidate because it gives frequent feedback:

- many sessions,
- many order cycles,
- intraday entries and exits,
- OCO behavior,
- bracket/protective order handling,
- EOD flattening,
- feed staleness sensitivity,
- and enough fills to reveal operational bugs quickly.

If the runtime can handle v2b, then slower systems such as yearly ORB, monthly ORB, and ATR Supertrend should be much easier to operate because they have fewer timing-critical events.

## Later Start-Small Tests

After MNQ v2b is stable:

- Yearly ORB MNQ or MYM small-unit trial.
- NQ v2b only after capital and stress tolerance are much larger.
- ATR daily ladder only after contract scaling, add scheduling, and weekly/daily Supertrend state are fully audited.
- Monthly overlap/retest only after the 4h bar builder and retest-limit lifecycle are proven.

Each new strategy should start with:

- smallest viable contract,
- smallest viable size,
- one strategy instance,
- paper/dry-run first,
- then small live/funded-paper,
- then only scale after operational confidence exists.
