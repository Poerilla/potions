"""Counterfactual: research ST-flip exits that would win if ST-flip were disabled.

For each NQ split15@12 st_flip trade, replay the open from entry with the same
risk/scale/EOD/runner rules but **no ST-flip**. Chart those that flip from
st_flip loss → counterfactual win (up to 50).
"""

from __future__ import annotations

from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .bars import rth_bars
from .structure_program_st_study import chart_trades
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
TRADES = REPO / "live" / "state" / "structure_program_st" / "nq" / "split15_r12" / "trades.csv"
OUT = REPO / "live" / "state" / "structure_program_st" / "st_flip_killed_winners"
NY = "America/New_York"
POINT_VALUE = 20.0
ENTRY_QTY = 15.0
SCALE_QTY = 5.0
EOD_QTY = 5.0
RUNNER_QTY = 5.0
RUNNER_R = 6.0


def _cf_pnl(side: str, entry: float, risk: float, day_bars: pd.DataFrame, entry_ts: pd.Timestamp) -> dict:
    """Walk RTH tape from entry bar; no ST-flip. Returns exit info + pnl_usd."""
    sign = 1.0 if side == "long" else -1.0
    stop = entry - risk if side == "long" else entry + risk
    tp1 = entry + sign * risk
    tpr = entry + sign * RUNNER_R * risk
    qty_open = ENTRY_QTY
    qty_eod = 0.0
    qty_runner = 0.0
    scaled = False
    realized = 0.0
    be = entry

    def realize(q: float, px: float) -> None:
        nonlocal realized, qty_open
        if q <= 0:
            return
        realized += sign * (px - entry) * POINT_VALUE * q
        qty_open -= q

    tape = day_bars[day_bars.index >= entry_ts]
    if tape.empty:
        return {"cf_pnl": 0.0, "cf_reason": "no_tape", "cf_exit": entry}

    last_px = entry
    for i, (ts, row) in enumerate(tape.iterrows()):
        h, l, c = float(row["high"]), float(row["low"]), float(row["close"])
        last_px = c
        is_eod = ts.time() >= time(15, 59)

        # stop (risk or BE)
        cur_stop = be if scaled else stop
        hit_stop = (side == "long" and l <= cur_stop) or (side == "short" and h >= cur_stop)
        if hit_stop and qty_open > 0:
            reason = "be_stop" if scaled else "risk_stop"
            realize(qty_open, cur_stop)
            return {"cf_pnl": realized, "cf_reason": reason, "cf_exit": cur_stop}

        # scale 1R
        if not scaled:
            hit_tp1 = (side == "long" and h >= tp1) or (side == "short" and l <= tp1)
            if hit_tp1:
                realize(SCALE_QTY, tp1)
                scaled = True
                be = entry
                qty_eod = min(EOD_QTY, qty_open)
                qty_runner = qty_open - qty_eod

        # runner 6R
        if scaled and qty_runner > 0:
            hit_r = (side == "long" and h >= tpr) or (side == "short" and l <= tpr)
            if hit_r:
                q = min(qty_runner, qty_open)
                realize(q, tpr)
                qty_runner = 0.0
                if qty_open <= 0:
                    return {"cf_pnl": realized, "cf_reason": "runner_6r", "cf_exit": tpr}

        if is_eod and qty_open > 0:
            if not scaled:
                realize(qty_open, c)
                return {"cf_pnl": realized, "cf_reason": "eod_flat", "cf_exit": c}
            if qty_eod > 0:
                q = min(qty_eod, qty_open)
                realize(q, c)
                qty_eod = 0.0
            if qty_open <= 0:
                return {"cf_pnl": realized, "cf_reason": "scale_1r+eod", "cf_exit": c}
            # runners can hold overnight — mark at EOD for this counterfactual
            realize(qty_open, c)
            return {"cf_pnl": realized, "cf_reason": "eod_mark_runners", "cf_exit": c}

    if qty_open > 0:
        realize(qty_open, last_px)
    return {"cf_pnl": realized, "cf_reason": "session_end", "cf_exit": last_px}


