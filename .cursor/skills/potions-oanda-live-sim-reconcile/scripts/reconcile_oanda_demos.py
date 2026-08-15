#!/usr/bin/env python3
"""Reconcile live/demo *_oanda fills vs Engine+PaperBroker StrategyPlugin replay.

Replays each demo's stored bars with the live ``strategy_instances`` config_json
and compares ``reason=entry`` fills to the live tape. Optionally also replays
with the fresh spawn ``strategy_config_payload`` to surface config drift
(e.g. Monday OR missing skip_entry_months).

Usage:
  PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \\
    python3 .cursor/skills/potions-oanda-live-sim-reconcile/scripts/reconcile_oanda_demos.py
  ... --demo usdjpy_monday_or_ungated_oanda --also-fresh
"""

from __future__ import annotations

import argparse
import csv
import importlib
import json
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

REPO = Path(__file__).resolve().parents[4]
if str(REPO.parent) not in sys.path:
    sys.path.insert(0, str(REPO.parent))
if str(REPO / "v20-python" / "src") not in sys.path:
    sys.path.insert(0, str(REPO / "v20-python" / "src"))

from potions.live.broker import DEFAULT_TICK_SIZE  # noqa: E402
from potions.live.engine import Engine, bars_from_csv  # noqa: E402
from potions.live.models import Bar, StrategyInstance, as_row  # noqa: E402
from potions.live.notifications import NullNotificationSink  # noqa: E402
from potions.live.store import FlatFileStore  # noqa: E402
from potions.live.verification import QuietPaperVerificationProvider  # noqa: E402

DEMO_ROOT = REPO / "live" / "demo"
OUT_ROOT = REPO / "live" / "state" / "_oanda_live_sim_reconcile"

# How to load fresh spawn payload for config-drift checks.
# kind=direct: module.strategy_config_payload(**kwargs)
# kind=v2b_spec: common.strategy_config_payload(module.SPEC)
FRESH_PAYLOAD: Dict[str, Dict[str, Any]] = {
    "usdjpy_monday_or_ungated_oanda": {
        "kind": "direct",
        "module": "potions.live.demo.usdjpy_monday_or_ungated_oanda",
        "kwargs": {},
    },
    "eurusd_v2b_ungated_oanda": {
        "kind": "v2b_spec",
        "module": "potions.live.demo.eurusd_v2b_ungated_oanda",
    },
    "nas100_v2b_ungated_oanda": {
        "kind": "v2b_spec",
        "module": "potions.live.demo.nas100_v2b_ungated_oanda",
    },
    "spx500_v2b_ungated_oanda": {
        "kind": "v2b_spec",
        "module": "potions.live.demo.spx500_v2b_ungated_oanda",
    },
    "us30_v2b_ungated_oanda": {
        "kind": "v2b_spec",
        "module": "potions.live.demo.us30_v2b_ungated_oanda",
    },
    "nas100_hourly_st_pmc_sl50_tp150_3r_oanda": {
        "kind": "direct",
        "module": "potions.live.demo.nas100_hourly_st_pmc_common",
        "kwargs": {"oanda_routing": True, "book": "sl50_tp150_3r"},
    },
    "nas100_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda": {
        "kind": "direct",
        "module": "potions.live.demo.nas100_hourly_st_pmc_common",
        "kwargs": {"oanda_routing": True, "book": "sl50_tp150_runners_2r_10r"},
    },
    "us30_hourly_st_pmc_sl50_tp150_3r_oanda": {
        "kind": "direct",
        "module": "potions.live.demo.us30_hourly_st_pmc_common",
        "kwargs": {"oanda_routing": True, "book": "sl50_tp150_3r"},
    },
    "us30_hourly_st_pmc_sl50_tp150_runners_2r_10r_oanda": {
        "kind": "direct",
        "module": "potions.live.demo.us30_hourly_st_pmc_common",
        "kwargs": {"oanda_routing": True, "book": "sl50_tp150_runners_2r_10r"},
    },
}

ENTRY_REASONS = {"entry"}


