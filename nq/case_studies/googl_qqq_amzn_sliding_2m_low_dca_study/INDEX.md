# GOOGL / QQQ / AMZN Sliding 2-Month Low DCA Study

Data: Yahoo adjusted daily OHLCV (USD). Window: **2010-01-04 to 2026-06-03** for all three (full shared history).

Rule: regular DCA buys **$1,000/month** on the first trading day open. Overlay variants contribute and buy an extra **$500** when the ticker touches its prior 2-calendar-month low.

Signal modes: `all_touches`, `new_touch_cluster`, and `first_touch_per_month`. Same-total monthly DCA is included so extra contributions are compared fairly.

## Which Instrument Wins?

### Plain monthly DCA ($1k/month, $198k total)

| Rank | Ticker | End Equity | Net | Return on Contrib | Max DD | Net/DD |
|---:|---|---:|---:|---:|---:|---:|
| 1 | **GOOGL** | $1,999,668 | $1,801,668 | 910% | $-387,887 | 4.64 |
| 2 | **AMZN** | $1,913,551 | $1,715,551 | 866% | $-752,118 | 2.28 |
| 3 | **QQQ** | $1,311,051 | $1,113,051 | 562% | $-216,073 | 5.15 |

**Ending wealth:** GOOGL beats AMZN by ~$86k (~4.5%) and QQQ by ~$689k (~53%) on the same $198k schedule.

**Risk-adjusted (net / max drawdown):** QQQ has the shallowest peak-to-trough equity dip; GOOGL is second; AMZN’s deeper drawdowns drag net/DD despite strong total return.

### Best overlay per ticker (vs same-total monthly lump DCA)

| Ticker | Best Signal | End Equity | vs Base Monthly | vs Same-Total Monthly |
|---|---|---:|---:|---:|
| GOOGL | all_touches | $3,058,873 | +$1,059,205 | +$94,719 |
| AMZN | new_touch_cluster | $2,436,587 | +$523,035 | +$34,983 |
| QQQ | first_touch_per_month | $1,457,318 | +$146,267 | **-$12,648** |

**Overlay takeaway:** The 2-month-low sidecar clearly helps GOOGL and AMZN. For QQQ, every overlay variant finishes **below** putting the same total cash into a higher flat monthly DCA — the extra buys do not beat simply raising the monthly contribution.

## Common / Available-History Best Rows

| Ticker | Best Signal | Window | Signals | Signals/Yr | Extra Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | all_touches | 2010-01-04 to 2026-06-03 | 191 | 11.64 | $95,500 | $3,058,873 | $1,059,205 | $2,964,154 | $94,719 |
| AMZN | new_touch_cluster | 2010-01-04 to 2026-06-03 | 101 | 6.15 | $50,500 | $2,436,587 | $523,035 | $2,401,603 | $34,983 |
| QQQ | first_touch_per_month | 2010-01-04 to 2026-06-03 | 48 | 2.92 | $24,000 | $1,457,318 | $146,267 | $1,469,966 | $-12,648 |

## Full Rows (2010–2026)

| Ticker | Signal | Signals | Extra Contrib | Total Contrib | End Equity | More Than Base | Same-Total Monthly | vs Same-Total Monthly | Max DD | Net/DD |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| GOOGL | all_touches | 191 | $95,500 | $293,500 | $3,058,873 | $1,059,205 | $2,964,154 | $94,719 | $-590,096 | 4.69 |
| GOOGL | new_touch_cluster | 100 | $50,000 | $248,000 | $2,567,666 | $567,998 | $2,504,635 | $63,031 | $-497,396 | 4.66 |
| GOOGL | first_touch_per_month | 57 | $28,500 | $226,500 | $2,337,206 | $337,538 | $2,287,499 | $49,707 | $-453,075 | 4.66 |
| AMZN | new_touch_cluster | 101 | $50,500 | $248,500 | $2,436,587 | $523,035 | $2,401,603 | $34,983 | $-950,499 | 2.30 |
| AMZN | first_touch_per_month | 58 | $29,000 | $227,000 | $2,205,836 | $292,285 | $2,193,819 | $12,018 | $-863,675 | 2.29 |
| AMZN | all_touches | 167 | $83,500 | $281,500 | $2,695,141 | $781,590 | $2,720,529 | $-25,388 | $-1,041,481 | 2.32 |
| QQQ | first_touch_per_month | 48 | $24,000 | $222,000 | $1,457,318 | $146,267 | $1,469,966 | $-12,648 | $-236,235 | 5.23 |
| QQQ | all_touches | 152 | $76,000 | $274,000 | $1,782,129 | $471,078 | $1,814,283 | $-32,154 | $-279,191 | 5.40 |
| QQQ | new_touch_cluster | 79 | $39,500 | $237,500 | $1,538,722 | $227,671 | $1,572,599 | $-33,877 | $-244,807 | 5.32 |

## Read

- **If you only DCA with no timing rule:** prefer **GOOGL** for highest ending equity since 2010; **AMZN** is close second; **QQQ** trails on absolute dollars but had the smallest equity drawdown for the same contributions.
- **If you use the rolling 2-month-low extra buy:** **GOOGL** benefits most (large uplift vs base and vs lump monthly). **AMZN** benefits modestly (`new_touch_cluster` is the fair ops choice). **QQQ** does not — lump the cash into monthly DCA instead.
- AMZN’s `all_touches` overlay beats base monthly by a lot but still loses vs equal-total monthly DCA (same pattern as the BTCC/AMZN/DIA study).
- This is one historical path (2010 IPO-era GOOGL, post-GFC bull + corrections). Not a forecast; concentration and single-name risk differ (GOOGL/AMZN vs diversified QQQ).

## Charts

- GOOGL: [`charts/googl_common_overlay.png`](charts/googl_common_overlay.png)
- QQQ: [`charts/qqq_common_overlay.png`](charts/qqq_common_overlay.png)
- AMZN: [`charts/amzn_common_overlay.png`](charts/amzn_common_overlay.png)

## Files

- `summary.csv`
- `curves.csv`
- `events.csv`
- `signals_and_levels.csv`

## Reproduce

```bash
cd /home/tester/hsm/potions
python3 scripts/multi_asset_sliding_low_extra_overlay.py \
  --tickers GOOGL QQQ AMZN \
  --output-root nq/case_studies/googl_qqq_amzn_sliding_2m_low_dca_study
```
