# EURUSD Monthly ORB TP25/1R/runner (broker-like)

Shared: OR=3, max 2/month, **1 @ 0.25R / 1 @ 1R / 1 runner**, BE after TP1,
daily-close SL, month-end flatten. Fee $7.00/unit.

| Entry mode | Trades | Units | Net | Close DD | Stress DD | Net/Stress |
|---|---:|---:|---:|---:|---:|---:|
| oco | 473 | 1419 | $-44663.00 | $-102217.25 | $-102712.25 | -0.43 |
| first_break_opposite | 173 | 519 | $31394.50 | $-42746.00 | $-44792.00 | 0.70 |

- **oco**: arm OCO @ ORH/ORL right after OR forms.
- **first_break_opposite**: ignore first OR break, then arm stop the other way.

Compare prior limit-retest scaleout3: ~+$22k / 0.45 Net/Stress.
