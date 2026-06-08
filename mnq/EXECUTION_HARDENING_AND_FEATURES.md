# MNQ Execution Hardening And Causal Features

This note documents the live-style assumptions added beside the existing
research backtests. The default backtest mode remains no-op/legacy so older CSVs
can still be reproduced. Live realism is opt-in through chronological child
handling, deterministic roll selection, and explicit execution stress profiles.

## Execution Model

Use `--child-engine chronological` when testing anything intended to become a
TradingView/Pine + Tradovate workflow. The chronological engine behaves like a
live bot:

1. Parent v2b/v2d order fills.
2. Existing TP/SL/partial exits are checked on each 1m bar.
3. Already-live child limits are checked.
4. Only after a 5m candle has completed is a child signal evaluated.
5. A child limit becomes live at the 5m close plus any configured delay.
6. Pending children are cancelled on TP, SL, child partial stop, EOD, or blackout.

The child audit CSV records:

`candidate_time`, `limit_price`, `live_after`, `filter_pass`,
`filter_reason`, `filled`, `fill_time`, and `cancel_reason`.

## Deterministic Roll Calendar

`lib/mnq_roll_calendar.csv` defines quarterly MNQ roll windows with:

`product`, `start_date`, `end_date`, `symbol`, `notes`.

Use `--roll-mode calendar` for live-style deterministic contract selection. Use
`--roll-mode legacy-volume` to reproduce older backtests that picked the same-day
highest-volume symbol after the full session was known.

Pine cannot select futures contracts internally. For live use, chart/trade the
active Tradovate contract directly. Continuous symbols such as `MNQ1!` are useful
for research and visual checks, but they are not a broker-routed contract.

## Stress Profiles

The normal baseline keeps current assumptions:

- entry slippage stays at `--slip-ticks`
- no stop slippage
- targets fill on touch
- child limits fill on touch
- no random child misses
- current intrabar ordering
- no blackout windows

The sidecar `--stress-report` runs chronological simulations for:

| Profile | Purpose |
|---|---|
| `baseline` | No-op chronological reference. |
| `mild` | Child limits require 1 tick through; stop slippage +1 tick. |
| `conservative` | Target and child limits require 1 tick through; stop slippage +2 ticks; adverse target/stop ambiguity; deterministic 15% child miss model. |
| `latency` | Child orders become live one 1m bar later. This is a coarse proxy for 1-5 seconds with only 1m data. |
| `blackout` | Skips new entries/children during windows from a CSV with `start,end,reason`. Existing protective exits still apply. |

The stress report is still a 1m OHLC approximation. Exact queue position,
bid/ask spread, sub-second latency, partial fills, and order priority require
tick or 1-second market data plus actual Tradovate order/fill logs.

## Monthly ORB Session Hardening

The monthly ORB studies currently define the opening range from the first three
rows in the instrument daily CSV. On the available MNQ/NQ files, those rows can
include Globex/session-calendar rows such as Sunday evening dates. This is
causal, but it is not the same as saying "first three RTH trading days" unless
the daily file itself is explicitly RTH-only.

Hardening action before a live Pine/MultiCharts port:

- choose and document the session definition: full futures session vs RTH-only
- generate an explicit monthly OR calendar table with `period`,
  `range_start_date`, `range_end_date`, `first_trade_date`, `session_definition`,
  `range_high`, and `range_low`
- make both Python and Pine/MultiCharts consume that same definition
- keep current CSV-row behavior as a named research mode, not an implicit live
  assumption

## Optional Child Filters

Child filters are disabled by default. When enabled, they are intended to reject
scale-ins that are most sensitive to execution noise:

| Filter | Intent |
|---|---|
| Minimum distance remaining to target | Avoid adding when little reward remains. |
| Maximum elapsed time since parent fill | Avoid late-session or stale continuation adds. |
| Min/max opening range size | Avoid abnormally tiny or huge OR days. |
| Minimum child-close distance to target | Avoid adding after a candle closes too close to TP. |
| Maximum 1m impulse inside signal candle | Avoid adding after a violent 1m spike. |
| Max child adds | Keep live testing at one child until paper logs prove robustness. |

## Causal Feature Table Plan

Future predictor work should write one row per session/trade with both a feature
value and a `known_at` timestamp. Any candidate live filter should also carry
`tradable_at_entry = true/false` to prevent accidental lookahead.

| Feature | Known when? | Current data enough? | Pine feasibility | Notes |
|---|---|---|---|---|
| OR width vs prior-day ATR | 9:45 after OR completes | Daily + RTH 1m enough | Yes | ATR must use prior completed daily bars. |
| Gap from prior close | 9:30 RTH open | Daily + 1m enough | Yes | Use prior completed session close, not same-day close. |
| Distance to prior day high/low | Before session | Daily enough | Yes | Clean causal level feature. |
| Distance to prior week high/low | Before session | Daily enough; existing prior-week helper can be reused | Yes | Prior calendar week only. |
| Overnight trend | By 9:30 | Full Globex 1m needed; likely available in raw DBN | Yes if chart has overnight data | Define exact window before testing. |
| First 15m volume percentile | 9:45 | 1m volume + rolling history enough | Partial | Pine can compute rolling percentiles awkwardly; Python easier. |
| Breakout aligned with premarket direction | At breakout | 1m + overnight enough | Yes | Valid for child/fade decisions; v2b stop already exists. |
| Breakout into/away from major levels | At breakout | Daily/prior-week/overnight levels needed | Yes | Define level priority before testing. |
| Time-to-breakout after 9:45 | At breakout | 1m enough | Yes | Not a pre-entry filter for pre-placed v2b stops; valid for child/fade logic. |
| Breakout candle body/wick quality | After candle close | 1m enough | Yes | Not legal for same-bar stop entry unless entry is delayed. |

## Proposed Feature Generator

Add a future script such as `scripts/build_causal_feature_table.py` that:

- loads the same 1m and daily data as the backtests
- uses the selected roll mode
- writes one row per date/leg
- records feature values, `known_at`, and `tradable_at_entry`
- joins final trade outcome only after all causal features are computed
- supports walk-forward slicing so filters are selected on prior data only

Until that table exists, predictor claims should be treated as exploratory.

## Pine/Tradovate Notes

Pine scale-ins should use separate entry IDs such as `L1/S1` for the parent and
`LC1/SC1`, `LC2/SC2` for children. `pyramiding` must allow the parent plus
children. Parent exits keep the wide v2b/v2d stop and shared target; child exits
use their own tighter stop and shared target through separate `strategy.exit`
calls.

Build 5m child signals causally on the 1m chart by detecting completed 5m
windows. Do not use incomplete higher-timeframe data to decide a child add.
