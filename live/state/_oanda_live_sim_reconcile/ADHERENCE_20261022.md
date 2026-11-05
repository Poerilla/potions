# Live strategy adherence — 2026-10-22

Live OANDA practice books (all daemons UP): NAS100 clean-break `trail06_m4_e2_out_be`, USDJPY Asia-range London `S_3_1_3_flt`, USDJPY Monday OR `M2_S3_R1`.

Two checks:

1. **Live fills vs rule replay** — the daemon's actual `fills.csv` vs a fresh Engine+StrategyPlugin replay on the daemon's own stored bars, live `config_json`, plus a fresh-spawn config drift check. Entries before `RUN_META.started_at` excluded.
2. **Tick-fed parity** — stored OANDA ticks → live aggregation path vs fresh plugin on the same bars.

## Verdict: entry/exit execution follows the rules on all three books; Asia-range roll50 gate is frozen open (operator-accepted, see below)

| Book | Live vs replay entries | Exits by reason | Config drift | Tick parity |
|---|---|---|---|---|
| USDJPY Monday OR | 8 / 8 exact | identical (dd30 6, dd50 6, week_end 1) | none | MATCH 36/36 (Jul 28 → Oct 22) |
| NAS100 clean-break | 10 / 10 same 5m signal bar (7 exact minute) | identical (add 2, close_back_into_range 5, failed_clean_close 5) | none | MATCH 34/34 (tick archive Jul 24 → Aug 19 only) |
| USDJPY Asia-range London | 20 / 24 within ±2 min; 3 same price, earlier trigger; 1 extra live reversal | identical except +1 eod_close (the extra reversal) | none | MATCH 113/113 (Aug 11 → Oct 22) |

## Explained differences (not rule breaches)

- **NAS100 minute offsets (3 days):** replay stamps the fill at the 5m bar label; live records the actual tick minute inside the same 5m bar (e.g. 13:48 live vs 13:45 bar). Same side/qty; entry price gap 0–14.75 pts from intrabar timing.
- **USDJPY Asia 2026-09-25 / 10-06:** same stop level, same fill price (157.949 vs 157.950; 158.249 vs 158.2475), same exits. Live triggers on the executable bid/ask; stored 1m bars are mid and missed the level by 0.2 / 0.8 pip until 09:09 / 09:30 UTC.
- **USDJPY Asia 2026-10-15:** 3-minute offset, same prices and exits.
- **USDJPY Asia 2026-10-01 (extra live trade):** the long's wide stop hit on the bid at 14:32:37 (mid bar low 157.3845 never reached 157.370 in that minute). Live then placed the stop-and-reverse sell and filled 27 s later at 157.368 inside the 14:33 bar. Replay only stops in the 14:33 bar and the reverse cannot fill in the same bar (`live_after_ts`); price never revisited the level, so no reversal. Rule-consistent and causal; costs ≈ -193k JPY (sell 157.368 → EOD 157.644).

## Shadow roll50 gate frozen open (USDJPY Asia-range) — left as is by operator

The fills/tick checks replay the daemon's own shadow book, so they cannot see this.

- Since the 2026-09-22 restart the shadow book has stayed at **107 nets**. Every session is a `take`, and the EOD append waits for `state/unit_trades.csv`, which the live daemon never writes (`take_await_unit_trades`, logged on every post-EOD tick: 25k–67k rows/day in `campaign_parity.csv` + `PROGRESS.log`).
- Counterfactual (read-only): appending each session's unfiltered candle-sim net, the PF<1.0 gate would have **sat out 14 of the 15 sessions from Oct 2** (all except Oct 15). Live P&L on those 14 sessions: **−$1,453**; on the 7 allowed sessions: −$5,587. Current roll50 PF would be 0.83 → sit out.
- Why it is open: from **Aug 13 → Sep 2** the gate sat out every session at an unchanging WR 0.500 / PF 0.707 (window not advancing). On **Sep 2** the shadow book was reseeded `last100_clear_roll50` (`prefer_clear_roll`, `latest_clear_roll_end`: "so the trailing roll window is not stuck on a PF-broken research tail"); gate reopened Sep 3 at PF 1.028 and has not moved since. Book running unthrottled ≈ the Aug 11 three-book forward test's book B (Jan-only), which beat roll50 book C out-of-sample (N/S 6.56 vs 4.23).
- Operator decision 2026-10-22: **leave frozen**; no shadow code change, no backfill.
- Counterfactual tape: `asia_shadow_counterfactual_20261022.json`.

## Data issue found

`usdjpy_asia_range_london_oanda/state/bars/USDJPY_1m.csv` stores **every 1m bar twice** (67,608 duplicate rows since 2026-08-11). Cause: `usdjpy_asia_range_london_common.py` calls `self.store.append_bar(bar_1m)` and then `engine.process_bar(bar_1m)` with `persist_bars=True`, which appends again. Each bar is still **processed once** — trading unaffected (24 entries / 24 distinct trade IDs). The reconciler now skips duplicate bar timestamps; results unchanged after dedup.

**Fixed 2026-10-22 16:39 EDT:** removed the explicit `store.append_bar` in the runner (Engine persists); the skip-day candle-sim reader now skips repeated timestamps for the doubled history. Daemon restarted flat, pre-Asia window, on account `-004` (pid 643631); bars since restart written once. A first restart attempt without `--oanda-config` came up on shared `-001` (stream timeouts only; 0 orders/intents/fills) and was stopped within 4 minutes; README launch line now includes the config.

## Not live

`us30_hourly_st_pmc_sl50_tp150_3r_paper`, `usdjpy_asia_range_london_paper`, `usdjpy_monday_or_ungated_paper` — down since 2026-09-20 (stream reconnect failure). Not audited.

## Artifacts

- `live/state/_oanda_live_sim_reconcile/adherence_20261022_dedup.json`
- `live/state/usdjpy_live_demo_plugin_tick_parity_v1/RUN_COMPLETE.json`
- `live/state/nas100_clean_break_demo_plugin_tick_parity_v1/RUN_COMPLETE.json`
