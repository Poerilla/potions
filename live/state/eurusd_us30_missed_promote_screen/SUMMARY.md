# EURUSD / US30 missed promote screen

Dropped live ungated v2b daemons (paper+OANDA) for EURUSD and US30 (2026-08-11).

Filter contract: calendar-month blackout (`neg_frac_years≥0.55` & mean yr net&lt;0) + shadow roll50 on **unfiltered** campaign nets
(WR floor **22%** / PF≥1 for ST+PMC; WR≥40% / PF≥1 for Monday OR / London v2b).

| Book | Sym | Unfilt N/S | Filt N/S* | Skip months | Screen | Demo |
|---|---|---:|---:|---|---|---|
| EURUSD ST+PMC 50/150 fair 3R | EURUSD | 3.01 | 7.23 | 6,8 | **promote** ×1 | **paper+oanda UP** (full) |
| EURUSD ST+PMC 50/150 2R→10R | EURUSD | 1.80 | 3.41 | — | promote → **half** (concentration) | **paper+oanda UP** (½) |
| US30 Monday OR M3_S3_R2 (max 3/wk) | US30 | 1.85 | 2.08 | 9 | promote → **half** | **paper+oanda UP** (½, Sep skip) |
| EURUSD Monday OR M1_S2_R2 (Phase 2) | EURUSD | 1.74 | 1.16 | 8 | **paper_half** | **paper UP** (½, Aug skip; no OANDA) |
| US30 London prior-opposed S_1_1_3 | US30 | 6.23 | 10.23 | 2 | half_size | **deferred** (thin/concentrated; live ST feed) |
| US30 London 4h OR S_1_1_1 | US30 | 1.57 | 3.46 | 2,6 | half_size | **reject** (575 roll PF&lt;1 windows) |
| US30 Monday OR M3_S3_R3 | US30 | 1.88 | 0.24 | 1 | half_size | **reject** (filt N/S 0.24) |

\* Filtered N/S = filtered net / |closed-equity DD| on taken campaigns.

## Final demo decisions (post deep-check)

- **EURUSD ST+PMC 50/150 fair 3R** — full paper+OANDA. Offline Jun/Aug+roll lift N/S 3.01→7.23; live plugin does not yet sit out months (base book already N/S 3.01).
- **EURUSD ST+PMC 2R→10R** — half paper+OANDA (top-10 winners ≈172% of net).
- **US30 Monday OR M3_S3_R2** — half paper+OANDA + `skip_entry_months=[9]`.
- **EURUSD Monday OR M1_S2_R2** — half paper-only + Aug skip (Phase 2 sub-period FAIL).
- **US30 London prior-opposed** — research only for now (N/S high but 2021–25 only, top-10 ≈66% of net; needs live ST event feed for prior gate).
- **US30 London 4h / M3_S3_R3** — do not demo.

CLI: `demo-eurusd-hourly-st-pmc-{paper,oanda}`, `demo-eurusd-hourly-st-pmc-2r10r-{paper,oanda}`,
`demo-us30-monday-or-{paper,oanda}`, `demo-eurusd-monday-or-paper`.

Promote package email: `PROMOTE_PACKAGE/EMAIL.html`.
