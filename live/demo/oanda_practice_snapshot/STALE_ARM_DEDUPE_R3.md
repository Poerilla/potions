# OANDA stale-arm cleanup round 3 — 2026-08-21

Time: 2026-08-21T16:07:26Z UTC
Account: practice `101-002-39860312-003`
Hub: live/demo/oanda_practice_snapshot/

## What we found

US30 ST+PMC 3r (`-003`) stacked hourly entry LIMITs: heartbeats `orders=1→5`.
Root cause: `StrategyContext.strategy_open_orders` only treated `submitted` /
`partially_filled` as open; OANDA rests are `working`, so refresh never saw
priors and armed a new LIMIT each hour.

Note: `account.pendingOrders` was empty while `order.list_pending` / `order.get`
still showed PENDING ids 5–8 + 11.

## What we did

- Patched `OPEN_ORDER_STATUSES` (+ RiskManager / ST+PMC / London prior-opposed helpers).
- Stopped daemon; cancelled stale remote LIMITs **8,7,6,5**; kept **11** @ 52945.2 (t42 refreshed).
- Local `orders.csv`: marked [] cancelled; kept `ord_0fc075855acd`.

## Stance

Account back to **1** intentional US30 arm. Daemon restart required to load patch
so stacking cannot recur.

Artifacts: `STALE_ARM_DEDUPE_R3.json`
