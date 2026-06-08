# ES Prior-Opposed v2b Event Calendar Audit

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
| skip_all_event_days  |      218 | 339927.50 |       -17907.50 |       -19342.50 |             17.57 |          63.76 |            2.34 |     1559.30 |
| skip_cpi_days        |      228 | 339277.50 |       -17907.50 |       -19335.00 |             17.55 |          64.04 |            2.30 |     1488.06 |
| event_days_to_1_1_0  |      245 | 347871.50 |       -19353.50 |       -20666.00 |             16.83 |          63.67 |            2.29 |     1419.88 |
| event_days_to_1_1_1  |      245 | 348143.50 |       -22219.00 |       -23531.50 |             14.79 |          63.67 |            2.25 |     1420.99 |
| cpi_days_to_1_1_1    |      245 | 344863.50 |       -22219.00 |       -23531.50 |             14.66 |          63.67 |            2.23 |     1407.61 |
| fomc_days_to_1_1_1   |      245 | 352120.50 |       -27950.00 |       -29262.50 |             12.03 |          63.67 |            2.21 |     1437.23 |
| skip_fomc_days       |      234 | 349720.00 |       -27950.00 |       -29262.50 |             11.95 |          63.68 |            2.22 |     1494.53 |
| skip_fomc_after_1330 |      239 | 348957.50 |       -27950.00 |       -29262.50 |             11.93 |          63.60 |            2.19 |     1460.07 |
| base_1_1_3           |      245 | 348687.50 |       -27950.00 |       -29262.50 |             11.92 |          63.67 |            2.18 |     1423.21 |

## Read

- Best event-calendar row: **skip_all_event_days** at 17.57 Net/Stress versus base 11.92.
- Treat this as a first-pass date audit only; CPI/FOMC labels do not include surprise magnitude, press conference windows, or other macro releases.

## Files

- `event_calendar.csv`
- `event_scenario_matrix.csv`
- `campaigns_on_event_days.csv`