"""NQ quarterly first-touch extreme playbook backtest.

One trade per quarter on the first daily touch of the prior quarter high or low:

1. failure_fade — wick through extreme, close back inside prior range.
   Market fade @ close (10). SL = adverse extreme of touch candle.
   5 off @ 15% into prior range; BE on first week-close back in range;
   5 off @ 62% into prior range.

   If the fade exits on ``stop`` or ``be_stop``, a one-shot reclaim may fire:
   significant level = original SL (sweep candle high/low). Wait for a close
   through that level (below for longs / above for shorts), then a close back
   through it → market entry same direction. New SL = prior entry ± 2× prior
   risk. Same size/exits; TP1 = new entry ± 14% of prior width; TP2 kept from
   the failed fade. At most one reclaim per quarter; ends the sequence.

2. on_level_cont — close on the extreme (tolerance).
   Limit @ close for continuation (10). SL = touch-candle adverse extreme.
   5 @ 14% extension / 5 @ 62% extension.

3. close_through_cont — close beyond the extreme.
   Limit @ extreme for continuation (10). SL = breakout-candle adverse extreme.
   5 @ 30% extension / 5 @ 62% extension.

Costs: 1-tick adverse slip on market/stop; $1.50/unit; NQ $20/pt.

Hub: ``live/state/nq_quarterly_extreme_playbook/``
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .nq_quarterly_range_retrace_study import QuarterRange, build_quarters, load_daily
from .replay_audit import POINT_VALUES
from .v2b_st_pmc_alignment_study import REPO

DEFAULT_DAILY = REPO / "nq" / "nq_daily.csv"
DEFAULT_OUT = REPO / "live" / "state" / "nq_quarterly_extreme_playbook"

TICK = 0.25
POINT_VALUE = float(POINT_VALUES["NQ"])
FEE_PER_UNIT = 1.50
ENTRY_QTY = 10
SCALE_QTY = 5
ON_LEVEL_FRAC_OF_WIDTH = 0.005
ON_LEVEL_MIN_PTS = 1.0


@dataclass
class LegFill:
    ts: str
    reason: str
    qty: int
    price: float
    pnl_pts: float
    pnl_usd: float


@dataclass
class TradeResult:
    prior_label: str
    next_label: str
    setup: str
    side: str
    extreme: str
    prior_high: float
    prior_low: float
    prior_width: float
    touch_date: str
    touch_close: float
    signal_level: float
    entry_date: str
    entry_price: float
    entry_kind: str
    stop0: float
    tp1: float
    tp2: float
    tp1_pct: float
    tp2_pct: float
    phase: str = "primary"
    parent_entry: float = 0.0
    parent_stop0: float = 0.0
    parent_risk: float = 0.0
    parent_exit_reason: str = ""
    be_armed_date: str = ""
    exit_date: str = ""
    exit_reason: str = ""
    fills: List[LegFill] = field(default_factory=list)
    qty_closed: int = 0
    net_pts: float = 0.0
    net_usd: float = 0.0
    fees_usd: float = 0.0
    mfe_pts: float = 0.0
    mae_pts: float = 0.0
    filled: bool = False
    skipped_reason: str = ""

    def as_row(self) -> Dict[str, object]:
        row = {k: v for k, v in asdict(self).items() if k != "fills"}
        row["n_fills"] = len(self.fills)
        row["fill_reasons"] = "|".join(f.reason for f in self.fills)
        return row


RECLAIM_TP1_PCT = 0.14
FADE_FAIL_EXITS = frozenset({"stop", "be_stop"})

def _on_level_tol(width: float) -> float:
    return max(ON_LEVEL_MIN_PTS, ON_LEVEL_FRAC_OF_WIDTH * float(width))


def _week_id(ts: pd.Timestamp) -> Tuple[int, int]:
    iso = ts.isocalendar()
    return int(iso[0]), int(iso[1])


def _slip(price: float, *, is_buy: bool) -> float:
    return float(price) + TICK if is_buy else float(price) - TICK


def _pnl_pts(direction: str, entry: float, exit_px: float) -> float:
    return (float(exit_px) - float(entry)) if direction == "long" else (float(entry) - float(exit_px))


def _classify_touch(
    row: pd.Series, *, prior_high: float, prior_low: float, width: float
) -> Optional[Tuple[str, str, str]]:
    hi = float(row["high"])
    lo = float(row["low"])
    cl = float(row["close"])
    tol = _on_level_tol(width)
    took_high = hi >= prior_high
    took_low = lo <= prior_low
    if not took_high and not took_low:
        return None
    if took_high and took_low:
        if (prior_low - lo) > (hi - prior_high):
            took_high = False
        else:
            took_low = False
    if took_low:
        # Downside probe of prior low.
        if cl > prior_low + tol:
            return "prior_low", "failure_fade", "long"  # close back in range → fade long
        if abs(cl - prior_low) <= tol:
            return "prior_low", "on_level_cont", "short"  # on level → continuation short
        return "prior_low", "close_through_cont", "short"  # close below → cont short
    # Upside probe of prior high.
    if cl < prior_high - tol:
        return "prior_high", "failure_fade", "short"
    if abs(cl - prior_high) <= tol:
        return "prior_high", "on_level_cont", "long"
    return "prior_high", "close_through_cont", "long"


def _targets(
    *, setup: str, direction: str, prior_high: float, prior_low: float, width: float
) -> Tuple[float, float, float, float]:
    w = float(width)
    if setup == "failure_fade":
        p1, p2 = 0.15, 0.62
        if direction == "long":
            return prior_low + p1 * w, prior_low + p2 * w, p1, p2
        return prior_high - p1 * w, prior_high - p2 * w, p1, p2
    p1, p2 = (0.14, 0.62) if setup == "on_level_cont" else (0.30, 0.62)
    if direction == "long":
        return prior_high + p1 * w, prior_high + p2 * w, p1, p2
    return prior_low - p1 * w, prior_low - p2 * w, p1, p2


def _week_end_indices(bars: pd.DataFrame) -> set:
    week_end_idx = set()
    for i in range(len(bars) - 1):
        if _week_id(pd.Timestamp(bars.iloc[i]["date"])) != _week_id(pd.Timestamp(bars.iloc[i + 1]["date"])):
            week_end_idx.add(i)
    if len(bars):
        week_end_idx.add(len(bars) - 1)
    return week_end_idx


def _manage_open_trade(
    tr: TradeResult,
    *,
    bars: pd.DataFrame,
    start_i: int,
    direction: str,
    entry: float,
    stop0: float,
    tp1: float,
    tp2: float,
    prior_high: float,
    prior_low: float,
    allow_be: bool,
) -> None:
    stop = float(stop0)
    qty = ENTRY_QTY
    tp1_done = False
    be_done = False
    mfe = 0.0
    mae = 0.0
    week_end_idx = _week_end_indices(bars)

    def close_qty(row: pd.Series, reason: str, px: float, q: int, *, slipped: bool) -> None:
        nonlocal qty
        if q <= 0:
            return
        fill_px = _slip(px, is_buy=(direction == "short")) if slipped else float(px)
        pts = _pnl_pts(direction, entry, fill_px)
        fee = FEE_PER_UNIT * q
        usd = pts * POINT_VALUE * q - fee
        tr.fills.append(
            LegFill(
                ts=str(pd.Timestamp(row["date"]).date()),
                reason=reason,
                qty=int(q),
                price=float(fill_px),
                pnl_pts=float(pts * q),
                pnl_usd=float(usd),
            )
        )
        tr.net_pts += pts * q
        tr.net_usd += usd
        tr.fees_usd += fee
        tr.qty_closed += int(q)
        qty -= int(q)
        tr.exit_date = str(pd.Timestamp(row["date"]).date())
        tr.exit_reason = reason

    for j in range(int(start_i), len(bars)):
        if qty <= 0:
            break
        row = bars.iloc[j]
        hi = float(row["high"])
        lo = float(row["low"])
        cl = float(row["close"])
        if direction == "long":
            mfe = max(mfe, hi - entry)
            mae = min(mae, lo - entry)
        else:
            mfe = max(mfe, entry - lo)
            mae = min(mae, entry - hi)

        stop_hit = (direction == "long" and lo <= stop) or (direction == "short" and hi >= stop)
        if stop_hit:
            if direction == "long":
                raw = min(float(row["open"]), stop) if float(row["open"]) < stop else stop
            else:
                raw = max(float(row["open"]), stop) if float(row["open"]) > stop else stop
            reason = "be_stop" if be_done and abs(stop - entry) < 1e-9 else "stop"
            close_qty(row, reason, raw, qty, slipped=True)
            break

        if not tp1_done and qty >= SCALE_QTY:
            tp1_hit = (direction == "long" and hi >= tp1) or (direction == "short" and lo <= tp1)
            if tp1_hit:
                close_qty(row, "tp1", tp1, SCALE_QTY, slipped=False)
                tp1_done = True
                if qty <= 0:
                    break

        tp2_hit = (direction == "long" and hi >= tp2) or (direction == "short" and lo <= tp2)
        if tp2_hit and qty > 0:
            close_qty(row, "tp2", tp2, qty, slipped=False)
            break

        if allow_be and not be_done and j in week_end_idx and qty > 0:
            if prior_low <= cl <= prior_high:
                stop = entry
                be_done = True
                tr.be_armed_date = str(pd.Timestamp(row["date"]).date())

    tr.mfe_pts = float(mfe)
    tr.mae_pts = float(mae)
    if qty > 0 and tr.filled:
        close_qty(bars.iloc[-1], "quarter_eod", float(bars.iloc[-1]["close"]), qty, slipped=True)


def simulate_trade(
    *,
    prior: QuarterRange,
    nxt: QuarterRange,
    touch_row: pd.Series,
    next_bars: pd.DataFrame,
    setup: str,
    direction: str,
    extreme: str,
) -> TradeResult:
    width = prior.width
    prior_high, prior_low = prior.high, prior.low
    touch_date = str(pd.Timestamp(touch_row["date"]).date())
    touch_close = float(touch_row["close"])
    level = prior_low if extreme == "prior_low" else prior_high
    stop0 = float(touch_row["low"]) if direction == "long" else float(touch_row["high"])
    tp1, tp2, tp1_pct, tp2_pct = _targets(
        setup=setup, direction=direction, prior_high=prior_high, prior_low=prior_low, width=width
    )
    tr = TradeResult(
        prior_label=prior.label,
        next_label=nxt.label,
        setup=setup,
        side=direction,
        extreme=extreme,
        prior_high=prior_high,
        prior_low=prior_low,
        prior_width=width,
        touch_date=touch_date,
        touch_close=touch_close,
        signal_level=float(level),
        entry_date="",
        entry_price=0.0,
        entry_kind="",
        stop0=stop0,
        tp1=tp1,
        tp2=tp2,
        tp1_pct=tp1_pct,
        tp2_pct=tp2_pct,
        phase="primary",
    )

    bars = next_bars.sort_values("date").reset_index(drop=True)
    touch_idx = bars.index[bars["date"] == touch_row["date"]]
    if len(touch_idx) == 0:
        tr.skipped_reason = "touch_bar_missing"
        return tr
    t_i = int(touch_idx[0])

    if setup == "failure_fade":
        tr.entry_price = _slip(touch_close, is_buy=(direction == "long"))
        tr.entry_date = touch_date
        tr.entry_kind = "market_close"
        tr.filled = True
        start_i = t_i + 1
    else:
        limit_px = touch_close if setup == "on_level_cont" else float(level)
        tr.entry_kind = "limit"
        tr.signal_level = float(limit_px)
        start_i = None
        for j in range(t_i + 1, len(bars)):
            row = bars.iloc[j]
            if direction == "long" and float(row["low"]) <= limit_px:
                raw = min(float(row["open"]), limit_px) if float(row["open"]) < limit_px else limit_px
                tr.entry_price = _slip(raw, is_buy=True)
                tr.entry_date = str(pd.Timestamp(row["date"]).date())
                tr.filled = True
                start_i = j  # same-bar management after fill
                break
            if direction == "short" and float(row["high"]) >= limit_px:
                raw = max(float(row["open"]), limit_px) if float(row["open"]) > limit_px else limit_px
                tr.entry_price = _slip(raw, is_buy=False)
                tr.entry_date = str(pd.Timestamp(row["date"]).date())
                tr.filled = True
                start_i = j
                break
        if not tr.filled or start_i is None:
            tr.skipped_reason = "limit_unfilled"
            tr.exit_reason = "limit_unfilled"
            return tr

    _manage_open_trade(
        tr,
        bars=bars,
        start_i=int(start_i),
        direction=direction,
        entry=float(tr.entry_price),
        stop0=float(stop0),
        tp1=float(tp1),
        tp2=float(tp2),
        prior_high=prior_high,
        prior_low=prior_low,
        allow_be=(setup == "failure_fade"),
    )
    return tr


def simulate_failure_fade_reclaim(
    *,
    prior: QuarterRange,
    nxt: QuarterRange,
    next_bars: pd.DataFrame,
    parent: TradeResult,
) -> TradeResult:
    """One-shot reclaim after a failed failure_fade (stop or be_stop).

    Significant level = original fade SL (sweep candle extreme). Longs wait for
    close below then close back above → market buy; shorts the mirror. New SL is
    2× prior risk from the prior entry. TP1 from new entry at 14% of prior width;
    TP2 kept from the failed fade.
    """
    direction = parent.side
    width = float(prior.width)
    prior_high, prior_low = prior.high, prior.low
    reclaim_level = float(parent.stop0)
    parent_entry = float(parent.entry_price)
    risk = abs(parent_entry - reclaim_level)
    if direction == "long":
        stop0 = parent_entry - 2.0 * risk
    else:
        stop0 = parent_entry + 2.0 * risk
    tp2 = float(parent.tp2)
    # TP1 placeholder until entry known; filled after signal.
    tr = TradeResult(
        prior_label=prior.label,
        next_label=nxt.label,
        setup="failure_fade_reclaim",
        side=direction,
        extreme=parent.extreme,
        prior_high=prior_high,
        prior_low=prior_low,
        prior_width=width,
        touch_date=parent.touch_date,
        touch_close=parent.touch_close,
        signal_level=reclaim_level,
        entry_date="",
        entry_price=0.0,
        entry_kind="market_close_reclaim",
        stop0=float(stop0),
        tp1=0.0,
        tp2=tp2,
        tp1_pct=RECLAIM_TP1_PCT,
        tp2_pct=float(parent.tp2_pct),
        phase="reclaim",
        parent_entry=parent_entry,
        parent_stop0=reclaim_level,
        parent_risk=float(risk),
        parent_exit_reason=str(parent.exit_reason),
    )
    if risk < 1e-12:
        tr.skipped_reason = "zero_parent_risk"
        return tr

    bars = next_bars.sort_values("date").reset_index(drop=True)
    if not parent.exit_date:
        tr.skipped_reason = "parent_no_exit"
        return tr
    exit_mask = bars["date"] == pd.Timestamp(parent.exit_date)
    if not exit_mask.any():
        tr.skipped_reason = "parent_exit_bar_missing"
        return tr
    start_scan = int(bars.index[exit_mask][0])  # include exit bar for pierce/reclaim

    pierced = False
    entry_i = None
    for j in range(start_scan, len(bars)):
        cl = float(bars.iloc[j]["close"])
        if not pierced:
            if direction == "long" and cl < reclaim_level:
                pierced = True
            elif direction == "short" and cl > reclaim_level:
                pierced = True
            continue
        # Already pierced: wait for close back through the level.
        if direction == "long" and cl > reclaim_level:
            entry_i = j
            break
        if direction == "short" and cl < reclaim_level:
            entry_i = j
            break

    if entry_i is None:
        tr.skipped_reason = "reclaim_unfilled"
        tr.exit_reason = "reclaim_unfilled"
        return tr

    entry_row = bars.iloc[int(entry_i)]
    entry_close = float(entry_row["close"])
    tr.entry_price = _slip(entry_close, is_buy=(direction == "long"))
    tr.entry_date = str(pd.Timestamp(entry_row["date"]).date())
    tr.filled = True
    if direction == "long":
        tr.tp1 = float(tr.entry_price) + RECLAIM_TP1_PCT * width
    else:
        tr.tp1 = float(tr.entry_price) - RECLAIM_TP1_PCT * width

    _manage_open_trade(
        tr,
        bars=bars,
        start_i=int(entry_i) + 1,
        direction=direction,
        entry=float(tr.entry_price),
        stop0=float(stop0),
        tp1=float(tr.tp1),
        tp2=float(tp2),
        prior_high=prior_high,
        prior_low=prior_low,
        allow_be=True,
    )
    return tr


def run_backtest(daily: pd.DataFrame, quarters: Sequence[QuarterRange]) -> List[TradeResult]:
    trades: List[TradeResult] = []
    for i in range(len(quarters) - 1):
        prior = quarters[i]
        nxt = quarters[i + 1]
        if prior.width <= 0:
            continue
        next_bars = (
            daily[(daily["year"] == nxt.year) & (daily["quarter"] == nxt.quarter)]
            .sort_values("date")
            .reset_index(drop=True)
        )
        if next_bars.empty:
            continue
        chosen = None
        for _, row in next_bars.iterrows():
            cls = _classify_touch(row, prior_high=prior.high, prior_low=prior.low, width=prior.width)
            if cls is None:
                continue
            chosen = (row, cls[0], cls[1], cls[2])
            break
        if chosen is None:
            trades.append(
                TradeResult(
                    prior_label=prior.label,
                    next_label=nxt.label,
                    setup="none",
                    side="",
                    extreme="",
                    prior_high=prior.high,
                    prior_low=prior.low,
                    prior_width=prior.width,
                    touch_date="",
                    touch_close=0.0,
                    signal_level=0.0,
                    entry_date="",
                    entry_price=0.0,
                    entry_kind="",
                    stop0=0.0,
                    tp1=0.0,
                    tp2=0.0,
                    tp1_pct=0.0,
                    tp2_pct=0.0,
                    skipped_reason="no_touch",
                    exit_reason="no_touch",
                )
            )
            continue
        row, extreme, setup, direction = chosen
        primary = simulate_trade(
            prior=prior,
            nxt=nxt,
            touch_row=row,
            next_bars=next_bars,
            setup=setup,
            direction=direction,
            extreme=extreme,
        )
        trades.append(primary)
        if (
            setup == "failure_fade"
            and primary.filled
            and primary.exit_reason in FADE_FAIL_EXITS
        ):
            reclaim = simulate_failure_fade_reclaim(
                prior=prior, nxt=nxt, next_bars=next_bars, parent=primary
            )
            trades.append(reclaim)
    return trades


def _metrics(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {
            "n": 0,
            "net_usd": 0.0,
            "win_rate": 0.0,
            "avg_usd": 0.0,
            "profit_factor": 0.0,
            "max_dd_usd": 0.0,
            "net_stress": 0.0,
        }
    net = float(df["net_usd"].sum())
    wins = df.loc[df["net_usd"] > 0, "net_usd"]
    losses = df.loc[df["net_usd"] <= 0, "net_usd"]
    gw = float(wins.sum()) if len(wins) else 0.0
    gl = float((-losses).sum()) if len(losses) else 0.0
    pf = (gw / gl) if gl > 1e-9 else (999.0 if gw > 0 else 0.0)
    eq = df["net_usd"].cumsum()
    dd = float((eq - eq.cummax()).min()) if len(eq) else 0.0
    stress = abs(dd) if dd < 0 else 0.0
    return {
        "n": int(len(df)),
        "net_usd": net,
        "win_rate": float((df["net_usd"] > 0).mean() * 100.0),
        "avg_usd": float(df["net_usd"].mean()),
        "profit_factor": float(pf),
        "max_dd_usd": float(dd),
        "net_stress": (net / stress) if stress > 1e-9 else 0.0,
    }


def write_reports(output_root: Path, trades: Sequence[TradeResult], daily_path: Path) -> None:
    all_df = pd.DataFrame([t.as_row() for t in trades])
    all_df.to_csv(output_root / "trades_all_quarters.csv", index=False)
    filled = all_df[all_df["filled"] == True].copy()  # noqa: E712
    filled.to_csv(output_root / "trades.csv", index=False)
    m = _metrics(filled)
    setups = ("failure_fade", "failure_fade_reclaim", "on_level_cont", "close_through_cont")
    lines = [
        "# NQ Quarterly Extreme Playbook Backtest",
        "",
        "First daily touch of prior-quarter high/low → **one primary trade per quarter** "
        "(plus optional one-shot `failure_fade_reclaim` after a failed fade).",
        "",
        f"- Daily: `{daily_path}`",
        f"- Quarter rows (primary): **{int((all_df['phase'] == 'primary').sum())}**",
        f"- Filled legs: **{len(filled)}**",
        f"- No touch: **{int((all_df['skipped_reason'] == 'no_touch').sum())}**",
        f"- Limit unfilled: **{int((all_df['skipped_reason'] == 'limit_unfilled').sum())}**",
        f"- Reclaim unfilled: **{int((all_df['skipped_reason'] == 'reclaim_unfilled').sum())}**",
        "",
        "## Rules",
        "",
        "1. **failure_fade** — wick through, close back in range → market fade @ close; "
        "SL = touch adverse extreme; 5 @ 15% into range; BE on first week-close in range; 5 @ 62%.",
        "   - **Reclaim (once, only if fade exits `stop`/`be_stop`):** significant level = original SL "
        "(sweep H/L). Wait close through then close back → market same direction. "
        "SL = prior entry ± 2× prior risk. Same 10/5/5 exits; TP1 = new entry ± 14% of prior width; "
        "TP2 kept from the failed fade. Sequence ends after this leg.",
        "2. **on_level_cont** — close on extreme (±0.5% of prior width, min 1pt) → limit @ close; "
        "5 @ 14% ext / 5 @ 62% ext.",
        "3. **close_through_cont** — close beyond extreme → limit @ extreme; 5 @ 30% / 5 @ 62% ext.",
        "",
        "Costs: 1-tick adverse slip on market/stop; $1.50/unit; NQ $20/pt. Stop before targets same bar.",
        "",
        "## Overall (filled legs)",
        "",
        f"- N: **{m['n']}**",
        f"- Net: **${m['net_usd']:,.2f}**",
        f"- Win%: **{m['win_rate']:.1f}%**",
        f"- Avg/trade: **${m['avg_usd']:,.2f}**",
        f"- PF: **{m['profit_factor']:.2f}**",
        f"- Max DD (trade equity): **${m['max_dd_usd']:,.2f}**",
        f"- Net/|DD|: **{m['net_stress']:.2f}**",
        "",
        "## By setup",
        "",
        "| Setup | N | Net $ | Win% | Avg $ | PF | MaxDD $ | Net/|DD| |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for setup in setups:
        sm = _metrics(filled[filled["setup"] == setup] if not filled.empty else filled)
        lines.append(
            "| %s | %d | %.2f | %.1f | %.2f | %.2f | %.2f | %.2f |"
            % (setup, sm["n"], sm["net_usd"], sm["win_rate"], sm["avg_usd"], sm["profit_factor"], sm["max_dd_usd"], sm["net_stress"])
        )

    # Fade sequence = primary fade + optional reclaim, aggregated by next_label.
    fade_legs = filled[filled["setup"].isin(["failure_fade", "failure_fade_reclaim"])].copy() if not filled.empty else filled
    if not fade_legs.empty:
        seq = (
            fade_legs.groupby("next_label", as_index=False)
            .agg(net_usd=("net_usd", "sum"), n_legs=("net_usd", "count"), setups=("setup", lambda s: "|".join(s)))
        )
        sm = _metrics(seq.rename(columns={"net_usd": "net_usd"}))
        # _metrics expects net_usd column — seq already has it
        sm = _metrics(seq)
        lines.extend(
            [
                "",
                "## failure_fade sequence (primary ± reclaim, by quarter)",
                "",
                f"- Sequences with any filled fade leg: **{sm['n']}**",
                f"- Combined net: **${sm['net_usd']:,.2f}**",
                f"- Win% (sequence): **{sm['win_rate']:.1f}%**",
                f"- PF: **{sm['profit_factor']:.2f}**",
                f"- Max DD: **${sm['max_dd_usd']:,.2f}**",
                f"- Net/|DD|: **{sm['net_stress']:.2f}**",
                f"- Quarters that filled a reclaim: **{int((fade_legs['setup'] == 'failure_fade_reclaim').sum())}**",
            ]
        )

    lines.extend(["", "## By side", "", "| Side | N | Net $ | Win% | PF |", "|---|---:|---:|---:|---:|"])
    for side in ("long", "short"):
        sm = _metrics(filled[filled["side"] == side] if not filled.empty else filled)
        lines.append("| %s | %d | %.2f | %.1f | %.2f |" % (side, sm["n"], sm["net_usd"], sm["win_rate"], sm["profit_factor"]))
    if not filled.empty:
        lines.extend(["", "## Exit mix", ""])
        for reason, n in filled["exit_reason"].value_counts().items():
            lines.append(f"- `{reason}`: **{int(n)}**")
        filled = filled.copy()
        filled["next_year"] = filled["next_label"].str.slice(0, 4).astype(int)
        lines.extend(["", "## By year (next quarter)", "", "| Year | N | Net $ | Win% |", "|---:|---:|---:|---:|"])
        for y, g in filled.groupby("next_year"):
            sm = _metrics(g)
            lines.append("| %d | %d | %.2f | %.1f |" % (y, sm["n"], sm["net_usd"], sm["win_rate"]))
    lines.extend(["", "## Files", "", "- `trades.csv`", "- `trades_all_quarters.csv`", ""])
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    email = [
        "NQ quarterly extreme playbook backtest complete (with failure_fade reclaim).",
        "",
        "Hub: %s" % output_root,
        "Filled legs: %d" % m["n"],
        "Net: $%.2f | Win%%: %.1f | PF: %.2f | MaxDD: $%.2f | N/S: %.2f"
        % (m["net_usd"], m["win_rate"], m["profit_factor"], m["max_dd_usd"], m["net_stress"]),
        "",
    ]
    for setup in setups:
        sm = _metrics(filled[filled["setup"] == setup] if not filled.empty else filled)
        email.append("%s: n=%d net=$%.2f win=%.1f%% PF=%.2f" % (setup, sm["n"], sm["net_usd"], sm["win_rate"], sm["profit_factor"]))
    if not fade_legs.empty:
        seq = fade_legs.groupby("next_label", as_index=False).agg(net_usd=("net_usd", "sum"))
        sm = _metrics(seq)
        email.append(
            "failure_fade sequence: n=%d net=$%.2f win=%.1f%% PF=%.2f N/S=%.2f"
            % (sm["n"], sm["net_usd"], sm["win_rate"], sm["profit_factor"], sm["net_stress"])
        )
    email.extend(["", "SUMMARY: %s" % (output_root / "SUMMARY.md")])
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run(daily_path: Path, output_root: Path, *, email: bool = False) -> int:
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    daily = load_daily(daily_path)
    quarters = build_quarters(daily)
    trades = run_backtest(daily, quarters)
    write_reports(output_root, trades, daily_path)
    filled_n = sum(1 for t in trades if t.filled)
    net = sum(t.net_usd for t in trades if t.filled)
    print("Wrote %s filled=%d net=$%.2f" % (output_root / "SUMMARY.md", filled_n, net), flush=True)
    if email:
        from .notify_email import send_email

        send_email(
            subject="potions: NQ quarterly extreme playbook complete (net $%.0f)" % net,
            body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
        )
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        return run(args.daily, args.output_root, email=bool(args.email))
    except Exception as exc:
        if args.email:
            try:
                from .notify_email import send_email

                send_email(
                    subject="potions: NQ quarterly extreme playbook FAILED",
                    body="Hub: %s\nError: %s\n" % (args.output_root, exc),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
