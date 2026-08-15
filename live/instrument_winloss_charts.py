"""Evenly sample 50 wins + 50 losses and chart them for an FX strategy book.

Supports:
  - Broker-like state roots with ``fills.csv`` (v2b Asia / London plugins)
  - Research sims with ``trades.csv`` (London sweep reversal)

Usage::

  python -m live.instrument_winloss_charts \\
    --state-root live/state/fx_v2b_asia_range_london/states/usdjpy_v2b_asia_range_london_S_1_1_3 \\
    --wins 50 --losses 50 --email
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .fx_v2b_london_ungated import MARKETS, REPO, _usd_norm
from .instrument_deep_check import load_campaigns, _resolve_paths
from .nq_v2b_prior_opposed_15m_charts import FillTrade, _draw_v2b_trade, _load_v2b_fill_groups, _plot_candles

NY = "America/New_York"


def _resample_5m(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    return (
        frame.resample("5min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum") if "volume" in frame.columns else ("close", "count"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def _sample_even(rows: pd.DataFrame, n: int) -> pd.DataFrame:
    if n <= 0 or rows.empty:
        return rows.iloc[0:0]
    if len(rows) <= n:
        return rows.copy()
    idx = np.linspace(0, len(rows) - 1, num=n, dtype=int)
    return rows.iloc[sorted(set(int(i) for i in idx))].copy()


def _window_for_trade(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start = entry_ts - pd.Timedelta(hours=2)
    end = exit_ts + pd.Timedelta(minutes=30)
    # Keep charts readable: cap at ~12h window.
    if end - start > pd.Timedelta(hours=12):
        end = start + pd.Timedelta(hours=12)
    return start, end


def _day_frame(gby: Dict[date, pd.DataFrame], session: date) -> pd.DataFrame:
    frames = []
    for d in (session - timedelta(days=1), session, session + timedelta(days=1)):
        raw = gby.get(d)
        if raw is None or raw.empty:
            continue
        day = raw.copy()
        if day.index.tz is None:
            day.index = day.index.tz_localize(NY)
        else:
            day.index = day.index.tz_convert(NY)
        frames.append(day)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    return out[~out.index.duplicated(keep="last")]


def _draw_sweep_levels(ax, row: pd.Series) -> None:
    t0 = ax.get_xlim()
    for col, color, ls in (
        ("london_high", "#e65100", "--"),
        ("london_low", "#e65100", "--"),
        ("initial_stop", "#c62828", ":"),
        ("tp1", "#2e7d32", "-."),
        ("tp2", "#2e7d32", "-."),
        ("tp3", "#2e7d32", "-."),
    ):
        if col not in row or pd.isna(row[col]):
            continue
        ax.axhline(float(row[col]), color=color, linestyle=ls, linewidth=1.0, alpha=0.85, label=col)


def chart_sample(
    *,
    state_root: Path,
    output_root: Optional[Path],
    wins: int,
    losses: int,
    force: bool,
    email: bool,
    label: Optional[str] = None,
) -> Path:
    paths = _resolve_paths(state_root, None, label)
    out = output_root or (paths.output_root.parent.parent / "winloss_charts" / paths.strategy_id)
    # Prefer nesting under deep_check sibling: hub/winloss_charts/<id>
    hub = paths.state_root.parent.parent if paths.state_root.parent.name == "states" else paths.state_root.parent
    out = output_root or (hub / "winloss_charts" / paths.strategy_id)
    if force and out.exists():
        shutil.rmtree(out)
    charts_dir = out / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    campaigns = load_campaigns(paths).sort_values("entry_ts").reset_index(drop=True)
    win_df = _sample_even(campaigns[campaigns["net_usd"] > 0], wins)
    loss_df = _sample_even(campaigns[campaigns["net_usd"] <= 0], losses)
    sample = pd.concat([win_df, loss_df]).sort_values("entry_ts").reset_index(drop=True)

    market = MARKETS[paths.symbol]
    one_m = REPO / "fx" / ("%s_1m.csv" % paths.symbol.lower())
    print("Loading %s 1m for %d charts..." % (paths.symbol, len(sample)), flush=True)
    gby = load_fx_1m_by_ny_date(one_m, paths.symbol)

    fill_groups: Dict[str, pd.DataFrame] = {}
    if paths.fills is not None:
        fill_groups = _load_v2b_fill_groups(paths.fills)

    trades_raw = None
    if paths.trades_csv is not None:
        trades_raw = pd.read_csv(paths.trades_csv)
        trades_raw["session"] = trades_raw["session"].astype(str)

    index_rows = []
    for i, row in enumerate(sample.itertuples(index=False), start=1):
        session = date.fromisoformat(str(row.session))
        day = _day_frame(gby, session)
        if day.empty:
            continue
        start, end = _window_for_trade(pd.Timestamp(row.entry_ts), pd.Timestamp(row.exit_ts))
        window = day[(day.index >= start) & (day.index <= end)]
        candles = _resample_5m(window)
        if candles.empty:
            continue

        outcome = "win" if float(row.net_usd) > 0 else "loss"
        fname = "%03d_%s_%s_%s.png" % (i, session.isoformat(), row.side, outcome)
        fig, ax = plt.subplots(figsize=(16, 7))
        _plot_candles(ax, candles, width_days=(5 / (24 * 60)) * 0.7)

        trade = FillTrade(
            trade_id=str(row.trade_id),
            side=str(row.side),
            entry_ts=pd.Timestamp(row.entry_ts),
            entry_price=float(row.entry_price),
            exit_ts=pd.Timestamp(row.exit_ts),
            exit_price=float(row.entry_price),
            net_usd=float(row.net_usd),
        )
        # Prefer last fill price when available.
        fills_df = fill_groups.get(str(row.trade_id))
        if fills_df is not None and not fills_df.empty:
            exits = fills_df[fills_df["reason"].astype(str) != "entry"]
            if not exits.empty:
                trade = FillTrade(
                    trade_id=trade.trade_id,
                    side=trade.side,
                    entry_ts=trade.entry_ts,
                    entry_price=trade.entry_price,
                    exit_ts=pd.Timestamp(exits["ts"].max()),
                    exit_price=float(exits.iloc[-1]["price"]),
                    net_usd=trade.net_usd,
                )
            _draw_v2b_trade(ax, trade, fills_df)
        else:
            color = "#006dce" if trade.side == "long" else "#7b3fb2"
            ax.scatter([trade.entry_ts], [trade.entry_price], s=120, color=color, marker="^" if trade.side == "long" else "v", zorder=10)
            ax.axvline(trade.entry_ts, color=color, linewidth=1.4, alpha=0.85)
            ax.axvline(trade.exit_ts, color=color, linewidth=1.0, alpha=0.65, linestyle="--")
            if trades_raw is not None:
                match = trades_raw[trades_raw["session"] == str(row.session)]
                if not match.empty:
                    _draw_sweep_levels(ax, match.iloc[0])
                    ax.scatter([trade.exit_ts], [float(match.iloc[0]["exit_price"])], s=70, color=color, marker="x", zorder=10)

        ax.set_title(
            "%s | %s | %s %s | %s | net %+.0f | %s"
            % (
                paths.symbol,
                paths.strategy_id,
                session.isoformat(),
                row.side,
                outcome.upper(),
                float(row.net_usd),
                str(row.exit_reasons),
            )
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        ax.grid(True, alpha=0.25)
        ax.legend(loc="upper left", fontsize=8)
        fig.autofmt_xdate()
        fig.savefig(charts_dir / fname, dpi=120, bbox_inches="tight")
        plt.close(fig)

        index_rows.append(
            {
                "seq": i,
                "session": session.isoformat(),
                "side": row.side,
                "outcome": outcome,
                "net_usd": float(row.net_usd),
                "exit_reasons": row.exit_reasons,
                "entry_ts": str(row.entry_ts),
                "exit_ts": str(row.exit_ts),
                "chart": "charts/%s" % fname,
            }
        )
        if i % 20 == 0:
            print("  charted %d/%d" % (i, len(sample)), flush=True)

    idx_df = pd.DataFrame(index_rows)
    idx_df.to_csv(out / "INDEX.csv", index=False)
    lines = [
        "# %s — %d wins / %d losses" % (paths.strategy_id, wins, losses),
        "",
        "| # | session | side | outcome | net | exits | chart |",
        "|---:|---|---|---|---:|---|---|",
    ]
    for r in index_rows:
        lines.append(
            "| %d | %s | %s | %s | %+.0f | %s | [%s](%s) |"
            % (r["seq"], r["session"], r["side"], r["outcome"], r["net_usd"], r["exit_reasons"], Path(r["chart"]).name, r["chart"])
        )
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Zip for email attachment (Resend-friendly single file).
    zip_path = out / "winloss_charts.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(out / "INDEX.md", arcname="INDEX.md")
        zf.write(out / "INDEX.csv", arcname="INDEX.csv")
        for r in index_rows:
            zf.write(out / r["chart"], arcname=r["chart"])

    n_wins = int((idx_df["outcome"] == "win").sum()) if not idx_df.empty else 0
    n_losses = int((idx_df["outcome"] == "loss").sum()) if not idx_df.empty else 0
    text = "\n".join(
        [
            "potions: win/loss charts %s" % paths.strategy_id,
            "",
            "Charts: %d wins + %d losses (requested %d/%d)" % (n_wins, n_losses, wins, losses),
            "Hub: %s" % out,
            "Zip: %s" % zip_path,
            "",
            "Evenly sampled across the full trade history.",
        ]
    )
    html_body = """<!DOCTYPE html><html><body style="font-family:Georgia,serif">
