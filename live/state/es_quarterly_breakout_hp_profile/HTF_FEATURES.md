# ES quarterly breakout — HTF features (causal asof entry)

Applied to the **quarterly range breakout** broker-like tape (n=60).

| Feature | Col | Buckets | Definition |
|---------|-----|---------|------------|
| Yearly ORB direction | `yor_dir` | `yor_up` / `yor_down` / `yor_inside` / `yor_both` / `yor_na` | Jan–Mar H/L OR; ready Apr 1. |
| Monthly OR direction | `mor_dir` | `mor_up` / `mor_down` / `mor_inside` / `mor_both` / `mor_na` | First 3 sessions of month. |
| Prior quarter type | `prior_q_type` | `q_inside` / `q_break_up` / `q_break_down` / `q_break_both` / `q_na` | Prior quarter vs its prior H/L. |
| Weekly ATR vs trade | `w_atr_align` | `w_atr_aligned` / `w_atr_opposed` / `w_atr_na` | Weekly ATR SuperTrend (14, ×3). |

Min bucket N=8. Shortlist coverage 5–55%; HTF dual-lift tags force-included for nulls.
