"""NAS100 clean-break: OANDA practice ticks → demo path vs StrategyPlugin parity.

Uses **only** stored OANDA practice stream ticks (``rth_ticks`` from NAS100
OANDA demos) — not ``fx/nas100_1m.csv`` or other research OHLC.

Path A (live/demo wiring): ticks → ``QuoteOneMinuteBarBuilder`` → left-label 5m
→ Engine+PaperBroker with frozen ``trail06_m4_e2_out_be`` config.

Path B (non-live plugin): the **same** completed 5m bars → fresh
Engine+PaperBroker + same StrategyPlugin config.

Primary verdict: fill keys ``(ts_minute, side, qty, reason)`` must MATCH.

Usage:
  PYTHONPATH=/home/tester/hsm:/home/tester/hsm/potions/v20-python/src \\
    python -m live.nas100_clean_break_demo_plugin_tick_parity --email
  python -m live.nas100_clean_break_demo_plugin_tick_parity --email --smoke
  python -m live.nas100_clean_break_demo_plugin_tick_parity --email --max-days 5
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from .broker import DEFAULT_TICK_SIZE
from .demo.nas100_v2b_clean_break_trail_oanda import (
    INSTRUMENT,
    LeftLabelFiveMinuteBarAggregator,
    MAX_QTY,
    STRATEGY_TYPE,
    TICK,
    VARIANT,
    strategy_config_payload,
)
from .engine import Engine
from .models import Bar, StrategyInstance, as_row, utc_now_iso
from .notifications import NullNotificationSink
from .oanda import QuoteOneMinuteBarBuilder
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "nas100_clean_break_demo_plugin_tick_parity_v1"

# Prefer the large NAS100 OANDA ungated practice tick archive (OANDA stream picks).
DEFAULT_TICK_DIR = (
    REPO / "live" / "demo" / "nas100_v2b_ungated_oanda" / "state" / "events" / "rth_ticks"
)
# Fallback / also-ok: this book's own live stream captures.
OWN_TICK_DIR = (
    REPO
    / "live"
    / "demo"
    / "nas100_v2b_clean_break_trail06_m4_e2_out_be_oanda"
    / "state"
    / "events"
    / "rth_ticks"
)

FillKey = Tuple[str, str, str, str]


def _cfg() -> Dict[str, Any]:
    cfg = strategy_config_payload()
    cfg["paper_only"] = True
    cfg["oanda_routing"] = False
    return cfg


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


def make_engine(state_root: Path, *, strategy_id: str, cfg: Dict[str, Any]) -> Engine:
    if state_root.exists():
        shutil.rmtree(state_root)
    state_root.mkdir(parents=True, exist_ok=True)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    DEFAULT_TICK_SIZE[INSTRUMENT] = TICK
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type=STRATEGY_TYPE,
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="5m",
        max_contracts=MAX_QTY,
        max_open_orders=32,
        config_json=json.dumps(cfg, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    return Engine(
        store=store,
        persist_bars=True,
        persist_health=False,
        slippage_ticks=0.0,
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        tick_size={INSTRUMENT: TICK},
    )


def flush_engine(engine: Engine) -> None:
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    engine.store.flush_tables()


def run_demo_tick_path(
    tick_paths: Sequence[Path],
    *,
    state_root: Path,
) -> Tuple[List[Bar], Dict[str, Any]]:
    """Live/demo path: OANDA ticks → 1m quote builder → left-label 5m → Engine."""
    cfg = _cfg()
    engine = make_engine(state_root, strategy_id="nas100_clean_break_demo_tick", cfg=cfg)
    builder_1m = QuoteOneMinuteBarBuilder(INSTRUMENT, source="oanda_practice_rth_tick_replay")
    agg_5m = LeftLabelFiveMinuteBarAggregator(INSTRUMENT, source="oanda_1m_aggregate_left5m_replay")
    bars_5m: List[Bar] = []
    bars_1m_n = 0
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
            bars_1m_n += 1
            engine.store.append_bar(bar_1m)
            for bar_5 in agg_5m.on_bar(bar_1m):
                bars_5m.append(bar_5)
                engine.process_bar(bar_5)
    for bar_1m in builder_1m.flush():
        bars_1m_n += 1
        engine.store.append_bar(bar_1m)
        for bar_5 in agg_5m.on_bar(bar_1m):
            bars_5m.append(bar_5)
            engine.process_bar(bar_5)
    for bar_5 in agg_5m.flush():
        bars_5m.append(bar_5)
        engine.process_bar(bar_5)
    flush_engine(engine)
    meta = {
        "ticks": ticks,
        "bars_1m": bars_1m_n,
        "bars_5m": len(bars_5m),
        "fills": len(_load_fills(state_root / "fills.csv")),
        "first_5m": bars_5m[0].ts if bars_5m else "",
        "last_5m": bars_5m[-1].ts if bars_5m else "",
    }
    return bars_5m, meta


def run_plugin_on_bars(
    bars_5m: Sequence[Bar],
    *,
    state_root: Path,
    strategy_id: str,
) -> Dict[str, Any]:
    cfg = _cfg()
    engine = make_engine(state_root, strategy_id=strategy_id, cfg=cfg)
    for bar in bars_5m:
        engine.store.append_bar(bar)
        engine.process_bar(bar)
    flush_engine(engine)
    fills = _load_fills(state_root / "fills.csv")
    return {
        "bars_5m": len(bars_5m),
        "fills": len(fills),
        "first_5m": bars_5m[0].ts if bars_5m else "",
        "last_5m": bars_5m[-1].ts if bars_5m else "",
    }


def compare_fills(a: Sequence[Dict[str, str]], b: Sequence[Dict[str, str]]) -> Dict[str, Any]:
    ka = [_fill_key(r) for r in a]
    kb = [_fill_key(r) for r in b]
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
    }


def write_report(
    *,
    hub: Path,
    tick_dir: Path,
    tick_paths: Sequence[Path],
    demo_meta: Dict[str, Any],
    plugin_meta: Dict[str, Any],
    demo_vs_plugin: Dict[str, Any],
) -> str:
    verdict = "MATCH" if demo_vs_plugin.get("match") else "MISMATCH"
    lines = [
        "# NAS100 clean-break: OANDA practice ticks → demo vs StrategyPlugin",
        "",
        "STATUS: **%s**" % verdict,
        "",
        "## Data (OANDA only)",
        "",
        "- Source: `%s`" % tick_dir,
        "- Kind: stored OANDA practice pricing-stream ticks (`rth_ticks/*.jsonl`).",
        "- **Not used:** `fx/nas100_1m.csv` / research OHLC.",
        "- Days (%d): %s" % (len(tick_paths), ", ".join(p.stem for p in tick_paths)),
        "- Frozen variant: `%s`" % VARIANT,
        "",
        "## Demo path (live/demo wiring)",
        "",
        "- ticks=%s bars_1m=%s bars_5m=%s fills=%s"
        % (
            demo_meta.get("ticks"),
            demo_meta.get("bars_1m"),
            demo_meta.get("bars_5m"),
            demo_meta.get("fills"),
        ),
        "- range: %s → %s" % (demo_meta.get("first_5m"), demo_meta.get("last_5m")),
        "",
        "## Plugin path (same 5m bars, fresh Engine)",
        "",
        "- bars_5m=%s fills=%s" % (plugin_meta.get("bars_5m"), plugin_meta.get("fills")),
        "",
        "## Compare",
        "",
        "```json",
        json.dumps(demo_vs_plugin, indent=2),
        "```",
        "",
        "## Stance",
        "",
        "- MATCH → live/demo aggregation+Engine wiring equals non-live StrategyPlugin on identical OANDA-derived bars.",
        "- MISMATCH → investigate demo aggregator / Engine wiring before trusting the OANDA daemon.",
        "- Practice wiring check only; not a funded promote gate.",
        "",
    ]
    text = "\n".join(lines) + "\n"
    (hub / "SUMMARY.md").write_text(text, encoding="utf-8")
    return verdict


def resolve_tick_dir(explicit: str) -> Path:
    if explicit:
        return Path(explicit)
    if DEFAULT_TICK_DIR.is_dir() and list_tick_days(DEFAULT_TICK_DIR):
        return DEFAULT_TICK_DIR
    if OWN_TICK_DIR.is_dir() and list_tick_days(OWN_TICK_DIR):
        return OWN_TICK_DIR
    raise FileNotFoundError(
        "No OANDA practice rth_ticks found under %s or %s" % (DEFAULT_TICK_DIR, OWN_TICK_DIR)
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--tick-dir",
        default="",
        help="OANDA rth_ticks dir (default: nas100_v2b_ungated_oanda practice archive)",
    )
    ap.add_argument("--max-days", type=int, default=0, help="Use last N tick days (0=all)")
    ap.add_argument("--smoke", action="store_true", help="Last 2 tick days only")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    tick_dir = resolve_tick_dir(args.tick_dir)
    days = list_tick_days(tick_dir)
    if not days:
        print("No OANDA tick days in %s" % tick_dir)
        return 2
    if args.smoke:
        days = days[-2:]
    elif int(args.max_days or 0) > 0:
        days = days[-int(args.max_days) :]

    if HUB.exists():
        shutil.rmtree(HUB)
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "INPUTS.json").write_text(
        json.dumps(
            {
                "tick_dir": str(tick_dir),
                "data_kind": "oanda_practice_rth_ticks",
                "research_ohlc_used": False,
                "days": [p.name for p in days],
                "variant": VARIANT,
                "started_at": utc_now_iso(),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    rid = begin_run(
        run_class="audit",
        variant_slug="nas100_clean_break_demo_plugin_tick_parity",
        instrument=INSTRUMENT,
        hub_path=str(HUB.relative_to(REPO)),
        parent_run_id="brl_21741b260a28",
        meta={"tick_days": len(days), "tick_dir": str(tick_dir), "smoke": bool(args.smoke)},
    )
    try:
        demo_root = HUB / "demo_tick"
        plugin_root = HUB / "plugin_same_bars"

        bars_5m, demo_meta = run_demo_tick_path(days, state_root=demo_root)
        plugin_meta = run_plugin_on_bars(
            bars_5m, state_root=plugin_root, strategy_id="nas100_clean_break_plugin_same_bars"
        )

        demo_fills = _load_fills(demo_root / "fills.csv")
        plugin_fills = _load_fills(plugin_root / "fills.csv")
        demo_vs_plugin = compare_fills(demo_fills, plugin_fills)
        _write_csv(HUB / "demo_fills.csv", demo_fills)
        _write_csv(HUB / "plugin_fills.csv", plugin_fills)
        (HUB / "demo_vs_plugin.json").write_text(json.dumps(demo_vs_plugin, indent=2) + "\n", encoding="utf-8")

        verdict = write_report(
            hub=HUB,
            tick_dir=tick_dir,
            tick_paths=days,
            demo_meta=demo_meta,
            plugin_meta=plugin_meta,
            demo_vs_plugin=demo_vs_plugin,
        )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "completed_at": utc_now_iso(),
                    "verdict": verdict,
                    "demo_meta": demo_meta,
                    "plugin_meta": plugin_meta,
                    "demo_vs_plugin": demo_vs_plugin,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        email_body = "\n".join(
            [
                "potions: NAS100 clean-break OANDA-tick demo↔plugin parity — %s" % verdict,
                "",
                "Hub: %s" % HUB,
                "Data: OANDA practice rth_ticks only (%s)" % tick_dir,
                "Days: %d (%s … %s)" % (len(days), days[0].stem, days[-1].stem),
                "Demo: ticks=%s bars_5m=%s fills=%s"
                % (demo_meta["ticks"], demo_meta["bars_5m"], demo_meta["fills"]),
                "Plugin same bars: fills=%s" % plugin_meta["fills"],
                "MATCH: %s" % demo_vs_plugin.get("match"),
                "",
                "Stance: practice wiring check only; not a promote gate.",
                "Research fx/nas100_1m NOT used.",
            ]
        )
        (HUB / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")

        complete_run(
            rid,
            trades=int(demo_meta.get("fills") or 0),
            meta={"verdict": verdict, "match": bool(demo_vs_plugin.get("match"))},
        )

        if args.email:
            from .notify_email import send_email

            send_email(
                subject="potions: NAS100 clean-break OANDA-tick demo↔plugin parity — %s" % verdict,
                body=email_body,
            )
            print("email sent")

        print("VERDICT=%s hub=%s" % (verdict, HUB))
        print(
            json.dumps(
                {"demo": demo_meta, "plugin": plugin_meta, "match": demo_vs_plugin.get("match")},
                indent=2,
            )
        )
        return 0 if demo_vs_plugin.get("match") else 1
    except Exception as exc:
        fail_run(rid, error=str(exc))
        (HUB / "ERROR.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if args.email:
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: NAS100 clean-break OANDA-tick demo↔plugin parity FAILED",
                    body="Hub: %s\n\n%s" % (HUB, traceback.format_exc()[-4000:]),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
