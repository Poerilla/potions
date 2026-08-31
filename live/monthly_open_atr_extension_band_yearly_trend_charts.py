"""Yearly monthly-candle trend charts with win/loss dots for mo-ext band hubs.

One PNG per calendar year: NQ **monthly** OHLC candles. Months with a broker
trade win get a tiny green dot; months with a loss get a tiny red dot.

Usage::

  python -m live.monthly_open_atr_extension_band_yearly_trend_charts \\
    --state-root live/state/monthly_open_atr_extension_band/broker_max_plus_0p3/plus_0p3/states/nq_mo_ext_band_max_plus_0p3_r6m \\
    --email
"""

from __future__ import annotations

import argparse
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .daily_ma50_yearly_charts import plot_candles
from .monthly_atr4_helpers import load_1h
from .monthly_open_atr_extension_band_trade_charts import _broker_trades_df
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "broker_max_plus_0p3"
    / "plus_0p3"
    / "states"
    / "nq_mo_ext_band_max_plus_0p3_r6m"
)
NY = "America/New_York"
WIN_DOT = "#1b8a4a"
LOSS_DOT = "#c62828"
PNG_BATCH_BYTES = 18 * 1024 * 1024
PNG_MAX_PER_EMAIL = 18


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def monthly_ohlc_from_1h(bars_1h: pd.DataFrame) -> pd.DataFrame:
    """Calendar-month OHLC in America/New_York from 1h continuous bars."""
    if bars_1h.empty:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close"])
    df = bars_1h.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize("UTC")
    local = df.tz_convert(NY)
    g = local.groupby([local.index.year, local.index.month], sort=True)
    rows = []
    for (y, m), chunk in g:
        if chunk.empty:
            continue
        rows.append(
            {
                "date": pd.Timestamp(year=int(y), month=int(m), day=1, tz=NY),
                "open": float(chunk["open"].iloc[0]),
                "high": float(chunk["high"].max()),
                "low": float(chunk["low"].min()),
                "close": float(chunk["close"].iloc[-1]),
                "year": int(y),
                "month": int(m),
            }
        )
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    out["date"] = pd.to_datetime(out["date"])
    return out.sort_values("date").reset_index(drop=True)


def month_outcomes(trades: pd.DataFrame) -> Dict[Tuple[int, int], str]:
    """Map (year, month) → 'win' | 'loss' from strategy trade PnL (net that month)."""
    out: Dict[Tuple[int, int], str] = {}
    if trades.empty:
        return out
    for (y, m), g in trades.groupby(["year", "month"]):
        net = float(g["pnl_usd"].sum())
        out[(int(y), int(m))] = "win" if net > 0 else "loss"
    return out


