# Combined ORB: London + NY Sessions (v2)

Opening Range Breakout backtests for **London** and **NY** sessions on
**MNQ and MYM**, using the v2 pre-placed OCO stop entry model (orders
rest at the exchange from the close of the opening range onward).

See `../scripts/validation.md` for the full v1→v2 context, and
`../archived/README.md` for the legacy v1 variants.

## Sessions

| Session | Opening Range (NY time) | Trade Window |
|---|---|---|
| **London** | 2:00–2:15 AM  | 2:15 AM – 11:00 AM |
| **NY**     | 9:30–9:45 AM  | 9:45 AM – 4:00 PM |

## Entry model (same for both sessions)

At the **close of the opening range**, place a buy-stop at `RH + 1 tick`
and a sell-stop at `RL - 1 tick` as an OCO pair:

- First trigger fills intrabar (entry = `trigger ± 1 tick slippage`)
- The other order is auto-canceled
- Attach bracket: target = `Entry ± Range`, stop = opposite range boundary
- Re-arm OCO after each trade (max 2 per session per day)
- Force-close at the session's `trade_end` bar

## Performance — v2 results, 1 contract, net of $1.50 RT

### MNQ (2021-03-04 → 2026-04-23)

| Session | Trades | Win% | Gross (pts) | Net $ | Max DD $ |
|---|---|---|---|---|---|
| **London** | 2,656 | 65.8% | +17,199 | **$30,414** | −$1,105 |
| **NY**     | 2,517 | 65.3% | +61,086 | **$118,397** | −$2,197 |
| **Combined** | 5,173 | 65.6% | +78,285 | **$148,812** | **−$2,027** |

### MYM (2019-05-06 → 2026-03-06)

| Session | Trades | Win% | Gross (pts) | Net $ | Max DD $ |
|---|---|---|---|---|---|
| **London** | 3,528 | **66.0%** | +35,146 | **$12,281** | **−$476** |
| **NY**     | 3,292 | 63.5% | +101,053 | **$45,588** | −$1,755 |
| **Combined** | 6,820 | 64.8% | +136,199 | **$57,870** | **−$1,227** |

MYM London has the highest win rate (66.0%) and tightest max DD ($476)
of any session/product combination. Volume in the 2:00-2:15 AM ET range
averages 322 contracts — thin but sufficient for micro-futures fills.

For each product the combined London+NY drawdown is smaller than either
session alone — the two sessions rarely drawdown on the same day
(correlation ≈ +0.08-0.28).

## v2d (fade) for London + NY

Same session windows as v2b; outputs `*_orb_results_v2d.csv` per session.
Used with `build_adaptive_50_150_portfolio.py` for adaptive backtests.

```bash
python combined_orb/scripts/london_ny_orb_v2d_fade.py --product MNQ
python combined_orb/scripts/london_ny_orb_v2d_fade.py --product MYM
```

## Adaptive 50/150 (portfolio builder)

After v2b (`london_ny_orb_stops.py`) and v2d (`london_ny_orb_v2d_fade.py`)
CSVs exist:

```bash
python combined_orb/scripts/build_adaptive_50_150_portfolio.py
```

Writes `mnq_london_adaptive_50_150.csv`, `mym_ny_adaptive_50_150.csv`,
refreshes `../mnq/v2d/mnq_orb_results_adaptive_50_150.csv`, and
`../orb-portfolio/adaptive_portfolio_combined_50_150.csv`.

## Usage

```bash
# MNQ (default)
python combined_orb/scripts/london_ny_orb_stops.py

# MYM
python combined_orb/scripts/london_ny_orb_stops.py --product MYM

# Tweak slippage (in ticks)
python combined_orb/scripts/london_ny_orb_stops.py --slip-ticks 2

# Custom output directory
python combined_orb/scripts/london_ny_orb_stops.py --output-dir /tmp/orb
```

## Outputs

MNQ (no prefix):

| File | Description |
|---|---|
| `london_orb_results_stops.csv` | MNQ London session trades (v2) |
| `ny_orb_results_stops.csv`     | MNQ NY session trades (v2) |
| `combined_orb_results_stops.csv` | MNQ both sessions merged |

MYM (prefixed):

| File | Description |
|---|---|
| `mym_london_orb_results_stops.csv` | MYM London session trades (v2) |
| `mym_ny_orb_results_stops.csv`     | MYM NY session trades (v2) |
| `mym_combined_orb_results_stops.csv` | MYM both sessions merged |

Every CSV has `Net_$` and `Cumulative_$` columns computed at 1 contract
net of a $1.50 round-turn commission, so sizing to N contracts is
`× N`.

## Live-execution considerations for London

- **MNQ liquidity**: during 2:15–11:00 AM is thinner than RTH, especially
  before 4:00 AM. Stop-market fills still reliable but bid/ask spreads
  can widen. Expect ~1-2 tick additional slippage vs NY session.
- **MYM liquidity**: at ~70% of NY session volume. 2:00-2:15 AM range
  window averages only 322 contracts of volume — fills are still reliable
  but consider 2-tick slippage in worst-case modeling rather than 1 tick.
- **Bid/ask spread**: during overnight sessions spread can widen to 2-3
  ticks on low-volume minutes. The 1-tick slippage assumption in the
  backtest may be optimistic in this window.
- **Economic releases**: European macro (ECB, CPI, PMI) often hit during
  the London window and can produce fast moves. Stop-market is the
  right order type — do not use stop-limit during this session.
- **News avoidance (optional filter)**: FOMC, CPI, NFP and other high-impact
  events still occur during the overlap. For the execution test, treat
  these as normal trading days; for production, consider a pre-release
  pause.

## Scripts

| Script | Role |
|---|---|
| `scripts/london_ny_orb_stops.py` | **v2 canonical** — pre-placed OCO stop entry for both sessions |
| `../archived/v1_scripts/` | Old v1 London+NY script for reference |

## Archived v1 comparison (for reference)

| Session | v1 trades | v1 win% | v1 net @ 1 MNQ |
|---|---|---|---|
| London | 2,489 | 63.2% | ~$24,400 |
| NY     | 1,997 | 60.4% | ~$63,200 |

v2 is strictly better on every metric. See `../archived/README.md` for why.
