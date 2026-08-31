"""NQ opening-candle follow via limit-at-close, risk = candle body, target 3R.

Contract (Engine + PaperBroker + ``first_hour_follow`` on RTH 5m):

- Opening candle green → buy **limit** at close; red → sell **limit** at close
- Stop = candle **open** (R = body)
- Target = **3R**; flatten ~15:59
- Cancel resting entry if open (SL) is swept before fill

Books:

1. ``open30_close_limit_3r`` — 09:30–10:00 opening candle
2. ``open1h_close_limit_3r`` — 09:30–10:30 opening candle
3. ``open30_market_close_3r`` — 30m control with market_close (same risk/TP)
4. ``open1h_market_close_3r`` — 1h control (matches retained baseline geometry)

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_opening_candle_close_limit --email
  python -m live.nq_opening_candle_close_limit --force --email --smoke
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .nq_5m_large_candle_study import NQ_5M_CSV, load_rth_5m
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
HUB_DEFAULT = REPO / "live" / "state" / "nq_opening_candle_close_limit"
FEE = 1.50
TICK = 0.25
POINT_VALUE = 20.0

BOOKS: List[Tuple[str, str, Dict]] = [
    (
        "open30_close_limit_3r",
        "30m open candle: limit@close SL=open TP=3R",
        {
            "entry_mode": "close_limit",
            "fh_end": "10:00",
            "min_fh_bars": 6,
            "sl_mode": "open",
            "tp_mode": "r_mult",
            "r_mult": 3.0,
        },
    ),
    (
        "open1h_close_limit_3r",
        "1h open candle: limit@close SL=open TP=3R",
        {
            "entry_mode": "close_limit",
            "fh_end": "10:30",
            "min_fh_bars": 10,
            "sl_mode": "open",
            "tp_mode": "r_mult",
            "r_mult": 3.0,
        },
    ),
    (
        "open30_market_close_3r",
        "30m open candle: market_close SL=open TP=3R",
        {
            "entry_mode": "market_close",
            "fh_end": "10:00",
            "min_fh_bars": 6,
            "sl_mode": "open",
            "tp_mode": "r_mult",
            "r_mult": 3.0,
        },
    ),
    (
        "open1h_market_close_3r",
        "1h open candle: market_close SL=open TP=3R",
        {
            "entry_mode": "market_close",
            "fh_end": "10:30",
            "min_fh_bars": 10,
            "sl_mode": "open",
            "tp_mode": "r_mult",
            "r_mult": 3.0,
        },
    ),
]


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def run_book(
    *,
    hub: Path,
    slug: str,
    label: str,
    cfg: Dict,
    df: pd.DataFrame,
    force: bool,
) -> dict:
    strategy_id = "nq_oc_%s" % slug
    state_root = hub / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(hub, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES["NQ"] = POINT_VALUE
    DEFAULT_TICK_SIZE["NQ"] = TICK
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": TICK,
        "entry_qty": 1,
        "fade": False,
        "fh_start": "09:30",
        "bar_minutes": 5,
        "eod_cutoff": "15:59",
        "require_fh_body": "",
        "suppress_alerts": True,
        **cfg,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="first_hour_follow",
                    version="v1",
                    instrument="NQ",
                    broker_instrument="NQ",
                    account_mode="paper",
                    enabled=True,
                    timeframes="5m",
                    max_contracts=4,
                    max_open_orders=8,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    spread = SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0,
        low_volume_multiplier=1.5,
        tick_size=TICK,
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={"NQ": TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=spread),
    )
    _progress(
        hub,
        "RUN %s bars=%s entry=%s fh_end=%s"
        % (strategy_id, f"{len(df):,}", cfg.get("entry_mode"), cfg.get("fh_end")),
    )
    audit_bars: List[AuditBar] = []
    n = 0
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts"]).tz_convert(NY)
        ts_s = ts.strftime("%Y-%m-%dT%H:%M:%S")
        bar = Bar(
            instrument="NQ",
            timeframe="5m",
            ts=ts_s,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            complete=True,
            source=str(NQ_5M_CSV),
        )
        engine.process_bar(bar)
        audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        n += 1
        if n % 50000 == 0:
            _progress(hub, "  %s %d/%d" % (strategy_id, n, len(df)))
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_v2b_fills(fills_path, strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument="NQ",
        fee_per_unit=FEE,
    )
    net = float(audit.get("net_usd") or 0.0)
    stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    trades = int(audit.get("trades") or len({u.trade_id for u in units}))
    wr = float(audit.get("win_rate") or 0.0)
    if wr > 1.0:
        wr = wr / 100.0

    entry_n = stop_n = tp_n = eod_n = 0
    if fills_path.exists():
        fdf = pd.read_csv(fills_path)
        reasons = fdf["reason"].astype(str) if "reason" in fdf.columns else pd.Series(dtype=str)
        entry_n = int((reasons == "entry").sum())
        stop_n = int(reasons.isin(["stop"]).sum())
        tp_n = int(reasons.isin(["tp", "target", "tp1", "tp2", "tp3"]).sum())
        eod_n = int(reasons.isin(["eod_close", "eod"]).sum())

    ns = (net / abs(stress)) if stress else 0.0
    metrics = {
        "instrument": "NQ",
        "strategy_id": strategy_id,
        "slug": slug,
        "label": label,
        "config": payload,
        "bars": len(audit_bars),
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "win_rate": wr,
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "net_over_stress": ns,
        "fill_entry_n": entry_n,
        "fill_stop_n": stop_n,
        "fill_tp_n": tp_n,
        "fill_eod_n": eod_n,
        "works": bool(ns >= 2.0 and net > 0 and trades >= 200),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f entries=%d stop=%d tp=%d eod=%d"
        % (slug, trades, wr * 100, net, stress, ns, entry_n, stop_n, tp_n, eod_n),
    )
    return metrics


def classify_stance(results: List[dict]) -> Tuple[str, Optional[str]]:
    """Return (stance text, best limit-book slug if HP-worthy)."""
    limit_books = [r for r in results if "close_limit" in str(r.get("slug", ""))]
    if not limit_books:
        return ("no limit books", None)
    best = max(limit_books, key=lambda r: float(r.get("net_over_stress") or 0.0))
    ns = float(best.get("net_over_stress") or 0.0)
    net = float(best.get("net_usd") or 0.0)
    trades = int(best.get("trades") or 0)
    if ns >= 2.0 and net > 0 and trades >= 200:
        return (
            "WORKS — best limit book N/S %.2f; proceed to HP analysis" % ns,
            str(best["slug"]),
        )
    if net > 0 and ns >= 1.0:
        return ("MARGINAL — green but weak N/S; HP optional diagnostic only", str(best["slug"]))
    return ("REJECT — limit-at-close opening candle does not clear N/S gate", None)


def write_summary(hub: Path, results: List[dict], stance: str, hp_slug: Optional[str]) -> Path:
    lines = [
        "# NQ opening-candle close-limit 3R",
        "",
        "Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.",
        "Realism: slip 1 tick, spread, fee $1.50/unit, NQ $20/pt.",
        "",
        "**Contract:** green → buy limit @ close; red → sell limit @ close; "
        "SL = open (R = body); TP = 3R; cancel if SL swept before fill.",
        "",
        "| Book | Trades | WR | Net | Stress | N/S | entries | stop | tp | eod |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            "| {label} | {trades} | {wr:.1f}% | ${net:,.0f} | ${stress:,.0f} | **{ns:.2f}** | "
            "{en} | {st} | {tp} | {eod} |".format(
                label=r["label"],
                trades=int(r["trades"]),
                wr=100.0 * float(r["win_rate"]),
                net=float(r["net_usd"]),
                stress=float(r["intrabar_stress_dd_usd"]),
                ns=float(r["net_over_stress"]),
                en=int(r.get("fill_entry_n", 0) or 0),
                st=int(r.get("fill_stop_n", 0) or 0),
                tp=int(r.get("fill_tp_n", 0) or 0),
                eod=int(r.get("fill_eod_n", 0) or 0),
            )
        )
    lines += [
        "",
        "## Stance",
        "",
        "- %s" % stance,
    ]
    if hp_slug:
        lines.append("- HP candidate: `%s`" % hp_slug)
    lines += [
        "",
        "## Notes",
        "",
        "- 30m books use `fh_end=10:00` / `min_fh_bars=6` (signal 09:55).",
        "- 1h books use `fh_end=10:30` / `min_fh_bars=10` (signal 10:25).",
        "- Market-close twins isolate the limit-fill haircut vs the retained 1h sleeve.",
        "",
        "Hub: `%s`" % hub,
        "",
    ]
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, results: List[dict], stance: str, hp_slug: Optional[str]) -> Path:
    lines = [
        "NQ opening-candle close-limit 3R study complete",
        "Hub: %s" % hub,
        "",
        "Stance: %s" % stance,
    ]
    if hp_slug:
        lines.append("HP candidate: %s" % hp_slug)
    lines.append("")
    for r in results:
        lines.append(
            "%s: trades=%d WR=%.1f%% net=$%+.0f N/S=%.2f | entry=%d stop=%d tp=%d eod=%d"
            % (
                r["slug"],
                int(r["trades"]),
                100 * float(r["win_rate"]),
                float(r["net_usd"]),
                float(r["net_over_stress"]),
                int(r.get("fill_entry_n", 0) or 0),
                int(r.get("fill_stop_n", 0) or 0),
                int(r.get("fill_tp_n", 0) or 0),
                int(r.get("fill_eod_n", 0) or 0),
            )
        )
    lines.append("")
    path = hub / "EMAIL.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=HUB_DEFAULT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--only", nargs="+", default=None)
    args = ap.parse_args(argv)

    hub = args.out
    hub.mkdir(parents=True, exist_ok=True)
    if args.force and (hub / "PROGRESS.log").exists() and not args.only:
        (hub / "PROGRESS.log").unlink()

    try:
        df = load_rth_5m(progress=True)
        if args.smoke:
            cut = pd.Timestamp(df["ts"].max()).tz_convert(NY) - pd.Timedelta(days=400)
            df = df[df["ts"] >= cut].reset_index(drop=True)
            _progress(hub, "SMOKE bars=%d" % len(df))
        books = BOOKS
        if args.only:
            want = set(args.only)
            books = [b for b in BOOKS if b[0] in want]
            if not books:
                raise SystemExit("no books matched --only %s" % sorted(want))

        results: List[dict] = []
        prior: Dict[str, dict] = {}
        summary_csv = hub / "summary.csv"
        if args.only and summary_csv.exists():
            try:
                for _, row in pd.read_csv(summary_csv).iterrows():
                    prior[str(row.get("slug"))] = row.to_dict()
            except Exception:
                prior = {}

        for slug, label, cfg in books:
            results.append(
                run_book(
                    hub=hub,
                    slug=slug,
                    label=label,
                    cfg=cfg,
                    df=df,
                    force=args.force,
                )
            )
        if args.only and prior:
            by_slug = {r["slug"]: r for r in results}
            merged = []
            for slug, _label, _cfg in BOOKS:
                if slug in by_slug:
                    merged.append(by_slug[slug])
                elif slug in prior:
                    merged.append(prior[slug])
            results = merged or results

        stance, hp_slug = classify_stance(results)
        write_summary(hub, results, stance, hp_slug)
        email_path = write_email(hub, results, stance, hp_slug)
        write_run_manifest(
            hub,
            data_inputs=[NQ_5M_CSV],
            strategy_config={"books": [b[0] for b in BOOKS], "stance": stance},
            broker_realism_config={
                "slippage_ticks": 1.0,
                "fee": FEE,
                "tick": TICK,
                "point_value": POINT_VALUE,
            },
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "stance": stance,
                    "hp_slug": hp_slug,
                    "results": [
                        {
                            "slug": r["slug"],
                            "trades": r["trades"],
                            "net_usd": r["net_usd"],
                            "net_over_stress": r["net_over_stress"],
                            "win_rate": r["win_rate"],
                        }
                        for r in results
                    ],
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: NQ opening-candle close-limit 3R complete",
                body=email_path.read_text(encoding="utf-8"),
            )
        _progress(hub, "COMPLETE stance=%s" % stance)
        return 0
    except Exception as exc:
        tb = traceback.format_exc()
        _progress(hub, "FAIL %s\n%s" % (exc, tb))
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": False, "error": str(exc), "traceback": tb}, indent=2) + "\n",
            encoding="utf-8",
        )
        fail_body = "NQ opening-candle close-limit FAILED\nHub: %s\n\n%s\n" % (hub, tb[-2500:])
        (hub / "EMAIL.txt").write_text(fail_body, encoding="utf-8")
        if args.email:
            try:
                send_email(subject="potions: NQ opening-candle close-limit FAILED", body=fail_body)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
