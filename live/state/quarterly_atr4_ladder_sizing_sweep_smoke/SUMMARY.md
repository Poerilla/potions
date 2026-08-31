# Quarterly ATR4 ladder — runner-heavy sizing sweep

Stress top-5 books; ladder ATR rungs fixed (+2/+4/+6/+8); only contract
allocation changes. Runner-heavy cells target residual ≥8.

Contribution priors (board +PnL share): flatten 30.8% · tp4 24.9% · tp3 19.9% · tp2 16.0% · tp1 8.5%.

`net_per_10ct` / `ns_risk_norm` scale PnL & stress to a 10-contract entry so larger books are comparable to baseline `2/2/2/2/2`.

## Per-market ranking (by ns_risk_norm)

### GBPUSD

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|

### NAS100

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `1/2/2/3/8` | 16 | $93,167 | $0 | 5.00 | $58,230 | 0.00 | 35% | contrib-shaped among scales; runner=8 (~share-weighted) |

### NQ

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|

### EURUSD

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|

### XAUUSD

| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |
|---|---:|---:|---:|---:|---:|---:|---:|---|

## Board aggregate (sum net/10ct; worst stress/10ct)

| sizing | Σ net/10ct | Σ stress/10ct | N/Sₙ | note |
|---|---:|---:|---:|---|

Hub: `live/state/quarterly_atr4_ladder_sizing_sweep_smoke`
