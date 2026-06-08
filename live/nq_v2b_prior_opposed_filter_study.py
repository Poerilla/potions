from __future__ import annotations

import argparse
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pandas as pd

from .nq_v2b_prior_opposed_replay import PRIOR_OPPOSED_MARKETS

REPO = Path(__file__).resolve().parents[1]


def money(value: float) -> str:
    return "$%s%.2f" % ("-" if value < 0 else "", abs(value))


def max_drawdown(values: pd.Series) -> float:
    if values.empty:
        return 0.0
    return float((values - values.cummax()).min())


def profit_factor(values: pd.Series) -> float:
    gains = float(values[values > 0].sum())
    losses = abs(float(values[values < 0].sum()))
    if losses == 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def scenario_equity(rows: pd.DataFrame) -> Dict[str, float]:
    close_eq = 0.0
    close_peak = 0.0
    stress_peak = 0.0
    closed_dd = 0.0
    stress_dd = 0.0
    for row in rows.itertuples(index=False):
        stress_eq = close_eq + float(row.scenario_mae_usd)
        stress_peak = max(stress_peak, close_peak)
        stress_dd = min(stress_dd, stress_eq - stress_peak)
        close_eq += float(row.scenario_net_usd)
        close_peak = max(close_peak, close_eq)
        closed_dd = min(closed_dd, close_eq - close_peak)
    return {
        "net_usd": close_eq,
        "closed_dd_usd": closed_dd,
        "stress_dd_usd": stress_dd,
    }


def build_trade_unit_matrix(campaigns: pd.DataFrame, unit_trades: pd.DataFrame) -> pd.DataFrame:
    unit_trades = unit_trades.copy()
    unit_trades["unit_id"] = pd.to_numeric(unit_trades["unit_id"], errors="coerce").fillna(0).astype(int)
    unit_trades["net_usd"] = pd.to_numeric(unit_trades["net_usd"], errors="coerce").fillna(0.0)
    rows = []
    for trade_id, group in unit_trades.groupby("trade_id"):
        group = group.sort_values("unit_id")
        group = group.assign(campaign_unit_rank=range(1, len(group) + 1))
        rows.append(
            {
                "trade_id": trade_id,
                "net_1_1_3": float(group["net_usd"].sum()),
                "net_1_1_1": float(group[group["campaign_unit_rank"] <= 3]["net_usd"].sum()),
                "net_1_1_0": float(group[group["campaign_unit_rank"] <= 2]["net_usd"].sum()),
                "qty_1_1_3": int(len(group)),
                "qty_1_1_1": int((group["campaign_unit_rank"] <= 3).sum()),
                "qty_1_1_0": int((group["campaign_unit_rank"] <= 2).sum()),
            }
        )
    matrix = pd.DataFrame(rows)
    out = campaigns.merge(matrix, on="trade_id", how="left")
    for col in ["net_1_1_3", "net_1_1_1", "net_1_1_0", "qty_1_1_3", "qty_1_1_1", "qty_1_1_0"]:
        out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0.0)
    return out


def apply_scenario(
    base: pd.DataFrame,
    name: str,
    sizing_rule: Callable[[pd.Series], str],
    execute_rule: Optional[Callable[[pd.Series], bool]] = None,
) -> Dict[str, object]:
    rows = []
    for _idx, row in base.iterrows():
        execute = True if execute_rule is None else bool(execute_rule(row))
        if not execute:
            continue
        sizing = sizing_rule(row)
        net_col = "net_%s" % sizing
        qty_col = "qty_%s" % sizing
        base_qty = float(row.get("qty_1_1_3", 5.0)) or 5.0
        qty = float(row.get(qty_col, 0.0))
        scale = qty / base_qty if base_qty else 0.0
        rows.append(
            {
                "trade_id": row["trade_id"],
                "entry_ts": row["entry_ts"],
                "session": row["session"],
                "year": row["year"],
                "sizing": sizing,
                "scenario_net_usd": float(row[net_col]),
                "scenario_mae_usd": float(row["campaign_mae_usd"]) * scale,
                "or_width_quartile": row.get("or_width_quartile", ""),
                "gap_quartile": row.get("gap_quartile", ""),
                "atr14_quartile": row.get("atr14_quartile", ""),
            }
        )
    df = pd.DataFrame(rows).sort_values("entry_ts") if rows else pd.DataFrame()
    if df.empty:
        return {
            "scenario": name,
            "trades": 0,
            "net_usd": 0.0,
            "closed_dd_usd": 0.0,
            "stress_dd_usd": 0.0,
            "net_over_stress": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "avg_trade": 0.0,
        }
    eq = scenario_equity(df)
    net = eq["net_usd"]
    stress = eq["stress_dd_usd"]
    return {
        "scenario": name,
        "trades": len(df),
        "net_usd": net,
        "closed_dd_usd": eq["closed_dd_usd"],
        "stress_dd_usd": stress,
        "net_over_stress": net / abs(stress) if stress else 0.0,
        "win_rate_pct": 100.0 * float((df["scenario_net_usd"] > 0).mean()),
        "profit_factor": profit_factor(df["scenario_net_usd"]),
        "avg_trade": float(df["scenario_net_usd"].mean()),
    }


