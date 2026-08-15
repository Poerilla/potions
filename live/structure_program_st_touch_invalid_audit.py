"""Audit touch_st_align PaperBroker entries vs structure key validity.

Classifies each campaign by where the fill sits relative to the watched
structure key at the ST-flip entry:

  reclaimed   — long fill >= key / short fill <= key (structure back on side)
  still_through — long fill < key / short fill > key (buying/selling broken level)
  deep_through  — still_through and |fill−key| >= 25 pts

Also records minutes spent on the through side before the flip.

Usage:
  python -m live.structure_program_st_touch_invalid_audit
"""

from __future__ import annotations

import argparse
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .structure_program_st_study import (
    ATR_LEN,
    ATR_MULT,
    StructureProgramEngine,
    rth_slice,
    to_15m,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE = (
    REPO
    / "live"
    / "state"
    / "structure_program_st_broker_touch_align"
    / "states"
    / "nq_touch_st_align_r8"
)
OUT = REPO / "live" / "state" / "structure_program_st_broker_touch_align" / "invalid_audit"
NY = "America/New_York"
DEEP_PTS = 25.0


def _ny(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def load_broker_camps(state: Path) -> pd.DataFrame:
    u = pd.read_csv(state / "unit_trades.csv")
    u["entry_ts"] = pd.to_datetime(u["entry_ts"], utc=True)
    u["exit_ts"] = pd.to_datetime(u["exit_ts"], utc=True)
    last = u.sort_values("exit_ts").groupby("trade_id", as_index=False).tail(1)
    camp = u.groupby("trade_id", as_index=False).agg(
        pnl_usd=("net_usd", "sum"),
        direction=("direction", "first"),
        entry_ts=("entry_ts", "min"),
        fill_px=("entry_price", "first"),
        units=("unit_id", "count"),
    )
    camp = camp.merge(
        last[["trade_id", "exit_ts", "exit_price", "exit_reason"]], on="trade_id"
    )
    camp["side"] = camp["direction"].str.lower()
    return camp.sort_values("entry_ts").reset_index(drop=True)


def replay_signals(gby: Dict[date, pd.DataFrame], start: date) -> pd.DataFrame:
    """Emit one row per touch→through→ST-flip continuation signal (analytic twin)."""
    engine = StructureProgramEngine()
    days = sorted(d for d in gby if d >= start)
    recent: List[pd.DataFrame] = []
    rows: List[dict] = []
    pending: Optional[dict] = None

    for day in days:
        rth = rth_slice(gby.get(day))
        if rth.empty or len(rth) < 60:
            continue
        engine.ingest_day_15m(to_15m(rth))
        if not engine.ready or engine.program is None:
            recent.append(rth)
            recent = recent[-3:]
            continue

        tape = pd.concat(recent + [rth]) if recent else rth
        tape = tape[~tape.index.duplicated(keep="last")].sort_index()
        st_df = compute_supertrend(tape, atr_len=ATR_LEN, multiplier=ATR_MULT)
        day_start, day_end = rth.index[0], rth.index[-1]

        for i in range(len(st_df)):
            ts = st_df.index[i]
            if ts < day_start:
                continue
            row = st_df.iloc[i]
            h, l, c = float(row.high), float(row.low), float(row.close)
            st_px = row.supertrend
            trend = int(row.supertrend_trend) if not pd.isna(row.supertrend_trend) else 0
            if pd.isna(st_px):
                continue
            st_px = float(st_px)
            prog = engine.program

            if pending is not None:
                side = pending["side"]
                bad = (side == "long" and prog != "buy") or (side == "short" and prog != "sell")
                if bad or prog not in {"buy", "sell"}:
                    pending = None
                else:
                    sk = float(pending["structure_key"])
                    if not pending.get("touched"):
                        fresh = engine.latest_key("bull" if side == "long" else "bear")
                        if fresh is not None:
                            sk = float(fresh)
                            pending["structure_key"] = sk
                    if side == "long":
                        if l <= sk:
                            pending["touched"] = True
                        if l < sk:
                            pending["through"] = True
                            if pending.get("through_ts") is None:
                                pending["through_ts"] = ts
                            pending["through_bars"] = int(pending.get("through_bars") or 0) + (
                                1 if c < sk else 0
                            )
                            if c < sk:
                                pending["through_streak"] = int(pending.get("through_streak") or 0) + 1
                            else:
                                pending["through_streak"] = 0
                    else:
                        if h >= sk:
                            pending["touched"] = True
                        if h > sk:
                            pending["through"] = True
                            if pending.get("through_ts") is None:
                                pending["through_ts"] = ts
                            if c > sk:
                                pending["through_streak"] = int(pending.get("through_streak") or 0) + 1
                            else:
                                pending["through_streak"] = 0
                    if pending.get("through"):
                        pending["phase"] = "wait_flip"
                    if pending.get("phase") == "wait_flip" and i >= 1:
                        prev = st_df.iloc[i - 1]
                        prev_trend = (
                            int(prev.supertrend_trend)
                            if not pd.isna(prev.supertrend_trend)
                            else 0
                        )
                        prev_st = prev.supertrend
                        flip = False
                        if not pd.isna(prev_st):
                            prev_st = float(prev_st)
                            if side == "long" and prev_trend == -1 and trend == 1 and c > prev_st:
                                flip = True
                            elif side == "short" and prev_trend == 1 and trend == -1 and c < prev_st:
                                flip = True
                        if flip and not (
                            (side == "long" and st_px >= c) or (side == "short" and st_px <= c)
                        ):
                            sk = float(pending["structure_key"])
                            still = (side == "long" and c < sk) or (side == "short" and c > sk)
                            mins = 0.0
                            if pending.get("through_ts") is not None:
                                mins = (ts - pending["through_ts"]).total_seconds() / 60.0
                            rows.append(
                                {
                                    "signal_ts": ts,
                                    "side": side,
                                    "program": prog,
                                    "structure_key": sk,
                                    "entry_px": c,
                                    "st_stop": st_px,
                                    "through_ts": pending.get("through_ts"),
                                    "mins_through": mins,
                                    "through_streak_at_flip": int(pending.get("through_streak") or 0),
                                    "still_through": still,
                                    "dist_key_pts": abs(c - sk),
                                    "side_sign": 1 if side == "long" else -1,
                                }
                            )
                            pending = None
                            continue

            if pending is None and prog in {"buy", "sell"}:
                sk = engine.latest_key("bull" if prog == "buy" else "bear")
                if sk is not None:
                    pending = {
                        "phase": "watch",
                        "side": "long" if prog == "buy" else "short",
                        "structure_key": float(sk),
                        "touched": False,
                        "through": False,
                        "through_ts": None,
                        "through_streak": 0,
                    }

            if pending is not None and ts == day_end:
                pending["rth_closes"] = int(pending.get("rth_closes") or 0) + 1
                if pending["rth_closes"] >= 3:
                    pending = None

        recent.append(rth)
        recent = recent[-3:]

    return pd.DataFrame(rows)


def classify(row) -> str:
    if bool(row.still_through):
        if float(row.dist_key_pts) >= DEEP_PTS:
            return "deep_through"
        return "still_through"
    return "reclaimed"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--start", default="2020-01-01")
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    start = date.fromisoformat(args.start)

    print("Loading broker campaigns…", flush=True)
    camp = load_broker_camps(Path(args.state))
    print("Loading NQ 1m + replaying touch→flip signals…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    sig = replay_signals(gby, start)
    sig.to_csv(out / "analytic_signals.csv", index=False)
    print("signals", len(sig), "camps", len(camp), flush=True)

    # nearest signal within ±3 minutes, same side
    camp = camp.copy()
    camp["entry_ny"] = camp["entry_ts"].map(_ny)
    sig = sig.copy()
    sig["signal_ny"] = pd.to_datetime(sig["signal_ts"]).map(_ny)
    matched = []
    sig_by_side = {s: g.sort_values("signal_ny") for s, g in sig.groupby("side")}
    for _, r in camp.iterrows():
        side = str(r.side)
        pool = sig_by_side.get(side)
        if pool is None or pool.empty:
            matched.append(None)
            continue
        # broker fills next bar after signal → prefer signal 0–2 min before entry
        delta = (r.entry_ny - pool["signal_ny"]).dt.total_seconds()
        ok = (delta >= -30) & (delta <= 180)
        cand = pool.loc[ok]
        if cand.empty:
            # widen
            ok = delta.abs() <= 300
            cand = pool.loc[ok]
        if cand.empty:
            matched.append(None)
            continue
        j = cand.iloc[(cand["signal_ny"] - r.entry_ny).abs().argmin()]
        matched.append(j.to_dict())

    rows = []
    for i, r in camp.iterrows():
        m = matched[i]
        base = {
            "trade_id": r.trade_id,
            "side": r.side,
            "entry_ts": r.entry_ts,
            "fill_px": float(r.fill_px),
            "pnl_usd": float(r.pnl_usd),
            "exit_reason": r.exit_reason,
            "matched": m is not None,
        }
        if m is None:
            base.update(
                {
                    "structure_key": np.nan,
                    "still_through": np.nan,
                    "dist_key_pts": np.nan,
                    "mins_through": np.nan,
                    "validity": "unmatched",
                }
            )
        else:
            # recompute still_through from broker fill vs matched key
            sk = float(m["structure_key"])
            fill = float(r.fill_px)
            still = (r.side == "long" and fill < sk) or (r.side == "short" and fill > sk)
            dist = abs(fill - sk)
            validity = "deep_through" if still and dist >= DEEP_PTS else (
                "still_through" if still else "reclaimed"
            )
            base.update(
                {
                    "structure_key": sk,
                    "signal_ts": m["signal_ts"],
                    "st_stop": m["st_stop"],
                    "still_through": still,
                    "dist_key_pts": dist,
                    "mins_through": m["mins_through"],
                    "through_streak_at_flip": m["through_streak_at_flip"],
                    "validity": validity,
                }
            )
        rows.append(base)

    df = pd.DataFrame(rows)
    df.to_csv(out / "campaign_validity.csv", index=False)

    lines = [
        "# touch_st_align — structural validity vs entry level",
        "",
        "PaperBroker campaigns joined to reconstructed touch→through→ST-flip signals.",
        "",
        "## Validity classes (at fill vs structure key)",
        "",
        "- **reclaimed** — fill on the program side of the key (long ≥ key / short ≤ key)",
        "- **still_through** — fill still through the broken key (<25 pts)",
        "- **deep_through** — still through and ≥%.0f pts beyond the key" % DEEP_PTS,
        "- **unmatched** — no analytic twin within ~5 minutes",
        "",
    ]
    matched_n = int(df.matched.sum())
    lines += [
        "## Coverage",
        "",
        "- Campaigns: **%d** · matched: **%d** (%.1f%%)"
        % (len(df), matched_n, 100.0 * matched_n / max(len(df), 1)),
        "",
        "## By validity",
        "",
    ]
    g = (
        df.groupby("validity")
        .agg(n=("trade_id", "count"), net=("pnl_usd", "sum"), wr=("pnl_usd", lambda s: (s > 0).mean()))
        .reset_index()
    )
    g["wr_pct"] = (100.0 * g["wr"]).round(1)
    try:
        lines.append(g[["validity", "n", "net", "wr_pct"]].to_markdown(index=False))
    except Exception:
        lines.append(g[["validity", "n", "net", "wr_pct"]].to_string(index=False))

    sub = df[df.validity.isin(["reclaimed", "still_through", "deep_through"])]
    if not sub.empty:
        lines += [
            "",
            "## Matched only — PnL split",
            "",
            "- reclaimed net **$%.0f** (n=%d)"
            % (
                sub.loc[sub.validity == "reclaimed", "pnl_usd"].sum(),
                int((sub.validity == "reclaimed").sum()),
            ),
            "- still_through net **$%.0f** (n=%d)"
            % (
                sub.loc[sub.validity == "still_through", "pnl_usd"].sum(),
                int((sub.validity == "still_through").sum()),
            ),
            "- deep_through net **$%.0f** (n=%d)"
            % (
                sub.loc[sub.validity == "deep_through", "pnl_usd"].sum(),
                int((sub.validity == "deep_through").sum()),
            ),
            "",
            "### Minutes through before flip (matched)",
            "",
        ]
        for v in ["reclaimed", "still_through", "deep_through"]:
            s = sub.loc[sub.validity == v, "mins_through"]
            if len(s):
                lines.append(
                    "- %s: median **%.0f** min · p75 **%.0f** · share ≥20m **%.1f%%**"
                    % (v, s.median(), s.quantile(0.75), 100.0 * (s >= 20).mean())
                )
        lines += [
            "",
            "### If we had skipped still_through + deep_through",
            "",
        ]
        keep = sub[sub.validity == "reclaimed"]
        lines.append(
            "- Keep reclaimed only: n=%d net **$%.0f** WR %.1f%%"
            % (len(keep), keep.pnl_usd.sum(), 100.0 * (keep.pnl_usd > 0).mean())
        )
        drop = sub[sub.validity != "reclaimed"]
        lines.append(
            "- Dropped through entries: n=%d net **$%.0f**"
            % (len(drop), drop.pnl_usd.sum())
        )

    lines += [
        "",
        "## Read",
        "",
        "Continuation entries that fire while price is still through the structure "
        "are structurally faded (buying broken support / selling broken resistance). "
        "A 20-minute still-through fade path would harvest that regime instead of "
        "waiting for an aligned ST flip into the broken level.",
        "",
        "Artifacts: `campaign_validity.csv`, `analytic_signals.csv`.",
        "",
    ]
    (out / "SUMMARY.md").write_text("\n".join(lines))
    print((out / "SUMMARY.md").read_text(), flush=True)


if __name__ == "__main__":
    main()
