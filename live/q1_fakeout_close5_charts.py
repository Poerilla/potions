"""Chart A1 close5-confirmed boundary fades (stop at failed extreme) with gates.

Gates marked on each chart:
  1. OR (09:30-09:45)
  2. Touch break
  3. 5m close outside OR
  4. 5m close back inside (failure confirm)
  5. Limit fill at the broken boundary
  6. Exit (TP opposite boundary / SL failed extreme)

Usage: python -m live.q1_fakeout_close5_charts
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from .q1_fakeout_loss_autopsy import OUT, Trade, rth
from .q1_fakeout_structure_followup import load_gby, scan_close5_fades
from .v2b_strategy_cross_market_replay import MARKETS, _regime_dates

CHARTS = Path(__file__).resolve().parents[1] / "live" / "state" / "q1_fakeout_satellite" / "charts" / "close5_a1"
TRADES = OUT / "followup_variant_trades.csv"


def _xi(idx: List[pd.Timestamp], ts) -> Optional[int]:
    if ts is None:
        return None
    ts = pd.Timestamp(ts)
    try:
        return idx.index(ts)
    except ValueError:
        # nearest bar
        for i, t in enumerate(idx):
            if t >= ts:
                return i
        return None


def draw(t: Trade, day_df: pd.DataFrame, entry_px: float, entry_ts, exit_ts, exit_px: float, outcome: str, pnl: float, path: Path) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    bars = rth(day_df)
    fig, ax = plt.subplots(figsize=(15, 8))
    x = list(range(len(bars)))
    idx = list(bars.index)
    up = bars["close"] >= bars["open"]
    ax.vlines(x, bars["low"], bars["high"], color="#999", lw=0.55, zorder=1)
    ax.vlines([i for i, u in zip(x, up) if u], bars["open"][up], bars["close"][up], color="#1a9850", lw=2.2, zorder=2)
    ax.vlines(
        [i for i, u in zip(x, up) if not u], bars["close"][~up], bars["open"][~up], color="#d73027", lw=2.2, zorder=2
    )

    # levels
    for level, style, color, label in [
        (t.or_high, "-", "#222", "OR high"),
        (t.or_low, "-", "#222", "OR low"),
        (t.stop, ":", "#e08214", "SL failed extreme"),
        (t.tp_bound, "--", "#1a9850", "TP opposite boundary"),
        (t.failed_extreme, "-.", "#b35806", "failed extreme wick"),
    ]:
        ax.axhline(level, ls=style, color=color, lw=1.1, label=label, zorder=3)

    # gate markers
    gates: List[Tuple[object, str, str, str]] = [
        (t.break_ts, "1 touch break", "D", "#542788"),
        (getattr(t, "close_out_ts", None), "2 close5 OUT", "s", "#e08214"),
        (t.confirm_ts, "3 close5 IN", "s", "#2166ac"),
        (entry_ts, "4 limit fill @ boundary", "^" if t.direction == "Long" else "v", "#2166ac"),
        (exit_ts, "5 exit (%s)" % outcome.upper(), "X", "#d73027" if outcome == "sl" else "#1a9850"),
    ]
    for ts, label, marker, color in gates:
        i = _xi(idx, ts)
        if i is None:
            continue
        y = float(bars.iloc[i]["close"])
        if "limit fill" in label:
            y = float(entry_px)
        elif "exit" in label:
            y = float(exit_px)
        elif "failed" in label.lower() or "OUT" in label:
            y = float(t.failed_extreme) if "OUT" not in label else float(bars.iloc[i]["close"])
        ax.scatter([i], [y], marker=marker, s=160, color=color, zorder=6, edgecolors="white", linewidths=0.6)
        ax.annotate(
            label,
            xy=(i, y),
            xytext=(8, 14 if "exit" not in label else -18),
            textcoords="offset points",
            fontsize=8,
            color=color,
            fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=color, lw=0.7),
        )

    hours = [i for i, ts in enumerate(idx) if ts.minute == 0]
    ax.set_xticks(hours)
    ax.set_xticklabels([idx[i].strftime("%H:%M") for i in hours])
    tag = "WIN" if outcome == "tp" else ("LOSS" if outcome == "sl" else outcome.upper())
    ax.set_title(
        "A1 close5 fade @ boundary | %s %s %s | pnl $%.0f | break=%s | R=%.2f"
        % (t.session, t.direction, tag, pnl, t.break_side, t.r)
    )
    ax.legend(loc="best", fontsize=8)
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=90)
    plt.close(fig)


def spread(items: List[pd.Series], n: int) -> List[pd.Series]:
    if len(items) <= n:
        return items
    step = len(items) / n
    return [items[int(i * step)] for i in range(n)]


def main() -> None:
    CHARTS.mkdir(parents=True, exist_ok=True)
    (CHARTS / "winners").mkdir(exist_ok=True)
    (CHARTS / "losers").mkdir(exist_ok=True)

    gby = load_gby()
    cfg = MARKETS["nq"]
    regime = set(_regime_dates(cfg, gby))
    fades = {t.trade_id: t for t in scan_close5_fades(gby, regime)}

    a1 = pd.read_csv(TRADES)
    a1 = a1[a1["variant"] == "A1_close5_fade_stop_extreme"].copy()
    a1["entry_ts"] = pd.to_datetime(a1["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    a1["exit_ts"] = pd.to_datetime(a1["exit_ts"], utc=True).dt.tz_convert("America/New_York")
    a1["year"] = a1["entry_ts"].dt.year

    wins = a1[a1["outcome"] == "tp"].sort_values(["year", "pnl_usd"], ascending=[True, False])
    losses = a1[a1["outcome"] == "sl"].sort_values(["year", "pnl_usd"], ascending=[True, True])
    # year-spread sample of 5 each
    win_rows = spread([r for _, r in wins.iterrows()], 5)
    loss_rows = spread([r for _, r in losses.iterrows()], 5)

    lines = [
        "# A1 close5-confirmed boundary fade — gate charts (stop at failed extreme)",
        "",
        "Gates on each chart:",
        "1. **touch break** (diamond) — first 1m pierce of OR",
        "2. **close5 OUT** (orange square) — 5m candle closes outside OR (break confirm, before 10:30)",
        "3. **close5 IN** (blue square) — 5m candle closes back inside within 2 candles (failure confirm)",
        "4. **limit fill @ boundary** (blue triangle) — entry at the broken OR edge",
        "5. **exit** (X) — TP at opposite boundary (green) or SL at failed extreme (red)",
        "",
        "## Winners (5)",
        "",
    ]
    for r in win_rows:
        t = fades[str(r["trade_id"])]
        path = CHARTS / "winners" / ("%s_%s_pnl%.0f.png" % (t.session, t.direction, r["pnl_usd"]))
        draw(t, gby[t.session], r["entry_px"], r["entry_ts"], r["exit_ts"], r["exit_px"], r["outcome"], r["pnl_usd"], path)
        lines.append("- `%s` %s pnl $%.0f — ![](winners/%s)" % (t.session, t.direction, r["pnl_usd"], path.name))
        print("winner", path.name, flush=True)

    lines += ["", "## Losers (5)", ""]
    for r in loss_rows:
        t = fades[str(r["trade_id"])]
        path = CHARTS / "losers" / ("%s_%s_pnl%.0f.png" % (t.session, t.direction, r["pnl_usd"]))
        draw(t, gby[t.session], r["entry_px"], r["entry_ts"], r["exit_ts"], r["exit_px"], r["outcome"], r["pnl_usd"], path)
        lines.append("- `%s` %s pnl $%.0f — ![](losers/%s)" % (t.session, t.direction, r["pnl_usd"], path.name))
        print("loser", path.name, flush=True)

    (CHARTS / "INDEX.md").write_text("\n".join(lines))
    print("charts -> %s" % CHARTS)


if __name__ == "__main__":
    main()
