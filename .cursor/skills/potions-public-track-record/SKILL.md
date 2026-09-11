---
name: potions-public-track-record
description: >-
  Exports sanitized public GitHub Pages tear sheets (FX Momentum,
  FX Intraday Trend, Index Momentum) from sleeve fills + research hubs, never
  account NAV. Use when updating poerilla.github.io/fx-momentum-track,
  public track record, tear sheets, practice vs backtest charts, or the daily
  Pages cron.
---

# Public track record / tear sheets (GitHub Pages)

**Pages:** https://poerilla.github.io/fx-momentum-track/  
**Public repo:** `/home/tester/fx-momentum-track` (`Poerilla/fx-momentum-track`)  
**Private exporter:** `live/public_track_record/`

## Hard rules

1. **Sleeve PnL only** — LIVE/SIM charts come from each demo’s local `state/fills.csv` (instrument + `strategy_id`). **Never** OANDA account NAV, balance, resettablePL, or account-wide transaction history.
2. **No leaks** — no instruments, pairs, session names, plugin ids, account ids, OANDA URLs, hub paths, mechanic words (`breakout`, …), sizing jargon, SPY/benchmark overlays, or internal Net/Stress language.
3. **LIVE/SIM ≠ BACKTEST** — visually separated sections with explicit windows. Never blend series on one chart.
4. **No size-ups on the public path** — growth of $100,000 additive (flat size). Size-up math stays private/research-only.
5. **Allocator metrics** — CAGR, vol, Sharpe/Sortino, max DD, Calmar, win rate, profit factor, monthly return grid, drawdown chart. Skip research-only diagnostics.
6. **Email** on cron failure always; success email when pushed or `--email`.

## Tab map (private → public name)

| Public tab | Demo sleeve | Research tape |
|---|---|---|
| FX Momentum | `usdjpy_asia_range_london_oanda` | Asia filtered `unit_trades` |
| FX Intraday Trend | `usdjpy_monday_or_ungated_oanda` | Monday OR `M2_S3_R1` research fills |
| Index Momentum | `nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda` | Clean-break 1mfill `unit_trades` |

## Manual refresh

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
./scripts/update_public_track_record.sh --email
```

## Page shape

Each tab is a mini tear sheet: overview → LIVE/SIM equity + KPIs → BACKTEST equity + drawdown + KPIs → monthly grid → yearly → assumptions/disclosures.

## Related

- `potions-demo-status` — daemon health (not public metrics)
- `potions-oanda-pl-attribution` — account PL (do **not** feed into public page)
- `potions-job-email` — notify on failure / push
