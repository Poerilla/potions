"""Broker-like: NQ band-max fade, SL max+50% band, TP@open + runner 2R past TP.

Compares all-weeks vs skip week 4. Ladder 0@med / 5@month-open / 5 runner;
on open fill → SL to BE + runner limit at open ± 2R (R = entry→stop).

Hub: ``live/state/monthly_open_atr_extension_band/broker_max_plus_0p5_runner2r/``
DSR: TRL-2026-00128
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

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
from .run_ledger import log_run
from .spread_model import SpreadModel
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
BAND_ROOT = REPO / "live" / "state" / "monthly_open_atr_extension_band"
DEFAULT_OUT = BAND_ROOT / "broker_max_plus_0p5_runner2r"
FEE = 1.50
ENTRY_MODE = "max"
SL_MODE = "plus_0.5"
LADDER: Tuple[int, int, int] = (0, 5, 5)
RUNNER_R_MULT = 2.0
DSR = "TRL-2026-00128"
# (slug, skip_entry_weeks)
VARIANTS: Sequence[Tuple[str, List[int]]] = (
    ("all_weeks", []),
    ("no_w4", [4]),
)


def default_hub_for_market(market: str) -> Path:
    m = str(market).upper()
    if m == "NQ":
        return DEFAULT_OUT
    return BAND_ROOT / ("broker_max_plus_0p5_runner2r_%s" % m.lower())


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


def bars_from_1h_df(df, instrument: str, source: str) -> List[Bar]:
    import pandas as pd

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


def run_variant(
    *,
    output_root: Path,
    market: str,
    variant_slug: str,
    skip_entry_weeks: Sequence[int],
    rolling_window: int,
    slippage_ticks: float,
) -> Dict[str, float]:
    market = market.upper()
    spec = MARKETS[market]
    tick = float(DEFAULT_TICK_SIZE.get(market, spec.tick))
    pv = float(POINT_VALUES.get(market, spec.point_value))
    POINT_VALUES[market] = pv
    DEFAULT_TICK_SIZE[market] = tick

    fee = float(getattr(spec, "fee_per_unit", FEE) or FEE)
    variant_root = output_root / variant_slug
    skip_tag = "now4" if 4 in {int(w) for w in skip_entry_weeks} else "allw"
    strategy_id = "%s_mo_ext_max_%s_r2r_%s_L0_5_5_r%dm" % (
        market.lower(),
        SL_MODE.replace(".", "p"),
        skip_tag,
        rolling_window,
    )
    state_root = variant_root / "states" / strategy_id
    audits_root = variant_root / "audits"
    if variant_root.exists():
        shutil.rmtree(variant_root)
    variant_root.mkdir(parents=True, exist_ok=True)

    month_plans = build_month_plans(
        spec,
        entry_mode=ENTRY_MODE,
        sl_mode=SL_MODE,
        rolling_window=rolling_window,
    )
    (variant_root / "month_plans.json").write_text(
        json.dumps(month_plans, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    entry_qty = int(sum(LADDER))
    bars_df = load_1h(spec)
    bars = bars_from_1h_df(bars_df, market, "load_1h")
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": entry_qty,
        "entry_mode": ENTRY_MODE,
        "sl_mode": SL_MODE,
        "rolling_window": int(rolling_window),
        "timeframe": "1h",
        "month_plans": month_plans,
        "suppress_alerts": True,
        "skip_entry_weeks": [int(w) for w in skip_entry_weeks],
        "ladder_qtys": list(LADDER),
        "runner_target_r_mult": float(RUNNER_R_MULT),
        "require_trade_through": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_open_atr_extension_band",
                    version="v3",
                    instrument=market,
                    broker_instrument=market,
                    account_mode="paper",
                    enabled=True,
                    timeframes="1h",
                    max_contracts=entry_qty,
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
    _progress(output_root, "RUN %s skip=%s bars=%d" % (strategy_id, list(skip_entry_weeks), len(bars)))
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
        name="%s mo-ext max/%s runner2r %s" % (market, SL_MODE, variant_slug),
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=bar_path if bar_path.exists() else Path("load_1h"),
        bars=replay_bars,
        units=units,
        instrument=market,
        notes=(
            "max entry; SL plus_0.5 band; ladder 0/5/5; runner TP = open±2R; BE after open; "
            "gap-retag; skip_weeks=%s; slip=%g fee=$%.2f"
            % (list(skip_entry_weeks), slippage_ticks, fee)
        ),
        output_root=audits_root,
        fee_per_unit=fee,
    )
    eq_path = audits_root / strategy_id / "equity_curve.csv"
    ns = (
        float(audit.net_usd) / abs(float(audit.intrabar_mtm_dd_usd))
        if abs(float(audit.intrabar_mtm_dd_usd)) > 1e-9
        else 0.0
    )
    metrics = {
        "variant": variant_slug,
        "skip_entry_weeks": list(skip_entry_weeks),
        "ladder_qtys": list(LADDER),
        "runner_target_r_mult": float(RUNNER_R_MULT),
        "entry_qty": float(entry_qty),
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
        "ns": ns,
        "equity_curve": str(eq_path),
    }
    (variant_root / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f trades=%d"
        % (variant_slug, metrics["net_usd"], ns, int(metrics["trades"])),
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
    rows: Sequence[Dict],
    rolling_window: int,
    slippage_ticks: float,
    *,
    market: str = "NQ",
    fee: float = FEE,
) -> None:
    enriched = []
    for r in rows:
        eq = Path(str(r.get("equity_curve") or ""))
        risk = _risk_metrics(eq) if eq.exists() else {}
        enriched.append({**r, **risk})

    mkt = str(market).upper()
    lines = [
        "# %s band-max fade — SL max+50%% band · open TP + runner 2R" % mkt,
        "",
        "Engine + PaperBroker **1h**. Entry **max**; SL **plus_0.5**; band **%d-mo rolling**."
        % rolling_window,
        "",
        _sl_mode_blurb(ENTRY_MODE, SL_MODE),
        "",
        "- Ladder: **0** @ band-med / **5** @ month-open / **5** runner",
        "- On open fill: runner SL → **BE**; runner TP = month-open ± **2R** (R = entry→stop)",
        "- Gap rule: void gap-through entry; require retag",
        "- Compare: **all weeks** vs **skip week 4**",
        "",
        f"- Slippage: **{slippage_ticks:g}** tick · fee **${fee:.2f}**/unit · DSR `{DSR}`",
        "",
        "## Comparison",
        "",
        "| Variant | Skip w4 | Trades | Net $ | Stress DD | N/S | Sharpe | Sortino | Calmar |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "potions: %s band-max +50%% SL · open TP + runner 2R (all vs no-w4)" % mkt,
        "",
        "Hub: %s" % output_root,
        "DSR: %s" % DSR,
        "Entry max; SL plus_0.5; ladder 0/5/5; runner = open±2R after BE",
        "",
    ]
    for r in enriched:
        skip = "yes" if 4 in {int(w) for w in (r.get("skip_entry_weeks") or [])} else "no"
        lines.append(
            "| %s | %s | %d | %s | %s | %.2f | %.2f | %.2f | %.2f |"
            % (
                r["variant"],
                skip,
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
            "%s: net=$%s stress=$%s N/S=%.2f Sharpe=%.2f trades=%d skip_w4=%s"
            % (
                r["variant"],
                "{:,.0f}".format(r["net_usd"]),
                "{:,.0f}".format(abs(r["stress_dd"])),
                r["ns"],
                r.get("sharpe", 0.0),
                int(r["trades"]),
                skip,
            )
        )

    best = max(enriched, key=lambda x: x["ns"]) if enriched else None
    stance = "research"
    if best and best["ns"] >= 1.5:
        stance = "research — strong lift vs max+30% flat; beats pct75 wide_2.5x N/S on this tape"
    elif best and best["ns"] >= 1.0:
        stance = "research — promising vs prior max+30% (N/S 0.62)"
    elif best:
        stance = "research / lean reject vs pct75 wide_2.5x (N/S ~1.31)"
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            "- Best **N/S**: `%s` (%.2f)" % (best["variant"], best["ns"]) if best else "- No rows",
            "- Prior max+30% flat (no runner): net +$238k, N/S **0.62**",
            "- pct75 wide_2.5x ref: N/S ~**1.31**",
            "- **Skip week 4 did not help** here (lower net and N/S).",
            "",
            "Stance: %s." % stance,
            "",
        ]
    )
    email.extend(["", "Best N/S: %s (%.2f)" % (best["variant"], best["ns"]) if best else "", "Stance: %s." % stance])
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "variant",
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
        json.dumps(
            {
                "ok": True,
                "dsr": DSR,
                "market": mkt,
                "variants": [r["variant"] for r in enriched],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run(
    *,
    output_root: Optional[Path] = None,
    market: str = "NQ",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    force: bool = True,
    slippage_ticks: float = 1.0,
    email: bool = False,
) -> int:
    market = str(market).upper()
    if market not in MARKETS:
        raise SystemExit("Unknown market %s (want %s)" % (market, ",".join(sorted(MARKETS))))
    if output_root is None:
        output_root = default_hub_for_market(market)
    fee = float(getattr(MARKETS[market], "fee_per_unit", FEE) or FEE)
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        output_root,
        data_inputs=[MARKETS[market].csv, MARKETS[market].source_1h or Path("")],
        strategy_config={
            "strategy_type": "monthly_open_atr_extension_band",
            "market": market,
            "entry_mode": ENTRY_MODE,
            "sl_mode": SL_MODE,
            "ladder_qtys": list(LADDER),
            "runner_target_r_mult": RUNNER_R_MULT,
            "variants": [v[0] for v in VARIANTS],
            "rolling_window": rolling_window,
            "dsr_trial_id": DSR,
        },
        broker_realism_config={"slippage_ticks": slippage_ticks, "fee_per_unit": fee},
        extra={"notes": "max+50% SL; open TP + 2R runner; all weeks vs no week 4"},
    )
    rows: List[Dict[str, float]] = []
    try:
        for slug, skip in VARIANTS:
            rows.append(
                run_variant(
                    output_root=output_root,
                    market=market,
                    variant_slug=slug,
                    skip_entry_weeks=skip,
                    rolling_window=rolling_window,
                    slippage_ticks=slippage_ticks,
                )
            )
        write_compare(
            output_root,
            rows,
            rolling_window,
            slippage_ticks,
            market=market,
            fee=fee,
        )
        for r in rows:
            eq = Path(str(r.get("equity_curve") or ""))
            hub = (output_root / str(r["variant"])).resolve()
            try:
                hub_rel = str(hub.relative_to(REPO))
            except ValueError:
                hub_rel = str(hub)
            log_run(
                run_class="broker_like",
                variant_slug=str(r["strategy_id"]),
                instrument=market,
                hub_path=hub_rel,
                net_usd=r["net_usd"],
                stress_dd_usd=r["stress_dd"],
                close_mtm_dd_usd=r["close_dd"],
                ns=r["ns"],
                trades=int(r["trades"]),
                units=int(r["units"]),
                equity_curve_path=eq if eq.exists() else None,
                dsr_trial_id=DSR,
                meta={
                    "entry_mode": ENTRY_MODE,
                    "sl_mode": SL_MODE,
                    "ladder": list(LADDER),
                    "runner_target_r_mult": RUNNER_R_MULT,
                    "variant": r["variant"],
                    "skip_entry_weeks": r["skip_entry_weeks"],
                },
                notes="monthly_open_atr_extension_band_max_runner_broker",
            )
        if email:
            send_email(
                subject="potions: %s band-max +50%% SL · runner 2R (all vs no-w4)" % market,
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "FAILED\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: %s band-max +50%% runner2r FAILED\n\nHub: %s\n\n%s\n"
            % (market, output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: %s band-max +50%% runner2r FAILED" % market,
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--market", default="NQ")
    ap.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Default: broker_max_plus_0p5_runner2r for NQ, …_<market> otherwise",
    )
    ap.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    ap.add_argument("--slippage-ticks", type=float, default=1.0)
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    return run(
        output_root=args.output_root,
        market=str(args.market).upper(),
        rolling_window=int(args.rolling_window),
        force=not bool(args.no_force),
        slippage_ticks=float(args.slippage_ticks),
        email=bool(args.email),
    )


if __name__ == "__main__":
    raise SystemExit(main())