def top_deletion(base: pd.DataFrame, n: int) -> Dict[str, object]:
    top_ids = set(base.nlargest(n, "net_1_1_3")["trade_id"])
    return apply_scenario(
        base,
        "delete_top_%d_winners" % n,
        lambda row: "1_1_3",
        lambda row: row["trade_id"] not in top_ids,
    )


def write_report(output_root: Path, summary: pd.DataFrame, campaigns: pd.DataFrame, instrument: str) -> None:
    lines = [
        "# %s Prior-Opposed v2b Filter Study" % instrument,
        "",
        "This study tests the obvious robustness levers from the first audit: skip or reduce size on widest opening ranges, large gaps, weak 2022 behavior, and top-winner deletion.",
        "",
        "Reduced-size scenarios are unit-level, not proportional approximations:",
        "",
        "- `1_1_3`: original five-unit `S_1_1_3` campaign.",
        "- `1_1_1`: keep unit IDs 1-3, dropping two runner units.",
        "- `1_1_0`: keep unit IDs 1-2, dropping all runner units.",
        "",
        "Stress is reconstructed from campaign-level 1m MAE and scaled by active unit count. Use the original broker replay as the authoritative fill tape.",
        "",
        "## Scenario Matrix",
        "",
        summary.to_markdown(index=False, floatfmt=".2f"),
        "",
        "## Read",
        "",
    ]
    base = summary[summary["scenario"].eq("base_1_1_3")].iloc[0]
    best = summary.sort_values("net_over_stress", ascending=False).iloc[0]
    lines += [
        "- The best Net/Stress row in this filter pass is **%s** at %.2f Net/Stress, versus base %.2f."
        % (best["scenario"], float(best["net_over_stress"]), float(base["net_over_stress"])),
        "- Skip rows show whether the weak bucket is worth excluding; reduce-size rows show whether the edge survives with less runner exposure.",
        "- Top-winner deletion rows show how much the headline depends on the biggest right-tail trades.",
        "",
        "## 2022 Forensics",
        "",
        "2022 campaign list is in `campaigns_2022.csv`. The related 15m charts are already in the broker-like chart pack; a dedicated 2022 chart index is here: [`../charts/prior_opposed_15m/INDEX_2022.md`](../charts/prior_opposed_15m/INDEX_2022.md).",
        "",
        "## Files",
        "",
        "- `filter_scenario_matrix.csv`",
        "- `campaigns_with_sizing.csv`",
        "- `campaigns_2022.csv`",
    ]
    (output_root / "FILTER_STUDY.md").write_text("\n".join(lines))


