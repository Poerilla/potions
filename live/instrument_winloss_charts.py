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
from .fx_v2b_london_ungated import REPO
from .instrument_deep_check import load_campaigns, _resolve_paths
from .nq_v2b_prior_opposed_15m_charts import FillTrade, _draw_v2b_trade, _load_v2b_fill_groups, _plot_candles

NY = "America/New_York"


def _is_yearly_orb_book(strategy_id: str) -> bool:
    value = str(strategy_id).lower()
    return "yorb" in value or "yearly_orb" in value


def _is_quarterly_range_book(strategy_id: str) -> bool:
    value = str(strategy_id).lower()
    return "quarterly_range" in value or "quarterly_breakout" in value


def _is_daily_swing_book(strategy_id: str) -> bool:
    """Daily-bar swing books charted on ES_D / FX_D rather than 1m windows."""
    return _is_yearly_orb_book(strategy_id) or _is_quarterly_range_book(strategy_id)


def _prior_quarter_bounds(entry_ts: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """Calendar quarter immediately before the entry session."""
    ts = pd.Timestamp(entry_ts).tz_localize(None).normalize()
    curr_q = (int(ts.month) - 1) // 3  # 0..3
    if curr_q == 0:
        prior_year, prior_q = int(ts.year) - 1, 3
    else:
        prior_year, prior_q = int(ts.year), curr_q - 1
    start_month = prior_q * 3 + 1
    start = pd.Timestamp(year=prior_year, month=start_month, day=1)
    end_month = start_month + 2
    if end_month == 12:
        end = pd.Timestamp(year=prior_year, month=12, day=31)
    else:
        end = pd.Timestamp(year=prior_year, month=end_month + 1, day=1) - pd.Timedelta(days=1)
    return start, end


def _window_for_quarterly_daily(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    prior_start, _prior_end = _prior_quarter_bounds(entry_ts)
    end = max(pd.Timestamp(exit_ts).tz_localize(None).normalize() + pd.Timedelta(days=15), entry_ts + pd.Timedelta(days=20))
    return prior_start, end


def _add_quarterly_levels(ax, candles: pd.DataFrame, entry_ts: pd.Timestamp) -> None:
    prior_start, prior_end = _prior_quarter_bounds(entry_ts)
    opening = candles[(candles.index >= prior_start) & (candles.index <= prior_end)]
    if opening.empty:
        return
    rh = float(opening["high"].max())
    rl = float(opening["low"].min())
    mid = 0.5 * (rh + rl)
    for value, label, color, style in [
        (rh, "prior Q high", "#455a64", "-"),
        (rl, "prior Q low", "#455a64", "-"),
        (mid, "prior Q mid", "#6d6d6d", "--"),
    ]:
        ax.axhline(value, color=color, linestyle=style, linewidth=0.9, alpha=0.75)
        ax.text(candles.index[0], value, " " + label, color=color, fontsize=7, va="bottom")
    q_start = pd.Timestamp(entry_ts).tz_localize(None).normalize().replace(
        month=((int(entry_ts.month) - 1) // 3) * 3 + 1, day=1
    )
    ax.axvline(q_start, color="#6d6d6d", linewidth=0.8, alpha=0.55, linestyle=":")
    ax.text(q_start, ax.get_ylim()[1], " Q start", color="#6d6d6d", fontsize=7, va="top")


def _load_daily_candles(paths) -> pd.DataFrame:
    state_daily = paths.state_root / "bars" / ("%s_D.csv" % paths.symbol)
    source = state_daily if state_daily.exists() else paths.daily
    if source is None or not source.exists():
        return pd.DataFrame()
    raw = pd.read_csv(source)
    ts_col = "ts" if "ts" in raw.columns else "date"
    raw[ts_col] = pd.to_datetime(raw[ts_col])
    raw = raw.set_index(ts_col).sort_index()
    cols = ["open", "high", "low", "close"]
    for col in cols:
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    if "volume" not in raw.columns:
        raw["volume"] = 0
    else:
        raw["volume"] = pd.to_numeric(raw["volume"], errors="coerce").fillna(0)
    return raw.dropna(subset=cols)


def _load_daily_fill_groups(fills_path: Optional[Path]) -> Dict[str, pd.DataFrame]:
    if fills_path is None or not fills_path.exists():
        return {}
    fills = pd.read_csv(fills_path)
    if fills.empty:
        return {}
    # Daily fills are stored as session dates. Keep them as naive chart dates instead
    # of converting midnight UTC to the prior New York evening.
    fills["plot_ts"] = pd.to_datetime(fills["ts"].astype(str).str.slice(0, 10), errors="coerce")
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    return {str(k): g.sort_values("plot_ts").copy() for k, g in fills.groupby("trade_id")}


def _daily_trade_dates(row, fills_df: Optional[pd.DataFrame]) -> Tuple[pd.Timestamp, pd.Timestamp]:
    if fills_df is not None and not fills_df.empty and "plot_ts" in fills_df.columns:
        entries = fills_df[fills_df["reason"].astype(str).isin(["entry", "runner_entry"])]
        exits = fills_df[~fills_df["reason"].astype(str).isin(["entry", "runner_entry"])]
        if not entries.empty:
            entry_ts = pd.Timestamp(entries["plot_ts"].min())
            exit_ts = pd.Timestamp(exits["plot_ts"].max()) if not exits.empty else entry_ts
            return entry_ts, exit_ts
    return pd.Timestamp(row.entry_ts).tz_localize(None).normalize(), pd.Timestamp(row.exit_ts).tz_localize(None).normalize()


def _window_for_yorb_daily(entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    year_start = pd.Timestamp(year=int(entry_ts.year), month=1, day=1)
    year_end = pd.Timestamp(year=int(entry_ts.year), month=12, day=31)
    end = max(year_end, exit_ts + pd.Timedelta(days=15))
    return year_start, end


def _add_yorb_levels(ax, candles: pd.DataFrame, entry_ts: pd.Timestamp) -> None:
    jan = pd.Timestamp(year=int(entry_ts.year), month=1, day=1)
    mar_end = pd.Timestamp(year=int(entry_ts.year), month=3, day=31)
    opening = candles[(candles.index >= jan) & (candles.index <= mar_end)]
    if opening.empty:
        return
    rh = float(opening["high"].max())
    rl = float(opening["low"].min())
    rng = rh - rl
    for value, label, color, style in [
        (rh, "Jan-Mar high", "#455a64", "-"),
        (rl, "Jan-Mar low", "#455a64", "-"),
        (rh + rng, "+1R", "#2e7d32", "--"),
        (rl - rng, "-1R", "#c62828", "--"),
        (rh + 2 * rng, "+2R", "#2e7d32", ":"),
        (rl - 2 * rng, "-2R", "#c62828", ":"),
    ]:
        ax.axhline(value, color=color, linestyle=style, linewidth=0.9, alpha=0.7)
        ax.text(candles.index[0], value, " " + label, color=color, fontsize=7, va="bottom")
    apr = pd.Timestamp(year=int(entry_ts.year), month=4, day=1)
    ax.axvline(apr, color="#6d6d6d", linewidth=0.8, alpha=0.6, linestyle=":")
    ax.text(apr, ax.get_ylim()[1], " Apr start", color="#6d6d6d", fontsize=7, va="top")


def _draw_daily_trade(ax, row, fills_df: Optional[pd.DataFrame], entry_ts: pd.Timestamp, exit_ts: pd.Timestamp) -> None:
    color = "#006dce" if str(row.side) == "long" else "#7b3fb2"
    marker = "^" if str(row.side) == "long" else "v"
    ax.scatter([entry_ts], [float(row.entry_price)], s=120, color=color, marker=marker, zorder=10)
    ax.axvline(entry_ts, color=color, linewidth=1.5, alpha=0.85)
    ax.axvline(exit_ts, color=color, linewidth=1.0, alpha=0.65, linestyle="--")
    ax.text(entry_ts, float(row.entry_price), " entry $%.0f" % float(row.net_usd), color=color, fontsize=8, va="bottom", zorder=11)

    if fills_df is None or fills_df.empty:
        return
    exits = fills_df[~fills_df["reason"].astype(str).isin(["entry", "runner_entry"])]
    for _idx, fill in exits.iterrows():
        reason = str(fill["reason"])
        exit_marker = "o" if reason in {"tp1", "tp2", "tp25", "tp"} else "x"
        ax.scatter([pd.Timestamp(fill["plot_ts"])], [float(fill["price"])], s=58, color=color, marker=exit_marker, zorder=10)


def _display_exit_reasons(row, fills_df: Optional[pd.DataFrame], daily_mode: bool) -> str:
    if daily_mode and fills_df is not None and not fills_df.empty:
        exits = fills_df[~fills_df["reason"].astype(str).isin(["entry", "runner_entry"])]
        reasons = sorted(set(str(v) for v in exits["reason"].dropna()))
        if reasons:
            return ",".join(reasons)
    return str(row.exit_reasons)


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

    daily_mode = _is_daily_swing_book(paths.strategy_id)
    quarterly_mode = _is_quarterly_range_book(paths.strategy_id)
    daily_candles = pd.DataFrame()
    gby: Dict[date, pd.DataFrame] = {}
    if daily_mode:
        print("Loading %s daily replay bars for %d charts..." % (paths.symbol, len(sample)), flush=True)
        daily_candles = _load_daily_candles(paths)
        if daily_candles.empty:
            raise FileNotFoundError("No daily candles found for %s under %s" % (paths.symbol, paths.state_root))
    else:
        one_m = REPO / "fx" / ("%s_1m.csv" % paths.symbol.lower())
        print("Loading %s 1m for %d charts..." % (paths.symbol, len(sample)), flush=True)
        gby = load_fx_1m_by_ny_date(one_m, paths.symbol)

    fill_groups: Dict[str, pd.DataFrame] = {}
    if paths.fills is not None:
        fill_groups = _load_daily_fill_groups(paths.fills) if daily_mode else _load_v2b_fill_groups(paths.fills)

    trades_raw = None
    if paths.trades_csv is not None:
        trades_raw = pd.read_csv(paths.trades_csv)
        trades_raw["session"] = trades_raw["session"].astype(str)

    index_rows = []
    for i, row in enumerate(sample.itertuples(index=False), start=1):
        session = date.fromisoformat(str(row.session))
        fills_df = fill_groups.get(str(row.trade_id))
        if daily_mode:
            entry_plot_ts, exit_plot_ts = _daily_trade_dates(row, fills_df)
            if quarterly_mode:
                start, end = _window_for_quarterly_daily(entry_plot_ts, exit_plot_ts)
            else:
                start, end = _window_for_yorb_daily(entry_plot_ts, exit_plot_ts)
            candles = daily_candles[(daily_candles.index >= start) & (daily_candles.index <= end)]
            if candles.empty:
                continue
            session = entry_plot_ts.date()
        else:
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
        _plot_candles(ax, candles, width_days=0.65 if daily_mode else (5 / (24 * 60)) * 0.7)

        trade = FillTrade(
            trade_id=str(row.trade_id),
            side=str(row.side),
            entry_ts=entry_plot_ts if daily_mode else pd.Timestamp(row.entry_ts),
            entry_price=float(row.entry_price),
            exit_ts=exit_plot_ts if daily_mode else pd.Timestamp(row.exit_ts),
            exit_price=float(row.entry_price),
            net_usd=float(row.net_usd),
        )
        # Prefer last fill price when available.
        if daily_mode:
            if quarterly_mode:
                _add_quarterly_levels(ax, candles, entry_plot_ts)
            else:
                _add_yorb_levels(ax, candles, entry_plot_ts)
            _draw_daily_trade(ax, row, fills_df, entry_plot_ts, exit_plot_ts)
        elif fills_df is not None and not fills_df.empty:
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

        exit_reasons = _display_exit_reasons(row, fills_df, daily_mode)
        ax.set_title(
            "%s | %s | %s %s | %s | net %+.0f | %s"
            % (
                paths.symbol,
                paths.strategy_id,
                session.isoformat(),
                row.side,
                outcome.upper(),
                float(row.net_usd),
                exit_reasons,
            )
        )
        if daily_mode:
            ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        else:
            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        ax.grid(True, alpha=0.25)
        handles, labels = ax.get_legend_handles_labels()
        if handles and labels:
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
                "exit_reasons": exit_reasons,
                "entry_ts": str(entry_plot_ts.date() if daily_mode else row.entry_ts),
                "exit_ts": str(exit_plot_ts.date() if daily_mode else row.exit_ts),
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
