"""Align structure-program keys with same-day v2b / OR profile levels (NQ).

For each RTH day after the structure lists are ready, record program + latest
bull/bear keys and join to OR-profile ``sessions.csv`` (first_break, 1R/2R).

Question: when v2b breaks out, do structure entry levels sit in the breakout
path (between OR boundary and 1R/2R)?

Usage:
  python -m live.structure_program_st_v2b_align
"""

from __future__ import annotations

import argparse
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .structure_program_st_study import StructureProgramEngine, rth_slice, to_15m
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
SESSIONS = REPO / "live" / "state" / "or_profile_engine" / "nq" / "2026H2" / "sessions.csv"
OUT = REPO / "live" / "state" / "structure_program_st" / "v2b_align"
NY_OPEN = time(9, 30)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--max-days", type=int, default=0)
    ap.add_argument("--sessions", default=str(SESSIONS))
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = date.fromisoformat(args.start) if args.start else None

    print("Loading NQ…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if args.max_days:
        days = days[: args.max_days]

    engine = StructureProgramEngine()
    rows: List[dict] = []
    for di, day in enumerate(days, 1):
        rth = rth_slice(gby.get(day))
        if rth.empty or len(rth) < 60:
            continue
        engine.ingest_day_15m(to_15m(rth))
        if not engine.ready or engine.program not in {"buy", "sell"}:
            continue
        bull_key = engine.latest_key("bull")
        bear_key = engine.latest_key("bear")
        # snapshot after 09:45 (OR complete) and at session end
        after_or = rth[rth.index.time >= time(9, 45)]
        px_0945 = float(after_or.iloc[0]["close"]) if len(after_or) else float("nan")
        px_close = float(rth.iloc[-1]["close"])
        rows.append(
            {
                "session_date": day.isoformat(),
                "program": engine.program,
                "bull_key": bull_key,
                "bear_key": bear_key,
                "entry_key": bull_key if engine.program == "buy" else bear_key,
                "entry_side": "long" if engine.program == "buy" else "short",
                "px_0945": px_0945,
                "px_close": px_close,
            }
        )
        if di % 250 == 0:
            print("  %d/%d structure days logged=%d" % (di, len(days), len(rows)), flush=True)

    struct = pd.DataFrame(rows)
    struct.to_csv(out / "structure_day_keys.csv", index=False)
    print("structure days", len(struct), flush=True)

    sess = pd.read_csv(args.sessions)
    sess["session_date"] = pd.to_datetime(sess["session_date"]).dt.date.astype(str)
    struct["session_date"] = struct["session_date"].astype(str)
    j = struct.merge(sess, on="session_date", how="inner")
    if j.empty:
        print("No overlap with sessions.csv", flush=True)
        return

    R = j["or_width_pts"].astype(float)
    oh = j["or_high"].astype(float)
    ol = j["or_low"].astype(float)
    key = j["entry_key"].astype(float)
    side = j["entry_side"]
    brk = j["first_break_side"].astype(str)

    j["dir_align"] = ((side == "long") & (brk == "up")) | ((side == "short") & (brk == "down"))
    # long: key in [or_high, or_high+2R]; short: key in [or_low-2R, or_low]
    j["in_0_1r"] = (
        ((side == "long") & (key >= oh) & (key <= oh + R))
        | ((side == "short") & (key <= ol) & (key >= ol - R))
    )
    j["in_1_2r"] = (
        ((side == "long") & (key > oh + R) & (key <= oh + 2 * R))
        | ((side == "short") & (key < ol - R) & (key >= ol - 2 * R))
    )
    j["beyond_2r"] = (
        ((side == "long") & (key > oh + 2 * R)) | ((side == "short") & (key < ol - 2 * R))
    )
    j["inside_or"] = (key <= oh) & (key >= ol)
    j["against_break"] = (
        ((side == "long") & (key < ol)) | ((side == "short") & (key > oh))
    )
    # distance from breakout boundary in R
    j["key_r_from_break"] = [
        ((float(k) - float(h)) / float(r) if s == "long" else (float(l) - float(k)) / float(r))
        if float(r) > 0
        else float("nan")
        for k, h, l, r, s in zip(key, oh, ol, R, side)
    ]
    j["v2b_tp1"] = [float(h) + float(r) if s == "long" else float(l) - float(r) for h, l, r, s in zip(oh, ol, R, side)]
    j["v2b_tp2"] = [float(h) + 2 * float(r) if s == "long" else float(l) - 2 * float(r) for h, l, r, s in zip(oh, ol, R, side)]
    j["abs_key_minus_tp1"] = (key - j["v2b_tp1"]).abs()
    j["abs_key_minus_or"] = [
        abs(float(k) - float(h)) if s == "long" else abs(float(k) - float(l))
        for k, h, l, s in zip(key, oh, ol, side)
    ]

    j.to_csv(out / "joined.csv", index=False)

    aligned = j[j["dir_align"]]
    lines = [
        "# Structure keys vs v2b / OR levels (NQ)",
        "",
        "Structure program entry key (bull LL if buy / bear HH if sell) joined to "
        "`or_profile_engine/nq/2026H2/sessions.csv`.",
        "",
        "## Coverage",
        "",
        f"- Structure ready days: **{len(struct)}**",
        f"- Joined to OR sessions: **{len(j)}**",
        f"- Program direction == first_break_side: **{j['dir_align'].mean()*100:.1f}%** ({int(j['dir_align'].sum())})",
        "",
        "## Where entry_key sits vs breakout path (all joined days)",
        "",
        f"| bucket | pct | n |",
        f"|---|---:|---:|",
        f"| inside OR | {100*j['inside_or'].mean():.1f}% | {int(j['inside_or'].sum())} |",
        f"| in 0–1R beyond break | {100*j['in_0_1r'].mean():.1f}% | {int(j['in_0_1r'].sum())} |",
        f"| in 1–2R | {100*j['in_1_2r'].mean():.1f}% | {int(j['in_1_2r'].sum())} |",
        f"| beyond 2R | {100*j['beyond_2r'].mean():.1f}% | {int(j['beyond_2r'].sum())} |",
        f"| against break (wrong side of OR) | {100*j['against_break'].mean():.1f}% | {int(j['against_break'].sum())} |",
        "",
        "## Direction-aligned subset only (program matches first_break)",
        "",
        f"- n = **{len(aligned)}**",
        f"- in 0–1R: **{100*aligned['in_0_1r'].mean():.1f}%**",
        f"- in 1–2R: **{100*aligned['in_1_2r'].mean():.1f}%**",
        f"- beyond 2R: **{100*aligned['beyond_2r'].mean():.1f}%**",
        f"- inside OR: **{100*aligned['inside_or'].mean():.1f}%**",
        f"- median |key − OR boundary| pts: **{aligned['abs_key_minus_or'].median():.1f}**",
        f"- median |key − v2b TP1| pts: **{aligned['abs_key_minus_tp1'].median():.1f}**",
        f"- median key distance from break (R): **{aligned['key_r_from_break'].median():.2f}**",
        "",
        "## Read",
        "",
        "If structure keys often sit in the 0–2R band **in the breakout direction**, "
        "a resting limit at the structure is fishing the same side as v2b continuation. "
        "If keys are usually inside OR or against the break, they are mean-reversion / "
        "counter to the v2b path.",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines))
    print("\n".join(lines))
    print("→ %s" % (out / "SUMMARY.md"), flush=True)


if __name__ == "__main__":
    main()