def write_2022_chart_index(chart_root: Path, campaigns_2022: pd.DataFrame, instrument: str) -> None:
    manifest_path = chart_root / "chart_manifest.csv"
    if not manifest_path.exists():
        return
    manifest = pd.read_csv(manifest_path)
    manifest_2022 = manifest[manifest["session"].astype(str).str.startswith("2022-")].copy()
    lines = [
        "# %s Prior-Opposed v2b 2022 Forensic Charts" % instrument,
        "",
        "Subset of the full 15m chart pack for the weak 2022 slice.",
        "",
        "| # | Session | Side | Net | Prior ST+PMC | Chart |",
        "|---:|---|---|---:|---|---|",
    ]
    for item in manifest_2022.itertuples(index=False):
        chart = str(item.chart)
        lines.append(
            "| %s | %s | %s | $%s | %s | [%s](%s) |"
            % (item.idx, item.session, item.side, format(float(item.net), ",.2f"), item.prior_st_side, chart, chart)
        )
    (chart_root / "INDEX_2022.md").write_text("\n".join(lines))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Filter and deletion tests for prior-opposed v2b.")
    parser.add_argument("--market", choices=PRIOR_OPPOSED_MARKETS, default="nq")
    parser.add_argument(
        "--audit-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--state-root",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--chart-root",
        type=Path,
        default=None,
    )
    args = parser.parse_args(argv)
    market = args.market.lower()
    instrument = market.upper()
    audit_root = args.audit_root or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/robustness_audit"
    state_root = args.state_root or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/states/{market}_v2b_prior_opposed_stpmc_only_S_1_1_3"
    chart_root = args.chart_root or REPO / f"live/state/{market}_v2b_prior_opposed_stpmc_broker_like/charts/prior_opposed_15m"
    campaigns = pd.read_csv(audit_root / "campaigns_robustness.csv", parse_dates=["entry_ts", "exit_ts"])
    units = pd.read_csv(state_root / "unit_trades.csv")
    base = build_trade_unit_matrix(campaigns, units)
    base.to_csv(audit_root / "campaigns_with_sizing.csv", index=False)
    scenarios: List[Dict[str, object]] = []
    scenarios.append(apply_scenario(base, "base_1_1_3", lambda row: "1_1_3"))
    scenarios.append(apply_scenario(base, "skip_or_q4_high", lambda row: "1_1_3", lambda row: row["or_width_quartile"] != "Q4 high"))
    scenarios.append(apply_scenario(base, "or_q4_high_to_1_1_1", lambda row: "1_1_1" if row["or_width_quartile"] == "Q4 high" else "1_1_3"))
    scenarios.append(apply_scenario(base, "or_q4_high_to_1_1_0", lambda row: "1_1_0" if row["or_width_quartile"] == "Q4 high" else "1_1_3"))
    scenarios.append(apply_scenario(base, "skip_gap_q4_high", lambda row: "1_1_3", lambda row: row["gap_quartile"] != "Q4 high"))
    scenarios.append(apply_scenario(base, "gap_q4_high_to_1_1_1", lambda row: "1_1_1" if row["gap_quartile"] == "Q4 high" else "1_1_3"))
    scenarios.append(apply_scenario(base, "gap_q4_high_to_1_1_0", lambda row: "1_1_0" if row["gap_quartile"] == "Q4 high" else "1_1_3"))
    scenarios.append(
        apply_scenario(
            base,
            "skip_or_q4_or_gap_q4",
            lambda row: "1_1_3",
            lambda row: row["or_width_quartile"] != "Q4 high" and row["gap_quartile"] != "Q4 high",
        )
    )
    scenarios.append(
        apply_scenario(
            base,
            "or_or_gap_q4_to_1_1_1",
            lambda row: "1_1_1" if row["or_width_quartile"] == "Q4 high" or row["gap_quartile"] == "Q4 high" else "1_1_3",
        )
    )
    scenarios.append(apply_scenario(base, "skip_2022", lambda row: "1_1_3", lambda row: int(row["year"]) != 2022))
    scenarios.append(
        apply_scenario(
            base,
            "skip_2022_or_or_q4",
            lambda row: "1_1_3",
            lambda row: int(row["year"]) != 2022 and row["or_width_quartile"] != "Q4 high",
        )
    )
    for n in [5, 10, 20]:
        scenarios.append(top_deletion(base, n))

    summary = pd.DataFrame(scenarios).sort_values("net_over_stress", ascending=False)
    summary.to_csv(audit_root / "filter_scenario_matrix.csv", index=False)
    campaigns_2022 = base[base["year"].astype(int) == 2022].copy()
    campaigns_2022.to_csv(audit_root / "campaigns_2022.csv", index=False)
    write_2022_chart_index(chart_root, campaigns_2022, instrument)
    write_report(audit_root, summary, base, instrument)
    print("Wrote %s" % (audit_root / "FILTER_STUDY.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
