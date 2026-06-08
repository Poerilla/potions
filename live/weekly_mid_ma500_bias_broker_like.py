from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import List, Sequence

import pandas as pd

from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .nq_weekly_mid_ma500_bias_replay import load_15m_for_market
from .replay_audit import AuditResult, audit_units, read_bars, units_from_live_fills
from .store import FlatFileStore
from .v2b_strategy_cross_market_replay import MARKETS


REPO = Path(__file__).resolve().parents[1]
DEFAULT_SLIPPAGE_TICKS = 1.0
DEFAULT_FEE_PER_UNIT = 1.50


def to_bars(df: pd.DataFrame, instrument: str) -> List[Bar]:
    out: List[Bar] = []
    for ts, row in df.iterrows():
        out.append(
            Bar(
                instrument=instrument,
                timeframe="15m",
                ts=str(ts),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0.0),
                complete=True,
                source="weekly_mid_ma500_bias_broker_like",
            )
        )
    return out


def money(value: float) -> str:
    return "$%s" % f"{value:,.2f}"


def ratio(result: AuditResult) -> float:
    return result.net_usd / abs(result.intrabar_mtm_dd_usd) if result.intrabar_mtm_dd_usd else 0.0


def unit_stats(output_root: Path, slug: str) -> tuple[float, float]:
    path = output_root / "audits" / slug / "unit_fills.csv"
    if not path.exists():
        return 0.0, 0.0
    df = pd.read_csv(path)
    if df.empty or "usd" not in df.columns:
        return 0.0, 0.0
    usd = pd.to_numeric(df["usd"], errors="coerce").fillna(0.0)
    win_rate = 100.0 * float((usd > 0).sum()) / float(len(usd)) if len(usd) else 0.0
    gross_win = float(usd[usd > 0].sum())
    gross_loss = -float(usd[usd < 0].sum())
    profit_factor = gross_win / gross_loss if gross_loss else 0.0
    return win_rate, profit_factor


