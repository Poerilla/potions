#!/usr/bin/env python3
"""
Monte Carlo stress on the **v2e** per-leg P/L series (2 MNQ, from sim_v2e_all.py).

Keeps **chronological** trade order. Each simulation re-draws **execution noise**:

  1. **Round-turn fees** (deterministic or optional one fee tier): subtract a fixed
     $/round for every row that has a v2e fill (non–no-fill trade).
  2. **Slippage** — iid Gaussian in **index points** per fill, converted to
     $ at $2/contract × 2 contracts = **$4 per index point** for 2× MNQ. Mean 0.
  3. **Fill error (±range)** — iid **Uniform** in index points, default **±5**,
     same $/pt scaling: models “bad / lucky fills” off the 1m-sim mark.

**No-fill** rows (v2e not filled, ~0 pnl) pay **no** fee and get **no** slip in
this simple model (you never traded).

Output (default: mnq/v2e/data/):
  v2e_monte_friction_stats.csv, v2e_monte_friction_final.png, v2e_monte_friction_dd.png, v2e_monte_friction_equity.png

Regenerate the input series first if needed:
  python3 sim_v2e_all.py
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker

V2E_ROOT = Path(__file__).resolve().parent.parent
POTIONS = V2E_ROOT.parent.parent
DEFAULT_CSV = V2E_ROOT / 'data' / 'mnq_v2e_per_leg.csv'
OUT_DIR = V2E_ROOT / 'data'
DPM = 2.0
NLOT = 2
DOLLARS_PER_INDEX_POINT_V2E = DPM * NLOT  # $4 / index point for 2× MNQ

N_SIMS_DEFAULT = 10_000


def has_v2e_fill(row) -> bool:
    """Traded in v2e sim: fee rows only when status is not no_data and P/L is finite."""
    st = str(row.get('status', ''))
    if st == 'no_data':
        return False
    pnl = row.get('v2e_pnl_5m')
    if pnl is None or (isinstance(pnl, float) and np.isnan(pnl)):
        return False
    pnl = float(pnl)
    stp = int(
        row.get('full_5c_stop', row.get('full_3c_stop', row.get('full_5_lot_stop', 0)))
        or 0
    )
    return (abs(pnl) > 1e-9) or (stp == 1)


def run_friction_monte(
    base_pl: np.ndarray,
    is_fill: np.ndarray,
    n_sims: int,
    fee_5: float,
    slip_std_pts: float,
    fill_err_range_pts: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Returns: curves (n_sims, n), max_dds, finals
    per row adjusted = base + noise - fee (if fill)
    """
    n = len(base_pl)
    curves = np.zeros((n_sims, n), dtype=np.float64)
    max_dds = np.zeros(n_sims, dtype=np.float64)
    finals = np.zeros(n_sims, dtype=np.float64)

    fee_vec = np.where(is_fill, -float(fee_5), 0.0)

    for s in range(n_sims):
        noise = np.zeros(n, dtype=np.float64)
        m = is_fill
        nfill = int(m.sum())
        if nfill > 0 and slip_std_pts > 0:
            slip = rng.normal(0.0, slip_std_pts, size=nfill)
            noise[m] += slip * DOLLARS_PER_INDEX_POINT_V2E
        if nfill > 0 and fill_err_range_pts > 0:
            u = rng.uniform(-fill_err_range_pts, fill_err_range_pts, size=nfill)
            noise[m] += u * DOLLARS_PER_INDEX_POINT_V2E
        # fee is deterministic; base already in series
        adj = base_pl + fee_vec + noise
        eq = np.cumsum(adj)
        curves[s] = eq
        finals[s] = eq[-1]
        peak = np.maximum.accumulate(eq)
        max_dds[s] = (peak - eq).max()
    return curves, max_dds, finals


