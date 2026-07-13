# NQ v2b Prior-Opposed ST+PMC Full-History CSV Diagnostic

**Important:** this is **not** the battle-tested `Engine + PaperBroker` replay. The true long-history replay is blocked because `nq/raw/glbx-mdp3-20100606-20260308.ohlcv-1m.dbn.zst` is missing from the workspace. This diagnostic uses the legacy full-history NQ v2b scaleout CSV and filters rows where a same-session NQ hourly ST+PMC entry had already fired in the opposite direction before the CSV v2b fill.

- v2b source: `nq/v2d/nq_adaptive_50_150_v2b_scaleout.csv`
- ST+PMC source: `live/state/hourly_st_pmc_strategyplugin_variants_cross_market/nq/combined_state/fills.csv` / `nq_hourly_st_pmc_sl25_tp75_3r`
- ST+PMC entry event window: **2010-07-06 03:00 EDT** to **2026-03-05 12:00 EST**

| Window | Rows | First Fill | Last Fill | Net | Closed DD | Net/DD | Win % | PF | Direction Mix |
|---|---:|---|---|---:|---:|---:|---:|---:|---|
| full_csv_diagnostic | 498 | 2011-01-17 | 2026-03-02 | $320,096.00 | $-16,952.00 | 18.88 | 61.6% | 2.00 | 189 long / 309 short |
| same_start_as_broker_like_2021_03_04 | 191 | 2021-03-04 | 2026-03-02 | $208,162.00 | $-16,952.00 | 12.28 | 68.1% | 2.14 | 69 long / 122 short |

Read: use this only as a directional full-history smell test. It does not model delayed order arming, 1-tick slippage, stop gap-through, stop-first same-bar ambiguity, or the retest/miss questions that made the broker-like NQ row need execution scrutiny.

Files:

- `summary.csv`
- `matching_v2b_rows.csv`