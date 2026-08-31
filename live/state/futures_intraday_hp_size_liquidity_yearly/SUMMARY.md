# HP size liquidity quantification + next-best non-NQ @4×

## How we quantify liquidity risk

Participation metrics (higher = more footprint / adverse-selection risk):

1. **Entry-minute share** = `HP qty / volume on the fill minute` (strictest).
2. **±5m share** = qty / volume in entry±5 minutes (absorbs resting-limit fill window).
3. **RTH / day ADV share** = qty / session day volume (capital-market context).
4. **Tail flags**: p90/p95/max participation; fraction of HP days >1% / >5% / >10% / >25% of the bar.
5. **Toy impact proxy**: `sqrt(participation)` (Almgren-style scaling; not a $ impact model).
6. **Capital footprint**: notional (= qty × price × point value) and ≈ initial margin.

Rule of thumb used here: entry-minute p90 ≪ **5%** and almost no days >10% → **tape OK**; risk is then **margin / DD capital**, not CME thinness.

## NQ OR-norm @ **4×** (qty=20) — liquidity scorecard

| Metric | Value | Read |
|---|---:|---|
| Median entry-bar vol | 2,852 | deep NQ minute |
| Median / p90 / p95 / max **% of entry bar** | 0.70% / 1.07% / 1.33% / 4.13% | **comfortable** |
| Days >1% / >5% / >10% / >25% of entry bar | 16% / 0% / 0% / 0% | no crowding |
| Median / p90 % of ±5m | 0.09% / 0.14% | fine |
| Median % of RTH day | 0.00% | negligible |
| Median notional / ≈IM | $7,054,750 / $400,000 | **capital** gate |
| Median / p90 sqrt(participation) | 0.0837 / 0.1032 | low |

**Verdict @4× NQ:** liquidity **does not bind**. Stress/N/S/capital bind first (book stress $89,978, N/S 34.19).

## Next-best non-NQ prior-opposed HP: **ES ST-age** @4× on $250k

Chosen as next-best **prior-opposed** sleeve by 4× N/S among non-NQ A/B candidates (ES 20.19 > YM overnight-middle 13.88). Note: under ΔN/S nulls ES is **NOT VALIDATED** — sensitivity only. (YM ST+PMC Thursday prints higher raw 4× N/S but is Tier C shadow / different family.)

Whole-book @4×: net **$823,220**, stress **$40,780**, N/S **20.19**. $250k → **$1,073,220**. CAGR span **33.9%** (5.00y) / calendar-n **27.5%**.

| Year | N | HP | Net | Stress | N/S | Start | End | Year ret |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2021.0 | 35.0 | 12.0 | $209,280 | $18,180 | 11.51 | $250,000 | $459,280 | 83.7% |
| 2022.0 | 15.0 | 7.0 | $104,705 | $27,530 | 3.80 | $459,280 | $563,985 | 22.8% |
| 2023.0 | 56.0 | 16.0 | $103,008 | $40,780 | 2.53 | $563,985 | $666,992 | 18.3% |
| 2024.0 | 66.0 | 13.0 | $151,650 | $15,455 | 9.81 | $666,992 | $818,642 | 22.7% |
| 2025.0 | 54.0 | 18.0 | $203,115 | $15,312 | 13.27 | $818,642 | $1,021,758 | 24.8% |
| 2026.0 | 19.0 | 2.0 | $51,462 | $18,810 | 2.74 | $1,021,758 | $1,073,220 | 5.0% |

### ES @4× liquidity (daily ADV — no local ES 1m)

| Metric | Value |
|---|---:|
| Qty | 20 |
| Median day volume | 1,638,990 |
| Median / p90 / max **% of day** | 0.00% / 0.00% / 0.00% |
| Days >0.1% / >0.5% / >1% of day | 0% / 0% / 0% |
| Median notional / ≈IM | $4,703,375 / $300,000 |

**ES daily verdict:** day-ADV share is tiny (≪0.1% median). Without 1m we cannot rule out entry-minute crowding, but day capacity is not the issue.

## Cross-check: YM overnight-middle @4× 1m liquidity

| Metric | Value |
|---|---:|
| Qty | 20 |
| Median / p90 / max % entry bar | 3.71% / 8.65% / 90.91% |
| Days >1% / >5% / >10% bar | 97% / 31% / 8% |
| Median % ±5m / RTH | 0.42% / 0.02% |

## Stance

- **NQ @4×:** quantify liquidity via entry-minute / ±5m / RTH participation + tails + sqrt(participation). Result: **no material liquidity issue**; capital/IM (~$400k) and N/S rollback vs 2× are the gates.
- **ES ST-age @4×:** next-best non-NQ prior-opposed by sensitivity N/S; yearly path on $250k above. **NOT VALIDATED** under ΔN/S nulls — research only.
