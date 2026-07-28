# Monday OR tune-up — StrategyPlugin broker

Engine + PaperBroker · 15m · 1-tick slip · $1.50/unit.

## Locked / tested cells

| pair | tag | tune-up | net$ | MTM DD$ | N/S | ΔN/S vs P1 | Δnet$ | core? |
|---|---|---|---:|---:|---:|---:|---:|---|
| USDJPY | M2_S3_R1 | sitout+3 + skip Aug/Sep | +293966 | -27726 | 10.60 | +2.40 | +75077 | YES |
| USDJPY | M2_S3_R2 | skip-1-after-2W + skip Aug/Sep | +300288 | -28278 | 10.62 | +2.43 | +72725 | YES |
| EURUSD | M1_S2_R2 | skip-1-after-W | +112075 | -62577 | 1.79 | +0.05 | -11195 | NO (rejected) |
| GBPUSD | M1_S1_R2 | skip-1-after-W | +164421 | -102509 | 1.60 | -1.07 | -66858 | NO (rejected) |
| XAUUSD | M2_S2_R3 | sitout +100 pts + skip Jul/Sep/Dec | +580139 | -172265 | 3.37 | +1.47 | +142200 | YES |

See `CORE_WEEK_SITOUT.md` and `SESSION_2026-07-28.md`.
