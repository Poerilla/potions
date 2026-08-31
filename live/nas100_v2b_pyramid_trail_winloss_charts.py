"""NAS100 v2b clean-break pyramid+trail: 100 winners + 100 losers charts.

Uses validation S0 state for ``trail06_m8_e2_out_be`` (parent CFD top-1).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nas100_v2b_pyramid_trail_winloss_charts --email
"""

from __future__ import annotations

import argparse
import zipfile
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .first_hour_follow_cross_market import load_market_5m
from .notify_email import send_email
from .nq_v2b_prior_opposed_15m_charts import _plot_candles
from .v2b_clean_break_pyramid_trail_sizing_v1 import CFD_SPECS

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "v2b_clean_break_pyramid_trail_cfd_validation_v1"
STATE = HUB / "states" / "nas100_v2b_clean_break_trail06_m8_e2_out_be"
OUT = HUB / "winloss_charts" / "nas100_trail06_m8_e2_out_be"
VARIANT = "trail06_m8_e2_out_be"
FEE = 1.50
POINT = 1.0
NY = "America/New_York"


def _progress(msg: str) -> None:
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def campaigns_from_fills(fills_path: Path) -> pd.DataFrame:
    f = pd.read_csv(fills_path)
    f["ts"] = pd.to_datetime(f["ts"], utc=True).dt.tz_convert(NY)
    f["price"] = pd.to_numeric(f["price"], errors="coerce")
    f["quantity"] = pd.to_numeric(f["quantity"], errors="coerce").fillna(1).astype(int)
    rows = []
    for tid, g in f.sort_values("ts").groupby("trade_id"):
        buys = g[g["side"].astype(str).str.lower() == "buy"]
        sells = g[g["side"].astype(str).str.lower() == "sell"]
        if buys.empty or sells.empty:
            continue
        # Skip ephemeral orphan closes
        if str(tid).startswith("trade_") and not str(tid).startswith("nas100_"):
            continue
        avg_entry = float((buys["price"] * buys["quantity"]).sum() / buys["quantity"].sum())
        avg_exit = float((sells["price"] * sells["quantity"]).sum() / sells["quantity"].sum())
        qty = int(buys["quantity"].sum())
        fees = FEE * float(g["quantity"].sum())
        gross = (avg_exit - avg_entry) * qty * POINT
        net = gross - fees
        entry_ts = pd.Timestamp(buys["ts"].iloc[0])
        exit_ts = pd.Timestamp(sells["ts"].iloc[-1])
        reasons = sorted(set(sells["reason"].astype(str)))
        rows.append(
            {
                "trade_id": str(tid),
                "session": entry_ts.date().isoformat(),
                "side": "long",
                "entry_ts": entry_ts,
                "exit_ts": exit_ts,
                "entry_price": float(buys["price"].iloc[0]),
                "avg_entry": avg_entry,
                "avg_exit": avg_exit,
                "qty": qty,
                "n_adds": max(0, int(buys.shape[0]) - 1),
                "net_usd": net,
                "gross_usd": gross,
                "fees_usd": fees,
                "exit_reasons": ",".join(reasons),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def _sample_even(df: pd.DataFrame, n: int) -> pd.DataFrame:
    if df.empty or n <= 0:
        return df.iloc[0:0]
    if len(df) <= n:
        return df.copy()
    idx = np.linspace(0, len(df) - 1, n)
    pick = sorted({int(round(i)) for i in idx})
    while len(pick) < n:
        for j in range(len(df)):
            if j not in pick:
                pick.append(j)
            if len(pick) >= n:
                break
    return df.iloc[sorted(pick)[:n]].copy()


def _or_levels(day_bars: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
    or_bars = day_bars[(day_bars.index.time >= time(9, 30)) & (day_bars.index.time < time(9, 45))]
    if or_bars.empty:
        return None, None
    return float(or_bars["high"].max()), float(or_bars["low"].min())


def _window(entry: pd.Timestamp, exit: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    start = entry.normalize() + pd.Timedelta(hours=9, minutes=25)
    end = max(exit + pd.Timedelta(minutes=20), entry + pd.Timedelta(hours=2))
    eod = entry.normalize() + pd.Timedelta(hours=16)
    return start, min(end, eod)


def draw_one(
    *,
    row: pd.Series,
    day_bars: pd.DataFrame,
    fills: pd.DataFrame,
    out_path: Path,
) -> None:
    entry = pd.Timestamp(row["entry_ts"])
    exit_ = pd.Timestamp(row["exit_ts"])
    start, end = _window(entry, exit_)
    win = day_bars[(day_bars.index >= start) & (day_bars.index <= end)]
    if win.empty:
        return
    or_hi, or_lo = _or_levels(day_bars)
    fig, ax = plt.subplots(figsize=(14, 6))
    _plot_candles(ax, win, width_days=(5 / (24 * 60)) * 0.7)
    if or_hi is not None:
        ax.axhline(or_hi, color="#1565c0", lw=1.1, ls="-", alpha=0.9, label="OR high")
        ax.axhline(or_hi + 0.2, color="#1565c0", lw=0.8, ls=":", alpha=0.7, label="OR high+2t")
    if or_lo is not None:
        ax.axhline(or_lo, color="#6d4c41", lw=1.0, ls="--", alpha=0.75, label="OR low")
    # shade OR window
    ax.axvspan(
        entry.normalize() + pd.Timedelta(hours=9, minutes=30),
        entry.normalize() + pd.Timedelta(hours=9, minutes=45),
        color="#90caf9",
        alpha=0.15,
        zorder=0,
    )
    tg = fills[fills["trade_id"] == row["trade_id"]].sort_values("ts")
    for _, fr in tg.iterrows():
        ts = pd.Timestamp(fr["ts"])
        px = float(fr["price"])
        reason = str(fr["reason"])
        if fr["side"] == "buy":
            ax.scatter([ts], [px], c="#0a7", s=36 if reason == "entry" else 22, marker="^", zorder=6)
            if reason == "entry":
                ax.annotate("entry", (ts, px), fontsize=7, color="#0a7")
            elif reason == "add":
                ax.annotate("+1", (ts, px), fontsize=6, color="#0a7")
        else:
            ax.scatter([ts], [px], c="#c33", s=40, marker="v", zorder=6)
            ax.annotate(reason[:14], (ts, px), fontsize=6, color="#c33", rotation=30)
    outcome = "WIN" if float(row["net_usd"]) > 0 else "LOSS"
    ax.set_title(
        "NAS100 %s %s | qty=%d adds=%d | net=$%+.0f | %s | AUDIT ONLY"
        % (row["session"], VARIANT, int(row["qty"]), int(row["n_adds"]), row["net_usd"], outcome),
        fontsize=10,
    )
    ax.text(
        0.01,
        0.02,
        "BROKER-LIKE EXECUTION AUDIT — NOT A TRADE RECOMMENDATION",
        transform=ax.transAxes,
        fontsize=8,
        color="#555",
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=win.index.tz))
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)


def run(*, wins: int, losses: int, email: bool) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fills_path = STATE / "fills.csv"
    if not fills_path.exists():
        raise FileNotFoundError(fills_path)
    _progress("load campaigns from fills")
    camps = campaigns_from_fills(fills_path)
    win_df = _sample_even(camps[camps["net_usd"] > 0].sort_values("entry_ts"), wins)
    loss_df = _sample_even(camps[camps["net_usd"] <= 0].sort_values("entry_ts"), losses)
    _progress(
        "sample wins=%d/%d losses=%d/%d"
        % (len(win_df), int((camps.net_usd > 0).sum()), len(loss_df), int((camps.net_usd <= 0).sum()))
    )

    _progress("load NAS100 5m")
    bars = load_market_5m(CFD_SPECS["nas100"], HUB)
    bars = bars.copy()
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert(NY)
    bars = bars.set_index("ts").sort_index()
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["trade_id"] = fills["trade_id"].astype(str)

    index_rows: List[dict] = []
    for folder, sample in (("winners", win_df), ("losers", loss_df)):
        for i, (_, row) in enumerate(sample.iterrows(), start=1):
            day = bars[bars.index.date == pd.Timestamp(row["entry_ts"]).date()]
            fname = "%03d_%s_qty%d_net%+d.png" % (
                i,
                row["session"].replace("-", ""),
                int(row["qty"]),
                int(round(row["net_usd"])),
            )
            path = OUT / folder / fname
            draw_one(row=row, day_bars=day, fills=fills, out_path=path)
            index_rows.append(
                {
                    "folder": folder,
                    "i": i,
                    "session": row["session"],
                    "trade_id": row["trade_id"],
                    "qty": int(row["qty"]),
                    "n_adds": int(row["n_adds"]),
                    "net_usd": float(row["net_usd"]),
                    "exit_reasons": row["exit_reasons"],
                    "file": str(path.relative_to(OUT)),
                }
            )
            if i % 25 == 0:
                _progress("%s %d/%d" % (folder, i, len(sample)))

    idx = pd.DataFrame(index_rows)
    idx.to_csv(OUT / "sample_index.csv", index=False)
    lines = [
        "# NAS100 trail06_m8_e2_out_be — 100 winners / 100 losers",
        "",
        "STATUS: RESEARCH AUDIT CHARTS — NOT TRADE RECOMMENDATIONS",
        "",
        "Source: `%s` (validation S0)" % STATE,
        "Variant: `%s`" % VARIANT,
        "Sample: %d winners + %d losers (even chronological sample)" % (len(win_df), len(loss_df)),
        "Universe: %d campaigns (wins=%d losses=%d)"
        % (len(camps), int((camps.net_usd > 0).sum()), int((camps.net_usd <= 0).sum())),
        "",
        "## Winners",
        "",
    ]
    for _, r in idx[idx.folder == "winners"].iterrows():
        lines.append(
            "- `%s` — %s qty=%d net=$%+.0f (%s)"
            % (r["file"], r["session"], r["qty"], r["net_usd"], r["exit_reasons"])
        )
    lines += ["", "## Losers", ""]
    for _, r in idx[idx.folder == "losers"].iterrows():
        lines.append(
            "- `%s` — %s qty=%d net=$%+.0f (%s)"
            % (r["file"], r["session"], r["qty"], r["net_usd"], r["exit_reasons"])
        )
    (OUT / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = OUT / "winloss_charts.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in OUT.rglob("*.png"):
            zf.write(p, arcname=str(p.relative_to(OUT)))
        zf.write(OUT / "INDEX.md", arcname="INDEX.md")
        zf.write(OUT / "sample_index.csv", arcname="sample_index.csv")

    body = (
        "potions: nas100_trail06_m8_e2_out_be win/loss charts\n\n"
        "100 winners + 100 losers (even sample) for NAS100 CFD pyramid+trail.\n"
        "Hub: %s\n"
        "Charts: %s\n"
        "Zip: %s\n"
        "AUDIT ONLY — not a trade recommendation.\n"
        % (HUB, OUT, zip_path)
    )
    (OUT / "EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(
            subject="potions: NAS100 trail06_m8 win/loss charts (100/100)",
            body=body,
            attachments=[zip_path] if zip_path.exists() else None,
        )
    _progress("DONE charts=%d -> %s" % (len(index_rows), OUT))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--wins", type=int, default=100)
    ap.add_argument("--losses", type=int, default=100)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    run(wins=int(args.wins), losses=int(args.losses), email=bool(args.email))


if __name__ == "__main__":
    main()
