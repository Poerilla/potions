from __future__ import annotations

import argparse
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .execution_scrutiny import classify_execution_row
from .nq_v2b_prior_opposed_replay import DEFAULT_ST_STRATEGY_IDS, PRIOR_OPPOSED_MARKETS, default_st_fills_path
from .nq_v2b_prior_opposed_robustness_audit import max_drawdown, profit_factor, stop_slippage_audit
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .v2b_st_pmc_alignment_study import REPO
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


NY = "America/New_York"
FEE_PER_UNIT = 1.50
LATENCY_SCENARIOS = (0.2, 0.5, 1.0, 5.0, 15.0)


@dataclass(frozen=True)
class ScrutinyConfig:
    market: str
    instrument: str
    strategy_id: str
    state_root: Path
    st_fills: Path
    st_strategy_id: str
    output_dir: Path
    prior_trade_filter: Optional[Path] = None
    prior_trade_filter_regime: str = "not_aligned_prior_opposed"
    strict_plugin_gate: bool = True


def default_configs(output_root: Path) -> Dict[str, ScrutinyConfig]:
    configs: Dict[str, ScrutinyConfig] = {}
    for market in PRIOR_OPPOSED_MARKETS:
        instrument = MARKETS[market].instrument
        strategy_id = f"{market}_v2b_prior_opposed_stpmc_only_S_1_1_3"
        configs[market] = ScrutinyConfig(
            market=market,
            instrument=instrument,
            strategy_id=strategy_id,
            state_root=REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/states/{strategy_id}",
            st_fills=default_st_fills_path(market),
            st_strategy_id=DEFAULT_ST_STRATEGY_IDS[market],
            output_dir=output_root / market,
            strict_plugin_gate=True,
        )
    return configs


def money(value: float) -> str:
    return "$%s%.2f" % ("-" if value < 0 else "", abs(value))


def load_prior_trade_ids(path: Optional[Path], regime: str) -> Optional[set[str]]:
    if path is None:
        return None
    df = pd.read_csv(path)
    if "regime" not in df.columns or "trade_id" not in df.columns:
        raise ValueError("Prior trade filter must contain regime and trade_id: %s" % path)
    return set(df[df["regime"].astype(str) == regime]["trade_id"].astype(str))


def load_st_events(path: Path, strategy_id: str) -> pd.DataFrame:
    fills = pd.read_csv(path)
    fills = fills[fills["strategy_id"].astype(str) == strategy_id].copy()
    fills = fills[fills["reason"].astype(str).isin(["entry", "runner_entry"])].copy()
    if fills.empty:
        return pd.DataFrame(columns=["session", "stpmc_entry_time", "stpmc_side", "stpmc_trade_id"])
    fills["stpmc_entry_time"] = _to_ny(fills["ts"])
    fills["stpmc_side"] = fills["side"].astype(str).str.lower().map(lambda side: "long" if side == "buy" else "short")
    fills["session"] = fills["stpmc_entry_time"].dt.date.astype(str)
    fills["stpmc_trade_id"] = fills["trade_id"].astype(str)
    return fills[["session", "stpmc_entry_time", "stpmc_side", "stpmc_trade_id"]].sort_values("stpmc_entry_time")


