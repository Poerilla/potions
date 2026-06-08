# MNQ Prior-Opposed v2b Event Calendar Audit

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
| base_1_1_3           |      353 | 113547.50 |        -3493.50 |        -4654.50 |             24.40 |          68.56 |            2.61 |      321.66 |
| cpi_days_to_1_1_1    |      353 | 112957.50 |        -3488.50 |        -4654.50 |             24.27 |          68.84 |            2.68 |      319.99 |
| skip_cpi_days        |      335 | 113463.00 |        -3562.00 |        -4690.50 |             24.19 |          70.15 |            2.80 |      338.70 |
| fomc_days_to_1_1_1   |      353 | 111389.50 |        -3194.50 |        -4654.50 |             23.93 |          68.84 |            2.62 |      315.55 |
| event_days_to_1_1_1  |      353 | 110799.50 |        -3189.50 |        -4654.50 |             23.80 |          69.12 |            2.69 |      313.88 |
| event_days_to_1_1_0  |      353 | 109425.50 |        -3037.50 |        -4654.50 |             23.51 |          69.41 |            2.72 |      309.99 |
| skip_fomc_days       |      337 | 109273.00 |        -2924.00 |        -4654.50 |             23.48 |          68.84 |            2.64 |      324.25 |
| skip_all_event_days  |      319 | 109188.50 |        -3135.50 |        -4690.50 |             23.28 |          70.53 |            2.84 |      342.28 |
| skip_fomc_after_1330 |      345 | 108245.50 |        -3572.00 |        -4654.50 |             23.26 |          68.41 |            2.56 |      313.76 |

## Read

- Best event-calendar row: **base_1_1_3** at 24.40 Net/Stress versus base 24.40.
- Treat this as a first-pass date audit only; CPI/FOMC labels do not include surprise magnitude, press conference windows, or other macro releases.

## Files

- `event_calendar.csv`
- `event_scenario_matrix.csv`
- `campaigns_on_event_days.csv`