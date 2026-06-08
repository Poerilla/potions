# MNQ Prior-Opposed ST+PMC → v2b

Complete stats and context for **MNQ hourly ST+PMC (opposite direction) gating v2b `S_1_1_3`**, from broker-like `Engine + PaperBroker + StrategyPlugin` replay and related research passes.

**Canonical state:** [`states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/`](states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/)  
**Combined-system summary:** [`summary.csv`](summary.csv) · [`paired_trade_contribution.csv`](paired_trade_contribution.csv)  
**Tracker cross-ref:** [`../../../mnq/case_studies/STRATEGY_TRACKER.md`](../../../mnq/case_studies/STRATEGY_TRACKER.md) (intraday ORB leader section)

---

## Rule

| Piece | Detail |
|--------|--------|
| **ST+PMC source** | `mnq_hourly_st_pmc_sl25_tp75_3r` (25 pt stop / 75 pt target, 3R) |
| **v2b** | `S_1_1_3` scaleout OCO: entry **5**, TP1 **1**, TP2 **1**, runner **3** |
| **Gate** | v2b arms only after a **same-session** hourly ST+PMC entry in the **opposite** direction |
| **Arming model** | **Delayed arming** — if ST+PMC fires first, v2b may still arm the opposite OR boundary later in the session (live-orderable; not a static filter on an existing tape) |
| **Regime** | Prior-day **MA50 > MA150** on MNQ daily (`use_regime_filter`) |
| **Start** | 2021-03-04 |
| **Broker realism** | 1-tick slippage, **$1.50**/closed unit, stop gap-through, stop-first same-bar ordering, OCO-collapsed risk projection |

**Implementation:** `live/v2b_prior_opposed_combined_system.py` (`prior_opposite_only`, `dynamic_sizing_events` from hourly ST+PMC fills).

**NQ note:** NQ has a dedicated broker-like folder with causal audit, robustness, and event-calendar studies under `live/state/nq_v2b_prior_opposed_stpmc_broker_like/`. MNQ uses the same gate logic via this combined-system replay; those NQ-only audits are not duplicated for MNQ here.

---

## A. Broker-like gated v2b only (primary)

Source: `summary.csv`, `unit_trades.csv`, independent `fast_intraday_audit` (2026-05-27).

### Headline

| Metric | Value |
|--------|------:|
| **Campaigns (trades)** | 353 |
| **Units** | 1,765 |
| **Net** | **$113,547.50** |
| **Closed DD** | **-$3,493.50** (summary) · **-$5,340.50** (audit equity) |
| **Intrabar stress DD** | **-$5,418.00** |
| **Net / Stress** | **20.96** |
| **Campaign win rate** | **68.56%** |
| **Campaign PF** | **2.615** |
| **Max open units** | 5 |

### Campaign distribution

| Metric | Value |
|--------|------:|
| Avg campaign | $321.66 |
| Median campaign | $199.00 |
| Best campaign | $5,830.00 |
| Worst campaign | -$2,065.00 |
| Max winning streak | 11 |
| Max losing streak | 4 |
| Return on **$7,500** ref | **~1,514%** (full window) |

### Direction (campaigns)

| Side | Campaigns | Net | Win % |
|------|----------:|----:|------:|
| **Short** | 205 | $85,959.00 | 74.15% |
| **Long** | 148 | $27,588.50 | 60.81% |

### Yearly (campaigns)

| Year | Campaigns | Units | Net | Win % | PF |
|------|----------:|------:|----:|------:|---:|
| 2021 | 77 | 385 | $26,560.00 | 72.73% | 3.63 |
| 2022 | 16 | 80 | $874.50 | 56.25% | 1.11 |
| 2023 | 74 | 370 | $16,291.00 | 67.57% | 2.34 |
| 2024 | 93 | 465 | $18,747.00 | 63.44% | 1.81 |
| 2025 | 74 | 370 | $38,097.00 | 70.27% | 3.71 |
| 2026 | 19 | 95 | $12,978.00 | 84.21% | 5.61 |

