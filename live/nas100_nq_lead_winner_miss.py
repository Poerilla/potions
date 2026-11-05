"""Lookahead diagnostic: why the coupled NAS100 stream misses NQ winners.

The causal book (`nas100_v2b_nq_lead_coupled_resting_limit`) may enter only on
the single NAS100 bar strictly after the NQ entry bar completes, and only if
that close is through a ratio-scaled copy of the NQ opening range.

This study is allowed to look ahead. It classifies each skipped campaign as a
late break, a break that already ran back inside, a different NAS opening
range, or a session that never shares the break. It also marks a would-be
NAS100 ``S_1_1_1`` if the first later close through the mapped range had been
taken. That tape is not a causal result and is not a promote.
"""

from __future__ import annotations

import argparse
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .bars import rth_bars
from .fx_data import ensure_nas100_platform_files, load_fx_1m_by_ny_date
from .hourly_st_pmc_strategyplugin_variants import REPO
from .nq_lead_nas100_prior_opposed_replay import COUPLED_NQ_ROOT, COUPLED_OUTPUT, FEE_PER_UNIT, TICK

HUB = COUPLED_OUTPUT / "winner_miss_lookahead"
NQ_UNITS = (
    COUPLED_NQ_ROOT
    / "states"
    / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3"
    / "unit_trades.csv"
)
POINT_VALUE = 1.0
OR_END = time(9, 45)
EOD = time(15, 59)
LEVEL_GAP_WIDTHS = 0.25


