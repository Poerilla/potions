# NQ 2c half+open $2k + reverse after full stop (1h path)

- Primary: 2 @ p_liq; 1@half 1@open; SL = **50 pts** ($2000 / 2 / $20)
- Reverse **only** after ``stop_full`` (no half fill yet)
- Reverse: limit opposite @ stop; target = **|entry − open|**; SL = 50 pts; qty 2

| Book | N | WR | Net $ | Stress $ | N/S | stop_full | rev_tgt | rev_stop |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| hp primary | 101 | 46% | +18712 | 18144 | 1.03 | 50 | 0 | 0 |
| hp reverse | 50 | 46% | +107220 | 11028 | 9.72 | 0 | 22 | 27 |
| hp combined | 151 | 46% | +125932 | 12096 | 10.41 | 50 | 22 | 27 |
| all primary | 161 | 45% | +14399 | 27715 | 0.52 | 79 | 0 | 0 |
| all reverse | 79 | 44% | +126596 | 8064 | 15.70 | 0 | 34 | 43 |
| all combined | 240 | 45% | +140995 | 16934 | 8.33 | 79 | 34 | 43 |

Hub: `/home/tester/hsm/potions/live/state/monthly_open_atr_extension_band/liq_run_fade_2c_half_open_r2000_reverse_path`

Stance: reverse **helps** on path HP — proceed to 1m broker with reverse on.
