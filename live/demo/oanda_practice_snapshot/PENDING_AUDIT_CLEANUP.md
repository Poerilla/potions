# OANDA pending-order audit + stale-arm cleanup — 2026-08-19

Time: 2026-08-19T21:36:00Z UTC
Account: practice 101-002-39860312-001
Hub: live/demo/oanda_practice_snapshot/

## What we found

After the earlier NAS100 orphan cancels (1719 / 1756–1760 / 1767), the account
still had **24 pending** orders:

- 4× NAS100 STOP_LOSS / TAKE_PROFIT — **valid** brackets on open trades 1737/1740
  (runners book: SL−50, TPs +300 / +1500 ≈ 2R / 10R). Keep.
- 20× US30 LIMITs — all tagged + mirrored in local CSVs, so containment called
  them "armed_entry", but they were **not** paper-inline:

  Paper ST+PMC wants **one** current arm set while flat:
  - 3r: 1× entry LIMIT (SL−50 / TP+150)
  - runners: 3× ladder (entry / 2R / 10R) at one price

  Broker/local had piled up **multiple hourly re-arms** (14:00 and 20:00 price
  sets) because refresh did not fully cancel prior remote LIMITs → duplicate
  entry risk if price tagged several rests.

## What we did

Cancelled **16** stale/duplicate US30 LIMITs (tx 1778–1793).
Kept paper-inline set only:

| Keep | Book | Geometry |
|---|---|---|
| 1773 | us30 … 3r | LIMIT @53367.3  SL−50 TP+150 |
| 1774/1775/1776 | us30 … runners | LIMIT @53371.0  SL−50 / TP+150,+300,+1500 |

NAS100 +2 still owned by runners; protectives 1738–1742 untouched.
Local `orders.csv` marked cancelled for removed cids.
`oanda-practice-sync --repair-demo-positions` re-run — demo position rows ok.

Pending now: **8** (4 protective + 4 intentional US30 arms).

## How orphans / piles happen (root cause)

1. **Shared practice account** — many demos, one broker book. A flat sibling can
   still arm entries while another tag holds the same instrument (NAS100 case).
2. **Hourly refresh without reliable remote cancel** — ST+PMC re-prices each
   hour; if old LIMITs stay PENDING, you get multi-price / multi-copy arms that
   paper would have replaced with a single set.
3. **Containment was shadow + classifier FP** — intentional entries looked like
   orphans; true cross-book risk was not cancelled automatically.

## How to avoid

- Keep **cross-book entry gate** (already shipped): block new entries when the
  account already holds the instrument and this strategy is flat.
- On entry refresh: **remote-ack cancel before resubmit** (already preferred for
  refresh_entry); watch for `cancel_local_only_no_remote` in oanda_order_events.
- Stay in containment **shadow** until confident; optionally flip to `live` for
  orphan protective cancel only after armed_entry classification is stable.
- Periodic audit: `oanda-practice-sync` + compare pending count to expected
  (1 arm 3r / 3 arms runners / trade-linked SL+TP only while open).

Artifacts:
- STALE_ARM_DEDUPE.json
- PENDING_AUDIT.json
- ORPHAN_4_CANCEL.md (earlier NAS100 cancels)
- REPORT.md (post-repair sync)

Stance: account clean for paper-inline arms; NAS100 runners position protected.

