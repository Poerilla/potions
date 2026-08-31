# NQ Prior-Opposed Resting-Limit Causal Timing Audit

Source run: `live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/`.

This audit checks the causal sequence for the resting-limit version of the prior-opposed gate:

1. ST+PMC creates an opposite-side entry-limit gate only when the completed hourly bar is knowable (`live_after_ts + 1h`).
2. v2b can arm only after that gate timestamp and after the opening range is complete.
3. The v2b entry fill must occur after the v2b stop order is active.

## Result

- Entry-order arm rows checked: **528** across **520** trade IDs
- ST resting-limit gate available before v2b arm: **528 / 528**
- Filled entry orders after arm time: **432 / 432** across **432** filled trade IDs
- Causality violations in run summary: **0**
- Resting-limit run performance: **432 campaigns / $1,330,920 net / $-68,610 stress / 19.40 Net/Stress**

Read: the resting-limit baseline is causal at the hour-complete gate level. It does not use the old left-label hourly fill stamp as if it were already known.

Note: there are more arm rows than filled campaigns because some OCO/resting entry stops are cancelled or never filled. The performance summary counts filled/closed campaigns.

## Time From ST Gate Availability To v2b Arm

| Bucket | Armed entry orders |
|---|---:|
| <=1m | 142 |
| 1-5m | 0 |
| 5-30m | 4 |
| 30m-2h | 123 |
| >2h | 259 |

## Time From v2b Arm To Entry Fill

| Bucket | Filled entry orders |
|---|---:|
| <=1m | 101 |
| 1-5m | 78 |
| 5-30m | 120 |
| 30m-2h | 92 |
| >2h | 41 |

## First 25 Arm Rows

