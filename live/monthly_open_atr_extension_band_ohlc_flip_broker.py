"""Broker-like: first-week 4h OHLC/OLHC liquidity-run flip → band-max fade.

Week-1 NY 4h pattern:
  - ≥2 consecutive 4h candles with O&C on the same side of month open (liquidity run)
  - then a 4h close on the opposite side (still week 1)
  - fade that run: resting limit at band-max entry; SL = run swing extreme
  - ladder 1/1/1 → band-med / month-open / runner to EOM (BE only after open TP)

Hub: ``live/state/monthly_open_atr_extension_band/broker_max_ohlc_flip_111/``
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .monthly_atr4_helpers import load_1h
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    _sl_mode_blurb,
    build_month_plans,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run, metrics_from_equity_curve
from .spread_model import SpreadModel
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = (
    REPO / "live" / "state" / "monthly_open_atr_extension_band" / "broker_max_ohlc_flip_111"
)
FEE = 1.50
ENTRY_MODE = "max"
SL_MODE = "plus_0.3"  # band stop unused for armed trades (swing SL); kept for plan build
LADDER: Tuple[int, int, int] = (1, 1, 1)
DSR = "TRL-2026-00135"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _spread(tick: float) -> SpreadModel:
    return SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0,
        low_volume_multiplier=1.5,
        tick_size=tick,
    )


def bars_from_1h_df(df: pd.DataFrame, instrument: str, source: str) -> List[Bar]:
    rows: List[Bar] = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        ts_s = pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")
        o = float(row["open"])
        h = float(row["high"])
        l = float(row["low"])
        c = float(row["close"])
        if min(o, h, l, c) <= 0 or h < max(o, c) or l > min(o, c):
            continue
        rows.append(
            Bar(
                instrument=instrument,
                timeframe="1h",
                ts=ts_s,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=source,
            )
        )
    return rows


def _profile_losses(state_root: Path, strategy_id: str, audits_root: Path) -> Dict[str, object]:
    """Break down exits / runner contribution from unit fills + campaigns."""
    fills_path = state_root / "fills.csv"
    out: Dict[str, object] = {"strategy_id": strategy_id}
    if not fills_path.exists():
        out["error"] = "no fills"
        return out
    fills = pd.read_csv(fills_path)
    if fills.empty:
        out["error"] = "empty fills"
        return out
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    reasons = fills.groupby(fills["reason"].astype(str)).size().to_dict()
    out["fill_reasons"] = {str(k): int(v) for k, v in reasons.items()}

    unit_path = audits_root / strategy_id / "unit_fills.csv"
    if unit_path.exists():
        units = pd.read_csv(unit_path)
        # replay_audit unit_fills use ``usd``; older research frames used ``pnl_usd``.
        pnl_col = "pnl_usd" if "pnl_usd" in units.columns else ("usd" if "usd" in units.columns else "")
        if not units.empty and "exit_reason" in units.columns and pnl_col:
            by_exit = (
                units.groupby(units["exit_reason"].astype(str))
                .agg(n=(pnl_col, "size"), net=(pnl_col, "sum"), avg=(pnl_col, "mean"))
                .reset_index()
            )
            out["by_exit_reason"] = by_exit.to_dict(orient="records")
            stops = units[units["exit_reason"].astype(str).str.lower().isin(["stop", "sl"])]
            wins = units[units[pnl_col] > 0]
            losses = units[units[pnl_col] < 0]
            out["unit_n"] = int(len(units))
            out["unit_net"] = float(units[pnl_col].sum())
            out["stop_units"] = int(len(stops))
            out["stop_net"] = float(stops[pnl_col].sum()) if len(stops) else 0.0
            out["win_units"] = int(len(wins))
            out["loss_units"] = int(len(losses))
            out["avg_win"] = float(wins[pnl_col].mean()) if len(wins) else 0.0
            out["avg_loss"] = float(losses[pnl_col].mean()) if len(losses) else 0.0
            # Runner impact: units with exit eom / flatten after target path vs stopped early
            runnerish = units[
                units["exit_reason"].astype(str).str.lower().isin(["eom", "flatten", "target_runner", "runner_tp"])
            ]
            out["runner_units"] = int(len(runnerish))
            out["runner_net"] = float(runnerish[pnl_col].sum()) if len(runnerish) else 0.0
            med = units[units["exit_reason"].astype(str).str.lower().isin(["target_med", "tp_med"])]
            opn = units[units["exit_reason"].astype(str).str.lower().isin(["target_open", "target"])]
            out["med_units"] = int(len(med))
            out["med_net"] = float(med[pnl_col].sum()) if len(med) else 0.0
            out["open_tp_units"] = int(len(opn))
            out["open_tp_net"] = float(opn[pnl_col].sum()) if len(opn) else 0.0
    return out


def run_variant(
    *,
    output_root: Path,
    market: str = "NQ",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    force: bool = True,
    slippage_ticks: float = 1.0,
) -> Dict[str, float]:
    market = market.upper()
    spec = MARKETS[market]
    tick = float(DEFAULT_TICK_SIZE.get(market, spec.tick))
    pv = float(POINT_VALUES.get(market, spec.point_value))
    POINT_VALUES[market] = pv
    DEFAULT_TICK_SIZE[market] = tick

    strategy_id = "nq_mo_ext_band_max_ohlc_flip_111_r%dm" % int(rolling_window)
    variant_root = output_root / "plus_0p3"
    state_root = variant_root / "states" / strategy_id
    audits_root = variant_root / "audits"
    if force and variant_root.exists():
        shutil.rmtree(variant_root)
    variant_root.mkdir(parents=True, exist_ok=True)

    month_plans = build_month_plans(
        spec,
        entry_mode=ENTRY_MODE,
        sl_mode=SL_MODE,
        rolling_window=rolling_window,
        watch_start_mode="month_open",
    )
    (variant_root / "month_plans.json").write_text(
        json.dumps(month_plans, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    bars_df = load_1h(spec)
    bars = bars_from_1h_df(bars_df, market, "load_1h")
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": sum(LADDER),
        "entry_mode": ENTRY_MODE,
        "sl_mode": SL_MODE,
        "entry_trigger": "first_week_ohlc_flip",
        "rolling_window": int(rolling_window),
        "timeframe": "1h",
        "month_plans": month_plans,
        "suppress_alerts": True,
        "require_trade_through": False,
        "ladder_qtys": list(LADDER),
        "runner_target_r_mult": 0.0,
        "ohlc_run_min_bars": 2,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_open_atr_extension_band",
                    version="v5",
                    instrument=market,
                    broker_instrument=market,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1h",
                    max_contracts=sum(LADDER),
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=True,
        persist_health=False,
        tick_size={market: tick},
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(
            slippage_ticks=slippage_ticks,
            spread_model=_spread(tick),
        ),
    )
    _progress(output_root, "RUN %s bars=%d ladder=%s" % (strategy_id, len(bars), LADDER))
    engine.replay_bars(bars)
    store.flush_tables()

    bar_path = state_root / "bars" / ("%s_1h.csv" % market)
    replay_bars = read_bars(bar_path, "ts") if bar_path.exists() else bars
    units = units_from_live_fills(
        state_root / "fills.csv",
        strategy_id,
        replay_bars[-1].ts if replay_bars else "",
        replay_bars[-1].close if replay_bars else None,
    )
    audit = audit_units(
        name="NQ monthly open OHLC flip 1/1/1",
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=bar_path if bar_path.exists() else Path("load_1h"),
        bars=replay_bars,
        units=units,
        instrument=market,
        notes=(
            "first_week_ohlc_flip; market on flip close; swing SL; ladder 1/1/1 "
            "med/band_max/EOM runner; slip=%g fee=$%.2f" % (slippage_ticks, FEE)
        ),
        output_root=audits_root,
        fee_per_unit=FEE,
    )
    eq_path = audits_root / strategy_id / "equity_curve.csv"
    risk = metrics_from_equity_curve(eq_path) if eq_path.exists() else {}
    profile = _profile_losses(state_root, strategy_id, audits_root)
    (variant_root / "loss_runner_profile.json").write_text(
        json.dumps(profile, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    metrics = {
        "entry_mode": ENTRY_MODE,
        "entry_trigger": "first_week_ohlc_flip",
        "sl_mode": "swing_run",
        "ladder": list(LADDER),
        "strategy_id": strategy_id,
        "state_root": str(state_root),
        "bars": float(len(replay_bars)),
        "units": float(audit.units),
        "trades": float(audit.trades),
        "net_usd": float(audit.net_usd),
        "stress_dd": float(audit.intrabar_mtm_dd_usd),
        "close_dd": float(audit.close_mtm_dd_usd),
        "win_units": float(audit.win_units),
        "loss_units": float(audit.loss_units),
        "ns": (
            float(audit.net_usd) / abs(float(audit.intrabar_mtm_dd_usd))
            if abs(float(audit.intrabar_mtm_dd_usd)) > 1e-9
            else 0.0
        ),
        "sharpe": float(risk.get("sharpe") or 0.0),
        "sortino": float(risk.get("sortino") or 0.0),
        "calmar": float(risk.get("calmar") or 0.0),
        "equity_curve": str(eq_path),
        "profile": profile,
    }
    (variant_root / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE net=%+.0f N/S=%.2f Sharpe=%.2f trades=%d"
        % (metrics["net_usd"], metrics["ns"], metrics["sharpe"], int(metrics["trades"])),
    )
    return metrics


def write_summary(output_root: Path, metrics: Dict[str, float]) -> None:
    profile = dict(metrics.get("profile") or {})
    lines = [
        "# NQ monthly open — first-week 4h OHLC/OLHC flip fade",
        "",
        "Engine + PaperBroker **1h** fills; pattern on **NY 4h** buckets.",
        "",
        "- Entry trigger: ≥2 same-side 4h O&C (liquidity run) then opposite 4h close in **week 1**",
        "- Direction: follow the flip (opposite of the liquidity run)",
        "- Entry: **market** on confirming 4h close",
        "- SL: **swing** of the liquidity run (BE only after main/band-max TP)",
        "- Ladder **1/1/1**: band-med / band-max (trade direction) / runner → EOM",
        "- Band: 6m rolling levels for TPs; slip 1 tick; fee $1.50/unit",
        "",
        "## Results",
        "",
        "| Trades | Units | Net $ | Stress DD $ | N/S | Sharpe | Sortino | Calmar |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %d | %d | %+.0f | %+.0f | %.2f | %.2f | %.2f | %.2f |"
        % (
            int(metrics.get("trades") or 0),
            int(metrics.get("units") or 0),
            float(metrics.get("net_usd") or 0),
            float(metrics.get("stress_dd") or 0),
            float(metrics.get("ns") or 0),
            float(metrics.get("sharpe") or 0),
            float(metrics.get("sortino") or 0),
            float(metrics.get("calmar") or 0),
        ),
        "",
        "## Loss / runner profile",
        "",
        "- Stop units: **%s** (net $%+.0f)"
        % (profile.get("stop_units", "?"), float(profile.get("stop_net") or 0)),
        "- Med TP units: **%s** (net $%+.0f)"
        % (profile.get("med_units", "?"), float(profile.get("med_net") or 0)),
        "- Open TP units: **%s** (net $%+.0f)"
        % (profile.get("open_tp_units", "?"), float(profile.get("open_tp_net") or 0)),
        "- Runner/EOM units: **%s** (net $%+.0f)"
        % (profile.get("runner_units", "?"), float(profile.get("runner_net") or 0)),
        "- Avg win / avg loss (units): $%+.0f / $%+.0f"
        % (float(profile.get("avg_win") or 0), float(profile.get("avg_loss") or 0)),
        "",
        "Vs reclaim baseline (`broker_max_plus_0p3_reclaim`): net +$517k, N/S 1.54 @ qty10 flat.",
        "",
    ]
    by_exit = profile.get("by_exit_reason") or []
    if by_exit:
        lines.extend(["| Exit reason | N | Net $ | Avg $ |", "|---|---:|---:|---:|"])
        for row in by_exit:
            lines.append(
                "| %s | %d | %+.0f | %+.0f |"
                % (
                    row.get("exit_reason"),
                    int(row.get("n") or 0),
                    float(row.get("net") or 0),
                    float(row.get("avg") or 0),
                )
            )
        lines.append("")
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=["trades", "units", "net_usd", "stress_dd", "ns", "sharpe", "sortino", "calmar"],
        )
        w.writeheader()
        w.writerow(
            {
                "trades": int(metrics.get("trades") or 0),
                "units": int(metrics.get("units") or 0),
                "net_usd": float(metrics.get("net_usd") or 0),
                "stress_dd": float(metrics.get("stress_dd") or 0),
                "ns": float(metrics.get("ns") or 0),
                "sharpe": float(metrics.get("sharpe") or 0),
                "sortino": float(metrics.get("sortino") or 0),
                "calmar": float(metrics.get("calmar") or 0),
            }
        )


def run(*, output_root: Path, market: str = "NQ", force: bool = True, email: bool = False) -> int:
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        output_root,
        data_inputs=[MARKETS[market.upper()].csv, MARKETS[market.upper()].source_1h or Path("")],
        strategy_config={
            "strategy_type": "monthly_open_atr_extension_band",
            "entry_mode": ENTRY_MODE,
            "entry_trigger": "first_week_ohlc_flip",
            "ladder_qtys": list(LADDER),
            "sl": "swing_run",
        },
        broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE},
        extra={"dsr_trial_id": DSR},
    )
    try:
        metrics = run_variant(output_root=output_root, market=market, force=False)
        write_summary(output_root, metrics)
        try:
            hub_rel = str(output_root.resolve().relative_to(REPO))
        except ValueError:
            hub_rel = str(output_root)
        log_run(
            run_class="broker_like",
            variant_slug="monthly_open_atr_extension_band_max_ohlc_flip_111_r6m",
            instrument=market.upper(),
            hub_path=hub_rel,
            net_usd=float(metrics["net_usd"]),
            stress_dd_usd=float(metrics["stress_dd"]),
            close_mtm_dd_usd=float(metrics["close_dd"]),
            ns=float(metrics["ns"]),
            trades=int(metrics["trades"]),
            equity_curve_path=Path(str(metrics.get("equity_curve") or "")),
            dsr_trial_id=DSR,
            meta={"ladder": list(LADDER), "entry_trigger": "first_week_ohlc_flip"},
        )
        body = (output_root / "SUMMARY.md").read_text(encoding="utf-8")
        (output_root / "EMAIL.txt").write_text(body, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "metrics": metrics}, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        if email:
            send_email(subject="potions: OHLC flip 1/1/1 complete", body=body)
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(output_root, "FAILED\n" + tb)
        (output_root / "EMAIL.txt").write_text("FAILED\n\n" + tb, encoding="utf-8")
        if email:
            send_email(subject="potions: OHLC flip 1/1/1 FAILED", body=tb[-4000:])
        raise


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--market", default="NQ")
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--no-force", action="store_false", dest="force")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    return run(output_root=args.output_root, market=args.market, force=args.force, email=args.email)


if __name__ == "__main__":
    raise SystemExit(main())