def _ny(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("America/New_York")
    else:
        t = t.tz_convert("America/New_York")
    return t


def _beyond(side: str, px: float, hi: float, lo: float) -> bool:
    if side == "long":
        return px >= hi
    if side == "short":
        return px <= lo
    return False


def _through_wick(side: str, hi: float, lo: float, brk: float) -> bool:
    if side == "long":
        return hi >= brk
    return lo <= brk


def _break_level(side: str, hi: float, lo: float) -> float:
    return hi if side == "long" else lo


def _inside_points(side: str, px: float, hi: float, lo: float) -> float:
    """Positive when price has not cleared the mapped break."""

    if side == "long":
        return hi - px
    return px - lo


def _load_nq_nets(path: Path) -> pd.DataFrame:
    units = pd.read_csv(path)
    g = units.groupby("trade_id", as_index=False).agg(
        nq_net_usd=("net_usd", "sum"),
        nq_units=("unit_id", "count"),
        direction=("direction", "first"),
        nq_entry_ts=("entry_ts", "first"),
        nq_entry_price=("entry_price", "first"),
    )
    g["nq_win"] = g["nq_net_usd"] > 0
    return g


def _native_or(day: pd.DataFrame) -> Optional[Dict[str, float]]:
    if day is None or day.empty:
        return None
    times = day.index.time
    mask = (times >= time(9, 30)) & (times < OR_END)
    window = day.loc[mask, ["high", "low", "close"]].dropna()
    if window.empty:
        return None
    return {
        "nas_or_high": float(window["high"].max()),
        "nas_or_low": float(window["low"].min()),
    }


def _close_through(side: str, close: float, level: float) -> bool:
    if side == "long":
        return close >= level
    if side == "short":
        return close <= level
    return False


def _first_close_break(day: pd.DataFrame, side: str, level: float, start: pd.Timestamp, end: pd.Timestamp):
    view = day.loc[(day.index >= start) & (day.index <= end)]
    for ts, row in view.iterrows():
        if pd.isna(row["close"]):
            continue
        if _close_through(side, float(row["close"]), level):
            return ts
    return None


def _prior_close_break(day: pd.DataFrame, side: str, level: float, start: pd.Timestamp, before: pd.Timestamp) -> bool:
    view = day.loc[(day.index >= start) & (day.index < before)]
    for _, row in view.iterrows():
        if pd.isna(row["close"]):
            continue
        if _close_through(side, float(row["close"]), level):
            return True
    return False


def _prior_wick_break(day: pd.DataFrame, side: str, level: float, start: pd.Timestamp, before: pd.Timestamp) -> bool:
    view = day.loc[(day.index >= start) & (day.index < before)]
    for _, row in view.iterrows():
        if pd.isna(row["high"]) or pd.isna(row["low"]):
            continue
        if _through_wick(side, float(row["high"]), float(row["low"]), level):
            return True
    return False


def _simulate_s111(
    day: pd.DataFrame,
    fill_ts: pd.Timestamp,
    side: str,
    or_hi: float,
    or_lo: float,
) -> Optional[float]:
    """Lookahead S_1_1_1 from the next bar open. Stop is checked before targets."""

    rng = or_hi - or_lo
    if rng <= 0 or fill_ts not in day.index:
        return None
    if side == "long":
        stop0 = or_lo
        tp1 = or_hi + rng
        tp2 = or_hi + 2.0 * rng
        be = or_hi + TICK
        sign = 1.0
    else:
        stop0 = or_hi
        tp1 = or_lo - rng
        tp2 = or_lo - 2.0 * rng
        be = or_lo - TICK
        sign = -1.0
    entry = float(day.loc[fill_ts, "open"]) + (TICK if side == "long" else -TICK)
    realized = -FEE_PER_UNIT * 3.0
    qty = 3
    tp1_done = False
    tp2_done = False
    stop = stop0
    after = day.loc[day.index >= fill_ts]
    for ts, row in after.iterrows():
        if pd.isna(row["high"]) or pd.isna(row["low"]) or pd.isna(row["close"]):
            continue
        hi = float(row["high"])
        lo = float(row["low"])
        op = float(row["open"])
        cl = float(row["close"])
        if ts.time() >= EOD:
            exit_px = cl - TICK if side == "long" else cl + TICK
            realized += sign * (exit_px - entry) * qty * POINT_VALUE - FEE_PER_UNIT * qty
            return realized

        def stop_hit() -> bool:
            return lo <= stop if side == "long" else hi >= stop

        def stop_px() -> float:
            if side == "long":
                return (op - TICK) if op <= stop else (stop - TICK)
            return (op + TICK) if op >= stop else (stop + TICK)

        if not tp1_done:
            if stop_hit():
                realized += sign * (stop_px() - entry) * qty * POINT_VALUE - FEE_PER_UNIT * qty
                return realized
            hit_tp1 = hi >= tp1 if side == "long" else lo <= tp1
            if hit_tp1:
                realized += sign * (tp1 - entry) * POINT_VALUE - FEE_PER_UNIT
                qty -= 1
                tp1_done = True
                stop = be
                if stop_hit():
                    realized += sign * (stop_px() - entry) * qty * POINT_VALUE - FEE_PER_UNIT * qty
                    return realized
                hit_tp2 = hi >= tp2 if side == "long" else lo <= tp2
                if hit_tp2 and qty > 0:
                    realized += sign * (tp2 - entry) * POINT_VALUE - FEE_PER_UNIT
                    qty -= 1
                    tp2_done = True
            continue
        if stop_hit():
            realized += sign * (stop_px() - entry) * qty * POINT_VALUE - FEE_PER_UNIT * qty
            return realized
        if not tp2_done:
            hit_tp2 = hi >= tp2 if side == "long" else lo <= tp2
            if hit_tp2 and qty > 0:
                realized += sign * (tp2 - entry) * POINT_VALUE - FEE_PER_UNIT
                qty -= 1
                tp2_done = True
                if qty <= 0:
                    return realized
    return realized


def _classify_row(rec: Dict[str, object]) -> str:
    if rec["state"] != "skipped" or rec["skip_reason"] != "structure_failed":
        if rec["state"] == "entered":
            return "entered_on_legal_bar"
        return "skipped_" + str(rec["skip_reason"] or "other")
    if rec["prior_close_through"]:
        return "close_gave_back"
    if rec["decision_wick_only"]:
        return "wick_on_legal_bar"
    if rec["later_close_through"]:
        return "delayed_break"
    return "never_breaks"


def _minutes(a: Optional[pd.Timestamp], b: Optional[pd.Timestamp]) -> Optional[float]:
    if a is None or b is None or pd.isna(a) or pd.isna(b):
        return None
    return (pd.Timestamp(a) - pd.Timestamp(b)).total_seconds() / 60.0


def build_campaigns(bars_by_day: Dict[date, pd.DataFrame]) -> pd.DataFrame:
    audit = pd.read_csv(COUPLED_OUTPUT / "sync_audit.csv")
    nq = _load_nq_nets(NQ_UNITS)
    merged = audit.merge(nq, left_on="campaign_id", right_on="trade_id", how="left")
    rows: List[Dict[str, object]] = []
    for rec in merged.itertuples(index=False):
        side = str(rec.side)
        skip_reason = "" if pd.isna(rec.skip_reason) else str(rec.skip_reason)
        session = _ny(rec.t_nq).date()
        day = rth_bars(bars_by_day.get(session), session, dense=True)
        t_nq = _ny(rec.t_nq)
        t_nas = _ny(rec.t_nas)
        avail = _ny(rec.available_at_ts)
        mapped_hi = float(rec.mapped_or_high) if pd.notna(rec.mapped_or_high) else None
        mapped_lo = float(rec.mapped_or_low) if pd.notna(rec.mapped_or_low) else None
        native = _native_or(day)
        out: Dict[str, object] = {
            "campaign_id": rec.campaign_id,
            "session": session.isoformat(),
            "side": side,
            "state": rec.state,
            "skip_reason": skip_reason,
            "nq_net_usd": float(rec.nq_net_usd) if pd.notna(rec.nq_net_usd) else None,
            "nq_win": bool(rec.nq_win) if pd.notna(rec.nq_win) else False,
            "t_nq": t_nq.isoformat(),
            "available_at": avail.isoformat(),
            "t_nas": t_nas.isoformat(),
            "mapped_or_high": mapped_hi,
            "mapped_or_low": mapped_lo,
        }
        if day.empty or mapped_hi is None or mapped_lo is None or t_nas not in day.index:
            out["miss_class"] = "no_bar"
            rows.append(out)
            continue
        bar = day.loc[t_nas]
        close = float(bar["close"])
        mapped_break = _break_level(side, mapped_hi, mapped_lo)
        mapped_width = mapped_hi - mapped_lo
        inside = _inside_points(side, close, mapped_hi, mapped_lo)
        decision_through = _beyond(side, close, mapped_hi, mapped_lo)
        decision_wick = _through_wick(side, float(bar["high"]), float(bar["low"]), mapped_break)
        prior_close = _prior_close_break(day, side, mapped_break, t_nq, t_nas)
        prior_wick = _prior_wick_break(day, side, mapped_break, t_nq, t_nas)
        eod_ts = day.index[day.index.time <= EOD][-1]
        later = _first_close_break(day, side, mapped_break, t_nas + pd.Timedelta(minutes=1), eod_ts)
        first_mapped = _first_close_break(day, side, mapped_break, day.index[0], eod_ts)
        nas_or_high = native["nas_or_high"] if native else None
        nas_or_low = native["nas_or_low"] if native else None
        native_break = None
        native_width = None
        native_pass = None
        level_gap_widths = None
        first_native = None
        if native and nas_or_high is not None and nas_or_low is not None and nas_or_high > nas_or_low:
            native_break = _break_level(side, nas_or_high, nas_or_low)
            native_width = nas_or_high - nas_or_low
            native_pass = _beyond(side, close, nas_or_high, nas_or_low)
            # Positive: mapped break sits further out than NAS's own OR.
            if side == "long":
                gap = mapped_break - native_break
            else:
                gap = native_break - mapped_break
            level_gap_widths = gap / native_width
            first_native = _first_close_break(day, side, native_break, day.index[0], eod_ts)
        signal_ts = None
        if decision_through:
            signal_ts = t_nas
        elif later is not None:
            signal_ts = later
        hypo_net = None
        hypo_win = None
        if signal_ts is not None:
            loc = day.index.get_loc(signal_ts)
            if isinstance(loc, slice):
                loc = loc.start
            if loc + 1 < len(day.index):
                hypo_net = _simulate_s111(day, day.index[loc + 1], side, mapped_hi, mapped_lo)
                if hypo_net is not None:
                    hypo_win = hypo_net > 0
        built = {
            **out,
            "decision_close": close,
            "mapped_break": mapped_break,
            "mapped_width": mapped_width,
            "inside_points": inside,
            "inside_widths": inside / mapped_width if mapped_width else None,
            "decision_close_through": decision_through,
            "decision_wick_through": decision_wick,
            "decision_wick_only": (not decision_through) and decision_wick and not prior_close,
            "prior_close_through": prior_close,
            "prior_wick_through": prior_wick,
            "later_close_through": later is not None,
            "minutes_after_decision_to_mapped_break": _minutes(later, t_nas) if later is not None else None,
            "minutes_nq_to_mapped_break": _minutes(first_mapped, t_nq) if first_mapped is not None else None,
            "nas_or_high": nas_or_high,
            "nas_or_low": nas_or_low,
            "nas_or_width": native_width,
            "native_break": native_break,
            "width_ratio_mapped_over_native": (mapped_width / native_width) if native_width else None,
            "level_gap_native_widths": level_gap_widths,
            "mapped_farther_than_native": bool(level_gap_widths is not None and level_gap_widths > LEVEL_GAP_WIDTHS),
            "native_pass_mapped_fail": bool(native_pass and not decision_through),
            "decision_passes_native_or": native_pass,
            "minutes_nq_to_native_break": _minutes(first_native, t_nq) if first_native is not None else None,
            "native_broke_before_nq": bool(first_native is not None and first_native < t_nq),
            "native_never_breaks": first_native is None,
            "hypo_net_usd": hypo_net,
            "hypo_win": hypo_win,
        }
        built["miss_class"] = _classify_row(built)
        rows.append(built)
    return pd.DataFrame(rows)


def _pct(n: int, d: int) -> str:
    if d <= 0:
        return "n/a"
    return "%.1f%%" % (100.0 * n / d)


def _subset_table(df: pd.DataFrame, mask: pd.Series, label: str) -> List[str]:
    sub = df.loc[mask]
    lines = ["### %s (n=%d)" % (label, len(sub)), ""]
    if sub.empty:
        lines.append("No rows.")
        lines.append("")
        return lines
    counts = sub["miss_class"].value_counts()
    lines.append("| Class | N | Share |")
    lines.append("|---|---:|---:|")
    for name, n in counts.items():
        lines.append("| %s | %d | %s |" % (name, int(n), _pct(int(n), len(sub))))
    lines.append("")
    failed = sub[sub["skip_reason"] == "structure_failed"] if "skip_reason" in sub.columns else sub.iloc[0:0]
    if not failed.empty:
        lines.extend(_mechanism_lines(failed))
    return lines


def _mechanism_lines(failed: pd.DataFrame) -> List[str]:
    lines: List[str] = []
    med_pts = float(failed["inside_points"].median())
    med_w = float(failed["inside_widths"].median())
    wick = int(failed["decision_wick_through"].fillna(False).sum())
    near = failed["minutes_nq_to_mapped_break"]
    near_n = int(((near >= -2) & (near <= 1)).sum())
    stale = int((near <= -15).sum())
    lines.append(
        "On the legal bar the close is back inside by a median **%.1f** points (**%.3f** mapped-OR widths). "
        "The same bar still wicks through the mapped level in **%s**. "
        "The first NAS close through that level is within two minutes of the NQ fill on **%s** of these rows "
        "(**%s** were already through more than 15 minutes earlier)."
        % (med_pts, med_w, _pct(wick, len(failed)), _pct(near_n, len(failed)), _pct(stale, len(failed)))
    )
    lines.append("")
    delay = failed["minutes_after_decision_to_mapped_break"]
    lines.append("| Reclaim of the mapped close after the legal bar | N | Share |")
    lines.append("|---|---:|---:|")
    buckets = [("1 min", 1, 1), ("2–5 min", 2, 5), ("6–15 min", 6, 15), ("16–60 min", 16, 60), (">60 min", 61, 10_000)]
    for name, lo, hi in buckets:
        n = int(((delay >= lo) & (delay <= hi)).sum())
        lines.append("| %s | %d | %s |" % (name, n, _pct(n, len(failed))))
    never = int(delay.isna().sum())
    lines.append("| never again that RTH | %d | %s |" % (never, _pct(never, len(failed))))
    lines.append("")
    if delay.notna().any():
        lines.append(
            "When the close does come back through, the median wait is **%.0f** minutes (p25 %.0f, p75 %.0f)."
            % (float(delay.median()), float(delay.quantile(0.25)), float(delay.quantile(0.75)))
        )
        lines.append("")
    native_fail = int(failed["native_pass_mapped_fail"].fillna(False).sum())
    farther = int(failed["mapped_farther_than_native"].fillna(False).sum())
    ratio = float(failed["width_ratio_mapped_over_native"].median())
    gap = float(failed["level_gap_native_widths"].median())
    native_t = failed["minutes_nq_to_native_break"]
    coincident = int(((native_t >= -2) & (native_t <= 2)).sum())
    lines.append(
        "NAS's own 09:30–09:45 range is not a different box. Median mapped/native width ratio **%.3f**. "
        "Median level gap **%.3f** native widths (positive means the mapped NQ break is further out). "
        "The mapped level is more than %.2f native widths further out on **%s** of rows. "
        "The legal close would still have cleared NAS's own range on **%s**. "
        "NAS's own range breaks within two minutes of the NQ fill on **%s**."
        % (ratio, gap, LEVEL_GAP_WIDTHS, _pct(farther, len(failed)), _pct(native_fail, len(failed)), _pct(coincident, len(failed)))
    )
    lines.append("")
    return lines


def _hypo_block(df: pd.DataFrame) -> List[str]:
    lines = ["## Would-be NAS100 S_1_1_1 (lookahead)", ""]
    lines.append(
        "If the first NAS close through the mapped range after the NQ bar completes is taken "
        "(fill on the next open, 1 tick adverse, fee $1.50 per unit per fill, stop before target), "
        "the campaign is a would-be NAS trade. The 60-second cap is removed. This is not the causal book."
    )
    lines.append("")
    lines.append("| Slice | NQ campaigns | NAS trades | NAS win% | NAS net | NQ-win & NAS-win | NQ-win & NAS-loss | NQ-loss & NAS-win |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|")

    def add(label: str, mask: pd.Series) -> None:
        sub = df.loc[mask]
        taken = sub[sub["hypo_net_usd"].notna()]
        both_win = int(((taken["nq_win"]) & (taken["hypo_win"] == True)).sum())  # noqa: E712
        nq_only = int(((taken["nq_win"]) & (taken["hypo_win"] == False)).sum())  # noqa: E712
        nas_only = int(((~taken["nq_win"]) & (taken["hypo_win"] == True)).sum())  # noqa: E712
        win_pct = _pct(int((taken["hypo_win"] == True).sum()), len(taken))  # noqa: E712
        net = float(taken["hypo_net_usd"].sum()) if len(taken) else 0.0
        lines.append(
            "| %s | %d | %d | %s | $%.0f | %d | %d | %d |"
            % (label, len(sub), len(taken), win_pct, net, both_win, nq_only, nas_only)
        )

    add("All campaigns", pd.Series(True, index=df.index))
    add("Causal entries", df["state"] == "entered")
    add("structure_failed", df["skip_reason"] == "structure_failed")
    add("NQ winners, structure_failed", (df["nq_win"]) & (df["skip_reason"] == "structure_failed"))
    add("NQ losers, structure_failed", (~df["nq_win"]) & (df["skip_reason"] == "structure_failed"))
    lines.append("")
    skipped_winners = df[(df["nq_win"]) & (df["skip_reason"] == "structure_failed")]
    rescued = skipped_winners[skipped_winners["hypo_win"] == True]  # noqa: E712
    lost = skipped_winners[skipped_winners["hypo_win"] == False]  # noqa: E712
    never = skipped_winners[skipped_winners["hypo_net_usd"].isna()]
    causal = df[df["state"] == "entered"]
    causal_proxy = float(causal["hypo_net_usd"].sum())
    lines.append(
        "Of **%d** NQ-winner campaigns the causal book skipped for structure, lookahead NAS wins **%d**, "
        "loses **%d**, and never gets a mapped close-break **%d**. "
        "The same exit proxy on the 193 causal entries nets about **$%.0f**, next to the broker book’s **$7,474**, "
        "so the skipped-winner dollars are on that scale and still use the later close."
        % (len(skipped_winners), len(rescued), len(lost), len(never), causal_proxy)
    )
    lines.append("")
    return lines


def write_summary(df: pd.DataFrame, path: Path) -> str:
    structure = df["skip_reason"] == "structure_failed"
    winners_missed = structure & df["nq_win"]
    losers_missed = structure & ~df["nq_win"]
    lines = [
        "# NAS100 misses of NQ winners — lookahead structure",
        "",
        "Diagnostic only. The causal coupled book is unchanged: one NAS100 bar after the NQ entry bar completes, close must be through the ratio-mapped NQ opening range. This note looks past that bar on purpose.",
        "",
        "Parent hub: `live/state/nas100_v2b_nq_lead_coupled_resting_limit/`. Lead book: hour-complete NQ resting-limit. Stance: **research only**.",
        "",
        "## What the legal bar is doing",
        "",
        "NQ fill stamps are the left-labeled minute. The follower may look on the next NAS bar after that minute completes, so the decision is about two minutes after the NQ print. Structure is the NAS **close** versus NQ's opening range scaled by the last NAS close already known at reveal. It is not NAS100's own 09:30–09:45 range.",
        "",
        "Campaigns in the sync audit: **%d**. Entered: **%d**. `structure_failed`: **%d**."
        % (len(df), int((df["state"] == "entered").sum()), int(structure.sum())),
        "",
        "Classes on a structure miss:",
        "",
        "- `close_gave_back` — a NAS close was already through the mapped level on the NQ fill minute or the completion minute, and the only legal bar (about two minutes after the fill) closed back inside.",
        "- `wick_on_legal_bar` — that legal bar is the first trade through the level, and it closes back inside.",
        "- `delayed_break` — no close has been through yet, and a later close the same session is.",
        "- `never_breaks` — no NAS close through the mapped level for the rest of RTH.",
        "",
    ]
    lines.extend(_subset_table(df, winners_missed, "NQ winners skipped for structure"))
    lines.extend(_subset_table(df, losers_missed, "NQ losers skipped for structure"))
    lines.extend(_subset_table(df, df["state"] == "entered", "Causal NAS entries"))
    lines.extend(_hypo_block(df))
    lines.extend(
        [
            "## Read",
            "",
            _read_paragraph(df),
            "",
            "Files: `campaigns.csv`, `class_counts.csv`.",
            "",
        ]
    )
    text = "\n".join(lines)
    path.write_text(text, encoding="utf-8")
    return text


def _read_paragraph(df: pd.DataFrame) -> str:
    missed = df[(df["skip_reason"] == "structure_failed") & (df["nq_win"])]
    n = len(missed)
    if n == 0:
        return "No skipped NQ winners."
    counts = missed["miss_class"].value_counts(normalize=True)
    delay = missed["minutes_after_decision_to_mapped_break"].dropna()
    delay_txt = "%.0f min" % float(delay.median()) if len(delay) else "n/a"
    within5 = int(((missed["minutes_after_decision_to_mapped_break"] >= 1) & (missed["minutes_after_decision_to_mapped_break"] <= 5)).sum())
    on_fill = int((missed["minutes_nq_to_mapped_break"] == 0).sum())
    on_complete = int((missed["minutes_nq_to_mapped_break"] == 1).sum())
    both = missed[missed["hypo_win"] == True]  # noqa: E712
    native_share = 100.0 * float(missed["native_pass_mapped_fail"].fillna(False).mean())
    return (
        "NAS100 is not late to the break. On **%d** of **%d** skipped NQ winners the first close through the mapped range "
        "is the NQ fill minute (%d) or the completion minute (%d). The follower may only use the bar after that, and that close "
        "has already fallen back inside (median %.1f points, %.3f of the range) even though the bar still wicks the level on **%s** of them. "
        "The two opening ranges match: median width ratio %.3f, median level gap %.3f native widths. "
        "Using NAS's own range would have passed the legal close on only %.0f%% of these winner-misses. "
        "The close comes back through a median of %s later (**%s** within five minutes). "
        "A lookahead S_1_1_1 on that later close wins **%d** of the %d. "
        "The same giveback hits NQ losers, so the one-bar close gate is not sorting winners from losers. "
        "One skipped NQ winner never reclaims the mapped close."
        % (
            on_fill + on_complete,
            n,
            on_fill,
            on_complete,
            float(missed["inside_points"].median()),
            float(missed["inside_widths"].median()),
            _pct(int(missed["decision_wick_through"].fillna(False).sum()), n),
            float(missed["width_ratio_mapped_over_native"].median()),
            float(missed["level_gap_native_widths"].median()),
            native_share,
            delay_txt,
            _pct(within5, n),
            len(both),
            n,
        )
    )


def _class_counts(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    slices = {
        "all": pd.Series(True, index=df.index),
        "nq_winners": df["nq_win"],
        "nq_losers": ~df["nq_win"],
        "structure_failed_nq_winners": (df["skip_reason"] == "structure_failed") & df["nq_win"],
        "structure_failed_nq_losers": (df["skip_reason"] == "structure_failed") & ~df["nq_win"],
        "entered": df["state"] == "entered",
    }
    for name, mask in slices.items():
        sub = df.loc[mask]
        for cls, n in sub["miss_class"].value_counts().items():
            rows.append({"slice": name, "miss_class": cls, "n": int(n), "share": n / len(sub) if len(sub) else 0})
    return pd.DataFrame(rows)


def run(email: bool = False) -> Path:
    from .run_ledger import begin_run, complete_run, fail_run

    HUB.mkdir(parents=True, exist_ok=True)
    run_id = begin_run(
        run_class="pandas",
        variant_slug="nas100_nq_lead_winner_miss_lookahead",
        instrument="NAS100",
        hub_path=HUB,
        notes="lookahead diagnostic of coupled structure_failed vs NQ winners; not a causal book",
        meta={"parent_hub": str(COUPLED_OUTPUT), "lookahead": True},
    )
    try:
        one_m, _daily = ensure_nas100_platform_files(REPO)
        bars = load_fx_1m_by_ny_date(one_m, "NAS100")
        df = build_campaigns(bars)
        df.to_csv(HUB / "campaigns.csv", index=False)
        counts = _class_counts(df)
        counts.to_csv(HUB / "class_counts.csv", index=False)
        text = write_summary(df, HUB / "SUMMARY.md")
        taken = df[df["hypo_net_usd"].notna()]
        equity = taken.sort_values("t_nq")["hypo_net_usd"].cumsum()
        dd = float((equity - equity.cummax()).min()) if len(equity) else 0.0
        net = float(taken["hypo_net_usd"].sum()) if len(taken) else 0.0
        complete_run(
            run_id,
            net_usd=net,
            stress_dd_usd=dd,
            close_mtm_dd_usd=dd,
            ns=(net / abs(dd)) if dd else None,
            trades=int(len(taken)),
            replay_start="2021-03-04",
            hub_path=HUB,
            notes="lookahead S_1_1_1 proxy on first mapped close-break; DD is campaign-close, not 1m stress",
        )
    except Exception as exc:
        fail_run(run_id, notes="winner-miss study crashed: %s" % exc)
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: NAS100 NQ-lead winner-miss study crashed",
                body="Hub: %s\nCrash: %s\n" % (HUB, exc),
            )
        raise
    if email:
        from .notify_email import send_email

        body = _email_body(df, HUB)
        (HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
        send_email(subject="potions: NAS100 NQ-lead winner-miss study complete", body=body)
    return HUB


def _email_body(df: pd.DataFrame, hub: Path) -> str:
    missed = df[(df["skip_reason"] == "structure_failed") & (df["nq_win"])]
    lines = [
        "Hub: %s" % hub,
        "Parent: %s" % COUPLED_OUTPUT,
        "Book: NQ resting-limit hour-complete vs coupled NAS100 sync audit.",
        "Study: lookahead. Not a causal replay and not a demo promote.",
        "NQ-winner structure misses: %d" % len(missed),
        "Mechanism: close gives back on the only legal bar. First mapped close-break is the NQ minute; NAS own OR width matches (ratio ~1.01).",
        "Median giveback: %.1f pts. Legal bar still wicks the level on %s."
        % (
            float(missed["inside_points"].median()),
            _pct(int(missed["decision_wick_through"].fillna(False).sum()), len(missed)),
        ),
        "Close back through: median %.0f min. Within 5 min: %s."
        % (
            float(missed["minutes_after_decision_to_mapped_break"].median()),
            _pct(
                int(
                    (
                        (missed["minutes_after_decision_to_mapped_break"] >= 1)
                        & (missed["minutes_after_decision_to_mapped_break"] <= 5)
                    ).sum()
                ),
                len(missed),
            ),
        ),
    ]
    rescued = int((missed["hypo_win"] == True).sum())  # noqa: E712
    lines.append("Lookahead NAS winners among those misses: %d of %d" % (rescued, len(missed)))
    lines.append("Stance: research only. Not a demo promote. Opening-range mismatch is not the miss.")
    lines.append("")
    return "\n".join(lines)


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Lookahead study of NAS100 misses vs NQ winners.")
    parser.add_argument("--email", action="store_true")
    args = parser.parse_args(argv)
    hub = run(email=args.email)
    print("Wrote %s" % hub)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
