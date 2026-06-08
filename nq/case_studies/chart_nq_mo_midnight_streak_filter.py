#!/usr/bin/env python3
"""
Chart winners/losers for MO midnight retest · streak filter variant.

Rules: days 1–3 of bias streak · max 2 streaks/month · SL30 / TP200 (from trades_sl30.csv).

Output::

  nq_mo_midnight_retest/charts/bias_streak_filter/winners/
  nq_mo_midnight_retest/charts/bias_streak_filter/losers/

Usage::

  python3 nq/case_studies/chart_nq_mo_midnight_streak_filter.py
"""
from __future__ import annotations

import argparse
import random
import sys
from datetime import date
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1] / 'mnq' / 'case_studies' / 'midnight_open_hourly_charts'))

from backtest_nq_mo_midnight_retest import (  # noqa: E402
    TradeRecord,
    load_daily,
    plot_trade_chart,
)
from build_midnight_open_hourly_charts import (  # noqa: E402
    DEFAULT_DBN_NQ,
    load_1m_by_ny_date,
    resample_15m_midnight_to_1600,
)

STUDY = 'bias_streak_filter'


def apply_streak_filter(df: pd.DataFrame, daily: pd.DataFrame) -> pd.DataFrame:
    tdays = sorted(daily['date'].dt.date.unique())
    idx = {d: i for i, d in enumerate(tdays)}
    out = df.copy()
    out['session_d'] = pd.to_datetime(out['session']).dt.date
    out['streak_start'] = out['streak_id'].map(lambda s: date.fromisoformat(s.rsplit('_', 1)[0]))
    out['streak_day'] = out.apply(lambda r: idx[r['session_d']] - idx[r['streak_start']] + 1, axis=1)
    rank_map: dict[tuple, int] = {}
    for month, g in out.groupby(out['session_d'].map(lambda d: pd.Timestamp(d).to_period('M'))):
        ordered = sorted(g['streak_id'].unique(), key=lambda s: date.fromisoformat(s.rsplit('_', 1)[0]))
        for i, sid in enumerate(ordered, 1):
            rank_map[(month, sid)] = i
    out['streak_rank'] = out.apply(
        lambda r: rank_map[(pd.Timestamp(r['session_d']).to_period('M'), r['streak_id'])], axis=1
    )
    return out[(out['streak_day'] <= 3) & (out['streak_rank'] <= 2)].copy()


def row_to_trade(row: pd.Series) -> TradeRecord:
    return TradeRecord(
        session=pd.Timestamp(row['session']).date(),
        side=row['side'],
        bias=row['bias'],
        streak_id=row['streak_id'],
        midnight_close=float(row['midnight_close']),
        mo=float(row['mo']),
        breakout_ts=pd.Timestamp(row['breakout_ts']),
        entry_ts=pd.Timestamp(row['entry_ts']),
        entry=float(row['entry']),
        exit_ts=pd.Timestamp(row['exit_ts']),
        exit=float(row['exit']),
        pts=float(row['pts']),
        result=row['result'],
        stop_pts=float(row['stop_pts']),
        attempt=int(row['attempt']),
    )


