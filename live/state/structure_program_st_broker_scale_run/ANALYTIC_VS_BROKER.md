# Analytic vs PaperBroker — optimism review (`scale_run`)

NQ `structure_sl_scale_run` (research tape) vs `nq_scale_run_r8` (StrategyPlugin + PaperBroker).

| | Analytic | Broker |
|--|--:|--:|
| net | **+$2.03M** | **−$103k** |
| WR (campaign) | 49.8% | 12.7% |
| trades | 325 | 228 |
| hit +22 / +50 / +200 | 50% / 39% / 20% | 14% / 8% / **1.8%** |
| median hold | 6 min | **1 min** |
| full +200 runners | 64 (+$1.74M) | 4 campaigns / 20 units |

## Where analytic is optimistic (ranked)

### 1. Different entry universe (critical)

- Analytic entry-days **241** vs broker **160**; only **70** shared.
- **171 analytic-only days** → **+$1.73M** (≈85% of analytic net). Broker never entered.
- Only ~60 trades match within 60 minutes / 20 pts; **64 analytic runners → 7** have any same day+side broker trade.
- Broker-only days (90) are roughly flat (+$4k).

The research edge is largely a **different trade set**, not the same fills with less friction.

### 2. Post-entry survival / ST handling (critical)

- Analytic: `st_be_armed` on **61%** of trades; only **23** adverse `st_flip` exits (−$19k).
- Broker: **91** `st_flip`-only campaigns, median hold **1 minute**, unit `st_flip` **−$199k** (all adverse at flatten under `fav_be`).
- Scale rate collapses because trades die before +22.

### 3. Runner monetization (critical)

- Analytic +200 exits = **+$1.74M** (85% of net), median hold **3.4 hours** (p90 ~71h).
- Broker almost never gets there (1.8% of campaigns).

### 4. Matched-path divergence (material)

On 60 matched trades: analytic **+$27k** vs broker **−$86k**. Nine analytic winners are broker losers (scales vs `risk_stop` / `st_flip` / `be_stop`).

### 5. Fill friction (secondary)

- Entry slip ~0.69 pts mean → ~**$47k**; fees ~**$10k**.
- Real for live trading, but **not** what creates the $2.1M gap.

## Not the story

Analytic is not “same signals, optimistic fills.” It is “more (and better) signals kept alive long enough to print 50/200.” Until entry parity and broker ST survival match the research path, analytic results overstate plugin edge.

Canvas: `scale-run-analytic-vs-broker` in Cursor canvases.
