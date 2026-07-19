"""EURUSD prior-opposed replay: hourly ST+PMC gate → v2b StrategyPlugin.

Prior-opposed = v2b only arms after a same-session hourly ST+PMC entry has
already fired in the opposite direction (ST + PMC v2b).

FX adaptations vs futures:
- Absolute price units: ``sl25_tp75`` means 25/75 *pips* (0.0025 / 0.0075).
- Tick size 0.00001; point value 100000 (1 standard lot USD per 1.0 move).
- Same NY RTH 09:30–16:00 OR window as the equity-index v2b path.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_loss_research import VariantConfig
from .hourly_st_pmc_strategyplugin_variants import REPO, run_variant
from .models import Bar, StrategyInstance, as_row
from .nq_v2b_prior_opposed_replay import Result, load_st_events, summarize_units, write_report
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MarketConfig, _regime_dates
from .v2b_strategy_replay import AuditBar
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


NY = "America/New_York"
INSTRUMENT = "EURUSD"
MARKET = "eurusd"
PIP = 0.0001
TICK = 0.00001
# 25/75 pips — name retained so prior-opposed ST strategy_id matches futures convention.
ST_VARIANT = VariantConfig(
    "sl25_tp75_3r",
    stop_pts=25.0 * PIP,
    tp1_pts=75.0 * PIP,
    notes="EURUSD 25/75 pip ST+PMC; absolute price units.",
)
ST_STRATEGY_ID = "%s_hourly_st_pmc_%s" % (MARKET, ST_VARIANT.name)
V2B_STRATEGY_ID = "%s_v2b_prior_opposed_stpmc_only_S_1_1_3" % MARKET
POINT_VALUE = 100000.0  # 1 standard lot: $10 per pip = $100k per 1.0
FEE_PER_UNIT = 7.0  # rough round-turn commission proxy per lot
DEFAULT_START = date(2015, 1, 2)


def _ensure_point_value() -> None:
    POINT_VALUES.setdefault(INSTRUMENT, POINT_VALUE)
    DEFAULT_TICK_SIZE.setdefault(INSTRUMENT, TICK)


def load_eurusd_hourly_bars(one_m: Path) -> List[Bar]:
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    hourly_df = resample_hourly(concat_all_1m(gby))
    bars: List[Bar] = []
    for ts, row in hourly_df.iterrows():
        bars.append(
            Bar(
                instrument=INSTRUMENT,
                timeframe="1h",
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
        )
    return bars


def run_st_pmc(
    *,
    one_m: Path,
    daily: Path,
    output_root: Path,
    force: bool,
    max_bars: Optional[int] = None,
) -> Path:
    _ensure_point_value()
    st_root = output_root / "st_pmc"
    print("Loading EURUSD hourly bars for ST+PMC...", flush=True)
    bars = load_eurusd_hourly_bars(one_m)
    if max_bars:
        bars = bars[:max_bars]
    print("  %s hourly bars" % f"{len(bars):,}", flush=True)
    # Monkey-patch tick into config_json path via instrument lookup extension.
    from . import hourly_st_pmc_strategyplugin_variants as hsv

    hsv.TICK_SIZE[INSTRUMENT] = TICK
    result = run_variant(
        cfg=ST_VARIANT,
        bars=bars,
        output_root=st_root,
        dbn=one_m,
        daily_path=daily,
        instrument=INSTRUMENT,
        market=MARKET,
        force=force,
        quiet=True,
    )
    print(
        "  ST+PMC %s Net=$%s units=%d"
        % (result.variant, f"{result.audit.net_usd:,.2f}", result.audit.units),
        flush=True,
    )
    fills = result.state_root / "fills.csv"
    if not fills.exists():
        raise FileNotFoundError(fills)
    return fills


def _has_full_rth_close(raw_day: Optional[pd.DataFrame], session: date) -> bool:
    from .bars import rth_bars

    rth = rth_bars(raw_day, session, dense=True)
    if rth.empty:
        return False
    cutoff = pd.Timestamp("15:55").time()
    return bool((rth.index.time >= cutoff).any())


def run_v2b_prior_opposed(
    *,
    one_m: Path,
    daily: Path,
    st_fills: Path,
    output_root: Path,
    force: bool,
    start: date,
    max_days: Optional[int] = None,
) -> Result:
    _ensure_point_value()
    cfg = MarketConfig(
        market=MARKET,
        instrument=INSTRUMENT,
        daily_path=daily,
        dbn_path=one_m,
        start=start,
        fee_per_unit=FEE_PER_UNIT,
    )
    state_root = output_root / "states" / V2B_STRATEGY_ID
    if force and state_root.exists():
        shutil.rmtree(state_root)

    st_events = load_st_events(st_fills, ST_STRATEGY_ID)
    print("Loading EURUSD 1m bars for v2b prior-opposed...", flush=True)
    gby = load_fx_1m_by_ny_date(one_m, INSTRUMENT)
    st_orders = st_fills.parent / "orders.csv"
    if st_orders.exists():
        print("Refining EURUSD ST+PMC gate timestamps with 1m first-touch...", flush=True)
        st_events = load_st_events(
            st_fills,
            ST_STRATEGY_ID,
            orders_path=st_orders,
            bars_by_ny_date=gby,
        )
    regime_dates = _regime_dates(cfg, gby, start=start)
    regime_dates = [d for d in regime_dates if _has_full_rth_close(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    print("  regime sessions: %d" % len(regime_dates), flush=True)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=V2B_STRATEGY_ID,
        strategy_type="v2b_scaleout",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="1m",
        max_contracts=5,
        max_open_orders=64,
        config_json=json.dumps(
            {
                "market": MARKET,
                "mode": "oco_then_reverse",
                "entry_qty": 5,
                "tp1_qty": 1,
                "tp2_qty": 1,
                "tick_size": TICK,
                "use_regime_filter": True,
                "start": start.isoformat(),
                "regime_dates": [d.isoformat() for d in regime_dates],
                "record_levels": False,
                "dynamic_sizing_events": st_events,
                "prior_opposite_only": True,
                "prior_opposite_entry_qty": 5,
                "prior_opposite_tp1_qty": 1,
                "prior_opposite_tp2_qty": 1,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])

    fx_spread = SpreadModel(
        rth_half_spread_ticks=5.0,  # ~0.5 pip half-spread
        eth_half_spread_ticks=10.0,
        open_widen_half_spread_ticks=10.0,
        low_volume_threshold=1.0,
        low_volume_multiplier=1.5,
        tick_size=TICK,
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={INSTRUMENT: TICK},
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=fx_spread),
    )

    from .bars import rth_bars

    audit_bars: List[AuditBar] = []
    for idx, day in enumerate(regime_dates, start=1):
        df = rth_bars(gby.get(day), day, dense=True)
        if df.empty:
            continue
        for ts, row in df.iterrows():
            ts_s = pd.Timestamp(ts).isoformat()
            bar = Bar(
                instrument=INSTRUMENT,
                timeframe="1m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(one_m),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if idx % 250 == 0:
            print("  EURUSD %d/%d sessions" % (idx, len(regime_dates)), flush=True)
    store.flush_tables()

    result = summarize_units(
        V2B_STRATEGY_ID,
        state_root,
        audit_bars,
        INSTRUMENT,
        FEE_PER_UNIT,
        market=MARKET,
        regime_days=len(regime_dates),
        st_events=st_events,
        start_date=start,
    )
    write_report(output_root, result)
    write_run_manifest(
        output_root,
        data_inputs=[one_m, daily, st_fills],
        output_paths=[
            output_root / "summary.csv",
            output_root / "INDEX.md",
            state_root / "fills.csv",
            state_root / "orders.csv",
        ],
        strategy_config={
            "strategy_id": V2B_STRATEGY_ID,
            "market": MARKET,
            "start": start.isoformat(),
            "st_strategy_id": ST_STRATEGY_ID,
            "st_stop_pips": 25,
            "st_target_pips": 75,
            "entry_qty": 5,
            "sizing": "S_1_1_3",
            "point_value": POINT_VALUE,
            "tick_size": TICK,
        },
        broker_realism_config={
            "slippage_ticks": 1.0,
            "fee_per_unit": FEE_PER_UNIT,
            "directional_adverse_path": True,
            "spread_model": "fx_half_pip",
        },
        causality_mode="audit",
        extra={
            "driver": "eurusd_prior_opposed_replay",
            "causality_violations": result.causality_violations,
            "timezone_note": "Histdata timestamps localized as America/New_York",
        },
    )
    return result


def run(
    *,
    output_root: Path,
    force: bool = True,
    start: date = DEFAULT_START,
    max_days: Optional[int] = None,
    max_st_bars: Optional[int] = None,
    skip_st: bool = False,
    st_fills: Optional[Path] = None,
    force_convert: bool = False,
) -> Result:
    _ensure_point_value()
    output_root.mkdir(parents=True, exist_ok=True)
    one_m, daily = ensure_eurusd_platform_files(REPO, force=force_convert)

    if skip_st:
        if st_fills is None:
            st_fills = output_root / "st_pmc" / "states" / ST_STRATEGY_ID / "fills.csv"
        if not st_fills.exists():
            raise FileNotFoundError(st_fills)
    else:
        st_fills = run_st_pmc(
            one_m=one_m,
            daily=daily,
            output_root=output_root,
            force=force,
            max_bars=max_st_bars,
        )

    return run_v2b_prior_opposed(
        one_m=one_m,
        daily=daily,
        st_fills=st_fills,
        output_root=output_root,
        force=force,
        start=start,
        max_days=max_days,
    )


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="EURUSD ST+PMC → v2b prior-opposed StrategyPlugin replay.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "eurusd_v2b_prior_opposed_stpmc_broker_like",
    )
    parser.add_argument("--start", default=DEFAULT_START.isoformat())
    parser.add_argument("--max-days", type=int, default=None, help="Cap v2b regime sessions (smoke tests).")
    parser.add_argument("--max-st-bars", type=int, default=None, help="Cap hourly ST bars (smoke tests).")
    parser.add_argument("--skip-st", action="store_true", help="Reuse existing ST fills under output-root.")
    parser.add_argument("--st-fills", type=Path, default=None)
    parser.add_argument("--force-convert", action="store_true", help="Rebuild fx/eurusd_*.csv from raw Histdata.")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    try:
        start = date.fromisoformat(args.start)
    except ValueError as exc:
        raise SystemExit("--start must be YYYY-MM-DD") from exc

    result = run(
        output_root=args.output_root,
        force=not args.no_force,
        start=start,
        max_days=args.max_days,
        max_st_bars=args.max_st_bars,
        skip_st=args.skip_st,
        st_fills=args.st_fills,
        force_convert=args.force_convert,
    )
    print(
        "Wrote %s (Net=$%.2f Net/Stress=%.2f causality_violations=%d)"
        % (args.output_root / "INDEX.md", result.net_usd, result.net_stress, result.causality_violations),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