def plot_year(
    *,
    monthly: pd.DataFrame,
    year: int,
    outcomes: Dict[Tuple[int, int], str],
    market: str,
    out_path: Path,
    title_extra: str = "",
) -> None:
    year_df = monthly[monthly["year"] == int(year)].copy()
    if year_df.empty:
        return
    # Small pad with prior Dec / next Jan when available for continuity.
    pad = monthly[
        (monthly["date"] >= pd.Timestamp(year=year, month=1, day=1, tz=NY) - pd.DateOffset(months=1))
        & (monthly["date"] <= pd.Timestamp(year=year, month=12, day=1, tz=NY) + pd.DateOffset(months=1))
    ].copy()
    if pad.empty:
        pad = year_df

    fig, ax = plt.subplots(figsize=(14, 7.2))
    # plot_candles expects naive-ish dates with .dt; normalize for mpl
    plot_df = pad.copy()
    plot_df["date"] = pd.to_datetime(plot_df["date"]).dt.tz_localize(None)
    plot_candles(ax, plot_df, width_days=18.0)

    # Highlight the year span lightly
    y0 = pd.Timestamp(year=year, month=1, day=1)
    y1 = pd.Timestamp(year=year, month=12, day=31)
    ax.axvspan(y0, y1, color="#f5f7fa", alpha=0.55, zorder=0)

    highs = year_df["high"].to_numpy(dtype=float)
    lows = year_df["low"].to_numpy(dtype=float)
    span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 1.0
    pad_y = max(span * 0.025, 1.0)

    for _, row in year_df.iterrows():
        key = (int(row["year"]), int(row["month"]))
        outcome = outcomes.get(key)
        if not outcome:
            continue
        x = mdates.date2num(pd.Timestamp(year=key[0], month=key[1], day=1).to_pydatetime())
        if outcome == "win":
            y = float(row["high"]) + pad_y
            ax.scatter(
                [x],
                [y],
                s=22,
                c=WIN_DOT,
                marker="o",
                zorder=6,
                edgecolors="none",
                label="_win",
            )
        else:
            y = float(row["low"]) - pad_y
            ax.scatter(
                [x],
                [y],
                s=22,
                c=LOSS_DOT,
                marker="o",
                zorder=6,
                edgecolors="none",
                label="_loss",
            )

    # Legend proxies
    ax.scatter([], [], s=28, c=WIN_DOT, label="trade win month")
    ax.scatter([], [], s=28, c=LOSS_DOT, label="trade loss month")

    ax.set_title(
        "%s monthly candles · %d%s"
        % (market.upper(), int(year), (" · " + title_extra) if title_extra else "")
    )
    ax.set_ylabel(market.upper())
    ax.grid(True, color="#e0e0e0", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax.set_xlim(
        pd.Timestamp(year=year, month=1, day=1) - pd.Timedelta(days=20),
        pd.Timestamp(year=year, month=12, day=31) + pd.Timedelta(days=20),
    )
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def _pack_png_batches(paths: List[Path]) -> List[List[Path]]:
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        sz = p.stat().st_size
        overflow = cur and (len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES)
        if overflow:
            batches.append(cur)
            cur = []
            cur_bytes = 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    return batches


def build(
    *,
    state_root: Path,
    output_root: Path,
    market: str = "NQ",
    email: bool = False,
    force: bool = True,
    title_extra: str = "max+30% band fade",
) -> List[dict]:
    if force and output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    charts_dir = output_root / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    _progress(output_root, "Loading broker trades from %s" % state_root)
    trades = _broker_trades_df(state_root, market)
    outcomes = month_outcomes(trades)
    _progress(
        output_root,
        "Trade months: %d (wins=%d losses=%d)"
        % (
            len(outcomes),
            sum(1 for v in outcomes.values() if v == "win"),
            sum(1 for v in outcomes.values() if v == "loss"),
        ),
    )

    _progress(output_root, "Building monthly OHLC from 1h...")
    bars = load_1h(MARKETS[market.upper()])
    monthly = monthly_ohlc_from_1h(bars)

    # Years that overlap strategy trades, plus any year with a candle in that span.
    if outcomes:
        y0 = min(y for y, _ in outcomes)
        y1 = max(y for y, _ in outcomes)
    else:
        y0 = int(monthly["year"].min())
        y1 = int(monthly["year"].max())
    years = [y for y in range(y0, y1 + 1) if not monthly[monthly["year"] == y].empty]

    rows: List[dict] = []
    for y in years:
        path = charts_dir / ("%d.png" % y)
        plot_year(
            monthly=monthly,
            year=y,
            outcomes=outcomes,
            market=market,
            out_path=path,
            title_extra=title_extra,
        )
        y_out = {k: v for k, v in outcomes.items() if k[0] == y}
        rows.append(
            {
                "year": y,
                "months": int(len(monthly[monthly["year"] == y])),
                "win_months": sum(1 for v in y_out.values() if v == "win"),
                "loss_months": sum(1 for v in y_out.values() if v == "loss"),
                "chart": str(path.relative_to(output_root)),
            }
        )
        _progress(
            output_root,
            "chart %d win=%d loss=%d -> %s"
            % (y, rows[-1]["win_months"], rows[-1]["loss_months"], path.name),
        )

    idx = pd.DataFrame(rows)
    idx.to_csv(output_root / "INDEX.csv", index=False)
    lines = [
        "# %s yearly monthly-candle trend charts" % market.upper(),
        "",
        "Hub: `%s`" % output_root,
        "State: `%s`" % state_root,
        "",
        "Monthly OHLC from 1h continuous. Tiny **green** dots = months with strategy **win**; "
        "**red** = **loss** (net PnL that month).",
        "",
        "| Year | Months | Win months | Loss months | Chart |",
        "|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| %d | %d | %d | %d | [%s](%s) |"
            % (r["year"], r["months"], r["win_months"], r["loss_months"], Path(r["chart"]).name, r["chart"])
        )
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email_body = "\n".join(
        [
            "potions: %s monthly trend charts (win/loss dots) — %s" % (market.upper(), title_extra),
            "",
            "Hub: %s" % output_root,
            "Years: %d · trade months: %d (W %d / L %d)"
            % (
                len(rows),
                len(outcomes),
                sum(1 for v in outcomes.values() if v == "win"),
                sum(1 for v in outcomes.values() if v == "loss"),
            ),
            "",
            "One chart per year; monthly candles with tiny green/red outcome dots.",
        ]
    )
    (output_root / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")
    import json

    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "years": len(rows), "trade_months": len(outcomes)}, indent=2) + "\n",
        encoding="utf-8",
    )

    if email:
        pngs = [charts_dir / ("%d.png" % r["year"]) for r in rows]
        batches = _pack_png_batches(pngs)
        for bi, batch in enumerate(batches, start=1):
            subj = "potions: %s monthly trend charts (%d/%d) — %s" % (
                market.upper(),
                bi,
                len(batches),
                title_extra,
            )
            body = email_body + "\n\nBatch %d/%d · %d PNGs\n" % (bi, len(batches), len(batch))
            send_email(subject=subj, body=body, attachments=batch)
            _progress(output_root, "email batch %d/%d attachments=%d" % (bi, len(batches), len(batch)))
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--state-root", type=Path, default=DEFAULT_STATE)
    ap.add_argument("--output-root", type=Path, default=None)
    ap.add_argument("--market", default="NQ")
    ap.add_argument("--title-extra", default="max+30% band fade")
    ap.add_argument("--force", action="store_true", default=True)
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    state_root = args.state_root
    out = args.output_root
    if out is None:
        # .../states/<id> → sibling yearly_monthly_charts under variant root
        hub = state_root.parent.parent if state_root.parent.name == "states" else state_root.parent
        out = hub / "yearly_monthly_charts"
    try:
        rows = build(
            state_root=state_root,
            output_root=out,
            market=str(args.market).upper(),
            email=bool(args.email),
            force=not bool(args.no_force),
            title_extra=str(args.title_extra),
        )
        print("Wrote %d yearly charts -> %s" % (len(rows), out), flush=True)
        return 0
    except Exception:
        err = traceback.format_exc()
        out.mkdir(parents=True, exist_ok=True)
        (out / "EMAIL.txt").write_text("FAILED\n\n%s\n" % err, encoding="utf-8")
        if args.email:
            send_email(subject="potions: monthly trend charts FAILED", body=err)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
