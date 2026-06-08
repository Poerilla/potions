# QQQ Sliding 2-Month Low Extra-$500 Overlay

Rule: keep regular QQQ DCA at **$1,000/month**, then contribute and buy an additional **$500** whenever the selected sliding-low signal fires.

The extra buy uses the trailing-low limit price from the sliding-low study. This is more capital than base DCA, so the table includes a same-total monthly-DCA comparison.

Base monthly DCA: **$318,000 contributed**, **$4,001,076 ending equity**, **$3,683,076 net**, **$-714,352 max DD**, **5.16 Net/DD**.

## Leaderboard

| Rank | Signal | Signals | Extra Contrib | Total Contrib | End Equity | More Than Base | Net | Max DD | Net/DD | Same-Total Monthly | vs Same-Total Monthly |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | all_touches | 379 | $189,500 | $507,500 | $7,190,259 | $3,189,183 | $6,682,759 | $-1,280,975 | 5.22 | $1,596/mo -> $6,385,365 | $804,894 |
| 2 | new_touch_cluster | 176 | $88,000 | $406,000 | $5,395,003 | $1,393,927 | $4,989,003 | $-959,409 | 5.20 | $1,277/mo -> $5,108,292 | $286,711 |
| 3 | first_touch_per_month | 98 | $49,000 | $367,000 | $4,734,867 | $733,791 | $4,367,867 | $-843,501 | 5.18 | $1,154/mo -> $4,617,594 | $117,273 |

## Read

- Best ending-equity overlay is **all_touches**, ending at **$7,190,259** after adding **$189,500** of extra contributions. That is **$3,189,183** more ending equity than the base `$1,000/month` DCA.
- Against same-total monthly DCA, that best overlay is **$804,894**.

## Charts

- Overlay equity comparison: [`charts/extra_500_overlay_equity.png`](charts/extra_500_overlay_equity.png)

## Files

- `extra_500_overlay_summary.csv`
- `extra_500_overlay_curves.csv`
- `extra_500_overlay_events.csv`
