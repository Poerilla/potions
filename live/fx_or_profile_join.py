"""Join FX OR-profile sessions to profitable ST+PMC 1mfill daily nets (Plan C step 4).

Usage:
  python -m live.fx_or_profile_join --asof 2026H2fx --markets us30 nas100
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Dict, List

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
ENGINE = REPO / "live" / "state" / "or_profile_engine"
STPMC = REPO / "live" / "state" / "st_pmc_1mfill_cross_market"
# US30 fair-control prior lives outside the cross-market hub
US30_ALT = REPO / "live" / "state" / "us30_st_pmc_retest_add_experiment"
OUT = REPO / "live" / "state" / "or_profile_engine" / "fx_join"

FILLS_BY_MARKET = {
    "us30": [
        STPMC / "us30" / "states" / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill" / "fills.csv",
        US30_ALT / "states" / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill" / "fills.csv",
    ],
    "nas100": [STPMC / "nas100" / "states" / "nas100_hourly_st_pmc_sl50_tp150_3r_1mfill" / "fills.csv"],
    "eurusd": [STPMC / "eurusd" / "states" / "eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill" / "fills.csv"],
    "usdjpy": [STPMC / "usdjpy" / "states" / "usdjpy_hourly_st_pmc_sl50_tp150_3r_1mfill" / "fills.csv"],
    "xauusd": [STPMC / "xauusd" / "states" / "xauusd_hourly_st_pmc_sl50_tp150_3r_1mfill" / "fills.csv"],
}

# map or-profile market key -> stpmc key
PROFILE_TO_STPMC = {
    "us30": "us30",
    "nas100": "nas100",
    "eurusd_london": "eurusd",
    "eurusd_ny": "eurusd",
    "usdjpy_london": "usdjpy",
    "usdjpy_ny": "usdjpy",
    "xauusd_ny": "xauusd",
}


def load_daily_stpmc_net(market: str) -> pd.DataFrame:
    paths = FILLS_BY_MARKET.get(market, [])
    path = next((p for p in paths if p.exists()), None)
    if path is None:
        return pd.DataFrame()
    fills = pd.read_csv(path, parse_dates=["ts"])
    # crude unit PnL from entry/exit pairs by trade_id
    rows = []
    for tid, grp in fills.groupby("trade_id"):
        grp = grp.sort_values("ts")
        ent = grp[grp["reason"].astype(str).str.contains("entry", case=False)]
        if ent.empty:
            ent = grp.iloc[:1]
        else:
            ent = ent.iloc[:1]
        # PaperBroker reasons use "target" (not "tp"); keep "tp" for older dumps.
        exits = grp[
            grp["reason"]
            .astype(str)
            .str.contains("stop|target|tp|eod|trail|close", case=False, regex=True)
        ]
        if exits.empty:
            continue
        side = str(ent.iloc[0]["side"])
        sign = 1.0 if side == "buy" else -1.0
        ep = float(ent.iloc[0]["price"])
        pnl = 0.0
        qty_e = float(ent.iloc[0]["quantity"])
        # points * qty (CFD point value left out; relative cell ranking only)
        for _, ex in exits.iterrows():
            pnl += sign * (float(ex["price"]) - ep) * float(ex["quantity"])
        session = pd.Timestamp(ent.iloc[0]["ts"])
        if session.tzinfo is not None:
            session = session.tz_convert("America/New_York")
        rows.append({"session_date": session.date(), "stpmc_points": pnl, "stpmc_units": qty_e})
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df.groupby("session_date", as_index=False).agg(stpmc_points=("stpmc_points", "sum"), stpmc_units=("stpmc_units", "sum"))


def join_one(asof: str, profile_key: str) -> pd.DataFrame:
    sess_path = ENGINE / profile_key / asof / "sessions.csv"
    if not sess_path.exists():
        print("missing %s" % sess_path, flush=True)
        return pd.DataFrame()
    sess = pd.read_csv(sess_path)
    sess = sess[sess["trigger"] == "touch"].copy()
    sess["session_date"] = pd.to_datetime(sess["session_date"]).dt.date
    stpmc_key = PROFILE_TO_STPMC.get(profile_key, profile_key)
    daily = load_daily_stpmc_net(stpmc_key)
    if daily.empty:
        print("no stpmc fills for %s" % stpmc_key, flush=True)
        return pd.DataFrame()
    joined = sess.merge(daily, on="session_date", how="inner")
    return joined


def cell_table(joined: pd.DataFrame, dims: List[str]) -> pd.DataFrame:
    rows = []
    overall = float(joined["stpmc_points"].mean()) if len(joined) else 0.0
    for key, grp in joined.groupby(dims):
        if not isinstance(key, tuple):
            key = (key,)
        net = grp["stpmc_points"]
        rows.append(
            {
                **{d: key[i] for i, d in enumerate(dims)},
                "n": len(grp),
                "mean_points": round(float(net.mean()), 4),
                "sum_points": round(float(net.sum()), 2),
                "edge_vs_all": round(float(net.mean()) - overall, 4),
                "win_pct": round(100.0 * (net > 0).mean(), 1),
            }
        )
    return pd.DataFrame(rows).sort_values("mean_points")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--asof", default="2026H2fx")
    ap.add_argument("--markets", nargs="+", default=["us30", "nas100"])
    args = ap.parse_args()
    out = OUT / args.asof
    out.mkdir(parents=True, exist_ok=True)
    lines = ["# FX OR-profile → ST+PMC 1mfill join (%s)" % args.asof, ""]
    for m in args.markets:
        j = join_one(args.asof, m.lower())
        if j.empty:
            continue
        j.to_csv(out / ("%s_joined.csv" % m), index=False)
        by_q = cell_table(j, ["or_width_q"])
        by_gap = cell_table(j, ["gap_bucket"])
        by_qg = cell_table(j, ["or_width_q", "gap_bucket"])
        by_q.to_csv(out / ("%s_by_or_width_q.csv" % m), index=False)
        by_gap.to_csv(out / ("%s_by_gap.csv" % m), index=False)
        by_qg.to_csv(out / ("%s_by_q_gap.csv" % m), index=False)
        lines.append("## %s (n=%d joined sessions, mean points/session %.4f)" % (m.upper(), len(j), j.stpmc_points.mean()))
        lines.append("")
        lines.append("### by or_width_q")
        lines.append("")
        lines.append("| " + " | ".join(by_q.columns) + " |")
        lines.append("|" + "---|" * len(by_q.columns))
        for _, r in by_q.iterrows():
            lines.append("| " + " | ".join(str(r[c]) for c in by_q.columns) + " |")
        lines.append("")
        lines.append("### by gap_bucket")
        lines.append("")
        lines.append("| " + " | ".join(by_gap.columns) + " |")
        lines.append("|" + "---|" * len(by_gap.columns))
        for _, r in by_gap.iterrows():
            lines.append("| " + " | ".join(str(r[c]) for c in by_gap.columns) + " |")
        lines.append("")
        # flat-gap / q4 carry-over flags
        flat = by_gap[by_gap["gap_bucket"] == "flat"]
        q4 = by_q[by_q["or_width_q"] == "q4"]
        flat_e = float(flat.iloc[0]["edge_vs_all"]) if len(flat) else None
        q4_e = float(q4.iloc[0]["edge_vs_all"]) if len(q4) else None
        # NQ v2b overlays: flat-gap skip and q4 no-runner assume negative edge vs all.
        flat_same = flat_e is not None and flat_e < 0
        q4_same = q4_e is not None and q4_e < 0
        lines.append(
            "Carry-over vs NQ overlays: flat-gap edge %s (%s); q4 edge %s (%s). "
            "NQ P1/P3 expect both edges negative."
            % (
                ("%.4f" % flat_e) if flat_e is not None else "n/a",
                "SAME SIGN — skip candidate" if flat_same else "OPPOSITE — do not import flat-gap skip",
                ("%.4f" % q4_e) if q4_e is not None else "n/a",
                "SAME SIGN — q4 dampen candidate" if q4_same else "OPPOSITE — do not import q4 no-runner",
            )
        )
        lines.append("")
    (out / "SUMMARY.md").write_text("\n".join(lines))
    print("-> %s" % (out / "SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
