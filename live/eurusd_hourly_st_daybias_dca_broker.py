"""Broker stress for EURUSD hourly ST day-bias DCA (Engine + PaperBroker).

Signals on completed 1h bars; resting orders fill on 1m tape (matches research path).
Half-lot units (PV $50k / fee $0.75), FX half-spread, 1-tick slippage.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

import pandas as pd

from .engine import Engine
from .eurusd_overnight_sweep import _fx_spread
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_retest_replay import read_bars_from_engine_bars
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
NY = "America/New_York"
HALF_LOT_POINT_VALUE = 50_000.0
FEE_PER_HALF_LOT = 0.75
TICK = 1e-5
OUT_DEFAULT = REPO / "live" / "state" / "eurusd_hourly_st_daybias_dca_broker"
BASELINE_NET = 23533.68
BASELINE_NET_STRESS = 1.49

# Research-positive cells, best first
DEFAULT_VARIANTS: List[Tuple[float, str]] = [
    (0.30, "week"),
    (0.30, "month"),
    (0.40, "week"),
    (0.40, "month"),
    (0.50, "week"),
]


def _slug(frac: float, period: str, tp_atr: float = 0.0) -> str:
    base = "eurusd_st_daybias_f%.0f_%s" % (frac * 100, period)
    if tp_atr and tp_atr > 0:
        return "%s_tp_%gatr" % (base, tp_atr)
    return base


def _df_to_bars(df: pd.DataFrame, timeframe: str, source: str) -> Dict[pd.Timestamp, Bar]:
    out: Dict[pd.Timestamp, Bar] = {}
    for ts, row in df.iterrows():
        out[pd.Timestamp(ts)] = Bar(
            instrument=INSTRUMENT,
            timeframe=timeframe,
            ts=pd.Timestamp(ts).isoformat(),
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0)),
            complete=True,
            source=source,
        )
    return out


def load_replay_frames(
    one_m_path: Path, start: str, end: str
) -> Tuple[pd.DataFrame, pd.DataFrame, List[Bar]]:
    gby = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    one_m = concat_all_1m(gby).sort_index()
    start_ts = pd.Timestamp(start, tz=NY)
    end_ts = pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)
    one_m = one_m[(one_m.index >= start_ts) & (one_m.index < end_ts)]
    hourly = resample_hourly(one_m)
    # Stress MTM on hourly (platform norm for this family); fills still on 1m.
    audit_bars = list(_df_to_bars(hourly, "1h", str(one_m_path)).values())
    return one_m, hourly, audit_bars


def _broker_needs_1m(engine: Engine, strategy_id: str) -> bool:
    """Skip dead 1m tape when flat with no working orders."""
    broker = engine.broker
    open_orders = getattr(broker, "open_orders", None)
    if callable(open_orders):
        try:
            oo = open_orders()
            if oo:
                return True
        except TypeError:
            pass
    # Fallback: inspect store positions / orders tables if present
    try:
        for row in engine.store.read_table("broker_orders"):
            if str(row.get("strategy_id")) != strategy_id:
                continue
            if str(row.get("status")) in {"submitted", "partially_filled"}:
                return True
    except Exception:
        pass
    try:
        for row in engine.store.read_table("positions"):
            if str(row.get("strategy_id")) != strategy_id:
                continue
            if int(float(row.get("quantity") or 0)) != 0:
                return True
    except Exception:
        pass
    # Also check in-memory caches commonly present on PaperBroker
    for attr in ("_orders_cache", "_positions_cache"):
        cache = getattr(broker, attr, None)
        if not isinstance(cache, dict):
            continue
        for obj in cache.values():
            if attr == "_orders_cache":
                if getattr(obj, "strategy_id", "") == strategy_id and getattr(obj, "status", "") in {
                    "submitted",
                    "partially_filled",
                }:
                    return True
            else:
                if getattr(obj, "strategy_id", "") == strategy_id and int(
                    getattr(obj, "quantity", 0) or 0
                ) != 0:
                    return True
    return False


def _itertuples_1m(one_m: pd.DataFrame, source: str) -> Iterator[Bar]:
    vol = one_m["volume"] if "volume" in one_m.columns else None
    for i, (ts, o, h, l, c) in enumerate(
        zip(one_m.index, one_m["open"], one_m["high"], one_m["low"], one_m["close"])
    ):
        yield Bar(
            instrument=INSTRUMENT,
            timeframe="1m",
            ts=pd.Timestamp(ts).isoformat(),
            open=float(o),
            high=float(h),
            low=float(l),
            close=float(c),
            volume=float(vol.iloc[i]) if vol is not None else 0.0,
            complete=True,
            source=source,
        )


def _run_one(
    *,
    one_m: pd.DataFrame,
    hourly: pd.DataFrame,
    audit_bars: List[Bar],
    one_m_path: Path,
    out: Path,
    frac: float,
    period: str,
    force: bool,
    tp_atr: float = 0.0,
) -> dict:
    strategy_id = _slug(frac, period, tp_atr)
    state_root = out / "states" / strategy_id
    if force and state_root.exists():
        shutil.rmtree(state_root)

    config = {
        "timeframe": "1h",
        "atr_len": 14,
        "atr_mult": 3.0,
        "pullback_frac": frac,
        "bias_thresh": 0.70,
        "exit_period": period,
        "add_qty": 1,
        "max_adds": 5,
        "tick_size": TICK,
        "tp_atr_mult": float(tp_atr or 0.0),
    }
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="hourly_st_daybias_dca",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="1h,1m",
        max_contracts=5,
        max_open_orders=32,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])

    prev_pv = POINT_VALUES.get(INSTRUMENT)
    POINT_VALUES[INSTRUMENT] = HALF_LOT_POINT_VALUE
    try:
        engine = Engine(
            store=store,
            persist_bars=False,
            persist_health=False,
            slippage_ticks=1.0,
            tick_size={INSTRUMENT: TICK},
            spread_model=_fx_spread(),
            notification_sink=NullNotificationSink(),
            verification_provider=QuietPaperVerificationProvider(),
            emit_order_alerts=False,
            broker_log_events=False,
            broker_persist_modifications=False,
        )
        h_bars = _df_to_bars(hourly, "1h", str(one_m_path))
        h_times = list(hourly.index)
        print(
            "Replaying %s (%d 1h signals; 1m fills when working orders; f=%.0f%% %s)..."
            % (strategy_id, len(h_times), frac * 100, period),
            flush=True,
        )
        seen_1m = 0
        one_m_index = one_m.index
        for i, h_ts in enumerate(h_times):
            # Signal only — do not fill on hourly OHLC (lookahead vs 1m tape).
            engine.process_bar(h_bars[pd.Timestamp(h_ts)], broker_fills=False)
            if not _broker_needs_1m(engine, strategy_id):
                if (i + 1) % 10000 == 0:
                    print("  1h %d/%d (1m fills %d)" % (i + 1, len(h_times), seen_1m), flush=True)
                continue
            left = pd.Timestamp(h_ts)
            right = pd.Timestamp(h_times[i + 1]) if i + 1 < len(h_times) else one_m_index[-1] + pd.Timedelta(minutes=1)
            # Orders are live_after hour close → fill on subsequent 1m
            lo = one_m_index.searchsorted(left, side="right")
            hi = one_m_index.searchsorted(right, side="right")
            if lo >= hi:
                continue
            sl = one_m.iloc[lo:hi]
            for bar in _itertuples_1m(sl, str(one_m_path)):
                engine.process_bar(bar)
                seen_1m += 1
            if (i + 1) % 10000 == 0:
                print("  1h %d/%d (1m fills %d)" % (i + 1, len(h_times), seen_1m), flush=True)
        print("  done: 1m bars processed=%d" % seen_1m, flush=True)
        if hasattr(engine.broker, "flush_state"):
            engine.broker.flush_state()
        store.flush_tables()

        fills_path = state_root / "fills.csv"
        if not fills_path.exists():
            raise RuntimeError("No fills at %s" % fills_path)
        units = units_from_live_fills(fills_path, strategy_id)
        audit = audit_units(
            name="EURUSD ST day-bias DCA f%.0f %s" % (frac * 100, period),
            slug=strategy_id,
            source=fills_path,
            bar_source=one_m_path,
            bars=read_bars_from_engine_bars(audit_bars),
            units=units,
            instrument=INSTRUMENT,
            notes=(
                "hourly_st_daybias_dca. 1h ST day-bias; 1m fills. pullback f=%.2f; "
                "SL=prev extreme; max 5×/month; exit=%s; tp_atr=%s. Unit=0.5 lot PV=$50k; "
                "fee=$%.2f; slippage=1 tick + FX half-spread."
                % (frac, period, tp_atr or "off", FEE_PER_HALF_LOT)
            ),
            output_root=out / "audits" / strategy_id,
            fee_per_unit=FEE_PER_HALF_LOT,
        )
    finally:
        if prev_pv is not None:
            POINT_VALUES[INSTRUMENT] = prev_pv

    ratio = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
    promote = audit.net_usd >= BASELINE_NET and ratio >= BASELINE_NET_STRESS
    row = {
        "strategy_id": strategy_id,
        "frac": frac,
        "period": period,
        "tp_atr_mult": float(tp_atr or 0.0),
        "trades": audit.trades,
        "units": audit.units,
        "net_usd": round(audit.net_usd, 2),
        "closed_dd_usd": round(audit.close_mtm_dd_usd, 2),
        "stress_dd_usd": round(audit.intrabar_mtm_dd_usd, 2),
        "net_over_stress": round(ratio, 3),
        "win_units": audit.win_units,
        "win_rate_pct": round(100.0 * audit.win_units / audit.units, 2) if audit.units else 0.0,
        "max_open_units": audit.max_open_units,
        "vs_baseline_net": round(audit.net_usd - BASELINE_NET, 2),
        "promote_candidate": bool(promote),
        "fill_tape": "1m",
        "state_root": str(state_root),
    }
    print(json.dumps(row, indent=2), flush=True)
    return row


def _write_summary(out: Path, rows: Sequence[dict]) -> None:
    df = pd.DataFrame(list(rows))
    if not df.empty:
        df = df.sort_values("net_over_stress", ascending=False)
    df.to_csv(out / "leaderboard.csv", index=False)
    (out / "summary.json").write_text(df.to_json(orient="records", indent=2), encoding="utf-8")

    lines = [
        "# EURUSD hourly ST day-bias DCA — broker stress",
        "",
        "Engine + PaperBroker. **1h signals / 1m fills.** Unit = 0.5 lot (PV $50k), fee $0.75,",
        "1-tick slip + FX half-spread. Window matches research (default 2015 → 2026-03).",
        "",
        "Gate vs promoted sleeve: net ≥ $%.0fk and Net/Stress ≥ %.2f."
        % (BASELINE_NET / 1000.0, BASELINE_NET_STRESS),
        "",
        "| Strategy | f | Period | TP | Net | Stress DD | Net/Stress | Units | WR | Max open | Promote? |",
        "|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for _, r in df.iterrows():
        tp_m = float(r.get("tp_atr_mult") or 0)
        tp_s = "—" if tp_m <= 0 else "%g×ATR" % tp_m
        lines.append(
            "| %s | %.0f%% | %s | %s | $%s | $%s | %.2f | %d | %.1f%% | %d | %s |"
            % (
                r["strategy_id"],
                100 * r["frac"],
                r["period"],
                tp_s,
                f"{r['net_usd']:,.0f}",
                f"{r['stress_dd_usd']:,.0f}",
                r["net_over_stress"],
                r["units"],
                r["win_rate_pct"],
                r["max_open_units"],
                "YES" if r["promote_candidate"] else "no",
            )
        )
    lines.extend(
        [
            "",
            "Research (pandas) pack: `../eurusd_hourly_st_daybias_dca/SUMMARY.md`",
            "States / audits under this folder.",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out / "SUMMARY.md", flush=True)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD ST day-bias DCA broker stress")
    parser.add_argument("--output-root", type=Path, default=OUT_DEFAULT)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--start", default="2015-01-01")
    parser.add_argument("--end", default="2026-03-31")
    parser.add_argument(
        "--only",
        default="",
        help="Comma list like 0.30:week,0.40:month (default = all positive research cells)",
    )
    parser.add_argument(
        "--tp-atr",
        default="0",
        help="Comma list of ATR TP multiples (0=off). Applied to each --only / default variant.",
    )
    args = parser.parse_args(argv)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    one_m_path, _daily = ensure_eurusd_platform_files(REPO)
    print("Loading 1m + hourly %s → %s ..." % (args.start, args.end), flush=True)
    one_m, hourly, audit_bars = load_replay_frames(one_m_path, args.start, args.end)
    print("  1m bars: %d | 1h bars: %d" % (len(one_m), len(hourly)), flush=True)

    if args.only.strip():
        variants: List[Tuple[float, str]] = []
        for part in args.only.split(","):
            part = part.strip()
            if not part:
                continue
            f_s, p = part.split(":")
            variants.append((float(f_s), p.strip()))
    else:
        variants = list(DEFAULT_VARIANTS)

    tp_list = [float(x.strip()) for x in args.tp_atr.split(",") if x.strip()]
    if not tp_list:
        tp_list = [0.0]

    rows: List[Dict] = []
    for frac, period in variants:
        for tp_atr in tp_list:
            rows.append(
                _run_one(
                    one_m=one_m,
                    hourly=hourly,
                    audit_bars=audit_bars,
                    one_m_path=one_m_path,
                    out=out,
                    frac=frac,
                    period=period,
                    force=args.force,
                    tp_atr=tp_atr,
                )
            )
            _write_summary(out, rows)

    _write_summary(out, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
