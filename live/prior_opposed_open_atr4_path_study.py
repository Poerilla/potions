"""Prior-opposed session days: open ±4×ATR(14) opposite-path on 5m (non-HA).

Diagnostic only — no broker fills.

On days when a profitable prior-opposed book has an entry campaign:
  1. Opening price = first session 5m bar open (RTH 09:30 or London 03:00).
  2. ATR14 = Wilder ATR on continuous 5m, known at open (prior completed bar).
  3. Levels: open ±4×ATR and open ±8×ATR.
  4. Same path rules as ``quarterly_atr4_opposite_path_study``:
       first fade WIN if opposite ±4 before same-side ±8;
       reverse WIN if original ±4 before reverse-side ±8.
  5. Rank path candidates by WR → ``best_path.csv``.

Hub: ``live/state/prior_opposed_open_atr4_path/``.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import asdict, dataclass
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .gbpusd_quarterly_4h_charts import ATR_LEN, wilder_atr
from .quarterly_atr4_opposite_path_study import (
    MIN_PATH_N,
    _round_up_half_atr,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "prior_opposed_open_atr4_path"
NY = "America/New_York"
CACHE_5M = REPO / "live" / "state" / "_cache" / "bars"


@dataclass(frozen=True)
class BookSpec:
    key: str
    symbol: str
    variant: str
    fills: Path
    session: str  # rth | london
    ns_note: str


# Profitable prior-opposed books (N/S > 0 on banked hubs).
BOOKS: Dict[str, BookSpec] = {
    "nq_rl": BookSpec(
        key="nq_rl",
        symbol="NQ",
        variant="resting_limit_S_1_1_3",
        fills=REPO
        / "live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/states/"
        / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        session="rth",
        ns_note="19.40",
    ),
    "mnq_rl": BookSpec(
        key="mnq_rl",
        symbol="MNQ",
        variant="resting_limit_S_1_1_3",
        fills=REPO
        / "live/state/mnq_v2b_prior_opposed_stpmc_resting_limit/states/"
        / "mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        session="rth",
        ns_note="18.44",
    ),
    "ym_rl": BookSpec(
        key="ym_rl",
        symbol="YM",
        variant="resting_limit_S_1_1_3",
        fills=REPO
        / "live/state/ym_v2b_prior_opposed_stpmc_resting_limit/states/"
        / "ym_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        session="rth",
        ns_note="8.53",
    ),
    "mym_rl": BookSpec(
        key="mym_rl",
        symbol="MYM",
        variant="resting_limit_S_1_1_3",
        fills=REPO
        / "live/state/mym_v2b_prior_opposed_stpmc_resting_limit/states/"
        / "mym_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        session="rth",
        ns_note="6.47",
    ),
    "us30_london": BookSpec(
        key="us30_london",
        symbol="US30",
        variant="london_prior_opposed_S_1_1_3",
        fills=REPO
        / "live/state/fx_v2b_london_prior_opposed/states/"
        / "us30_v2b_london_prior_opposed_S_1_1_3/fills.csv",
        session="london",
        ns_note="6.23",
    ),
    "nas100_london": BookSpec(
        key="nas100_london",
        symbol="NAS100",
        variant="london_prior_opposed_S_1_1_3",
        fills=REPO
        / "live/state/fx_v2b_london_prior_opposed/states/"
        / "nas100_v2b_london_prior_opposed_S_1_1_3/fills.csv",
        session="london",
        ns_note="8.38",
    ),
}


@dataclass
class DayPath:
    book: str
    symbol: str
    variant: str
    session_day: str
    atr14: float
    open_px: float
    upper4: float
    lower4: float
    upper8: float
    lower8: float
    first_side: str
    first_touch_ts: str
    first_outcome: str
    first_resolve_ts: str
    reverse_outcome: str
    reverse_resolve_ts: str


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _session_bounds(session: str) -> Tuple[time, time]:
    if session == "london":
        return time(3, 0), time(12, 0)  # open 03:00; flatten < 12:00
    return time(9, 30), time(16, 0)


def campaign_days(fills_path: Path) -> List[date]:
    df = pd.read_csv(fills_path)
    ent = df[df["reason"].astype(str) == "entry"].copy()
    if ent.empty:
        return []
    ts = pd.to_datetime(ent["ts"], utc=True, errors="coerce")
    local = ts.dt.tz_convert(NY)
    days = sorted({d.date() for d in local.dropna()})
    return days


def load_5m(symbol: str) -> pd.DataFrame:
    """Load continuous 5m OHLC (non-HA) with Wilder ATR; index = NY ts."""
    sym = symbol.upper()
    cache = CACHE_5M / ("%s_5m.parquet" % sym.lower())
    if cache.exists():
        df = pd.read_parquet(cache)
    else:
        from .futures_intraday_hp_sizeup_lib import ensure_tf_bars

        df = ensure_tf_bars(sym, "5m")
        if df is None or df.empty:
            raise FileNotFoundError("no 5m bars for %s" % sym)
    df = df.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
    df = df.set_index("ts").sort_index()
    keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
    df = df[keep].dropna(subset=["open", "high", "low", "close"])
    atr = wilder_atr(df, ATR_LEN)
    # Causal ATR at bar open = previous completed bar's ATR.
    df = df.assign(atr=atr, atr_known=atr.shift(1))
    return df


def _scan_path_arrays(
    highs: Sequence[float],
    lows: Sequence[float],
    ts_vals: Sequence[object],
    *,
    entry_side: str,
    target: float,
    fail: float,
) -> Tuple[str, str]:
    """Array scan for target (opposite ±4) vs fail (same-side ±8)."""
    target_side = "lower" if entry_side == "upper" else "upper"
    fail_side = entry_side
    for i in range(len(highs)):
        hi = float(highs[i])
        lo = float(lows[i])
        hit_fail = (hi >= fail) if fail_side == "upper" else (lo <= fail)
        hit_tgt = (hi >= target) if target_side == "upper" else (lo <= target)
        if hit_fail and hit_tgt:
            return "fail_8", str(ts_vals[i])
        if hit_fail:
            return "fail_8", str(ts_vals[i])
        if hit_tgt:
            return "win", str(ts_vals[i])
    return "unresolved", ""


def analyze_book(book: BookSpec, bars: pd.DataFrame) -> List[DayPath]:
    open_t, end_t = _session_bounds(book.session)
    days = campaign_days(book.fills)
    # Pre-index by calendar date once (avoids O(days × bars) masks).
    by_date: Dict[date, pd.DataFrame] = {
        d: g for d, g in bars.groupby(bars.index.date, sort=False)
    }
    rows: List[DayPath] = []
    for d in days:
        empty = DayPath(
            book=book.key,
            symbol=book.symbol,
            variant=book.variant,
            session_day=str(d),
            atr14=float("nan"),
            open_px=float("nan"),
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
        day = by_date.get(d)
        if day is None or day.empty:
            rows.append(empty)
            continue
        times = day.index.time
        sess = day[(times >= open_t) & (times < end_t)]
        if sess.empty:
            rows.append(empty)
            continue
        open_bar = sess.iloc[0]
        atr14 = float(open_bar["atr_known"])
        open_px = float(open_bar["open"])
        if not (atr14 > 0) or math.isnan(atr14) or not math.isfinite(open_px):
            rows.append(empty)
            continue
        upper4 = open_px + 4.0 * atr14
        lower4 = open_px - 4.0 * atr14
        upper8 = open_px + 8.0 * atr14
        lower8 = open_px - 8.0 * atr14
        highs = sess["high"].to_numpy(dtype=float)
        lows = sess["low"].to_numpy(dtype=float)
        ts_vals = list(sess.index)
        base = DayPath(
            book=book.key,
            symbol=book.symbol,
            variant=book.variant,
            session_day=str(d),
            atr14=atr14,
            open_px=open_px,
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
        first_side = ""
        first_i = -1
        first_ts = ""
        for i in range(len(highs)):
            hit_up = highs[i] >= upper4
            hit_dn = lows[i] <= lower4
            if hit_up and hit_dn:
                base.first_side = "dual_skip"
                base.first_touch_ts = str(ts_vals[i])
                base.first_outcome = "dual_skip"
                break
            if hit_up or hit_dn:
                first_side = "upper" if hit_up else "lower"
                first_i = i
                first_ts = str(ts_vals[i])
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
        outcome, resolve_ts = _scan_path_arrays(
            highs[first_i:],
            lows[first_i:],
            ts_vals[first_i:],
            entry_side=first_side,
            target=target,
            fail=fail,
        )
        base.first_outcome = outcome
        base.first_resolve_ts = resolve_ts
        if outcome != "win":
            rows.append(base)
            continue

        rev_side = "lower" if first_side == "upper" else "upper"
        rev_target = upper4 if first_side == "upper" else lower4
        rev_fail = lower8 if first_side == "upper" else upper8
        rev_start = 0
        for j, ts in enumerate(ts_vals[first_i:]):
            if str(ts) == resolve_ts:
                rev_start = j
                break
        path_h = highs[first_i:]
        path_l = lows[first_i:]
        path_t = ts_vals[first_i:]
        rev_out, rev_ts = _scan_path_arrays(
            path_h[rev_start:],
            path_l[rev_start:],
            path_t[rev_start:],
            entry_side=rev_side,
            target=rev_target,
            fail=rev_fail,
        )
        base.reverse_outcome = rev_out
        base.reverse_resolve_ts = rev_ts
        rows.append(base)
    return rows


def summarize(rows: Sequence[DayPath]) -> List[dict]:
    out: List[dict] = []
    by_b: Dict[str, List[DayPath]] = {}
    for r in rows:
        by_b.setdefault(r.book, []).append(r)
    for book, items in by_b.items():
        touched = [r for r in items if r.first_side in {"upper", "lower"}]
        wins = [r for r in touched if r.first_outcome == "win"]
        fails = [r for r in touched if r.first_outcome == "fail_8"]
        unresolved = [r for r in touched if r.first_outcome == "unresolved"]
        rev_wins = [r for r in wins if r.reverse_outcome == "win"]
        rev_fails = [r for r in wins if r.reverse_outcome == "fail_8"]
        n_touch = len(touched)
        n_win = len(wins)
        spec = BOOKS[book]
        out.append(
            {
                "book": book,
                "symbol": spec.symbol,
                "variant": spec.variant,
                "po_ns": spec.ns_note,
                "campaign_days": len(items),
                "first_touches": n_touch,
                "first_win_opposite4": n_win,
                "first_fail_8": len(fails),
                "first_unresolved": len(unresolved),
                "dual_skip": sum(1 for r in items if r.first_outcome == "dual_skip"),
                "no_touch": sum(1 for r in items if r.first_outcome == "no_touch"),
                "no_levels": sum(1 for r in items if r.first_outcome == "no_levels"),
                "first_win_rate_given_touch": (n_win / n_touch) if n_touch else 0.0,
                "reverse_after_win": n_win,
                "reverse_win": len(rev_wins),
                "reverse_fail_8": len(rev_fails),
                "reverse_win_rate_given_first_win": (len(rev_wins) / n_win) if n_win else 0.0,
            }
        )
    return out


def path_candidates(items: Sequence[DayPath]) -> List[dict]:
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

    def add_second(label: str, subset: Sequence[DayPath], entry_sides: Sequence[str]) -> None:
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
    add_second("second_after_lower", [r for r in wins if r.first_side == "lower"], ["upper"])
    add_second("second_after_upper", [r for r in wins if r.first_side == "upper"], ["lower"])
    return cands


def _ts(val: str) -> Optional[pd.Timestamp]:
    if not val or (isinstance(val, float) and math.isnan(val)):
        return None
    ts = pd.Timestamp(val)
    if ts.tzinfo is None:
        return ts.tz_localize(NY)
    return ts.tz_convert(NY)


def _first_leg_mae(row: DayPath, bars: pd.DataFrame) -> Optional[dict]:
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
        "session_day": row.session_day,
        "touch_ts": str(touch),
        "resolve_ts": str(resolve),
        "atr14": atr,
        "mae_px": mae_px,
        "mae_atr": (mae_px / atr) if atr > 0 else float("nan"),
    }


def _reverse_leg_mae(row: DayPath, bars: pd.DataFrame) -> Optional[dict]:
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
        end_idx = bars.index[bars.index >= start]
        end = end_idx[-1] if len(end_idx) else start
    seg = bars[(bars.index >= start) & (bars.index <= end)]
    if seg.empty:
        return None
    atr = float(row.atr14)
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
        "session_day": row.session_day,
        "touch_ts": str(start),
        "resolve_ts": str(end),
        "atr14": atr,
        "mae_px": mae_px,
        "mae_atr": (mae_px / atr) if atr > 0 else float("nan"),
        "reverse_outcome": row.reverse_outcome,
        "first_side": row.first_side,
    }


def _tattoo_rows(items: Sequence[DayPath], *, path_id: str, bars: pd.DataFrame) -> List[dict]:
    out: List[dict] = []
    if path_id.startswith("first_"):
        side = path_id.split("_", 1)[1]
        wins = [r for r in items if r.first_side == side and r.first_outcome == "win"]
        wins = sorted(wins, key=lambda r: (r.session_day, r.first_touch_ts))
        for i, r in enumerate(wins, start=1):
            mae = _first_leg_mae(r, bars)
            if mae:
                mae["win_rank"] = i
                mae["path_id"] = path_id
                mae["book"] = r.book
                mae["symbol"] = r.symbol
                out.append(mae)
        return out
    if path_id == "second_after_lower":
        pool = [r for r in items if r.first_side == "lower" and r.reverse_outcome == "win"]
    elif path_id == "second_after_upper":
        pool = [r for r in items if r.first_side == "upper" and r.reverse_outcome == "win"]
    else:
        pool = [r for r in items if r.reverse_outcome == "win"]
    pool = sorted(pool, key=lambda r: (r.session_day, r.first_resolve_ts))
    for i, r in enumerate(pool, start=1):
        mae = _reverse_leg_mae(r, bars)
        if mae and mae.get("reverse_outcome") == "win":
            mae["win_rank"] = i
            mae["path_id"] = path_id
            mae["book"] = r.book
            mae["symbol"] = r.symbol
            out.append(mae)
    return out


def select_best_paths(
    detail: Sequence[DayPath],
    bars_by_symbol: Dict[str, pd.DataFrame],
) -> Tuple[List[dict], List[dict], List[dict]]:
    by_b: Dict[str, List[DayPath]] = {}
    for r in detail:
        by_b.setdefault(r.book, []).append(r)

    best_rows: List[dict] = []
    all_cands: List[dict] = []
    tattoos: List[dict] = []

    for book, items in by_b.items():
        spec = BOOKS[book]
        cands = path_candidates(items)
        for c in cands:
            row = dict(c)
            row["book"] = book
            row["symbol"] = spec.symbol
            row["variant"] = spec.variant
            all_cands.append(row)

        eligible = [c for c in cands if int(c["n"]) >= MIN_PATH_N]
        if not eligible:
            eligible = [c for c in cands if int(c["n"]) > 0]
        if not eligible:
            best_rows.append(
                {
                    "book": book,
                    "symbol": spec.symbol,
                    "variant": spec.variant,
                    "path_id": "none",
                    "trade_mode": "first_only",
                    "allowed_sides": ["lower"],
                    "first_side_filter": "lower",
                    "n": 0,
                    "wins": 0,
                    "win_rate": 0.0,
                    "risk_atr_mult": 2.0,
                    "exists": False,
                    "note": "no path samples on prior-opposed days",
                }
            )
            continue

        def rank_key(c: dict) -> Tuple:
            prefer_first = 1 if c["trade_mode"] == "first_only" else 0
            prefer_lower = 1 if "lower" in str(c.get("entry_side") or "") else 0
            return (float(c["win_rate"]), int(c["n"]), prefer_first, prefer_lower)

        best = max(eligible, key=rank_key)
        bars = bars_by_symbol[spec.symbol]
        mae_list = _tattoo_rows(items, path_id=best["path_id"], bars=bars)
        tattoos.extend(mae_list)
        tattoo = mae_list[0] if mae_list else None
        mae_atr = float(tattoo["mae_atr"]) if tattoo else float("nan")
        risk = _round_up_half_atr(mae_atr) if tattoo else 2.0
        if best["trade_mode"] == "first_only":
            allowed = [best["entry_side"]]
        else:
            allowed = [s.strip() for s in str(best["entry_side"]).split(",") if s.strip()]
        wr = float(best["win_rate"])
        # "Exists" = eligible sample + WR >= 50% (meaningful path, not just least-bad).
        exists = int(best["n"]) >= MIN_PATH_N and wr >= 0.50
        best_rows.append(
            {
                "book": book,
                "symbol": spec.symbol,
                "variant": spec.variant,
                "path_id": best["path_id"],
                "trade_mode": best["trade_mode"],
                "allowed_sides": allowed,
                "first_side_filter": best["first_side_filter"],
                "n": int(best["n"]),
                "wins": int(best["wins"]),
                "win_rate": wr,
                "tattoo_win_rank": int(tattoo["win_rank"]) if tattoo else None,
                "tattoo_day": tattoo.get("session_day") if tattoo else None,
                "tattoo_side": tattoo.get("entry_side") if tattoo else None,
                "tattoo_mae_px": float(tattoo["mae_px"]) if tattoo else None,
                "tattoo_mae_atr": mae_atr if tattoo else None,
                "tattoo_touch_ts": tattoo.get("touch_ts") if tattoo else None,
                "tattoo_resolve_ts": tattoo.get("resolve_ts") if tattoo else None,
                "risk_atr_mult": float(risk),
                "exists": exists,
                "note": (
                    "best WR among n>=%d; WR>=50%% → exists"
                    % MIN_PATH_N
                    if exists
                    else "max WR among n>=%d but WR<50%% (weak / no clean best path)"
                    % MIN_PATH_N
                ),
            }
        )
    return best_rows, all_cands, tattoos


def write_artifacts(
    output_root: Path,
    detail: Sequence[DayPath],
    summary: Sequence[dict],
    *,
    best_paths: Optional[Sequence[dict]] = None,
    candidates: Optional[Sequence[dict]] = None,
    mae_tattoos: Optional[Sequence[dict]] = None,
) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([asdict(r) for r in detail]).to_csv(output_root / "day_paths.csv", index=False)
    pd.DataFrame(list(summary)).to_csv(output_root / "summary.csv", index=False)
    if candidates is not None:
        pd.DataFrame(list(candidates)).to_csv(output_root / "path_candidates.csv", index=False)
    if mae_tattoos is not None:
        pd.DataFrame(list(mae_tattoos)).to_csv(output_root / "mae_tattoos.csv", index=False)
    if best_paths is not None:
        bp = []
        for row in best_paths:
            r = dict(row)
            sides = r.get("allowed_sides") or []
            if isinstance(sides, (list, tuple)):
                r["allowed_sides"] = ",".join(str(x) for x in sides)
            bp.append(r)
        pd.DataFrame(bp).to_csv(output_root / "best_path.csv", index=False)

    lines = [
        "# Prior-opposed open ±4×ATR opposite-path (5m, non-HA)",
        "",
        "Universe: profitable prior-opposed books only.",
        "Levels: **session open price** ± k×ATR(14) on continuous **5m** OHLC (not Heikin Ashi).",
        "ATR known at open = prior completed 5m Wilder ATR.",
        "Days = campaign entry days from each book's fills.",
        "",
        "**First fade win:** touch ±4, then opposite ±4, **before** same-side ±8.",
        "**Reverse after win:** from opposite ±4, reach original ±4 before reverse-side ±8.",
        "",
        "| Book | Symbol | Variant | PO N/S | Days | Touches | First→opp4 | Fail±8 | Unres | First WR | Rev win | Rev WR |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in summary:
        lines.append(
            "| %s | %s | %s | %s | %d | %d | %d | %d | %d | %.1f%% | %d | %.1f%% |"
            % (
                m["book"],
                m["symbol"],
                m["variant"],
                m["po_ns"],
                int(m["campaign_days"]),
                int(m["first_touches"]),
                int(m["first_win_opposite4"]),
                int(m["first_fail_8"]),
                int(m["first_unresolved"]),
                100.0 * float(m["first_win_rate_given_touch"]),
                int(m["reverse_win"]),
                100.0 * float(m["reverse_win_rate_given_first_win"]),
            )
        )

    if best_paths:
        lines += [
            "",
            "## Best path (max WR, n≥%d); exists if WR≥50%%" % MIN_PATH_N,
            "",
            "| Book | Symbol | Best path | Mode | Sides | N | WR | Exists | Risk |",
            "|---|---|---|---|---|---:|---:|---|---:|",
        ]
        for b in best_paths:
            lines.append(
                "| %s | %s | %s | %s | %s | %d | %.1f%% | %s | %.2f×ATR |"
                % (
                    b["book"],
                    b["symbol"],
                    b.get("path_id") or "",
                    b.get("trade_mode") or "",
                    ",".join(b.get("allowed_sides") or [])
                    if isinstance(b.get("allowed_sides"), (list, tuple))
                    else (b.get("allowed_sides") or ""),
                    int(b.get("n") or 0),
                    100.0 * float(b.get("win_rate") or 0.0),
                    "YES" if b.get("exists") else "no",
                    float(b.get("risk_atr_mult") or 0.0),
                )
            )

    lines += [
        "",
        "Hub: `%s`" % output_root.resolve(),
        "",
        "Detail: `day_paths.csv`, `path_candidates.csv`, `mae_tattoos.csv`, `best_path.csv`.",
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email = [
        "potions: prior-opposed open±4ATR 5m path study complete",
        "",
        "Hub: %s" % output_root.resolve(),
        "5m non-HA; open ±4/±8 ATR on prior-opposed campaign days.",
        "",
    ]
    if best_paths:
        email.append("Best path (exists=WR≥50%% & n≥%d):" % MIN_PATH_N)
        for b in best_paths:
            email.append(
                "  %s/%s  %s  WR=%.0f%% (n=%d)  exists=%s  risk=%.2f×ATR"
                % (
                    b["symbol"],
                    b.get("variant"),
                    b.get("path_id"),
                    100.0 * float(b.get("win_rate") or 0.0),
                    int(b.get("n") or 0),
                    b.get("exists"),
                    float(b.get("risk_atr_mult") or 0.0),
                )
            )
    email.append("")
    email.append("See SUMMARY.md / best_path.csv.")
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_batch(
    *,
    output_root: Path,
    book_keys: Sequence[str],
    email: bool,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    detail: List[DayPath] = []
    bars_by_symbol: Dict[str, pd.DataFrame] = {}
    try:
        for key in book_keys:
            book = BOOKS[key]
            _progress(
                output_root,
                "START %s symbol=%s variant=%s" % (book.key, book.symbol, book.variant),
            )
            if book.symbol not in bars_by_symbol:
                _progress(output_root, "  load 5m %s" % book.symbol)
                bars_by_symbol[book.symbol] = load_5m(book.symbol)
                _progress(
                    output_root,
                    "  bars=%s" % f"{len(bars_by_symbol[book.symbol]):,}",
                )
            part = analyze_book(book, bars_by_symbol[book.symbol])
            detail.extend(part)
            _progress(
                output_root,
                "DONE %s days=%d touches=%d"
                % (
                    book.key,
                    len(part),
                    sum(1 for r in part if r.first_side in {"upper", "lower"}),
                ),
            )
        summary = summarize(detail)
        best_paths, candidates, mae_tattoos = select_best_paths(detail, bars_by_symbol)
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
                    "books": list(book_keys),
                    "best_paths": [
                        {
                            "book": b["book"],
                            "symbol": b["symbol"],
                            "path_id": b.get("path_id"),
                            "win_rate": b.get("win_rate"),
                            "exists": b.get("exists"),
                            "risk_atr_mult": b.get("risk_atr_mult"),
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
            "potions: prior-opposed open±4ATR path study FAILED\n\nHub: %s\n\n%s\n"
            % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: prior-opposed open±4ATR path study FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        send_email(
            subject="potions: prior-opposed open±4ATR 5m path study complete",
            body=body,
        )
        _progress(output_root, "email sent")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--book", action="append", default=None, help="Book key (default: all profitable)")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    keys = args.book or list(BOOKS.keys())
    for k in keys:
        if k not in BOOKS:
            raise SystemExit("Unknown book %s; choose from %s" % (k, ", ".join(BOOKS)))
    run_batch(output_root=args.output_root, book_keys=keys, email=bool(args.email))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
