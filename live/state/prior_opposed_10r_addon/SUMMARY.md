# Prior-opposed + single 10R runner add-on

Frozen S_1_1_3 book (1 TP1 + 1 TP2 + 3 EOD runners). **Add one** contract targeting **10×R**
(R = campaign wide-stop / TP1 distance; BE after TP1).

| market | baseline net | addon net | combined | base N/S | new N/S | Δ N/S | 10R hits | promote? |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `us30` | $6323 | $1109 | $7432 | 0.59 | **0.69** | +0.10 | 1 (0%) | YES |
| `nas100` | $923 | $813 | $1736 | 0.12 | **0.22** | +0.10 | 5 (2%) | YES |
| `nq` | $1330920 | $246049 | $1576969 | 19.40 | **22.54** | +3.14 | 1 (0%) | YES |
| `mnq` | $128360 | $24227 | $152588 | 18.44 | **21.51** | +3.07 | 1 (0%) | YES |

## Stance

- **NQ/MNQ:** optional promote as +1 inventory (ΔN/S ~+3). Edge is EOD marks after BE, not 10R hits (~0.2%).
- **US30/NAS100:** do **not** promote — ΔN/S tiny; absolute N/S still <1. Prior-opposed gate remains weak.
- Stress model is optimistic (published stress + one-unit −R). True concurrent stack may be higher.
- Artifacts: `summary.csv`, per-market `addon_units.csv` (exit-reason breakdown in EMAIL).

