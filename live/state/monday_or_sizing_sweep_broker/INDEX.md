# Monday OR sizing sweep — broker-like hub

**Phase 1 complete (2026-07-21):** 27 cells × **all 6** instruments (EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD) through Engine + PaperBroker.  
Ranked by **≈USD Net/Stress**. Driver: `live/monday_or_sizing_sweep_broker.py`.

## Cross-pair broker #1

| Pair | Baseline `M1_S1_R1` | **Broker #1** | N/S | ≈USD net | Stress |
|---|---|---|---:|---:|---:|
| **USDJPY** | 4.27 · +$138k | **`M2_S3_R1`** | **8.20** | +$219k | −$27k |
| **GBPUSD** | 1.87 · +$202k | **`M1_S1_R2`** | **2.67** | +$231k | −$87k |
| **XAUUSD** | 1.04 · +$260k | **`M2_S2_R3`** | **1.90** | +$438k | −$230k |
| **AUDJPY** | 1.07 · +$59k | **`M1_S2_R2`** | **1.83** | +$96k | −$52k |
| **EURUSD** | 0.83 · +$76k | **`M1_S2_R2`** | **1.74** | +$123k | −$71k |
| **XAGUSD** | −1.00 · −$195k | **`M2_S2_R3`** | **−0.97** | −$224k | −$230k |

Full top-5 tables: [`SUMMARY_ALL.md`](SUMMARY_ALL.md).

### Structure of winners

| Tag | Main | Shifted | Max primary/week | Who wins |
|---|---|---|---|---|
| `M2_S3_R1` | 3=(1@30,2@50) | 4 | 2 | USDJPY |
| `M1_S1_R2` | 3=(2@30,1@50) | 3 | 3 | GBPUSD |
| `M2_S2_R3` | 3=(1@30,2@50) | 2 | ∞ | XAU (heat!), XAG (fail) |
| `M1_S2_R2` | 3=(2@30,1@50) | 2 | 3 | EURUSD, AUDJPY |

## Stance

- **USDJPY-first** sleeve (`M2_S3_R1` / near-tie `M2_S3_R2`).
- **GBPUSD** second book at `M1_S1_R2` (matched size, max 3/week).
- **EURUSD / AUDJPY** share light-shifted `M1_S2_R2`; EURUSD beats ST+PMC (1.49) on N/S.
- **XAUUSD** can print dollars with `M2_S2_R3` but stress (~−$230k) makes CE fragile — not a clean sleeve.
- **XAGUSD** reject at every size.

## Files

| Path | Content |
|---|---|
| [`SUMMARY_ALL.md`](SUMMARY_ALL.md) | Cross-pair #1 + top 5 each |
| [`SUMMARY.md`](SUMMARY.md) | EURUSD full 27 |
| [`SUMMARY_usdjpy.md`](SUMMARY_usdjpy.md) / `_gbpusd` / `_audjpy` / `_xauusd` / `_xagusd` | Per-pair full tables |
| [`results_all.csv`](results_all.csv) | 162 rows |

*All-pairs broker Phase 1 finished 2026-07-21.*