**2022 is the weak year** (flat net, PF ~1.1) — same pattern noted on NQ.

### Exit reasons (units)

| Exit | Units | Net |
|------|------:|----:|
| eod_close | 800 | +$119,194.00 |
| tp1 | 235 | +$27,796.50 |
| tp2 | 115 | +$25,649.50 |
| runner_stop | 300 | -$7,267.50 |
| wide_stop | 315 | -$51,825.00 |

### Unit-level

| Metric | Value |
|--------|------:|
| Unit win rate | 55.52% |
| Unit PF | 2.52 |
| Avg unit P&L | $64.33 |

### Audit cross-check (`fast_intraday_audit`)

| Metric | Audit | `summary.csv` |
|--------|------:|--------------:|
| Net | $113,547.50 | $113,547.50 |
| Intrabar stress DD | -$5,418.00 | -$5,418.00 |
| Closed DD | -$5,340.50 | -$3,493.50 |
| Max open units | 5 | 5 |

Net and stress DD match. Closed DD differs slightly by metric definition (equity curve vs summary field).

---

## B. Paired ST+PMC + v2b (combined-system views)

Answers whether the **prior ST leg** adds value around the gated v2b setup.

| View | Trades | Units | Net | Closed DD | Stress DD | Win % | PF | Net/Stress |
|------|-------:|------:|----:|----------:|----------:|------:|---:|-----------:|
| **v2b gated only** | 353 | 1,765 | $113,547.50 | -$3,493.50 | -$5,418.00 | 68.56% | 2.615 | **20.96** |
| **Prior ST only** (gate trades) | 353 | 353 | $1,894.50 | -$1,085.50 | -$1,085.50 | 28.61% | 1.145 | 1.75 |
| **Paired prior ST + v2b** | 353 | 2,118 | $115,442.00 | -$3,159.50 | -$6,503.50 | 68.56% | 2.676 | 17.75 |
| **Full ST + gated v2b portfolio** | 1,144 | 2,556 | $122,424.62 | -$3,397.50 | -$7,880.00 | 43.18% | 2.238 | 15.54 |

**Read:**

- Almost all edge is **v2b after opposed ST+PMC** (~$113.5k).
- The prior ST leg alone is only **+$1,894.50** (28.6% win).
- Paired net is essentially v2b plus a small ST contribution.
- Full portfolio stress is conservative (v2b stress + ST budget); overlap risk is not fully modeled in that exploratory pass.

---

## C. Unit-tape screening (discovery pass)

These rows **filter existing `S_1_1_3` campaigns** on the all-days unit tape. They do **not** model delayed arming, so trade counts are lower than the broker-like replay.

### Timing study — v2b as second signal

[`../../mnq_v2b_st_pmc_timing_study/INDEX.md`](../../mnq_v2b_st_pmc_timing_study/INDEX.md)

| Bucket | Trades | Win % | Net | Avg trade | PF |
|--------|-------:|------:|----:|----------:|---:|
| v2b base (all) | 1,384 | 53.61% | $74,441.50 | $53.79 | 1.160 |
| v2b after **aligned** ST+PMC | 132 | 53.03% | $3,774.50 | $28.59 | 1.077 |
| v2b after **prior opposed** ST+PMC | **183** | **66.12%** | **$57,668.50** | **$315.13** | **2.237** |
| v2b, no prior ST | 1,069 | 51.54% | $12,998.50 | $12.16 | 1.035 |

**Do not** use same-direction ST+PMC as a v2b size-up gate (aligned bucket underperforms base).

### Regime decomposition — `not_aligned_prior_opposed`

[`../../mnq_v2b_regime_weighting_research/INDEX.md`](../../mnq_v2b_regime_weighting_research/INDEX.md)

| Metric | Value |
|--------|------:|
| Campaigns | 183 |
| Win rate | 66.12% |
| Net | $57,668.50 |
| Reconstructed stress DD | -$5,606.50 |
| Net / Stress | **10.29** |
| PF | 2.237 |
| Avg trade | $315.13 |
| Avg MAE | -$519.03 |

