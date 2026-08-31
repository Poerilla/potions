"""Path study: open-week ±4×ATR → opposite ±4 without ±8, then reverse fade.

Same levels as the quarterly ATR4 fade chart/plugin (4h, mid ± k×ATR(14) at
opening-week close). Diagnostic only — no broker fills.

Per quarter after the opening week:
  1. First touch of mid±4×ATR (skip same-bar dual touch).
  2. First-fade WIN if opposite ±4 is touched before same-side ±8.
     FAIL if same-side ±8 first; UNRESOLVED if quarter ends first.
  3. After a first-fade WIN, reverse from that opposite ±4:
     reverse WIN if the original ±4 is touched before reverse-side ±8.

Also ranks path candidates by win rate (first lower/upper vs reverse legs),
computes 4h MAE tattoos on the traded leg, and writes ``best_path.csv`` for
the ladder broker to consume.

Outputs under ``live/state/quarterly_atr4_opposite_path/``.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .gbpusd_quarterly_4h_charts import (
    ATR_LEN,
    NY,
    load_4h,
    opening_week_slice,
    quarter_windows,
    wilder_atr,
)
from .quarterly_atr4_fade_broker import ALL_SYMBOLS, MARKETS, MarketSpec

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_opposite_path"
MIN_PATH_N = 5  # minimum sample for a candidate to compete on WR


@dataclass
class QuarterPath:
    market: str
    year: int
    quarter: int
    atr14: float
    mid: float
    upper4: float
    lower4: float
    upper8: float
    lower8: float
    first_side: str  # upper | lower | none | dual_skip | no_levels
    first_touch_ts: str
    first_outcome: str  # win | fail_8 | unresolved | dual_skip | no_touch | no_levels
    first_resolve_ts: str
    reverse_outcome: str  # win | fail_8 | unresolved | n/a
    reverse_resolve_ts: str


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _bar_hits(high: float, low: float, level: float, side: str) -> bool:
    if side == "upper":
        return high >= level
    return low <= level


def _scan_path(
    bars: pd.DataFrame,
    *,
    entry_side: str,
    target: float,
    fail: float,
) -> Tuple[str, str]:
    """Scan bars for target (opposite ±4) vs fail (same-side ±8).

    Returns (outcome, resolve_ts) where outcome in {win, fail_8, unresolved}.
    """
    target_side = "lower" if entry_side == "upper" else "upper"
    fail_side = entry_side
    for ts, row in bars.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        hit_fail = _bar_hits(hi, lo, fail, fail_side)
        hit_tgt = _bar_hits(hi, lo, target, target_side)
        if hit_fail and hit_tgt:
            # Same-bar both: treat as fail (blowthrough / path invalid for clean win).
            return "fail_8", str(ts)
        if hit_fail:
            return "fail_8", str(ts)
        if hit_tgt:
            return "win", str(ts)
    return "unresolved", ""


def analyze_market(
    market: MarketSpec,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[QuarterPath]:
    bars = load_4h(market.csv, market.symbol)
    atr = wilder_atr(bars, ATR_LEN)
    bars = bars.assign(atr=atr)
    rows: List[QuarterPath] = []

    for year, quarter, q0, q1 in quarter_windows(bars, start, end):
        ow = opening_week_slice(bars, q0)
        empty = QuarterPath(
            market=market.symbol,
            year=year,
            quarter=quarter,
            atr14=float("nan"),
            mid=float("nan"),
            upper4=float("nan"),
            lower4=float("nan"),
            upper8=float("nan"),
            lower8=float("nan"),
            first_side="no_levels",
            first_touch_ts="",
            first_outcome="no_levels",
            first_resolve_ts="",
            reverse_outcome="n/a",
            reverse_resolve_ts="",
        )
        if ow.empty or len(ow) < 1:
            rows.append(empty)
            continue
        atr14 = float(ow["atr"].iloc[-1])
        if not (atr14 > 0) or pd.isna(atr14):
            rows.append(empty)
            continue
        hi = float(ow["high"].max())
        lo = float(ow["low"].min())
        if hi <= lo:
            rows.append(empty)
            continue
        mid = 0.5 * (hi + lo)
        upper4 = mid + 4.0 * atr14
        lower4 = mid - 4.0 * atr14
        upper8 = mid + 8.0 * atr14
        lower8 = mid - 8.0 * atr14

        # Watch after opening week closes (same as plugin levels_ready).
        _, w1 = _week_end(q0)
        watch = bars[(bars.index >= max(w1, q0)) & (bars.index < q1)]
        base = QuarterPath(
            market=market.symbol,
            year=year,
            quarter=quarter,
            atr14=atr14,
            mid=mid,
            upper4=upper4,
            lower4=lower4,
            upper8=upper8,
            lower8=lower8,
            first_side="none",
            first_touch_ts="",
            first_outcome="no_touch",
            first_resolve_ts="",
            reverse_outcome="n/a",
            reverse_resolve_ts="",
        )
        if watch.empty:
            rows.append(base)
            continue

        first_side = ""
        first_i = -1
        first_ts = ""
        for i, (ts, row) in enumerate(watch.iterrows()):
            hi_b = float(row["high"])
            lo_b = float(row["low"])
            hit_up = hi_b >= upper4
            hit_dn = lo_b <= lower4
            if hit_up and hit_dn:
                base.first_side = "dual_skip"
                base.first_touch_ts = str(ts)
                base.first_outcome = "dual_skip"
                break
            if hit_up or hit_dn:
                first_side = "upper" if hit_up else "lower"
                first_i = i
                first_ts = str(ts)
                break
        if base.first_outcome == "dual_skip":
            rows.append(base)
            continue
        if not first_side:
            rows.append(base)
            continue

        base.first_side = first_side
        base.first_touch_ts = first_ts
        target = lower4 if first_side == "upper" else upper4
        fail = upper8 if first_side == "upper" else lower8
        path_bars = watch.iloc[first_i:]
        outcome, resolve_ts = _scan_path(path_bars, entry_side=first_side, target=target, fail=fail)
        base.first_outcome = outcome
        base.first_resolve_ts = resolve_ts

        if outcome != "win":
            rows.append(base)
            continue

        # Reverse fade: enter at opposite ±4; target original ±4; fail = reverse ±8.
        rev_side = "lower" if first_side == "upper" else "upper"
        rev_target = upper4 if first_side == "upper" else lower4
        rev_fail = lower8 if first_side == "upper" else upper8
        # Start at the bar that completed the first win (inclusive).
        rev_start = None
        for j, ts in enumerate(path_bars.index):
            if str(ts) == resolve_ts:
                rev_start = j
                break
        rev_bars = path_bars.iloc[rev_start:] if rev_start is not None else path_bars.iloc[0:0]
        rev_out, rev_ts = _scan_path(rev_bars, entry_side=rev_side, target=rev_target, fail=rev_fail)
        base.reverse_outcome = rev_out
        base.reverse_resolve_ts = rev_ts
        rows.append(base)

    return rows


def _week_end(q_start: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    local = q_start.tz_convert(NY) if q_start.tzinfo is not None else q_start.tz_localize(NY)
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    return monday, monday + pd.Timedelta(days=7)


def summarize(rows: Sequence[QuarterPath]) -> List[dict]:
    out: List[dict] = []
    by_m: Dict[str, List[QuarterPath]] = {}
    for r in rows:
        by_m.setdefault(r.market, []).append(r)
    for market, items in by_m.items():
        n_q = len(items)
        touched = [r for r in items if r.first_side in {"upper", "lower"}]
        wins = [r for r in touched if r.first_outcome == "win"]
        fails = [r for r in touched if r.first_outcome == "fail_8"]
        unresolved = [r for r in touched if r.first_outcome == "unresolved"]
        rev_wins = [r for r in wins if r.reverse_outcome == "win"]
        rev_fails = [r for r in wins if r.reverse_outcome == "fail_8"]
        rev_unres = [r for r in wins if r.reverse_outcome == "unresolved"]
        n_touch = len(touched)
        n_win = len(wins)
        out.append(
            {
                "market": market,
                "quarters": n_q,
                "first_touches": n_touch,
                "first_win_opposite4": n_win,
                "first_fail_8": len(fails),
                "first_unresolved": len(unresolved),
                "dual_skip": sum(1 for r in items if r.first_outcome == "dual_skip"),
                "no_touch": sum(1 for r in items if r.first_outcome == "no_touch"),
                "first_win_rate_given_touch": (n_win / n_touch) if n_touch else 0.0,
                "reverse_after_win": n_win,
                "reverse_win": len(rev_wins),
                "reverse_fail_8": len(rev_fails),
                "reverse_unresolved": len(rev_unres),
                "reverse_win_rate_given_first_win": (len(rev_wins) / n_win) if n_win else 0.0,
                "both_legs_win": len(rev_wins),
            }
        )
    return out


def _ts(val: str) -> Optional[pd.Timestamp]:
    if not val or (isinstance(val, float) and math.isnan(val)):
        return None
    ts = pd.Timestamp(val)
    if ts.tzinfo is None:
        return ts.tz_localize(NY)
    return ts.tz_convert(NY)


def _first_leg_mae(row: QuarterPath, bars: pd.DataFrame) -> Optional[dict]:
    """MAE on first-fade leg: first touch → first resolve."""
    if row.first_outcome != "win" or row.first_side not in {"upper", "lower"}:
        return None
    touch = _ts(row.first_touch_ts)
    resolve = _ts(row.first_resolve_ts)
    if touch is None or resolve is None or bars.empty:
        return None
    idx = bars.index
    if idx.tz is not None:
        touch = touch.tz_convert(idx.tz)
        resolve = resolve.tz_convert(idx.tz)
    seg = bars[(bars.index >= touch) & (bars.index <= resolve)]
    if seg.empty:
        return None
    atr = float(row.atr14)
    if row.first_side == "upper":
        entry = float(row.upper4)
        mae_px = max(0.0, float(seg["high"].max()) - entry)
        entry_side = "upper"
    else:
        entry = float(row.lower4)
        mae_px = max(0.0, entry - float(seg["low"].min()))
        entry_side = "lower"
    return {
        "leg": "first",
        "entry_side": entry_side,
        "year": int(row.year),
        "quarter": int(row.quarter),
        "touch_ts": str(touch),
        "resolve_ts": str(resolve),
        "atr14": atr,
        "mae_px": mae_px,
        "mae_atr": (mae_px / atr) if atr > 0 else float("nan"),
    }


def _reverse_leg_mae(row: QuarterPath, bars: pd.DataFrame) -> Optional[dict]:
    """MAE on reverse leg: opposite ±4 at first resolve → reverse resolve."""
    if row.first_outcome != "win" or row.reverse_outcome not in {"win", "fail_8", "unresolved"}:
        return None
    if row.first_side not in {"upper", "lower"}:
        return None
    start = _ts(row.first_resolve_ts)
    if start is None or bars.empty:
        return None
    end = _ts(row.reverse_resolve_ts)
    idx = bars.index
    if idx.tz is not None:
        start = start.tz_convert(idx.tz)
        if end is not None:
            end = end.tz_convert(idx.tz)
    if end is None:
        # unresolved: through last bar in the same calendar quarter as start
        end = bars.index[bars.index >= start]
        end = end[-1] if len(end) else start
    seg = bars[(bars.index >= start) & (bars.index <= end)]
    if seg.empty:
        return None
    atr = float(row.atr14)
    # Reverse entry is opposite ±4 from first side.
    if row.first_side == "lower":
        entry = float(row.upper4)
        mae_px = max(0.0, float(seg["high"].max()) - entry)
        entry_side = "upper"
    else:
        entry = float(row.lower4)
        mae_px = max(0.0, entry - float(seg["low"].min()))
        entry_side = "lower"
    return {
        "leg": "reverse",
        "entry_side": entry_side,
        "year": int(row.year),
        "quarter": int(row.quarter),
        "touch_ts": str(start),
        "resolve_ts": str(end),
        "atr14": atr,
        "mae_px": mae_px,
        "mae_atr": (mae_px / atr) if atr > 0 else float("nan"),
        "reverse_outcome": row.reverse_outcome,
        "first_side": row.first_side,
    }


def _round_up_half_atr(mae_atr: float) -> float:
    """Risk sizing tattoo → stop: 1.96→2.0, 0.32→0.5."""
    if not (mae_atr > 0) or math.isnan(mae_atr):
        return 0.5
    return max(0.5, math.ceil(mae_atr * 2.0 - 1e-12) / 2.0)


def path_candidates(items: Sequence[QuarterPath]) -> List[dict]:
    """Candidate paths ranked later by WR (same tattoo methodology as GBP/US30)."""
    touched = [r for r in items if r.first_side in {"upper", "lower"}]
    wins = [r for r in touched if r.first_outcome == "win"]
    cands: List[dict] = []

    def add_first(side: str) -> None:
        subset = [r for r in touched if r.first_side == side]
        n = len(subset)
        w = sum(1 for r in subset if r.first_outcome == "win")
        cands.append(
            {
                "path_id": "first_%s" % side,
                "trade_mode": "first_only",
                "first_side_filter": side,
                "entry_side": side,
                "n": n,
                "wins": w,
                "win_rate": (w / n) if n else 0.0,
                "leg": "first",
            }
        )

    add_first("lower")
    add_first("upper")

    def add_second(label: str, subset: Sequence[QuarterPath], entry_sides: Sequence[str]) -> None:
        n = len(subset)
        w = sum(1 for r in subset if r.reverse_outcome == "win")
        cands.append(
            {
                "path_id": label,
                "trade_mode": "second_only",
                "first_side_filter": (
                    "lower"
                    if label.endswith("after_lower")
                    else ("upper" if label.endswith("after_upper") else "both")
                ),
                "entry_side": ",".join(entry_sides),
                "n": n,
                "wins": w,
                "win_rate": (w / n) if n else 0.0,
                "leg": "reverse",
            }
        )

    add_second("second_any", wins, ["lower", "upper"])
    add_second(
        "second_after_lower",
        [r for r in wins if r.first_side == "lower"],
        ["upper"],  # reverse entry after lower-first win
    )
    add_second(
        "second_after_upper",
        [r for r in wins if r.first_side == "upper"],
        ["lower"],
    )
    return cands


def _tattoo_rows(
    items: Sequence[QuarterPath],
    *,
    path_id: str,
    bars: pd.DataFrame,
) -> List[dict]:
    """Chronological win MAE tattoos on the traded leg for the chosen path."""
    out: List[dict] = []
    if path_id.startswith("first_"):
        side = path_id.split("_", 1)[1]
        wins = [
            r
            for r in items
            if r.first_side == side and r.first_outcome == "win"
        ]
        wins = sorted(wins, key=lambda r: (r.year, r.quarter, r.first_touch_ts))
        for i, r in enumerate(wins, start=1):
            mae = _first_leg_mae(r, bars)
            if mae:
                mae["win_rank"] = i
                mae["path_id"] = path_id
                mae["market"] = r.market
                out.append(mae)
        return out

    # reverse / second paths
    if path_id == "second_after_lower":
        pool = [r for r in items if r.first_side == "lower" and r.reverse_outcome == "win"]
    elif path_id == "second_after_upper":
        pool = [r for r in items if r.first_side == "upper" and r.reverse_outcome == "win"]
    else:
        pool = [r for r in items if r.reverse_outcome == "win"]
    pool = sorted(pool, key=lambda r: (r.year, r.quarter, r.first_resolve_ts))
    for i, r in enumerate(pool, start=1):
        mae = _reverse_leg_mae(r, bars)
        if mae and mae.get("reverse_outcome") == "win":
            mae["win_rank"] = i
            mae["path_id"] = path_id
            mae["market"] = r.market
            out.append(mae)
    return out


def select_best_paths(detail: Sequence[QuarterPath]) -> Tuple[List[dict], List[dict], List[dict]]:
    """Return (best_rows, all_candidates, mae_tattoos)."""
    by_m: Dict[str, List[QuarterPath]] = {}
    for r in detail:
        by_m.setdefault(r.market, []).append(r)

    best_rows: List[dict] = []
    all_cands: List[dict] = []
    tattoos: List[dict] = []
    bars_cache: Dict[str, pd.DataFrame] = {}

    for market, items in by_m.items():
        cands = path_candidates(items)
        for c in cands:
            row = dict(c)
            row["market"] = market
            all_cands.append(row)

        eligible = [c for c in cands if int(c["n"]) >= MIN_PATH_N]
        if not eligible:
            eligible = [c for c in cands if int(c["n"]) > 0]
        if not eligible:
            best_rows.append(
                {
                    "market": market,
                    "path_id": "none",
                    "trade_mode": "first_only",
                    "allowed_sides": ["lower"],
                    "first_side_filter": "lower",
                    "n": 0,
                    "wins": 0,
                    "win_rate": 0.0,
                    "tattoo_win_rank": None,
                    "tattoo_year": None,
                    "tattoo_quarter": None,
                    "tattoo_mae_px": None,
                    "tattoo_mae_atr": None,
                    "risk_atr_mult": 2.0,
                    "note": "no path samples",
                }
            )
            continue

        # Highest WR; tie-break: larger n, then prefer first_over second, lower over upper.
        def rank_key(c: dict) -> Tuple:
            prefer_first = 1 if c["trade_mode"] == "first_only" else 0
            prefer_lower = 1 if "lower" in str(c.get("entry_side") or "") else 0
            return (float(c["win_rate"]), int(c["n"]), prefer_first, prefer_lower)

        best = max(eligible, key=rank_key)
        if market not in bars_cache:
            spec = MARKETS[market]
            bars_cache[market] = load_4h(spec.csv, market)
        bars = bars_cache[market]
        mae_list = _tattoo_rows(items, path_id=best["path_id"], bars=bars)
        tattoos.extend(mae_list)

        # Tattoo pick: 1st chronological win (GBPUSD style); fall back to 2nd then median.
        tattoo = None
        if mae_list:
            tattoo = mae_list[0]
            # For second_only, if a 2nd win exists, still size from 1st reverse-win MAE
            # (US30 previously used 2nd *first*-path win by mistake).
        mae_atr = float(tattoo["mae_atr"]) if tattoo else float("nan")
        risk = _round_up_half_atr(mae_atr) if tattoo else 2.0

        if best["trade_mode"] == "first_only":
            allowed = [best["entry_side"]]
        else:
            allowed = [s.strip() for s in str(best["entry_side"]).split(",") if s.strip()]

        best_rows.append(
            {
                "market": market,
                "path_id": best["path_id"],
                "trade_mode": best["trade_mode"],
                "allowed_sides": allowed,
                "first_side_filter": best["first_side_filter"],
                "n": int(best["n"]),
                "wins": int(best["wins"]),
                "win_rate": float(best["win_rate"]),
                "tattoo_win_rank": int(tattoo["win_rank"]) if tattoo else None,
                "tattoo_year": int(tattoo["year"]) if tattoo else None,
                "tattoo_quarter": int(tattoo["quarter"]) if tattoo else None,
                "tattoo_side": tattoo.get("entry_side") if tattoo else None,
                "tattoo_mae_px": float(tattoo["mae_px"]) if tattoo else None,
                "tattoo_mae_atr": mae_atr if tattoo else None,
                "tattoo_touch_ts": tattoo.get("touch_ts") if tattoo else None,
                "tattoo_resolve_ts": tattoo.get("resolve_ts") if tattoo else None,
                "risk_atr_mult": float(risk),
                "note": "max WR among n>=%d" % MIN_PATH_N,
            }
        )
    return best_rows, all_cands, tattoos


def write_artifacts(
    output_root: Path,
    detail: Sequence[QuarterPath],
    summary: Sequence[dict],
    *,
    best_paths: Optional[Sequence[dict]] = None,
    candidates: Optional[Sequence[dict]] = None,
    mae_tattoos: Optional[Sequence[dict]] = None,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    detail_df = pd.DataFrame([asdict(r) for r in detail])
    detail_df.to_csv(output_root / "quarter_paths.csv", index=False)
    sum_df = pd.DataFrame(list(summary))
    sum_df.to_csv(output_root / "summary.csv", index=False)

    if candidates is not None:
        pd.DataFrame(list(candidates)).to_csv(output_root / "path_candidates.csv", index=False)
    if mae_tattoos is not None:
        pd.DataFrame(list(mae_tattoos)).to_csv(output_root / "mae_tattoos.csv", index=False)
    if best_paths is not None:
        # Serialize allowed_sides as JSON-ish string for CSV round-trip.
        bp = []
        for row in best_paths:
            r = dict(row)
            sides = r.get("allowed_sides") or []
            if isinstance(sides, (list, tuple)):
                r["allowed_sides"] = ",".join(str(x) for x in sides)
            bp.append(r)
        pd.DataFrame(bp).to_csv(output_root / "best_path.csv", index=False)

    lines = [
        "# Quarterly ±4×ATR opposite-path study",
        "",
        "Same open-week mid ±ATR(14) levels as the quarterly ATR4 fade model (4h).",
        "",
        "**First fade win:** touch ±4, then opposite ±4, **before** same-side ±8.",
        "**Reverse after win:** from that opposite ±4, reach original ±4 before reverse-side ±8.",
        "",
        "| Market | Quarters | First touches | First win (→opp4) | Fail (±8) | Unresolved | First WR | Rev after win | Rev win | Rev fail8 | Rev WR |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in summary:
        lines.append(
            "| %s | %d | %d | %d | %d | %d | %.1f%% | %d | %d | %d | %.1f%% |"
            % (
                m["market"],
                int(m["quarters"]),
                int(m["first_touches"]),
                int(m["first_win_opposite4"]),
                int(m["first_fail_8"]),
                int(m["first_unresolved"]),
                100.0 * float(m["first_win_rate_given_touch"]),
                int(m["reverse_after_win"]),
                int(m["reverse_win"]),
                int(m["reverse_fail_8"]),
                100.0 * float(m["reverse_win_rate_given_first_win"]),
            )
        )

    if best_paths:
        lines += [
            "",
            "## Highest-WR path + MAE tattoo → risk",
            "",
            "Candidates: `first_lower`, `first_upper`, `second_any`, `second_after_lower`, "
            "`second_after_upper` (min n=%d). Risk = ceil(tattoo MAE/ATR to next 0.5)."
            % MIN_PATH_N,
            "",
            "| Market | Best path | Mode | Sides | N | WR | Tattoo | MAE | MAE/ATR | Risk |",
            "|---|---|---|---|---:|---:|---|---:|---:|---:|",
        ]
        for b in best_paths:
            tattoo = ""
            if b.get("tattoo_year"):
                tattoo = "%s Q%d #%s %s" % (
                    b.get("tattoo_year"),
                    b.get("tattoo_quarter"),
                    b.get("tattoo_win_rank"),
                    b.get("tattoo_side") or "",
                )
            mae_px = b.get("tattoo_mae_px")
            mae_atr = b.get("tattoo_mae_atr")
            lines.append(
                "| %s | %s | %s | %s | %d | %.1f%% | %s | %s | %s | %.2f×ATR |"
                % (
                    b["market"],
                    b.get("path_id") or "",
                    b.get("trade_mode") or "",
                    ",".join(b.get("allowed_sides") or [])
                    if isinstance(b.get("allowed_sides"), (list, tuple))
                    else (b.get("allowed_sides") or ""),
                    int(b.get("n") or 0),
                    100.0 * float(b.get("win_rate") or 0.0),
                    tattoo,
                    ("%.5g" % mae_px) if mae_px is not None else "",
                    (("%.2f×" % mae_atr) if mae_atr is not None and not math.isnan(mae_atr) else ""),
                    float(b.get("risk_atr_mult") or 0.0),
                )
            )

    lines += [
        "",
        "Hub: `%s`" % output_root.resolve(),
        "",
        "Detail: `quarter_paths.csv`, `path_candidates.csv`, `mae_tattoos.csv`, `best_path.csv`.",
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    if best_paths:
        (output_root / "BEST_PATH.md").write_text("\n".join(lines), encoding="utf-8")

    email = [
        "potions: quarterly ±4→opp4 path + best-path MAE complete",
        "",
        "Hub: %s" % output_root.resolve(),
        "Highest-WR path per market (n>=%d) + MAE tattoo → risk_atr_mult." % MIN_PATH_N,
        "",
    ]
    for m in summary:
        email.append(
            "  %s  touch=%d  first_win=%d (%.0f%%)  fail8=%d  |  after_win reverse_win=%d/%d (%.0f%%)  rev_fail8=%d"
            % (
                m["market"],
                int(m["first_touches"]),
                int(m["first_win_opposite4"]),
                100.0 * float(m["first_win_rate_given_touch"]),
                int(m["first_fail_8"]),
                int(m["reverse_win"]),
                int(m["reverse_after_win"]),
                100.0 * float(m["reverse_win_rate_given_first_win"]),
                int(m["reverse_fail_8"]),
            )
        )
    if best_paths:
        email.append("")
        email.append("Best path / risk:")
        for b in best_paths:
            email.append(
                "  %s  %s  WR=%.0f%% (n=%d)  risk=%.2f×ATR  tattoo_mae_atr=%s"
                % (
                    b["market"],
                    b.get("path_id"),
                    100.0 * float(b.get("win_rate") or 0.0),
                    int(b.get("n") or 0),
                    float(b.get("risk_atr_mult") or 0.0),
                    (
                        ("%.2f" % b["tattoo_mae_atr"])
                        if b.get("tattoo_mae_atr") is not None
                        and not math.isnan(float(b["tattoo_mae_atr"]))
                        else "n/a"
                    ),
                )
            )
    email += ["", "See SUMMARY.md / best_path.csv."]
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    symbols: Sequence[str],
    email: bool,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    detail: List[QuarterPath] = []
    try:
        for sym in symbols:
            market = MARKETS[sym.upper()]
            _progress(output_root, "START %s" % market.symbol)
            part = analyze_market(market, start=start, end=end)
            detail.extend(part)
            _progress(output_root, "DONE %s quarters=%d" % (market.symbol, len(part)))
        summary = summarize(detail)
        best_paths, candidates, mae_tattoos = select_best_paths(detail)
        write_artifacts(
            output_root,
            detail,
            summary,
            best_paths=best_paths,
            candidates=candidates,
            mae_tattoos=mae_tattoos,
        )
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "markets": list(symbols),
                    "best_paths": [
                        {
                            "market": b["market"],
                            "path_id": b.get("path_id"),
                            "trade_mode": b.get("trade_mode"),
                            "risk_atr_mult": b.get("risk_atr_mult"),
                            "win_rate": b.get("win_rate"),
                        }
                        for b in best_paths
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: quarterly ±4 path study FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: quarterly ±4 path study FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        send_email(
            subject="potions: quarterly ±4→opp4 path + best-path MAE complete",
            body=body,
        )
        _progress(output_root, "email sent")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--symbol", action="append", default=None)
    ap.add_argument("--start", default=None)
    ap.add_argument("--end", default=None)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    symbols = args.symbol or list(ALL_SYMBOLS)
    for s in symbols:
        if s.upper() not in MARKETS:
            raise SystemExit("Unknown symbol %s" % s)
    start = date.fromisoformat(args.start) if args.start else None
    end = date.fromisoformat(args.end) if args.end else None
    run_batch(
        output_root=args.output_root,
        symbols=symbols,
        email=args.email,
        start=start,
        end=end,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
