"""Chart worst PaperBroker scale_run campaigns (loss focus).

Usage:
  python -m live.structure_program_st_chart_broker_losses --n 100
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .structure_program_st_study import chart_trades
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE = (
    REPO / "live" / "state" / "structure_program_st_broker_scale_run" / "states" / "nq_scale_run_r8"
)
DEFAULT_OUT = REPO / "live" / "state" / "structure_program_st_broker_scale_run" / "loss_charts"
RISK_PTS = 8.0


def campaigns_from_units(units_path: Path) -> pd.DataFrame:
    u = pd.read_csv(units_path)
    u["entry_ts"] = pd.to_datetime(u["entry_ts"], utc=True)
    u["exit_ts"] = pd.to_datetime(u["exit_ts"], utc=True)
    last = u.sort_values("exit_ts").groupby("trade_id", as_index=False).tail(1)
    camp = (
        u.groupby("trade_id", as_index=False)
        .agg(
            pnl_usd=("net_usd", "sum"),
            direction=("direction", "first"),
            entry_ts=("entry_ts", "min"),
            entry=("entry_price", "first"),
            units=("unit_id", "count"),
        )
    )
    camp = camp.merge(
        last[["trade_id", "exit_ts", "exit_price", "exit_reason"]],
        on="trade_id",
        how="left",
    )
    # worst-reason by $ contribution
    by_r = u.groupby(["trade_id", "exit_reason"], as_index=False)["net_usd"].sum()
    worst = by_r.loc[by_r.groupby("trade_id")["net_usd"].idxmin()].rename(
        columns={"exit_reason": "worst_reason", "net_usd": "worst_reason_pnl"}
    )
    camp = camp.merge(worst[["trade_id", "worst_reason", "worst_reason_pnl"]], on="trade_id")
    reasons = (
        u.groupby("trade_id")["exit_reason"]
        .apply(lambda s: "+".join(sorted(set(s))))
        .rename("exit_reasons")
        .reset_index()
    )
    camp = camp.merge(reasons, on="trade_id")

    # columns expected by chart_trades (structure_sl_scale_run overlay)
    camp["side"] = camp["direction"].str.lower()
    camp["program"] = camp["side"].map({"long": "buy", "short": "sell"})
    camp["variant"] = "structure_sl_scale_run"
    camp["exit"] = camp["exit_price"]
    camp["limit_px"] = camp["entry"]
    camp["stop"] = camp.apply(
        lambda r: float(r["entry"]) - RISK_PTS if r["side"] == "long" else float(r["entry"]) + RISK_PTS,
        axis=1,
    )
    camp["st_at_signal"] = camp["entry"]  # unknown in broker ledger; omit misleading line via =entry
    camp["risk_pts"] = RISK_PTS
    camp["pnl_pts"] = camp["pnl_usd"] / 20.0
    camp["mae_pts"] = float("nan")
    camp["mfe_pts"] = float("nan")
    camp["signal_ts"] = camp["entry_ts"]
    camp["structure_key"] = camp["entry"]
    camp["qty"] = 15.0
    camp["scaled"] = camp["exit_reasons"].str.contains("scale_")
    camp["scale_px"] = float("nan")
    camp["runner_target"] = float("nan")
    # chart title uses exit_reason — prefer composite
    camp["exit_reason"] = camp["exit_reasons"]
    # stable numeric id for filenames/titles
    camp = camp.sort_values("entry_ts").reset_index(drop=True)
    camp["trade_id"] = camp.index + 1
    camp["broker_trade_id"] = camp["trade_id"]  # overwritten below — fix
    return camp


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--n", type=int, default=100)
    args = ap.parse_args()
    state = Path(args.state)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    units_path = state / "unit_trades.csv"
    u = pd.read_csv(units_path)
    u["entry_ts"] = pd.to_datetime(u["entry_ts"], utc=True)
    u["exit_ts"] = pd.to_datetime(u["exit_ts"], utc=True)

    last = u.sort_values("exit_ts").groupby("trade_id", as_index=False).tail(1)
    camp = u.groupby("trade_id", as_index=False).agg(
        pnl_usd=("net_usd", "sum"),
        direction=("direction", "first"),
        entry_ts=("entry_ts", "min"),
        entry=("entry_price", "first"),
        units=("unit_id", "count"),
    )
    camp = camp.merge(last[["trade_id", "exit_ts", "exit_price", "exit_reason"]], on="trade_id")
    by_r = u.groupby(["trade_id", "exit_reason"], as_index=False)["net_usd"].sum()
    worst = by_r.loc[by_r.groupby("trade_id")["net_usd"].idxmin()].rename(
        columns={"exit_reason": "worst_reason", "net_usd": "worst_reason_pnl"}
    )
    camp = camp.merge(worst[["trade_id", "worst_reason", "worst_reason_pnl"]], on="trade_id")
    reasons = (
        u.groupby("trade_id")["exit_reason"]
        .apply(lambda s: "+".join(sorted(set(s.astype(str)))))
        .rename("exit_reasons")
        .reset_index()
    )
    camp = camp.merge(reasons, on="trade_id")
    camp["broker_trade_id"] = camp["trade_id"]
    camp["side"] = camp["direction"].str.lower()
    camp["program"] = camp["side"].map({"long": "buy", "short": "sell"})
    camp["variant"] = "structure_sl_scale_run"
    camp["exit"] = camp["exit_price"]
    camp["limit_px"] = camp["entry"]
    camp["stop"] = [
        float(e) - RISK_PTS if s == "long" else float(e) + RISK_PTS
        for e, s in zip(camp["entry"], camp["side"])
    ]
    camp["st_at_signal"] = camp["entry"]
    camp["risk_pts"] = RISK_PTS
    camp["pnl_pts"] = camp["pnl_usd"] / 20.0
    camp["mae_pts"] = float("nan")
    camp["signal_ts"] = camp["entry_ts"]
    camp["exit_reason"] = camp.apply(
        lambda r: "%s|%s" % (r["worst_reason"], r["exit_reasons"]), axis=1
    )
    # numeric ids for chart titles
    camp = camp.sort_values("pnl_usd").reset_index(drop=True)
    camp["trade_id"] = range(1, len(camp) + 1)

    losers = camp[camp["pnl_usd"] <= 0].copy()
    pick = losers.nsmallest(args.n, "pnl_usd")
    print(
        "Campaigns=%d losers=%d | charting worst %d (sum $%.0f of loser $%.0f)"
        % (
            len(camp),
            len(losers),
            len(pick),
            pick["pnl_usd"].sum(),
            losers["pnl_usd"].sum(),
        ),
        flush=True,
    )
    print("Worst-reason mix among charts:", flush=True)
    print(pick["worst_reason"].value_counts().to_string(), flush=True)
    print("By year:", flush=True)
    print(pd.to_datetime(pick["entry_ts"]).dt.year.value_counts().sort_index().to_string(), flush=True)

    pick.to_csv(out / "worst_trades.csv", index=False)

    # LOSS focus summary
    year = camp.copy()
    year["year"] = pd.to_datetime(year["entry_ts"]).dt.year
    unit_year = u.copy()
    unit_year["year"] = pd.to_datetime(unit_year["entry_ts"]).dt.year
    lines = [
        "# Broker scale_run — where losses concentrate",
        "",
        "PaperBroker NQ `nq_scale_run_r8` campaign + unit attribution.",
        "",
        "## Headline",
        "",
        "- Campaigns: **%d** (losers %d) · net **$%.0f**"
        % (len(camp), len(losers), camp["pnl_usd"].sum()),
        "- Unit PnL: `st_flip` (adverse) **$%.0f** · `risk_stop` **$%.0f** · `be_stop` **$%.0f**"
        % (
            u.loc[u.exit_reason == "st_flip", "net_usd"].sum(),
            u.loc[u.exit_reason == "risk_stop", "net_usd"].sum(),
            u.loc[u.exit_reason == "be_stop", "net_usd"].sum(),
        ),
        "- Charts: worst **%d** losers → `charts/` (sum $%.0f)"
        % (len(pick), pick["pnl_usd"].sum()),
        "",
        "## By year (campaign net)",
        "",
    ]
    try:
        lines.append(year.groupby("year")["pnl_usd"].agg(["count", "sum", "mean"]).to_markdown())
    except Exception:
        lines.append(year.groupby("year")["pnl_usd"].agg(["count", "sum", "mean"]).to_string())
    lines += ["", "## Unit $ by year × exit_reason", ""]
    piv = unit_year.pivot_table(
        index="year", columns="exit_reason", values="net_usd", aggfunc="sum", fill_value=0
    )
    try:
        lines.append(piv.to_markdown())
    except Exception:
        lines.append(piv.to_string())
    lines += [
        "",
        "## Loser campaigns by worst_reason",
        "",
    ]
    g = losers.groupby("worst_reason")["pnl_usd"].agg(["count", "sum", "mean"]).sort_values("sum")
    try:
        lines.append(g.to_markdown())
    except Exception:
        lines.append(g.to_string())
    lines += [
        "",
        "## Takeaway",
        "",
        "Most dollar damage is **adverse ST-flip flattens** (fav_be mode still exits when "
        "close is through entry), then **full risk_stop** on the 15-lot. Scale/runner legs "
        "are profitable but too rare under broker fills to offset.",
        "",
    ]
    (out / "LOSS_FOCUS.md").write_text("\n".join(lines))
    print("→ %s" % (out / "LOSS_FOCUS.md"), flush=True)

    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    # chart_trades splits sample across wins/losses with step=len/(n/2).
    # With losers-only, pass n=2*len so step=1 and all rows are charted.
    chart_trades(pick, gby, out, n=max(2 * len(pick), 2), variant="structure_sl_scale_run")
    print("→ %s" % out, flush=True)


if __name__ == "__main__":
    main()
