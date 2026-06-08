# Potions Flat-File Live Runtime

This is a paper-first automation runtime for turning the research strategies
into broker-routed systems. Version 0 keeps all state in flat files and uses a
`PaperBroker` by default. The Tradovate adapter is only a boundary shell until
real live routing is explicitly implemented.

## What exists in v0

- Broker interface with `PaperBroker` and inert `TradovateBroker` shell.
- Flat-file state under `potions/live/state/`.
- Persisted job queue, strategy registry, risk checks, spoofed 2FA, disk alerts,
  market-close reports, and a local health endpoint.
- Strategy plugins: `yearly_orb_scaleout3` and `atr_supertrend_dca`.

## Quick Start

```bash
python -m potions.live.cli init --with-yearly-orb --instrument MNQ
python -m potions.live.cli replay --bars potions/mnq/mnq_daily.csv --instrument MNQ --timeframe D
python -m potions.live.cli report
python -m potions.live.cli health --port 8765
```

Use `--state-root /tmp/potions-live-state` while experimenting if you do not
want to write into the default `potions/live/state/` folder.

The current full MNQ Yearly ORB paper replay and exact command path are banked
in [`YEARLY_ORB_MNQ_PAPER_REPLAY.md`](YEARLY_ORB_MNQ_PAPER_REPLAY.md).

The current cross-candidate MTM replay/audit is banked in
[`state/candidate_mtm_audits/SUMMARY.md`](state/candidate_mtm_audits/SUMMARY.md).

The current true StrategyPlugin signal replay ranking is banked in
[`state/strategy_plugin_signal_replays/SUMMARY.md`](state/strategy_plugin_signal_replays/SUMMARY.md).

The current cross-market broker-like bar replay ranking is banked in
[`state/broker_like_replays/SUMMARY.md`](state/broker_like_replays/SUMMARY.md).
This is now the preferred comparison surface for viable daily-bar candidates.
ATR comparison charts are in
[`state/broker_like_replays/charts/INDEX.md`](state/broker_like_replays/charts/INDEX.md).

## Safety Defaults

- Strategies default to `paper`.
- New live entries require verification.
- Paper verification is spoofed and auto-approved.
- Brackets, protective exits, cancels, and range-close flattening do not require
  verification.
- Entry orders can carry `live_after_ts` and `expires_after_ts`; the paper broker
  will not fill early or after expiry.
- Paper market orders fill at the next replay bar open, matching a daily-close
  signal routed for the next tradable open.
- Real Tradovate live routing is not implemented in v0.

## Strategy Notes

The Yearly ORB plugin evaluates completed daily bars only:

- Jan-Mar builds the yearly ORB.
- Apr-Dec watches for a daily close outside the range.
- It places three boundary retest limits, each with its own bracket.
- The runner starts with the swing stop and moves that stop to breakeven after
  the full TP has traded.
- A daily close back inside the yearly ORB requests a market flatten.
- Retest entry orders expire at year end, and year-change reset cancels any
  remaining strategy open orders.

## Market-Close Checklist

Reports are intentionally operator-oriented. Before live credentials, the
checklist should be clean or explicitly explained. It checks account mode,
routable contract / roll placeholders, last completed bar, pending 2FA, failed
jobs, engine errors, risk blocks, expired orders, missing protective brackets,
pending flatten orders, open exposure, active levels, persisted state,
verification records, and recovery files.

Monthly ORB overlap/restricted and v2b should be added as separate plugins once
the daily ATR and Yearly ORB paper paths are reconciled against live/paper fills.
