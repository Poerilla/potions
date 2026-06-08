# Monthly ORB Breakout-Close Entry

Causal entry variant: after a daily close outside the monthly OR, place a limit order for later bars only. Long breakout candles must close green; short breakout candles must close red. Close-entry variants use the breakout close as entry. Boundary-retest variants use the original OR boundary as entry after the breakout close is known. Inside-candle variants use the most recent opposite-color fully-inside candle run before breakout. Stop-study variants compare the opposite range boundary, breakout candle low/high, 2x breakout-candle adverse distance, boundary plus/minus breakout candle size, the near breakout boundary itself, and the low/high of the selected inside-candle run.

## Candidate Flag

**Inside-candle-open restricted is now the primary scaling candidate among causal monthly ORB standalone variants by drawdown and profit factor.** Boundary-retest restricted remains the higher-net retest benchmark. Both are mechanically coherent; the original boundary-entry restricted row remains non-causal research context only.

| Instrument | Variant | Periods | Trades | Range-close exits | Target behind entry | Net pts | Net $ | Max DD pts | Max DD $ | Win rate | PF | Avg/trade pts | Wins >=2R | Wins >=3R |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | original boundary-entry | 83 | 128 | 0 | 0 | 15,751.25 | $31,502.50 | -2,722.25 | $-5,444.50 | 66.41% | 1.80 | 123.06 | 0 | 0 |
| MNQ | boundary-retest unrestricted | 83 | 106 | 0 | 0 | 3,164.50 | $6,329.00 | -4,118.25 | $-8,236.50 | 56.60% | 1.15 | 29.85 | 0 | 0 |
| MNQ | boundary-retest restricted | 83 | 117 | 75 | 0 | 6,297.50 | $12,595.00 | -2,239.50 | $-4,479.00 | 30.77% | 1.66 | 53.82 | 0 | 0 |
| MNQ | inside-candle-open unrestricted | 83 | 69 | 0 | 0 | 4,116.00 | $8,232.00 | -2,481.75 | $-4,963.50 | 42.03% | 1.36 | 59.65 | 9 | 1 |
| MNQ | inside-candle-open restricted | 83 | 77 | 58 | 0 | 5,726.75 | $11,453.50 | -1,146.75 | $-2,293.50 | 54.55% | 2.43 | 74.37 | 6 | 1 |
| MNQ | inside-candle-open unrestricted source-stop | 83 | 71 | 0 | 0 | 4,044.00 | $8,088.00 | -1,987.25 | $-3,974.50 | 29.58% | 1.53 | 56.96 | 13 | 7 |
| MNQ | inside-candle-open restricted source-stop | 83 | 77 | 45 | 0 | 5,145.75 | $10,291.50 | -1,003.25 | $-2,006.50 | 49.35% | 2.74 | 66.83 | 8 | 3 |
| MNQ | close-entry unrestricted | 83 | 151 | 0 | 0 | -2,477.25 | $-4,954.50 | -7,307.25 | $-14,614.50 | 57.62% | 0.93 | -16.41 | 0 | 0 |
| MNQ | close-entry restricted | 83 | 146 | 65 | 0 | 2,536.00 | $5,072.00 | -3,176.00 | $-6,352.00 | 53.42% | 1.16 | 17.37 | 0 | 0 |
| MNQ | close-entry unrestricted breakout-stop | 83 | 156 | 0 | 0 | 694.25 | $1,388.50 | -5,126.25 | $-10,252.50 | 41.03% | 1.03 | 4.45 | 18 | 7 |
| MNQ | close-entry restricted breakout-stop | 83 | 146 | 28 | 0 | -2,504.75 | $-5,009.50 | -6,096.25 | $-12,192.50 | 39.73% | 0.85 | -17.16 | 11 | 4 |
| MNQ | close-entry unrestricted 2x-breakout-stop | 83 | 154 | 0 | 0 | -2,997.75 | $-5,995.50 | -7,033.25 | $-14,066.50 | 51.95% | 0.91 | -19.47 | 5 | 2 |
| MNQ | close-entry restricted 2x-breakout-stop | 83 | 146 | 53 | 0 | 1,719.50 | $3,439.00 | -3,259.75 | $-6,519.50 | 47.95% | 1.11 | 11.78 | 4 | 0 |
| MNQ | close-entry unrestricted boundary-candle-stop | 83 | 154 | 0 | 0 | -1,594.25 | $-3,188.50 | -6,659.50 | $-13,319.00 | 52.60% | 0.95 | -10.35 | 3 | 0 |
| MNQ | close-entry restricted boundary-candle-stop | 83 | 146 | 54 | 0 | 1,670.25 | $3,340.50 | -3,146.00 | $-6,292.00 | 51.37% | 1.10 | 11.44 | 2 | 0 |
| MNQ | close-entry unrestricted near-boundary-stop | 83 | 162 | 0 | 0 | 1,263.00 | $2,526.00 | -3,585.25 | $-7,170.50 | 29.01% | 1.07 | 7.80 | 21 | 16 |
| MNQ | close-entry restricted near-boundary-stop | 83 | 149 | 0 | 0 | 308.75 | $617.50 | -2,305.00 | $-4,610.00 | 34.90% | 1.03 | 2.07 | 20 | 9 |
| MNQ | original boundary-entry restricted | 83 | 141 | 66 | 0 | 22,019.50 | $44,039.00 | -1,197.00 | $-2,394.00 | 50.35% | 3.58 | 156.17 | 0 | 0 |
| NQ | original boundary-entry | 190 | 305 | 0 | 0 | 22,315.00 | $446,300.00 | -2,718.00 | $-54,360.00 | 67.54% | 1.95 | 73.16 | 0 | 0 |
| NQ | boundary-retest unrestricted | 190 | 255 | 0 | 0 | 5,101.25 | $102,025.00 | -4,111.50 | $-82,230.00 | 57.65% | 1.20 | 20.00 | 0 | 0 |
| NQ | boundary-retest restricted | 190 | 275 | 169 | 0 | 8,560.75 | $171,215.00 | -2,239.25 | $-44,785.00 | 33.45% | 1.70 | 31.13 | 0 | 0 |
| NQ | inside-candle-open unrestricted | 190 | 164 | 0 | 0 | 4,469.25 | $89,385.00 | -2,472.50 | $-49,450.00 | 41.46% | 1.32 | 27.25 | 18 | 6 |
| NQ | inside-candle-open restricted | 190 | 179 | 134 | 0 | 5,858.25 | $117,165.00 | -1,147.50 | $-22,950.00 | 48.04% | 2.09 | 32.73 | 6 | 2 |
| NQ | inside-candle-open unrestricted source-stop | 190 | 169 | 0 | 0 | 4,396.75 | $87,935.00 | -1,977.00 | $-39,540.00 | 30.77% | 1.46 | 26.02 | 25 | 13 |
| NQ | inside-candle-open restricted source-stop | 190 | 179 | 100 | 0 | 5,585.25 | $111,705.00 | -1,002.75 | $-20,055.00 | 43.02% | 2.42 | 31.20 | 10 | 5 |
| NQ | close-entry unrestricted | 190 | 353 | 0 | 0 | -705.00 | $-14,100.00 | -7,668.00 | $-153,360.00 | 59.49% | 0.98 | -2.00 | 0 | 0 |
| NQ | close-entry restricted | 190 | 331 | 134 | 0 | 4,251.75 | $85,035.00 | -3,173.25 | $-63,465.00 | 55.89% | 1.22 | 12.85 | 0 | 0 |
| NQ | close-entry unrestricted breakout-stop | 190 | 363 | 0 | 0 | 3,107.75 | $62,155.00 | -5,849.75 | $-116,995.00 | 43.80% | 1.11 | 8.56 | 46 | 23 |
| NQ | close-entry restricted breakout-stop | 190 | 334 | 62 | 0 | -1,369.50 | $-27,390.00 | -6,014.25 | $-120,285.00 | 42.51% | 0.93 | -4.10 | 25 | 13 |
| NQ | close-entry unrestricted 2x-breakout-stop | 190 | 356 | 0 | 0 | 609.25 | $12,185.00 | -7,001.75 | $-140,035.00 | 55.06% | 1.02 | 1.71 | 15 | 5 |
| NQ | close-entry restricted 2x-breakout-stop | 190 | 333 | 108 | 0 | 3,334.75 | $66,695.00 | -3,251.75 | $-65,035.00 | 50.15% | 1.17 | 10.01 | 10 | 2 |
| NQ | close-entry unrestricted boundary-candle-stop | 190 | 356 | 0 | 0 | -191.00 | $-3,820.00 | -7,222.75 | $-144,455.00 | 55.06% | 1.00 | -0.54 | 18 | 3 |
| NQ | close-entry restricted boundary-candle-stop | 190 | 331 | 106 | 0 | 3,060.75 | $61,215.00 | -3,141.25 | $-62,825.00 | 54.08% | 1.15 | 9.25 | 9 | 3 |
| NQ | close-entry unrestricted near-boundary-stop | 190 | 374 | 0 | 0 | 784.25 | $15,685.00 | -3,583.25 | $-71,665.00 | 29.41% | 1.04 | 2.10 | 53 | 38 |
| NQ | close-entry restricted near-boundary-stop | 190 | 341 | 0 | 0 | 496.75 | $9,935.00 | -2,306.25 | $-46,125.00 | 35.19% | 1.04 | 1.46 | 45 | 27 |
| NQ | original boundary-entry restricted | 190 | 325 | 150 | 0 | 27,897.00 | $557,940.00 | -1,197.75 | $-23,955.00 | 50.46% | 3.56 | 85.84 | 0 | 0 |

