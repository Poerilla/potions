"""NQ v2b OR close→swing ungated: 5m signals + 1m PaperBroker fills.

First-two-years research sleeve (default 2010-06-07 → 2012-06-07):

- 15m opening range from 5m RTH bars
- Breakout = 5m **close** outside OR (no OCO/stops)
- Entry = limit at first causal pullback swing close
- S_1_1_3 exits (v2b OR geometry shifted to swing)
- No bull/vol/MA regime filter

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_v2b_or_close_swing_broker --years 2 --email --force
  python -m live.nq_v2b_or_close_swing_broker --chart 200
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytz

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills

REPO = Path(__file__).resolve().parents[1]
NY = pytz.timezone("America/New_York")
DEFAULT_OUT = REPO / "live" / "state" / "nq_or15_close_swing_v2b"
NQ_5M = REPO / "nq" / "nq_5min_rth.csv"
DSR = "TRL-2026-00175"
SIGNAL_OFFSET_MIN = 5


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _utc_z(ts: pd.Timestamp) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    return t.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "nq_v2b_or_close_swing_ungated",
            "is_independent": "TRUE",
            "market": "NQ",
            "replay_window_start": "2010-06-07",
            "replay_window_end": "2012-06-07",
            "replay_type": "FIRST_N_YEARS",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "entry": "5m_close_outside_or15_then_swing_limit",
                    "book": "S_1_1_3",
                    "regime": "none",
                }
            ),
            "fixed_parameters_ref": "live/strategies/v2b_or_close_swing.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "v2b ungated OR15 close+swing on 5m; first 2y NQ",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr_complete() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",COMPLETE,", 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def load_5m(path: Path, start: date, end: date) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["ts_event"], utc=True).dt.tz_convert(NY)
    df = df.assign(ts=ts).set_index("ts").sort_index()
    lo = pd.Timestamp(start, tz=NY)
    hi = pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)
    df = df[(df.index >= lo) & (df.index < hi)]
    return df


def _signal_bars(df: pd.DataFrame) -> Tuple[List[Bar], List[AuditBar]]:
    out: List[Bar] = []
    audit: List[AuditBar] = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        ts_s = _utc_z(ts)
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        out.append(
            Bar(
                instrument="NQ",
                timeframe="5m",
                ts=ts_s,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(NQ_5M),
            )
        )
        audit.append(AuditBar(ts_s, o, h, l, c))
    return out, audit


def _concat_1m(gby: Dict[date, pd.DataFrame], start: date, end: date) -> pd.DataFrame:
    frames = []
    for d in sorted(gby):
        if d < start or d > end:
            continue
        part = gby[d]
        if part is None or part.empty:
            continue
        frames.append(part)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames).sort_index()
    if out.index.tz is None:
        out.index = out.index.tz_localize(NY)
    else:
        out.index = out.index.tz_convert(NY)
    return out


def _replay_5m_with_1m(
    engine: Engine,
    *,
    signal_bars: Sequence[Bar],
    one_m: pd.DataFrame,
    label: str,
    output_root: Path,
) -> int:
    """Left-labeled 5m signal (no fill) interleaved with 1m broker fills up to bar completion."""
    idx = one_m.index
    seen = 0
    n = len(signal_bars)
    cursor: Optional[pd.Timestamp] = None
    source = str(MARKETS["nq"].dbn_path)
    offset = pd.Timedelta(minutes=SIGNAL_OFFSET_MIN)

    def replay_1m_until(start: Optional[pd.Timestamp], end: pd.Timestamp) -> None:
        nonlocal seen
        lo = 0 if start is None else idx.searchsorted(start, side="left")
        hi = idx.searchsorted(end, side="left")
        if lo >= hi:
            return
        sl = one_m.iloc[lo:hi]
        vol = sl["volume"] if "volume" in sl.columns else None
        for j, (ts, o, h, l, c) in enumerate(zip(sl.index, sl["open"], sl["high"], sl["low"], sl["close"])):
            if min(float(o), float(h), float(l), float(c)) <= 0:
                continue
            engine.process_bar(
                Bar(
                    instrument="NQ",
                    timeframe="1m",
                    ts=_utc_z(ts),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(vol.iloc[j]) if vol is not None else 0.0,
                    complete=True,
                    source=source,
                )
            )
            seen += 1

    for i, sbar in enumerate(signal_bars):
        left = pd.Timestamp(sbar.ts)
        if left.tzinfo is None:
            left = left.tz_localize("UTC")
        else:
            left = left.tz_convert("UTC")
        complete = left + offset
        replay_1m_until(cursor, complete)
        # Strategy sees left-label ts for RTH/OR clock; fills already advanced to completion.
        engine.process_bar(sbar, broker_fills=False)
        cursor = complete
        if (i + 1) % 5000 == 0 or (i + 1) == n:
            _progress(output_root, "  %s signal %d/%d (1m=%d)" % (label, i + 1, n, seen))

    if cursor is not None and len(idx):
        replay_1m_until(cursor, idx[-1] + pd.Timedelta(minutes=1))
    _progress(output_root, "  %s done 1m=%d" % (label, seen))
    return seen


def run_replay(
    *,
    output_root: Path,
    years: float,
    force: bool,
    email: bool,
    causality_mode: str,
) -> dict:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    _append_dsr()

    start = date(2010, 6, 7)
    end = (pd.Timestamp(start) + pd.DateOffset(years=years)).date()
    strategy_id = "nq_v2b_or_close_swing_ungated"
    state_root = output_root / "states" / strategy_id
    rid = begin_run(
        run_class="broker_like",
        variant_slug=strategy_id,
        instrument="NQ",
        hub_path=str(output_root.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={"years": years, "start": str(start), "end": str(end), "book": "S_1_1_3"},
    )
    try:
        if force and state_root.exists():
            shutil.rmtree(state_root)

        POINT_VALUES["NQ"] = 20.0
        DEFAULT_TICK_SIZE["NQ"] = 0.25

        _progress(output_root, "Loading NQ 5m RTH %s → %s" % (start, end))
        df5 = load_5m(NQ_5M, start, end)
        signal_bars, audit_bars = _signal_bars(df5)
        _progress(output_root, "  5m bars=%d" % len(signal_bars))

        cfg = MARKETS["nq"]
        _progress(output_root, "Loading NQ 1m DBN …")
        gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), "nq")
        one_m = _concat_1m(gby, start, end)
        _progress(output_root, "  1m bars=%d" % len(one_m))

        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        payload = {
            "tick_size": 0.25,
            "entry_qty": 5,
            "tp1_qty": 1,
            "tp2_qty": 1,
            "rth_start": "09:30",
            "or_end": "09:45",
            "or_bars": 3,
            "eod_cutoff": "15:55",
            "session_end": "16:00",
            "bar_minutes": 5,
            "max_campaigns": 1,
            "swing_require_pullback": True,
            "suppress_alerts": True,
        }
        store.write_table(
            "strategy_instances",
            [
                as_row(
                    StrategyInstance(
                        strategy_id=strategy_id,
                        strategy_type="v2b_or_close_swing",
                        version="v1",
                        instrument="NQ",
                        broker_instrument="NQ",
                        account_mode="paper",
                        enabled=True,
                        timeframes="5m",
                        max_contracts=8,
                        max_open_orders=32,
                        config_json=json.dumps(payload, sort_keys=True),
                    )
                )
            ],
        )
        engine = Engine(
            store=store,
            persist_bars=False,
            persist_health=False,
            tick_size={"NQ": 0.25},
            notification_sink=NullNotificationSink(),
            verification_provider=QuietPaperVerificationProvider(),
            emit_order_alerts=False,
            broker_log_events=False,
            broker_persist_modifications=False,
            causality_mode=causality_mode,
            **hardened_replay_engine_kwargs(slippage_ticks=1.0),
        )
        _progress(output_root, "START %s causality=%s" % (strategy_id, causality_mode))
        _replay_5m_with_1m(
            engine,
            signal_bars=signal_bars,
            one_m=one_m,
            label=strategy_id,
            output_root=output_root,
        )
        store.flush_tables()

        units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
        audit = fast_intraday_audit(
            strategy_id=strategy_id,
            state_root=state_root,
            bars=audit_bars,
            units=units,
            instrument="NQ",
            fee_per_unit=1.50,
        )
        net = float(audit.get("net_usd") or 0.0)
        stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
        ns = (net / abs(stress)) if stress else 0.0
        trades = int(audit.get("trades") or len({u.trade_id for u in units}))
        wr = float(audit.get("win_rate") or 0.0)
        pf = float(audit.get("profit_factor") or 0.0)
        if ns >= 2.0 and trades >= 40:
            stance = "research — interesting N/S"
        elif net > 0 and trades >= 20:
            stance = "weak — needs tune"
        else:
            stance = "reject / thin"

        metrics = {
            "strategy_id": strategy_id,
            "market": "NQ",
            "book": "S_1_1_3",
            "window_start": str(start),
            "window_end": str(end),
            "trades": trades,
            "net_usd": net,
            "intrabar_stress_dd_usd": stress,
            "net_over_stress": ns,
            "win_rate": wr / 100.0 if wr > 1 else wr,
            "profit_factor": pf,
            "stance": stance,
            "dsr_trial": DSR,
            "bars_5m": len(signal_bars),
            "bars_1m": len(one_m),
        }
        (state_root / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
        summary = (
            "# NQ OR15 close→swing ungated (v2b)\n\n"
            "Window: %s → %s · DSR %s\n\n"
            "| Market | Book | Trades | Net | Stress DD | N/S | WR | PF | Stance |\n"
            "|---|---|---:|---:|---:|---:|---:|---:|---|\n"
            "| NQ | S_1_1_3 close+swing | %d | $%+.0f | $%.0f | %.2f | %.1f%% | %.2f | %s |\n\n"
            "Hub: `%s`\n"
            % (
                start,
                end,
                DSR,
                trades,
                net,
                stress,
                ns,
                (wr if wr > 1 else wr * 100.0),
                pf,
                stance,
                output_root,
            )
        )
        (output_root / "SUMMARY.md").write_text(summary)
        pd.DataFrame([metrics]).to_csv(output_root / "summary.csv", index=False)
        complete_run(
            rid,
            net_usd=net,
            stress_dd_usd=stress,
            ns=ns,
            trades=trades,
        )
        _mark_dsr_complete()
        body = "potions: NQ v2b OR close→swing ungated DONE\n\n" + summary
        (output_root / "EMAIL.txt").write_text(body)
        if email:
            send_email(subject="potions: NQ OR15 close+swing ungated (2y)", body=body)
        _progress(output_root, "DONE net=%+.0f N/S=%.2f trades=%d" % (net, ns, trades))
        return metrics
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        err = traceback.format_exc()
        (output_root / "EMAIL.txt").write_text("FAILED\n\n" + err)
        if email:
            send_email(subject="potions: NQ OR15 close+swing FAILED", body=err[-4000:])
        raise


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------


def _load_features(state_root: Path) -> pd.DataFrame:
    path = state_root / "feature_snapshots.csv"
    if not path.exists():
        return pd.DataFrame()
    fs = pd.read_csv(path)
    if fs.empty:
        return fs
    fs["event_ts"] = pd.to_datetime(fs["event_ts"], utc=True).dt.tz_convert(NY)
    return fs


def _trade_days_from_fills(fills: pd.DataFrame) -> List[date]:
    entries = fills[fills["reason"].astype(str) == "entry"].copy()
    if entries.empty:
        return []
    entries["ts"] = pd.to_datetime(entries["ts"], utc=True).dt.tz_convert(NY)
    days = sorted({t.date() for t in entries["ts"]})
    return days


def _plot_session(
    *,
    day: date,
    bars5: pd.DataFrame,
    fills: pd.DataFrame,
    features: pd.DataFrame,
    out_path: Path,
    net_usd: float,
) -> None:
    day_bars = bars5[bars5.index.date == day]
    if day_bars.empty:
        return
    fig, ax = plt.subplots(figsize=(14, 7))
    width = (5.0 / (24 * 60)) * 0.8
    for ts, row in day_bars.iterrows():
        o, h, l, c = float(row.open), float(row.high), float(row.low), float(row.close)
        color = "#2e7d32" if c >= o else "#c62828"
        x = mdates.date2num(ts.to_pydatetime())
        ax.plot([x, x], [l, h], color=color, linewidth=1.0, zorder=2)
        ax.add_patch(
            plt.Rectangle(
                (x - width / 2.0, min(o, c)),
                width,
                max(abs(c - o), 1e-6),
                facecolor=color,
                edgecolor=color,
                linewidth=0.6,
                zorder=3,
            )
        )

    # OR levels from feature or first 3 bars
    or_hi = or_lo = None
    if not features.empty:
        ready = features[(features["feature_name"] == "v2b_or_ready") & (features["event_ts"].dt.date == day)]
        if not ready.empty:
            try:
                meta = json.loads(str(ready.iloc[0]["metadata_json"]))
                or_hi = float(meta["or_high"])
                or_lo = float(meta["or_low"])
            except Exception:
                pass
    if or_hi is None:
        opening = day_bars.iloc[:3]
        if len(opening):
            or_hi = float(opening["high"].max())
            or_lo = float(opening["low"].min())
    if or_hi is not None and or_lo is not None:
        ax.axhline(or_hi, color="#1565c0", linestyle="-", linewidth=1.2, label="OR high", zorder=4)
        ax.axhline(or_lo, color="#1565c0", linestyle="-", linewidth=1.2, label="OR low", zorder=4)
        ax.axhspan(or_lo, or_hi, color="#90caf9", alpha=0.15, zorder=0)

    # Breakout + swing from features
    if not features.empty:
        bo = features[(features["feature_name"] == "v2b_or_breakout_detect") & (features["event_ts"].dt.date == day)]
        for _, row in bo.iterrows():
            try:
                meta = json.loads(str(row["metadata_json"]))
                px = float(meta.get("breakout_close"))
            except Exception:
                continue
            ts = row["event_ts"]
            ax.scatter([ts], [px], marker="D", s=70, color="#f9a825", zorder=10, label="breakout")
        sw = features[(features["feature_name"] == "v2b_swing_entry_arm") & (features["event_ts"].dt.date == day)]
        for _, row in sw.iterrows():
            try:
                meta = json.loads(str(row["metadata_json"]))
                px = float(meta.get("swing_close"))
                st = pd.to_datetime(meta.get("swing_ts"), utc=True).tz_convert(NY)
                stop = float(meta.get("stop") or 0)
                tp1 = float(meta.get("tp1") or 0)
                tp2 = float(meta.get("tp2") or 0)
            except Exception:
                continue
            ax.scatter([st], [px], marker="s", s=80, color="#6a1b9a", zorder=11, label="swing")
            ax.axhline(px, color="#6a1b9a", linestyle="--", linewidth=1.0, alpha=0.8)
            if stop:
                ax.axhline(stop, color="#c62828", linestyle=":", linewidth=1.0, label="SL")
            if tp1:
                ax.axhline(tp1, color="#2e7d32", linestyle="-.", linewidth=1.0, label="TP1")
            if tp2:
                ax.axhline(tp2, color="#00838f", linestyle="-.", linewidth=1.0, label="TP2")

    day_fills = fills.copy()
    day_fills["ts"] = pd.to_datetime(day_fills["ts"], utc=True).dt.tz_convert(NY)
    day_fills = day_fills[day_fills["ts"].dt.date == day]
    for _, f in day_fills.iterrows():
        reason = str(f["reason"])
        color = {
            "entry": "#1565c0",
            "tp1": "#2e7d32",
            "tp2": "#00838f",
            "stop": "#c62828",
            "wide_stop": "#c62828",
            "runner_stop": "#c62828",
            "eod_close": "#6d4c41",
            "add": "#455a64",
        }.get(reason, "#333333")
        marker = "^" if str(f["side"]).lower() == "buy" else "v"
        if reason != "entry":
            marker = "o" if reason.startswith("tp") else "x"
        ax.scatter([f["ts"]], [float(f["price"])], marker=marker, s=90, color=color, zorder=12, label=reason)

    ax.set_title("NQ 5m · %s · OR15 close→swing · PnL $%+.0f" % (day.isoformat(), net_usd))
    ax.set_ylabel("NQ")
    ax.grid(True, color="#dedede", linewidth=0.5, alpha=0.8)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=NY))
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)


def run_charts(*, output_root: Path, limit: int = 200) -> int:
    output_root = Path(output_root)
    strategy_id = "nq_v2b_or_close_swing_ungated"
    state_root = output_root / "states" / strategy_id
    fills_path = state_root / "fills.csv"
    if not fills_path.exists():
        raise SystemExit("Missing fills at %s — run replay first" % fills_path)
    fills = pd.read_csv(fills_path)
    days = _trade_days_from_fills(fills)[: int(limit)]
    if not days:
        raise SystemExit("No entry fills to chart")
    start, end = days[0], days[-1]
    _progress(output_root, "Loading 5m for charts %s → %s (%d sessions)" % (start, end, len(days)))
    bars5 = load_5m(NQ_5M, start, end)
    features = _load_features(state_root)

    # PnL by day from units (NQ point value $20)
    units = units_from_v2b_fills(fills_path, strategy_id)
    pnl_by_day: Dict[date, float] = {}
    for u in units:
        ets = pd.Timestamp(u.entry_ts)
        if ets.tzinfo is None:
            ets = ets.tz_localize("UTC")
        d = ets.tz_convert(NY).date()
        sign = 1.0 if u.direction == "Long" else -1.0
        gross = sign * (float(u.exit_price) - float(u.entry_price)) * 20.0
        fee = 1.50
        pnl_by_day[d] = pnl_by_day.get(d, 0.0) + gross - fee

    charts_root = output_root / "charts" / "nq_5m"
    charts_root.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, day in enumerate(days):
        out = charts_root / ("nq_5m_%s.png" % day.isoformat())
        _plot_session(
            day=day,
            bars5=bars5,
            fills=fills,
            features=features,
            out_path=out,
            net_usd=float(pnl_by_day.get(day, 0.0)),
        )
        written += 1
        if (i + 1) % 25 == 0 or (i + 1) == len(days):
            _progress(output_root, "  charts %d/%d" % (i + 1, len(days)))
    _progress(output_root, "DONE charts=%d → %s" % (written, charts_root))
    return written


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--years", type=float, default=2.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    p.add_argument("--causality-mode", choices=["audit", "strict"], default="strict")
    p.add_argument("--chart", type=int, default=0, help="If >0, build this many session charts (after replay)")
    p.add_argument("--charts-only", action="store_true")
    args = p.parse_args(argv)

    if not args.charts_only:
        run_replay(
            output_root=args.output_root,
            years=float(args.years),
            force=bool(args.force),
            email=bool(args.email),
            causality_mode=str(args.causality_mode),
        )
    if int(args.chart) > 0 or args.charts_only:
        n = run_charts(output_root=args.output_root, limit=int(args.chart) or 200)
        if args.email or not args.charts_only:
            hub = Path(args.output_root)
            body = (hub / "EMAIL.txt").read_text() if (hub / "EMAIL.txt").exists() else ""
            body += "\nCharts written: %d under %s/charts/nq_5m/\n" % (n, hub)
            (hub / "EMAIL.txt").write_text(body)
            send_email(subject="potions: NQ OR15 close+swing charts ready", body=body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
