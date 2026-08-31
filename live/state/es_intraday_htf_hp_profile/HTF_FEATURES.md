# ES HTF features (causal asof entry)

Added for ES broker-like HP profiling. All labels use **completed** daily/weekly bars only
(shifted +1 session for asof).

| Feature | Col | Buckets | Definition |
|---------|-----|---------|------------|
| Yearly ORB direction | `yor_dir` | `yor_up` / `yor_down` / `yor_inside` / `yor_both` / `yor_na` | Jan–Mar high/low OR; ready Apr 1. State from YTD extremes + prior close vs OR. |
| Monthly OR direction | `mor_dir` | `mor_up` / `mor_down` / `mor_inside` / `mor_both` / `mor_na` | First 3 sessions of calendar month. Ready after 3rd bar close. |
| Prior quarter type | `prior_q_type` | `q_inside` / `q_break_up` / `q_break_down` / `q_break_both` / `q_na` | Completed prior quarter vs *its* prior quarter H/L. Known at prior quarter end. |
| Weekly ATR vs trade | `w_atr_align` | `w_atr_aligned` / `w_atr_opposed` / `w_atr_na` | Weekly ATR SuperTrend (14, ×3) on W-FRI bars; align = bull+long or bear+short. |

## Coverage note

Several HTF buckets exceed the 5–35% HP shortlist coverage band (e.g. `yor_up` ~57%,
`q_break_up` ~77% on prior-opposed). They remain **diagnostic** — size-up shortlist still
uses the usual families (ST-age, calendar, prior-RTH). HTF pairs were still sent through
the 1.25× null suite under `es_intraday_htf_hp_nulls/`.