def _parse_ts_minute(ts: str) -> Optional[int]:
    """Epoch minutes for fuzzy matching; tolerates Z / offset / space."""
    raw = (ts or "").strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    if " " in raw and "T" not in raw:
        raw = raw.replace(" ", "T", 1)
    # trim to minutes for fromisoformat safety
    try:
        from datetime import datetime

        if "." in raw:
            head, rest = raw.split(".", 1)
            frac = ""
            tz = ""
            for i, ch in enumerate(rest):
                if ch.isdigit():
                    frac += ch
                else:
                    tz = rest[i:]
                    break
            raw = "%s.%s%s" % (head, (frac + "000000")[:6], tz)
        dt = datetime.fromisoformat(raw)
        return int(dt.timestamp() // 60)
    except Exception:
        return None


def _entry_key(row: Dict[str, str]) -> Tuple[str, str, str]:
    ts = (row.get("ts") or "")[:16]  # YYYY-MM-DDTHH:MM
    side = (row.get("side") or "").lower()
    qty = str(int(float(row.get("quantity") or row.get("qty") or 0)))
    return (ts, side, qty)


def _load_entries(fills_path: Path) -> List[Dict[str, str]]:
    if not fills_path.exists():
        return []
    rows = list(csv.DictReader(fills_path.open(encoding="utf-8")))
    return [r for r in rows if (r.get("reason") or "").lower() in ENTRY_REASONS]


def _started_at_iso(demo_dir: Path) -> Optional[str]:
    meta_path = demo_dir / "RUN_META.json"
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return meta.get("started_at") or meta.get("spawned_at")


def _filter_entries_after(entries: Sequence[Dict[str, str]], started_at: Optional[str]) -> List[Dict[str, str]]:
    if not started_at:
        return list(entries)
    start_m = _parse_ts_minute(started_at)
    if start_m is None:
        return list(entries)
    out: List[Dict[str, str]] = []
    for r in entries:
        m = _parse_ts_minute(r.get("ts") or "")
        if m is None or m >= start_m:
            out.append(r)
    return out


def _load_instance(demo_dir: Path) -> Dict[str, str]:
    path = demo_dir / "state" / "strategy_instances.csv"
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    if not rows:
        raise FileNotFoundError("empty strategy_instances: %s" % path)
    return rows[0]


def _bars_for_demo(demo_dir: Path, instrument: str, timeframes: str) -> List[Bar]:
    bars_dir = demo_dir / "state" / "bars"
    tfs = [t.strip() for t in (timeframes or "").split(",") if t.strip()]
    if not tfs:
        tfs = ["1m"]
    loaded: List[Bar] = []
    for tf in tfs:
        candidates = [
            bars_dir / ("%s_%s.csv" % (instrument, tf)),
            bars_dir / ("%s_%s.csv" % (instrument.upper(), tf)),
        ]
        path = next((p for p in candidates if p.exists()), None)
        if path is None:
            # fallback: any *_{tf}.csv
            matches = sorted(bars_dir.glob("*_%s.csv" % tf))
            path = matches[0] if matches else None
        if path is None:
            continue
        loaded.extend(bars_from_csv(path, instrument=instrument, timeframe=tf, source=str(path)))
    loaded.sort(key=lambda b: (b.ts, {"1m": 0, "15m": 1, "1h": 2}.get(b.timeframe, 9)))
    return loaded


def _fresh_payload(demo_name: str) -> Optional[Dict[str, Any]]:
    spec = FRESH_PAYLOAD.get(demo_name)
    if not spec:
        return None
    mod_name = str(spec["module"])
    try:
        mod = importlib.import_module(mod_name)
    except Exception as exc:  # noqa: BLE001
        print("  warn: cannot import %s: %s" % (mod_name, exc))
        return None
    kind = str(spec.get("kind") or "direct")
    try:
        if kind == "v2b_spec":
            from potions.live.demo.oanda_v2b_ungated_common import (  # noqa: WPS433
                strategy_config_payload as v2b_payload,
            )

            return dict(v2b_payload(mod.SPEC))
        fn = getattr(mod, "strategy_config_payload", None)
        if fn is None:
            return None
        return dict(fn(**dict(spec.get("kwargs") or {})))
    except Exception as exc:  # noqa: BLE001
        print("  warn: strategy_config_payload failed for %s: %s" % (demo_name, exc))
        return None


def _config_drift(live_cfg: Dict[str, Any], fresh: Optional[Dict[str, Any]]) -> List[str]:
    if not fresh:
        return []
    # Keys that affect entries / risk overlays — missing on live is drift.
    material = {
        "skip_entry_months",
        "week_sitout_after_pts",
        "week_sitout_blocks_shifted",
        "skip_after_win_streak",
        "skip_after_win_n",
        "max_trades_per_week",
        "entry_qty",
        "dd30_qty",
        "dd50_qty",
        "shifted_entry_qty",
        "shifted_primary",
        "skip_both_opposed",
        "prior_opposite_only",
        "prior_aligned_only",
        "or_bars",
        "mode",
        "variant",
        "stop_pts",
        "target_pts",
        "runner_mode",
    }
    issues: List[str] = []
    for k in sorted(material):
        if k not in fresh:
            continue
        if k not in live_cfg:
            issues.append("missing %s (fresh=%r)" % (k, fresh[k]))
        elif live_cfg[k] != fresh[k]:
            issues.append("%s live=%r fresh=%r" % (k, live_cfg[k], fresh[k]))
    return issues


def _replay(
    *,
    label: str,
    demo_name: str,
    instrument: str,
    strategy_type: str,
    timeframes: str,
    max_contracts: int,
    cfg: Dict[str, Any],
    bars: Sequence[Bar],
) -> List[Dict[str, str]]:
    out = OUT_ROOT / demo_name / label
    if out.exists():
        shutil.rmtree(out)
    store = FlatFileStore(out, defer_table_writes=True)
    store.ensure()
    tick = float(cfg.get("tick_size") or DEFAULT_TICK_SIZE.get(instrument, 0.01))
    DEFAULT_TICK_SIZE[instrument] = tick
    instance = StrategyInstance(
        strategy_id="reconcile_%s_%s" % (demo_name, label),
        strategy_type=strategy_type,
        version="v1",
        instrument=instrument,
        broker_instrument=instrument,
        account_mode="paper",
        enabled=True,
        timeframes=timeframes or "1m",
        max_contracts=max(int(max_contracts or 1), 1),
        max_open_orders=64,
        config_json=json.dumps(cfg, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=0.0,
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        tick_size={instrument: tick},
    )
    for bar in bars:
        engine.process_bar(bar)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()
    return _load_entries(out / "fills.csv")


def _match_report(
    live: Sequence[Dict[str, str]],
    sim: Sequence[Dict[str, str]],
    *,
    fuzzy_minutes: int = 2,
) -> Dict[str, Any]:
    """Exact sequence match, else fuzzy side/qty within ±fuzzy_minutes."""
    lk = [_entry_key(r) for r in live]
    sk = [_entry_key(r) for r in sim]
    exact = lk == sk
    # fuzzy: greedy match each live entry to nearest unused sim entry
    unused = list(sim)
    unmatched_live: List[Tuple[str, str, str]] = []
    for lr in live:
        lm = _parse_ts_minute(lr.get("ts") or "")
        side = (lr.get("side") or "").lower()
        qty = str(int(float(lr.get("quantity") or 0)))
        best_i = None
        best_dt = None
        for i, sr in enumerate(unused):
            if (sr.get("side") or "").lower() != side:
                continue
            if str(int(float(sr.get("quantity") or 0))) != qty:
                continue
            sm = _parse_ts_minute(sr.get("ts") or "")
            if lm is None or sm is None:
                continue
            dt = abs(lm - sm)
            if dt <= fuzzy_minutes and (best_dt is None or dt < best_dt):
                best_dt = dt
                best_i = i
        if best_i is None:
            unmatched_live.append(_entry_key(lr))
        else:
            unused.pop(best_i)
    unmatched_sim = [_entry_key(r) for r in unused]
    fuzzy_ok = not unmatched_live and not unmatched_sim
    return {
        "match": exact,
        "fuzzy_match": fuzzy_ok,
        "live_n": len(lk),
        "sim_n": len(sk),
        "live_only": sorted(set(lk) - set(sk)),
        "sim_only": sorted(set(sk) - set(lk)),
        "fuzzy_unmatched_live": unmatched_live,
        "fuzzy_unmatched_sim": unmatched_sim,
        "first_diff": next(((a, b) for a, b in zip(lk, sk) if a != b), None)
        if lk and sk
        else (lk[:1], sk[:1]),
    }


def reconcile_one(demo_name: str, *, also_fresh: bool) -> Dict[str, Any]:
    demo_dir = DEMO_ROOT / demo_name
    inst = _load_instance(demo_dir)
    instrument = inst["instrument"]
    strategy_type = inst["strategy_type"]
    timeframes = inst.get("timeframes") or "1m"
    live_cfg = json.loads(inst.get("config_json") or "{}")
    fresh = _fresh_payload(demo_name)
    drift = _config_drift(live_cfg, fresh)

    bars = _bars_for_demo(demo_dir, instrument, timeframes)
    started = _started_at_iso(demo_dir)
    live_entries_all = _load_entries(demo_dir / "state" / "fills.csv")
    # Score against the current daemon epoch (RUN_META.started_at). Older fills remain
    # on disk for PnL forensics but must not fail reconcile after an intentional
    # config upgrade / restart.
    live_entries = _filter_entries_after(live_entries_all, started)

    result: Dict[str, Any] = {
        "demo": demo_name,
        "instrument": instrument,
        "strategy_type": strategy_type,
        "bars": len(bars),
        "started_at": started,
        "live_entries_all": len(live_entries_all),
        "drift": drift,
    }
    if not bars:
        result["status"] = "SKIP"
        result["reason"] = "no bars"
        return result

    max_c = int(float(inst.get("max_contracts") or 4))
    sim_live = _replay(
        label="live_cfg",
        demo_name=demo_name,
        instrument=instrument,
        strategy_type=strategy_type,
        timeframes=timeframes,
        max_contracts=max_c,
        cfg=live_cfg,
        bars=bars,
    )
    # Seeded history (ST+PMC 1h CSV) can fire entries before the daemon started —
    # only score sim entries at/after RUN_META.started_at.
    sim_live = _filter_entries_after(sim_live, started)
    live_vs = _match_report(live_entries, sim_live)
    result["live_cfg_replay"] = live_vs

    if also_fresh and fresh is not None:
        # Keep demo routing flags so fill_price semantics stay close; overlay fresh risk keys.
        merged = dict(live_cfg)
        merged.update(fresh)
        sim_fresh = _replay(
            label="fresh_cfg",
            demo_name=demo_name,
            instrument=instrument,
            strategy_type=strategy_type,
            timeframes=timeframes,
            max_contracts=max_c,
            cfg=merged,
            bars=bars,
        )
        sim_fresh = _filter_entries_after(sim_fresh, started)
        result["fresh_cfg_replay"] = _match_report(live_entries, sim_fresh)

    if live_vs.get("match"):
        result["status"] = "DRIFT" if drift else "MATCH"
    elif live_vs.get("fuzzy_match"):
        result["status"] = "FUZZY" if not drift else "FUZZY_DRIFT"
    else:
        result["status"] = "MISMATCH"
    return result


def list_oanda_demos() -> List[str]:
    names = []
    for d in sorted(DEMO_ROOT.iterdir()):
        if d.is_dir() and d.name.endswith("_oanda") and (d / "state" / "strategy_instances.csv").exists():
            names.append(d.name)
    return names


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="append", default=[], help="Demo run dirname (repeatable)")
    ap.add_argument("--also-fresh", action="store_true", help="Also replay fresh spawn payload")
    ap.add_argument("--json-out", type=Path, default=None)
    args = ap.parse_args()
    demos = args.demo or list_oanda_demos()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)

    rows: List[Dict[str, Any]] = []
    print(
        "%-52s %-12s %6s %6s %6s  %s"
        % ("demo", "status", "bars", "liveE", "simE", "notes")
    )
    for name in demos:
        try:
            r = reconcile_one(name, also_fresh=bool(args.also_fresh))
        except Exception as exc:  # noqa: BLE001
            r = {"demo": name, "status": "ERROR", "reason": str(exc)}
        rows.append(r)
        live_vs = r.get("live_cfg_replay") or {}
        notes = []
        if r.get("drift"):
            notes.append("drift:" + ";".join(r["drift"][:2]))
        if live_vs and not live_vs.get("match") and not live_vs.get("fuzzy_match"):
            notes.append(
                "unmatched live=%s sim=%s"
                % (live_vs.get("fuzzy_unmatched_live"), live_vs.get("fuzzy_unmatched_sim"))
            )
        elif live_vs and live_vs.get("fuzzy_match") and not live_vs.get("match"):
            notes.append("±2m side/qty ok")
        if r.get("reason"):
            notes.append(str(r["reason"]))
        fresh_vs = r.get("fresh_cfg_replay")
        if (
            fresh_vs is not None
            and not fresh_vs.get("match")
            and not fresh_vs.get("fuzzy_match")
            and (live_vs.get("match") or live_vs.get("fuzzy_match"))
        ):
            notes.append("fresh≠live tape (expected if DRIFT)")
        print(
            "%-52s %-12s %6s %6s %6s  %s"
            % (
                name,
                r.get("status"),
                r.get("bars", "-"),
                live_vs.get("live_n", "-"),
                live_vs.get("sim_n", "-"),
                " | ".join(notes) or "",
            )
        )

    out_json = args.json_out or (OUT_ROOT / "summary.json")
    out_json.write_text(json.dumps(rows, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("\nWrote %s" % out_json)
    bad = [r for r in rows if r.get("status") in ("MISMATCH", "ERROR")]
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
