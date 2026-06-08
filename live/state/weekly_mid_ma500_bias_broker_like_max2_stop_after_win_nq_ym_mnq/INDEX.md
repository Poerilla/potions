# Weekly 50% + MA500 Bias Retest Broker-Like Replay

Strict StrategyPlugin replay through Engine + PaperBroker on 15-minute bars. Orders activate only after the confirming bar closes, fills use the broker realism defaults, and any open position is flattened with a market order on the first bar of the next week.

This is intentionally stricter than the standalone research simulator and should be treated as the hardening result, not a point-for-point reproduction of the research tape.

| Market | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Win % | PF | Net / Stress | Audit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| NQ | 572 | 572 | $59,769.50 | $-29,893.00 | $-30,048.00 | 1 | 30.6% | 1.16 | 1.99 | [audits/nq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/nq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
| YM | 736 | 736 | $8,466.00 | $-9,969.00 | $-10,004.00 | 1 | 19.0% | 1.06 | 0.85 | [audits/ym_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/ym_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |
| MNQ | 330 | 330 | $4,045.75 | $-3,027.50 | $-3,042.00 | 1 | 20.9% | 1.17 | 1.33 | [audits/mnq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md](audits/mnq_weekly_mid_ma500_bias/reports/MTM_AUDIT.md) |