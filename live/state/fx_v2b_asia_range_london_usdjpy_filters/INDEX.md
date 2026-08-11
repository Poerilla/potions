# USDJPY Asia-range London — month + rolling WR/PF filters

Filters:
- Skip entry months: **Jan** (consistently negative on sizing tapes)
- Shadow rolling 50 campaigns: sit out when WR < 40% or PF < 1.00

| Rank | Book | Variant | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | S_3_1_3 | skip_months+roll50_wr40_pf1 | 943 | 861 | $178142 | $-24627 | 7.23 | 48.6 | 1.294 |
| 2 | S_3_3_3 | skip_months+roll50_wr40_pf1 | 939 | 857 | $225075 | $-31663 | 7.11 | 48.2 | 1.288 |
| 3 | S_0_5_0 | skip_months+roll50_wr40_pf1 | 939 | 856 | $113716 | $-17057 | 6.67 | 48.2 | 1.259 |
| 4 | S_3_3_3 | unfiltered | 1678 | 1673 | $196627 | $-91767 | 2.14 | 47.3 | 1.141 |

## Gate skips

- **S_0_5_0**: allowed=939 skip_sessions=739 reasons={'month': 165, 'wr': 7, 'pf': 435, 'both': 195}
- **S_3_1_3**: allowed=943 skip_sessions=735 reasons={'month': 165, 'wr': 2, 'pf': 462, 'both': 165}
- **S_3_3_3**: allowed=939 skip_sessions=739 reasons={'month': 165, 'wr': 1, 'pf': 467, 'both': 166}

- Hub: `/home/tester/hsm/potions/live/state/fx_v2b_asia_range_london_usdjpy_filters`

