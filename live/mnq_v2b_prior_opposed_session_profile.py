from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .mnq_v2b_prior_opposed_15m_charts import NY, resample_15m
from .v2b_st_pmc_alignment_study import REPO
from .v2b_strategy_cross_market_replay import MARKETS, _rth_bars, load_1m_by_ny_date_any


TICK = 0.25


@dataclass
class CandleView:
    idx: int
    ts: pd.Timestamp
    open: float
    high: float
    low: float
    close: float


@dataclass
class OrLevels:
    high: float
    low: float

    @property
    def range(self) -> float:
        return self.high - self.low

    def long_trigger(self) -> float:
        return self.high + TICK

    def short_trigger(self) -> float:
        return self.low - TICK

    def target_1r_long(self) -> float:
        return self.high + self.range

    def target_2r_long(self) -> float:
        return self.high + 2.0 * self.range

    def target_1r_short(self) -> float:
        return self.low - self.range

    def target_2r_short(self) -> float:
        return self.low - 2.0 * self.range


@dataclass
class SessionProfile:
    idx: int
    session: str
    side: str
    net_usd: float
    outcome: str
    trade_id: str
    chart: str
    tags: List[str] = field(default_factory=list)
    narrative: str = ""
    break_candle: int = 0
    entry_candle: int = 0
    tp1_candle: int = 0
    tp2_candle: int = 0
    or_retest_after_break: bool = False
    opposite_break_2r_before_entry: bool = False
    failed_same_side_before_entry: bool = False


def opening_range(rth: pd.DataFrame) -> Optional[OrLevels]:
    opening = rth[
        (rth.index.time >= time(9, 30))
        & (rth.index.time < time(9, 45))
    ]
    if opening.empty:
        return None
    return OrLevels(high=float(opening["high"].max()), low=float(opening["low"].min()))