def run_market(
    output_root: Path,
    market_name: str,
    max_trades: int,
    risk_pts: float,
    target_pts: float,
    stop_after_first_win: bool,
    force: bool,
) -> AuditResult:
    cfg = MARKETS[market_name]
    strategy_id = "%s_weekly_mid_ma500_bias" % market_name
    state_root = output_root / "states" / strategy_id
    audits_root = output_root / "audits"
    if state_root.exists() and force:
        shutil.rmtree(state_root)
    state_root.parent.mkdir(parents=True, exist_ok=True)
    audits_root.mkdir(parents=True, exist_ok=True)

    bars_df = load_15m_for_market(market_name, 500)
    bars = to_bars(bars_df, cfg.instrument)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="weekly_mid_ma500_bias",
        version="v1",
        instrument=cfg.instrument,
        broker_instrument=cfg.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="15m",
        max_contracts=1,
        max_open_orders=12,
        config_json=json.dumps(
            {
                "entry_qty": 1,
                "max_trades_per_week": max_trades,
                "risk_pts": risk_pts,
                "target_pts": target_pts,
                "ma_window": 500,
                "record_levels": False,
                "stop_after_weekly_win": stop_after_first_win,
            },
            sort_keys=True,
        ),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=True,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        emit_order_alerts=False,
    )
    print("Replaying %s weekly-mid MA500 bias on %d 15m bars..." % (cfg.instrument, len(bars)), flush=True)
    engine.replay_bars(bars)
    store.flush_tables()

    replay_bars = read_bars(state_root / "bars" / ("%s_15m.csv" % cfg.instrument), "ts")
    units = units_from_live_fills(
        state_root / "fills.csv",
        strategy_id,
        replay_bars[-1].ts,
        replay_bars[-1].close,
    )
    result = audit_units(
        name="%s weekly 50%% + MA500 bias retest (StrategyPlugin)" % cfg.instrument,
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=state_root / "bars" / ("%s_15m.csv" % cfg.instrument),
        bars=replay_bars,
        units=units,
        instrument=cfg.instrument,
        notes=(
            "Broker-like 15m Engine + PaperBroker replay. Previous-week 50%% entry level, "
            "bias from hourly close and 15m MA500 both on same side, one limit unit at midpoint, "
            "target %.1f pts, stop %.1f pts, max %d trades/week, stop after first weekly win=%s. Orders activate only after "
            "the confirming bar closes. Realism: slippage=%g tick(s), fee=$%.2f/unit."
            % (target_pts, risk_pts, max_trades, stop_after_first_win, DEFAULT_SLIPPAGE_TICKS, DEFAULT_FEE_PER_UNIT)
        ),
        output_root=audits_root,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    return result


def write_summary(output_root: Path, rows: Sequence[AuditResult]) -> None:
    csv_rows = []
    lines = [
        "# Weekly 50% + MA500 Bias Retest Broker-Like Replay",
        "",
        "Strict StrategyPlugin replay through Engine + PaperBroker on 15-minute bars. Orders activate only after the confirming bar closes, fills use the broker realism defaults, and any open position is flattened with a market order on the first bar of the next week.",
        "",
        "This is intentionally stricter than the standalone research simulator and should be treated as the hardening result, not a point-for-point reproduction of the research tape.",
        "",
        "| Market | Units | Trades | Net | Closed DD | Intrabar Stress DD | Max Open Units | Win % | PF | Net / Stress | Audit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for result in rows:
        market = result.slug.split("_", 1)[0]
        r = ratio(result)
        win_rate, profit_factor = unit_stats(output_root, result.slug)
        csv_rows.append(
            {
                "market": market,
                "name": result.name,
                "units": result.units,
                "trades": result.trades,
                "net": result.net_usd,
                "closed_dd": result.close_mtm_dd_usd,
                "intrabar_stress_dd": result.intrabar_mtm_dd_usd,
                "max_open_units": result.max_open_units,
                "win_rate": win_rate,
                "profit_factor": profit_factor,
                "net_over_stress": r,
            }
        )
        audit = Path("audits") / result.slug / "reports" / "MTM_AUDIT.md"
        lines.append(
            "| %s | %d | %d | %s | %s | %s | %d | %.1f%% | %.2f | %.2f | [%s](%s) |"
            % (
                market.upper(),
                result.units,
                result.trades,
                money(result.net_usd),
                money(result.close_mtm_dd_usd),
                money(result.intrabar_mtm_dd_usd),
                result.max_open_units,
                win_rate,
                profit_factor,
                r,
                audit,
                audit,
            )
        )
    pd.DataFrame(csv_rows).to_csv(output_root / "summary.csv", index=False)
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def run(
    output_root: Path,
    markets: Sequence[str],
    max_trades: int,
    risk_pts: float,
    target_pts: float,
    stop_after_first_win: bool,
    force: bool,
) -> List[AuditResult]:
    if output_root.exists() and force:
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    results: List[AuditResult] = []
    for market_name in markets:
        results.append(run_market(output_root, market_name, max_trades, risk_pts, target_pts, stop_after_first_win, force=True))
        write_summary(output_root, results)
    write_summary(output_root, results)
    print("Wrote %s" % (output_root / "INDEX.md"), flush=True)
    return results


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Broker-like replay for weekly 50% + MA500 bias strategy.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/weekly_mid_ma500_bias_broker_like")
    parser.add_argument("--market", action="append", choices=sorted(MARKETS), default=None)
    parser.add_argument("--max-trades", type=int, default=6)
    parser.add_argument("--risk-pts", type=float, default=50.0)
    parser.add_argument("--target-pts", type=float, default=300.0)
    parser.add_argument("--stop-after-first-win", action="store_true")
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    run(
        args.output_root,
        args.market or ["nq"],
        args.max_trades,
        args.risk_pts,
        args.target_pts,
        args.stop_after_first_win,
        force=not args.no_force,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
