---
name: potions-oanda-pl-attribution
description: >-
  Attributes OANDA practice account balance and realized PL from transaction
  history (fills by instrument / exit reason, financing, deposit bridge).
  Use when explaining wins/losses behind balance or resettablePL, PL
  attribution, which instruments made money, or oanda-pl-attribution.
---

# OANDA practice PL attribution

Shared **practice** account. Explains whether a big number is **balance** vs
**trading PnL**, then breaks realized ORDER_FILL `pl` by instrument and exit
reason.

Read-only. Does **not** place/cancel/flatten. Practice only.

## When to use

- User quotes a balance-like figure (e.g. `100895`) and asks what won/lost
- “Where did practice PnL come from?” / by instrument / stops vs limits
- After a stretch of OANDA demos, before or after `potions-demo-status`

Not for open-position CSV repair → `potions-oanda-reconcile`.  
Not for live vs StrategyPlugin tape → `potions-oanda-live-sim-reconcile`.

## Run

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
set -a && source live/demo/.env && set +a   # never print tokens

python3 -m potions.live.cli oanda-pl-attribution --email
# or: python3 -m potions.live.demo.oanda_pl_attribution --email
```

Always pass `--email` when you run this for the user (writes hub email body + Resend).

## Artifacts

Under `live/demo/oanda_practice_snapshot/`:

| File | Role |
|------|------|
| `PL_ATTRIBUTION.md` | Human summary (balance bridge + fill tables) |
| `PL_ATTRIBUTION.json` | Machine summary + top wins/losses |
| `EMAIL_PL_ATTRIBUTION.txt` | Same body as emailed |
| `transactions_all.json` | Raw tx dump for follow-up |

## How to answer the user

1. **Balance ≠ trading PnL.** If they quote ~NAV/balance, say so first.
2. **Balance bridge** (prefer broker fields):
   - `start_deposit + resettablePL + financing ≈ balance`
   - Typical start: first `TRANSFER_FUNDS` (~$100k on this practice book)
3. **Instrument / exit attribution** (prefer ORDER_FILL `pl`):
   - Sum by instrument (tags are often empty on fills)
   - Wins vs losses count/USD; stops vs limits/markets
   - Top wins / top losses
4. Note **open** unrealized separately (not in resettablePL).

## Caveats (do not hide)

- Use `transaction.range(..., fromID=, toID=)` in chunks — bare `from`/`to` fails on this v20 client.
- OANDA transaction IDs can have **gaps**; missing IDs return empty. Then
  `sum(fill PL) ≠ resettablePL`. Prefer broker fields for the balance bridge;
  fill PL for “which book / exit type.”
- Shared account: one instrument can be touched by multiple demos (v2b + ST+PMC).
  Attribute by instrument unless `clientExtensions.tag` is present.

## Safety

- Practice only (`OANDA_ENV=practice`); driver refuses other envs
- Never print `OANDA_TOKEN` or `.env` contents
- No emergency flatten from this skill

## Related skills

- `potions-oanda-reconcile` — snapshot + `positions.csv` repair
- `potions-demo-status` — heartbeats / open inventory
- `potions-oanda-live-sim-reconcile` — live fills vs Engine+PaperBroker on demo bars
- `potions-job-email` — completion email pattern