def post_or_candles(rth: pd.DataFrame) -> List[CandleView]:
    c15 = resample_15m(rth)
    c15 = c15[c15.index.time >= time(9, 45)]
    out: List[CandleView] = []
    for i, (ts, row) in enumerate(c15.iterrows(), start=1):
        out.append(
            CandleView(
                idx=i,
                ts=pd.Timestamp(ts),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
        )
    return out


def candle_hits_long_break(c: CandleView, or_: OrLevels) -> bool:
    return c.high >= or_.long_trigger()


def candle_hits_short_break(c: CandleView, or_: OrLevels) -> bool:
    return c.low <= or_.short_trigger()


def candle_closes_above_or(c: CandleView, or_: OrLevels) -> bool:
    return c.close > or_.high


def candle_closes_below_or(c: CandleView, or_: OrLevels) -> bool:
    return c.close < or_.low


def candle_hits_1r_long(c: CandleView, or_: OrLevels) -> bool:
    return c.high >= or_.target_1r_long()


def candle_hits_2r_long(c: CandleView, or_: OrLevels) -> bool:
    return c.high >= or_.target_2r_long()


def candle_hits_1r_short(c: CandleView, or_: OrLevels) -> bool:
    return c.low <= or_.target_1r_short()


def candle_hits_2r_short(c: CandleView, or_: OrLevels) -> bool:
    return c.low <= or_.target_2r_short()


def first_break(
    candles: Sequence[CandleView],
    or_: OrLevels,
    side: str,
    *,
    until_idx: Optional[int] = None,
) -> Optional[CandleView]:
    for c in candles:
        if until_idx is not None and c.idx > until_idx:
            break
        if side == "long" and candle_hits_long_break(c, or_):
            return c
        if side == "short" and candle_hits_short_break(c, or_):
            return c
    return None


def first_close_break(candles: Sequence[CandleView], or_: OrLevels, side: str) -> Optional[CandleView]:
    for c in candles:
        if side == "long" and candle_closes_above_or(c, or_):
            return c
        if side == "short" and candle_closes_below_or(c, or_):
            return c
    return None


def failed_break_before(
    candles: Sequence[CandleView],
    or_: OrLevels,
    side: str,
    before_ts: pd.Timestamp,
) -> bool:
    """Break in side, then close back inside OR before 1R, before cutoff."""
    subset = [c for c in candles if c.ts < before_ts]
    brk = first_break(subset, or_, side)
    if brk is None:
        return False
    after = [c for c in subset if c.idx > brk.idx]
    hit_1r = False
    for c in after:
        if side == "long" and candle_hits_1r_long(c, or_):
            hit_1r = True
            break
        if side == "short" and candle_hits_1r_short(c, or_):
            hit_1r = True
            break
        if side == "long" and c.close < or_.low:
            return True
        if side == "short" and c.close > or_.high:
            return True
    return not hit_1r and any(
        (side == "long" and c.close <= or_.high)
        or (side == "short" and c.close >= or_.low)
        for c in after
    )


def opposite_reached_2r_before(
    candles: Sequence[CandleView],
    or_: OrLevels,
    trade_side: str,
    before_ts: pd.Timestamp,
) -> bool:
    opp = "short" if trade_side == "long" else "long"
    subset = [c for c in candles if c.ts < before_ts]
    brk = first_break(subset, or_, opp)
    if brk is None:
        return False
    for c in subset:
        if c.idx < brk.idx:
            continue
        if opp == "long" and candle_hits_2r_long(c, or_):
            return True
        if opp == "short" and candle_hits_2r_short(c, or_):
            return True
    return False


def or_boundary_retest_after_break(
    candles: Sequence[CandleView],
    or_: OrLevels,
    side: str,
    from_idx: int,
    until_ts: pd.Timestamp,
) -> bool:
    for c in candles:
        if c.idx <= from_idx or c.ts > until_ts:
            continue
        if side == "long" and c.low <= or_.high:
            return True
        if side == "short" and c.high >= or_.low:
            return True
    return False


def hit_r_levels(
    candles: Sequence[CandleView],
    or_: OrLevels,
    side: str,
    from_idx: int,
    until_ts: pd.Timestamp,
) -> Tuple[int, int]:
    tp1 = 0
    tp2 = 0
    for c in candles:
        if c.idx < from_idx or c.ts > until_ts:
            continue
        if side == "long":
            if tp1 == 0 and candle_hits_1r_long(c, or_):
                tp1 = c.idx
            if tp2 == 0 and candle_hits_2r_long(c, or_):
                tp2 = c.idx
        else:
            if tp1 == 0 and candle_hits_1r_short(c, or_):
                tp1 = c.idx
            if tp2 == 0 and candle_hits_2r_short(c, or_):
                tp2 = c.idx
    return tp1, tp2


def deep_retrace_after_break(
    candles: Sequence[CandleView],
    or_: OrLevels,
    side: str,
    break_idx: int,
    until_ts: pd.Timestamp,
) -> bool:
    """Pullback to ~60% of OR→1R extension (or back through OR boundary)."""
    if side == "long":
        anchor = or_.high
        ext = or_.target_1r_long() - or_.high
        threshold = anchor + 0.4 * ext
        for c in candles:
            if c.idx <= break_idx or c.ts > until_ts:
                continue
            if c.low <= threshold or c.low <= or_.high:
                return True
    else:
        anchor = or_.low
        ext = or_.low - or_.target_1r_short()
        threshold = anchor - 0.4 * ext
        for c in candles:
            if c.idx <= break_idx or c.ts > until_ts:
                continue
            if c.high >= threshold or c.high >= or_.low:
                return True
    return False


def inside_or_session(
    candles: Sequence[CandleView],
    or_: OrLevels,
    until_ts: pd.Timestamp,
) -> bool:
    subset = [c for c in candles if c.ts <= until_ts]
    any_close_out = any(candle_closes_above_or(c, or_) or candle_closes_below_or(c, or_) for c in subset)
    return not any_close_out


def candle_for_ts(candles: Sequence[CandleView], ts: pd.Timestamp) -> int:
    for c in candles:
        if c.ts >= ts:
            return c.idx
    return len(candles)


def load_tp_exit_times(unit_trades: Path, trade_id: str) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    tp1_ts: Optional[pd.Timestamp] = None
    tp2_ts: Optional[pd.Timestamp] = None
    with unit_trades.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if row.get("trade_id") != trade_id:
                continue
            reason = str(row.get("exit_reason", ""))
            ts = pd.to_datetime(row["exit_ts"], utc=True).tz_convert(NY)
            if reason == "tp1" and tp1_ts is None:
                tp1_ts = ts
            if reason == "tp2" and tp2_ts is None:
                tp2_ts = ts
    return tp1_ts, tp2_ts


def build_narrative(
    *,
    side: str,
    outcome: str,
    net_usd: float,
    break_c: Optional[CandleView],
    close_break_c: Optional[CandleView],
    entry_candle: int,
    tp1_candle: int,
    tp2_candle: int,
    or_retest: bool,
    deep_retrace: bool,
    inside_or: bool,
    failed_same_before: bool,
    opposite_2r_before: bool,
    opposite_side: str,
    wick_only_break: bool,
    runner_only: bool,
    eod_no_1r: bool,
) -> Tuple[str, List[str]]:
    tags: List[str] = []
    parts: List[str] = []

    pre_bits: List[str] = []
    if failed_same_before and opposite_2r_before:
        tags.append("failed_same_then_opposite_2r")
        pre_bits.append(
            "Before entry: failed %s break, then opposite %s reached ~2R"
            % (side, opposite_side)
        )
    elif failed_same_before:
        tags.append("failed_same_side_break")
        pre_bits.append("Before entry: failed %s OR break" % side)
    elif opposite_2r_before:
        tags.append("opposite_2r_before_entry")
        pre_bits.append("Before entry: opposite %s reached ~2R" % opposite_side)
    if pre_bits:
        parts.extend(pre_bits)

    if break_c is not None:
        ord_label = {1: "1st", 2: "2nd", 3: "3rd"}.get(break_c.idx, "%dth" % break_c.idx)
        brk = "%s break on %s 15m candle" % (side, ord_label)
        if wick_only_break and close_break_c is None:
            tags.append("wick_only_break")
            brk += " (wick through OR, no close outside)"
        elif wick_only_break:
            tags.append("wick_then_close_break")
            brk += " (wick first, close outside later)"
        parts.insert(0, brk)
    else:
        tags.append("no_clear_break")
        parts.insert(0, "No clean %s OR break on 15m before exit" % side)

    if inside_or:
        tags.append("inside_or")
        parts.append("Price mostly stayed inside OR (no 15m close outside range through exit)")

    if or_retest:
        tags.append("or_boundary_retest")
        parts.append("OR boundary retested after initial break")
    else:
        tags.append("no_or_retest")
        parts.append("OR boundary not retested on subsequent 15m candles")

    if deep_retrace:
        tags.append("deep_retrace")
        parts.append("Deep retracement (~60% of OR→1R) after break")

    if tp1_candle:
        tags.append("hit_1r")
        parts.append("1R on %s 15m candle" % ({1: "1st", 2: "2nd", 3: "3rd"}.get(tp1_candle, "%dth" % tp1_candle)))
    if tp2_candle:
        tags.append("hit_2r")
        parts.append("2R on %s 15m candle" % ({1: "1st", 2: "2nd", 3: "3rd"}.get(tp2_candle, "%dth" % tp2_candle)))
    if not tp1_candle and not inside_or:
        tags.append("no_1r")
    if eod_no_1r:
        tags.append("eod_without_1r")
        parts.append("Session ended without 1R hit on 15m")

    if runner_only and outcome == "win":
        tags.append("runner_stop_after_tp")
        parts.append("Runner stopped after partial take-profit")

    parts.append("Trade %s $%.0f" % (outcome.upper(), net_usd))
    return ". ".join(parts) + ".", tags


def profile_campaign(
    *,
    idx: int,
    row: pd.Series,
    candles: Sequence[CandleView],
    or_: OrLevels,
    unit_trades: Path,
    chart_rel: str,
) -> SessionProfile:
    side = str(row["side"]).lower()
    entry_ts = pd.to_datetime(row["entry_ts"], utc=True).tz_convert(NY)
    exit_ts = pd.to_datetime(row["exit_ts"], utc=True).tz_convert(NY)
    net = float(row["base_1_1_3_net"])
    outcome = "win" if net > 0 else "loss"
    opposite_side = "short" if side == "long" else "long"

    until = exit_ts
    entry_candle = candle_for_ts(candles, entry_ts)
    pre_entry = [c for c in candles if c.idx <= entry_candle]
    brk = first_break(pre_entry, or_, side, until_idx=entry_candle)
    close_brk = first_close_break(pre_entry, or_, side)
    wick_only = brk is not None and (close_brk is None or close_brk.idx > brk.idx)

    break_idx = brk.idx if brk else 0
    tp1_candle, tp2_candle = hit_r_levels(candles, or_, side, break_idx or 1, until)

    tp1_ts, tp2_ts = load_tp_exit_times(unit_trades, str(row["trade_id"]))
    if tp1_ts is not None:
        tp1_candle = candle_for_ts(candles, tp1_ts) or tp1_candle
    if tp2_ts is not None:
        tp2_candle = candle_for_ts(candles, tp2_ts) or tp2_candle

    or_retest = (
        or_boundary_retest_after_break(candles, or_, side, break_idx, until) if break_idx else False
    )
    deep_retrace = deep_retrace_after_break(candles, or_, side, break_idx, until) if break_idx else False
    inside_or = inside_or_session(candles, or_, until)
    failed_same = failed_break_before(candles, or_, side, entry_ts)
    opposite_2r = opposite_reached_2r_before(candles, or_, side, entry_ts)

    tp1_hit = float(row.get("tp1_unit_usd", 0) or 0) != 0
    eod_no_1r = not tp1_hit and not inside_or
    runner_only = tp1_hit and float(row.get("tp2_unit_usd", 0) or 0) == 0 and net > 0

    narrative, tags = build_narrative(
        side=side,
        outcome=outcome,
        net_usd=net,
        break_c=brk,
        close_break_c=close_brk,
        entry_candle=entry_candle,
        tp1_candle=tp1_candle,
        tp2_candle=tp2_candle,
        or_retest=or_retest,
        deep_retrace=deep_retrace,
        inside_or=inside_or,
        failed_same_before=failed_same,
        opposite_2r_before=opposite_2r,
        opposite_side=opposite_side,
        wick_only_break=wick_only,
        runner_only=runner_only,
        eod_no_1r=eod_no_1r,
    )

    return SessionProfile(
        idx=idx,
        session=str(row["session"]),
        side=side,
        net_usd=net,
        outcome=outcome,
        trade_id=str(row["trade_id"]),
        chart=chart_rel,
        tags=tags,
        narrative=narrative,
        break_candle=break_idx,
        entry_candle=entry_candle,
        tp1_candle=tp1_candle,
        tp2_candle=tp2_candle,
        or_retest_after_break=or_retest,
        opposite_break_2r_before_entry=opposite_2r,
        failed_same_side_before_entry=failed_same,
    )


def write_outputs(output_root: Path, profiles: Sequence[SessionProfile]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)

    csv_path = output_root / "session_profiles.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=[
                "idx",
                "session",
                "side",
                "outcome",
                "net_usd",
                "trade_id",
                "chart",
                "break_candle",
                "entry_candle",
                "tp1_candle",
                "tp2_candle",
                "or_retest_after_break",
                "opposite_break_2r_before_entry",
                "failed_same_side_before_entry",
                "tags",
                "narrative",
            ],
        )
        writer.writeheader()
        for p in profiles:
            writer.writerow(
                {
                    "idx": p.idx,
                    "session": p.session,
                    "side": p.side,
                    "outcome": p.outcome,
                    "net_usd": f"{p.net_usd:.2f}",
                    "trade_id": p.trade_id,
                    "chart": p.chart,
                    "break_candle": p.break_candle,
                    "entry_candle": p.entry_candle,
                    "tp1_candle": p.tp1_candle,
                    "tp2_candle": p.tp2_candle,
                    "or_retest_after_break": int(p.or_retest_after_break),
                    "opposite_break_2r_before_entry": int(p.opposite_break_2r_before_entry),
                    "failed_same_side_before_entry": int(p.failed_same_side_before_entry),
                    "tags": "|".join(p.tags),
                    "narrative": p.narrative,
                }
            )

    lines = [
        "# MNQ v2b Prior-Opposed Session Timeline",
        "",
        "Automated 15m OR-structure profiles for the same campaigns as "
        "`charts/prior_opposed_15m/`. Narratives mirror the manual chart-review "
        "style (break candle, OR retest, 1R/2R timing, failed/opposite breaks). "
        "No inference — chronological display only.",
        "",
        "| Session | W/L | Side | Net | Break | 1R | 2R | OR retest | Pattern |",
        "|---|---|---|---:|---:|---:|---:|---|---|",
    ]
    for p in profiles:
        lines.append(
            "| {session} | {wl} | {side} | ${net:,.0f} | {brk} | {tp1} | {tp2} | {rt} | {pat} |".format(
                session=p.session,
                wl=p.outcome.upper()[:1],
                side=p.side,
                net=p.net_usd,
                brk=p.break_candle or "-",
                tp1=p.tp1_candle or "-",
                tp2=p.tp2_candle or "-",
                rt="Y" if p.or_retest_after_break else "N",
                pat=p.narrative.replace("|", "/"),
            )
        )
    (output_root / "TIMELINE.md").write_text("\n".join(lines), encoding="utf-8")

    detail_lines = [
        "# MNQ v2b Prior-Opposed Session Timeline (detail)",
        "",
        "One block per session in chart order.",
        "",
    ]
    for p in profiles:
        detail_lines.extend(
            [
                "## %s — %s %s ($%.0f)" % (p.session, p.outcome.upper(), p.side.upper(), p.net_usd),
                "",
                "- Chart: `%s`" % p.chart,
                "- Tags: `%s`" % ", ".join(p.tags),
                "",
                p.narrative,
                "",
            ]
        )
    (output_root / "TIMELINE_DETAIL.md").write_text("\n".join(detail_lines), encoding="utf-8")

    losses = [p for p in profiles if p.outcome == "loss"]
    loss_lines = [
        "# Loss-only timeline (prior-opposed MNQ v2b)",
        "",
        "Same automated profiles, losses only (%d sessions)." % len(losses),
        "",
    ]
    for p in losses:
        loss_lines.append(
            "- **%s** %s $%.0f — %s" % (p.session, p.side, p.net_usd, p.narrative)
        )
    (output_root / "LOSSES_TIMELINE.md").write_text("\n".join(loss_lines), encoding="utf-8")

    readme = [
        "# Prior-opposed session profiles",
        "",
        "Generated by `python -m live.mnq_v2b_prior_opposed_session_profile`.",
        "",
        "- [`TIMELINE.md`](TIMELINE.md) — compact table, all sessions",
        "- [`TIMELINE_DETAIL.md`](TIMELINE_DETAIL.md) — one narrative block per session",
        "- [`LOSSES_TIMELINE.md`](LOSSES_TIMELINE.md) — loss sessions only",
        "- [`session_profiles.csv`](session_profiles.csv) — machine-readable tags and fields",
        "",
        "Break candle = first 15m bar (after 09:45) that tags the v2b entry side, on or before entry.",
        "1R/2R candles = first touch of OR extension targets from break through campaign exit.",
    ]
    (output_root / "README.md").write_text("\n".join(readme), encoding="utf-8")


