# Live/demo adherence issues ledger

Append-only record for month-end adherence audits. Scope: process health,
brackets, fill-reason mix, stream/recovery, OANDA bleed — **not** PnL.

Artifacts per check often also live as:
- `EMAIL_ADHERENCE_YYYY-MM-DD*.txt`
- `ADHERENCE_INVENTORY_YYYY-MM-DD.csv` (and/or `ADHERENCE_INVENTORY_TODAY.csv`)

---

## 2026-08-13 — midday email (~17:27 UTC / 13:27 EDT)

Source: `EMAIL_ADHERENCE_2026-08-13.txt`

| Severity | Issue | Status at write |
|----------|-------|-----------------|
| FLAG | `us30_hourly_st_pmc_sl50_tp150_3r_oanda`: open US30 qty=2, local orders empty / no working stop+target vs 3R design | open (midday) |
| FLAG | Shared OANDA practice bleed: non-US30/NAS100 demos showing NAS100+US30 rows in `positions.csv` with `strategy_id=oanda` while heartbeat qty may be 0 | open (midday) |
| NOTE | Overnight OANDA stream: V20Timeout / disconnect / HTTP 429; heartbeats recovered | recovered |
| NOTE | `us30_london_prior_opposed_oanda`: ticks=0, bars advancing | intentional? |

Verdict then: paper books healthy; OANDA shared-account state needs careful reading.

---

## 2026-08-13 — as_of 18:35 UTC (14:35 EDT)

Sources: `EMAIL_ADHERENCE_TODAY.txt`, `ADHERENCE_INVENTORY_TODAY.csv`
(also archived as `ADHERENCE_INVENTORY_2026-08-13.csv`, `EMAIL_ADHERENCE_2026-08-13_1835Z.txt`)

### Inventory
- demos with pidfile: 35 — alive 35 / dead 0
- PROGRESS stale >20m: none
- open without any working order: none

### FLAGs (execution / brackets)
| Demo | Observation | Contrast |
|------|-------------|----------|
| `nas100_v2b_ungated_oanda` | open NAS100 qty=3 with only working protective stop (`bracket_role=entry`); tp1/tp2/wide_stop not resting after latest entry | paper twin has runner_stop+tp2 |
| `spx500_v2b_ungated_oanda` | open SPX500 qty=3 with only working protective stop (`bracket_role=entry`); tp1/tp2 not resting after latest entry | — |

### Expected opens (not flags)
- `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_paper`: qty=1, runner_stop+target (post scale-out)
- `nas100_v2b_ungated_paper`: qty=2, runner_stop+tp2 (post-tp1)

### Fill-reason mix (today, adherence only)
Reason vocabulary matched contracts (no unexpected reasons):
- us30 ST+PMC runners paper: entry / runner_entry / runner_entry_2 / stop / runner_stop
- us30 ST+PMC 3R paper: entry / stop
- us30 london prior-opposed paper: entry / eod_close
- nas100 v2b paper: entry / tp1
- spx500 v2b paper: entry / tp1 / runner_stop

### Stream / bleed
- Several OANDA + paper demos: HTTP 429 / timeout / stream ERROR — heartbeats advancing → recovered reconnect noise
- Open OANDA locals match demo instrument (NAS100 / SPX500) — **no foreign-symbol bleed in open rows** at this check (midday bleed concern not reproduced)

### Verdict
Daemons up. Paper v2b / ST+PMC / prior-opposed fill paths look adherent.
**Watch:** NAS100 + SPX500 v2b OANDA stop-only (missing resting TPs) after re-entry.

### Midday → evening delta
- Midday US30 3R OANDA open-without-brackets: **not present** at 18:35 (all other demos flat locally; no open-without-working-order)
- Midday instrument bleed in open rows: **cleared** at 18:35
- New: v2b OANDA NAS100 + SPX500 stop-only after re-entry


---

## 2026-08-14 — morning (~2026-08-14 11:47 UTC)

Sources: `EMAIL_ADHERENCE_2026-08-14.txt`, `ADHERENCE_INVENTORY_TODAY.csv`,
`live/state/_oanda_live_sim_reconcile/summary.json`

### Inventory
- demos with pidfile: 35 — alive 35 / dead 0
- PROGRESS stale >20m: none
- open without any working order: none
- stop-only opens: none
- foreign-symbol bleed in open rows: none
- fills today: none (quiet pre-cash)

### Expected opens (not flags)
- `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_paper`: qty=1, runner_stop+target (post scale-out)

### Prior flags closed
- Aug 13 NAS100/SPX500 v2b OANDA stop-only: **cleared** (flat after Aug 13 eod_close)
- Aug 13 midday US30 3R OANDA open-without-brackets: still **cleared**

### Notes
- `usdjpy_monday_or_ungated_oanda`: heartbeat `open_positions=1` vs empty local positions/orders — counter drift; live↔sim MATCH
- `eurusd_v2b_ungated_oanda` / `us30_v2b_ungated_oanda`: intentionally stopped (no pidfile)
- Overnight 429/timeout stream noise — recovered

### Live↔sim
- 18/19 MATCH on OANDA inventory
- MISMATCH only on stopped `eurusd_v2b_ungated_oanda` (historical latency/smoke class)

### Verdict
Adherence good. Active books executing as expected; Aug 13 watch items cleared.


---

## 2026-08-14 — evening post-close (~01:35 UTC / 21:35 EDT)