| session_date   | st_pmc_side_needed   | st_limit_available_ts     | v2b_direction   | v2b_arm_ts                | v2b_entry_fill_ts         |   minutes_st_available_to_v2b_arm | minutes_v2b_arm_to_entry_fill   | campaign_net_usd   |
|:---------------|:---------------------|:--------------------------|:----------------|:--------------------------|:--------------------------|----------------------------------:|:--------------------------------|:-------------------|
| 2021-03-04     | short                | 2021-03-04T00:00:00-05:00 | Long            | 2021-03-04T09:44:00-05:00 | 2021-03-04T11:02:00-05:00 |                               584 | 78.0                            | -11682.50          |
| 2021-03-05     | short                | 2021-03-05T12:00:00-05:00 | Long            | 2021-03-05T12:01:00-05:00 | 2021-03-05T13:37:00-05:00 |                                 1 | 96.0                            | 5442.50            |
| 2021-03-09     | short                | 2021-03-08T17:00:00-05:00 | Long            | 2021-03-09T09:44:00-05:00 | 2021-03-09T09:49:00-05:00 |                              1004 | 5.0                             | 11902.50           |
| 2021-03-12     | short                | 2021-03-12T06:00:00-05:00 | Long            | 2021-03-12T09:44:00-05:00 | 2021-03-12T09:50:00-05:00 |                               224 | 6.0                             | -7682.50           |
| 2021-03-12     | long                 | 2021-03-11T21:00:00-05:00 | Short           | 2021-03-12T09:44:00-05:00 |                           |                               764 |                                 | -7682.50           |
| 2021-03-12     | long                 | 2021-03-11T21:00:00-05:00 | Short           | 2021-03-12T10:27:00-05:00 | 2021-03-12T10:28:00-05:00 |                               807 | 1.0                             | -9232.50           |
| 2021-03-15     | short                | 2021-03-15T02:00:00-04:00 | Long            | 2021-03-15T09:44:00-04:00 | 2021-03-15T09:52:00-04:00 |                               464 | 8.0                             | -5507.50           |
| 2021-03-16     | long                 | 2021-03-16T12:00:00-04:00 | Short           | 2021-03-16T12:01:00-04:00 | 2021-03-16T14:25:00-04:00 |                                 1 | 144.0                           | -757.50            |
| 2021-03-17     | short                | 2021-03-17T09:00:00-04:00 | Long            | 2021-03-17T09:44:00-04:00 | 2021-03-17T09:49:00-04:00 |                                44 | 5.0                             | 15427.50           |
| 2021-03-18     | long                 | 2021-03-18T04:00:00-04:00 | Short           | 2021-03-18T09:44:00-04:00 | 2021-03-18T09:45:00-04:00 |                               344 | 1.0                             | 1087.50            |
| 2021-03-19     | short                | 2021-03-19T03:00:00-04:00 | Long            | 2021-03-19T09:44:00-04:00 | 2021-03-19T10:52:00-04:00 |                               404 | 68.0                            | -107.50            |
| 2021-03-23     | long                 | 2021-03-23T12:00:00-04:00 | Short           | 2021-03-23T12:01:00-04:00 | 2021-03-23T14:06:00-04:00 |                                 1 | 125.0                           | -5332.50           |
| 2021-03-24     | long                 | 2021-03-24T06:00:00-04:00 | Short           | 2021-03-24T09:44:00-04:00 | 2021-03-24T09:48:00-04:00 |                               224 | 4.0                             | 16837.50           |
| 2021-03-25     | short                | 2021-03-25T12:00:00-04:00 | Long            | 2021-03-25T12:01:00-04:00 | 2021-03-25T15:04:00-04:00 |                                 1 | 183.0                           | -3182.50           |
| 2021-04-06     | long                 | 2021-04-06T13:00:00-04:00 | Short           | 2021-04-06T13:01:00-04:00 |                           |                                 1 |                                 |                    |
| 2021-04-09     | long                 | 2021-04-08T22:00:00-04:00 | Short           | 2021-04-09T09:44:00-04:00 |                           |                               704 |                                 |                    |
| 2021-04-14     | long                 | 2021-04-14T09:00:00-04:00 | Short           | 2021-04-14T09:44:00-04:00 | 2021-04-14T10:02:00-04:00 |                                44 | 18.0                            | 10702.50           |
| 2021-04-16     | long                 | 2021-04-16T09:00:00-04:00 | Short           | 2021-04-16T09:44:00-04:00 | 2021-04-16T09:45:00-04:00 |                                44 | 1.0                             | -6632.50           |
| 2021-04-22     | long                 | 2021-04-22T05:00:00-04:00 | Short           | 2021-04-22T09:44:00-04:00 | 2021-04-22T09:47:00-04:00 |                               284 | 3.0                             | -4182.50           |
| 2021-04-27     | long                 | 2021-04-27T09:00:00-04:00 | Short           | 2021-04-27T09:44:00-04:00 | 2021-04-27T09:45:00-04:00 |                                44 | 1.0                             | 3692.50            |
| 2021-04-29     | long                 | 2021-04-29T09:00:00-04:00 | Short           | 2021-04-29T09:44:00-04:00 | 2021-04-29T09:45:00-04:00 |                                44 | 1.0                             | 6247.50            |
| 2021-05-03     | short                | 2021-05-03T06:00:00-04:00 | Long            | 2021-05-03T09:44:00-04:00 | 2021-05-03T10:07:00-04:00 |                               224 | 23.0                            | -6232.50           |
| 2021-05-04     | short                | 2021-05-04T13:00:00-04:00 | Long            | 2021-05-04T13:01:00-04:00 |                           |                                 1 |                                 |                    |
| 2021-05-06     | short                | 2021-05-06T11:00:00-04:00 | Long            | 2021-05-06T11:01:00-04:00 | 2021-05-06T11:34:00-04:00 |                                 1 | 33.0                            | 8587.50            |
| 2021-05-11     | short                | 2021-05-11T09:00:00-04:00 | Long            | 2021-05-11T09:44:00-04:00 | 2021-05-11T09:51:00-04:00 |                                44 | 7.0                             | 12117.50           |

## Full Table

- CSV: [`resting_limit_causal_timing_table.csv`](resting_limit_causal_timing_table.csv)
- Day-level source: [`day_timelines/day_summary.csv`](day_timelines/day_summary.csv)
- Event-level source: [`day_timelines/day_event_timeline.csv`](day_timelines/day_event_timeline.csv)

## Remaining Caveat

This proves ordering at 1m/hour-complete resolution. It does not prove sub-second broker queue placement or same-minute tick order. Entry orders that arm and fill inside the next minute still need tick-level/broker-paper parity if promoted.
