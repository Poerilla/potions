# Broker-Like Bar Replay Rankings

New standard: strategy-generated `OrderIntent`s through `Engine` + `PaperBroker`. Orders become active only after the confirming bar has closed. Open units are marked at the final replay close.

Realism knobs: `slippage_ticks=1`, `fee_per_unit=$1.50`, stop gap-through enabled, OCO-collapsed risk projection.

| Rank | Candidate | Instrument | Units | Trades | Net | Close MTM DD | Intrabar Stress DD | Max Open Units | Net / Stress DD |
|---:|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | ES Yearly ORB scaleout3 | ES | 219 | 73 | $328,727.75 | $-38,875.00 | $-40,403.00 | 3 | 8.14 |
| 2 | NQ Yearly ORB scaleout3 | NQ | 204 | 68 | $850,314.00 | $-103,790.00 | $-106,720.00 | 3 | 7.97 |
| 3 | YM Yearly ORB scaleout3 | YM | 243 | 81 | $288,756.75 | $-39,490.00 | $-39,810.00 | 3 | 7.25 |
| 4 | MNQ Yearly ORB scaleout3 | MNQ | 72 | 24 | $67,942.12 | $-10,370.00 | $-10,669.00 | 3 | 6.37 |
| 5 | NQ ATR daily ladder 1/1/2/2/2 10-max | NQ | 402 | 149 | $1,572,142.00 | $-236,014.50 | $-255,950.00 | 10 | 6.14 |
| 6 | MNQ ATR daily ladder 1/1/2/2/2 10-max | MNQ | 162 | 52 | $146,875.00 | $-23,456.50 | $-25,610.00 | 10 | 5.74 |
| 7 | NQ ATR daily 3-initial 10-max | NQ | 623 | 149 | $1,717,280.50 | $-299,713.00 | $-309,068.50 | 10 | 5.56 |
| 8 | MNQ ATR daily 3-initial 10-max | MNQ | 233 | 52 | $159,819.00 | $-28,734.00 | $-29,350.50 | 10 | 5.45 |
| 9 | NQ Yearly ORB scaleout3 20% range-close | NQ | 138 | 46 | $741,289.25 | $-127,940.00 | $-141,210.00 | 3 | 5.25 |
| 10 | MNQ Yearly ORB scaleout3 20% range-close | MNQ | 30 | 10 | $66,845.25 | $-12,785.00 | $-14,141.00 | 3 | 4.73 |
| 11 | ES ATR weekly 2-initial / 3-add / 6-max | ES | 142 | 42 | $853,549.50 | $-194,833.00 | $-200,208.00 | 6 | 4.26 |
| 12 | ES Yearly ORB scaleout3 20% range-close | ES | 165 | 55 | $350,746.25 | $-76,176.00 | $-86,332.50 | 3 | 4.06 |
| 13 | MYM Yearly ORB scaleout3 | MYM | 81 | 27 | $15,122.75 | $-3,570.00 | $-3,916.00 | 3 | 3.86 |
| 14 | NQ ATR weekly 2-initial / 3-add / 6-max | NQ | 127 | 38 | $1,443,304.50 | $-407,338.00 | $-428,513.00 | 6 | 3.37 |
| 15 | YM Yearly ORB scaleout3 20% range-close | YM | 147 | 49 | $182,899.50 | $-61,418.00 | $-63,597.50 | 3 | 2.88 |
| 16 | MNQ ATR weekly 2-initial / 3-add / 6-max | MNQ | 54 | 17 | $119,295.00 | $-40,744.50 | $-42,836.50 | 6 | 2.78 |
| 17 | MES ATR weekly 2-initial / 3-add / 6-max | MES | 28 | 8 | $37,444.25 | $-14,496.25 | $-17,212.50 | 6 | 2.18 |
| 18 | YM Monthly ORB restricted scaleout3 | YM | 705 | 235 | $118,122.50 | $-52,388.50 | $-56,855.75 | 3 | 2.08 |
| 19 | ES ATR daily 3-initial 10-max | ES | 631 | 148 | $567,916.00 | $-274,459.50 | $-278,247.00 | 10 | 2.04 |
| 20 | MYM Yearly ORB scaleout3 20% range-close | MYM | 42 | 14 | $12,097.62 | $-5,954.00 | $-6,098.00 | 3 | 1.98 |
| 21 | ES ATR daily ladder 1/1/2/2/2 10-max | ES | 417 | 148 | $448,399.50 | $-240,399.50 | $-246,499.50 | 10 | 1.82 |
| 22 | YM ATR daily 3-initial 10-max | YM | 611 | 145 | $289,998.50 | $-162,760.00 | $-166,754.50 | 10 | 1.74 |
| 23 | YM ATR weekly 2-initial / 3-add / 6-max | YM | 157 | 49 | $406,094.50 | $-231,969.50 | $-246,159.50 | 6 | 1.65 |
| 24 | MYM ATR weekly 2-initial / 3-add / 6-max | MYM | 83 | 27 | $24,726.50 | $-18,963.00 | $-19,032.00 | 6 | 1.30 |
| 25 | MYM ATR daily 3-initial 10-max | MYM | 249 | 58 | $16,016.50 | $-12,351.00 | $-13,278.00 | 10 | 1.21 |
| 26 | MYM Monthly ORB restricted scaleout3 boundary-stop entry | MYM | 573 | 191 | $9,436.25 | $-7,467.88 | $-8,030.12 | 3 | 1.18 |
| 27 | MES Yearly ORB scaleout3 20% range-close | MES | 33 | 11 | $9,878.31 | $-7,633.50 | $-8,545.50 | 3 | 1.16 |
| 28 | YM Monthly ORB restricted scaleout3 boundary-stop entry | YM | 1317 | 439 | $93,420.75 | $-79,478.00 | $-84,545.50 | 3 | 1.10 |
| 29 | MES Monthly ORB restricted scaleout3 boundary-stop entry | MES | 336 | 112 | $9,685.06 | $-9,229.50 | $-9,836.25 | 3 | 0.98 |
| 30 | NQ Monthly ORB restricted scaleout3 | NQ | 687 | 229 | $173,383.25 | $-198,062.00 | $-201,682.00 | 3 | 0.86 |
| 31 | MES Yearly ORB scaleout3 | MES | 36 | 12 | $1,954.75 | $-2,616.00 | $-2,859.00 | 3 | 0.68 |
| 32 | MYM Monthly ORB restricted scaleout3 | MYM | 288 | 96 | $5,470.88 | $-9,320.75 | $-9,977.75 | 3 | 0.55 |
| 33 | MES Monthly ORB restricted scaleout3 | MES | 171 | 57 | $3,820.06 | $-6,932.87 | $-7,390.37 | 3 | 0.52 |
| 34 | MNQ Monthly ORB restricted scaleout3 boundary-stop entry | MNQ | 555 | 185 | $10,755.38 | $-20,536.00 | $-21,705.38 | 3 | 0.50 |
| 35 | YM ATR daily ladder 1/1/2/2/2 10-max | YM | 408 | 145 | $101,693.00 | $-223,105.50 | $-225,220.50 | 10 | 0.45 |
| 36 | MNQ Monthly ORB restricted scaleout3 | MNQ | 291 | 97 | $8,848.88 | $-19,968.62 | $-20,334.62 | 3 | 0.44 |
| 37 | NQ Monthly ORB restricted scaleout3 boundary-stop entry | NQ | 1308 | 436 | $80,948.00 | $-201,943.75 | $-213,575.75 | 3 | 0.38 |
| 38 | ES Monthly ORB restricted scaleout3 | ES | 672 | 224 | $28,207.62 | $-96,566.87 | $-97,016.87 | 3 | 0.29 |
| 39 | ES Monthly ORB restricted scaleout3 boundary-stop entry | ES | 1305 | 435 | $26,530.00 | $-154,439.88 | $-171,539.88 | 3 | 0.15 |
| 40 | MYM ATR daily ladder 1/1/2/2/2 10-max | MYM | 173 | 58 | $2,366.50 | $-19,284.50 | $-19,707.50 | 10 | 0.12 |
| 41 | MES ATR daily 3-initial 10-max | MES | 172 | 41 | $1,719.50 | $-27,553.25 | $-27,935.75 | 10 | 0.06 |
| 42 | MES ATR daily ladder 1/1/2/2/2 10-max | MES | 112 | 41 | $-1,831.75 | $-24,104.50 | $-24,714.50 | 10 | -0.07 |

## Coverage Notes

- Monthly overlap range breakout daily-ST retest x5 remains a 4h causal research artifact. MNQ/NQ have 4h caches; ES/MES/YM/MYM do not yet have equivalent 4h cache files in this workspace.
- v2b clean-break variants need a 1m/5m StrategyPlugin before they can be compared in this broker-like table.
- This table is intentionally different from theoretical/research tables: it favors implementability and order timing over optimistic same-bar fills.