def plot_equity_fan(
    curves: np.ndarray,
    actual_chronological: np.ndarray,
    det_fee_only: np.ndarray,
    outpath: Path,
    title: str,
    n_sims: int,
) -> None:
    n = curves.shape[1]
    x = np.arange(n)
    p5 = np.percentile(curves, 5, axis=0)
    p25 = np.percentile(curves, 25, axis=0)
    p50 = np.percentile(curves, 50, axis=0)
    p75 = np.percentile(curves, 75, axis=0)
    p95 = np.percentile(curves, 95, axis=0)

    fig, ax = plt.subplots(figsize=(16, 9))
    fig.patch.set_facecolor('#fafafa')
    ax.set_facecolor('#fafafa')
    ax.fill_between(x, curves.min(0), curves.max(0), alpha=0.06, color='#1565c0', label='Min–max')
    ax.fill_between(x, p5, p95, alpha=0.12, color='#1565c0', label='5–95%')
    ax.fill_between(x, p25, p75, alpha=0.25, color='#1565c0', label='25–75%')
    ax.plot(x, p50, color='#1565c0', lw=1.5, label='Median (stochastic slip + fill err + fee)')
    ax.plot(x, det_fee_only, color='#2e7d32', lw=1.2, ls='--', label='Cumulative: base P/L − round-turn fees (no noise)')
    ax.plot(x, actual_chronological, color='#c62828', lw=2, label='Cumulative: frictionless v2e (as in CSV)')
    ax.set_title(
        f'{title}\n({n_sims:,} sims, chronological order, fees + slip N(0,σ) + U(±a) on fills)',
        fontsize=14, fontweight='bold', pad=12,
    )
    ax.set_xlabel('Row index (chronological legs)')
    ax.set_ylabel('Cumulative $ (2 MNQ)')
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
    ax.legend(loc='upper left', framealpha=0.9, fontsize=9)
    ax.grid(True, alpha=0.3)
    ax.axhline(0, color='gray', lw=0.5)
    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def plot_dist(data: np.ndarray, title: str, xlabel: str, outpath: Path, vline: float | None) -> None:
    fig, ax = plt.subplots(figsize=(12, 6))
    fig.patch.set_facecolor('#fafafa')
    ax.set_facecolor('#fafafa')
    ax.hist(data, bins=80, color='#1565c0', alpha=0.7, edgecolor='white', linewidth=0.5)
    if vline is not None:
        ax.axvline(vline, color='#c62828', lw=2, ls='--', label=f"Fee-only (no noise): ${vline:,.0f}")
        ax.legend(fontsize=10)
    p5, p50, p95 = np.percentile(data, [5, 50, 95])
    for pct, val, ls in [(5, p5, ':'), (50, p50, '-'), (95, p95, ':')]:
        ax.axvline(val, color='#2e7d32', lw=1.2, ls=ls, alpha=0.7)
    ax.set_title(title, fontsize=15, fontweight='bold', pad=12)
    ax.set_xlabel(xlabel)
    ax.set_ylabel('Frequency')
    if 'P/L' in xlabel or '$' in xlabel:
        ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f'${v:,.0f}'))
    ax.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    plt.savefig(outpath, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Saved {outpath}")


def main() -> int:
    ap = argparse.ArgumentParser(
        description='v2e Monte Carlo with fees, slippage, and fill error (±index points, 2 MNQ $/pt).',
    )
    ap.add_argument('--csv', type=Path, default=DEFAULT_CSV, help='mnq_v2e_per_leg.csv from sim_v2e_all')
    ap.add_argument('--out-dir', type=Path, default=OUT_DIR, help='Output directory')
    ap.add_argument('--sims', type=int, default=N_SIMS_DEFAULT)
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument(
        '--fee-rt-5',
        type=float,
        default=5.0,
        help='Round-turn all-in $ per v2e filled leg (2 MNQ). Default: 5',
    )
    ap.add_argument(
        '--slip-std-pts',
        type=float,
        default=0.35,
        help='Stdev of Gaussian **slip** in index points per fill (0 = off). Default 0.35',
    )
    ap.add_argument(
        '--fill-err-pts',
        type=float,
        default=5.0,
        help='Uniform fill error in index points, U(-a,a) per fill. 0 = off. Default 5',
    )
    ap.add_argument('--no-plots', action='store_true', help='Skip PNG generation')
    args = ap.parse_args()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if not args.csv.is_file():
        print(f"Missing {args.csv} — run:  python3 sim_v2e_all.py", file=sys.stderr)
        return 1

    df = pd.read_csv(args.csv)
    if 'v2e_pnl_5m' not in df.columns:
        print('CSV must have v2e_pnl_5m', file=sys.stderr)
        return 1

    raw_pl = df['v2e_pnl_5m'].to_numpy(dtype=np.float64)
    # no_data rows are NaN in new v2e CSV — treat as $0 path, no fee
    base = np.where(np.isfinite(raw_pl), raw_pl, 0.0)
    is_fill = np.array([has_v2e_fill(df.iloc[i]) for i in range(len(df))], dtype=bool)
    n_fills = int(is_fill.sum())
    fee_total_per_sim = n_fills * args.fee_rt_5

    rng = np.random.default_rng(args.seed)

    print(f"Rows: {len(df):,}  |  v2e fills (fee rows): {n_fills:,}")
    print(f"  Frictionless cum v2e:  ${base.sum():+,.0f}")
    print(f"  Est. total RT fees:    ${-fee_total_per_sim:,.0f}  ($ {args.fee_rt_5}/fill × {n_fills})")
    print(f"  Base − fees (no slip):  ${base.sum() - fee_total_per_sim:+,.0f}")
    print(f"  Mc: slip σ = {args.slip_std_pts} index pts, fill err U(±{args.fill_err_pts}) index pts, {args.sims:,} sims\n")

    curves, max_dds, finals = run_friction_monte(
        base,
        is_fill,
        args.sims,
        args.fee_rt_5,
        args.slip_std_pts,
        args.fill_err_pts,
        rng,
    )

    # Reference curves (chronological)
    fee_vec = np.where(is_fill, -args.fee_rt_5, 0.0)
    det_cum = np.cumsum(base + fee_vec)
    base_cum = np.cumsum(base)

    if not args.no_plots:
        plot_equity_fan(
            curves,
            base_cum,
            det_cum,
            out_dir / 'v2e_monte_friction_equity.png',
            'v2e — 2 MNQ, friction Monte Carlo (chronological)',
            args.sims,
        )
        plot_dist(
            finals,
            f'v2e terminal P/L (fees + slip + fill err) — {args.sims:,} paths',
            'Final cumulative $',
            out_dir / 'v2e_monte_friction_final.png',
            float(det_cum[-1]),
        )
        plot_dist(
            max_dds,
            'v2e max drawdown ($) — cumulative equity paths',
            'Max drawdown $',
            out_dir / 'v2e_monte_friction_dd.png',
            None,
        )

    d0, d1 = pd.to_datetime(df['Date']).min(), pd.to_datetime(df['Date']).max()
    years = max((d1 - d0).days / 365.25, 0.1)

    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    rows = []
    for p in percentiles:
        fp = float(np.percentile(finals, p))
        ddv = float(np.percentile(max_dds, p))
        rows.append({
            'Percentile': f'{p}th',
            'Final_PL': round(fp, 2),
            'Max_DD': round(ddv, 2),
            'Capital_3x': round(ddv * 3, 2),
        })
    stats_df = pd.DataFrame(rows)
    stats_path = out_dir / 'v2e_monte_friction_stats.csv'
    stats_df.to_csv(stats_path, index=False)
    print(f"Saved {stats_path}")
    meta = {
        'source_csv': str(args.csv),
        'rows': len(df),
        'v2e_fill_count': n_fills,
        'fee_rt_5': args.fee_rt_5,
        'slip_std_pts': args.slip_std_pts,
        'fill_err_pts_uniform_hi': args.fill_err_pts,
        'sims': args.sims,
        'seed': args.seed,
        'dollars_per_index_point_v2e': DOLLARS_PER_INDEX_POINT_V2E,
        'frictionless_cum_': float(base.sum()),
        'fee_total_est': float(fee_total_per_sim),
        'cum_base_minus_fees': float(base.sum() - fee_total_per_sim),
        'years_in_sample': float(round(years, 4)),
    }
    meta_path = out_dir / 'v2e_monte_friction_meta.json'
    with open(meta_path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    print(f"Saved {meta_path}")

    print(f"\n  Deterministic: base − fees only, final: ${det_cum[-1]:+,.0f}")
    print(f"  Stochastic:    median final (50th):  ${np.median(finals):+,.0f}")
    print(
        f"  5th–95th final:  ${np.percentile(finals, 5):+,.0f} … ${np.percentile(finals, 95):+,.0f}"
    )
    print(
        f"  5th–95th max DD: ${np.percentile(max_dds, 5):+,.0f} … ${np.percentile(max_dds, 95):+,.0f}"
    )
    print(f"  P(final > 0): {(finals > 0).mean()*100:.1f}%")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