def load_campaigns(cfg: ScrutinyConfig) -> pd.DataFrame:
    fills = pd.read_csv(cfg.state_root / "fills.csv")
    orders = pd.read_csv(cfg.state_root / "orders.csv")
    fills["ts"] = _to_ny(fills["ts"])
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(0).astype(int)
    orders["live_after_ts"] = orders["live_after_ts"].astype(str)
    orders["stop_price"] = pd.to_numeric(orders["stop_price"], errors="coerce")
    prior_ids = load_prior_trade_ids(cfg.prior_trade_filter, cfg.prior_trade_filter_regime)
    rows = []
    point_value = POINT_VALUES[cfg.instrument]
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        trade_id = str(trade_id)
        if prior_ids is not None and trade_id not in prior_ids:
            continue
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty:
            continue
        entry = entries.iloc[0]
        entry_order_rows = orders[orders["broker_order_id"].astype(str) == str(entry["broker_order_id"])]
        if entry_order_rows.empty:
            continue
        entry_order = entry_order_rows.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        net = 0.0
        exit_reasons: List[str] = []
        for _idx, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            exit_px = float(exit_row["price"])
            pts = exit_px - entry_px if side == "long" else entry_px - exit_px
            net += pts * point_value * qty - FEE_PER_UNIT * qty
            exit_reasons.append(str(exit_row["reason"]))
        entry_ts = pd.Timestamp(entry["ts"])
        session = entry_ts.date().isoformat()
        rows.append(
            {
                "campaign_id": trade_id,
                "date": session,
                "side": side,
                "entry_ts": entry_ts,
                "exit_ts": pd.Timestamp(exits["ts"].max()) if not exits.empty else pd.NaT,
                "entry_price": entry_px,
                "entry_qty": int(entry["quantity"]),
                "v2b_order_active_time": _parse_market_ts(str(entry_order["live_after_ts"]), session),
                "v2b_order_creation_time": _parse_market_ts(str(entry_order["live_after_ts"]), session),
                "v2b_order_created_at_wallclock": str(entry_order.get("created_at", "")),
                "stop_price": float(entry_order["stop_price"]),
                "net": net,
                "exit_type": ",".join(sorted(set(exit_reasons))),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def load_market_bars(market: str) -> Dict[date, pd.DataFrame]:
    cfg = MARKETS[market]
    return load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)


def add_timing_fields(campaigns: pd.DataFrame, cfg: ScrutinyConfig, bars_by_day: Dict[date, pd.DataFrame], st_events: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for row in campaigns.itertuples(index=False):
        session_date = date.fromisoformat(str(row.date))
        active_ts = pd.Timestamp(row.v2b_order_active_time)
        rth = _rth_bars(bars_by_day.get(session_date), session_date)
        or_done = _session_ts(str(row.date), "09:44")
        or_end = _session_ts(str(row.date), "09:45")
        first_touch = pd.NaT
        pre_arm_touch = pd.NaT
        post_fill_trigger_touch = pd.NaT
        post_fill_level_retest = pd.NaT
        mae = math.nan
        if not rth.empty:
            after_active = rth[rth.index > active_ts]
            pre_arm = rth[(rth.index >= or_end) & (rth.index <= active_ts)]
            after_entry = rth[rth.index > pd.Timestamp(row.entry_ts)]
            if pd.notna(row.exit_ts):
                after_entry = after_entry[after_entry.index <= pd.Timestamp(row.exit_ts)]
            if row.side == "long":
                first_touch = _first_cross(after_active, "high", float(row.stop_price), above=True)
                pre_arm_touch = _first_cross(pre_arm, "high", float(row.stop_price), above=True)
                post_fill_trigger_touch = _first_cross(after_entry, "high", float(row.stop_price), above=True)
            else:
                first_touch = _first_cross(after_active, "low", float(row.stop_price), above=False)
                pre_arm_touch = _first_cross(pre_arm, "low", float(row.stop_price), above=False)
                post_fill_trigger_touch = _first_cross(after_entry, "low", float(row.stop_price), above=False)
            post_fill_level_retest = _first_level_span(after_entry, float(row.stop_price))
            if pd.notna(row.exit_ts):
                window = rth[(rth.index >= row.entry_ts) & (rth.index <= row.exit_ts)]
                if not window.empty:
                    qty = int(row.entry_qty)
                    if row.side == "long":
                        adverse_pts = min(0.0, float(window["low"].min()) - float(row.entry_price))
                    else:
                        adverse_pts = min(0.0, float(row.entry_price) - float(window["high"].max()))
                    mae = adverse_pts * POINT_VALUES[cfg.instrument] * qty
        if pd.isna(first_touch):
            first_touch = pd.Timestamp(row.entry_ts)
        available_seconds = (pd.Timestamp(first_touch) - active_ts).total_seconds()
        latency_risk = _latency_risk(available_seconds, pre_arm_touch)
        st_match = _latest_prior_stpmc(st_events, str(row.date), row.side, active_ts)
        rows.append(
            {
                "campaign_id": row.campaign_id,
                "v2b_or_completion_time": or_done,
                "v2b_or_end_time": or_end,
                "first_breakout_touch_time": first_touch,
                "pre_arm_touch_time": pre_arm_touch,
                "time_available_before_touch_seconds": available_seconds,
                "time_available_before_touch": _format_seconds(available_seconds),
                "latency_bucket": _latency_bucket(available_seconds),
                "latency_risk": latency_risk,
                "post_fill_trigger_touch_time": post_fill_trigger_touch,
                "post_fill_trigger_touch_after_seconds": _seconds_after(row.entry_ts, post_fill_trigger_touch),
                "post_fill_level_retest_time": post_fill_level_retest,
                "post_fill_level_retest_after_seconds": _seconds_after(row.entry_ts, post_fill_level_retest),
                "post_fill_level_retest_before_exit": pd.notna(post_fill_level_retest),
                "late_fill_estimate_1m": _late_fill_estimate(
                    latency_risk,
                    pd.notna(post_fill_level_retest),
                    pd.notna(post_fill_trigger_touch),
                ),
                "mae": mae,
                "stpmc_entry_time": st_match.get("stpmc_entry_time", pd.NaT),
                "stpmc_side": st_match.get("stpmc_side", ""),
                "stpmc_trade_id": st_match.get("stpmc_trade_id", ""),
                "opposite_gate_known_before_v2b": bool(st_match),
                "opposite_gate_recognition_time": active_ts if st_match else pd.NaT,
                "same_minute_gate_to_v2b": bool(st_match)
                and (active_ts - pd.Timestamp(st_match["stpmc_entry_time"])).total_seconds() <= 60.0,
                "pre_arm_breakout_touch": pd.notna(pre_arm_touch),
            }
        )
    timing = campaigns.merge(pd.DataFrame(rows), on="campaign_id", how="left")
    for delay in LATENCY_SCENARIOS:
        col = _delay_col(delay)
        timing[col] = timing.apply(
            lambda item: _delay_classification(
                float(item["time_available_before_touch_seconds"]),
                _coerce_notna(item["pre_arm_touch_time"]),
                delay,
            ),
            axis=1,
        )
    return timing


def summarize_latency(timing: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for key, group in timing.groupby("latency_risk", dropna=False):
        pnl = pd.to_numeric(group["net"], errors="coerce").fillna(0.0)
        dd = max_drawdown(pnl.cumsum())
        rows.append(
            {
                "latency_risk": str(key),
                "campaigns": len(group),
                "net_usd": pnl.sum(),
                "win_rate_pct": 100.0 * float((pnl > 0).mean()) if len(group) else 0.0,
                "profit_factor": profit_factor(pnl),
                "closed_dd_usd": dd,
                "net_over_closed_dd": pnl.sum() / abs(dd) if dd else 0.0,
            }
        )
    return pd.DataFrame(rows).sort_values("latency_risk")


def summarize_delays(timing: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for delay in LATENCY_SCENARIOS:
        col = _delay_col(delay)
        for key, group in timing.groupby(col, dropna=False):
            pnl = pd.to_numeric(group["net"], errors="coerce").fillna(0.0)
            rows.append(
                {
                    "delay_seconds": delay,
                    "classification": str(key),
                    "campaigns": len(group),
                    "net_usd": pnl.sum(),
                    "win_rate_pct": 100.0 * float((pnl > 0).mean()) if len(group) else 0.0,
                    "profit_factor": profit_factor(pnl),
                }
            )
    return pd.DataFrame(rows).sort_values(["delay_seconds", "classification"])


def summarize_late_fill_estimates(timing: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for risk, risk_group in timing.groupby("latency_risk", dropna=False):
        for estimate, group in risk_group.groupby("late_fill_estimate_1m", dropna=False):
            pnl = pd.to_numeric(group["net"], errors="coerce").fillna(0.0)
            rows.append(
                {
                    "latency_risk": str(risk),
                    "late_fill_estimate_1m": str(estimate),
                    "campaigns": len(group),
                    "net_usd": pnl.sum(),
                    "win_rate_pct": 100.0 * float((pnl > 0).mean()) if len(group) else 0.0,
                    "profit_factor": profit_factor(pnl),
                }
            )
    return pd.DataFrame(rows).sort_values(["latency_risk", "late_fill_estimate_1m"])


def build_tick_manifest(timing: pd.DataFrame, stop_slippage: pd.DataFrame) -> pd.DataFrame:
    selected: Dict[str, set[str]] = {}

    def add(reason: str, trade_ids: Iterable[str]) -> None:
        for trade_id in trade_ids:
            selected.setdefault(str(trade_id), set()).add(reason)

    add("latency_not_bar_safe", timing[timing["latency_risk"].astype(str) != "safe"]["campaign_id"])
    add("same_minute_gate_to_v2b", timing[timing["same_minute_gate_to_v2b"].astype(bool)]["campaign_id"])
    add("top_20_winner", timing.sort_values("net", ascending=False).head(20)["campaign_id"])
    add("worst_20_loser", timing.sort_values("net", ascending=True).head(20)["campaign_id"])
    if not stop_slippage.empty and "gap_beyond_1tick_usd" in stop_slippage.columns:
        gap = stop_slippage.copy()
        gap["gap_beyond_1tick_usd"] = pd.to_numeric(gap["gap_beyond_1tick_usd"], errors="coerce").fillna(0.0)
        trade_col = "trade_id_fill" if "trade_id_fill" in gap.columns else "trade_id"
        add("top_gap_through_stop_cost", gap.sort_values("gap_beyond_1tick_usd", ascending=False).head(20)[trade_col])
    rows = []
    timing_by_trade = timing.set_index("campaign_id")
    for trade_id, reasons in sorted(selected.items()):
        if trade_id not in timing_by_trade.index:
            continue
        row = timing_by_trade.loc[trade_id]
        rows.append(
            {
                "campaign_id": trade_id,
                "date": row["date"],
                "side": row["side"],
                "entry_ts": row["entry_ts"],
                "net": row["net"],
                "latency_risk": row["latency_risk"],
                "time_available_before_touch_seconds": row["time_available_before_touch_seconds"],
                "manifest_reasons": ",".join(sorted(reasons)),
                "tick_data_status": "required_not_available_in_bar_replay",
            }
        )
    return pd.DataFrame(rows).sort_values(["date", "campaign_id"])


def write_market_report(
    cfg: ScrutinyConfig,
    timing: pd.DataFrame,
    latency: pd.DataFrame,
    delays: pd.DataFrame,
    retests: pd.DataFrame,
    manifest: pd.DataFrame,
) -> None:
    cfg.output_dir.mkdir(parents=True, exist_ok=True)
    timing_out = timing.copy()
    timing_out["scrutiny_classification"] = timing_out.apply(lambda row: classify_execution_row(row.to_dict()), axis=1)
    for col in timing_out.columns:
        if pd.api.types.is_datetime64_any_dtype(timing_out[col]):
            timing_out[col] = timing_out[col].astype(str)
    timing_out.to_csv(cfg.output_dir / "historical_timing_report.csv", index=False)
    scrutiny_cols = [
        col
        for col in [
            "campaign_id",
            "date",
            "side",
            "entry_ts",
            "v2b_order_active_time",
            "first_breakout_touch_time",
            "latency_risk",
            "scrutiny_classification",
            "pre_arm_breakout_touch",
            "late_fill_estimate_1m",
            "post_fill_level_retest_before_exit",
            "opposite_gate_known_before_v2b",
            "net",
        ]
        if col in timing_out.columns
    ]
    timing_out[scrutiny_cols].to_csv(cfg.output_dir / "execution_scrutiny.csv", index=False)
    latency.to_csv(cfg.output_dir / "latency_summary.csv", index=False)
    delays.to_csv(cfg.output_dir / "delay_sensitivity_summary.csv", index=False)
    retests.to_csv(cfg.output_dir / "retest_summary.csv", index=False)
    manifest.to_csv(cfg.output_dir / "tick_replay_manifest.csv", index=False)

    pnl = pd.to_numeric(timing["net"], errors="coerce").fillna(0.0)
    violations = int((~timing["opposite_gate_known_before_v2b"].astype(bool)).sum())
    ambiguous = int((timing["latency_risk"].astype(str) == "ambiguous_same_1m_bar").sum())
    pre_arm = int((timing["latency_risk"].astype(str) == "pre_arm_breakout_touch").sum())
    safe = int((timing["latency_risk"].astype(str) == "safe").sum())
    not_safe = timing[timing["latency_risk"].astype(str) != "safe"]
    later_retest = int((not_safe["late_fill_estimate_1m"].astype(str) == "later_level_retest").sum())
    trigger_only = int((not_safe["late_fill_estimate_1m"].astype(str) == "later_trigger_touch_only").sum())
    no_later_touch = int((not_safe["late_fill_estimate_1m"].astype(str) == "no_later_touch_in_1m").sum())
    classification_counts = timing_out["scrutiny_classification"].value_counts().to_dict()
    lines = [
        "# %s Prior-Opposed ST+PMC v2b Execution Scrutiny" % cfg.instrument,
        "",
        "Rules are frozen. This audit looks for timing, causality, latency, and live-readiness problems; it does not optimize the strategy.",
        "",
        "| Campaigns | Net | Win % | PF | Causal violations | Bar-safe | Ambiguous <=1m | Pre-arm touch | Later level retest | Trigger-only later touch | No later 1m touch | Tick manifest |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        "| %d | %s | %.2f | %.3f | %d | %d | %d | %d | %d | %d | %d | %d |"
        % (
            len(timing),
            money(float(pnl.sum())),
            100.0 * float((pnl > 0).mean()) if len(timing) else 0.0,
            profit_factor(pnl),
            violations,
            safe,
            ambiguous,
            pre_arm,
            later_retest,
            trigger_only,
            no_later_touch,
            len(manifest),
        ),
        "",
        "Classification: **%s OK / %s NEEDS_TICK / %s VIOLATION_RISK**."
        % (
            classification_counts.get("OK", 0),
            classification_counts.get("NEEDS_TICK", 0),
            classification_counts.get("VIOLATION_RISK", 0),
        ),
        "",
        "## Read",
        "",
    ]
    if violations:
        lines.append("- Causal issue: %d campaigns did not find a prior opposite ST+PMC entry in the source fill book." % violations)
    else:
        lines.append("- Causality check passed at the fill-book level: every campaign found a prior opposite ST+PMC entry.")
    if ambiguous or pre_arm:
        lines.append("- Latency is not fully answered by 1m bars: %d campaigns are same-minute ambiguous and %d show the breakout level touched before the v2b gate/order was active." % (ambiguous, pre_arm))
        lines.append("- Coarse retest estimate: among the %d not-bar-safe campaigns, %d later span the entry level again on 1m bars, %d later touch only the trigger side, and %d show no later 1m touch before exit." % (len(not_safe), later_retest, trigger_only, no_later_touch))
    else:
        lines.append("- All campaigns are bar-safe by the current coarse 1m timing rule.")
    if cfg.strict_plugin_gate:
        lines.append("- This market is a strict StrategyPlugin delayed-arming replay.")
    else:
        lines.append("- This market is a research-tape mirror, not a strict delayed-arming plugin replay; use it as small-contract timing context.")
    lines.extend(
        [
            "",
            "## Files",
            "",
            "- `historical_timing_report.csv`",
            "- `execution_scrutiny.csv`",
            "- `latency_summary.csv`",
            "- `delay_sensitivity_summary.csv`",
            "- `retest_summary.csv`",
            "- `tick_replay_manifest.csv`",
        ]
    )
    (cfg.output_dir / "SCRUTINY_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (cfg.output_dir / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_market(cfg: ScrutinyConfig) -> pd.DataFrame:
    print("Scrutinizing %s..." % cfg.instrument, flush=True)
    campaigns = load_campaigns(cfg)
    st_events = load_st_events(cfg.st_fills, cfg.st_strategy_id)
    bars_by_day = load_market_bars(cfg.market)
    timing = add_timing_fields(campaigns, cfg, bars_by_day, st_events)
    latency = summarize_latency(timing)
    delays = summarize_delays(timing)
    retests = summarize_late_fill_estimates(timing)
    slippage = stop_slippage_audit(
        cfg.state_root / "fills.csv",
        cfg.state_root / "orders.csv",
        POINT_VALUES[cfg.instrument],
        DEFAULT_TICK_SIZE.get(cfg.instrument.upper(), 0.25),
    )
    manifest = build_tick_manifest(timing, slippage)
    write_market_report(cfg, timing, latency, delays, retests, manifest)
    return timing


def write_root_report(output_root: Path, market_rows: Dict[str, pd.DataFrame]) -> None:
    for market in PRIOR_OPPOSED_MARKETS:
        if market in market_rows:
            continue
        existing = output_root / market / "historical_timing_report.csv"
        if existing.exists():
            market_rows[market] = pd.read_csv(existing)
    rows = []
    ordered_markets = [market for market in PRIOR_OPPOSED_MARKETS if market in market_rows]
    for market in ordered_markets:
        timing = market_rows[market]
        if "scrutiny_classification" not in timing.columns:
            timing = timing.copy()
            timing["scrutiny_classification"] = timing.apply(lambda row: classify_execution_row(row.to_dict()), axis=1)
        pnl = pd.to_numeric(timing["net"], errors="coerce").fillna(0.0)
        classification_counts = timing["scrutiny_classification"].value_counts().to_dict()
        rows.append(
            {
                "market": market.upper(),
                "campaigns": len(timing),
                "net_usd": float(pnl.sum()),
                "win_rate_pct": 100.0 * float((pnl > 0).mean()) if len(timing) else 0.0,
                "profit_factor": profit_factor(pnl),
                "causal_violations": int((~timing["opposite_gate_known_before_v2b"].astype(bool)).sum()),
                "safe": int((timing["latency_risk"].astype(str) == "safe").sum()),
                "ambiguous_same_1m_bar": int((timing["latency_risk"].astype(str) == "ambiguous_same_1m_bar").sum()),
                "pre_arm_breakout_touch": int((timing["latency_risk"].astype(str) == "pre_arm_breakout_touch").sum()),
                "scrutiny_ok": int(classification_counts.get("OK", 0)),
                "scrutiny_needs_tick": int(classification_counts.get("NEEDS_TICK", 0)),
                "scrutiny_violation_risk": int(classification_counts.get("VIOLATION_RISK", 0)),
                "later_level_retest": int(
                    (
                        (timing["latency_risk"].astype(str) != "safe")
                        & (timing["late_fill_estimate_1m"].astype(str) == "later_level_retest")
                    ).sum()
                ),
                "later_trigger_touch_only": int(
                    (
                        (timing["latency_risk"].astype(str) != "safe")
                        & (timing["late_fill_estimate_1m"].astype(str) == "later_trigger_touch_only")
                    ).sum()
                ),
                "no_later_touch_in_1m": int(
                    (
                        (timing["latency_risk"].astype(str) != "safe")
                        & (timing["late_fill_estimate_1m"].astype(str) == "no_later_touch_in_1m")
                    ).sum()
                ),
            }
        )
    summary = pd.DataFrame(rows)
    output_root.mkdir(parents=True, exist_ok=True)
    summary.to_csv(output_root / "summary.csv", index=False)
    lines = [
        "# v2b Prior-Opposed ST+PMC Execution Scrutiny",
        "",
        "This is an execution and live-readiness audit only. Strategy rules and sizing are frozen.",
        "",
        "| Market | Campaigns | Net | Win % | PF | Causal violations | Bar-safe | Ambiguous <=1m | Pre-arm touch | Later level retest | Trigger-only later touch | No later 1m touch |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            "| {market} | {campaigns} | {net} | {wr:.2f} | {pf:.3f} | {viol} | {safe} | {amb} | {pre} | {retest} | {trigger} | {miss} |".format(
                market=row["market"],
                campaigns=row["campaigns"],
                net=money(row["net_usd"]),
                wr=row["win_rate_pct"],
                pf=row["profit_factor"],
                viol=row["causal_violations"],
                safe=row["safe"],
                amb=row["ambiguous_same_1m_bar"],
                pre=row["pre_arm_breakout_touch"],
                retest=row["later_level_retest"],
                trigger=row["later_trigger_touch_only"],
                miss=row["no_later_touch_in_1m"],
            )
        )
    if rows:
        lines.extend(
            [
                "",
                "## Standardized Scrutiny Classification",
                "",
                "| Market | OK | NEEDS_TICK | VIOLATION_RISK | Tick-critical % |",
                "|---|---:|---:|---:|---:|",
            ]
        )
        for row in rows:
            tick_critical = row["scrutiny_needs_tick"] + row["scrutiny_violation_risk"]
            pct = 100.0 * tick_critical / row["campaigns"] if row["campaigns"] else 0.0
            lines.append(
                "| {market} | {ok} | {needs} | {risk} | {pct:.1f}% |".format(
                    market=row["market"],
                    ok=row["scrutiny_ok"],
                    needs=row["scrutiny_needs_tick"],
                    risk=row["scrutiny_violation_risk"],
                    pct=pct,
                )
            )
    lines.extend(
        [
            "",
            "Important: 1m bars cannot prove 200ms execution safety. The retest columns are coarse estimates only: `later_level_retest` means a later 1m bar spans the entry level before exit; `later_trigger_touch_only` means the trigger side appears again but the exact level is not proven; `no_later_touch_in_1m` is the rough completely-missed bucket. Campaigns in `ambiguous_same_1m_bar` and `pre_arm_breakout_touch` are still routed to each market's `tick_replay_manifest.csv` for Databento/broker tick reconstruction.",
            "",
            "ES/YM/MYM use the same strict delayed-arming plugin gate and were replayed on full-RTH sessions only after the first YM/MYM pass exposed two early-close / holiday entries with no normal 15:55 flatten. The cleaned ES/YM/MYM fill books have zero entry-without-exit campaigns.",
            "",
        ]
    )
    for market in PRIOR_OPPOSED_MARKETS:
        if (output_root / market / "SCRUTINY_REPORT.md").exists():
            lines.append("- %s: [`%s/SCRUTINY_REPORT.md`](%s/SCRUTINY_REPORT.md)" % (market.upper(), market, market))
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    output_paths = [output_root / "summary.csv", output_root / "INDEX.md"]
    for market in PRIOR_OPPOSED_MARKETS:
        output_paths.extend(
            [
                output_root / market / "execution_scrutiny.csv",
                output_root / market / "historical_timing_report.csv",
                output_root / market / "tick_replay_manifest.csv",
            ]
        )
    write_run_manifest(
        output_root,
        output_paths=output_paths,
        strategy_config={"driver": "v2b_prior_opposed_execution_scrutiny", "markets": PRIOR_OPPOSED_MARKETS},
        causality_mode="audit",
        extra={"scrutiny_schema": "OK_NEEDS_TICK_VIOLATION_RISK"},
    )


def _latest_prior_stpmc(st_events: pd.DataFrame, session: str, v2b_side: str, active_ts: pd.Timestamp) -> Dict[str, object]:
    if st_events.empty:
        return {}
    wanted = "short" if v2b_side == "long" else "long"
    candidates = st_events[
        (st_events["session"].astype(str) == str(session))
        & (st_events["stpmc_side"].astype(str) == wanted)
        & (st_events["stpmc_entry_time"] < active_ts)
    ]
    if candidates.empty:
        return {}
    row = candidates.iloc[-1]
    return {
        "stpmc_entry_time": pd.Timestamp(row["stpmc_entry_time"]),
        "stpmc_side": str(row["stpmc_side"]),
        "stpmc_trade_id": str(row["stpmc_trade_id"]),
    }


def _first_cross(df: pd.DataFrame, col: str, level: float, above: bool) -> pd.Timestamp:
    if df.empty:
        return pd.NaT
    values = pd.to_numeric(df[col], errors="coerce")
    crossed = values >= level if above else values <= level
    if not crossed.any():
        return pd.NaT
    return pd.Timestamp(df.index[crossed.argmax()])


def _first_level_span(df: pd.DataFrame, level: float) -> pd.Timestamp:
    if df.empty:
        return pd.NaT
    highs = pd.to_numeric(df["high"], errors="coerce")
    lows = pd.to_numeric(df["low"], errors="coerce")
    spanned = (lows <= level) & (highs >= level)
    if not spanned.any():
        return pd.NaT
    return pd.Timestamp(df.index[spanned.argmax()])


def _seconds_after(start: object, end: object) -> float:
    if not _coerce_notna(end):
        return math.nan
    return (pd.Timestamp(end) - pd.Timestamp(start)).total_seconds()


def _late_fill_estimate(latency_risk: str, level_retest: bool, trigger_touch: bool) -> str:
    if str(latency_risk) == "safe":
        return "bar_safe"
    if level_retest:
        return "later_level_retest"
    if trigger_touch:
        return "later_trigger_touch_only"
    return "no_later_touch_in_1m"


def _latency_bucket(seconds: float) -> str:
    if seconds <= 0:
        return "zero_or_negative"
    if seconds <= 60:
        return "same_1m_bar"
    if seconds <= 300:
        return "1_to_5m"
    if seconds <= 1800:
        return "5_to_30m"
    return "over_30m"


def _latency_risk(seconds: float, pre_arm_touch: object) -> str:
    if _coerce_notna(pre_arm_touch):
        return "pre_arm_breakout_touch"
    if seconds <= 0:
        return "late_miss"
    if seconds <= 60:
        return "ambiguous_same_1m_bar"
    return "safe"


def _delay_classification(seconds: float, pre_arm_touch: bool, delay_seconds: float) -> str:
    if pre_arm_touch:
        return "pre_arm_breakout_touch"
    if seconds <= 0:
        return "late_miss"
    if seconds <= 60:
        return "ambiguous_same_1m_bar"
    if delay_seconds >= seconds:
        return "late_miss"
    if seconds - delay_seconds <= 60:
        return "ambiguous_after_delay"
    return "safe"


def _delay_col(delay: float) -> str:
    if delay < 1.0:
        return "delay_%dms" % int(round(delay * 1000.0))
    return "delay_%ss" % str(delay).replace(".", "_")


def _format_seconds(seconds: float) -> str:
    if math.isnan(seconds):
        return ""
    return "%.3fs" % seconds


def _coerce_notna(value: object) -> bool:
    try:
        return bool(pd.notna(value))
    except TypeError:
        return False


def _to_ny(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, utc=True).dt.tz_convert(NY)


def _parse_market_ts(value: str, session: str) -> pd.Timestamp:
    if not value or value == "nan":
        return pd.NaT
    text = str(value)
    if len(text) == 10:
        text = "%sT00:00:00-05:00" % text
    ts = pd.Timestamp(text)
    if ts.tzinfo is None:
        ts = ts.tz_localize(NY)
    return ts.tz_convert(NY)


def _session_ts(session: str, hhmm: str) -> pd.Timestamp:
    return pd.Timestamp("%sT%s:00" % (session, hhmm)).tz_localize(NY)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Audit timing and live-readiness risks for prior-opposed ST+PMC v2b.")
    parser.add_argument("--output-root", type=Path, default=REPO / "live/state/v2b_prior_opposed_execution_scrutiny")
    parser.add_argument("--markets", nargs="+", choices=PRIOR_OPPOSED_MARKETS, default=["nq", "mnq"])
    args = parser.parse_args(argv)
    configs = default_configs(args.output_root)
    market_rows: Dict[str, pd.DataFrame] = {}
    for market in args.markets:
        market_rows[market] = run_market(configs[market])
    write_root_report(args.output_root, market_rows)
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