## Output CSVs

- MNQ boundary-retest unrestricted: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_boundary_retest.csv`
- MNQ boundary-retest restricted: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_boundary_retest_restricted.csv`
- MNQ inside-candle-open unrestricted: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open.csv`
- MNQ inside-candle-open restricted: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_restricted.csv`
- MNQ inside-candle-open unrestricted source-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_source_stop.csv`
- MNQ inside-candle-open restricted source-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_restricted_source_stop.csv`
- MNQ close-entry unrestricted: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry.csv`
- MNQ close-entry restricted: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_restricted.csv`
- MNQ close-entry unrestricted breakout-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_breakout_stop.csv`
- MNQ close-entry restricted breakout-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_restricted_breakout_stop.csv`
- MNQ close-entry unrestricted 2x-breakout-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_2x_breakout_stop.csv`
- MNQ close-entry restricted 2x-breakout-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_restricted_2x_breakout_stop.csv`
- MNQ close-entry unrestricted boundary-candle-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_boundary_candle_stop.csv`
- MNQ close-entry restricted boundary-candle-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_restricted_boundary_candle_stop.csv`
- MNQ close-entry unrestricted near-boundary-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_near_boundary_stop.csv`
- MNQ close-entry restricted near-boundary-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_close_entry_restricted_near_boundary_stop.csv`
- NQ boundary-retest unrestricted: `/home/tester/hsm/potions/nq/nq_monthly_orb_boundary_retest.csv`
- NQ boundary-retest restricted: `/home/tester/hsm/potions/nq/nq_monthly_orb_boundary_retest_restricted.csv`
- NQ inside-candle-open unrestricted: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open.csv`
- NQ inside-candle-open restricted: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_restricted.csv`
- NQ inside-candle-open unrestricted source-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_source_stop.csv`
- NQ inside-candle-open restricted source-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_restricted_source_stop.csv`
- NQ close-entry unrestricted: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry.csv`
- NQ close-entry restricted: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_restricted.csv`
- NQ close-entry unrestricted breakout-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_breakout_stop.csv`
- NQ close-entry restricted breakout-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_restricted_breakout_stop.csv`
- NQ close-entry unrestricted 2x-breakout-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_2x_breakout_stop.csv`
- NQ close-entry restricted 2x-breakout-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_restricted_2x_breakout_stop.csv`
- NQ close-entry unrestricted boundary-candle-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_boundary_candle_stop.csv`
- NQ close-entry restricted boundary-candle-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_restricted_boundary_candle_stop.csv`
- NQ close-entry unrestricted near-boundary-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_near_boundary_stop.csv`
- NQ close-entry restricted near-boundary-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_close_entry_restricted_near_boundary_stop.csv`
