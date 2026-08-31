"""Broker-like first-hour variants: baseline / half-body / retrace / 0.75 ladder.

Books (Engine + PaperBroker + ``first_hour_follow`` on RTH 5m):

1. ``baseline_open_3xbody`` — market_close at FH close; SL=open; TP=3×body
2. ``halfbody_sl_3r`` — market_close at FH close; SL=0.5×body; TP=3R (R=SL dist)
3. ``retrace72_extreme_3r`` — limit at body 72% retrace from close; SL=FH extreme;
   TP=3R; cancel if extreme swept before fill
4. ``body75_ladder_1r2r3r`` — market_close; SL=0.75×body; 1@1R + 1@2R + 1@3R

Instruments: NQ (futures) or NAS100 (OANDA CFD).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_1h_first_hour_broker_variants --force --email
  python -m live.nq_1h_first_hour_broker_variants --instrument NAS100 --force --email
  python -m live.nas100_1h_first_hour_broker_variants --force --email
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
from .first_hour_follow_cross_market import MARKETS, load_market_5m
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
RTH_OPEN = time(9, 30)
RTH_CLOSE = time(16, 0)
FEE = 1.50
NAS100_1M_CSV = REPO / "fx" / "nas100_1m.csv"

INSTRUMENT_SPECS = {
    "NQ": {
        "state_prefix": "nq",
        "tick": 0.25,
        "point_value": 20.0,
        "fee_per_unit": FEE,
        "data_inputs": [NQ_5M_CSV],
        "default_out": REPO / "live" / "state" / "nq_1h_first_hour_broker_variants",
        "pv_note": "NQ $20/pt",
    },
    "NAS100": {
        "state_prefix": "nas100",
        "tick": 0.1,
        "point_value": 1.0,
        "fee_per_unit": FEE,
        "data_inputs": [NAS100_1M_CSV],
        "default_out": REPO / "live" / "state" / "nas100_1h_first_hour_broker_variants",
        "pv_note": "NAS100 $1/pt (CFD)",
    },
}

BOOKS: List[Tuple[str, str, Dict]] = [
    (
        "baseline_open_3xbody",
        "baseline SL=open TP=3×body 1-lot",
        {
            "entry_mode": "market_close",
            "sl_mode": "open",
            "tp_mode": "body_mult",
            "r_mult": 3.0,
        },
    ),
    (
        "halfbody_sl_3r",
        "half-body SL + 3R 1-lot",
        {
            "entry_mode": "market_close",
            "sl_mode": "body_frac",
            "sl_body_frac": 0.5,
            "tp_mode": "r_mult",
            "r_mult": 3.0,
        },
    ),
    (
        "retrace72_extreme_3r",
        "retrace body 72% → SL extreme → 3R",
        {
            "entry_mode": "retrace_limit",
            "retrace_frac": 0.72,
            "sl_mode": "extreme",
            "tp_mode": "r_mult",
            "r_mult": 3.0,
        },
    ),
    (
        "body75_ladder_1r2r3r",
        "0.75-body SL + 1R/2R/3R ladder 3-lot",
        {
            "entry_mode": "market_close",
            "sl_mode": "body_frac",
            "sl_body_frac": 0.75,
            "tp_mode": "r_mult",
            "r_mult": 3.0,
            "entry_qty": 3,
            "tp_ladder_r": [1.0, 2.0, 3.0],
        },
    ),
]

# NQ pandas-diagnostic refs only (not applicable to NAS100).
DIAG_NQ = {
    "baseline_open_3xbody": {"n": 3968, "net": 243008.0, "ns": 9.32},
    "halfbody_sl_3r": {"n": 3919, "net": 179506.0, "ns": 10.01},
    "retrace72_extreme_3r": {"n": 2522, "net": 110780.0, "ns": 2.22},
    "body75_ladder_1r2r3r": {"n": 3919, "net": 536261.0, "ns": 7.64},
}


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def load_instrument_rth_5m(instrument: str, hub: Path) -> pd.DataFrame:
    if instrument == "NQ":
        return load_rth_5m(progress=True)
    market = MARKETS["NAS100"]
    df = load_market_5m(market, hub)
    if df is None or df.empty:
        raise RuntimeError("missing NAS100 RTH 5m bars")
    return df.reset_index(drop=True)


def run_book(
    *,
    hub: Path,
    instrument: str,
    tick: float,
    point_value: float,
    fee: float,
    data_source: Path,
    slug: str,
    label: str,
    cfg: Dict,
    df: pd.DataFrame,
    force: bool,
) -> dict:
    prefix = INSTRUMENT_SPECS[instrument]["state_prefix"]
    strategy_id = "%s_fh_%s" % (prefix, slug)
    state_root = hub / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(hub, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES[instrument] = point_value
    DEFAULT_TICK_SIZE[instrument] = tick
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": int(cfg.get("entry_qty") or 1),
        "fade": False,
        "fh_start": "09:30",
        "fh_end": "10:30",
        "bar_minutes": 5,
        "eod_cutoff": "15:59",
        "min_fh_bars": 10,
        "require_fh_body": "",
        "suppress_alerts": True,
        **{k: v for k, v in cfg.items() if k != "entry_qty"},
    }
    if "entry_qty" in cfg:
        payload["entry_qty"] = int(cfg["entry_qty"])
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="first_hour_follow",
                    version="v1",
                    instrument=instrument,
                    broker_instrument=instrument,
                    account_mode="paper",
                    enabled=True,
                    timeframes="5m",
                    max_contracts=8,
                    max_open_orders=16,
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
        tick_size=tick,
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={instrument: tick},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=spread),
    )
    _progress(hub, "RUN %s bars=%s entry=%s" % (strategy_id, f"{len(df):,}", cfg.get("entry_mode")))
    audit_bars: List[AuditBar] = []
    n = 0
    for _, row in df.iterrows():
        ts = pd.Timestamp(row["ts"]).tz_convert(NY)
        ts_s = ts.strftime("%Y-%m-%dT%H:%M:%S")
        bar = Bar(
            instrument=instrument,
            timeframe="5m",
            ts=ts_s,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            complete=True,
            source=str(data_source),
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
        instrument=instrument,
        fee_per_unit=fee,
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

    diag = DIAG_NQ if instrument == "NQ" else {}
    metrics = {
        "instrument": instrument,
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
        "net_over_stress": (net / abs(stress)) if stress else 0.0,
        "fill_entry_n": entry_n,
        "fill_stop_n": stop_n,
        "fill_tp_n": tp_n,
        "fill_eod_n": eod_n,
        "diag_n": diag.get(slug, {}).get("n"),
        "diag_net": diag.get(slug, {}).get("net"),
        "diag_ns": diag.get(slug, {}).get("ns"),
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f entries=%d stop=%d tp=%d eod=%d"
        % (slug, trades, wr * 100, net, stress, metrics["net_over_stress"], entry_n, stop_n, tp_n, eod_n),
    )
    return metrics


def write_summary(hub: Path, instrument: str, pv_note: str, results: List[dict]) -> Path:
    diag_note = (
        "- Diagnostic refs (NQ pandas): baseline N/S 9.32, half-body 3R N/S 10.01, "
        "retrace72 N/S 2.22, ladder N/S 7.64."
        if instrument == "NQ"
        else "- No NAS100 pandas diag table; compare to NQ broker N/S ranks."
    )
    lines = [
        "# %s first-hour broker-like variants" % instrument,
        "",
        "Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.",
        "Realism: slip 1 tick, spread, fee $1.50/unit, %s." % pv_note,
        "",
        "| Book | Trades | WR | Net | Stress | N/S | entries | stop | tp | eod | vs diag N/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        dns = r.get("diag_ns")
        dns_s = "%.2f" % float(dns) if dns is not None and not (isinstance(dns, float) and pd.isna(dns)) else "—"
        lines.append(
            "| {label} | {trades} | {wr:.1f}% | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | "
            "{en} | {st} | {tp} | {eod} | {dns} |".format(
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
                dns=dns_s,
            )
        )
    lines += [
        "",
        "## Notes",
        "",
        "- Baseline / half-body: `market_close` entry on 10:25 bar; protective **stop** + TP **limit**.",
        "- Retrace 72%: resting **limit** entry; cancel if FH extreme swept before fill; then stop+TP.",
        "- 0.75-body ladder: 3-lot entry; stop @ 0.75×body; 1-lot limits @ 1R/2R/3R (no OCO across rungs).",
        diag_note,
        "",
        "Hub: `%s`" % hub,
        "",
    ]
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, instrument: str, results: List[dict]) -> Path:
    lines = [
        "%s first-hour broker-like variants complete" % instrument,
        "Hub: %s" % hub,
        "",
    ]
    for r in results:
        lines.append(
            "%s: trades=%d WR=%.1f%% net=$%+.0f N/S=%.2f | fills entry=%d stop=%d tp=%d eod=%d"
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
    lines += ["", "Stance: compare to NQ broker ranks; promote only if N/S holds.", ""]
    path = hub / "EMAIL.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--instrument",
        type=str,
        default="NQ",
        choices=list(INSTRUMENT_SPECS.keys()),
    )
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument(
        "--only",
        nargs="+",
        default=None,
        help="Run only these book slugs (default: all)",
    )
    args = ap.parse_args(argv)

    instrument = str(args.instrument).upper()
    spec = INSTRUMENT_SPECS[instrument]
    tick = float(spec["tick"])
    point_value = float(spec["point_value"])
    fee = float(spec["fee_per_unit"])
    data_source = Path(spec["data_inputs"][0])
    hub = args.out or Path(spec["default_out"])
    hub.mkdir(parents=True, exist_ok=True)
    if args.force and (hub / "PROGRESS.log").exists() and not args.only:
        (hub / "PROGRESS.log").unlink()

    try:
        df = load_instrument_rth_5m(instrument, hub)
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
        results = []
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
                    instrument=instrument,
                    tick=tick,
                    point_value=point_value,
                    fee=fee,
                    data_source=data_source,
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
        write_summary(hub, instrument, str(spec["pv_note"]), results)
        email_path = write_email(hub, instrument, results)
        write_run_manifest(
            hub,
            data_inputs=list(spec["data_inputs"]),
            strategy_config={"instrument": instrument, "books": [b[0] for b in BOOKS]},
            broker_realism_config={
                "slippage_ticks": 1.0,
                "fee": fee,
                "tick": tick,
                "point_value": point_value,
            },
            extra={"results": results},
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "instrument": instrument, "results": results}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: %s FH broker variants complete" % instrument,
                body=email_path.read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(hub, "FAIL\n" + tb)
        fail = hub / "EMAIL_FAIL.txt"
        fail.write_text(tb, encoding="utf-8")
        try:
            send_email(subject="potions: %s FH broker variants FAILED" % instrument, body=tb)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