def main(n_charts: int = 50) -> None:
    df = pd.read_csv(TRADES)
    st = df[df.exit_reason.astype(str).str.contains("st_flip", case=False, na=False)].copy()
    print("ST-flip trades: %d" % len(st), flush=True)

    cfg = MARKETS["nq"]
    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(cfg.dbn_path.resolve(), cfg.market)

    rows = []
    for _, t in st.iterrows():
        entry_ts = pd.Timestamp(t.entry_ts)
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize(NY)
        else:
            entry_ts = entry_ts.tz_convert(NY)
        day = entry_ts.date()
        raw = gby.get(day)
        bars = rth_bars(raw, day, dense=True)
        if bars.empty:
            continue
        risk = float(t.risk_pts) if pd.notna(t.get("risk_pts", np.nan)) else 12.0
        cf = _cf_pnl(str(t.side), float(t.entry), risk, bars, entry_ts)
        rows.append(
            {
                **t.to_dict(),
                "st_flip_pnl": float(t.pnl_usd),
                "cf_pnl": cf["cf_pnl"],
                "cf_reason": cf["cf_reason"],
                "cf_delta": cf["cf_pnl"] - float(t.pnl_usd),
                "killed_winner": float(t.pnl_usd) <= 0 and cf["cf_pnl"] > 0,
            }
        )

    out = pd.DataFrame(rows)
    OUT.mkdir(parents=True, exist_ok=True)
    out.to_csv(OUT / "st_flip_counterfactual.csv", index=False)
    killed = out[out["killed_winner"]].sort_values("cf_delta", ascending=False)
    print(
        "Counterfactual: %d st_flip → %d would-be winners (cf>0 & st_flip_pnl<=0)"
        % (len(out), len(killed)),
        flush=True,
    )
    print(
        "Sum st_flip_pnl on killed=$%.0f · sum cf_pnl=$%.0f · delta=$%.0f"
        % (killed.st_flip_pnl.sum(), killed.cf_pnl.sum(), killed.cf_delta.sum()),
        flush=True,
    )
    killed.head(n_charts).to_csv(OUT / "killed_winners.csv", index=False)
    sample = killed.head(n_charts).copy()
    # chart_trades expects pnl_usd — keep original st_flip pnl but annotate
    if sample.empty:
        # fall back: largest missed upside among all st_flip (cf_delta)
        sample = out.sort_values("cf_delta", ascending=False).head(n_charts)
        print("No strict killed winners; charting top cf_delta instead", flush=True)
    chart_trades(sample, gby, OUT, n=len(sample), variant="split15_st_flip_killed")
    (OUT / "SUMMARY.md").write_text(
        "\n".join(
            [
                "# ST-flip killed winners (counterfactual hold)",
                "",
                "Research NQ split15@12 trades that exited via **st_flip** with pnl≤0, but a "
                "no-ST-flip hold (risk stop / 1R scale→BE / EOD / 6R) would have been **profitable**.",
                "",
                "- ST-flip trades evaluated: %d" % len(out),
                "- Killed winners: **%d**" % len(killed),
                "- Charts: %d → `charts/`" % len(sample),
                "- Sum ST-flip pnl (killed): $%.0f" % killed.st_flip_pnl.sum(),
                "- Sum counterfactual pnl (killed): $%.0f" % killed.cf_pnl.sum(),
                "",
                "## Top by cf_delta",
                "",
                sample[
                    ["trade_id", "side", "entry_ts", "st_flip_pnl", "cf_pnl", "cf_reason", "cf_delta", "mfe_pts"]
                ]
                .head(25)
                .to_markdown(index=False),
                "",
            ]
        )
    )
    print("→ %s" % OUT, flush=True)


if __name__ == "__main__":
    main(50)
