"""USDJPY live OANDA demos: practice ticks → demo path vs StrategyPlugin parity.

Covers the other two UP practice books (besides NAS100 clean-break):

1. ``usdjpy_monday_or_ungated_oanda`` — ticks → 1m → 15m → ``monday_or_breakout``
2. ``usdjpy_asia_range_london_oanda`` — ticks → 1m → ``v2b_scaleout`` (+ Asia OR inject)

Uses **only** stored OANDA practice ``fx_ticks`` from each demo — not research OHLC.

Primary verdict per book: fill keys ``(ts_minute, side, qty, reason)`` must MATCH.

Usage:
  PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \\
    python -m live.usdjpy_live_demo_plugin_tick_parity --email
  python -m live.usdjpy_live_demo_plugin_tick_parity --email --smoke
  python -m live.usdjpy_live_demo_plugin_tick_parity --email --book monday
  python -m live.usdjpy_live_demo_plugin_tick_parity --email --book asia
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pytz

from .asia_range_shadow import load_shadow_book
from .broker import DEFAULT_TICK_SIZE
from .demo.usdjpy_asia_range_london_common import (
    ASIA_END,
    ASIA_START,
    LONDON_OPEN,
    MIN_ASIA_BARS,
    OANDA_SPEC,
    default_output_root as asia_default_root,
    shadow_path,
    strategy_config_payload as asia_strategy_config,
)
from .demo.usdjpy_monday_or_ungated_oanda import (
    PHASE2_TAG,
    STRATEGY_ID as MONDAY_STRATEGY_ID,
    strategy_config_payload as monday_strategy_config,
)
from .engine import Engine
from .models import Bar, StrategyInstance, as_row, utc_now_iso
from .notifications import NullNotificationSink
from .oanda import FifteenMinuteBarAggregator, QuoteOneMinuteBarBuilder, parse_oanda_ts
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "usdjpy_live_demo_plugin_tick_parity_v1"
NY = pytz.timezone("America/New_York")

MONDAY_TICK_DIR = (
    REPO / "live" / "demo" / "usdjpy_monday_or_ungated_oanda" / "state" / "events" / "fx_ticks"
)
ASIA_TICK_DIR = (
    REPO / "live" / "demo" / "usdjpy_asia_range_london_oanda" / "state" / "events" / "fx_ticks"
)

INSTRUMENT = "USDJPY"
TICK = 0.001
FillKey = Tuple[str, str, str, str]


def _fill_key(row: Dict[str, str]) -> FillKey:
    ts = (row.get("ts") or "")[:16]
    side = (row.get("side") or "").lower()
    qty = str(int(float(row.get("quantity") or row.get("qty") or 0)))
    reason = (row.get("reason") or "").lower()
    return (ts, side, qty, reason)


def _load_fills(path: Path) -> List[Dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    return list(csv.DictReader(path.open(encoding="utf-8")))


def _write_csv(path: Path, rows: Sequence[Dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for row in rows:
            w.writerow(row)


def list_tick_days(tick_dir: Path) -> List[Path]:
    return sorted(tick_dir.glob("*.jsonl"))


def iter_ticks(paths: Sequence[Path]) -> Iterable[Dict[str, Any]]:
    for path in paths:
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def compare_fills(a: Sequence[Dict[str, str]], b: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    # Sort so same-bar multi-fills (e.g. dd30+dd50) are order-insensitive.
    ka = sorted(_fill_key(r) for r in a)
    kb = sorted(_fill_key(r) for r in b)
    exact = ka == kb
    first = next(((x, y) for x, y in zip(ka, kb) if x != y), None)
    return {
        "match": exact,
        "a_n": len(ka),
        "b_n": len(kb),
        "a_only": [list(x) for x in sorted(set(ka) - set(kb))[:50]],
        "b_only": [list(x) for x in sorted(set(kb) - set(ka))[:50]],
        "first_diff_a": list(first[0]) if first else None,
        "first_diff_b": list(first[1]) if first else None,
        "sequence_match": [_fill_key(r) for r in a] == [_fill_key(r) for r in b],
    }


def realized_pnl(state_root: Path) -> float:
    path = state_root / "positions.csv"
    if not path.exists() or path.stat().st_size == 0:
        return 0.0
    total = 0.0
    for row in csv.DictReader(path.open(encoding="utf-8")):
        try:
            total += float(row.get("realized_pnl") or 0.0)
        except ValueError:
            continue
    return total


def make_engine(
    state_root: Path,
    *,
    strategy_id: str,
    strategy_type: str,
    timeframes: str,
    max_contracts: int,
    cfg: Dict[str, Any],
) -> Engine:
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    DEFAULT_TICK_SIZE[INSTRUMENT] = TICK
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type=strategy_type,
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes=timeframes,
        max_contracts=max_contracts,
        max_open_orders=32,
        config_json=json.dumps(cfg, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    return Engine(
        store=store,
        persist_bars=True,
        persist_health=False,
        slippage_ticks=0.0,
        tick_size={INSTRUMENT: TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )


def flush_engine(engine: Engine) -> None:
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    engine.store.flush_tables()


def _monday_cfg() -> Dict[str, Any]:
    cfg = dict(monday_strategy_config())
    cfg["paper_only"] = True
    cfg["oanda_routing"] = False
    cfg["fill_price"] = "mid"
    return cfg


def _asia_cfg(live_root: Path) -> Dict[str, Any]:
    cfg = dict(asia_strategy_config(OANDA_SPEC, live_root))
    cfg["paper_only"] = True
    cfg["oanda_routing"] = False
    cfg["fill_price"] = "mid"
    cfg["shadow_campaigns_path"] = str(shadow_path(live_root))
    return cfg


def run_monday(tick_paths: Sequence[Path], hub: Path) -> Dict[str, Any]:
    cfg = _monday_cfg()
    max_qty = max(
        int(cfg.get("entry_qty") or 1),
        int(cfg.get("dd30_qty") or 1),
        int(cfg.get("dd50_qty") or 1),
        int(cfg.get("shifted_entry_qty") or 1),
    )
    demo_root = hub / "monday" / "demo_tick"
    plugin_root = hub / "monday" / "plugin_same_bars"
    demo_id = "usdjpy_monday_or_demo_tick"
    plugin_id = "usdjpy_monday_or_plugin_same_bars"

    engine = make_engine(
        demo_root,
        strategy_id=demo_id,
        strategy_type="monday_or_breakout",
        timeframes="15m",
        max_contracts=max_qty,
        cfg=cfg,
    )
    builder_1m = QuoteOneMinuteBarBuilder(INSTRUMENT, source="oanda_monday_or_tick_replay")
    agg_15m = FifteenMinuteBarAggregator(INSTRUMENT, source="oanda_monday_or_15m_replay")
    bars_15m: List[Bar] = []
    bars_1m_n = 0
    ticks = 0

    def handle_1m(bar_1m: Bar) -> None:
        nonlocal bars_1m_n
        bars_1m_n += 1
        for bar_15 in agg_15m.on_bar(bar_1m):
            bars_15m.append(bar_15)
            engine.process_bar(bar_15)

    for raw in iter_ticks(tick_paths):
        bid = float(raw.get("bid") or 0.0)
        ask = float(raw.get("ask") or 0.0)
        mid = raw.get("mid")
        mid_px = float(mid) if mid is not None else (bid + ask) / 2.0
        ts = str(raw.get("event_ts") or raw.get("ts") or "")
        qty = float(raw.get("quantity") or 0.0)
        if bid <= 0 or ask <= 0 or not ts:
            continue
        ticks += 1
        for bar_1m in builder_1m.on_quote(bid=bid, ask=ask, mid=mid_px, quantity=qty, ts=ts):
            handle_1m(bar_1m)
    for bar_1m in builder_1m.flush():
        handle_1m(bar_1m)
    for bar_15 in agg_15m.flush():
        bars_15m.append(bar_15)
        engine.process_bar(bar_15)
    flush_engine(engine)

    plugin = make_engine(
        plugin_root,
        strategy_id=plugin_id,
        strategy_type="monday_or_breakout",
        timeframes="15m",
        max_contracts=max_qty,
        cfg=cfg,
    )
    for bar in bars_15m:
        plugin.process_bar(bar)
    flush_engine(plugin)

    demo_fills = _load_fills(demo_root / "fills.csv")
    plugin_fills = _load_fills(plugin_root / "fills.csv")
    cmp = compare_fills(demo_fills, plugin_fills)
    _write_csv(hub / "monday" / "demo_fills.csv", demo_fills)
    _write_csv(hub / "monday" / "plugin_fills.csv", plugin_fills)
    (hub / "monday" / "demo_vs_plugin.json").write_text(json.dumps(cmp, indent=2) + "\n", encoding="utf-8")

    return {
        "book": "monday_or",
        "tick_dir": str(MONDAY_TICK_DIR),
        "days": [p.stem for p in tick_paths],
        "demo": {
            "ticks": ticks,
            "bars_1m": bars_1m_n,
            "bars_signal": len(bars_15m),
            "fills": len(demo_fills),
            "realized_pnl": realized_pnl(demo_root),
            "first_bar": bars_15m[0].ts if bars_15m else "",
            "last_bar": bars_15m[-1].ts if bars_15m else "",
            "phase2_tag": PHASE2_TAG,
            "strategy_id": MONDAY_STRATEGY_ID,
        },
        "plugin": {
            "bars_signal": len(bars_15m),
            "fills": len(plugin_fills),
            "realized_pnl": realized_pnl(plugin_root),
        },
        "demo_vs_plugin": cmp,
        "verdict": "MATCH" if cmp.get("match") else "MISMATCH",
    }


class AsiaOrInjector:
    """Mirrors live demo Asia OR accumulation + London inject into plugin config."""

    def __init__(self, engine: Engine, strategy_id: str, live_root: Path):
        self.engine = engine
        self.strategy_id = strategy_id
        self.live_root = live_root
        self._asia_session: Optional[date] = None
        self._asia_hi: Optional[float] = None
        self._asia_lo: Optional[float] = None
        self._asia_bars = 0
        self._injected_session: Optional[str] = None
        self.injections = 0

    def _london_session_for_asia_ts(self, wall: datetime) -> date:
        if wall.timetz().replace(tzinfo=None) >= ASIA_START:
            return wall.date() + timedelta(days=1)
        return wall.date()

    def _in_asia_window(self, wall: datetime) -> bool:
        t = wall.timetz().replace(tzinfo=None)
        return t >= ASIA_START or t < ASIA_END

    def on_1m(self, bar: Bar) -> None:
        wall = parse_oanda_ts(bar.ts).astimezone(NY)
        sess = self._london_session_for_asia_ts(wall)
        if self._asia_session != sess:
            self._asia_session = sess
            self._asia_hi = None
            self._asia_lo = None
            self._asia_bars = 0
            self._injected_session = None
        if self._in_asia_window(wall):
            self._asia_bars += 1
            hi = float(bar.high)
            lo = float(bar.low)
            self._asia_hi = hi if self._asia_hi is None else max(self._asia_hi, hi)
            self._asia_lo = lo if self._asia_lo is None else min(self._asia_lo, lo)
        self._maybe_inject(wall)

    def _maybe_inject(self, wall: datetime) -> None:
        if self._asia_session is None or self._asia_hi is None or self._asia_lo is None:
            return
        if self._asia_hi <= self._asia_lo or self._asia_bars < MIN_ASIA_BARS:
            return
        sess = self._asia_session.isoformat()
        if self._injected_session == sess:
            return
        if wall.date() != self._asia_session:
            return
        if wall.timetz().replace(tzinfo=None) < LONDON_OPEN:
            return

        rows = self.engine.store.read_table("strategy_instances")
        if not rows:
            return
        row = dict(rows[0])
        try:
            cfg = json.loads(row.get("config_json") or "{}")
        except json.JSONDecodeError:
            cfg = {}
        ranges = dict(cfg.get("session_or_ranges") or {})
        ranges[sess] = {
            "high": float(self._asia_hi),
            "low": float(self._asia_lo),
            "asia_bars": int(self._asia_bars),
            "asia_window": "19:00-03:00",
        }
        cfg["session_or_ranges"] = ranges
        cfg["shadow_campaigns_seed"] = load_shadow_book(shadow_path(self.live_root))
        row["config_json"] = json.dumps(cfg, sort_keys=True)
        self.engine.store.upsert_row("strategy_instances", "strategy_id", row)
        plugin = self.engine.manager.plugins.get(self.strategy_id)
        if plugin is not None:
            plugin.config["session_or_ranges"] = ranges
            plugin.config["shadow_campaigns_seed"] = cfg["shadow_campaigns_seed"]
            plugin.config["shadow_campaigns_path"] = str(shadow_path(self.live_root))
            st = dict(getattr(plugin, "state", None) or {})
            st["shadow_campaigns"] = list(cfg["shadow_campaigns_seed"])
            plugin.state = st
            if hasattr(plugin, "_commit_state"):
                try:
                    plugin._commit_state(st)
                except Exception:
                    pass
        self._injected_session = sess
        self.injections += 1


def run_asia(tick_paths: Sequence[Path], hub: Path) -> Dict[str, Any]:
    live_root = asia_default_root(OANDA_SPEC)
    cfg = _asia_cfg(live_root)
    max_qty = max(
        int(cfg.get("entry_qty") or 1),
        int(cfg.get("tp1_qty") or 1),
        int(cfg.get("tp2_qty") or 1),
        8,
    )
    demo_id = "usdjpy_asia_range_demo_tick"
    plugin_id = "usdjpy_asia_range_plugin_same_bars"
    demo_root = hub / "asia" / "demo_tick"
    plugin_root = hub / "asia" / "plugin_same_bars"

    demo = make_engine(
        demo_root,
        strategy_id=demo_id,
        strategy_type="v2b_scaleout",
        timeframes="1m",
        max_contracts=max_qty,
        cfg=cfg,
    )
    builder_1m = QuoteOneMinuteBarBuilder(INSTRUMENT, source="oanda_asia_range_tick_replay")
    inject_demo = AsiaOrInjector(demo, demo_id, live_root)
    bars_1m: List[Bar] = []
    ticks = 0

    for raw in iter_ticks(tick_paths):
        bid = float(raw.get("bid") or 0.0)
        ask = float(raw.get("ask") or 0.0)
        mid = raw.get("mid")
        mid_px = float(mid) if mid is not None else (bid + ask) / 2.0
        ts = str(raw.get("event_ts") or raw.get("ts") or "")
        qty = float(raw.get("quantity") or 0.0)
        if bid <= 0 or ask <= 0 or not ts:
            continue
        ticks += 1
        for bar_1m in builder_1m.on_quote(bid=bid, ask=ask, mid=mid_px, quantity=qty, ts=ts):
            bars_1m.append(bar_1m)
            inject_demo.on_1m(bar_1m)
            demo.process_bar(bar_1m)
    for bar_1m in builder_1m.flush():
        bars_1m.append(bar_1m)
        inject_demo.on_1m(bar_1m)
        demo.process_bar(bar_1m)
    flush_engine(demo)

    plugin = make_engine(
        plugin_root,
        strategy_id=plugin_id,
        strategy_type="v2b_scaleout",
        timeframes="1m",
        max_contracts=max_qty,
        cfg=cfg,
    )
    inject_plugin = AsiaOrInjector(plugin, plugin_id, live_root)
    for bar in bars_1m:
        inject_plugin.on_1m(bar)
        plugin.process_bar(bar)
    flush_engine(plugin)

    demo_fills = _load_fills(demo_root / "fills.csv")
    plugin_fills = _load_fills(plugin_root / "fills.csv")
    cmp = compare_fills(demo_fills, plugin_fills)
    _write_csv(hub / "asia" / "demo_fills.csv", demo_fills)
    _write_csv(hub / "asia" / "plugin_fills.csv", plugin_fills)
    (hub / "asia" / "demo_vs_plugin.json").write_text(json.dumps(cmp, indent=2) + "\n", encoding="utf-8")

    return {
        "book": "asia_range",
        "tick_dir": str(ASIA_TICK_DIR),
        "days": [p.stem for p in tick_paths],
        "demo": {
            "ticks": ticks,
            "bars_1m": len(bars_1m),
            "or_injections": inject_demo.injections,
            "fills": len(demo_fills),
            "realized_pnl": realized_pnl(demo_root),
            "first_bar": bars_1m[0].ts if bars_1m else "",
            "last_bar": bars_1m[-1].ts if bars_1m else "",
            "book_code": OANDA_SPEC.book,
            "strategy_id": OANDA_SPEC.strategy_id,
        },
        "plugin": {
            "bars_1m": len(bars_1m),
            "or_injections": inject_plugin.injections,
            "fills": len(plugin_fills),
            "realized_pnl": realized_pnl(plugin_root),
        },
        "demo_vs_plugin": cmp,
        "verdict": "MATCH" if cmp.get("match") else "MISMATCH",
    }


def write_summary(hub: Path, results: Sequence[Dict[str, Any]]) -> str:
    all_match = all(r.get("verdict") == "MATCH" for r in results)
    verdict = "MATCH" if all_match else "MISMATCH"
    lines = [
        "# USDJPY live OANDA demos: practice ticks → demo vs StrategyPlugin",
        "",
        "STATUS: **%s**" % verdict,
        "",
        "Data: OANDA practice ``fx_ticks`` only (not research OHLC).",
        "",
    ]
    for r in results:
        lines.extend(
            [
                "## %s — %s" % (r["book"], r["verdict"]),
                "",
                "- Tick dir: `%s`" % r["tick_dir"],
                "- Days (%d): %s" % (len(r["days"]), ", ".join(r["days"])),
                "- Demo: `%s`" % json.dumps(r["demo"], sort_keys=True),
                "- Plugin: `%s`" % json.dumps(r["plugin"], sort_keys=True),
                "- Compare: `%s`" % json.dumps(r["demo_vs_plugin"], sort_keys=True),
                "",
            ]
        )
    lines.extend(
        [
            "## Stance",
            "",
            "- MATCH → live/demo aggregation+Engine wiring equals non-live StrategyPlugin on identical OANDA-derived bars.",
            "- Practice wiring check only; not a funded promote gate.",
            "",
        ]
    )
    text = "\n".join(lines) + "\n"
    (hub / "SUMMARY.md").write_text(text, encoding="utf-8")
    return verdict


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--book", choices=("both", "monday", "asia"), default="both")
    ap.add_argument("--max-days", type=int, default=0, help="Use last N tick days (0=all)")
    ap.add_argument("--smoke", action="store_true", help="Last 2 tick days only")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    if HUB.exists():
        shutil.rmtree(HUB)
    HUB.mkdir(parents=True, exist_ok=True)

    rid = begin_run(
        run_class="audit",
        variant_slug="usdjpy_live_demo_plugin_tick_parity",
        instrument=INSTRUMENT,
        hub_path=str(HUB.relative_to(REPO)),
        meta={"book": args.book, "smoke": bool(args.smoke)},
    )
    try:
        results: List[Dict[str, Any]] = []

        def select_days(tick_dir: Path) -> List[Path]:
            days = list_tick_days(tick_dir)
            if not days:
                raise FileNotFoundError("No OANDA fx_ticks in %s" % tick_dir)
            if args.smoke:
                return days[-2:]
            if int(args.max_days or 0) > 0:
                return days[-int(args.max_days) :]
            return days

        if args.book in ("both", "monday"):
            print("running monday_or …", flush=True)
            results.append(run_monday(select_days(MONDAY_TICK_DIR), HUB))
            print(
                "monday_or %s fills=%s" % (results[-1]["verdict"], results[-1]["demo"]["fills"]),
                flush=True,
            )
        if args.book in ("both", "asia"):
            print("running asia_range …", flush=True)
            results.append(run_asia(select_days(ASIA_TICK_DIR), HUB))
            print(
                "asia_range %s fills=%s" % (results[-1]["verdict"], results[-1]["demo"]["fills"]),
                flush=True,
            )

        verdict = write_summary(HUB, results)
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps({"completed_at": utc_now_iso(), "verdict": verdict, "results": results}, indent=2)
            + "\n",
            encoding="utf-8",
        )

        email_lines = [
            "potions: USDJPY live OANDA demo↔plugin tick parity — %s" % verdict,
            "",
            "Hub: %s" % HUB,
            "Data: OANDA practice fx_ticks only (not research OHLC).",
            "",
        ]
        for r in results:
            email_lines.extend(
                [
                    "%s: %s" % (r["book"], r["verdict"]),
                    "  days=%d demo_fills=%s plugin_fills=%s pnl≈%.2f"
                    % (
                        len(r["days"]),
                        r["demo"].get("fills"),
                        r["plugin"].get("fills"),
                        float(r["demo"].get("realized_pnl") or 0.0),
                    ),
                    "  ticks=%s match=%s" % (r["demo"].get("ticks"), r["demo_vs_plugin"].get("match")),
                    "",
                ]
            )
        email_lines.append("Stance: practice wiring check only; not a promote gate.")
        email_body = "\n".join(email_lines)
        (HUB / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")

        net = sum(float(r["demo"].get("realized_pnl") or 0.0) for r in results)
        replay_starts = [str(r["demo"].get("first_bar") or "") for r in results if r["demo"].get("first_bar")]
        replay_ends = [str(r["demo"].get("last_bar") or "") for r in results if r["demo"].get("last_bar")]
        complete_run(
            rid,
            net_usd=net,
            trades=sum(int(r["demo"].get("fills") or 0) for r in results),
            replay_start=min(replay_starts) if replay_starts else "",
            replay_end=max(replay_ends) if replay_ends else "",
            notes="OANDA-tick demo↔plugin parity; research OHLC not used",
            meta={
                "verdict": verdict,
                "books": [r["book"] for r in results],
                "per_book": [
                    {
                        "book": r["book"],
                        "verdict": r.get("verdict"),
                        "fills": (r.get("demo") or {}).get("fills"),
                        "realized_pnl": (r.get("demo") or {}).get("realized_pnl"),
                        "match": (r.get("demo_vs_plugin") or {}).get("match"),
                    }
                    for r in results
                ],
                "skill": "potions-oanda-tick-demo-plugin-parity",
            },
        )
        if args.email:
            from .notify_email import send_email

            send_email(
                subject="potions: USDJPY live OANDA demo↔plugin tick parity — %s" % verdict,
                body=email_body,
            )
            print("email sent")

        print("VERDICT=%s hub=%s" % (verdict, HUB))
        print(json.dumps({"verdict": verdict, "results": results}, indent=2))
        return 0 if verdict == "MATCH" else 1
    except Exception as exc:
        fail_run(rid, error=str(exc))
        (HUB / "ERROR.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if args.email:
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: USDJPY live OANDA demo↔plugin tick parity FAILED",
                    body="Hub: %s\n\n%s" % (HUB, traceback.format_exc()[-4000:]),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
