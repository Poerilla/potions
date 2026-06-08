# Weekly 50% + MA500 Bias Retest Broker-Like Replay

Strict StrategyPlugin replay through Engine + PaperBroker on 15-minute bars. Orders activate only after the confirming bar closes, fills use the broker realism defaults, and any open position is flattened with a market order on the first bar of the next week.

This is intentionally stricter than the standalone research simulator and should be treated as the hardening result, not a point-for-point reproduction of the research tape.

| Market | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Win % | PF | Net / Stress | Audit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| NQ | 516 | 516 | $-9,129.00 | $-66,362.00 | $-66,667.00 | 1 | 32.6% | 0.97 | -0.14 | [audits/nq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/nq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
| YM | 505 | 505 | $-8,095.00 | $-15,510.50 | $-15,600.50 | 1 | 17.0% | 0.93 | -0.52 | [audits/ym_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/ym_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
| MNQ | 232 | 232 | $-2,801.00 | $-7,075.25 | $-7,097.75 | 1 | 16.4% | 0.88 | -0.39 | [audits/mnq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/mnq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |