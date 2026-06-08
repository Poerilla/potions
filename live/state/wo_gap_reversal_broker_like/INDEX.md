# WO Gap Reversal — cross-market broker-like replay

Causal **StrategyPlugin** replay through Engine + PaperBroker on **1h** bars.
Rules match the NQ chart study: 55% WO gap, limit retest, swing filter, 2ct scale-out.

| Market | Units | Trades | Net USD | Win % | PF | Closed DD | Stress DD | Max open | Net/Stress | Audit |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| NQ | 972 | 486 | $80,472.00 | 39.9% | 1.20 | $-33,635.00 | $-34,099.00 | 2 | 2.36 | [nq_wo_gap_reversal](audits/nq_wo_gap_reversal/reports/MTM_AUDIT.md) |
| MNQ | 342 | 171 | $5,931.50 | 35.7% | 1.43 | $-2,578.00 | $-2,698.00 | 2 | 2.20 | [mnq_wo_gap_reversal](audits/mnq_wo_gap_reversal/reports/MTM_AUDIT.md) |
| ES | 902 | 451 | $120,647.00 | 49.2% | 1.19 | $-44,937.00 | $-45,687.00 | 2 | 2.64 | [es_wo_gap_reversal](audits/es_wo_gap_reversal/reports/MTM_AUDIT.md) |
| YM | 1026 | 513 | $9,651.00 | 32.9% | 1.09 | $-11,918.50 | $-12,409.50 | 2 | 0.78 | [ym_wo_gap_reversal](audits/ym_wo_gap_reversal/reports/MTM_AUDIT.md) |
| MES | 246 | 123 | $7,394.75 | 45.1% | 1.35 | $-3,302.50 | $-3,315.00 | 2 | 2.23 | [mes_wo_gap_reversal](audits/mes_wo_gap_reversal/reports/MTM_AUDIT.md) |
| MYM | 476 | 238 | $-1,146.00 | 29.6% | 0.93 | $-1,635.00 | $-1,670.00 | 2 | -0.69 | [mym_wo_gap_reversal](audits/mym_wo_gap_reversal/reports/MTM_AUDIT.md) |