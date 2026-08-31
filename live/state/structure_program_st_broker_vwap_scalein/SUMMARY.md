# Structure-program ST — broker-like replay

Plan **vwap_scalein** risk=8 via StrategyPlugin `structure_program_st` + Engine/PaperBroker.

**Rules:** spaced session-VWAP limits inside active structure (5×3ct, ≤1 slice per
15m); SL at structure extreme; re-arm only after 15m close back inside after a
structure stop-out; ladder 5@+25→±12 / 5@+50 / 5@+200; fav ST→BE; RTH EOD flatten.

ST-flip mode: **fav_be** (min_bars=0) · entry_mode: **touch** · signals: **internal**

| market   | instrument   | plan         |   risk_pts |   risk_price | slug               |   sessions |   trades |   units |      net_usd |   closed_dd_usd |   intrabar_stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |
|:---------|:-------------|:-------------|-----------:|-------------:|:-------------------|-----------:|---------:|--------:|-------------:|----------------:|-------------------------:|------------------:|---------------:|----------------:|
| nq       | NQ           | vwap_scalein |          8 |            8 | nq_vwap_scalein_r8 |       2011 |      267 |     909 | -1.11202e+06 |    -1.11919e+06 |             -1.06638e+06 |             -1.04 |          12.54 |           0.044 |

**FAIL** vs promotion (TRL-2026-00086). Analytic counterpart:
`live/state/structure_program_st/vwap_scalein/` (−$6.44M PF 0.171).
Family stance: PARKED — see `../structure_program_st/RESEARCH_PATH.md`.
