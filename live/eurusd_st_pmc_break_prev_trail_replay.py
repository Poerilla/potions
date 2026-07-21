"""EURUSD research: PMC break → limit at prior opposite ST trail, 3R, London/NY only.

Same MA bull-prior gate as promoted ``sl25_tp75_3r_ma_bull_prior``, but entry/stop
geometry comes from SuperTrend trails (not fixed 25/75 pips).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .engine import Engine
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_retest_replay import (
    DEFAULT_FEE_PER_UNIT,
    DEFAULT_SLIPPAGE_TICKS,
    read_bars_from_engine_bars,
)
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .replay_audit import audit_units, units_from_live_fills
from .store import FlatFileStore
from .strategies.hourly_st_pmc_break_prev_trail import session_bucket
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly


REPO = Path(__file__).resolve().parents[1]
INSTRUMENT = "EURUSD"
MARKET = "eurusd"
PIP = 0.0001
TICK = 0.00001
POINT_VALUE = 100_000.0
STRATEGY_ID = "eurusd_hourly_st_pmc_break_prev_trail_pmc_only_3r"
DEFAULT_OUT = REPO / "live" / "state" / "eurusd_st_pmc_break_prev_trail"


def _load_hourly_bars(one_m_path: Path) -> List[Bar]:
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    hourly_df = resample_hourly(concat_all_1m(bars_by_day))
    out: List[Bar] = []
    for ts, row in hourly_df.iterrows():
        out.append(
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
                source=str(one_m_path),
            )
        )
    return out


def _config_json(daily_path: Path) -> str:
    return json.dumps(
        {
            "daily_bars_path": str(daily_path),
            "tick_size": TICK,
            "entry_qty": 1,
            "tp1_qty": 1,
            "runner_qty": 0,
            "ma_filter": "none",
            "reward_R": 3.0,
            "min_r_pts": 5 * PIP,
            "session_gate": True,
            "close_against_entry_exit": False,
            "st_flip_exit": False,
            "pmc_cross_exit": False,
            "atr_len": 14,
            "atr_mult": 3.0,
        },
        sort_keys=True,
    )


def _campaign_rows(fills_path: Path) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    if fills.empty:
        return pd.DataFrame()
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1.0)
    rows = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g["reason"] == "entry"]
        exits = g[g["reason"].isin(["stop", "target", "eod", "flatten", "close"])]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        exit_ = exits.iloc[-1]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        exit_px = float(exit_["price"])
        qty = float(entry["quantity"])
        if side == "long":
            pnl_pts = (exit_px - entry_px) * qty
        else:
            pnl_pts = (entry_px - exit_px) * qty
        pnl_usd = pnl_pts * POINT_VALUE - DEFAULT_FEE_PER_UNIT * qty
        exit_reason = str(exit_["reason"]).lower()
        win = exit_reason == "target" or (exit_reason not in {"stop"} and pnl_usd > 0)
        if exit_reason == "stop":
            win = False
        if exit_reason == "target":
            win = True
        sess = session_bucket(str(entry["ts"]))
        rows.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": entry["ts"],
                "exit_ts": exit_["ts"],
                "entry": entry_px,
                "exit": exit_px,
                "pnl_usd": pnl_usd,
                "exit_reason": exit_reason,
                "win": bool(win),
                "session": sess,
            }
        )
    return pd.DataFrame(rows)


def _session_stats(trades: pd.DataFrame) -> Dict[str, Dict[str, float]]:
    out: Dict[str, Dict[str, float]] = {}
    if trades.empty:
        return out
    for sess, g in trades.groupby("session"):
        n = len(g)
        wins = int(g["win"].sum())
        out[str(sess)] = {
            "trades": n,
            "wins": wins,
            "losses": n - wins,
            "win_rate_pct": 100.0 * wins / n if n else 0.0,
            "net_usd": float(g["pnl_usd"].sum()),
            "avg_pnl_usd": float(g["pnl_usd"].mean()) if n else 0.0,
            "profit_factor": float(
                g.loc[g["pnl_usd"] > 0, "pnl_usd"].sum()
                / abs(g.loc[g["pnl_usd"] < 0, "pnl_usd"].sum())
            )
            if (g["pnl_usd"] < 0).any() and (g["pnl_usd"] > 0).any()
            else (float("inf") if (g["pnl_usd"] > 0).any() else 0.0),
        }
    return out


def write_summary(
    *,
    out: Path,
    audit,
    trades: pd.DataFrame,
    sess: Dict[str, Dict[str, float]],
    state_root: Path,
) -> None:
    lines = [
        "# EURUSD — PMC break + prior opposite ST trail (3R)",
        "",
        "Plugin: `hourly_st_pmc_break_prev_trail`",
        "",
        "## Rules",
        "",
        "- Hourly ATR SuperTrend 14×3; prior-month close bias only (**no MA filter**).",
        "- **Long:** hourly close > PMC and ST bullish → buy **limit at last bearish ST trail**; "
        "SL at current bullish ST; TP = entry + **3R**.",
        "- **Short:** hourly close < PMC and ST bearish → sell limit at last bullish ST trail; "
        "SL at current bearish ST; TP = entry − 3R.",
        "- Entries only **London 08:00 → NY 15:00** (arming window); 15:00 NY hour cancels "
        "resting limits. Open risk can finish outside the window.",
        "- Fee $1.50/unit, PV $100k, 1-tick stop slip (Engine + PaperBroker).",
        "",
        "## Headline",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Campaigns | {len(trades)} |",
        f"| Units (audit) | {audit.units} |",
        f"| Net | ${audit.net_usd:,.2f} |",
        f"| Stress DD | ${audit.intrabar_mtm_dd_usd:,.2f} |",
        f"| Net/Stress | {audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0:.2f} |",
        f"| Win % | {100.0 * trades['win'].mean() if len(trades) else 0:.1f} |",
        "",
        "## Session consistency (by entry fill time)",
        "",
        "| Session | Trades | Wins | Win % | Net | Avg PnL | PF |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in ("london", "ny", "off"):
        s = sess.get(name)
        if not s:
            continue
        pf = s["profit_factor"]
        pf_s = "inf" if pf == float("inf") else f"{pf:.2f}"
        lines.append(
            f"| **{name}** | {s['trades']:.0f} | {s['wins']:.0f} | {s['win_rate_pct']:.1f}% | "
            f"${s['net_usd']:,.0f} | ${s['avg_pnl_usd']:,.0f} | {pf_s} |"
        )
    if sess:
        # Most consistent = highest win rate among london/ny with enough trades
        ranked = sorted(
            [(k, v) for k, v in sess.items() if k in {"london", "ny"} and v["trades"] >= 20],
            key=lambda kv: (kv[1]["win_rate_pct"], kv[1]["net_usd"]),
            reverse=True,
        )
        if ranked:
            best, st = ranked[0]
            lines.extend(
                [
                    "",
                    f"**Most consistent session (win rate, ≥20 trades):** **{best}** "
                    f"({st['win_rate_pct']:.1f}% WR, ${st['net_usd']:,.0f} net).",
                ]
            )
    lines.extend(
        [
            "",
            f"State: `{state_root}`",
            f"Trades CSV: `{out / 'trades_by_session.csv'}`",
            f"Session JSON: `{out / 'session_stats.json'}`",
            "",
        ]
    )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--force", action="store_true", default=True)
    parser.add_argument("--no-force", action="store_true")
    args = parser.parse_args(argv)
    force = bool(args.force) and not bool(args.no_force)

    one_m_path, daily_path = ensure_eurusd_platform_files(REPO)
    print("Loading EURUSD hourly bars...", flush=True)
    bars = _load_hourly_bars(one_m_path)
    print(f"  {len(bars):,} hourly bars", flush=True)

    out = args.output_root
    out.mkdir(parents=True, exist_ok=True)
    state_root = out / "states" / STRATEGY_ID
    if force and state_root.exists():
        shutil.rmtree(state_root)

    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    instance = StrategyInstance(
        strategy_id=STRATEGY_ID,
        strategy_type="hourly_st_pmc_break_prev_trail",
        version="v1",
        instrument=INSTRUMENT,
        broker_instrument=INSTRUMENT,
        account_mode="paper",
        enabled=True,
        timeframes="1h",
        max_contracts=1,
        max_open_orders=16,
        config_json=_config_json(daily_path),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=DEFAULT_SLIPPAGE_TICKS,
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
    )
    print("Replaying...", flush=True)
    for idx, bar in enumerate(bars, start=1):
        engine.process_bar(bar)
        if idx % 20000 == 0:
            print(f"  {idx}/{len(bars)}", flush=True)
    if hasattr(engine.broker, "flush_state"):
        engine.broker.flush_state()
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(fills_path, STRATEGY_ID)
    audit = audit_units(
        name="EURUSD PMC break prev ST trail 3R MA-bull",
        slug=STRATEGY_ID,
        source=fills_path,
        bar_source=one_m_path,
        bars=read_bars_from_engine_bars(list(bars)),
        units=units,
        instrument=INSTRUMENT,
        notes="Break-prev-trail variant; London/NY session gate; fee $1.50.",
        output_root=out / "audits" / STRATEGY_ID,
        fee_per_unit=DEFAULT_FEE_PER_UNIT,
    )
    trades = _campaign_rows(fills_path)
    if not trades.empty:
        trades.to_csv(out / "trades_by_session.csv", index=False)
    sess = _session_stats(trades)
    (out / "session_stats.json").write_text(json.dumps(sess, indent=2), encoding="utf-8")
    write_summary(out=out, audit=audit, trades=trades, sess=sess, state_root=state_root)

    # summary.csv for quick compare
    with (out / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(
            fh,
            fieldnames=[
                "strategy_id",
                "trades",
                "net_usd",
                "stress_dd_usd",
                "net_over_stress",
                "win_rate_pct",
                "london_wr",
                "ny_wr",
                "london_net",
                "ny_net",
            ],
        )
        w.writeheader()
        w.writerow(
            {
                "strategy_id": STRATEGY_ID,
                "trades": len(trades),
                "net_usd": round(audit.net_usd, 2),
                "stress_dd_usd": round(audit.intrabar_mtm_dd_usd, 2),
                "net_over_stress": round(
                    audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0,
                    2,
                ),
                "win_rate_pct": round(100.0 * float(trades["win"].mean()) if len(trades) else 0.0, 2),
                "london_wr": round(sess.get("london", {}).get("win_rate_pct", 0.0), 2),
                "ny_wr": round(sess.get("ny", {}).get("win_rate_pct", 0.0), 2),
                "london_net": round(sess.get("london", {}).get("net_usd", 0.0), 2),
                "ny_net": round(sess.get("ny", {}).get("net_usd", 0.0), 2),
            }
        )

    print(f"Net ${audit.net_usd:,.2f} / stress ${audit.intrabar_mtm_dd_usd:,.2f} / n={len(trades)}")
    print(f"Session stats: {json.dumps(sess, indent=2)}")
    print(f"SUMMARY → {out / 'SUMMARY.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
