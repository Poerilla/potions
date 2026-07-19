# EURUSD 15m ST DCA — filter sweep

Close-beyond-trail follow + fade-on-flip. Pandas path (closed-equity DD only).
Unit = 0.5 lot (PV $50k), fee $0.75/unit. Window 2015-01-01 → 2026-03-31.

| Strategy | Filter | Net | Closed DD | Net/DD | Trades | WR |
|---|---|---:|---:|---:|---:|---:|
| follow_close | week_mid_opposite | $-71,727 | $-84,126 | -0.85 | 4942 | 32.2% |
| follow_close | ma50_150_opposite | $-96,111 | $-106,390 | -0.90 | 4096 | 32.8% |
| follow_close | ma50_150_align | $-112,588 | $-123,288 | -0.91 | 4114 | 31.6% |
| follow_close | week_mid_align | $-148,908 | $-148,932 | -1.00 | 4062 | 32.5% |
| fade | week_mid_opposite | $-154,584 | $-156,230 | -0.99 | 2548 | 28.9% |
| fade | ma50_150_opposite | $-182,510 | $-183,034 | -1.00 | 2694 | 28.4% |
| fade | ma50_150_align | $-183,946 | $-186,203 | -0.99 | 2751 | 27.0% |
| fade | week_mid_align | $-205,812 | $-207,712 | -0.99 | 2894 | 26.5% |
| follow_close | none | $-208,699 | $-213,254 | -0.98 | 8210 | 32.2% |
| fade | none | $-366,457 | $-367,555 | -1.00 | 5445 | 27.7% |

Filters:
- **week_mid_align (follow):** long only below prior-week 50%; short only above.
- **week_mid_opposite (follow):** reverse of align.
- **week_mid_align (fade):** fade bullish (short) only below mid; fade bearish (long) only above.
- **week_mid_opposite (fade):** reverse.
- **ma50_150_align:** trade/fade with prior-day MA50 vs MA150 regime.
- **ma50_150_opposite:** against that regime.

`**` = net > FX baseline (~$23.5k) and Net/closed-DD ≥ 1.0 (still needs broker stress).

CSV: `/home/tester/hsm/potions/live/state/eurusd_intraday_st_dca_filters/filter_sweep.csv`
