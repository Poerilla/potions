"""Chart all Phase-5 4h WICK_REJECT events on ≥1 week pre + 1 week post 4h candles.

Population: atlas 4h invalidation, min_pen_ATR=0.05 (same as Prototype B).
Hub: live/state/nq_structure_change_wick_reject_4h_charts/

Emails unpackaged PNGs packed to Resend-friendly byte/count caps (no zip).

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_structure_wick_reject_4h_charts --email
  python -m live.nq_structure_wick_reject_4h_charts --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import plot_candles, shade_weeks
from .notify_email import send_email
from .nq_structure_change_event_study import HUB as ATLAS_HUB
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nq_structure_change_wick_reject_4h_charts"
BARS_4H = REPO / "live" / "state" / "_cache" / "bars_4h" / "nq_4h.csv"
TRADES_B = REPO / "live" / "state" / "nq_structure_change_phase5_prototypes" / "trades_B.csv"
NY = "America/New_York"
PEN_PRIMARY = 0.05
# ≥1 week of 4h context before confirm + 1 week after (price path after reject)
PRE_DAYS = 7
POST_DAYS = 7
PNG_BATCH_BYTES = 35 * 1024 * 1024  # Resend-friendly; prefer one packed email
PNG_MAX_PER_EMAIL = 200  # count soft-cap; byte cap binds for this book


def _localize(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_events(smoke: bool = False) -> pd.DataFrame:
    df = pd.read_csv(ATLAS_HUB / "structure_events.csv")
    m = (
        (df["event_type"] == "WICK_REJECT")
        & (df["structure_timeframe"] == "4h")
        & (df["event_family"] == "invalidation")
        & (pd.to_numeric(df["min_pen_ATR"], errors="coerce") == PEN_PRIMARY)
    )
    out = df.loc[m].copy()
    out = out.sort_values("confirm_bar_close_ts").reset_index(drop=True)
    if smoke:
        out = out.head(6)
    return out


def load_trades_b() -> pd.DataFrame:
    if not TRADES_B.exists():
        return pd.DataFrame()
    t = pd.read_csv(TRADES_B)
    return t.set_index("event_id", drop=False)


def load_4h() -> pd.DataFrame:
    df = pd.read_csv(BARS_4H)
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df["ts_event"], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    df = df.assign(ts_event=ts).dropna(subset=["ts_event"])
    df = df.set_index("ts_event").sort_index()
    return df[["open", "high", "low", "close"] + (["volume"] if "volume" in df.columns else [])]


def _xi_time(bars: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Timestamp]:
    if bars is None or bars.empty:
        return None
    ts = _localize(ts)
    pos = bars.index.searchsorted(ts, side="left")
    if pos >= len(bars):
        pos = len(bars) - 1
    best = bars.index[pos]
    best_dt = abs((best - ts).total_seconds())
    if pos > 0:
        t0 = bars.index[pos - 1]
        dt0 = abs((t0 - ts).total_seconds())
        if dt0 < best_dt:
            best, best_dt = t0, dt0
    if best_dt > 4 * 3600:
        return None
    return best


def chart_one(
    ev: pd.Series,
    bars: pd.DataFrame,
    trade: Optional[pd.Series],
    out_path: Path,
) -> bool:
    confirm_open = _localize(pd.Timestamp(ev["confirm_bar_open_ts"]))
    confirm_close = _localize(pd.Timestamp(ev["confirm_bar_close_ts"]))
    t0 = confirm_open - pd.Timedelta(days=PRE_DAYS)
    t1 = confirm_close + pd.Timedelta(days=POST_DAYS)
    plot = bars[(bars.index >= t0) & (bars.index <= t1)]
    if len(plot) < 8:
        return False
    # Enforce ≥1 calendar week of span
    span_days = (plot.index[-1] - plot.index[0]).total_seconds() / 86400.0
    if span_days < 6.5:
        # widen slightly if sparse weekend/holiday edge
        plot = bars[
            (bars.index >= confirm_open - pd.Timedelta(days=PRE_DAYS + 2))
            & (bars.index <= confirm_close + pd.Timedelta(days=POST_DAYS + 2))
        ]
        if len(plot) < 8:
            return False

    level = float(ev["protected_swing_price"])
    bdir = str(ev.get("break_direction") or "")
    odir = str(ev.get("outcome_direction") or "") or "(none)"
    entry = float(ev["entry_price"]) if pd.notna(ev.get("entry_price")) else np.nan
    stop_pts = (
        float(ev["stop_distance_points"]) if pd.notna(ev.get("stop_distance_points")) else np.nan
    )

    fig, ax = plt.subplots(figsize=(14, 7))
    shade_weeks(ax, plot.index[0], plot.index[-1] + pd.Timedelta(hours=4))
    plot_candles(ax, plot)

    ax.axhline(level, color="#1565c0", lw=1.6, ls="--", label="protected swing %.2f" % level)

    xo = _xi_time(plot, confirm_open)
    xc = _xi_time(plot, confirm_close)
    if xo is not None and xc is not None:
        left = mdates.date2num(xo.to_pydatetime()) - (2.0 / 24.0) * 0.5
        right = mdates.date2num(xc.to_pydatetime()) + (2.0 / 24.0) * 0.5
        ax.axvspan(left, right, color="#fff59d", alpha=0.4, label="confirm 4h", zorder=1)

    if pd.notna(entry):
        ax.axhline(entry, color="#6a1b9a", lw=1.2, ls=":", label="atlas entry open %.2f" % entry)
        if pd.notna(stop_pts) and stop_pts > 0 and odir in ("bullish", "bearish"):
            if odir == "bullish":
                stop = entry - stop_pts
                tgt = entry + stop_pts
            else:
                stop = entry + stop_pts
                tgt = entry - stop_pts
            ax.axhline(stop, color="#ef6c00", lw=1.1, ls="-.", label="struct stop ~ %.2f" % stop)
            ax.axhline(tgt, color="#2e7d32", lw=1.1, ls="-.", label="1R target ~ %.2f" % tgt)

    oa = _localize(pd.Timestamp(ev["order_active_ts"]))
    x_oa = _xi_time(plot, oa)
    if x_oa is not None:
        ax.axvline(
            mdates.date2num(x_oa.to_pydatetime()),
            color="#5e35b1",
            lw=1.2,
            alpha=0.85,
            label="order_active",
        )

    trade_note = ""
    if trade is not None and len(trade):
        tr = trade.iloc[0] if isinstance(trade, pd.DataFrame) else trade
        trade_note = " | B: %s R=%.2f net=$%.0f" % (
            tr.get("exit_reason", ""),
            float(tr.get("r_multiple") or 0),
            float(tr.get("net_usd") or 0),
        )
        if pd.notna(tr.get("fill_ts")):
            ft = _localize(pd.Timestamp(tr["fill_ts"]))
            ax.axvline(
                mdates.date2num(ft.to_pydatetime()),
                color="#00838f",
                lw=1.0,
                ls="--",
                alpha=0.7,
                label="fill",
            )
        if pd.notna(tr.get("exit_ts")):
            et = _localize(pd.Timestamp(tr["exit_ts"]))
            ax.axvline(
                mdates.date2num(et.to_pydatetime()),
                color="#b71c1c",
                lw=1.0,
                ls="--",
                alpha=0.7,
                label="exit",
            )

    title = (
        "NQ 4h | WICK_REJECT | %s | break=%s outcome=%s | %s | slice=%s\n"
        "pen=%.3f ATR | stop_pts=%.2f | window %s → %s (%d bars)%s"
        % (
            ev["event_id"],
            bdir,
            odir,
            confirm_close.strftime("%Y-%m-%d %H:%M"),
            ev.get("slice", ""),
            float(ev.get("penetration_ATR") or 0),
            stop_pts if pd.notna(stop_pts) else float("nan"),
            plot.index[0].strftime("%Y-%m-%d %H:%M"),
            plot.index[-1].strftime("%Y-%m-%d %H:%M"),
            len(plot),
            trade_note,
        )
    )
    ax.set_title(title, fontsize=9)
    ax.legend(loc="best", fontsize=7)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=plot.index.tz))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True


def _pack_batches(paths: Sequence[Path]) -> List[List[Path]]:
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in paths:
        if not p.exists():
            continue
        sz = p.stat().st_size
        if cur and (len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    return batches


def write_index(hub: Path, meta: pd.DataFrame) -> None:
    lines = [
        "# NQ 4h WICK_REJECT charts",
        "",
        "Population: atlas **4h invalidation** `WICK_REJECT`, `min_pen_ATR=0.05` (Prototype B book).",
        "Each chart: NQ 4h candles confirm −%dd / +%dd (pre context + post path),"
        % (PRE_DAYS, POST_DAYS),
        "week shades, yellow confirm window, protected swing, atlas entry / 1R stop+target,",
        "order_active. Prototype B fill/exit overlays when `trades_B.csv` matches.",
        "",
        "Charts: **%d** (ok=%d)" % (len(meta), int(meta["ok"].sum()) if len(meta) else 0),
        "",
        "| # | file | event_id | slice | confirm | outcome | bars | B exit | B net |",
        "|---:|---|---|---|---|---|---:|---|---:|",
    ]
    for i, r in meta.iterrows():
        lines.append(
            "| %d | `%s` | `%s` | %s | %s | %s | %s | %s | %s |"
            % (
                i + 1,
                r.get("chart_file", ""),
                r.get("event_id", ""),
                r.get("slice", ""),
                str(r.get("confirm_bar_close_ts", ""))[:19],
                r.get("outcome_direction", ""),
                r.get("n_bars", ""),
                r.get("exit_reason", ""),
                r.get("net_usd", ""),
            )
        )
    (hub / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(*, smoke: bool = False, email: bool = False) -> Path:
    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    charts_dir = hub / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    for old in charts_dir.glob("*.png"):
        old.unlink()

    rid = begin_run(
        run_class="other",
        variant_slug="nq_structure_wick_reject_4h_charts",
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={"pen": PEN_PRIMARY, "pre_days": PRE_DAYS, "post_days": POST_DAYS, "smoke": smoke},
    )
    try:
        if email:
            start = (
                "potions: NQ 4h WICK_REJECT charts STARTED\n\n"
                "Hub: %s\nPopulation: 4h invalidation WICK_REJECT pen≥0.05\n"
                "Window: confirm −%dd / +%dd 4h candles (extra post week for price path).\n"
                "Will attach as many unzipped PNGs as fit per email (no zip).\n"
                % (hub, PRE_DAYS, POST_DAYS)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            try:
                send_email(subject="potions: NQ 4h WICK_REJECT charts STARTED", body=start)
            except Exception as exc:  # noqa: BLE001
                _progress(hub, "start email failed: %s" % exc)

        _progress(hub, "load events")
        events = load_events(smoke=smoke)
        trades = load_trades_b()
        _progress(hub, "events=%d load 4h bars" % len(events))
        bars = load_4h()
        _progress(hub, "4h bars=%d" % len(bars))

        rows = []
        for i, (_, ev) in enumerate(events.iterrows(), start=1):
            eid = str(ev["event_id"])
            fname = "%03d_WICK_REJECT_%s.png" % (i, eid[:56])
            trade = None
            if not trades.empty and eid in trades.index:
                trade = trades.loc[eid]
            ok = chart_one(ev, bars, trade, charts_dir / fname)
            n_bars = 0
            if ok:
                confirm_open = _localize(pd.Timestamp(ev["confirm_bar_open_ts"]))
                confirm_close = _localize(pd.Timestamp(ev["confirm_bar_close_ts"]))
                plot = bars[
                    (bars.index >= confirm_open - pd.Timedelta(days=PRE_DAYS))
                    & (bars.index <= confirm_close + pd.Timedelta(days=POST_DAYS))
                ]
                n_bars = len(plot)
            exit_reason = ""
            net_usd = ""
            if trade is not None and len(trade):
                tr = trade.iloc[0] if isinstance(trade, pd.DataFrame) else trade
                exit_reason = str(tr.get("exit_reason") or "")
                net_usd = "%.0f" % float(tr.get("net_usd") or 0)
            rows.append(
                {
                    "chart_file": fname if ok else "",
                    "ok": int(ok),
                    "event_id": eid,
                    "slice": ev.get("slice", ""),
                    "confirm_bar_close_ts": ev["confirm_bar_close_ts"],
                    "break_direction": ev.get("break_direction", ""),
                    "outcome_direction": ev.get("outcome_direction", ""),
                    "penetration_ATR": ev.get("penetration_ATR", ""),
                    "n_bars": n_bars,
                    "exit_reason": exit_reason,
                    "net_usd": net_usd,
                }
            )
            if i % 10 == 0 or i == len(events):
                _progress(hub, "chart %d/%d ok=%s" % (i, len(events), ok))

        meta = pd.DataFrame(rows)
        meta.to_csv(hub / "chart_manifest.csv", index=False)
        write_index(hub, meta)

        pngs = sorted(charts_dir.glob("*.png"))
        total_bytes = sum(p.stat().st_size for p in pngs)
        stance = (
            "Potential reversal context, but far too weak and sparse for demo "
            "(Prototype B: marginal dollars, unstable R; not promote)."
        )
        body_lines = [
            "potions: NQ 4h WICK_REJECT charts COMPLETE",
            "",
            "Hub: %s" % hub,
            "Events charted: %d / %d (ok)" % (int(meta["ok"].sum()), len(meta)),
            "PNG bytes total: %.1f MB" % (total_bytes / (1024 * 1024)),
            "Window: confirm −%dd / +%dd 4h candles (1w pre + 1w post)." % (PRE_DAYS, POST_DAYS),
            "",
            "Stance: %s" % stance,
            "",
            "See INDEX.md + chart_manifest.csv.",
        ]
        (hub / "EMAIL.txt").write_text("\n".join(body_lines) + "\n", encoding="utf-8")
        (hub / "STATUS.md").write_text(
            "# Status — NQ 4h WICK_REJECT charts\n\n%s\n\nCharts: %d\n"
            % (stance, len(pngs)),
            encoding="utf-8",
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "n_events": len(meta),
                    "n_ok": int(meta["ok"].sum()),
                    "n_png": len(pngs),
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if email and pngs:
            batches = _pack_batches(pngs)
            for bi, batch in enumerate(batches, start=1):
                batch_mb = sum(p.stat().st_size for p in batch) / (1024 * 1024)
                subj = (
                    "potions: NQ 4h WICK_REJECT charts +1w post (%d/%d unzipped, batch %d/%d)"
                    % (len(batch), len(pngs), bi, len(batches))
                )
                b = "\n".join(body_lines) + "\n\nAttached %d PNGs (%.1f MB) batch %d/%d:\n" % (
                    len(batch),
                    batch_mb,
                    bi,
                    len(batches),
                )
                b += "\n".join("  %s" % p.name for p in batch)
                b += "\n\nFull hub: %s\n" % hub
                (hub / ("EMAIL_BATCH_%02d.txt" % bi)).write_text(b, encoding="utf-8")
                send_email(subject=subj, body=b, attachments=batch)
                _progress(hub, "emailed batch %d/%d n=%d" % (bi, len(batches), len(batch)))
        elif email:
            send_email(
                subject="potions: NQ 4h WICK_REJECT charts COMPLETE (no png)",
                body="\n".join(body_lines),
            )

        complete_run(rid, trades=int(meta["ok"].sum()), meta={"n_png": len(pngs)})
        return hub
    except Exception as exc:  # noqa: BLE001
        fail_run(rid, error=str(exc))
        err = "potions: NQ 4h WICK_REJECT charts FAILED\n\n%s\n\n%s\n" % (
            hub,
            traceback.format_exc()[-2500:],
        )
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if email:
            try:
                send_email(subject="potions: NQ 4h WICK_REJECT charts FAILED", body=err)
            except Exception:  # noqa: BLE001
                pass
        raise


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(smoke=bool(args.smoke), email=bool(args.email))


if __name__ == "__main__":
    main()
