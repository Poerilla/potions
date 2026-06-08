# Pine Scripts — TradingView execution

This folder holds the canonical Pine Script implementations of the ORB and
ATR strategy studies that match the Python backtests in `../scripts/` and
`../combined_orb/scripts/`.

## Files

| File | Purpose |
|---|---|
| **`atr_supertrend_dca_10max_entry_guard_3initial.pine`** | **ATR SUPERTREND LIVE-TEST LEADER.** Long-only ATR Supertrend DCA harness with selectable Daily or Weekly primary signal, 10 max contracts, 3 initial contracts, biweekly Friday adds, weekly-flat option for Daily mode, and initial-entry close guard. |
| **`atr_supertrend_dca_10max_entry_guard_ladder112221.pine`** | **LOWER-HEAT ATR SIZING VARIANT.** Same causal ATR Supertrend DCA logic, but scale events size as 1, 1, 2, 2, 2, then 1s until the max. Useful for paper-testing a smoother risk profile against the 3-initial leader. |
| **`yearly_orb_scaleout3_range_close.pine`** | **LOW-FREQUENCY YEARLY ORB CANDIDATE.** Daily-chart Pine harness for the yearly ORB scaleout3 / inside-range swing stop / range-close variant. Uses 3 entry IDs per side and a `Contracts per scaleout batch` input: MNQ `1` = 3 total contracts; MYM `4` = 12 total contracts scaled out as 4/4/4. |
| **`orb_adaptive_50_150_v2b_scaleout.pine`** | **CURRENT RESEARCH LEADER FOR PAPER TESTING.** Prior-day 50/150 SMA gates v2b-only breakout days; non-v2b days are skipped. Uses 2 entries per side (`L1/L2`, `S1/S2`): 1 contract exits at TP1, runner moves stop to entry and targets TP2. Default TradingView slippage is `1` tick, adjustable in Strategy Properties. |
| **`orb_adaptive_50_150.pine`** | **CANONICAL LIVE STRATEGY.** v2b/v2d switch on prior-day MNQ daily 50/150 SMA. Chart preset controls London vs NY range times. Run **one chart per leg** (e.g. MNQ1! for London+NY presets, MYM1! for MYM NY) with the same adaptive logic. Python triad backtest: ~**$20.5k** net 2021–2026 (1 MNQ NY + 1 MNQ London + 1 MYM NY); MNQ NY alone ~$3.7k/yr, 1.05 Calmar. |
| **`orb_adaptive_50_150_child.pine`** | **EXECUTION-TEST VARIANT.** Adaptive 50/150 with v2b_child-style scale-ins, separate parent/child entry IDs, `pyramiding=3`, completed-5m child signals, and optional no-op child filters. Start paper/live reconciliation with `Max child adds = 1`; compare against the Python chronological/stress run before scaling. |
| `orb_v2_preplaced_stops.pine` | v2b-only (always breakout). Simpler reference; ~$3,020/yr per MNQ, 0.64 Calmar. |

> **⚠️ 2026-04-25 update**: the script now implements bracket-then-reverse
> (after a Long trade closes, only the Short stop re-arms and vice
> versa). This matches the corrected v2b Python backtest. See
> `../scripts/validation.md` for the v2a→v2b correction story and
> honest expected returns.
>
> Under **v2b-only**, MNQ London and MYM sessions were net-negative; under
> **adaptive 50/150**, MYM NY and MNQ London flip to v2d on chop regimes
> and the combined triad is net-positive in Python (`orb-portfolio/README.md`).

## Quick start

1. **Open TradingView**, log in, open a chart for the symbol you want
   to trade (e.g. `MNQ1!` for continuous Micro Nasdaq, or the active
   front-month like `MNQM2026`).
2. **Set the chart timeframe.** Use `1 minute` for the v2/adaptive ORB
   scripts; use `1 minute` or `5 minute` for the ATR Supertrend DCA scripts
   so the Friday 15:50 add bar exists; use `Daily` for
   `yearly_orb_scaleout3_range_close.pine`. The v2 backtest is built on
   1-min intrabar fills, while the yearly ORB study is built from daily bars.
3. **Pine Editor → Open new** → paste the contents of the script you want:
   `atr_supertrend_dca_10max_entry_guard_3initial.pine` for the ATR leader,
   `atr_supertrend_dca_10max_entry_guard_ladder112221.pine` for the lower-heat ATR ladder,
   `yearly_orb_scaleout3_range_close.pine` for the yearly ORB candidate,
   `orb_adaptive_50_150_v2b_scaleout.pine` for the current scaleout leader,
   `orb_adaptive_50_150.pine` for the base adaptive model, or
   `orb_adaptive_50_150_child.pine` for the scale-in execution test.
4. **Save** with a descriptive name (e.g. `MNQ ORB Adaptive Child`).
5. **Add to chart** → strategy settings panel appears.
6. **Configure inputs** for your session (presets below).

## Session presets

