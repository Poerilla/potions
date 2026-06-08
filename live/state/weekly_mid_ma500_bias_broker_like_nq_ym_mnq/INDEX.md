# Weekly 50% + MA500 Bias Retest Broker-Like Replay

Strict StrategyPlugin replay through Engine + PaperBroker on 15-minute bars. Orders activate only after the confirming bar closes, fills use the broker realism defaults, and any open position is flattened with a market order on the first bar of the next week.

This is intentionally stricter than the standalone research simulator and should be treated as the hardening result, not a point-for-point reproduction of the research tape.

| Market | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Win % | PF | Net / Stress | Audit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| NQ | 835 | 835 | $18,507.50 | $-44,963.00 | $-44,998.00 | 1 | 28.7% | 1.03 | 0.41 | [audits/nq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/nq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
| YM | 1221 | 1221 | $-2,036.50 | $-28,628.00 | $-28,663.00 | 1 | 18.9% | 1.00 | -0.07 | [audits/ym_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/ym_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
| MNQ | 508 | 508 | $664.00 | $-4,930.75 | $-4,931.75 | 1 | 19.3% | 1.03 | 0.13 | [audits/mnq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/mnq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
