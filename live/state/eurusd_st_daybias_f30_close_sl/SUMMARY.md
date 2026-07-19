# f30 week — close-beyond SL + enter-at-SL

## Why pandas 'missed' stops

Not a mystical fill difference. Old pandas **`break`'d out of the entry-day 1m loop**
after a fill, so wicks through the prev-day extreme **later that same day were never
checked**. Broker resting stops fired. On the would-be-winner set, the theoretical
stop was **touched during the research hold in 41/41** cases.

## Variants (pandas, break-fixed)

| Strategy | Entry | Stop | Net | Closed DD | Net/DD | WR | Med hold | Stops | Period |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| f30_week_wick_1m_fixed | pullback | wick_1m | $-4,073 | $-9,637 | -0.42 | 15.5% | 3.0 | 498 | 122 |
| f30_week_enter_at_sl_wick | at_sl | wick_1m | $-6,967 | $-6,936 | -1.00 | 6.1% | 0.6 | 621 | 33 |
| f30_week_enter_at_sl_close_0buf | at_sl | close_1h | $-14,033 | $-13,970 | -1.00 | 11.4% | 1.0 | 586 | 63 |
| f30_week_close_1h_sl | pullback | close_1h | $-14,518 | $-16,400 | -0.89 | 19.2% | 5.3 | 438 | 156 |
| f30_week_enter_at_sl_close | at_sl | close_1h | $-14,923 | $-15,517 | -0.96 | 13.8% | 2.4 | 561 | 78 |

- **wick_1m**: exit if any 1m wick tags stop (honest vs old inflated path).
- **close_1h**: wicks through SL allowed; exit only if hourly **closes** beyond SL.
- **at_sl**: enter at prev-day extreme (the old stop level); buffer stop 5 pips beyond
  (or 0.5 pip if 0buf) to try to ride the bounce the false survivors captured.

## Verdict

| Idea | Result |
|---|---|
| Honest wick stop (break-fixed) | **−$4.1k** — old +$32k was fake |
| Close-beyond hourly SL | **−$14.5k** — worse (gives back more on failed bounces) |
| Enter at SL level | **−$7k to −$15k** — does not capture a bounce edge |

The “missed Friday rides” were almost entirely **stops the research engine ignored on the entry day**. There is no separate edge to harvest by entering at the SL.

Would-be-winner charts: **41/41** in [`charts_wouldbe_winners/INDEX.md`](charts_wouldbe_winners/INDEX.md)

CSV: `leaderboard.csv`