All times are New York (set via the script's `sess_tz` constant).

| Variant | Range start | Range end | Force-close | Symbol (TV) |
|---|---|---|---|---|
| MNQ NY     | 09:30 | 09:45 | 15:55 | MNQ1! |
| MNQ London | 02:00 | 02:15 | 10:55 | MNQ1! |
| MYM NY     | 09:30 | 09:45 | 15:55 | MYM1! |
| MYM London | 02:00 | 02:15 | 10:55 | MYM1! |

## TradingView / Tradovate Boundary

1. **Connect Tradovate** in TradingView's broker panel for manual or broker-panel
   trading. Use the active front-month contract for execution; continuous symbols
   are for research/backtesting.
2. **Pine strategy orders are simulated by TradingView's broker emulator.**
   These scripts can backtest, forward-test, and emit strategy order-fill alert
   messages, but Pine code does not log in to Tradovate or directly bind itself
   to a brokerage account.
3. **Automation path**: create a TradingView strategy alert using order-fill
   events and message `{{strategy.order.alert_message}}`, then route that alert
   through a Tradovate-capable execution bridge/webhook if you want unattended
   paper/live execution. Without that bridge, use the script as a Strategy Tester
   and manual execution aid.
4. **Reconciliation requirement**: compare TradingView strategy trades against
   Tradovate demo fills before any live sizing. TradingView still cannot prove
   queue position, partial fills, broker disconnects, or real slippage.

For the ORB scripts that use stop/limit/bracket orders, make sure the actual
execution bridge/broker settings match the order semantics described in each
script. For the ATR Supertrend DCA scripts below, entries/adds/exits are market
orders on confirmed strategy events, which is simpler to automate than bracket
or resting-limit logic.

For `yearly_orb_scaleout3_range_close.pine`, the entries are retest
**limit** orders at the yearly ORB boundary, not breakout stop-market
orders.

### ATR Supertrend DCA Scripts

The ATR DCA scripts cover both current ATR study time periods from one input:

| Script | Primary signal timeframe input | Sizing |
|---|---|---|
| `atr_supertrend_dca_10max_entry_guard_3initial.pine` | `Daily` or `Weekly` | 3 initial, then +1 every second eligible Friday |
| `atr_supertrend_dca_10max_entry_guard_ladder112221.pine` | `Daily` or `Weekly` | 1, 1, 2, 2, 2, then +1s |

Recommended first paper-test settings:

| Setting | Value |
|---|---|
| Chart timeframe | `1 minute` or `5 minute` |
| Symbol | Active Tradovate MNQ/NQ contract for execution; continuous symbol for research |
| Primary signal timeframe | `Weekly` for the current leader; `Daily` for the daily-primary comparison |
| ATR length / multiplier | `14` / `3.0` |
| Max contracts | `10` |
| Add interval | `2` eligible Fridays |
| Friday add time | `15:50` New York |
| Slippage | Strategy Properties -> Slippage, default `1` tick |

Causality notes:

- Daily and weekly Supertrend values are pulled from the last completed higher
  timeframe bar using `[1]` inside `request.security(...)`.
- The initial-entry guard is close-based; wicks below the guard do not flatten.
- Re-entry after a guard exit requires a later close back above the guard while
  the primary trend is still bullish.
- Friday adds are placed only on the completed intraday bar at the configured
  add time.

Python references:

```bash
python3 potions/scripts/atr_supertrend_dca_long.py \
  --symbol mnq \
  --signal-timeframe weekly \
  --add-interval-weeks 2 \
  --max-contracts 10 \
  --initial-contracts 3 \
  --long-entry-price-guard exit-reclaim

python3 potions/scripts/atr_supertrend_dca_long.py \
  --symbol mnq \
  --signal-timeframe weekly \
  --add-interval-weeks 2 \
  --max-contracts 10 \
  --position-size-schedule 1,1,2,2,2 \
  --long-entry-price-guard exit-reclaim
```

### v2b-only Scaleout Script

`orb_adaptive_50_150_v2b_scaleout.pine` uses separate entry IDs so the
TP1 contract and runner can be tracked independently:

| Role | Long ID | Short ID |
|---|---|---|
| TP1 contract | `L1` | `S1` |
| Runner contract | `L2` | `S2` |

Recommended first paper/backtest settings:

| Setting | Value |
|---|---|
| Chart timeframe | `1 minute` |
| Symbol | `MNQ1!` for research, or active Tradovate MNQ contract for execution |
| Slippage | Strategy Properties -> Slippage, default `1` tick |
| Initial capital | Start around the intended paper-test account size |
| Commission | Script default `0.75` per side per contract |

Note: TradingView exposes strategy slippage in the Properties panel rather
than as a normal Pine input. The script sets the default to `1` tick to
match the existing Pine scripts; adjust it there for stress testing.

### Child Scale-In Script

`orb_adaptive_50_150_child.pine` uses separate entry IDs:

| Role | Long IDs | Short IDs |
|---|---|---|
| v2b parent | `L1` | `S1` |
| v2d parent | `FL1` | `FS1` |
| child 1 | `LC1` | `SC1` |
| child 2 | `LC2` | `SC2` |

Recommended first execution-test settings:

| Input | Value |
|---|---|
| Max child adds | `1` |
| Child partial stop | `edge` |
| Enable child filters | `false` |
| Chart timeframe | `1 minute` |

Python comparison run:

```bash
python3 potions/mnq/v2d/orb_adaptive_50_150_child.py \
  --max-child-adds 1 \
  --child-engine chronological \
  --stress-report \
  --out /tmp/adaptive_chrono_child.csv
```

Use the generated `.child_audit.csv` and `.execution_stress.md` as the
baseline for paper-trade reconciliation.

### Yearly ORB Scaleout3 Script

`yearly_orb_scaleout3_range_close.pine` is the daily-chart automation
harness for the current higher-timeframe candidate:

| Role | Long ID | Short ID |
|---|---|---|
| 25% target batch | `L25` | `S25` |
| Full target batch | `LTP` | `STP` |
| Runner batch | `LRUN` | `SRUN` |

Recommended portfolio sizing inputs:

| Symbol | Contracts per scaleout batch | Total contracts |
|---|---:|---:|
| MNQ | `1` | `3` |
| MYM | `4` | `12` |

The 1 MNQ unit + 4 MYM unit portfolio means running two separate charts:
MNQ with batch qty `1`, MYM with batch qty `4`. This is 3 MNQ contracts
plus 12 MYM contracts, not 1 MNQ contract plus 4 MYM contracts.

Use a **daily** chart. The Python research uses daily OHLC and this Pine
script makes the retest order live after the breakout close; exact same-day
fill ordering and queue behavior still require broker fill logs for proof.

## Validation procedure before going live

1. **Bar-replay backtest** in TradingView on the last 90 days. Compare
   trade count and direction against
   `../mnq/mnq_orb_results_stops.csv` (or the matching v2 CSV) for the
   same window. They should agree within 1-2 trades.
2. **Paper trade** through Tradovate Demo for 5 sessions. Verify:
   - Range computed correctly (`Range_High` / `Range_Low` printed at
     9:45 ET match the chart's actual high/low of 9:30-9:44).
   - OCO behavior: when one stop fires, the other is canceled within
     200 ms.
   - Bracket exit attaches with correct target and stop levels.
   - For the child script: completed 5m child candidates, placed child
     limits, actual child fills, and child cancels match the Python audit
     closely enough to explain every difference.
3. **Live with real $$ at minimum size** (1 contract) for 1 month.
   Track:
   - Fills vs backtest expected (`fill_price - range_boundary` should
     average ≤ 1 tick).
   - Commission per round-turn matches Tradovate billing.
   - No missed re-arms (after a trade closes, OCO should re-arm before
     the next bar).
4. **Scale to target size only after 30 trading days** of clean
   reconciliation against the backtest.

## Inputs reference

| Input | Default | Notes |
|---|---|---|
| Range start hour/min | 09:30 | Set to 02:00 for London |
| Range end hour/min | 09:45 | Set to 02:15 for London |
| Force-close hour/min | 15:55 | Set to 10:55 for London (5 min before 11:00 trade window end) |
| Max trades/day | 2 | Matches v2 backtest |
| Trigger ticks beyond range | 1 | Buy-stop at RH+1tick. Increase to widen breakout filter (will miss some trades but skip more fakeouts). |
| Reward:Risk multiplier | 1.0 | Target = Entry ± (Range × R). Default = 1R. |

## Visuals

The script plots:
- **Range High / Low** as solid lines once the opening range is set
- **Long Target / Short Target** as dotted circles while the OCO is armed
- **Blue background shading** during the opening range window
- **Gray background shading** during the EOD close window

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Strategy takes way more trades than backtest | Chart timeframe is < 1 min (e.g. tick chart). Set chart to **1 min**. |
| Strategy takes way fewer trades than backtest | Chart timeframe is > 1 min (e.g. 5 min). Set chart to **1 min**. |
| Range is computed wrong | Symbol has wrong session settings. Use `MNQ1!` not `MNQ`. Check the chart shows price activity at 09:30-09:45 NY. |
| OCO doesn't cancel the other leg | Check the script declaration and entry IDs. Base scripts use `pyramiding=0`; the child script intentionally uses `pyramiding=3` and cancels parent OCO legs by ID. |
| Re-arm after trade close doesn't happen | The `armed` state didn't reset. Check that `trade_just_closed` evaluates true on the bar a position closes. |
| Position carried over from yesterday | Force-close hour/min is wrong, or `is_eod` evaluation didn't trigger. For London, set force-close to 10:55. |

## Related

- `../scripts/validation.md` — full v1 vs v2 strategy spec
- `../scripts/step2_preplaced_stops.py` — Python reference implementation
- `../combined_orb/scripts/london_ny_orb_stops.py` — Python London + NY backtest
- `../orb-portfolio/monte_carlo.py` — portfolio-level simulation
- `../case_studies/README.md` — **read before paper-trading** — six annotated real days showing what the system looks like in practice (clean wins, loss-then-win, whipsaws, EOD closes)
