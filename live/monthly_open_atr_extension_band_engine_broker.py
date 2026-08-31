"""Broker-like Engine+PaperBroker: NQ monthly open extension band fade.

Default hub compares pct75 SL variants on 6-month rolling bands:
  - mean_max   — SL at mean(max)
  - wide_2x    — SL max + 2×(max−entry)
  - wide_2.5x  — SL max + 2.5×(max−entry)

Also supports ``--entry-mode max --sl-modes plus_0.3`` (entry at band max;
SL max + 30% of band width).

Hub: ``live/state/monthly_open_atr_extension_band/broker_pct75_compare/``
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .monthly_atr4_helpers import load_1h
from .monthly_open_atr_extension_band_broker import (
    DEFAULT_ROLLING_BAND_MONTHS,
    ENTRY_QTY,
    _sl_mode_blurb,
    build_month_plans,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import log_run
from .spread_model import SpreadModel
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monthly_open_atr_extension_band" / "broker_pct75_compare"
NY = "America/New_York"
FEE = 1.50
SL_MODES = ("mean_max", "wide_2x", "wide_2.5x")


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


def _sl_slug(sl_mode: str) -> str:
    return str(sl_mode).replace(".", "p").replace("-", "_")


def run_variant(
    *,
    output_root: Path,
    market: str,
    sl_mode: str,
    rolling_window: int,
    force: bool,
    slippage_ticks: float,
    entry_mode: str = "pct75",
    entry_trigger: str = "resting_limit",
) -> Dict[str, float]:
    market = market.upper()
    entry_mode = str(entry_mode).lower()
    entry_trigger = str(entry_trigger or "resting_limit").lower()
    spec = MARKETS[market]
    tick = float(DEFAULT_TICK_SIZE.get(market, spec.tick))
    pv = float(POINT_VALUES.get(market, spec.point_value))
    POINT_VALUES[market] = pv
    DEFAULT_TICK_SIZE[market] = tick

    trigger_slug = "reclaim" if entry_trigger in {"traverse_reclaim", "reclaim", "close_reclaim"} else "limit"
    variant_root = output_root / _sl_slug(sl_mode)
    strategy_id = "nq_mo_ext_band_%s_%s_%s_r%dm" % (
        entry_mode,
        _sl_slug(sl_mode),
        trigger_slug,
        rolling_window,
    )
    state_root = variant_root / "states" / strategy_id
    audits_root = variant_root / "audits"
    if force and variant_root.exists():
        shutil.rmtree(variant_root)
    variant_root.mkdir(parents=True, exist_ok=True)

    month_plans = build_month_plans(
        spec,
        entry_mode=entry_mode,
        sl_mode=sl_mode,
        rolling_window=rolling_window,
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
        "entry_qty": ENTRY_QTY,
        "entry_mode": entry_mode,
        "sl_mode": sl_mode,
        "entry_trigger": entry_trigger,
        "rolling_window": int(rolling_window),
        "timeframe": "1h",
        "month_plans": month_plans,
        "suppress_alerts": True,
        "require_trade_through": entry_trigger == "resting_limit",
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_open_atr_extension_band",
                    version="v4",
                    instrument=market,
                    broker_instrument=market,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1h",
                    max_contracts=ENTRY_QTY,
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
    _progress(
        output_root,
        "RUN %s bars=%d entry=%s sl=%s" % (strategy_id, len(bars), entry_mode, sl_mode),
    )
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
        name="NQ monthly open ext band %s/%s rolling-%dm" % (entry_mode, sl_mode, rolling_window),
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=bar_path if bar_path.exists() else Path("load_1h"),
        bars=replay_bars,
        units=units,
        instrument=market,
        notes=(
            "%s entry on 6m rolling band. sl_mode=%s. "
            "Engine+PaperBroker 1h; slip=%g tick fee=$%.2f/unit."
            % (entry_mode, sl_mode, slippage_ticks, FEE)
        ),
        output_root=audits_root,
        fee_per_unit=FEE,
    )
    eq_path = audits_root / strategy_id / "equity_curve.csv"
    metrics = {
        "entry_mode": entry_mode,
        "entry_trigger": entry_trigger,
        "sl_mode": sl_mode,
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
        "equity_curve": str(eq_path),
    }
    (variant_root / "metrics.json").write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f trades=%d sharpe_path=%s"
        % (sl_mode, metrics["net_usd"], metrics["ns"], int(metrics["trades"]), eq_path),
    )
    return metrics


def _risk_metrics(eq_path: Path) -> Dict[str, float]:
    from .run_ledger import metrics_from_equity_curve

    out = metrics_from_equity_curve(eq_path)
    return {
        "sharpe": float(out.get("sharpe") or 0.0),
        "sortino": float(out.get("sortino") or 0.0),
        "calmar": float(out.get("calmar") or 0.0),
        "parmar": float(out.get("parmar") or out.get("calmar") or 0.0),
    }


def write_compare(
    output_root: Path,
    rows: Sequence[Dict[str, float]],
    rolling_window: int,
    slippage_ticks: float,
    entry_mode: str = "pct75",
    entry_trigger: str = "resting_limit",
) -> None:
    entry_mode = str(entry_mode).lower()
    entry_trigger = str(entry_trigger or "resting_limit").lower()
    enriched: List[Dict[str, float]] = []
    for r in rows:
        eq = Path(str(r.get("equity_curve") or ""))
        risk = _risk_metrics(eq) if eq.exists() else {}
        enriched.append({**r, **risk})

    trigger_blurb = (
        "Entry trigger **traverse_reclaim**: 1h close through band entry, then reverse "
        "and 1h close back in favour (long: close>entry & bullish; short: close<entry & bearish) → market."
        if "reclaim" in entry_trigger
        else "Entry trigger **resting_limit** at band entry."
    )
    lines = [
        "# NQ monthly open extension band — %s broker-like compare" % entry_mode,
        "",
        "Engine + PaperBroker on **1h** bars. Entry **%s**; band **%d-month rolling**."
        % (entry_mode, rolling_window),
        "",
        trigger_blurb,
        "",
    ]
    for r in enriched:
        lines.extend(["", _sl_mode_blurb(entry_mode, str(r["sl_mode"]))])
    lines.extend(
        [
        "",
        f"- Slippage: **{slippage_ticks:g}** tick · fee **${FEE:.2f}**/unit · NQ $20/pt",
        f"- Qty: **{ENTRY_QTY}** per entry · target = month open",
        "",
        "## Risk-adjusted comparison",
        "",
        "| SL mode | Trades | Net $ | Stress DD $ | N/S | Sharpe | Sortino | Calmar |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    email = [
        "potions: NQ %s extension band — broker-like SL compare" % entry_mode,
        "",
        "Hub: %s" % output_root,
        "Band: %d-month rolling · entry %s · Engine+PaperBroker 1h" % (rolling_window, entry_mode),
        "",
    ]
    for r in enriched:
        sm = str(r["sl_mode"])
        lines.append(
            "| %s | %d | %s | %s | %.2f | %.2f | %.2f | %.2f |"
            % (
                sm,
                int(r["trades"]),
                "{:,.0f}".format(r["net_usd"]),
                "{:,.0f}".format(r["stress_dd"]),
                r["ns"],
                r.get("sharpe", 0.0),
                r.get("sortino", 0.0),
                r.get("calmar", 0.0),
            )
        )
        email.append(
            "%s: net=$%s stress=$%s N/S=%.2f Sharpe=%.2f Sortino=%.2f Calmar=%.2f trades=%d"
            % (
                sm,
                "{:,.0f}".format(r["net_usd"]),
                "{:,.0f}".format(abs(r["stress_dd"])),
                r["ns"],
                r.get("sharpe", 0.0),
                r.get("sortino", 0.0),
                r.get("calmar", 0.0),
                int(r["trades"]),
            )
        )

    best_ns = max(enriched, key=lambda x: x["ns"])
    best_sh = max(enriched, key=lambda x: x.get("sharpe", 0.0))
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            "- Best **N/S**: `%s` (%.2f)" % (best_ns["sl_mode"], best_ns["ns"]),
            "- Best **Sharpe**: `%s` (%.2f)" % (best_sh["sl_mode"], best_sh.get("sharpe", 0.0)),
            "",
            "Pandas diagnostic hubs (no spread/slip): `variants/%s/`." % entry_mode,
            "",
        ]
    )
    email.extend(
        [
            "",
            "Best N/S: %s (%.2f)" % (best_ns["sl_mode"], best_ns["ns"]),
            "Best Sharpe: %s (%.2f)" % (best_sh["sl_mode"], best_sh.get("sharpe", 0.0)),
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "sl_mode",
            "trades",
            "units",
            "net_usd",
            "stress_dd",
            "close_dd",
            "ns",
            "sharpe",
            "sortino",
            "calmar",
            "win_units",
            "loss_units",
        ]
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in enriched:
            w.writerow({k: r.get(k, "") for k in fields})
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "variants": [r["sl_mode"] for r in enriched]}, indent=2) + "\n",
        encoding="utf-8",
    )


def _load_existing_metrics(output_root: Path) -> List[Dict[str, float]]:
    rows: List[Dict[str, float]] = []
    if not output_root.exists():
        return rows
    for child in sorted(output_root.iterdir()):
        mj = child / "metrics.json"
        if child.is_dir() and mj.exists():
            try:
                rows.append(json.loads(mj.read_text(encoding="utf-8")))
            except Exception:
                continue
    return rows


def run(
    *,
    output_root: Path,
    market: str = "NQ",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    force: bool = True,
    slippage_ticks: float = 1.0,
    email: bool = False,
    sl_modes: Optional[Sequence[str]] = None,
    entry_mode: str = "pct75",
    entry_trigger: str = "resting_limit",
    dsr_trial_id: Optional[str] = None,
) -> int:
    entry_mode = str(entry_mode).lower()
    entry_trigger = str(entry_trigger or "resting_limit").lower()
    modes = [str(m).strip() for m in (sl_modes or SL_MODES) if str(m).strip()]
    if not modes:
        raise ValueError("sl_modes empty")
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        output_root,
        data_inputs=[MARKETS[market.upper()].csv, MARKETS[market.upper()].source_1h or Path("")],
        strategy_config={
            "strategy_type": "monthly_open_atr_extension_band",
            "entry_mode": entry_mode,
            "entry_trigger": entry_trigger,
            "sl_modes": list(modes),
            "rolling_window": rolling_window,
            "entry_qty": ENTRY_QTY,
        },
        broker_realism_config={"slippage_ticks": slippage_ticks, "fee_per_unit": FEE},
        extra={"notes": "%s / %s SL compare on 6m rolling band" % (entry_mode, entry_trigger)},
    )
    rows: List[Dict[str, float]] = []
    try:
        for sl_mode in modes:
            rows.append(
                run_variant(
                    output_root=output_root,
                    market=market,
                    entry_mode=entry_mode,
                    entry_trigger=entry_trigger,
                    sl_mode=sl_mode,
                    rolling_window=rolling_window,
                    force=False,
                    slippage_ticks=slippage_ticks,
                )
            )
        # Merge prior variants when appending (e.g. --no-force --sl-modes wide_2.5x).
        by_mode = {str(r["sl_mode"]): r for r in _load_existing_metrics(output_root)}
        for r in rows:
            by_mode[str(r["sl_mode"])] = r
        order = list(SL_MODES) + [m for m in by_mode if m not in SL_MODES]
        merged = [by_mode[m] for m in order if m in by_mode]
        write_compare(
            output_root,
            merged,
            rolling_window,
            slippage_ticks,
            entry_mode=entry_mode,
            entry_trigger=entry_trigger,
        )
        for r in rows:
            eq = Path(str(r.get("equity_curve") or ""))
            hub = (output_root / _sl_slug(str(r["sl_mode"]))).resolve()
            try:
                hub_rel = str(hub.relative_to(REPO))
            except ValueError:
                hub_rel = str(hub)
            log_run(
                run_class="broker_like",
                variant_slug="monthly_open_atr_extension_band_%s_%s_%s_r%dm_broker"
                % (
                    entry_mode,
                    _sl_slug(str(r["sl_mode"])),
                    "reclaim" if "reclaim" in entry_trigger else "limit",
                    rolling_window,
                ),
                instrument=market.upper(),
                hub_path=hub_rel,
                net_usd=r["net_usd"],
                stress_dd_usd=r["stress_dd"],
                close_mtm_dd_usd=r["close_dd"],
                ns=r["ns"],
                trades=int(r["trades"]),
                units=int(r["units"]),
                equity_curve_path=eq if eq.exists() else None,
                dsr_trial_id=dsr_trial_id,
                meta={
                    "entry_mode": entry_mode,
                    "entry_trigger": entry_trigger,
                    "sl_mode": r["sl_mode"],
                    "rolling_window": rolling_window,
                },
                notes="monthly_open_atr_extension_band_engine_broker",
            )
        if email:
            send_email(
                subject="potions: NQ %s %s extension band broker-like"
                % (entry_mode, entry_trigger),
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "FAILED\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: %s broker compare FAILED\n\nHub: %s\n\n%s\n" % (entry_mode, output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: %s extension band broker compare FAILED" % entry_mode,
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--market", default="NQ")
    ap.add_argument("--entry-mode", default="pct75", choices=("inner", "mid", "max", "pct75"))
    ap.add_argument(
        "--entry-trigger",
        default="resting_limit",
        choices=("resting_limit", "traverse_reclaim"),
        help="resting_limit=limit at band; traverse_reclaim=close through then reclaim close",
    )
    ap.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    ap.add_argument("--slippage-ticks", type=float, default=1.0)
    ap.add_argument(
        "--sl-modes",
        default=",".join(SL_MODES),
        help="Comma-separated SL modes (default: %s)" % ",".join(SL_MODES),
    )
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--dsr-trial-id", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    modes = [p.strip() for p in str(args.sl_modes).split(",") if p.strip()]
    return run(
        output_root=args.output_root,
        market=str(args.market).upper(),
        entry_mode=str(args.entry_mode),
        entry_trigger=str(args.entry_trigger),
        rolling_window=int(args.rolling_window),
        force=not bool(args.no_force),
        slippage_ticks=float(args.slippage_ticks),
        email=bool(args.email),
        sl_modes=modes,
        dsr_trial_id=args.dsr_trial_id,
    )


if __name__ == "__main__":
    raise SystemExit(main())
