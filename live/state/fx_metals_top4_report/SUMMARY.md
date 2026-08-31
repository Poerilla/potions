# FX + Metals — Top models report

After adding **XAUUSD/XAGUSD** and running the futures-style gambit (yearly ORB,
monthly ORB, ATR ST, hourly ST+PMC, monthly FBO). Engine + PaperBroker, 1-tick slip.
Metals: XAU PV=$100, XAG PV=$1000. Book stats on **$250k** base; JPY→USD via daily incremental USDJPY.

**Data fix:** XAGUSD 2011-01-20 had 25 one-minute bars scaled ~100×; corrected and all silver
strategies re-run (pre-fix silver yearly N/S 316 was a spike artifact).

## Top 4 by Net/Stress

**Sized yearly ORB (2026-08-16)** — current N/S leaders from [`../yearly_orb_sizing_sweep_fx_metals/SUMMARY.md`](../yearly_orb_sizing_sweep_fx_metals/SUMMARY.md):

| Rank | Pair | Strategy | Net (USD≈) | MTM stress | **N/S** | Ladder | vs `1/1/1` |
|---:|---|---|---:|---:|---:|---|---:|
| 1 | **AUDJPY** | Yearly ORB sized | ~$420k | ~$−17k | **24.87** | **4/1/1** | +9.61 |
| 2 | **XAUUSD** | Yearly ORB sized | $1,037,711 | $−67,742 | **15.32** | **4/2/1** | +4.02 |
| 3 | **XAGUSD** | Yearly ORB sized | $301,376 | $−35,143 | **8.58** | **5/2/1** | +2.36 |
| 4 | **USDJPY** | Monthly ORB FBO 1/1/3 atr80 | $93,082 | $−26,548 | **4.25** | — | — |

**Baseline `1/1/1` (charted / $250k institutional metrics below — unchanged):**

| Rank | Pair | Strategy | Net (USD) | MTM stress | **N/S** | CAGR | Sharpe | Max DD | Worst mo | Worst yr | n | WR |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | **AUDJPY** | Yearly ORB scaleout3 `1/1/1` | $193,803 | $-9,036 | **15.26** | 2.60% | **1.03** | **-2.69%** | -1.33% | -0.40% | 146 | 88.8% |
| 2 | **XAUUSD** | Yearly ORB scaleout3 `1/1/1` | $541,254 | $-47,903 | **11.30** | 5.16% | 0.76 | -10.36% | -5.60% | -0.36% | 91 | 93.8% |
| 3 | **XAGUSD** | Yearly ORB scaleout3 `1/1/1` | $121,185 | $-19,508 | **6.21** | 1.74% | 0.65 | -5.54% | -2.34% | -0.01% | 89 | 88.8% |
| 4 | **USDJPY** | Monthly ORB FBO 1/1/3 atr80 | $93,082 | $-26,548 | **4.25** | 1.39% | 0.29 | -9.00% | -4.94% | -4.23% | 156 | 50.6% |

### Notes
- **AUDJPY #1 (sized):** N/S **24.87** on `4/1/1`; banked $250k Sharpe **1.03** / max DD **−2.69%** still refer to the `1/1/1` report (`audjpy_futures_strats_sweep/best_report_yearly_orb/`).
- **XAUUSD #2 (sized):** `4/2/1` lifts N/S 11.30 → **15.32** (+$1.04M net).
- **XAGUSD #3 (sized):** `5/2/1` lifts N/S 6.21 → **8.58** (post silver-fix tape).
- **USDJPY #4:** best monthly FBO sleeve; metals FBO still fails.
- Rank 5: XAUUSD ST+PMC MA-bull N/S **3.31**.
- Deep-checks / one-pagers: `live/state/yearly_orb_sizing_sweep_fx_metals/`.

## Metals gambit full table (post silver fix)

| Pair | Family | Strategy | Trades | Net | Stress | N/S |
|---|---|---|---:|---:|---:|---:|
| XAUUSD | yearly_orb | Yearly ORB scaleout3 | 91 | $541,254 | $-47,903 | 11.30 |
| XAGUSD | yearly_orb | Yearly ORB scaleout3 | 89 | $121,185 | $-19,508 | 6.21 |
| XAUUSD | yearly_orb | Yearly ORB scaleout3 20% range-close | 54 | $407,982 | $-86,821 | 4.70 |
| XAUUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r_ma_bull_prior | 353 | $202,746 | $-61,325 | 3.31 |
| XAUUSD | atr_st | ATR daily 3-initial 10-max | 200 | $918,830 | $-390,893 | 2.35 |
| XAUUSD | hourly_st_pmc | ST+PMC sl40_tp120_3r | 269 | $231,363 | $-100,799 | 2.30 |
| XAUUSD | atr_st | ATR daily ladder 1/1/2/2/2 10-max | 200 | $561,150 | $-256,769 | 2.19 |
| XAUUSD | monthly_orb | Monthly ORB restricted scaleout3 | 317 | $243,868 | $-123,102 | 1.98 |
| XAGUSD | atr_st | ATR daily ladder 1/1/2/2/2 10-max | 153 | $256,057 | $-133,837 | 1.91 |
| XAGUSD | atr_st | ATR daily 3-initial 10-max | 153 | $322,523 | $-177,396 | 1.82 |
| XAGUSD | yearly_orb | Yearly ORB scaleout3 20% range-close | 59 | $82,079 | $-46,474 | 1.77 |
| XAUUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r | 487 | $105,108 | $-71,425 | 1.47 |
| XAGUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r_ma_bull_prior | 179 | $44,950 | $-34,813 | 1.29 |
| XAUUSD | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 630 | $247,166 | $-194,794 | 1.27 |
| XAGUSD | atr_st | ATR weekly 2-initial / 3-add / 6-max | 57 | $387,539 | $-322,566 | 1.20 |
| XAGUSD | hourly_st_pmc | ST+PMC sl40_tp120_3r | 100 | $31,656 | $-41,341 | 0.77 |
| XAUUSD | atr_st | ATR weekly 2-initial / 3-add / 6-max | 68 | $198,654 | $-351,182 | 0.57 |
| XAGUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r | 200 | $28,650 | $-49,922 | 0.57 |
| XAUUSD | monthly_fbo | FBO 1_1_3 base | 152 | $108,457 | $-191,724 | 0.57 |
| XAUUSD | monthly_fbo | FBO 1_1_3 atr80 | 120 | $62,605 | $-173,000 | 0.36 |
| XAGUSD | monthly_orb | Monthly ORB restricted scaleout3 | 294 | $-6,365 | $-91,385 | -0.07 |
| XAGUSD | monthly_fbo | FBO 1_1_3 atr80 | 128 | $-7,392 | $-33,044 | -0.22 |
| XAGUSD | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 639 | $-40,107 | $-139,148 | -0.29 |
| XAGUSD | monthly_fbo | FBO 1_1_3 base | 154 | $-67,760 | $-141,739 | -0.48 |

**Charts:** [`charts/INDEX.md`](charts/INDEX.md) — yearly ORB (24/pair), USDJPY FBO trade-months (134), XAU ST+PMC profitable (112, max 300).

Packs: `live/state/metals_futures_strats_sweep/` · `live/state/fx_metals_top4_report/` · drivers `live/metals_futures_strats_sweep.py`, `live/fx_metals_top4_charts.py`
