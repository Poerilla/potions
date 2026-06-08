# NQ Prior-Opposed v2b Event Calendar Audit

Event dates are pulled from free official sources:

- Federal Reserve FOMC meeting calendar: https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- BLS CPI archived news releases: https://www.bls.gov/bls/news-release/cpi.htm

FOMC dates use the final meeting day / decision day. CPI dates use BLS archived release dates.

## Event Counts

| event_type   |   count |
|:-------------|--------:|
| CPI          |      64 |
| FOMC         |      47 |

## Scenario Matrix

| scenario             |   trades |    net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:---------------------|---------:|-----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| base_1_1_3           |      352 | 1184585.00 |       -34652.50 |       -46267.50 |             25.60 |          69.32 |            2.75 |     3365.30 |
| cpi_days_to_1_1_1    |      352 | 1171273.00 |       -34629.50 |       -46267.50 |             25.32 |          69.60 |            2.79 |     3327.48 |
| skip_cpi_days        |      336 | 1165185.00 |       -35395.00 |       -46267.50 |             25.18 |          70.54 |            2.87 |     3467.81 |
| fomc_days_to_1_1_1   |      352 | 1162473.00 |       -31689.50 |       -46267.50 |             25.13 |          69.60 |            2.76 |     3302.48 |
| event_days_to_1_1_1  |      352 | 1149161.00 |       -31666.50 |       -46267.50 |             24.84 |          69.89 |            2.80 |     3264.66 |
| skip_fomc_days       |      336 | 1140565.00 |       -37012.50 |       -46267.50 |             24.65 |          69.64 |            2.78 |     3394.54 |
| event_days_to_1_1_0  |      352 | 1131449.00 |       -31515.50 |       -46267.50 |             24.45 |          70.17 |            2.82 |     3214.34 |
| skip_fomc_after_1330 |      344 | 1130935.00 |       -37012.50 |       -46267.50 |             24.44 |          69.19 |            2.69 |     3287.60 |
| skip_all_event_days  |      320 | 1121165.00 |       -38825.00 |       -46267.50 |             24.23 |          70.94 |            2.91 |     3503.64 |

## Read

- Best event-calendar row: **base_1_1_3** at 25.60 Net/Stress versus base 25.60.
- Treat this as a first-pass date audit only; CPI/FOMC labels do not include surprise magnitude, press conference windows, or other macro releases.

## Files

- `event_calendar.csv`
- `event_scenario_matrix.csv`
- `campaigns_on_event_days.csv`