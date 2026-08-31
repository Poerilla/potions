"""Broker-like: NQ monthly open ext band — wide_2.5x ladders, no week 4, gap-retag.

Ladders (med / month-open / runner; BE stop after open target):
  3/3/3, 6/2/2, 1/1/7, 2/2/5, 2/5/3

Hub: ``live/state/monthly_open_atr_extension_band/broker_pct75_ladder_no_w4/``
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
DEFAULT_OUT = (
    REPO / "live" / "state" / "monthly_open_atr_extension_band" / "broker_pct75_ladder_no_w4"
)
FEE = 1.50
SL_MODE = "wide_2.5x"
LADDERS: Sequence[Tuple[int, int, int]] = (
    (3, 3, 3),
    (6, 2, 2),
    (1, 1, 7),
    (2, 2, 5),
    (2, 5, 3),
)


def _slug(ladder: Tuple[int, int, int]) -> str:
    return "%d_%d_%d" % ladder


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
    ladder: Tuple[int, int, int],
    rolling_window: int,
    slippage_ticks: float,
) -> Dict[str, float]:
    market = market.upper()
    spec = MARKETS[market]
    tick = float(DEFAULT_TICK_SIZE.get(market, spec.tick))
    pv = float(POINT_VALUES.get(market, spec.point_value))
    POINT_VALUES[market] = pv
    DEFAULT_TICK_SIZE[market] = tick

    slug = _slug(ladder)
    variant_root = output_root / ("ladder_%s" % slug)
    strategy_id = "nq_mo_ext_pct75_%s_now4_gap_L%s_r%dm" % (SL_MODE.replace(".", "p"), slug, rolling_window)
    state_root = variant_root / "states" / strategy_id
    audits_root = variant_root / "audits"
    if variant_root.exists():
        shutil.rmtree(variant_root)
    variant_root.mkdir(parents=True, exist_ok=True)

    month_plans = build_month_plans(
        spec,
        entry_mode="pct75",
        sl_mode=SL_MODE,
        rolling_window=rolling_window,
    )
    (variant_root / "month_plans.json").write_text(
        json.dumps(month_plans, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    entry_qty = int(sum(ladder))
    bars_df = load_1h(spec)
    bars = bars_from_1h_df(bars_df, market, "load_1h")
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": tick,
        "entry_qty": entry_qty,
        "entry_mode": "pct75",
        "sl_mode": SL_MODE,
        "rolling_window": int(rolling_window),
        "timeframe": "1h",
        "month_plans": month_plans,
        "suppress_alerts": True,
        "skip_entry_weeks": [4],
        "ladder_qtys": list(ladder),
        "require_trade_through": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="monthly_open_atr_extension_band",
                    version="v2",
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
    _progress(output_root, "RUN %s ladder=%s bars=%d" % (strategy_id, slug, len(bars)))
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
        name="NQ mo-ext pct75/%s ladder %s no-w4 gap-retag" % (SL_MODE, slug),
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=bar_path if bar_path.exists() else Path("load_1h"),
        bars=replay_bars,
        units=units,
        instrument=market,
        notes=(
            "pct75 wide_2.5x; skip week 4; gap-void+retag; ladder med/open/runner=%s; "
            "BE after open target. slip=%g fee=$%.2f"
            % (slug, slippage_ticks, FEE)
        ),
        output_root=audits_root,
        fee_per_unit=FEE,
    )
    eq_path = audits_root / strategy_id / "equity_curve.csv"
    ns = (
        float(audit.net_usd) / abs(float(audit.intrabar_mtm_dd_usd))
        if abs(float(audit.intrabar_mtm_dd_usd)) > 1e-9
        else 0.0
    )
    metrics = {
        "ladder": slug,
        "ladder_qtys": list(ladder),
        "entry_qty": float(entry_qty),
        "strategy_id": strategy_id,
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
        "DONE %s net=%+.0f N/S=%.2f trades=%d" % (slug, metrics["net_usd"], ns, int(metrics["trades"])),
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


def write_compare(output_root: Path, rows: Sequence[Dict], rolling_window: int, slippage_ticks: float) -> None:
    enriched = []
    for r in rows:
        eq = Path(str(r.get("equity_curve") or ""))
        risk = _risk_metrics(eq) if eq.exists() else {}
        # size-normalize to 10-lot for fair $ compare across ladders
        total = float(r.get("entry_qty") or 10.0) or 10.0
        scale = 10.0 / total
        enriched.append(
            {
                **r,
                **risk,
                "net_norm10": float(r["net_usd"]) * scale,
                "stress_norm10": float(r["stress_dd"]) * scale,
                "ns_norm10": (
                    (float(r["net_usd"]) * scale) / abs(float(r["stress_dd"]) * scale)
                    if abs(float(r["stress_dd"])) > 1e-9
                    else 0.0
                ),
            }
        )

    lines = [
        "# NQ monthly open ext band — ladder compare (no week 4, gap-retag)",
        "",
        "Engine + PaperBroker **1h**. Entry **pct75**; SL **wide_2.5x**; band **%d-mo rolling**."
        % rolling_window,
        "",
        _sl_mode_blurb("pct75", SL_MODE),
        "",
        "- **Skip entry weeks:** 4",
        "- **Gap rule:** void limit fill if prior close is on the approach side and bar opens through "
        "the entry; re-arm only after price re-tags the level.",
        "- Ladder: N@band-med / N@month-open / N runner; runner SL → **BE** only after open target.",
        f"- Slippage **{slippage_ticks:g}** tick · fee **${FEE:.2f}**/unit · NQ $20/pt",
        "",
        "## Risk-adjusted comparison",
        "",
        "| Ladder | Qty | Trades | Net $ | Net@10 | Stress $ | N/S | N/S@10 | Sharpe | Calmar |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "potions: NQ mo-ext ladder compare (no week 4, gap-retag)",
        "",
        "Hub: %s" % output_root,
        "DSR: TRL-2026-00124",
        "",
    ]
    for r in enriched:
        lines.append(
            "| %s | %d | %d | %s | %s | %s | %.2f | %.2f | %.2f | %.2f |"
            % (
                r["ladder"],
                int(r["entry_qty"]),
                int(r["trades"]),
                "{:,.0f}".format(r["net_usd"]),
                "{:,.0f}".format(r["net_norm10"]),
                "{:,.0f}".format(r["stress_dd"]),
                r["ns"],
                r["ns_norm10"],
                r.get("sharpe", 0.0),
                r.get("calmar", 0.0),
            )
        )
        email.append(
            "%s (qty %d): net=$%s norm10=$%s N/S=%.2f Sharpe=%.2f trades=%d"
            % (
                r["ladder"],
                int(r["entry_qty"]),
                "{:,.0f}".format(r["net_usd"]),
                "{:,.0f}".format(r["net_norm10"]),
                r["ns"],
                r.get("sharpe", 0.0),
                int(r["trades"]),
            )
        )

    best_ns = max(enriched, key=lambda x: x["ns_norm10"])
    best_net = max(enriched, key=lambda x: x["net_norm10"])
    lines.extend(
        [
            "",
            "## Verdict",
            "",
            "- Best **N/S@10**: `%s` (%.2f)" % (best_ns["ladder"], best_ns["ns_norm10"]),
            "- Best **net@10**: `%s` ($%s)" % (best_net["ladder"], "{:,.0f}".format(best_net["net_norm10"])),
            "",
            "Stance: research — compare ladders under gap-retag + no week 4 before promote.",
            "",
        ]
    )
    email.extend(
        [
            "",
            "Best N/S@10: %s (%.2f)" % (best_ns["ladder"], best_ns["ns_norm10"]),
            "Best net@10: %s ($%s)" % (best_net["ladder"], "{:,.0f}".format(best_net["net_norm10"])),
            "Stance: research.",
        ]
    )
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
        fields = [
            "ladder",
            "entry_qty",
            "trades",
            "units",
            "net_usd",
            "net_norm10",
            "stress_dd",
            "stress_norm10",
            "ns",
            "ns_norm10",
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
        json.dumps({"ok": True, "ladders": [r["ladder"] for r in enriched], "dsr": "TRL-2026-00124"}, indent=2)
        + "\n",
        encoding="utf-8",
    )


def run(
    *,
    output_root: Path,
    market: str = "NQ",
    rolling_window: int = DEFAULT_ROLLING_BAND_MONTHS,
    force: bool = True,
    slippage_ticks: float = 1.0,
    email: bool = False,
    ladders: Optional[Sequence[Tuple[int, int, int]]] = None,
) -> int:
    ladder_list = list(ladders or LADDERS)
    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    write_run_manifest(
        output_root,
        data_inputs=[MARKETS[market.upper()].csv, MARKETS[market.upper()].source_1h or Path("")],
        strategy_config={
            "strategy_type": "monthly_open_atr_extension_band",
            "entry_mode": "pct75",
            "sl_mode": SL_MODE,
            "skip_entry_weeks": [4],
            "require_trade_through": True,
            "ladders": ["%d/%d/%d" % x for x in ladder_list],
            "rolling_window": rolling_window,
            "dsr_trial_id": "TRL-2026-00124",
        },
        broker_realism_config={"slippage_ticks": slippage_ticks, "fee_per_unit": FEE},
        extra={"notes": "ladder compare no week 4 + gap retag"},
    )
    rows: List[Dict] = []
    try:
        for ladder in ladder_list:
            rows.append(
                run_variant(
                    output_root=output_root,
                    market=market,
                    ladder=ladder,
                    rolling_window=rolling_window,
                    slippage_ticks=slippage_ticks,
                )
            )
        write_compare(output_root, rows, rolling_window, slippage_ticks)
        for r in rows:
            eq = Path(str(r.get("equity_curve") or ""))
            hub = (output_root / ("ladder_%s" % r["ladder"])).resolve()
            try:
                hub_rel = str(hub.relative_to(REPO))
            except ValueError:
                hub_rel = str(hub)
            log_run(
                run_class="broker_like",
                variant_slug="mo_ext_pct75_%s_now4_gap_L%s" % (SL_MODE, r["ladder"]),
                instrument=market.upper(),
                hub_path=hub_rel,
                net_usd=r["net_usd"],
                stress_dd_usd=r["stress_dd"],
                close_mtm_dd_usd=r["close_dd"],
                ns=r["ns"],
                trades=int(r["trades"]),
                units=int(r["units"]),
                equity_curve_path=eq if eq.exists() else None,
                dsr_trial_id="TRL-2026-00124",
                meta={
                    "ladder": r["ladder"],
                    "skip_entry_weeks": [4],
                    "require_trade_through": True,
                    "sl_mode": SL_MODE,
                },
                notes="monthly_open_atr_extension_band_ladder_broker",
            )
        if email:
            send_email(
                subject="potions: NQ mo-ext ladder compare (no week 4, gap-retag)",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "FAILED\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: ladder compare FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ mo-ext ladder compare FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--market", default="NQ")
    ap.add_argument("--rolling-window", type=int, default=DEFAULT_ROLLING_BAND_MONTHS)
    ap.add_argument("--slippage-ticks", type=float, default=1.0)
    ap.add_argument(
        "--ladders",
        default=",".join("%d/%d/%d" % x for x in LADDERS),
        help="Comma-separated ladders like 3/3/3,6/2/2",
    )
    ap.add_argument("--no-force", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    ladders = []
    for part in str(args.ladders).split(","):
        part = part.strip()
        if not part:
            continue
        a, b, c = [int(x) for x in part.replace("-", "/").split("/")]
        ladders.append((a, b, c))
    return run(
        output_root=args.output_root,
        market=str(args.market).upper(),
        rolling_window=int(args.rolling_window),
        force=not bool(args.no_force),
        slippage_ticks=float(args.slippage_ticks),
        email=bool(args.email),
        ladders=ladders,
    )


if __name__ == "__main__":
    raise SystemExit(main())
