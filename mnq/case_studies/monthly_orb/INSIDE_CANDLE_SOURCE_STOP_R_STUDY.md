# Inside-Candle-Open Source-Stop R Study

Study variant: after a valid monthly OR breakout close, place the inside-candle-open limit exactly as before. Stop loss is moved from the opposing monthly OR boundary to the selected inside opposite-color candle run:

- Long: stop at the lowest low of the selected consecutive inside red candle run.
- Short: stop at the highest high of the selected consecutive inside green candle run.
- TP stays at the monthly OR boundary plus/minus one monthly range.
- Restricted variant still exits at daily close if price closes back inside the monthly OR.

This is a causal daily-bar study, but fill/stop/target ordering remains daily OHLC approximate.

## Results

| Instrument | Variant | Trades | Net | Max DD | Win rate | PF | Avg/trade pts |
|---|---|---:|---:|---:|---:|---:|---:|
| MNQ | inside-candle-open unrestricted source-stop | 71 | $8,088.00 | $-3,974.50 | 29.58% | 1.53 | 56.96 |
| MNQ | inside-candle-open restricted source-stop | 77 | $10,291.50 | $-2,006.50 | 49.35% | 2.74 | 66.83 |
| NQ | inside-candle-open unrestricted source-stop | 169 | $87,935.00 | $-39,540.00 | 30.77% | 1.46 | 26.02 |
| NQ | inside-candle-open restricted source-stop | 179 | $111,705.00 | $-20,055.00 | 43.02% | 2.42 | 31.20 |

## Winning Trade R Distribution

`Realized >= nR` uses actual exit P/L divided by source-stop risk. `MFE >= nR` uses best daily-bar favorable excursion between entry and exit, divided by source-stop risk.

| Instrument | Variant | Winning trades | Avg realized R | Median realized R | Realized >=2R | Realized >=3R | Realized >=5R | MFE >=2R | MFE >=3R | MFE >=5R | Max realized R | Max MFE R |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| MNQ | unrestricted source-stop | 21 | 2.75 | 2.43 | 13 | 7 | 3 | 13 | 9 | 5 | 7.23 | 8.12 |
| MNQ | restricted source-stop | 38 | 1.12 | 0.40 | 8 | 3 | 2 | 16 | 7 | 5 | 7.23 | 14.09 |
| NQ | unrestricted source-stop | 52 | 2.80 | 1.90 | 25 | 13 | 5 | 28 | 16 | 9 | 25.38 | 38.00 |
| NQ | restricted source-stop | 77 | 1.04 | 0.48 | 10 | 5 | 3 | 29 | 17 | 10 | 12.00 | 16.75 |

## Read

The source stop improves drawdown and profit factor versus the unrestricted wide-stop version, but does not improve net over the current restricted candidate.

For MNQ, source-stop restricted cuts max DD from `$-2,293.50` to `$-2,006.50`, but net falls from `$11,453.50` to `$10,291.50`. For NQ, max DD improves from `$-22,950.00` to `$-20,055.00`, but net falls from `$117,165.00` to `$111,705.00`.

The unrestricted source-stop version better preserves large R winners, but it does so with a much lower win rate. Restricted source-stop has many more positive exits, yet most are not large realized R because the close-back-inside rule harvests small saves before the monthly target.

Best current interpretation: source-stop restricted is an interesting lower-DD sibling, but the original inside-candle-open restricted remains the stronger default candidate by net, while source-stop is useful if capital efficiency and tighter defined risk matter more than absolute profit.

## Detail CSVs

- MNQ unrestricted source-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_source_stop.csv`
- MNQ unrestricted source-stop R detail: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_source_stop_r_detail.csv`
- MNQ restricted source-stop: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_restricted_source_stop.csv`
- MNQ restricted source-stop R detail: `/home/tester/hsm/potions/mnq/mnq_monthly_orb_inside_candle_open_restricted_source_stop_r_detail.csv`
- NQ unrestricted source-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_source_stop.csv`
- NQ unrestricted source-stop R detail: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_source_stop_r_detail.csv`
- NQ restricted source-stop: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_restricted_source_stop.csv`
- NQ restricted source-stop R detail: `/home/tester/hsm/potions/nq/nq_monthly_orb_inside_candle_open_restricted_source_stop_r_detail.csv`