Sources: `EMAIL_ADHERENCE_2026-08-14_evening.txt`, `ADHERENCE_INVENTORY_2026-08-14_evening.csv`,
`live/state/_oanda_live_sim_reconcile/summary.json`

### Inventory
- demos with pidfile: 35 — alive 35 / dead 0
- open without any working order: none
- stop-only opens: none
- foreign-symbol bleed in open rows: none
- PROGRESS stale >20m: 6 (4 OANDA hung + 2 paper v2b post-cash)

### FLAGs
| Severity | Issue | Status at write |
|----------|-------|-----------------|
| FLAG | Four OANDA streams hung ~4h after 429 reconnect (US30 MonOR, USDJPY MonOR, NAS100 v2b, SPX500 v2b) — pid alive, logs frozen ~17:16 EDT | open |
| FLAG | live↔sim: `nas100_v2b_ungated_oanda` / `spx500_v2b_ungated_oanda` missed today's sim entries (live fills stuck at Aug 13 eod) | open |
| FLAG | live↔sim: `nas100_hourly_st_pmc_sl50_tp150_3r_oanda` missed sim/paper entry (~15:00–15:14); paper filled entry+stop | open |
| FLAG | Orphan protective stops qty=3 on flat NAS100/SPX500 v2b OANDA | open |

### Expected opens (not flags)
- `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_paper`: qty=1, runner_stop+target

### Fill-reason mix (paper today)
- nas100 v2b: entry / wide_stop / tp1 / eod_close
- spx500 v2b: entry / wide_stop / tp1 / tp2 / eod_close
- nas100 ST+PMC 3R: entry / stop

### Live↔sim
- 15/19 MATCH; MISMATCH: stopped eurusd_v2b + three active books above
- Morning 18/19 MATCH → evening regression on today's cash session

### Verdict
Paper adherent post-close. OANDA weaker: hung streams + missed NAS/SPX v2b and NAS100 3R signals.


---

## 2026-08-14 — remediation (~02:15 UTC / 22:15 EDT)

Sources: this section; `EMAIL_ADHERENCE_2026-08-14_remediation.txt`;
`live/demo/__init__.py` (`next_stream_backoff`)

### Actions taken
1. **Cancelled orphan protective STOPs** on flat NAS100/SPX500 v2b OANDA (broker + local `orders.csv`). Broker now: **0 open trades, 0 pending STOP**.
2. **Stopped 429-hammering hung streams**, cooled ~3m, then **stagger-restarted**:
   - `usdjpy_monday_or_ungated_oanda` → STREAM connected + heartbeat (weekend FX quiet after 1 tick — expected)
   - `us30_monday_or_m3_s3_r2_half_oanda` → STREAM connected + heartbeat
3. **NAS100/SPX500 v2b OANDA left STOPPED overnight** (cash closed; reconnect 429 risked knocking Monday OR offline again). **Restart before Mon RTH.**
4. **Code:** `next_stream_backoff()` — HTTP 429 uses ≥120s step and ≤300s ceiling (wired into Monday OR OANDA + v2b OANDA common). Prevents 60s reconnect stampede.

### FLAG status
| Issue | Status |
|-------|--------|
| Four hung OANDA streams | **closed** for Monday OR; v2b OANDA intentionally stopped overnight |
| Orphan v2b protective stops | **closed** (broker STOP=0) |
| live↔sim missed today's NAS/SPX v2b + NAS100 3R entries | **acknowledged historical** — cannot replay; streams healthy going forward |

### Inventory after fix
- pidfile demos: **33 alive** (was 35; −2 v2b OANDA overnight stop)
- Broker: flat, no orphan STOPs
- Core FX overnight: USDJPY Monday OR + Asia-range OANDA up

### Verdict
Ops remediation complete. Monday OR OANDA recovered; orphans cleared; 429 backoff hardened. Restart NAS/SPX v2b OANDA Monday before cash open.

---

## 2026-08-14 — post-remediation recheck (~02:22 UTC / 22:22 EDT)

Sources: `ADHERENCE_INVENTORY_2026-08-14_post_remediation.csv`;
`EMAIL_ADHERENCE_2026-08-14_recheck.txt`; broker practice API

### Recheck
| Check | Result |
|-------|--------|
| Broker open trades | **0** |
| Broker pending STOP | **0** (75 pending LIMIT = ST+PMC runner/3R resting entries — expected) |
| Monday OR OANDA (USDJPY + US30) | alive, heartbeats ~8m after restart; weekend quiet ticks expected |
| NAS/SPX v2b OANDA | **no pidfile** (intentional overnight stop) |
| NAS/SPX v2b OANDA local working orders | **0** |
| Asia-range OANDA | heartbeat fresh |
| pidfile demos | **33 alive / 0 dead**; stale>20m = 2 paper v2b post-cash (expected quiet) |
| `next_stream_backoff` | present in `live/demo/__init__.py` (≥120s / ≤300s on 429) |

### FLAG closure (evening → now)
| Evening FLAG | Status |
|--------------|--------|
| Four hung OANDA streams | **closed** (Mon OR recovered; v2b OANDA stopped overnight) |
| Orphan v2b protective STOPs | **closed** |
| live↔sim missed cash entries | **historical only** — not replayable |

### Verdict
Remediation holding. No further ops action tonight. **Monday AM:** restart NAS100 + SPX500 v2b OANDA before cash open.
