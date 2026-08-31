"""Broker-like Engine+PaperBroker: NQ first-hour follow 3R.

Books:
  - follow_3r_all — every directional first hour
  - follow_3r_strong — first-hour body conviction = strong (|body|/range ≥ 0.66)

StrategyPlugin ``first_hour_follow`` on RTH 5m tape; market_close at 10:25 FH close;
SL at FH open; TP 3× body; flatten 15:59.
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
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
DEFAULT_OUT = REPO / "live" / "state" / "nq_1h_first_hour_broker"
NY = "America/New_York"
TICK = 0.25
POINT_VALUE = 20.0
FEE = 1.50

BOOKS: List[Tuple[str, str, Dict]] = [
    (
        "follow_3r_all",
        "follow 3R all first-hour",
        {"fade": False, "r_mult": 3.0, "require_fh_body": ""},
    ),
    (
        "follow_3r_strong",
        "follow 3R first-hour body=strong",
        {"fade": False, "r_mult": 3.0, "require_fh_body": "strong"},
    ),
]

DIAG_BASELINE = {
    "follow_3r_all": {"n": 3968, "wr": 0.382, "net": 243008.0, "ns": 9.32},
    "follow_3r_strong": {"n": 1125, "wr": 0.382 + 0.144, "net": None, "ns": 6.11},
}


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
    strategy_id = "nq_fh_%s" % slug
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
        "r_mult": float(cfg.get("r_mult") or 3.0),
        "fade": bool(cfg.get("fade")),
        "fh_start": "09:30",
        "fh_end": "10:30",
        "bar_minutes": 5,
        "eod_cutoff": "15:59",
        "min_fh_bars": 10,
        "require_fh_body": str(cfg.get("require_fh_body") or ""),
        "strong_body_min": 0.66,
        "suppress_alerts": True,
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

    _progress(hub, "RUN %s bars=%s" % (strategy_id, f"{len(df):,}"))
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

    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
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
    metrics = {
        "strategy_id": strategy_id,
        "slug": slug,
        "label": label,
        "bars": len(audit_bars),
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "win_rate": wr,
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "net_over_stress": (net / abs(stress)) if stress else 0.0,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "config": payload,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f"
        % (slug, trades, wr * 100.0, net, stress, metrics["net_over_stress"]),
    )
    return metrics


def write_summary(hub: Path, results: List[dict]) -> Path:
    lines = [
        "# NQ first-hour follow 3R (broker-like)",
        "",
        "Engine + PaperBroker + StrategyPlugin `first_hour_follow` on RTH 5m.",
        "Entry: `market_close` on last FH bar (10:25); SL = FH open; TP = 3× body; flatten 15:59.",
        "Realism: slip 1 tick, spread model, fee $1.50/unit, NQ $20/pt.",
        "",
        "| Book | Trades | WR | Net | Stress DD | N/S | vs diag n | vs diag net |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        base = DIAG_BASELINE.get(r["slug"], {})
        dn = base.get("n")
        dnet = base.get("net")
        dn_s = str(dn) if dn is not None else "—"
        if dnet is not None:
            dnet_s = "$%+.0f" % (float(r["net_usd"]) - float(dnet))
        else:
            dnet_s = "—"
        lines.append(
            "| {label} | {trades} | {wr:.1f}% | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | {dn} | {dnet} |".format(
                label=r["label"],
                trades=r["trades"],
                wr=100.0 * float(r["win_rate"]),
                net=float(r["net_usd"]),
                stress=float(r["intrabar_stress_dd_usd"]),
                ns=float(r["net_over_stress"]),
                dn=dn_s,
                dnet=dnet_s,
            )
        )
    lines.extend(
        [
            "",
            "## Diagnostic reference (pandas walk)",
            "",
            "- follow 3R all: n=3968 WR=38.2% net=$243008 N/S=9.32",
            "- follow 3R body=strong: n=1125 WR lift=+14.4pp avg lift=$+72 N/S=6.11",
            "",
            "Stance: promotion candidate only if broker-like N/S stays healthy vs diagnostic.",
            "",
        ]
    )
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, results: List[dict]) -> Path:
    lines = [
        "NQ first-hour follow 3R broker-like complete",
        "Hub: %s" % hub,
        "",
    ]
    for r in results:
        lines.append(
            "%s: trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f"
            % (
                r["slug"],
                r["trades"],
                100.0 * float(r["win_rate"]),
                float(r["net_usd"]),
                float(r["intrabar_stress_dd_usd"]),
                float(r["net_over_stress"]),
            )
        )
    lines.extend(["", "Diagnostic refs: all n=3968 net=$243k N/S=9.32; strong n=1125 N/S=6.11", ""])
    path = hub / "EMAIL.txt"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true", help="Last ~2y of RTH 5m only")
    args = ap.parse_args(argv)

    hub = args.out
    hub.mkdir(parents=True, exist_ok=True)
    if args.force and (hub / "PROGRESS.log").exists():
        (hub / "PROGRESS.log").unlink()

    try:
        df = load_rth_5m(progress=True)
        if args.smoke:
            cut = pd.Timestamp(df["ts"].max()).tz_convert(NY) - pd.Timedelta(days=500)
            df = df[df["ts"] >= cut].reset_index(drop=True)
            _progress(hub, "SMOKE bars=%d from %s" % (len(df), cut.date()))
        results = []
        for slug, label, cfg in BOOKS:
            results.append(
                run_book(hub=hub, slug=slug, label=label, cfg=cfg, df=df, force=args.force)
            )
        write_summary(hub, results)
        email_path = write_email(hub, results)
        write_run_manifest(
            hub,
            data_inputs=[NQ_5M_CSV],
            strategy_config={"strategy_type": "first_hour_follow", "books": [b[0] for b in BOOKS]},
            broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE, "tick": TICK},
            extra={"results": results},
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "results": results}, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: NQ first-hour follow 3R broker-like complete",
                body=email_path.read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(hub, "FAIL\n" + tb)
        fail = hub / "EMAIL_FAIL.txt"
        fail.write_text("NQ first-hour broker FAILED\nHub: %s\n\n%s\n" % (hub, tb), encoding="utf-8")
        try:
            send_email(subject="potions: NQ first-hour broker FAILED", body=fail.read_text())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
