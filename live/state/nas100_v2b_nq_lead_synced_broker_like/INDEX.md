# NAS100 v2b Prior-Opposed / Provisional ST+PMC Broker-Like Replay (nq_lead_sync)

True `Engine + PaperBroker + StrategyPlugin` replay.

**Dollar standard:** **×40** on native `$1`/pt CFD (`POINT_VALUE` reading). Shape (WR/PF) unchanged.

| | Native `$1`/pt | **×40 standard** |
|---|---:|---:|
| Net | $21,129.54 | **$845,182** |
| Closed DD | −$1,177.54 | **−$47,102** |
| Win% / PF | 67.86 / 2.155 | same |

| Trades | Units | Net (native) | Closed DD (native) | Win % | PF |
|---:|---:|---:|---:|---:|---:|
| 280 | 840 | $21129.54 | $-1177.54 | 67.86 | 2.155 |

## Entry sizing under ×40

Replay still runs `S_1_1_1` (entry **3** / tp1 **1** / tp2 **1**) at `$1`/pt.

×40 economics ≡ either:

| Mode | Entry | TP1 | TP2 | $/pt | $ per index point at entry |
|------|------:|----:|----:|-----:|---:|
| **A (preferred reading)** | 3 | 1 | 1 | **$40** | **$120** |
| B (same $ at `$1`/pt) | 120 | 40 | 40 | $1 | $120 |

Vs NQ prior-opposed `S_1_1_3` @ `$20`/pt: NQ entry = **$100**/pt; NAS×40 entry = **$120**/pt (~1.2× NQ entry dollars).

## Causality / gate

- Regime sessions replayed: **310**
- Replay start: **2021-03-04**
- Gate mode: **nq_lead_sync**
- Prior-opposite entries found: **280 / 280**
- Causal violations: **29**
- Direction mix: **115 long / 165 short**

Files:

- `summary.csv`
- `states/nas100_v2b_nq_lead_synced_S_1_1_1/`

## NQ-lead sync

- Sync ceiling: **60s** (early Δ **30s**)
- Entered campaigns (audit): **280**
- Skipped campaigns (audit): **29** (28 `nq_already_scaled`, 1 `nq_already_stopped`)
- CFD-local exits: `S_1_1_1` + EOD on NAS100 after synced entry
- Dollar reporting standard: **×40** (not ×20 PV, not MTM-DD ratio)
- Original NQ / standalone NAS100 prior-opposed strategies unchanged

## Compare vs standalone NAS100 prior-opposed

| Book | Trades | Net native | Net ×40 | Win% | PF | Closed DD native |
|---|---:|---:|---:|---:|---:|---:|
| NAS100 standalone PO (`S_1_1_3`) | 310 | $923 | $36,920 | 47.10 | 1.019 | $-7810 |
| NAS100 NQ-lead synced (`S_1_1_1`) | 280 | $21,130 | **$845,182** | 67.86 | 2.155 | $-1178 |

Overlap days **263**: synced day-PnL sum **$16,877** native (**$675k** ×40) vs standalone **$3,087** native (**$123k** ×40).

NQ futures book (native `$20`/pt) for reference: trades=352 net=$1,175,785 wr=69.32 pf=2.633.

## Combined with NQ prior-opposed best (resting_limit)

Portfolio = **NQ resting_limit** (causal baseline, native) + **NAS100 NQ-lead ×40**.

NAS lead was driven from the banked NQ campaign book; this is a **two-sleeve portfolio**, not a re-gated joint system.

| Sleeve | Campaigns | Net | WR% | PF | Closed DD | MTM / stress DD |
|---|---:|---:|---:|---:|---:|---:|
| NQ resting_limit | 432 | $1,330,920 | 65.97 | 2.34 | −$68,110 | **−$68,610** |
| NAS100 NQ-lead ×40 | 280 | $845,183 | 67.86 | 2.22 | −$47,102 | −$47,102 |
| **Combined** | **712** | **$2,176,103** | **66.71** | **2.29** | **−$81,242** | **−$115,712** (additive) |

| Combined ratio | |
|---|---:|
| Net / \|day closed DD\| | **26.8** |
| Net / \|additive MTM\| | **18.8** |

Closed DD is from a **day-aggregated joint equity** (unit `net_usd`, NAS×40). Additive MTM is \|NQ stress\| + \|NAS×40 DD\| (same-time worst case; true joint open MTM not re-simulated).

Artifact: `combined_with_nq_resting_limit.csv`