def build_profiles(
    *,
    chart_root: Path,
    campaign_regimes: Path,
    unit_trades: Path,
    dbn: Path,
    output_root: Path,
) -> List[SessionProfile]:
    regimes = pd.read_csv(campaign_regimes)
    regimes = regimes[regimes["regime"].astype(str) == "not_aligned_prior_opposed"].copy()
    regimes = regimes.sort_values(["session", "entry_ts", "trade_id"])

    print("Loading MNQ 1m bars...", flush=True)
    bars_by_day = load_1m_by_ny_date_any(dbn.resolve(), "mnq")

    profiles: List[SessionProfile] = []
    for idx, row in enumerate(regimes.itertuples(index=False), start=1):
        session = date.fromisoformat(str(row.session))
        rth = _rth_bars(bars_by_day.get(session), session)
        or_ = opening_range(rth)
        if or_ is None:
            continue
        candles = post_or_candles(rth)
        outcome = "win" if float(row.base_1_1_3_net) > 0 else "loss"
        chart_rel = "charts/%03d_%s_%s_%s.png" % (idx, row.session, row.side, outcome)
        profiles.append(
            profile_campaign(
                idx=idx,
                row=pd.Series(row._asdict()),
                candles=candles,
                or_=or_,
                unit_trades=unit_trades,
                chart_rel=chart_rel,
            )
        )
        if idx % 50 == 0:
            print("  profiled %d" % idx, flush=True)

    write_outputs(output_root, profiles)
    return profiles


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        description="Profile MNQ prior-opposed v2b sessions from 15m OR structure (chart-review style)."
    )
    parser.add_argument(
        "--chart-root",
        type=Path,
        default=REPO / "live/state/mnq_v2b_regime_weighting_research/charts/prior_opposed_15m",
    )
    parser.add_argument(
        "--campaign-regimes",
        type=Path,
        default=REPO / "live/state/mnq_v2b_regime_weighting_research/campaign_regimes.csv",
    )
    parser.add_argument(
        "--unit-trades",
        type=Path,
        default=REPO / "live/state/v2b_sizing_sweep/states/mnq_v2b_sizing_S_1_1_3/unit_trades.csv",
    )
    parser.add_argument("--dbn", type=Path, default=MARKETS["mnq"].dbn_path)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=None,
        help="Defaults to <chart-root>/profile",
    )
    args = parser.parse_args(argv)
    output_root = args.output_root or (args.chart_root / "profile")
    profiles = build_profiles(
        chart_root=args.chart_root,
        campaign_regimes=args.campaign_regimes,
        unit_trades=args.unit_trades,
        dbn=args.dbn,
        output_root=output_root,
    )
    print("Wrote %d profiles to %s" % (len(profiles), output_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
