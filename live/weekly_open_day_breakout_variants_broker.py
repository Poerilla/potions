"""Weekly open-day breakout — today's variant sweep on index CFDs.

Variants (same 4h signal / 1m fill path as ``weekly_open_day_breakout_1m_broker``):

1. ``filters_candle_sl`` — size filters on; candle SL; 2/1/1; Fri NY flatten
2. ``candle_sl_fri`` — no filters; candle SL; 2/1/1; Fri NY flatten (v2)
3. ``od_sl_fri`` — no filters; OD far SL; 2/1/1; Fri NY flatten (v3)
4. ``od_sl_20r`` — no filters; OD far SL; 2/1/1/1; BE after TP1; runner to 20R;
   no Fri flatten; hold across weeks (v4)
5. ``od_sl_fri_bull_hivol`` — v3 + causal bull (close≥200DMA) × high vol
   (20d realized vol ≥ trailing 252d median)
6. ``od_oco_1r_bull_hivol`` — OCO full size @ 1×OD-R; bull×hivol; unlimited/wk
7. ``od_half_eow_bull_hivol`` — 1@0.5×OD + 1@1×OD (BE) + 1 EOW runner; bull×hivol
8. ``od_half_3r_bull_hivol`` — same half/1R scale; runner to 3×OD-R; Fri residual
9. ``od_half_eow_bull_hivol_nohol`` — (7) + skip US-holiday / thin Mondays
10. ``od_half_3r_bull_hivol_nohol`` — (8) + skip US-holiday / thin Mondays
11. ``od_half_eow_bull_hivol_w1`` — (7) + causal ``allow_weeks_of_month=[1]``
12. ``od_half_eow_bull_hivol_w1_add8h`` — (11) + market +1 every 8h (same SL/TP prices)

Default markets: NAS100, SPX500 (SPX500 skipped when ``fx/spx500_1m.csv`` missing).
Hub: ``live/state/weekly_open_day_breakout_variants``
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .gbpusd_quarterly_4h_charts import load_4h
from .models import StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS, MarketSpec, _spread
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .v2b_strategy_replay import fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider
from .weekly_open_day_breakout_1m_broker import (
    _1m_csv,
    _progress,
    _replay_4h_with_1m,
    _signal_bars,
)
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "weekly_open_day_breakout_variants"
NY = "America/New_York"
DSR = "TRL-2026-00165"

# Shared base (Monday-aligned OD, max 2/wk, 4h/1m).
_BASE = {
    "atr_len": 14,
    "atr_mult": 4.0,
    "timeframe": "4h",
    "max_trades_per_week": 2,
    "record_levels": False,
    "suppress_alerts": True,
}

_BULL_HIVOL = {
    "require_bull_200dma": True,
    "require_high_vol": True,
    "ma_len": 200,
    "vol_ret_days": 20,
    "vol_median_lookback": 252,
}

_HALF_SCALE = {
    "exit_mode": "scale_od_frac",
    "entry_qty": 3,
    "tp1_qty": 1,
    "tp2_qty": 1,
    "tp3_qty": 0,
    "runner_qty": 1,
    "tp1_od_mult": 0.5,
    "tp2_od_mult": 1.0,
    "tp3_od_mult": None,
    "tp3_r_mult": None,
    "runner_r_mult": None,
    "stop_mode": "od_far",
    "be_after": "tp2",  # BE once 1×OD-R fills
    "hold_across_weeks": False,
    "skip_candle_gt_od": False,
    "skip_candle_gt_atr_room": False,
    "max_trades_per_week": 0,
    **_BULL_HIVOL,
}

_NOHOL = {
    "skip_us_holiday_monday": True,
    "min_open_day_bars": 5,
}

VARIANTS: Dict[str, Dict[str, Any]] = {
    "filters_candle_sl": {
        **_BASE,
        "label": "filters + candle SL + 2/1/1 Fri flatten",
        "entry_qty": 4,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "tp3_qty": 0,
        "runner_qty": 1,
        "tp3_r_mult": None,
        "runner_r_mult": None,
        "stop_mode": "candle",
        "friday_flatten": True,
        "hold_across_weeks": False,
        "skip_candle_gt_od": True,
        "skip_candle_gt_atr_room": True,
        "be_after": "tp2",
    },
    "candle_sl_fri": {
        **_BASE,
        "label": "candle SL + 2/1/1 Fri flatten (v2)",
        "entry_qty": 4,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "tp3_qty": 0,
        "runner_qty": 1,
        "tp3_r_mult": None,
        "runner_r_mult": None,
        "stop_mode": "candle",
        "friday_flatten": True,
        "hold_across_weeks": False,
        "skip_candle_gt_od": False,
        "skip_candle_gt_atr_room": False,
        "be_after": "tp2",
    },
    "od_sl_fri": {
        **_BASE,
        "label": "OD far SL + 2/1/1 Fri flatten (v3)",
        "entry_qty": 4,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "tp3_qty": 0,
        "runner_qty": 1,
        "tp3_r_mult": None,
        "runner_r_mult": None,
        "stop_mode": "od_far",
        "friday_flatten": True,
        "hold_across_weeks": False,
        "skip_candle_gt_od": False,
        "skip_candle_gt_atr_room": False,
        "be_after": "tp2",
    },
    "od_sl_20r": {
        **_BASE,
        "label": "OD far SL + 2/1/1/1 runner→20R BE (v4)",
        "entry_qty": 5,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "tp3_qty": 1,
        "runner_qty": 1,
        "tp3_r_mult": 4.0,
        "runner_r_mult": 20.0,
        "stop_mode": "od_far",
        "friday_flatten": False,
        "hold_across_weeks": True,
        "skip_candle_gt_od": False,
        "skip_candle_gt_atr_room": False,
        "be_after": "tp1",
    },
    "od_sl_fri_bull_hivol": {
        **_BASE,
        "label": "OD far SL + 2/1/1 Fri + bull×high-vol gate",
        "entry_qty": 4,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "tp3_qty": 0,
        "runner_qty": 1,
        "tp3_r_mult": None,
        "runner_r_mult": None,
        "stop_mode": "od_far",
        "friday_flatten": True,
        "hold_across_weeks": False,
        "skip_candle_gt_od": False,
        "skip_candle_gt_atr_room": False,
        "be_after": "tp2",
        **_BULL_HIVOL,
    },
    "od_oco_1r_bull_hivol": {
        **_BASE,
        "label": "OCO 1×OD-R target + OD far SL + bull×high-vol; unlimited/wk",
        "entry_qty": 1,
        "tp1_qty": 1,
        "tp2_qty": 0,
        "tp3_qty": 0,
        "runner_qty": 0,
        "tp3_r_mult": None,
        "runner_r_mult": None,
        "exit_mode": "oco_od_r",
        "stop_mode": "od_far",
        "friday_flatten": True,
        "hold_across_weeks": False,
        "skip_candle_gt_od": False,
        "skip_candle_gt_atr_room": False,
        "be_after": "none",
        "max_trades_per_week": 0,
        **_BULL_HIVOL,
    },
    "od_half_eow_bull_hivol": {
        **_BASE,
        **_HALF_SCALE,
        "label": "1@0.5×OD + 1@1×OD (BE) + 1 EOW runner; bull×hivol",
        "runner_od_mult": None,
        "friday_flatten": True,
    },
    "od_half_eow_bull_hivol_w1": {
        **_BASE,
        **_HALF_SCALE,
        "label": "half+EOW bull×hivol; week-of-month=1 entry gate",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [1],
    },
    "od_half_eow_bull_hivol_w1_add8h": {
        **_BASE,
        **_HALF_SCALE,
        "label": "half+EOW bull×hivol; week-1; +1 contract every 8h; max_adds=9",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [1],
        "add_every_hours": 8.0,
        "add_qty": 1,
        # Locked to observed NAS100 effective max (see RESEARCH_CONTRACT.yaml v1).
        "max_adds": 9,
    },
    "od_half_eow_bull_hivol_w1_add8h_swing_gated": {
        **_BASE,
        **_HALF_SCALE,
        "label": "swing-close; gated BO (week+regime); swing after gate; week-1; +1/8h",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [1],
        "add_every_hours": 8.0,
        "add_qty": 1,
        "max_adds": 9,
        "entry_mode": "swing_close",
        "breakout_mode": "gated",
        "swing_before_regime": False,
    },
    "od_half_eow_bull_hivol_w1_add8h_swing_struct": {
        **_BASE,
        **_HALF_SCALE,
        "label": "swing-close; structural BO; swing may precede bull×hivol; week-1; +1/8h",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [1],
        "add_every_hours": 8.0,
        "add_qty": 1,
        "max_adds": 9,
        "entry_mode": "swing_close",
        "breakout_mode": "structural",
        "swing_before_regime": True,
    },
    "od_half_eow_bull_hivol_w1_add8h_swing_gated_pre": {
        **_BASE,
        **_HALF_SCALE,
        "label": "swing-close; gated week@BO; swing may precede bull×hivol; week-1; +1/8h",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [1],
        "add_every_hours": 8.0,
        "add_qty": 1,
        "max_adds": 9,
        "entry_mode": "swing_close",
        "breakout_mode": "gated",
        "swing_before_regime": True,
    },
    "od_half_eow_bull_hivol_w1_add8h_swing_struct_post": {
        **_BASE,
        **_HALF_SCALE,
        "label": "swing-close; structural BO; swing only after bull×hivol on; week-1; +1/8h",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [1],
        "add_every_hours": 8.0,
        "add_qty": 1,
        "max_adds": 9,
        "entry_mode": "swing_close",
        "breakout_mode": "structural",
        "swing_before_regime": False,
    },
    # Best swing cell (struct) with gates removed: all weeks, no bull×hivol.
    "od_half_eow_ungated_allweeks_add8h_swing_struct": {
        **_BASE,
        **_HALF_SCALE,
        "label": "swing-close; structural BO; all weeks; NO bull×hivol; +1/8h",
        "runner_od_mult": None,
        "friday_flatten": True,
        "allow_weeks_of_month": [],
        "require_bull_200dma": False,
        "require_high_vol": False,
        "add_every_hours": 8.0,
        "add_qty": 1,
        "max_adds": 9,
        "entry_mode": "swing_close",
        "breakout_mode": "structural",
        "swing_before_regime": True,
        "swing_require_pullback": True,
    },
    "od_half_3r_bull_hivol": {
        **_BASE,
        **_HALF_SCALE,
        "label": "1@0.5×OD + 1@1×OD (BE) + 1@3×OD runner; bull×hivol",
        "runner_od_mult": 3.0,
        "friday_flatten": True,
    },
    "od_half_eow_bull_hivol_nohol": {
        **_BASE,
        **_HALF_SCALE,
        **_NOHOL,
        "label": "half+EOW bull×hivol; skip holiday/thin Monday",
        "runner_od_mult": None,
        "friday_flatten": True,
    },
    "od_half_3r_bull_hivol_nohol": {
        **_BASE,
        **_HALF_SCALE,
        **_NOHOL,
        "label": "half+3×OD runner bull×hivol; skip holiday/thin Monday",
        "runner_od_mult": 3.0,
        "friday_flatten": True,
    },
}


def _has_1m(market: MarketSpec) -> bool:
    return _1m_csv(market).exists()


def run_one_variant(
    *,
    output_root: Path,
    market: MarketSpec,
    variant_id: str,
    cfg: Dict[str, Any],
    force: bool,
    start: Optional[date],
    end: Optional[date],
    causality_mode: str = "audit",
) -> dict:
    strategy_id = "%s_wod_%s" % (market.symbol.lower(), variant_id)
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    one_m_path = _1m_csv(market)
    if not one_m_path.exists():
        raise FileNotFoundError("Missing 1m tape for %s: %s" % (market.symbol, one_m_path))
    if not market.csv.exists():
        raise FileNotFoundError("Missing 4h tape for %s: %s" % (market.symbol, market.csv))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick

    df = load_4h(market.csv, market.symbol)
    if start is not None:
        warm = pd.Timestamp(start, tz=NY) - pd.Timedelta(days=60)
        df = df[df.index >= warm]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]

    _progress(output_root, "Loading %s 1m ..." % market.symbol)
    gby = load_fx_1m_by_ny_date(one_m_path, market.symbol)
    one_m = concat_all_1m(gby)
    if start is not None:
        one_m = one_m[one_m.index >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        one_m = one_m[one_m.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if one_m.empty:
        raise RuntimeError("empty 1m tape for %s" % market.symbol)
    _progress(output_root, "  %s 4h=%d 1m=%d variant=%s" % (market.symbol, len(df), len(one_m), variant_id))

    signal_bars, audit_bars = _signal_bars(df, market)
    if start is not None:
        start_utc = pd.Timestamp(start, tz=NY).tz_convert("UTC")
        audit_bars = [b for b in audit_bars if pd.Timestamp(b.ts) >= start_utc]

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {k: v for k, v in cfg.items() if k != "label"}
    payload["tick_size"] = market.tick
    entry_qty = int(payload.get("entry_qty") or 4)
    max_contracts = max(entry_qty, 8)
    if float(payload.get("add_every_hours") or 0) > 0:
        max_contracts = max(max_contracts, 48)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="weekly_open_day_breakout",
                    version="v7",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="4h",
                    max_contracts=max_contracts,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={market.symbol: market.tick},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        causality_mode=causality_mode,
        **hardened_replay_engine_kwargs(
            slippage_ticks=1.0,
            spread_model=_spread(market.tick, market.family),
        ),
    )
    _progress(output_root, "START %s %s causality=%s" % (market.symbol, variant_id, causality_mode))
    _replay_4h_with_1m(
        engine,
        signal_bars=signal_bars,
        one_m=one_m,
        market=market,
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
        instrument=market.symbol,
        fee_per_unit=market.fee_per_unit,
    )
    net = float(audit.get("net_usd") or 0.0)
    stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    ns = (net / abs(stress)) if stress else 0.0
    trades = int(audit.get("trades") or len({u.trade_id for u in units}))
    if ns >= 2.0 and trades >= 20:
        stance = "research — interesting N/S"
    elif net > 0 and trades >= 10:
        stance = "weak — needs tune"
    else:
        stance = "reject / thin"

    metrics = {
        "strategy_id": strategy_id,
        "market": market.symbol,
        "variant": variant_id,
        "label": cfg.get("label") or variant_id,
        "feed_tf": "1m",
        "signal_tf": "4h",
        "bars_4h": len(signal_bars),
        "bars_1m": len(one_m),
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "win_rate": float(audit.get("win_rate") or 0.0) / 100.0,
        "profit_factor": float(audit.get("profit_factor") or 0.0),
        "net_over_stress": ns,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "stance": stance,
        "dsr_trial": DSR,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s/%s net=%+.0f N/S=%.2f trades=%d WR=%.1f%%"
        % (market.symbol, variant_id, net, ns, trades, 100.0 * metrics["win_rate"]),
    )
    return metrics


def write_summary(output_root: Path, rows: Sequence[dict], skipped: Sequence[str], start: date, end: date) -> None:
    lines = [
        "# Weekly open-day breakout — variant sweep",
        "",
        "Window: %s → %s · DSR %s" % (start.isoformat(), end.isoformat(), DSR),
        "",
        "| Market | Variant | Trades | Net | Stress DD | N/S | WR | PF | Stance |",
        "|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for m in rows:
        lines.append(
            "| %s | %s | %d | $%+.0f | $%+.0f | %.2f | %.1f%% | %.2f | %s |"
            % (
                m["market"],
                m["variant"],
                int(m.get("trades") or 0),
                float(m.get("net_usd") or 0.0),
                float(m.get("intrabar_stress_dd_usd") or 0.0),
                float(m.get("net_over_stress") or 0.0),
                100.0 * float(m.get("win_rate") or 0.0),
                float(m.get("profit_factor") or 0.0),
                m.get("stance") or "",
            )
        )
    if skipped:
        lines.extend(["", "Skipped: " + ", ".join(skipped), ""])
    lines.extend(["", "Hub: `%s`" % output_root, ""])
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(list(rows)).to_csv(output_root / "summary.csv", index=False)


def run(
    *,
    output_root: Path,
    markets: Sequence[str],
    variants: Sequence[str],
    years: float,
    force: bool,
    email: bool,
    causality_mode: str = "audit",
) -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    skipped: List[str] = []
    runnable: List[MarketSpec] = []
    for sym in markets:
        key = sym.upper()
        if key not in MARKETS:
            skipped.append("%s (unknown market)" % key)
            continue
        market = MARKETS[key]
        if not _has_1m(market):
            skipped.append("%s (no fx/%s_1m.csv)" % (key, key.lower()))
            continue
        if not market.csv.exists():
            skipped.append("%s (no 4h csv)" % key)
            continue
        runnable.append(market)

    if not runnable:
        body = "Weekly OD breakout variants\n\nHub: %s\n\nNo runnable markets.\nSkipped: %s\n" % (
            output_root,
            ", ".join(skipped) or "(none)",
        )
        (output_root / "EMAIL.txt").write_text(body, encoding="utf-8")
        if email:
            send_email(subject="potions: weekly OD variants — no markets", body=body)
        return 1

    probe = runnable[0]
    df_probe = load_4h(probe.csv, probe.symbol)
    end = df_probe.index.max().tz_convert(NY).date() if len(df_probe) else date.today()
    start = end - timedelta(days=int(round(365.25 * years)))
    start = start - timedelta(days=start.weekday())

    rid = begin_run(
        run_class="broker_like",
        variant_slug="weekly_open_day_breakout_variants",
        instrument=",".join(m.symbol for m in runnable),
        hub_path=str(output_root.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "years": years,
            "variants": list(variants),
            "skipped": skipped,
            "causality_mode": causality_mode,
        },
    )
    try:
        rows: List[dict] = []
        for market in runnable:
            for vid in variants:
                cfg = VARIANTS[vid]
                rows.append(
                    run_one_variant(
                        output_root=output_root,
                        market=market,
                        variant_id=vid,
                        cfg=cfg,
                        force=force,
                        start=start,
                        end=end,
                        causality_mode=causality_mode,
                    )
                )
        write_summary(output_root, rows, skipped, start, end)
        (output_root / "RUN_COMPLETE.json").write_text('{"ok": true}\n', encoding="utf-8")
        data_inputs: List[Path] = []
        for m in runnable:
            data_inputs.append(m.csv)
            data_inputs.append(_1m_csv(m))
        write_run_manifest(
            output_root,
            data_inputs=data_inputs,
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={
                "strategy_type": "weekly_open_day_breakout",
                "variants": list(variants),
                "plugin_version": "v6",
            },
            causality_mode=causality_mode,
            extra={"dsr_trial_id": DSR, "skipped": skipped, "causality_mode": causality_mode},
        )
        body_lines = [
            "Weekly open-day breakout — variant sweep",
            "",
            "Hub: %s" % output_root,
            "DSR: %s" % DSR,
            "Causality: %s" % causality_mode,
            "Window: %s → %s (~%.1fy)" % (start.isoformat(), end.isoformat(), years),
            "Variants: %s" % ", ".join(variants),
            "",
        ]
        if skipped:
            body_lines.append("Skipped: %s" % ", ".join(skipped))
            body_lines.append("")
        for m in rows:
            body_lines.append(
                "%s / %s: trades=%d net=$%+.0f N/S=%.2f WR=%.1f%% — %s"
                % (
                    m["market"],
                    m["variant"],
                    int(m["trades"]),
                    float(m["net_usd"]),
                    float(m["net_over_stress"]),
                    100.0 * float(m["win_rate"]),
                    m["stance"],
                )
            )
        body = "\n".join(body_lines) + "\n"
        (output_root / "EMAIL.txt").write_text(body, encoding="utf-8")
        if email:
            send_email(subject="potions: weekly OD breakout variants", body=body)
        complete_run(
            rid,
            net_usd=sum(float(r["net_usd"]) for r in rows),
            stress_dd_usd=min((float(r["intrabar_stress_dd_usd"]) for r in rows), default=0.0),
            trades=sum(int(r["trades"]) for r in rows),
            meta={"rows": rows, "skipped": skipped},
        )
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _progress(output_root, "CRASH %s\n%s" % (exc, traceback.format_exc()))
        if email:
            send_email(
                subject="potions: weekly OD variants FAILED",
                body="Hub: %s\n\n%s\n%s" % (output_root, exc, traceback.format_exc()[-2000:]),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--market", action="append", default=[], help="Repeatable; default NAS100,SPX500")
    p.add_argument(
        "--variant",
        action="append",
        default=[],
        choices=sorted(VARIANTS.keys()),
        help="Repeatable; default all four today's variants",
    )
    p.add_argument("--years", type=float, default=3.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--causality-mode",
        default="audit",
        choices=["audit", "strict"],
        help="CausalityGuard mode (strict for promotion-grade week-1 verification)",
    )
    args = p.parse_args(argv)
    markets = args.market or ["NAS100", "SPX500"]
    variants = args.variant or list(VARIANTS.keys())
    return run(
        output_root=args.output_root,
        markets=markets,
        variants=variants,
        years=float(args.years),
        force=bool(args.force),
        email=bool(args.email),
        causality_mode=str(args.causality_mode),
    )


if __name__ == "__main__":
    raise SystemExit(main())
