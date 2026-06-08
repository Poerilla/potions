# ORB Multi-Strategy Portfolio (v2b honest)

> **2026-04-25 revision**: this folder previously reported a $193k
> 4-strategy portfolio P/L — based on the **buggy v2a backtest**. The
> v2 same-direction re-entry bug has been fixed (now called v2b); see
> `../scripts/validation.md` Section 2 for the full correction
> context.
>
> Honest portfolio numbers are below. **Only MNQ NY is profitable**;
> the other three strategies are net-negative.

## Honest portfolio performance (v2b)

### Per-strategy (1 contract each)

| Strategy | Trades | Win% | Net $ | Annual | Max DD |
|---|---|---|---|---|---|
| **MNQ NY (only positive)** | 1,991 | 54.0% | **+$15,877** | ~$3.1k/yr | −$4,716 |
| MNQ London | 2,473 | 52% | −$1,738 | net loss | −$5,328 |
| MYM NY | 2,627 | 52.0% | −$1,620 | net loss | −$6,564 |
| MYM London | 3,265 | 53% | −$3,840 | net loss | −$4,381 |

### Combined 1×1×1×1

| Metric | Value |
|---|---|
| Total trades | 10,364 |
| Realized net P/L | **+$8,683** over ~5 years |
| Annual avg | **~$1,690/yr** |
| Max realized DD | −$8,536 |
| 99th-pct Monte-Carlo DD | −$13,936 |
| 99th-pct capital required (3× DD) | $41,808 |
| Annualized ROI on min capital | **~4%** |

**The 4-strategy portfolio underperforms MNQ NY alone.** Adding the
three losing strategies drags realized P/L down ~45% while increasing
required capital ~3×. There is no diversification benefit because
the negative-EV strategies don't offset MNQ NY's losing days — they
just add their own losing days.

## What about the previous "60% diversification benefit"?

The v2a numbers showed combined max DD of $2,223 vs sum-of-individual
$5,533 (60% reduction). That number was real for v2a but it was based
on inflated equity curves. Under v2b with mostly-flat-or-negative
strategies, the picture changes:

| | Standalone Max DD | Sum | Combined |
|---|---|---|---|
| MNQ NY | $4,716 | | |
| MNQ London | $5,328 | | |
| MYM NY | $6,564 | | |
| MYM London | $4,381 | | |
| **Totals** | | **$20,989** | **$8,536** |
| Diversification reduction | | | **59%** |

The diversification reduction in DD is still real (59%), but it's now
diversifying *losses* rather than profits. You're better off
concentrating capital in the only positive-EV strategy.

## Sizing recommendations (v2b)

| Use case | Allocation | Min account | Expected $/yr |
|---|---|---|---|
| **Recommended** | 1× MNQ NY only | **$10,000** | ~$3,100 |
| Aggressive single-strategy | 3× MNQ NY only | $25,000 | ~$9,300 |
| Full v2b portfolio (not recommended) | 1×1×1×1 | $42,000 | ~$1,690 |

The MNQ-NY-only minimum of $10,000 covers the −$4,716 max DD plus
$2,100 overnight initial margin plus ~$3,000 buffer.

## Reproduce

```bash
cd /home/tester/hsm/potions

python scripts/step2_preplaced_stops.py --product MNQ
python scripts/step2_preplaced_stops.py --product MYM
python combined_orb/scripts/london_ny_orb_stops.py --product MNQ
python combined_orb/scripts/london_ny_orb_stops.py --product MYM

python orb-portfolio/monte_carlo.py
python orb-portfolio/monte_carlo.py --mnq-london 0 --mym-ny 0 --mym-london 0   # MNQ NY only
```

## Adaptive 50/150 portfolio (MNQ London + MNQ NY + MYM NY)

All three legs use the **same causal rule**: prior calendar day’s MNQ
daily close — if SMA(50) > SMA(150) trade **v2b** (breakout), else
**v2d** (fade). Regime is always computed from **MNQ** daily data, even
for MYM NY.

| Leg (1 contract) | Trades | Win% | Net $ | Max DD |
|---|---|---|---|---|
| MNQ NY | 1,919 | 54.1% | **+$18,885** | −$3,542 |
| MNQ London | 2,395 | 53.3% | +$336 | −$3,347 |
| MYM NY | 2,606 | 53.0% | +$1,252 | −$4,304 |
| **Combined** (chronological: London → MNQ NY → MYM NY per day) | 6,920 | — | **+$20,473** | −$5,624 |

Reproduce adaptive CSVs and Monte Carlo:

```bash
cd /home/tester/hsm/potions

python combined_orb/scripts/london_ny_orb_v2d_fade.py --product MNQ
python combined_orb/scripts/london_ny_orb_v2d_fade.py --product MYM
python combined_orb/scripts/build_adaptive_50_150_portfolio.py

python orb-portfolio/monte_carlo.py --adaptive
```

Shuffle-based MC leaves **total P/L unchanged** (sum of trades); it
only reorders paths to study **drawdown** sensitivity. Use
`monte_carlo_stats.csv` for DD percentiles.

## Files

| File | Description |
|---|---|
| `monte_carlo.py` | v2b Monte Carlo; `--adaptive` uses `adaptive_portfolio_combined_50_150.csv` |
| `adaptive_portfolio_combined_50_150.csv` | All adaptive legs, sorted by date + session order |
| `monte_carlo_equity.png` | Equity fan (default 1×1×1×1) |
| `monte_carlo_drawdown.png` | DD distribution |
| `monte_carlo_final_pl.png` | Terminal P/L distribution |
| `monte_carlo_stats.csv` | Percentile stats |
| `portfolio_simulation.md`, `bias_aligned_*`, `portfolio_equity_*`, `capital_requirements.csv` | Legacy v1 artifacts retained for history (do not use for sizing) |

## Archived

Old v2a-based portfolio numbers and charts are preserved in
`../archived/v2a_results/` and `../archived/v1_scripts/monte_carlo.py`.
The previous version of this README claimed $193k portfolio P/L, $40k
annual return, $8,100 minimum account, and 100% probability of $200k+
profit. Those numbers were based on the buggy v2a CSVs. They are
superseded by the table above.
