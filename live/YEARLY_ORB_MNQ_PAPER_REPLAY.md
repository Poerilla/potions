# MNQ Yearly ORB Paper Replay

Runtime path: `potions/live/`

Strategy: `yearly_orb_scaleout3`

State root: `potions/live/state/mnq_yearly_orb_paper_replay`

Source bars: `potions/mnq/mnq_daily.csv`

Last replayed bar: `2026-03-08`

## Command

```bash
rm -rf potions/live/state/mnq_yearly_orb_paper_replay
python3 -m potions.live.cli --state-root potions/live/state/mnq_yearly_orb_paper_replay init \
  --with-yearly-orb \
  --strategy-id yearly_orb_mnq_paper \
  --instrument MNQ \
  --broker-instrument MNQ_CONT \
  --account-mode paper \
  --batch-qty 1 \
  --max-contracts 3
python3 -m potions.live.cli --state-root potions/live/state/mnq_yearly_orb_paper_replay replay \
  --bars potions/mnq/mnq_daily.csv \
  --instrument MNQ \
  --timeframe D
python3 -m potions.live.cli --state-root potions/live/state/mnq_yearly_orb_paper_replay report \
  --report-date 2026-03-08
```

## Result

| Metric | Value |
|---|---:|
| Bars replayed | 2,132 |
| Fills | 114 |
| Entry fills | 72 |
| Exit fills | 42 |
| Realized P/L, points | 19,608.31 |
| MNQ point value used | $2.00 |
| Gross paper P/L | $39,216.62 |
| Close-to-close MTM DD | -$12,546.00 |
| Intrabar stress MTM DD | -$13,378.50 |
| Max open units | 3 |
| Open positions | 0 |
| Open orders | 0 |
| Pending verifications | 0 |
| Risk blocks | 0 |
| Engine errors | 0 |

The report file is:

`potions/live/state/mnq_yearly_orb_paper_replay/reports/2026-03-08.md`

The MTM audit file is:

`potions/live/state/candidate_mtm_audits/mnq_yearly_orb_scaleout3_live_runtime/reports/MTM_AUDIT.md`

The MTM audit replays the actual paper broker fills as unit fills and marks open
units against completed daily bars. `Close-to-close MTM DD` uses daily closes.
`Intrabar stress MTM DD` marks longs to the daily low and shorts to the daily
high before the bar closes, which is the harsher heat number to use for live
capital planning.

## Read

This is a stricter live-runtime replay, not the original research simulator. The runtime uses the same engine/broker/verification/reporting path that live routing will eventually use:

- completed daily bars only;
- entries become active only after the confirming daily close;
- reduce-only market exits fill on the next tradable bar open;
- entry orders expire at the end of their strategy year;
- paper 2FA is spoof-approved, while live mode would block until approval;
- brackets and protective exits do not require 2FA.

The lower P/L versus the research CSV is expected. This runtime is deliberately closer to live operations and currently uses daily OHLC fills, so it does not claim intraday-perfect bracket behavior. It is the right harness for hardening order lifecycle, reporting, recovery, and safety checks before Tradovate credentials.

## Live Ops Checklist Added To Reports

The market-close report now checks:

- account mode and live/paper split;
- broker-routable contract and roll placeholder warnings;
- last completed market data bar;
- pending 2FA verification;
- failed jobs;
- engine errors;
- risk blocks;
- expired orders still open;
- entry intents missing protective brackets;
- pending reduce-only flatten orders without positions;
- open exposure and open order count;
- active ORB levels;
- persisted strategy state;
- verification records;
- recovery files.

Current replay status: all checks pass except the intentional `MNQ_CONT` roll warning. Before real Tradovate credentials, replace that placeholder with a routable contract or roll resolver and rerun this same paper path.

## Hardening Changes From This Replay

- Added `expires_after_ts` to order intents and broker orders.
- Yearly ORB entry orders now expire at year end.
- Year-change reset now cancels existing strategy open orders.
- Paper broker honors `live_after_ts` and `expires_after_ts`.
- Paper market orders fill at next bar open instead of next bar close.
- Market-close reports now include the live ops checklist and paper replay metrics.
