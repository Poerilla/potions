# NQ OR-norm extreme size-up (5× / 10×) + liquidity

Study parent: `futures_intraday_hp_sizeup_v1`
Book: **nq_prior_opposed_rl** — NQ prior-opposed RL, normal opening 15m range (`or_norm`).
Hub: `live/state/futures_intraday_hp_nq_or_norm_extreme_size`

Baseline book size on tape: **entry_qty=5** (v2b `S_1_1_3`). HP campaigns: **129** (29.9% of book).

**Sensitivity only** — linear scaling of HP campaign nets. Null-suite standing exists only for **1.25×** and **exact 2×** (provisional). **Do not promote 5×/10×** from this table.

## Size sensitivity

| Mult | HP qty | Net | Stress | N/S | ΔN/S | stress× | ≈IM HP |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 1× | 5 | $1,330,920 | $55,318 | **24.06** | +0.00 | 1.00 | $100,000 |
| 1.2× | 6 | $1,476,408 | $51,345 | **28.75** | +4.70 | 0.93 | $120,000 |
| 2× | 10 | $1,912,872 | $52,752 | **36.26** | +12.20 | 0.95 | $200,000 |
| 3× | 15 | $2,494,825 | $71,365 | **34.96** | +10.90 | 1.29 | $300,000 |
| 4× | 20 | $3,076,778 | $89,978 | **34.20** | +10.13 | 1.63 | $400,000 |
| 5× | 25 | $3,658,730 | $109,380 | **33.45** | +9.39 | 1.98 | $500,000 |
| 10× | 50 | $6,568,492 | $208,655 | **31.48** | +7.42 | 3.77 | $1,000,000 |

Peak N/S row: **2×** at N/S **36.26** (ΔN/S +12.20).

## Liquidity footprint (HP entries vs NQ 1m volume)

Contracts assumed = `entry_qty × mult` on HP days. Shares use entry minute volume, ±5m window, and full RTH day volume from the NQ 1m DBN.

| Mult | qty | med %% entry bar | p90 %% bar | %% days >10%% bar | %% >25%% | %% >50%% | med %% ±5m | med %% RTH | med notional | ≈IM |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1× | 5 | 0.2% | 0.3% | 0% | 0% | 0% | 0.02% | 0.001% | $1,763,688 | $100,000 |
| 1.2× | 6 | 0.2% | 0.3% | 0% | 0% | 0% | 0.03% | 0.001% | $2,116,425 | $120,000 |
| 2× | 10 | 0.3% | 0.5% | 0% | 0% | 0% | 0.04% | 0.002% | $3,527,375 | $200,000 |
| 3× | 15 | 0.5% | 0.8% | 0% | 0% | 0% | 0.07% | 0.003% | $5,291,062 | $300,000 |
| 4× | 20 | 0.7% | 1.1% | 0% | 0% | 0% | 0.09% | 0.004% | $7,054,750 | $400,000 |
| 5× | 25 | 0.9% | 1.3% | 0% | 0% | 0% | 0.11% | 0.005% | $8,818,438 | $500,000 |
| 10× | 50 | 1.8% | 2.7% | 1% | 0% | 0% | 0.22% | 0.011% | $17,636,875 | $1,000,000 |

## Stance

- Best economic N/S on this linear tape remains near **2×** (36.26), not 5×/10× (5× N/S 33.45, 10× N/S 31.48) — larger size adds net but **dilutes N/S** after 2×.
- Liquidity (NQ 1m): **not the blocker**. At **5×** (qty=25) median entry-bar share **0.9%** (p90 **1.3%**); at **10×** (qty=50) median **1.8%** / p90 **2.7%**. Days consuming >25% of the entry minute: 5× **0%**, 10× **0%**. Median RTH share stays ≪0.1%. Margin/notional footprint grows linearly (≈IM $500,000 @5× / $1,000,000 @10×) — capital constraint, not tape thinness.
- Operational read: **stay at provisional 1.25× / controlled-paper 2×**. 5×/10× are **N/S-suboptimal** vs 2× and unvalidated (no null suite); liquidity alone does not veto them on CME NQ.
- Next if pursuing size: dedicated null suite at the intended mult (not inferred), plus impact/queue model — not more linear scaling.

## Files

- `size_sensitivity_5_10.csv`
- `liquidity_footprint.csv`
- `hp_entry_volume_context.csv`
- `EMAIL.txt`
