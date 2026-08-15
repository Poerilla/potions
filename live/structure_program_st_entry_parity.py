"""Entry / signal parity diagnostics for structure_program_st.

1) Dump **all** analytic arms (not just fills) for structure_sl_scale_run.
2) Compare to broker entry fills (timing / price / day overlap).
3) Optionally note same-bar / next-bar death rates from an existing broker run.

Usage:
  python -m live.structure_program_st_entry_parity
  python -m live.structure_program_st_entry_parity --max-days 400
"""

from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .structure_program_st_study import (
    ATR_LEN,
    ATR_MULT,
    STRUCTURE_SL_PENDING_MAX_CLOSES,
    StructureProgramEngine,
    rth_slice,
    to_15m,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "structure_program_st_broker_scale_run" / "entry_parity"
BROKER_UNITS = (
    REPO
    / "live"
    / "state"
    / "structure_program_st_broker_scale_run"
    / "states"
    / "nq_scale_run_r8"
    / "unit_trades.csv"
)
BROKER_FILLS = (
    REPO
    / "live"
    / "state"
    / "structure_program_st_broker_scale_run"
    / "states"
    / "nq_scale_run_r8"
    / "fills.csv"
)


def dump_analytic_signals(
    gby: Dict[date, pd.DataFrame],
    *,
    start: Optional[date],
    max_days: int,
    risk_pts: float = 8.0,
) -> pd.DataFrame:
    """Walk analytic ST + structure engine; log every pending arm + fill/cancel/expire."""
    days = sorted(gby)
    if start:
        days = [d for d in days if d >= start]
    if max_days:
        days = days[:max_days]

    engine = StructureProgramEngine()
    pending = None
    position = None  # only used to block re-arms like research
    recent_rth: List[pd.DataFrame] = []
    rows: List[dict] = []
    sig_id = 0

    for day in days:
        rth = rth_slice(gby.get(day))
        if rth.empty or len(rth) < 60:
            continue
        engine.ingest_day_15m(to_15m(rth))
        warmup = pd.concat(recent_rth) if recent_rth else None
        tape = pd.concat([warmup, rth]) if warmup is not None else rth
        tape = tape[~tape.index.duplicated(keep="last")].sort_index()
        st_df = compute_supertrend(tape, atr_len=ATR_LEN, multiplier=ATR_MULT)
        day_start, day_end = rth.index[0], rth.index[-1]

        for i in range(len(st_df)):
            ts = st_df.index[i]
            if ts < day_start:
                continue
            row = st_df.iloc[i]
            h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
            st_px = row["supertrend"]
            trend = int(row["supertrend_trend"]) if not pd.isna(row["supertrend_trend"]) else 0
            if pd.isna(st_px):
                continue
            st_px = float(st_px)

            # research: manage open would run first — we only care about flat/pending for signals
            if position is not None:
                # crude: clear position flag only when we would have exited is unknown here;
                # for signal dump with blocking, use trade list later. Here: no position sim.
                pass

            if pending is not None:
                side = pending["side"]
                lim = float(pending["limit_px"])
                stop_p = float(pending["stop"])
                blown = (side == "long" and l <= stop_p) or (side == "short" and h >= stop_p)
                filled = (side == "long" and l <= lim) or (side == "short" and h >= lim)
                cancel_prog = engine.program is not None and (
                    (side == "long" and engine.program != "buy")
                    or (side == "short" and engine.program != "sell")
                )
                if blown:
                    rows.append({**pending, "event": "blown", "event_ts": ts})
                    pending = None
                elif filled:
                    rows.append(
                        {
                            **pending,
                            "event": "filled",
                            "event_ts": ts,
                            "fill_px": lim,
                            "note": "analytic_same_bar_touch",
                        }
                    )
                    # block until "flat" — approximate with no multi-day position model:
                    # mark a short block token; cleared at session end for dump-only
                    position = {"until": day_end}
                    pending = None
                elif cancel_prog:
                    rows.append({**pending, "event": "cancel_prog", "event_ts": ts})
                    pending = None
                elif ts == day_end:
                    pending["rth_closes"] = int(pending.get("rth_closes") or 0) + 1
                    if pending["rth_closes"] >= STRUCTURE_SL_PENDING_MAX_CLOSES:
                        rows.append({**pending, "event": "expire", "event_ts": ts})
                        pending = None

            if position is not None and ts >= position["until"]:
                position = None

            if position is None and pending is None and engine.ready and engine.program is not None:
                loc = st_df.index.get_loc(ts)
                if isinstance(loc, (slice, np.ndarray)) or int(loc) < 1:
                    continue
                prev = st_df.iloc[int(loc) - 1]
                prev_trend = int(prev["supertrend_trend"]) if not pd.isna(prev["supertrend_trend"]) else 0
                prev_st = prev["supertrend"]
                if pd.isna(prev_st):
                    continue
                prev_st = float(prev_st)
                prog = engine.program
                signal = None
                sk = None
                if prog == "buy" and prev_trend == -1 and trend == 1 and c > prev_st:
                    sk = engine.latest_key("bull")
                    if sk is not None and sk < prev_st:
                        signal = "long"
                elif prog == "sell" and prev_trend == 1 and trend == -1 and c < prev_st:
                    sk = engine.latest_key("bear")
                    if sk is not None and sk > prev_st:
                        signal = "short"
                if signal and sk is not None:
                    sig_id += 1
                    stop = sk - risk_pts if signal == "long" else sk + risk_pts
                    pending = {
                        "signal_id": sig_id,
                        "side": signal,
                        "program": prog,
                        "signal_ts": ts,
                        "limit_px": float(sk),
                        "stop": float(stop),
                        "structure_key": float(sk),
                        "st_at_signal": prev_st,
                        "risk_pts": risk_pts,
                        "rth_closes": 0,
                    }
                    rows.append({**pending, "event": "arm", "event_ts": ts})

        recent_rth.append(rth)
        recent_rth = recent_rth[-3:]

    return pd.DataFrame(rows)


def compare_to_broker(signals: pd.DataFrame, out: Path) -> str:
    arms = signals[signals.event == "arm"].copy()
    fills_a = signals[signals.event == "filled"].copy()
    lines = [
        "# Entry / signal parity",
        "",
        "## Analytic signal dump (session-blocked approx)",
        "",
        f"- Arms: **{len(arms)}**",
        f"- Fills (touch, same-bar): **{len(fills_a)}**",
        f"- Blown before fill: **{(signals.event == 'blown').sum()}**",
        f"- Expire / cancel_prog: **{(signals.event == 'expire').sum()}** / **{(signals.event == 'cancel_prog').sum()}**",
        "",
    ]
    if not BROKER_FILLS.exists():
        lines.append("Broker fills missing — skip broker compare.")
        (out / "ENTRY_PARITY.md").write_text("\n".join(lines))
        return "\n".join(lines)

    bf = pd.read_csv(BROKER_FILLS)
    bf["ts"] = pd.to_datetime(bf["ts"], utc=True)
    bent = bf[bf.reason == "entry"].copy()
    bent["side"] = bent["side"].map({"buy": "long", "sell": "short"})
    bent["day"] = bent["ts"].dt.tz_convert("America/New_York").dt.date

    arms["signal_ts"] = pd.to_datetime(arms["signal_ts"], utc=True)
    fills_a["event_ts"] = pd.to_datetime(fills_a["event_ts"], utc=True)
    arms["day"] = arms["signal_ts"].dt.tz_convert("America/New_York").dt.date
    fills_a["day"] = fills_a["event_ts"].dt.tz_convert("America/New_York").dt.date

    lines += [
        "## Broker entries (existing scale_run run)",
        "",
        f"- Entry fills: **{len(bent)}**",
        f"- Analytic fill days: **{fills_a.day.nunique()}** · Broker entry days: **{bent.day.nunique()}** · overlap: **{len(set(fills_a.day) & set(bent.day))}**",
        "",
        "## Code-level entry differences (not data)",
        "",
        "1. **Touch fill timing:** analytic fills on the touch bar at exact `limit_px`. "
        "Broker submits limit with `live_after_ts=touch_bar` and PaperBroker requires "
        "**strictly later** bar → entry fills next minute (+ slip).",
        "2. **Post-entry management:** analytic runs `_manage_open` *before* fill on that bar, "
        "so the fill bar does not ST-flip/stop the new position. Broker `on_bar_close` after "
        "fill can arm `st_flip` same bar; market fills next bar → classic 1-minute death.",
        "3. **Stop-first ordering:** protective stops before targets (pessimistic by design) "
        "once both are live; entry itself is next-bar due to `live_after_ts`.",
        "4. **Position blocking:** different hold times change which later ST breaks can arm.",
        "5. **ST path:** analytic `compute_supertrend` on warm+day tape vs plugin incremental "
        "EWM with 2-session warm — can diverge at edges.",
        "",
    ]

    # match analytic fills to broker entries
    used = set()
    matches = []
    for _, r in fills_a.iterrows():
        cands = bent[(bent.day == r.day) & (bent.side == r.side) & (~bent.fill_id.isin(used))].copy()
        if cands.empty:
            matches.append({"matched": False, "a_ts": r.event_ts, "a_px": r.fill_px, "a_side": r.side})
            continue
        cands["dt"] = (cands.ts - r.event_ts).abs().dt.total_seconds() / 60
        j = cands["dt"].idxmin()
        b = cands.loc[j]
        if b.dt > 120 or abs(float(b.price) - float(r.fill_px)) > 30:
            matches.append({"matched": False, "a_ts": r.event_ts, "a_px": r.fill_px, "a_side": r.side})
            continue
        used.add(b.fill_id)
        matches.append(
            {
                "matched": True,
                "a_ts": r.event_ts,
                "b_ts": b.ts,
                "a_px": float(r.fill_px),
                "b_px": float(b.price),
                "dt_min": b.dt,
                "px_diff": float(b.price) - float(r.fill_px),
                "a_side": r.side,
            }
        )
    m = pd.DataFrame(matches)
    mm = m[m.matched]
    lines += [
        "## Fill matching (analytic fill ↔ broker entry)",
        "",
        f"- Matched: **{len(mm)}** / {len(fills_a)} analytic fills",
        f"- Unmatched analytic fills: **{(~m.matched).sum()}**",
        f"- Broker-only entries: **{len(bent) - len(mm)}**",
    ]
    if len(mm):
        lines += [
            f"- Median |Δt|: **{mm.dt_min.median():.1f} min** · mean entry px diff (B−A): **{mm.px_diff.mean():.3f} pts**",
            "",
        ]
    else:
        lines.append("")

    if BROKER_UNITS.exists():
        u = pd.read_csv(BROKER_UNITS)
        u["entry_ts"] = pd.to_datetime(u.entry_ts, utc=True)
        u["exit_ts"] = pd.to_datetime(u.exit_ts, utc=True)
        camp = u.groupby("trade_id").agg(
            entry_ts=("entry_ts", "min"), exit_ts=("exit_ts", "max"), pnl=("net_usd", "sum")
        ).reset_index()
        last = u.sort_values("exit_ts").groupby("trade_id").tail(1)[["trade_id", "exit_reason"]]
        camp = camp.merge(last, on="trade_id")
        camp["hold_min"] = (camp.exit_ts - camp.entry_ts).dt.total_seconds() / 60
        dead = camp.hold_min <= 1
        lines += [
            "## Broker next-bar death (ordering / ST)",
            "",
            f"- Campaigns with hold ≤ 1 minute: **{dead.sum()} / {len(camp)} ({100*dead.mean():.1f}%)**",
            f"- PnL hold≤1: **${camp.loc[dead,'pnl'].sum():.0f}** · hold>1: **${camp.loc[~dead,'pnl'].sum():.0f}**",
            f"- Among hold≤1 exits: {camp.loc[dead,'exit_reason'].value_counts().to_dict()}",
            "",
            "If the book only kept hold>1 trades, it would be **net positive** on this run — "
            "survivorship of the entry bar is the broker gap, more than scale targets.",
            "",
        ]

    lines += [
        "## Proposed tests",
        "",
        "1. **Analytic-as-signal:** feed analytic `arm` rows into plugin (`signal_source=external`) "
        "so execution/ordering is the only difference.",
        "2. **sweep_reclaim entry:** after arm, require stop touch first, then reclaim through "
        "`limit_px` before submitting entry (liquidity-sweep entry).",
        "",
    ]
    (out / "ENTRY_PARITY.md").write_text("\n".join(lines))
    m.to_csv(out / "fill_matches.csv", index=False)
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--max-days", type=int, default=0)
    ap.add_argument("--risk-pts", type=float, default=8.0)
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = date.fromisoformat(args.start) if args.start else None

    print("Loading NQ…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    print("Dumping analytic signals…", flush=True)
    sig = dump_analytic_signals(gby, start=start, max_days=args.max_days, risk_pts=args.risk_pts)
    sig.to_csv(out / "analytic_signals.csv", index=False)
    arms = sig[sig.event == "arm"]
    arms.to_csv(out / "analytic_arms.csv", index=False)
    print("arms=%d events=%d → %s" % (len(arms), len(sig), out), flush=True)
    text = compare_to_broker(sig, out)
    print(text)
    print("→ %s" % (out / "ENTRY_PARITY.md"), flush=True)


if __name__ == "__main__":
    main()
