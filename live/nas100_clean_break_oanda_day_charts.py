"""Chart NAS100 clean-break OANDA practice traded days.

Default: demo local 5m bars + live sleeve fills.

``--corrected``: replay this sleeve's stored ``rth_ticks`` through the live/demo
OANDA wiring (quote 1m → left-label 5m → Engine+PaperBroker with current
``trail06_m4_e2_out_be`` config, including fill→5m bucket fix), then chart the
resulting fills under ``charts/traded_days/corrected/``.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nas100_clean_break_oanda_day_charts --email
  python -m live.nas100_clean_break_oanda_day_charts --corrected --email
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from datetime import datetime, time
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .nas100_clean_break_demo_plugin_tick_parity import (
    OWN_TICK_DIR,
    list_tick_days,
    run_demo_tick_path,
)
from .notify_email import send_email
from .nq_v2b_prior_opposed_15m_charts import _plot_candles
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
DEMO = REPO / "live" / "demo" / "nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda"
FILLS = DEMO / "state" / "fills.csv"
BARS_5M = DEMO / "state" / "bars" / "NAS100_5m.csv"
LEVELS = DEMO / "state" / "levels.csv"
OUT_LIVE = DEMO / "charts" / "traded_days"
OUT_CORRECTED = DEMO / "charts" / "traded_days" / "corrected"
VARIANT = "trail06_m4_e2_out_be"
FEE = 1.50
POINT = 1.0
NY = "America/New_York"


def _progress(msg: str) -> None:
    print("[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def campaigns_from_fills(fills: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for tid, g in fills.sort_values("ts").groupby("trade_id"):
        buys = g[g["side"].astype(str).str.lower() == "buy"]
        sells = g[g["side"].astype(str).str.lower() == "sell"]
        if buys.empty:
            continue
        entry_ts = pd.Timestamp(buys["ts"].iloc[0])
        qty = int(buys["quantity"].sum())
        avg_entry = float((buys["price"] * buys["quantity"]).sum() / buys["quantity"].sum())
        if sells.empty:
            last_px = float(buys["price"].iloc[-1])
            exit_ts = pd.Timestamp(buys["ts"].iloc[-1])
            fees = FEE * float(buys["quantity"].sum())
            net = -fees
            avg_exit = last_px
            status = "OPEN"
            reasons = "open"
        else:
            avg_exit = float((sells["price"] * sells["quantity"]).sum() / sells["quantity"].sum())
            fees = FEE * float(g["quantity"].sum())
            gross = (avg_exit - avg_entry) * qty * POINT
            net = gross - fees
            exit_ts = pd.Timestamp(sells["ts"].iloc[-1])
            status = "WIN" if net > 0 else "LOSS"
            reasons = ",".join(sorted(set(sells["reason"].astype(str))))
        rows.append(
            {
                "trade_id": str(tid),
                "session": entry_ts.tz_convert(NY).date().isoformat(),
                "entry_ts": entry_ts.tz_convert(NY),
                "exit_ts": exit_ts.tz_convert(NY),
                "avg_entry": avg_entry,
                "avg_exit": avg_exit,
                "qty": qty,
                "n_adds": max(0, int(buys.shape[0]) - 1),
                "net_usd": float(net),
                "status": status,
                "exit_reasons": reasons,
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def _or_from_bars(day_bars: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
    or_bars = day_bars[(day_bars.index.time >= time(9, 30)) & (day_bars.index.time < time(9, 45))]
    if or_bars.empty:
        return None, None
    return float(or_bars["high"].max()), float(or_bars["low"].min())


def _or_from_levels(levels: pd.DataFrame, session: str) -> Tuple[Optional[float], Optional[float]]:
    if levels.empty:
        return None, None
    day = pd.Timestamp(session).tz_localize(NY)
    day_utc_start = day.tz_convert("UTC")
    day_utc_end = (day + pd.Timedelta(days=1)).tz_convert("UTC")
    g = levels[(levels["active_from"] >= day_utc_start) & (levels["active_from"] < day_utc_end)]
    if g.empty:
        return None, None
    hi = g[g["level_name"] == "v2b_clean_or_high"]
    lo = g[g["level_name"] == "v2b_clean_or_low"]
    or_hi = float(hi["price"].iloc[-1]) if not hi.empty else None
    or_lo = float(lo["price"].iloc[-1]) if not lo.empty else None
    return or_hi, or_lo


def draw_day(
    *,
    row: pd.Series,
    day_bars: pd.DataFrame,
    fills: pd.DataFrame,
    or_hi: Optional[float],
    or_lo: Optional[float],
    out_path: Path,
    subtitle: str,
) -> None:
    entry = pd.Timestamp(row["entry_ts"])
    start = entry.normalize() + pd.Timedelta(hours=9, minutes=25)
    end = entry.normalize() + pd.Timedelta(hours=16, minutes=5)
    if row["status"] == "OPEN":
        end = max(end, entry + pd.Timedelta(hours=1))
    win = day_bars[(day_bars.index >= start) & (day_bars.index <= end)]
    if win.empty:
        win = day_bars
    if win.empty:
        return

    fig, ax = plt.subplots(figsize=(14, 6.2))
    _plot_candles(ax, win, width_days=(5 / (24 * 60)) * 0.7)
    ax.axvspan(
        entry.normalize() + pd.Timedelta(hours=9, minutes=30),
        entry.normalize() + pd.Timedelta(hours=9, minutes=45),
        color="#90caf9",
        alpha=0.15,
        zorder=0,
    )
    if or_hi is not None:
        ax.axhline(or_hi, color="#1565c0", lw=1.2, ls="-", alpha=0.9, label="OR high")
    if or_lo is not None:
        ax.axhline(or_lo, color="#6d4c41", lw=1.0, ls="--", alpha=0.8, label="OR low")

    tg = fills[fills["trade_id"] == row["trade_id"]].sort_values("ts")
    for _, fr in tg.iterrows():
        ts = pd.Timestamp(fr["ts"]).tz_convert(NY)
        px = float(fr["price"])
        reason = str(fr["reason"])
        side = str(fr["side"]).lower()
        if side == "buy":
            ax.scatter([ts], [px], c="#0a7", s=42 if reason == "entry" else 26, marker="^", zorder=6)
            ax.annotate(reason if reason != "entry" else "entry", (ts, px), fontsize=7, color="#0a7")
        else:
            ax.scatter([ts], [px], c="#c33", s=44, marker="v", zorder=6)
            ax.annotate(reason[:18], (ts, px), fontsize=7, color="#c33", rotation=25)

    ax.set_title(
        "NAS100 %s %s | %s | qty=%d adds=%d | net=$%+.2f | %s | %s"
        % (
            subtitle,
            row["session"],
            VARIANT,
            int(row["qty"]),
            int(row["n_adds"]),
            float(row["net_usd"]),
            row["status"],
            row["exit_reasons"],
        ),
        fontsize=10,
    )
    ax.text(
        0.01,
        0.02,
        subtitle,
        transform=ax.transAxes,
        fontsize=8,
        color="#555",
    )
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=win.index.tz))
    ax.grid(True, alpha=0.25)
    ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)


def _write_chart_pack(
    *,
    out: Path,
    fills: pd.DataFrame,
    bars: pd.DataFrame,
    levels: pd.DataFrame,
    subtitle: str,
    index_title: str,
    email: bool,
    email_subject: str,
    sessions_filter: Optional[Sequence[str]] = None,
) -> Tuple[Path, pd.DataFrame]:
    if out.exists():
        for p in out.glob("*"):
            if p.is_file():
                p.unlink()
    out.mkdir(parents=True, exist_ok=True)

    camps = campaigns_from_fills(fills)
    if sessions_filter is not None:
        want = set(sessions_filter)
        camps = camps[camps["session"].isin(want)].reset_index(drop=True)
    _progress("campaigns=%d sessions=%s" % (len(camps), camps["session"].tolist() if len(camps) else []))

    index_rows: List[dict] = []
    for i, (_, row) in enumerate(camps.iterrows(), start=1):
        day = bars[bars.index.date == pd.Timestamp(row["entry_ts"]).date()]
        or_hi, or_lo = _or_from_levels(levels, row["session"])
        if or_hi is None:
            or_hi, or_lo = _or_from_bars(day)
        fname = "%02d_%s_%s_net%+.0f.png" % (
            i,
            row["session"].replace("-", ""),
            row["status"].lower(),
            float(row["net_usd"]),
        )
        path = out / fname
        draw_day(
            row=row,
            day_bars=day,
            fills=fills,
            or_hi=or_hi,
            or_lo=or_lo,
            out_path=path,
            subtitle=subtitle,
        )
        index_rows.append(
            {
                "i": i,
                "session": row["session"],
                "trade_id": row["trade_id"],
                "status": row["status"],
                "qty": int(row["qty"]),
                "n_adds": int(row["n_adds"]),
                "net_usd": float(row["net_usd"]),
                "exit_reasons": row["exit_reasons"],
                "file": path.name,
            }
        )
        _progress("wrote %s" % path.name)

    idx = pd.DataFrame(index_rows)
    idx.to_csv(out / "INDEX.csv", index=False)
    lines = [
        "# %s" % index_title,
        "",
        "Demo: `%s`" % DEMO,
        "Variant: `%s`" % VARIANT,
        "Campaigns: %d (wins=%d losses=%d open=%d)"
        % (
            len(camps),
            int((camps.status == "WIN").sum()) if len(camps) else 0,
            int((camps.status == "LOSS").sum()) if len(camps) else 0,
            int((camps.status == "OPEN").sum()) if len(camps) else 0,
        ),
        "Net (closed, fee-adjusted): $%+.2f"
        % (float(camps.loc[camps.status != "OPEN", "net_usd"].sum()) if len(camps) else 0.0),
        "",
        "## Charts",
        "",
    ]
    for _, r in idx.iterrows():
        lines.append(
            "- `%s` — %s %s qty=%d net=$%+.2f (%s)"
            % (r["file"], r["session"], r["status"], r["qty"], r["net_usd"], r["exit_reasons"])
        )
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    zip_path = out / "traded_days.zip"
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(out.glob("*.png")):
            zf.write(p, arcname=p.name)
        zf.write(out / "INDEX.md", arcname="INDEX.md")
        zf.write(out / "INDEX.csv", arcname="INDEX.csv")
    _progress("zip %s" % zip_path)

    if email:
        body = (
            "%s\n\nHub: %s\nCampaigns: %d | wins=%d losses=%d open=%d\n"
            "Closed net (fee-adj): $%+.2f\n\n%s\n"
        ) % (
            index_title,
            out,
            len(camps),
            int((camps.status == "WIN").sum()) if len(camps) else 0,
            int((camps.status == "LOSS").sum()) if len(camps) else 0,
            int((camps.status == "OPEN").sum()) if len(camps) else 0,
            float(camps.loc[camps.status != "OPEN", "net_usd"].sum()) if len(camps) else 0.0,
            (out / "INDEX.md").read_text(encoding="utf-8"),
        )
        (out / "EMAIL.txt").write_text(body, encoding="utf-8")
        send_email(
            subject=email_subject % len(camps),
            body=body,
            attachments=[zip_path] if zip_path.stat().st_size < 12_000_000 else [],
        )
        _progress("email sent")
    return out, camps


def run_live_charts(*, email: bool) -> Path:
    fills = pd.read_csv(FILLS)
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills["trade_id"] = fills["trade_id"].astype(str)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1)

    bars = pd.read_csv(BARS_5M)
    bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert(NY)
    bars = bars.set_index("ts").sort_index()

    levels = pd.DataFrame()
    if LEVELS.exists():
        levels = pd.read_csv(LEVELS)
        levels["active_from"] = pd.to_datetime(levels["active_from"], utc=True)

    out, _ = _write_chart_pack(
        out=OUT_LIVE,
        fills=fills,
        bars=bars,
        levels=levels,
        subtitle="OANDA PRACTICE — LIVE SLEEVE FILLS ON STORED 5m BARS — NOT A TRADE RECOMMENDATION",
        index_title="NAS100 clean-break OANDA practice — traded days",
        email=email,
        email_subject="potions: NAS100 clean-break OANDA traded-day charts (%d)",
    )
    return out


def run_corrected_charts(*, email: bool, max_days: int = 0) -> Path:
    """Replay sleeve rth_ticks through demo OANDA wiring; chart corrected fills."""
    tick_dir = OWN_TICK_DIR
    if not tick_dir.is_dir():
        raise FileNotFoundError("No rth_ticks at %s" % tick_dir)
    days = list_tick_days(tick_dir)
    if not days:
        raise FileNotFoundError("Empty rth_ticks at %s" % tick_dir)
    if int(max_days or 0) > 0:
        days = days[-int(max_days) :]

    # Sessions that actually traded on the live sleeve — chart those first for compare.
    live_sessions: List[str] = []
    if FILLS.exists():
        lf = pd.read_csv(FILLS)
        lf["ts"] = pd.to_datetime(lf["ts"], utc=True)
        live_sessions = sorted(
            {pd.Timestamp(t).tz_convert(NY).date().isoformat() for t in lf["ts"]}
        )

    hub = OUT_CORRECTED / "_replay"
    if hub.exists():
        shutil.rmtree(hub)
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "INPUTS.json").write_text(
        json.dumps(
            {
                "tick_dir": str(tick_dir),
                "days": [p.name for p in days],
                "variant": VARIANT,
                "live_sessions_filter": live_sessions,
                "path": "oanda_ticks → QuoteOneMinuteBarBuilder → left-label 5m → Engine+PaperBroker",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    rid = begin_run(
        run_class="audit",
        variant_slug="nas100_clean_break_corrected_tick_day_charts",
        instrument="NAS100",
        hub_path=str(OUT_CORRECTED.relative_to(REPO)),
        parent_run_id="brl_21741b260a28",
        meta={"tick_days": len(days), "live_sessions": live_sessions},
    )
    try:
        _progress("replaying %d tick days via demo OANDA wiring → %s" % (len(days), hub))
        bars_5m, demo_meta = run_demo_tick_path(days, state_root=hub)
        _progress("replay done meta=%s" % demo_meta)

        fills = pd.read_csv(hub / "fills.csv") if (hub / "fills.csv").exists() else pd.DataFrame()
        if fills.empty:
            raise RuntimeError("corrected tick replay produced zero fills")
        fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
        fills["trade_id"] = fills["trade_id"].astype(str)
        fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
        fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1)
        fills.to_csv(OUT_CORRECTED / "fills.csv", index=False)

        # Bars from replay store
        bars_path = hub / "bars" / "NAS100_5m.csv"
        if not bars_path.exists():
            # Engine may only keep in-memory; rebuild from returned bars_5m
            rows = [
                {
                    "instrument": b.instrument,
                    "timeframe": b.timeframe,
                    "ts": b.ts,
                    "open": b.open,
                    "high": b.high,
                    "low": b.low,
                    "close": b.close,
                    "volume": b.volume,
                    "complete": True,
                    "source": b.source,
                }
                for b in bars_5m
            ]
            bars = pd.DataFrame(rows)
        else:
            bars = pd.read_csv(bars_path)
        bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert(NY)
        bars = bars.set_index("ts").sort_index()

        levels = pd.DataFrame()
        lev_path = hub / "levels.csv"
        if lev_path.exists() and lev_path.stat().st_size > 0:
            levels = pd.read_csv(lev_path)
            if "active_from" in levels.columns:
                levels["active_from"] = pd.to_datetime(levels["active_from"], utc=True)

        # Prefer live-traded sessions when present in corrected tape; else all.
        camps_all = campaigns_from_fills(fills)
        filter_sessions = [s for s in live_sessions if s in set(camps_all["session"])]
        if not filter_sessions:
            filter_sessions = None  # chart every corrected campaign

        out, camps = _write_chart_pack(
            out=OUT_CORRECTED,
            fills=fills,
            bars=bars,
            levels=levels,
            subtitle=(
                "CORRECTED — OANDA rth_ticks → demo wiring (1m→left5m→Engine) — "
                "NOT A TRADE RECOMMENDATION"
            ),
            index_title="NAS100 clean-break CORRECTED — tick→demo wiring traded days",
            email=False,  # send after ledger below
            email_subject="potions: NAS100 clean-break CORRECTED tick charts (%d)",
            sessions_filter=filter_sessions,
        )
        # Re-copy INDEX after _write_chart_pack wiped dir — fills already saved above may be gone
        fills.to_csv(OUT_CORRECTED / "fills.csv", index=False)
        (OUT_CORRECTED / "REPLAY_META.json").write_text(
            json.dumps({"demo_meta": demo_meta, "tick_days": [p.name for p in days]}, indent=2) + "\n",
            encoding="utf-8",
        )
        # Keep replay artifacts under _replay (not wiped by chart pack — chart pack only deletes files in out root)
        # Actually _write_chart_pack only deletes files in out, not subdirs — _replay stays.

        closed_net = float(camps.loc[camps.status != "OPEN", "net_usd"].sum()) if len(camps) else 0.0
        complete_run(
            rid,
            net_usd=closed_net,
            trades=int(len(camps)),
            meta={
                "verdict": "corrected_charts",
                "exit_reasons": camps["exit_reasons"].tolist() if len(camps) else [],
                "demo_meta": demo_meta,
            },
        )

        if email:
            body = (OUT_CORRECTED / "INDEX.md").read_text(encoding="utf-8")
            body = (
                "NAS100 clean-break CORRECTED charts (tick→demo OANDA wiring)\n\n"
                "Hub: %s\nReplay: %s\nTicks: %s (%d days)\n\n%s\n"
                % (OUT_CORRECTED, hub, tick_dir, len(days), body)
            )
            (OUT_CORRECTED / "EMAIL.txt").write_text(body, encoding="utf-8")
            zip_path = OUT_CORRECTED / "traded_days.zip"
            send_email(
                subject="potions: NAS100 clean-break CORRECTED tick→demo charts (%d)"
                % len(camps),
                body=body,
                attachments=[zip_path] if zip_path.exists() and zip_path.stat().st_size < 12_000_000 else [],
            )
            _progress("email sent")
        return out
    except Exception as exc:
        fail_run(rid, error=str(exc))
        raise


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument(
        "--corrected",
        action="store_true",
        help="Replay sleeve rth_ticks through demo OANDA wiring; write charts/traded_days/corrected",
    )
    ap.add_argument("--max-days", type=int, default=0, help="With --corrected, last N tick days (0=all)")
    args = ap.parse_args(argv)
    if args.corrected:
        out = run_corrected_charts(email=bool(args.email), max_days=int(args.max_days or 0))
    else:
        out = run_live_charts(email=bool(args.email))
    print("OUT", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
