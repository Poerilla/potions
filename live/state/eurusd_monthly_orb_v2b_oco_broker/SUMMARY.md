# EURUSD Monthly ORB v2b OCO (broker-like stress)

Engine + PaperBroker on Histdata daily EURUSD.
OCO @ ORH/ORL, max 2 fills/month, TP1=1R / TP2=2R, BE after TP1,
daily-close SL (wicks allowed), flatten month-end. Fee $7.00/unit.

| Structure | Trades | Units | Net | Close DD | Stress DD | Net/Stress |
|---|---:|---:|---:|---:|---:|---:|
| 1_1_2 | 419 | 1676 | $-103314.00 | $-214383.00 | $-216715.00 | -0.48 |
| 1_1_1 | 417 | 1251 | $-80681.00 | $-145810.00 | $-147559.00 | -0.55 |
| 1_1_0 | 471 | 942 | $-60461.00 | $-110309.00 | $-111475.00 | -0.54 |

## Runner value

Runner **does not help** under broker stress — it adds loss and DD:

- **S_1_1_2 vs S_1_1_0** (2-unit runner): ΔNet=$-42,853, Stress DD worse by ~$105k
- **S_1_1_1 vs S_1_1_0** (1-unit runner): ΔNet=$-20,220, Stress DD worse by ~$36k
- **Best of the three:** S_1_1_0 (no runner), still **fails** promote (~−$60k / −0.54 Net/Stress)

## Notes

- First stress pass had a fill-callback bug (no TP orders). Fixed; numbers above are the corrected run.
- Pandas research on the same daily CSV is still green (S_1_1_2 ~+$95k, S_1_1_0 ~+$293k) — path differs (same-day re-entry, no slip). Broker stress is the gate.
- Prior limit-retest scaleout3 remains ahead: ~+$22k / 0.45 Net/Stress.