<h2>%(title)s</h2>
<p>%(n_wins)d wins + %(n_losses)d losses. Hub <code>%(hub)s</code>.</p>
<p>Zip attached when under size limit; otherwise open the hub path.</p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px">
<tr><th>#</th><th>session</th><th>side</th><th>out</th><th>net</th><th>exits</th></tr>
%(rows)s
</table></body></html>""" % {
        "title": html.escape(paths.strategy_id),
        "n_wins": n_wins,
        "n_losses": n_losses,
        "hub": html.escape(str(out)),
        "rows": "\n".join(
            "<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>%+.0f</td><td>%s</td></tr>"
            % (r["seq"], html.escape(r["session"]), r["side"], r["outcome"], r["net_usd"], html.escape(str(r["exit_reasons"])))
            for r in index_rows[:40]
        )
        + ("<tr><td colspan='6'>… %d more in hub / zip</td></tr>" % max(0, len(index_rows) - 40) if len(index_rows) > 40 else ""),
    }
    (out / "EMAIL.txt").write_text(text + "\n", encoding="utf-8")
    (out / "EMAIL.html").write_text(html_body, encoding="utf-8")

    if email:
        from .notify_email import send_email

        atts = [zip_path] if zip_path.exists() and zip_path.stat().st_size < 7.5 * 1024 * 1024 else []
        send_email(
            subject="potions: win/loss charts %s" % paths.strategy_id,
            body=text,
            html=html_body,
            attachments=atts or None,
        )
        print("email sent (attachments=%d)" % len(atts), flush=True)

    print("Wrote %s (%d charts)" % (out, len(index_rows)), flush=True)
    return out


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-root", type=Path, required=True)
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument("--label", default=None)
    ap.add_argument("--wins", type=int, default=50)
    ap.add_argument("--losses", type=int, default=50)
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    chart_sample(
        state_root=args.state_root,
        output_root=args.output_root,
        wins=args.wins,
        losses=args.losses,
        force=not args.no_force,
        email=args.email,
        label=args.label,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