### Why 183 vs 353 campaigns?

| Method | Campaigns | Net | Role |
|--------|----------:|----:|------|
| Unit-tape filter (`prior_opposed`) | 183 | $57,668.50 | How the branch was **found** |
| Broker-like delayed arming | **353** | **$113,547.50** | **Live-orderable** stats |

Use **353 / $113.5k** for promotion and capital planning; use **183 / $57.7k** as a conservative screening floor.

---

## D. vs MNQ baseline `S_1_1_3` (all regime days)

[`../../v2b_sizing_sweep/MNQ_1_1_3_STATS.md`](../../v2b_sizing_sweep/MNQ_1_1_3_STATS.md)

| Metric | All-days `1/1/3` | Prior-opposed gated |
|--------|-----------------:|--------------------:|
| Campaigns | 1,384 | **353** (~25% of regime days) |
| Net | $74,441.50 | **$113,547.50** (+53%) |
| Stress DD | -$12,372.00 | **-$5,418.00** |
| Net / Stress | 6.02 | **20.96** |
| Win % | 53.61% | **68.56%** |
| PF | 1.160 | **2.615** |
| Avg campaign | $53.79 | **$321.66** |

Trade-off: fewer days traded, much higher quality per campaign.

---

## E. NQ comparison (same gate, different market)

[`../nq/INDEX.md`](../nq/INDEX.md) · [`../../nq_v2b_prior_opposed_stpmc_broker_like/INDEX.md`](../../nq_v2b_prior_opposed_stpmc_broker_like/INDEX.md)

| Market | Campaigns | Net | Stress DD | Net/Stress | Win % | PF |
|--------|----------:|----:|----------:|-----------:|------:|---:|
| **MNQ** | 353 | $113,547.50 | -$5,418.00 | 20.96 | 68.56% | 2.615 |
| **NQ** | 352 | $1,184,585.00 | -$53,847.00 | 22.00 | 69.32% | 2.654 |

MNQ is the **small-capital expression** of the same gate; NQ has fuller robustness documentation.

---

## F. Charts and related files

| Asset | Path |
|-------|------|
| This folder INDEX | [`INDEX.md`](INDEX.md) |
| Unit trades / fills / equity | [`states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/`](states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/) |
| Paired trade log | [`paired_trade_contribution.csv`](paired_trade_contribution.csv) |
| 15m review charts (subset) | [`../../mnq_v2b_regime_weighting_research/charts/prior_opposed_15m/INDEX.md`](../../mnq_v2b_regime_weighting_research/charts/prior_opposed_15m/INDEX.md) |
| Combined 15m (ST entry → RTH close) | [`charts/combined_15m/INDEX.md`](charts/combined_15m/INDEX.md) |
| Timing study | [`../../mnq_v2b_st_pmc_timing_study/`](../../mnq_v2b_st_pmc_timing_study/) |
| Regime weighting | [`../../mnq_v2b_regime_weighting_research/`](../../mnq_v2b_regime_weighting_research/) |
| Combined MNQ + NQ table | [`../INDEX.md`](../INDEX.md) |

---

## G. Promotion read (from STRATEGY_TRACKER)

- **Research promotion candidate** on MNQ — strong Net/Stress and PF vs plain `S_1_1_3`.
- **Not** the first live target (that remains MNQ v2b **`1/0/0`** plumbing).
- **Do not** size up v2b when prior ST+PMC is **same-direction** (aligned bucket worse than base).
- Edge is mostly **v2b after failed/opposed hourly ST+PMC**, not ST+PMC itself.
- Weighted sizing rows (`2/1/3`, `3/2/3`) raise net but lower Net/Stress vs base `1/1/3` on the unit tape — treat as allocator research, not first live config.

---

## H. Regenerate

```bash
cd /home/tester/hsm/potions
python3 -m live.v2b_prior_opposed_combined_system --market mnq
```

Force rebuild: pass `--force` if the module exposes it (see `live/v2b_prior_opposed_combined_system.py`).
