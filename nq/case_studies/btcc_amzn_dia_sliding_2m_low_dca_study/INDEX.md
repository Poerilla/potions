# BTCC / AMZN / DIA Sliding 2-Month Low DCA Overlay

Data: Yahoo adjusted daily OHLCV. `BTCC.TO` is a TSX-listed Canadian ETF, so values are nominal CAD-like Yahoo adjusted prices; `AMZN` and `DIA` are USD instruments. Do not compare absolute ending dollars across currencies without currency normalization.

Rule: regular DCA buys **$1,000/month** on the first trading day open. Overlay variants contribute and buy an extra **$500** when the ticker touches its prior 2-calendar-month low.

Signal modes: `all_touches`, `new_touch_cluster`, and `first_touch_per_month`. Same-total monthly DCA is included so extra contributions are compared fairly.

## Common Window Best Rows

Common window starts at the latest first available date across the tickers.

| Ticker | Best Signal | Window | Signals | Signals/Yr | Extra Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| AMZN | all_touches | 2021-02-25 to 2026-06-03 | 66 | 12.53 | $33,000 | $164,301 | $60,994 | $155,755 | $8,546 |
| BTCC.TO | new_touch_cluster | 2021-02-25 to 2026-06-03 | 42 | 7.97 | $21,000 | $127,191 | $36,750 | $119,661 | $7,530 |
| DIA | all_touches | 2021-02-25 to 2026-06-03 | 64 | 12.15 | $32,000 | $141,442 | $48,937 | $138,045 | $3,396 |

## Available-History Best Rows

| Ticker | Best Signal | Window | Signals | Signals/Yr | Extra Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| AMZN | new_touch_cluster | 2010-01-04 to 2026-06-03 | 101 | 6.15 | $50,500 | $2,436,587 | $523,035 | $2,401,603 | $34,983 |
| BTCC.TO | new_touch_cluster | 2021-02-25 to 2026-06-03 | 42 | 7.97 | $21,000 | $127,191 | $36,750 | $119,661 | $7,530 |
| DIA | first_touch_per_month | 2010-01-04 to 2026-06-03 | 54 | 3.29 | $27,000 | $695,390 | $88,409 | $689,751 | $5,639 |

## Full Common-Window Rows

| Ticker | Signal | Signals | Extra Contrib | Total Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly | Max DD | Net/DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| AMZN | all_touches | 66 | $33,000 | $98,000 | $164,301 | $60,994 | $155,755 | $8,546 | $-33,147 | 2.00 |
| AMZN | new_touch_cluster | 36 | $18,000 | $83,000 | $136,871 | $33,564 | $131,915 | $4,956 | $-29,268 | 1.84 |
| AMZN | first_touch_per_month | 20 | $10,000 | $75,000 | $122,027 | $18,720 | $119,200 | $2,827 | $-27,252 | 1.73 |
| BTCC.TO | new_touch_cluster | 42 | $21,000 | $86,000 | $127,191 | $36,750 | $119,661 | $7,530 | $-112,590 | 0.37 |
| BTCC.TO | all_touches | 71 | $35,500 | $100,500 | $146,047 | $55,605 | $139,837 | $6,210 | $-122,371 | 0.37 |
| BTCC.TO | first_touch_per_month | 25 | $12,500 | $77,500 | $108,627 | $18,185 | $107,834 | $793 | $-94,751 | 0.33 |
| DIA | all_touches | 64 | $32,000 | $97,000 | $141,442 | $48,937 | $138,045 | $3,396 | $-10,540 | 4.22 |
| DIA | new_touch_cluster | 30 | $15,000 | $80,000 | $115,359 | $22,855 | $113,852 | $1,508 | $-10,112 | 3.50 |
| DIA | first_touch_per_month | 17 | $8,500 | $73,500 | $105,637 | $13,133 | $104,601 | $1,036 | $-9,082 | 3.54 |

## Read

- The sidecar works best when the underlying trend is strong and drawdowns are deep enough to make the extra buys meaningful.
- `BTCC.TO` has a much shorter history, beginning in 2021, so its common-window row is the fair comparison to AMZN and DIA.
- `all_touches` usually wins ending equity but contributes much more extra cash; `new_touch_cluster` is a cleaner operational compromise.

## Charts

- BTCC.TO common-window chart: [`charts/btcc_to_common_overlay.png`](charts/btcc_to_common_overlay.png)
- AMZN common-window chart: [`charts/amzn_common_overlay.png`](charts/amzn_common_overlay.png)
- DIA common-window chart: [`charts/dia_common_overlay.png`](charts/dia_common_overlay.png)

## Files

- `summary.csv`
- `curves.csv`
- `events.csv`
- `signals_and_levels.csv`
