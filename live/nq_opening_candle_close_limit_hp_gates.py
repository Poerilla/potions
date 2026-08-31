"""Broker-like Engine gates for top HP notables on open1h_close_limit_3r.

Takes the strongest dual-lift HP buckets from
``live/state/nq_opening_candle_close_limit/hp/`` and re-runs them as
StrategyPlugin entry gates through Engine + PaperBroker (limit@close / SL=open /
TP=3R). Baseline is included for comparison (cached from parent hub when present).

Top-5 HP books (by mill z_WR, deduped):

1. strong FH body — native ``require_fh_body=strong``
2. trade_with_po — session allowlist from mill campaigns
3. during_counter_with_po — session allowlist
4. fh_p90 — session allowlist from first_hour_candles (all large-range days)
5. rsi_gt70 — session allowlist from mill campaigns

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_opening_candle_close_limit_hp_gates --email
  python -m live.nq_opening_candle_close_limit_hp_gates --force --email --smoke
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
from .nq_opening_candle_close_limit import FEE, POINT_VALUE, TICK
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
PARENT = REPO / "live" / "state" / "nq_opening_candle_close_limit"
HP_HUB = PARENT / "hp"
HUB_DEFAULT = PARENT / "hp_gates"

BASE_CFG = {
    "entry_mode": "close_limit",
    "fh_end": "10:30",
    "min_fh_bars": 10,
    "sl_mode": "open",
    "tp_mode": "r_mult",
    "r_mult": 3.0,
}


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _write_dates(path: Path, dates) -> int:
    uniq = sorted({str(d)[:10] for d in dates if str(d)[:10]})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(uniq) + ("\n" if uniq else ""), encoding="utf-8")
    return len(uniq)


def build_allowlists(hub: Path) -> Dict[str, Path]:
    """Build session allowlists for non-native HP gates. Returns slug → path."""
    camp_path = HP_HUB / "campaigns.csv"
    fh_path = HP_HUB / "first_hour_candles.csv"
    if not camp_path.exists():
        raise FileNotFoundError("missing HP campaigns: %s (run nq_opening_candle_close_limit_hp)" % camp_path)
    camp = pd.read_csv(camp_path)
    out_dir = hub / "allowlists"
    paths: Dict[str, Path] = {}

    # trade_with_po
    m = camp["trade_vs_po"].astype(str) == "trade_with_po"
    paths["hp_trade_with_po"] = out_dir / "trade_with_po.txt"
    n = _write_dates(paths["hp_trade_with_po"], camp.loc[m, "session_date"])
    _progress(hub, "ALLOWLIST trade_with_po days=%d" % n)

    # during_counter_with_po
    if "regime" not in camp.columns:
        raise KeyError("campaigns.csv missing regime column")
    m = camp["regime"].astype(str) == "during_counter_with_po"
    paths["hp_during_counter_with_po"] = out_dir / "during_counter_with_po.txt"
    n = _write_dates(paths["hp_during_counter_with_po"], camp.loc[m, "session_date"])
    _progress(hub, "ALLOWLIST during_counter_with_po days=%d" % n)

    # fh_p90 from first-hour candles (all large-range sessions, not fill-only)
    if fh_path.exists():
        fh = pd.read_csv(fh_path)
        m = fh["fh_size"].astype(str) == "fh_p90"
        dates = fh.loc[m, "session_date"]
    else:
        m = camp["fh_size"].astype(str) == "fh_p90"
        dates = camp.loc[m, "session_date"]
    paths["hp_fh_p90"] = out_dir / "fh_p90.txt"
    n = _write_dates(paths["hp_fh_p90"], dates)
    _progress(hub, "ALLOWLIST fh_p90 days=%d" % n)

    # rsi_gt70
    m = camp["rsi_bucket"].astype(str) == "rsi_gt70"
    paths["hp_rsi_gt70"] = out_dir / "rsi_gt70.txt"
    n = _write_dates(paths["hp_rsi_gt70"], camp.loc[m, "session_date"])
    _progress(hub, "ALLOWLIST rsi_gt70 days=%d" % n)

    return paths


def books_spec(allow: Dict[str, Path]) -> List[Tuple[str, str, Dict]]:
    return [
        (
            "baseline_open1h_close_limit_3r",
            "1h limit@close baseline (ungated)",
            {**BASE_CFG, "require_fh_body": ""},
        ),
        (
            "hp_strong_body",
            "HP: first-hour body=strong",
            {**BASE_CFG, "require_fh_body": "strong"},
        ),
        (
            "hp_trade_with_po",
            "HP: trade_with_po",
            {
                **BASE_CFG,
                "require_fh_body": "",
                "entry_dates_path": str(allow["hp_trade_with_po"]),
            },
        ),
        (
            "hp_during_counter_with_po",
            "HP: during_counter_with_po",
            {
                **BASE_CFG,
                "require_fh_body": "",
                "entry_dates_path": str(allow["hp_during_counter_with_po"]),
            },
        ),
        (
            "hp_fh_p90",
            "HP: first-hour range fh_p90",
            {
                **BASE_CFG,
                "require_fh_body": "",
                "entry_dates_path": str(allow["hp_fh_p90"]),
            },
        ),
        (
            "hp_rsi_gt70",
            "HP: hourly RSI > 70",
            {
                **BASE_CFG,
                "require_fh_body": "",
                "entry_dates_path": str(allow["hp_rsi_gt70"]),
            },
        ),
    ]


def _parent_baseline_metrics() -> Optional[dict]:
    metrics = PARENT / "states" / "nq_oc_open1h_close_limit_3r" / "metrics.json"
    if metrics.exists():
        return json.loads(metrics.read_text(encoding="utf-8"))
    return None


def run_book(
    *,
    hub: Path,
    slug: str,
    label: str,
    cfg: Dict,
    df: pd.DataFrame,
    force: bool,
) -> dict:
    strategy_id = "nq_ocg_%s" % slug
    state_root = hub / "states" / strategy_id
    metrics_path = state_root / "metrics.json"

    # Reuse parent baseline when ungated and cache present.
    if slug == "baseline_open1h_close_limit_3r" and not force:
        parent = _parent_baseline_metrics()
        if parent is not None:
            m = dict(parent)
            m["strategy_id"] = strategy_id
            m["slug"] = slug
            m["label"] = label
            m["from_parent_cache"] = True
            state_root.mkdir(parents=True, exist_ok=True)
            metrics_path.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            _progress(hub, "CACHE_PARENT %s N/S=%.2f" % (slug, float(m.get("net_over_stress") or 0)))
            return m

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
        "RUN %s bars=%s body=%s dates=%s"
        % (
            strategy_id,
            f"{len(df):,}",
            payload.get("require_fh_body") or "-",
            "yes" if payload.get("entry_dates_path") else "no",
        ),
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
    # HP sleeves: lower trade floor than the all-days book.
    min_tr = 80 if slug.startswith("hp_") else 200
    works = bool(ns >= 2.0 and net > 0 and trades >= min_tr)
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
        "works": works,
        "from_parent_cache": False,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s trades=%d WR=%.1f%% net=$%+.0f stress=$%.0f N/S=%.2f works=%s"
        % (slug, trades, wr * 100, net, stress, ns, works),
    )
    return metrics


def classify(results: List[dict]) -> Tuple[str, List[str], List[str]]:
    hp = [r for r in results if str(r.get("slug", "")).startswith("hp_")]
    survivors = [str(r["slug"]) for r in hp if r.get("works")]
    rejects = [str(r["slug"]) for r in hp if not r.get("works")]
    if survivors:
        best = max(hp, key=lambda r: float(r.get("net_over_stress") or 0.0))
        stance = (
            "SURVIVE — %d/%d HP gates clear N/S≥2; best `%s` N/S %.2f"
            % (len(survivors), len(hp), best["slug"], float(best.get("net_over_stress") or 0))
        )
    elif any(float(r.get("net_usd") or 0) > 0 for r in hp):
        stance = "MARGINAL — HP gates green but none clear N/S≥2 with enough trades"
    else:
        stance = "REJECT — no HP gate survives broker-like replay"
    return stance, survivors, rejects


def write_summary(hub: Path, results: List[dict], stance: str, survivors: List[str]) -> Path:
    lines = [
        "# NQ opening-candle close-limit — top HP broker gates",
        "",
        "Engine + PaperBroker + `first_hour_follow` on RTH 5m.",
        "Contract: 1h open candle → **limit @ close** → SL=open → TP=3R.",
        "Realism: slip 1 tick, spread, fee $1.50/unit, NQ $20/pt.",
        "",
        "Parent mill: [`../hp/SUMMARY.md`](../hp/SUMMARY.md).",
        "",
        "| Book | Trades | WR | Net | Stress | N/S | works |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            "| {label} | {trades} | {wr:.1f}% | ${net:,.0f} | ${stress:,.0f} | **{ns:.2f}** | {w} |".format(
                label=r["label"],
                trades=int(r["trades"]),
                wr=100.0 * float(r["win_rate"]),
                net=float(r["net_usd"]),
                stress=float(r["intrabar_stress_dd_usd"]),
                ns=float(r["net_over_stress"]),
                w="yes" if r.get("works") else "no",
            )
        )
    lines += [
        "",
        "## Stance",
        "",
        "- %s" % stance,
    ]
    if survivors:
        lines.append("- Survivors: " + ", ".join("`%s`" % s for s in survivors))
    lines += [
        "",
        "## Notes",
        "",
        "- `hp_strong_body` uses native plugin body gate.",
        "- PO / RSI gates use mill campaign session allowlists (filled-day set).",
        "- `hp_fh_p90` allowlist is from first-hour candles (all p90 sessions).",
        "- Survive = N/S ≥ 2, net > 0, trades ≥ 80 (HP) / 200 (baseline).",
        "",
        "Hub: `%s`" % hub,
        "",
    ]
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, results: List[dict], stance: str, survivors: List[str]) -> Path:
    lines = [
        "NQ opening-candle close-limit HP broker gates complete",
        "Hub: %s" % hub,
        "",
        "Stance: %s" % stance,
    ]
    if survivors:
        lines.append("Survivors: %s" % ", ".join(survivors))
    lines.append("")
    for r in results:
        lines.append(
            "%s: trades=%d WR=%.1f%% net=$%+.0f N/S=%.2f works=%s"
            % (
                r["slug"],
                int(r["trades"]),
                100 * float(r["win_rate"]),
                float(r["net_usd"]),
                float(r["net_over_stress"]),
                r.get("works"),
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
        allow = build_allowlists(hub)
        books = books_spec(allow)
        if args.only:
            want = set(args.only)
            books = [b for b in books if b[0] in want]
            if not books:
                raise SystemExit("no books matched --only %s" % sorted(want))

        df = load_rth_5m(progress=True)
        if args.smoke:
            cut = pd.Timestamp(df["ts"].max()).tz_convert(NY) - pd.Timedelta(days=400)
            df = df[df["ts"] >= cut].reset_index(drop=True)
            _progress(hub, "SMOKE bars=%d" % len(df))

        results: List[dict] = []
        for slug, label, cfg in books:
            results.append(
                run_book(hub=hub, slug=slug, label=label, cfg=cfg, df=df, force=args.force)
            )

        stance, survivors, rejects = classify(results)
        write_summary(hub, results, stance, survivors)
        email_path = write_email(hub, results, stance, survivors)
        write_run_manifest(
            hub,
            data_inputs=[NQ_5M_CSV, str(HP_HUB / "campaigns.csv")],
            strategy_config={
                "books": [b[0] for b in books_spec(allow)],
                "stance": stance,
                "survivors": survivors,
                "rejects": rejects,
            },
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
                    "survivors": survivors,
                    "rejects": rejects,
                    "results": [
                        {
                            "slug": r["slug"],
                            "trades": r["trades"],
                            "net_usd": r["net_usd"],
                            "net_over_stress": r["net_over_stress"],
                            "win_rate": r["win_rate"],
                            "works": r.get("works"),
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
                subject="potions: NQ open1h close-limit HP broker gates complete",
                body=email_path.read_text(encoding="utf-8"),
            )
        _progress(hub, "COMPLETE stance=%s survivors=%s" % (stance, survivors))
        return 0
    except Exception as exc:
        tb = traceback.format_exc()
        _progress(hub, "FAIL %s\n%s" % (exc, tb))
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": False, "error": str(exc), "traceback": tb}, indent=2) + "\n",
            encoding="utf-8",
        )
        fail_body = "NQ open1h close-limit HP broker gates FAILED\nHub: %s\n\n%s\n" % (
            hub,
            tb[-2500:],
        )
        (hub / "EMAIL.txt").write_text(fail_body, encoding="utf-8")
        if args.email:
            try:
                send_email(
                    subject="potions: NQ open1h close-limit HP broker gates FAILED",
                    body=fail_body,
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
