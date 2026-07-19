# XAUUSD / XAGUSD — futures-style strategy gambit

Histdata 1m from `fx/raw/` (2003-05 → 2026-03), converted per `fx/METADATA.md`.
Engine + PaperBroker, 1-tick slip. Point values: **XAUUSD $100/pt**, **XAGUSD $1000/pt**.

**2026-07-19 data fix:** 25 XAGUSD 1m bars on 2011-01-20 were ~100× too high; divided by 100 and re-ran all silver stages.

**2026-07-19 v2b completeness:** prior-opposed S_1_1_3 gated by ST+PMC 25/75 (2015+ RTH, MA50>MA150 regime) — fails on both metals (same as AUDJPY/EURUSD).

| Pair | Family | Strategy | Trades | Net | Stress DD | **N/S** |
|---|---|---|---:|---:|---:|---:|
| XAUUSD | yearly_orb | Yearly ORB scaleout3 | 91 | $541,254 | $-47,903 | **11.30** |
| XAGUSD | yearly_orb | Yearly ORB scaleout3 | 89 | $121,185 | $-19,508 | **6.21** |
| XAUUSD | yearly_orb | Yearly ORB scaleout3 20% range-close | 54 | $407,982 | $-86,821 | **4.70** |
| XAUUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r_ma_bull_prior | 353 | $202,746 | $-61,325 | **3.31** |
| XAUUSD | atr_st | ATR daily 3-initial 10-max | 200 | $918,830 | $-390,893 | **2.35** |
| XAUUSD | hourly_st_pmc | ST+PMC sl40_tp120_3r | 269 | $231,363 | $-100,799 | **2.30** |
| XAUUSD | atr_st | ATR daily ladder 1/1/2/2/2 10-max | 200 | $561,150 | $-256,769 | **2.19** |
| XAUUSD | monthly_orb | Monthly ORB restricted scaleout3 | 317 | $243,868 | $-123,102 | **1.98** |
| XAGUSD | atr_st | ATR daily ladder 1/1/2/2/2 10-max | 153 | $256,057 | $-133,837 | **1.91** |
| XAGUSD | atr_st | ATR daily 3-initial 10-max | 153 | $322,523 | $-177,396 | **1.82** |
| XAGUSD | yearly_orb | Yearly ORB scaleout3 20% range-close | 59 | $82,079 | $-46,474 | **1.77** |
| XAUUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r | 487 | $105,108 | $-71,425 | **1.47** |
| XAGUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r_ma_bull_prior | 179 | $44,950 | $-34,813 | **1.29** |
| XAUUSD | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 630 | $247,166 | $-194,794 | **1.27** |
| XAGUSD | atr_st | ATR weekly 2-initial / 3-add / 6-max | 57 | $387,539 | $-322,566 | **1.20** |
| XAGUSD | hourly_st_pmc | ST+PMC sl40_tp120_3r | 100 | $31,656 | $-41,341 | **0.77** |
| XAUUSD | atr_st | ATR weekly 2-initial / 3-add / 6-max | 68 | $198,654 | $-351,182 | **0.57** |
| XAGUSD | hourly_st_pmc | ST+PMC sl25_tp75_3r | 200 | $28,650 | $-49,922 | **0.57** |
| XAUUSD | monthly_fbo | FBO 1_1_3 base | 152 | $108,457 | $-191,724 | **0.57** |
| XAUUSD | monthly_fbo | FBO 1_1_3 atr80 | 120 | $62,605 | $-173,000 | **0.36** |
| XAGUSD | monthly_orb | Monthly ORB restricted scaleout3 | 294 | $-6,365 | $-91,385 | **-0.07** |
| XAGUSD | monthly_fbo | FBO 1_1_3 atr80 | 128 | $-7,392 | $-33,044 | **-0.22** |
| XAGUSD | monthly_orb | Monthly ORB restricted scaleout3 boundary-stop entry | 639 | $-40,107 | $-139,148 | **-0.29** |
| XAGUSD | monthly_fbo | FBO 1_1_3 base | 154 | $-67,760 | $-141,739 | **-0.48** |
| XAGUSD | v2b_prior_opposed | v2b OCO prior-opposed S_1_1_3 (ST+PMC gate) | 67 | $-55,884 | $-63,485 | **-0.88** |
| XAUUSD | v2b_prior_opposed | v2b OCO prior-opposed S_1_1_3 (ST+PMC gate) | 186 | $-332,540 | $-345,623 | **-0.96** |

## Takeaways

1. **Yearly ORB scaleout3 wins both metals** — XAU N/S **11.3**; XAG N/S **6.21** (post-fix).
2. **Gold ST+PMC MA-bull** is the best metals intraday sleeve (N/S **3.31**).
3. **Monthly FBO does not transfer** (XAU ≤0.57; XAG negative).
4. **v2b prior-opposed fails** — XAU −$333k / N/S **−0.96**; XAG −$56k / N/S **−0.88** (AUDJPY was −0.95).
5. Silver ATR family is usable post-fix (N/S 1.2–1.9) but far behind yearly ORB.

Cross-universe top-4: `../fx_metals_top4_report/SUMMARY.md`.
Driver: `live/metals_futures_strats_sweep.py` (stages: daily / stpmc / fbo / **v2b**).
