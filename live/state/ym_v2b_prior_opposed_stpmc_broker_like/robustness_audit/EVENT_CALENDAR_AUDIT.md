# YM Prior-Opposed v2b Event Calendar Audit

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
| base_1_1_3           |      347 | 320190.00 |       -24017.50 |       -24298.75 |             13.18 |          59.65 |            1.89 |      922.74 |
| fomc_days_to_1_1_1   |      347 | 315728.50 |       -24017.50 |       -24298.75 |             12.99 |          59.94 |            1.89 |      909.88 |
| skip_fomc_after_1330 |      340 | 315366.25 |       -24017.50 |       -24298.75 |             12.98 |          59.71 |            1.89 |      927.55 |
| cpi_days_to_1_1_1    |      347 | 308229.50 |       -24017.50 |       -24298.75 |             12.68 |          59.65 |            1.88 |      888.27 |
| event_days_to_1_1_1  |      347 | 305945.00 |       -24017.50 |       -24298.75 |             12.59 |          59.94 |            1.89 |      881.69 |
| skip_fomc_days       |      330 | 304820.00 |       -24017.50 |       -24298.75 |             12.54 |          59.70 |            1.88 |      923.70 |
| event_days_to_1_1_0  |      347 | 298822.50 |       -24017.50 |       -24298.75 |             12.30 |          59.94 |            1.89 |      861.16 |
| skip_cpi_days        |      328 | 287792.50 |       -24017.50 |       -24298.75 |             11.84 |          59.45 |            1.85 |      877.42 |
| skip_all_event_days  |      312 | 276985.00 |       -24017.50 |       -24298.75 |             11.40 |          59.62 |            1.86 |      887.77 |

## Read

- Best event-calendar row: **base_1_1_3** at 13.18 Net/Stress versus base 13.18.
- Treat this as a first-pass date audit only; CPI/FOMC labels do not include surprise magnitude, press conference windows, or other macro releases.

## Files

- `event_calendar.csv`
- `event_scenario_matrix.csv`
- `campaigns_on_event_days.csv`