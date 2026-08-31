# Quarterly ATR4 stress board — where equity growth comes from

Ladder on these books: **10 lots**, scale **2 off at +2 / +4 / +6 / +8 ATR** (`tp1`–`tp4`), then **2 residual** intended as BE → period-end `flatten`.

Board = stress/yearly names: GBPUSD, NAS100, NQ, EURUSD (best-path) + XAUUSD (family first_lower).

Artifacts: `exit_contribution_board.csv`, `campaign_runner_fates.csv`, `runner_whatif_summary.csv`.

## Verdict

1. **Growth is back-loaded.** Board-wide share of *positive* exit PnL:
   - `flatten` (EOQ runners) **30.8%**
   - `tp4` (+8 ATR) **24.9%**
   - `tp3` (+6 ATR) **19.9%**
   - `tp2` (+4 ATR) **16.0%**
   - `tp1` (+2 ATR) **8.5%**
2. **The runner is very significant** — often #1 contributor (GBPUSD, NAS100, EURUSD, XAUUSD). It is **not** mostly a break-even scratch.
3. **Taking the residual off at +6 ATR would hurt a lot** (~−$187k board-wide vs current).
4. **Capping the residual at +8 ATR** (flatten remaining when `tp4` hits; no EOQ ride) is **mixed by market**, ~−$31k board-wide — gives back big NAS100/EURUSD/XAUUSD extensions, helps NQ/GBPUSD mainly because post-`tp4` “stops” are painful.
5. **Important tape fact:** after `tp4`, many residual `stop` fills are at the **original risk stop**, not entry. So the “BE runner” is often still full residual risk — not a BE scratch. EOQ `flatten` winners are still real and large.

## Per-market contribution

| Market | Net | flatten | tp4 | tp3 | tp2 | tp1 | stop | Reach tp4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| GBPUSD | $404k | $163k (26%) | $154k | $128k | $114k | $65k | −$219k | 41% |
| NAS100 | $33k | $21k (51%) | $8k | $6k | $4k | $2k | −$7k | 33% |
| NQ | $307k | $79k (24%) | $108k | $79k | $49k | $20k | −$28k | 50% |
| EURUSD | $85k | $60k (43%) | $23k | $24k | $19k | $13k | −$54k | 25% |
| XAUUSD | $251k | $157k (37%) | $95k | $74k | $64k | $32k | −$171k | 37% |

(% = share of that market’s positive exit legs.)

## Runner fate (only campaigns that hit `tp4`)

| Market | BE-armed | EOQ flatten | “Stop” after tp4 | Flatten ATR mult (mean / med / max) |
|---|---:|---:|---:|---|
| GBPUSD | 21 | 12 | 9 | 14.4 / 12.0 / 39.8 |
| NAS100 | 3 | 3 | 0 | 43.2 / 31.9 / 78.5 |
| NQ | 4 | 2 | 2 | 21.1 / 21.1 / 28.0 |
| EURUSD | 4 | 3 | 1 | 24.4 / 23.5 / 34.4 |
| XAUUSD | 11 | 9 | 2 | 23.3 / 21.3 / 40.9 |

When flatten wins, residual often rides **well past +8 ATR** into the teens–40s ATR by quarter end. That is the main “only” source of outsized campaign PnL.

Post-`tp4` stop PnL is **not** ~0: GBPUSD ~−$1.8k avg / 2 lots; NQ ~−$10k avg / 2 lots — consistent with **original  risk stop** on the residual (fills checked: NQ `t6` entry 20765 → stop fill 20509 = initial stop).

## What-if: residual off at +8 vs +6

Replay-free counterfactual on existing unit tape:

- **Runner @ +8:** keep `tp1`–`tp4`; replace residual (`flatten`/`stop` after tp4) with same $/unit as that trade’s `tp4`.
- **Remaining @ +6:** after `tp3`, replace `tp4`+residual with that trade’s `tp3` $/unit (no +8 scale, no EOQ runner).

| Market | Actual | Runner@+8 Δ | Remaining@+6 Δ |
|---|---:|---:|---:|
| GBPUSD | $404k | **+$8k** | −$35k |
| NAS100 | $33k | −$13k | −$17k |
| NQ | $307k | **+$49k** | −$9k |
| EURUSD | $85k | −$22k | −$33k |
| XAUUSD | $251k | −$53k | −$93k |
| **Board** | **$1,080k** | **−$31k** | **−$187k** |

Interpretation:

- **+6 for residual is worse everywhere that matters** — you give up `tp4` and the big EOQ extensions.
- **+8 flat exit for residual** only looks good where post-`tp4` stops are frequent/expensive (NQ, some GBPUSD). On NAS100 / EURUSD / XAUUSD the EOQ runner *is* the edge.
- Until BE actually arms to entry, “cap at +8 when tp4 hits” is also a way to **avoid residual full-risk stop-outs** — part of why NQ what-if improves.

## What is working vs not

**Working**

- Scale ladder through **+6 and +8** (`tp3`/`tp4`) — together ~45% of positive PnL.
- **EOQ flatten on residual** after a full ladder — largest single positive bucket; mean flatten excursion ≫ +8 ATR.

**Not working / weaker**

- Assumption that residual is “mostly BE” — **false on this tape** (stops often = original risk; flatten winners are large).
- **Early scales alone (`tp1`)** — needed for partial wins, but small share of growth.
- **Cutting residual at +6** — clearly worse.
- **Blindly cutting residual at +8** — board slightly worse; kills the best runner markets.

## Practical stance

Keep current ladder (+2/+4/+6/+8) and **do not** move residual target to +6. Residual @ +8 as a *hard exit* is only interesting if you also want to kill EOQ tail risk / fix BE — and even then it is market-dependent (helps NQ, hurts XAUUSD/EURUSD/NAS100).

Separate follow-up: verify why post-`tp4` rebuild stops are not landing at entry on PaperBroker (intents after TP fills missing; residual stop fills at initial stop).
