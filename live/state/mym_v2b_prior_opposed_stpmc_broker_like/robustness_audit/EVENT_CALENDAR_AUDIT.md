# MYM Prior-Opposed v2b Event Calendar Audit

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

| scenario             |   trades |   net_usd |   closed_dd_usd |   stress_dd_usd |   net_over_stress |   win_rate_pct |   profit_factor |   avg_trade |
|:---------------------|---------:|----------:|----------------:|----------------:|------------------:|---------------:|----------------:|------------:|
| event_days_to_1_1_1  |      333 |  25723.96 |        -2481.96 |        -2512.59 |             10.24 |          60.06 |            1.77 |       77.25 |
| fomc_days_to_1_1_1   |      333 |  26171.60 |        -2481.96 |        -2558.71 |             10.23 |          60.06 |            1.76 |       78.59 |
| base_1_1_3           |      333 |  26058.12 |        -2481.96 |        -2558.71 |             10.18 |          59.76 |            1.74 |       78.25 |
| event_days_to_1_1_0  |      333 |  25556.88 |        -2481.96 |        -2512.59 |             10.17 |          60.06 |            1.79 |       76.75 |
| skip_fomc_after_1330 |      327 |  25924.82 |        -2481.96 |        -2558.71 |             10.13 |          59.94 |            1.75 |       79.28 |
| cpi_days_to_1_1_1    |      333 |  25395.48 |        -2481.96 |        -2512.59 |             10.11 |          59.76 |            1.75 |       76.26 |
| skip_fomc_days       |      318 |  25661.14 |        -2481.96 |        -2558.71 |             10.03 |          60.06 |            1.76 |       80.70 |
| skip_all_event_days  |      301 |  24128.28 |        -2481.96 |        -2512.59 |              9.60 |          60.13 |            1.78 |       80.16 |
| skip_cpi_days        |      315 |  24075.76 |        -2481.96 |        -2512.59 |              9.58 |          59.68 |            1.74 |       76.43 |

## Read

- Best event-calendar row: **event_days_to_1_1_1** at 10.24 Net/Stress versus base 10.18.
- Treat this as a first-pass date audit only; CPI/FOMC labels do not include surprise magnitude, press conference windows, or other macro releases.

## Files

- `event_calendar.csv`
- `event_scenario_matrix.csv`
- `campaigns_on_event_days.csv`