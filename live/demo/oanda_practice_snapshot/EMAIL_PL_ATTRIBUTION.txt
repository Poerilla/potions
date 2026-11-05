# OANDA practice PL attribution

Fetched: `2026-08-18T14:54:17Z`  Account: `101-002-39860312-001` (practice)

## Balance vs trading PnL

- **Balance** (what the UI often shows as a big number): **$99403.23**
- NAV: **$99403.23** (balance + unrealized **$0.00**)
- Broker `resettablePL` (realized): **$-423.18**
- Broker financing field: **$-175.69**
- Starting deposit hint: **$100000.00**
- Bridge check: `start + resettablePL + financing ≈ $99401.13`

If the user quotes ~balance (e.g. 100895), say clearly: that is **account balance**, not trading PnL.

## Realized ORDER_FILL PL by instrument

| Instrument | Fill PL | Role |
|---|---:|---|
| `NAS100_USD` | $2767.43 | v2b ungated NAS100 (shared account; ST+PMC may share tape) |
| `SPX500_USD` | $329.03 | v2b ungated SPX500 |
| `EUR_USD` | $-0.01 | v2b / ST+PMC EURUSD |
| `USD_JPY` | $-0.04 | Monday OR / Asia-range USDJPY |
| `US30_USD` | $-3173.30 | v2b ungated US30 (shared account; ST+PMC / london may share) |
| **Sum of fill PL** | **$-76.89** | |

Closing fills with PL: **77 wins / $15553.89** vs **100 losses / $-15630.77**.

### By exit / fill reason

- `STOP_ORDER`: $-10643.01
- `LIMIT_ORDER`: $8129.59
- `MARKET_ORDER`: $4543.03
- `STOP_LOSS_ORDER`: $-2263.62
- `TAKE_PROFIT_ORDER`: $1042.34
- `MARKET_ORDER_TRADE_CLOSE`: $-885.22
- `MARKET_ORDER_POSITION_CLOSEOUT`: $-0.00

### By clientExtensions.tag

- `(no tag)`: $-76.89

### Largest losses

- 2026-07-28T15:26:11 `NAS100_USD` **$-1118.74** units=3.0 `STOP_ORDER`
- 2026-07-30T15:00:45 `US30_USD` **$-1047.04** units=-3.0 `STOP_ORDER`
- 2026-08-05T19:59:06 `US30_USD` **$-1029.59** units=-3.0 `STOP_ORDER`
- 2026-07-30T16:04:15 `US30_USD` **$-1016.02** units=3.0 `STOP_ORDER`
- 2026-08-04T14:56:35 `US30_USD` **$-999.01** units=3.0 `STOP_ORDER`
- 2026-08-03T18:45:12 `US30_USD` **$-822.15** units=3.0 `STOP_ORDER`
- 2026-08-03T16:50:45 `US30_USD` **$-814.93** units=-3.0 `STOP_ORDER`
- 2026-08-12T22:25:26 `US30_USD` **$-726.09** units=-2.0 `MARKET_ORDER_TRADE_CLOSE`
- 2026-08-11T14:34:43 `US30_USD` **$-706.95** units=-3.0 `STOP_ORDER`
- 2026-07-29T20:00:04 `NAS100_USD` **$-695.54** units=-1.0 `MARKET_ORDER`

### Largest wins

- 2026-08-03T20:00:05 `NAS100_USD` **$1009.47** units=-2.0 `MARKET_ORDER`
- 2026-07-29T20:00:04 `US30_USD` **$942.01** units=1.0 `MARKET_ORDER`
- 2026-08-04T19:16:24 `NAS100_USD` **$674.43** units=-1.0 `LIMIT_ORDER`
- 2026-08-04T20:00:05 `NAS100_USD` **$610.00** units=-1.0 `MARKET_ORDER`
- 2026-08-12T14:05:00 `NAS100_USD` **$596.52** units=-3.0 `STOP_ORDER`
- 2026-08-06T17:22:14 `US30_USD` **$574.04** units=1.0 `LIMIT_ORDER`
- 2026-08-06T20:00:04 `US30_USD` **$564.29** units=1.0 `MARKET_ORDER`
- 2026-07-27T14:30:31 `NAS100_USD` **$520.09** units=1.0 `LIMIT_ORDER`
- 2026-08-04T20:00:03 `US30_USD` **$434.79** units=-2.0 `MARKET_ORDER`
- 2026-07-29T14:42:59 `NAS100_USD` **$431.86** units=1.0 `LIMIT_ORDER`

## Open trades

(flat)

## Caveats

- Prefer broker `resettablePL` + financing for the **balance bridge**.
- Prefer ORDER_FILL `pl` totals for **which instruments / exit types** made or lost money.
- Sum(fill PL) may disagree with `resettablePL` when OANDA transaction IDs have gaps (`missing_tx_ids_count=149`).
- Strategy tags are often empty on fills; instrument is the practical attribution key.

Artifacts: `transactions_all.json`, `PL_ATTRIBUTION.json`, this file.
