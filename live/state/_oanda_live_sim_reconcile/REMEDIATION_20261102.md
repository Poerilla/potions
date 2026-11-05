# OANDA remediation audit — 2026-11-02

## Outcome

The Asia roll-50 defect was real and is repaired. NAS execution sizing and target-fill realism are now aligned with demonstrated broker capacity, and both affected OANDA practice streams were restarted from verified-flat accounts.

## Asia shadow roll-50

- Root cause: taken sessions waited for `unit_trades.csv`; the OANDA daemon never writes that research artifact.
- Repair input: stored USDJPY 1m bars plus the daemon's persisted Asia opening ranges.
- Backfill window: 2026-09-03 through 2026-11-02.
- Sessions evaluated: 41.
- Campaign observations appended: 38.
- Legitimate no-campaign sessions: 2026-09-09, 2026-09-30, 2026-10-23.
- Shadow count: 107 → 145.
- Current prior-50 gate: WR 0.56, PF 1.14220696, not blocked.
- Backup: `live/demo/usdjpy_asia_range_london_oanda/log_archive/shadow_campaigns_pre_roll50_repair_20261102.json`.
- Machine report: `live/demo/usdjpy_asia_range_london_oanda/SHADOW_ROLL50_REPAIR_20261102.json`.

The runtime now uses the same unfiltered candle simulation on taken and skipped days. Observation writes are keyed by session and idempotent. A missing Asia range after the deadline, a broker-fill session with no simulated campaign, a failed count increment, or an append exception emits `shadow_observation_frozen_alarm` and an immediate Resend hard-alarm email.

## NAS execution and research

- Practice sizing: entry 10, add 10, hard maximum 30 (previous maximum 40).
- Broker rejection alert: every OANDA reject transaction sends immediately through Resend; `INSUFFICIENT_MARGIN` is labeled `HARD ALARM`. Transaction-id deduplication prevents duplicate email from response and status paths.
- Resting target pricing: quote-backed reduce-only targets fill at the target limit after touch. Completed bar-close price improvement is no longer granted.

Official 1m-fill validation, 2016-11-15 through 2025-09-30:

| Sessions | Trades | Units | Net | Closed DD | Stress DD | Max units | PF | N/S | Causality/timing violations |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2,277 | 1,166 | 1,817 | $9,449.35 | −$1,456.40 | −$1,528.40 | 3 | 1.398025 | 6.182511 | 0 |

Previous official tape: net $12,252.95, stress DD −$1,965.85, PF 1.427779, N/S 6.232902, max units 4. The new result is the combined effect of the 30-contract deployment cap and conservative target pricing; it should not be interpreted as isolated attribution to either change.

Public Index Momentum, flat 10× base:

- Backtest end equity: $194,493.50 (net $94,493.50).
- Closed max drawdown: −$14,283.50.
- Profit factor: 1.401.
- Practice window: 24 campaigns, net −$3,148.00 through 2026-11-02.

## Deployment verification

- Pre-restart and final pre-launch broker checks: `-003` and `-004` each had 0 open trades, 0 pending orders, margin used 0.
- Asia `-004`: pid 1578721, reconciled flat, stream HTTP 200, first heartbeat received, shadow count 145.
- NAS `-003`: pid 1580741, reconciled flat, stream HTTP 200, first heartbeat received, config entry/add/max = 10/10/30.
- Restart finding: the shared launcher used a child cwd that broke relative config paths and relied on an exported shell token. It now resolves the config path before spawn and loads `live/demo/.env` when `OANDA_TOKEN` is absent.

## Verification

- Focused runtime suite: 65 passed, 1 skipped.
- Official replay: 871,129 1m fill bars; 174,371 completed 5m signal bars; zero causality violations; zero non-MOC or entry fills at/before activation.
- Ledger: remediation audit `brl_deceeccb4893`; official validation `brl_01a3ca332c8f` (an identical overlapping run also completed as `brl_812d2eff695d`).
