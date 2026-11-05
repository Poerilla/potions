# OANDA orphan LIMIT mass-cancel — 2026-08-18

**Incident id:** `2026-08-18_oanda_orphan_limit_mass_cancel`  
**Cancelled at:** `2026-08-18T16:34:18Z` (UTC)  
**Logged at:** `2026-08-18T16:36:11Z`  
**Account:** practice `101-002-39860312-001`

## What

Cancelled **53** pending broker orders while the account was **flat**
(open trades/positions = 0). After cancel: **pending_left=0**.

| Instrument | Count |
|---|---:|
| NAS100_USD | 22 |
| US30_USD | 31 |

Types: {'LIMIT': 52, 'STOP': 1}

Also cancelled MonOR bare protective pair **1610 STOP** + **1611 LIMIT** (no onFill brackets).

## Local CSV clears

- `nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda`: 6 working → cancelled
- `us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda`: 27 working → cancelled
- `us30_monday_or_m3_s3_r2_half_oanda`: 2 working → cancelled

## Why (same-day context)

ST+PMC resting entry LIMITs (classic SL=50 / TP∈{{150,300,1500}} onFill) survived on the
shared practice account after local cancels that did not reliably ACK remote (pre
remote-first cancel fix). Containment was in **shadow**, so `orphan_protective`
only logged would-cancel. Untagged fills were not claimed by demos → orphan PnL.

Same day code: remote-ack-before-local cancel; containment email → NY EOD digest.

## If orphans recur today

1. `python3 -m potions.live.cli oanda-practice-sync` → pendingOrders
2. Diff new order ids against `ORPHAN_LIMIT_CANCEL.json` → `oanda_order_ids`
3. Per demo: `state/events/oanda_order_events.jsonl` look for
   `cancel_requested` / `remote_ack_before_local` / `cancel_local_only_no_remote` /
   `network_order_error` with `local_still_open`
4. `state/containment_email_digest.json` + `PROGRESS.log` `orphan_protective`
5. This hub + `CHANGE_LOG.md` entry 2026-08-18

## Files

- [`ORPHAN_LIMIT_CANCEL.json`](ORPHAN_LIMIT_CANCEL.json) — full id/price/units list
- [`ORPHAN_LIMIT_CANCEL_LOCAL.json`](ORPHAN_LIMIT_CANCEL_LOCAL.json)
- [`ORPHAN_LIMIT_CANCEL_META.json`](ORPHAN_LIMIT_CANCEL_META.json)
