# Season / DOW sit-out scan — other instruments + gold month counts

**Method:** trade-equity on existing StrategyPlugin fills (USDJPY tuneup cores; EUR/GBP/AUD Phase 1; XAU **current core**). Screening only for FX — not locked without a fresh broker run.

## Gold core — how often we trade each month

Book: `M2_S2_R3` + sitout +100 + skip Jul/Sep/Dec · **n=2909** trades · 2003-05 → 2026-03 · 24 calendar years in span.

| Month | Trades | % of book | Mean trades / year | Years with ≥1 trade | WR% | Net pts |
|---:|---:|---:|---:|---:|---:|---:|
| 1 | 545 | 18.7% | 22.7 | 23 | 28.1 | +1352 |
| 2 | 277 | 9.5% | 11.5 | 23 | 33.9 | +307 |
| 3 | 240 | 8.3% | 10.0 | 23 | 32.5 | +986 |
| 4 | 246 | 8.5% | 10.3 | 22 | 32.5 | +355 |
| 5 | 381 | 13.1% | 15.9 | 23 | 32.0 | +1370 |
| 6 | 340 | 11.7% | 14.2 | 23 | 30.6 | +384 |
| **7** | **0** | **0%** | **0** | **0** | — | 0 |
| 8 | 305 | 10.5% | 12.7 | 23 | 28.9 | +389 |
| **9** | **0** | **0%** | **0** | **0** | — | 0 |
| 10 | 303 | 10.4% | 12.6 | 23 | 31.0 | +393 |
| 11 | 272 | 9.4% | 11.3 | 23 | 31.2 | +394 |
| **12** | **0** | **0%** | **0** | **0** | — | 0 |

**Read:** In active months you typically get **~10–23 trades per year** (Jan heaviest ~23/yr; spring/fall ~10–13/yr). Jul/Sep/Dec are hard-zero by design. DOW: Tue carries most trades/net; Fri highest WR but least size.

## Other instruments — worth sitting out?

Copying gold’s **Jul/Sep/Dec** onto FX is **bad or flat**, not good:

| Pair | Tag | Jul/Sep/Dec ΔN/S | Notes |
|---|---|---:|---|
| USDJPY | M2_S3_R1 | **−4.57** | Hurts badly (Dec is a *good* JPY month) |
| USDJPY | M2_S3_R2 | **−4.79** | Same |
| EURUSD | M1_S2_R2 | +0.26 | Near noise |
| GBPUSD | M1_S1_R2 | +0.59 | Mild; Dec soft on GBP |
| AUDJPY | M1_S2_R2 | **−1.27** | Hurts (Jul/Dec strong on AUDJPY) |

### Pair-specific soft months (fill-proxy best among cov≥50%)

| Pair | Soft months (screening) | Best screen rule | ΔN/S proxy | Δnet | Cover |
|---|---|---|---:|---:|---:|
| **USDJPY** R1/R2 | **Aug + Sep** | skip Aug+Sep | +3.8 / +2.7 | +59 / +61 pts | ~82% |
| **EURUSD** | Feb, Aug, Nov | skip those 3 | +1.28 | +0.33 | 75% |
| **GBPUSD** | Dec, Feb (mild); Wed soft | skip Wed *or* Dec+Feb | +1.3 / +0.6 | tiny | ~75–84% |
| **AUDJPY** | Aug, Jun, May (, Apr) | skip Aug+Jun+May | +1.9 | +39 | 75% |

**DOW:** No instrument wants to skip Tue (main profit day). Fri is mixed (high WR, small net); GBP Wed slightly soft; AUD Fri slightly soft — not strong enough alone to lock without broker.

## Verdict

1. **Gold:** season blackout working as designed; ~11–23 trades/month-year in the nine open months; Jan/May dominate frequency and dollars.
2. **Do not** transplant Jul/Sep/Dec to FX.
3. **Interesting FX candidates (not locked):** USDJPY skip **Aug+Sep**; AUDJPY skip late-spring/summer soft block; EUR soft Feb/Aug/Nov. These need StrategyPlugin broker audits before core.

Artifacts: `live/state/monday_or_phase2/season_scan/`
