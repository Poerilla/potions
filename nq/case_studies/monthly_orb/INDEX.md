# NQ monthly ORB studies

NQ monthly opening-range research artifacts.

- Daily-close breakout scaleout4: [MONTHLY_ORB_DAILY_CLOSE_SCALEOUT4.md](MONTHLY_ORB_DAILY_CLOSE_SCALEOUT4.md)
- Restricted stop-limit cycle: [MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md](MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE.md)
- Restricted stop-limit cycle charts: [restricted_stop_limit_cycle/INDEX.md](restricted_stop_limit_cycle/INDEX.md)
- Restricted stop-limit cycle short: [MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md](MONTHLY_ORB_RESTRICTED_STOP_LIMIT_CYCLE_SHORT.md)
- Restricted stop-limit cycle short charts: [restricted_stop_limit_cycle_short/INDEX.md](restricted_stop_limit_cycle_short/INDEX.md)
- Overlap-range breakout study: [MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT.md](MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT.md)
- Overlap-range **MAE vs stop + 2-lot runner** sweep: [MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md](MONTHLY_ORB_OVERLAP_RANGE_BREAKOUT_SENSITIVITY.md) (`python scripts/monthly_orb_overlap_range_breakout.py --sensitivity`)
- Overlap-range breakout charts: [overlap_range_breakout/INDEX.md](overlap_range_breakout/INDEX.md)
- Yearly monthly OR rail charts: [monthly_orb_yearly_range_lines/INDEX.md](monthly_orb_yearly_range_lines/INDEX.md)
- Restricted scaleout3 charts: [baseline_restricted_scaleout3/INDEX.md](baseline_restricted_scaleout3/INDEX.md)

Daily-close scaleout4 summary:

- Entry at first daily close outside the monthly OR, 4 units: 1 off halfway to TP1, 2 off at TP1, 1 off at TP2, close all before TP1 on a daily close back inside, and move the runner stop to the breakout-side range boundary after TP1.
- NQ result: **181 trades**, **$231,148** net, **-$195,698** max DD, **51.4%** win rate, **1.30 PF**.
- Long side carried the edge: **$239,998** long net versus **-$8,850** short net.

Overlap-range breakout summary:

- Treat adjacent overlapping monthly ORs as one combined range, then trade a daily-close breakout of that combined range with a midpoint stop and one measured-move target.
- NQ result: **58 trades**, **$168,755** net, **-$28,215** max DD, **56.9%** win rate, **2.24 PF**.
- Long side carried almost everything: **$166,542** long net versus **$2,212** short net.

Restricted stop-limit cycle summary:

- Long-only daily-OHLC study extending the restricted branch with stop-entry breakout attempts, false breakout close-out, top-boundary retests, and bottom-boundary reclaims.
- NQ result after allowing 2-contract top-boundary refills while a runner remains open, allowing fresh breakout attempts before a bottom-limit reclaim fills, replacing the close-back-inside/hard-stop exits with 25% daily-close thresholds, and closing top refills on any daily close at/below the OR high: **338 packages**, **$612,935** net, **-$139,060** max DD, **49.1%** win rate, **1.58 PF**.
- Most edge came from stop-breakouts and bottom-limit reclaims: stop-breakouts added **$394,820** net, bottom-limit reclaims added **$162,715** net, and top refills added **$55,400**.
- The mirrored short-only version is not viable in this form: **377 packages**, **-$99,092** net, **-$229,472** max DD, **40.8%** win rate, **0.92 PF**. Stop-breakdowns and bottom refills were modestly positive, but top-limit reclaims lost **-$176,060**.

Regenerate:

```bash
python3 potions/scripts/monthly_orb_daily_close_scaleout4.py --market nq
python3 potions/scripts/monthly_orb_restricted_stop_limit_cycle.py --market nq --charts
python3 potions/scripts/monthly_orb_restricted_stop_limit_cycle_short.py --market nq --charts
python3 potions/scripts/monthly_orb_overlap_range_breakout.py --market nq --charts
```