def sample_stratified(df: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    if len(df) <= n:
        return df
    rng = random.Random(seed)
    df = df.copy()
    df['year'] = pd.to_datetime(df['session']).dt.year
    picked: list[pd.Series] = []
    years = sorted(df['year'].unique())
    per = max(1, n // len(years))
    for y in years:
        pool = df[df['year'] == y]
        rows = [pool.iloc[i] for i in rng.sample(range(len(pool)), min(per, len(pool)))]
        picked.extend(rows)
    if len(picked) < n:
        rest = df.drop(index=[r.name for r in picked])
        extra = [rest.iloc[i] for i in rng.sample(range(len(rest)), min(n - len(picked), len(rest)))]
        picked.extend(extra)
    return pd.DataFrame(picked).head(n)


def build(
    *,
    trades_csv: Path,
    charts_root: Path,
    daily_path: Path,
    dbn_path: Path,
    n_each: int,
    seed: int,
) -> None:
    daily = load_daily(daily_path)
    trades = pd.read_csv(trades_csv, parse_dates=['session', 'entry_ts', 'exit_ts', 'breakout_ts'])
    filtered = apply_streak_filter(trades, daily)

    winners = filtered[filtered['pts'] > 0]
    losers = filtered[filtered['pts'] <= 0]
    win_sample = sample_stratified(winners, n_each, seed)
    lose_sample = sample_stratified(losers, n_each, seed + 1)

    study_dir = charts_root / STUDY
    win_dir = study_dir / 'winners'
    lose_dir = study_dir / 'losers'
    win_dir.mkdir(parents=True, exist_ok=True)
    lose_dir.mkdir(parents=True, exist_ok=True)

    sessions = sorted(
        set(pd.to_datetime(win_sample['session']).dt.date) | set(pd.to_datetime(lose_sample['session']).dt.date)
    )
    print(f'Loading 1m for {len(sessions)} sessions ...', flush=True)
    gby = load_1m_by_ny_date(dbn_path, 'nq')
    b15: dict[date, pd.DataFrame] = {}
    for s in sessions:
        if s in gby:
            b15[s] = resample_15m_midnight_to_1600(gby[s], s)

    manifest: list[dict] = []

    def chart_batch(sample: pd.DataFrame, out_dir: Path, label: str) -> int:
        n = 0
        for i, (_, row) in enumerate(sample.iterrows()):
            t = row_to_trade(row)
            bars = b15.get(t.session)
            if bars is None or bars.empty:
                continue
            fname = f'{i+1:03d}_{t.session.isoformat()}_{t.side}_{t.result}_{t.pts:+.0f}.png'
            plot_trade_chart(out_dir / fname, t, bars)
            manifest.append(
                {
                    'bucket': label,
                    'chart': f'{STUDY}/{label}/{fname}',
                    'session': t.session.isoformat(),
                    'side': t.side,
                    'pts': t.pts,
                    'result': t.result,
                }
            )
            n += 1
        return n

    nw = chart_batch(win_sample, win_dir, 'winners')
    nl = chart_batch(lose_sample, lose_dir, 'losers')
    pd.DataFrame(manifest).to_csv(study_dir / 'manifest.csv', index=False)

    lines = [
        f'# MO midnight retest · {STUDY}',
        '',
        'Rules: **days 1–3** of bias streak · **max 2 streaks/month** · SL30 / TP200.',
        '',
        f'Filtered pool: **{len(filtered)}** trades ({len(winners)} wins / {len(losers)} losses).',
        f'Charted: **{nw}** winners · **{nl}** losers.',
        '',
        '## Winners',
        '',
        f'[`winners/`](winners/)',
        '',
        '## Losers',
        '',
        f'[`losers/`](losers/)',
        '',
        'Manifest: [`manifest.csv`](manifest.csv)',
        '',
    ]
    (study_dir / 'INDEX.md').write_text('\n'.join(lines), encoding='utf-8')
    print(f'Done → {study_dir} ({nw} winners, {nl} losers)', flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--trades', type=Path, default=HERE / 'nq_mo_midnight_retest' / 'trades_sl30.csv')
    ap.add_argument('--charts-root', type=Path, default=HERE / 'nq_mo_midnight_retest' / 'charts')
    ap.add_argument('--daily', type=Path, default=HERE.parent / 'nq_daily.csv')
    ap.add_argument('--dbn', type=Path, default=DEFAULT_DBN_NQ)
    ap.add_argument('--n-each', type=int, default=50)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args()
    build(
        trades_csv=args.trades,
        charts_root=args.charts_root,
        daily_path=args.daily,
        dbn_path=args.dbn,
        n_each=args.n_each,
        seed=args.seed,
    )
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
