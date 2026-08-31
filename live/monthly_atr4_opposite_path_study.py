"""Monthly open-week ±4×ATR → opposite ±4 path study on **1h** bars.

Same logic as ``quarterly_atr4_opposite_path_study``, but:

- Period = calendar month (flatten horizon / path window = month)
- Bars / ATR = 1h Wilder ATR(14) at opening-week close
- Opening week = ISO week containing month start (clipped into the month)

Writes ``best_path.csv`` + MAE tattoos for the monthly ladder broker.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .gbpusd_quarterly_4h_charts import ATR_LEN, NY, wilder_atr
from .monthly_atr4_helpers import load_1h, month_windows, opening_week_slice
from .quarterly_atr4_fade_broker import ALL_SYMBOLS, MARKETS, MarketSpec
from .quarterly_atr4_opposite_path_study import (
    MIN_PATH_N,
    QuarterPath,
    _round_up_half_atr,
    _scan_path,
    _tattoo_rows,
    path_candidates,
    summarize,
    write_artifacts,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monthly_atr4_opposite_path"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = output_root / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _week_end(period_start: pd.Timestamp) -> Tuple[pd.Timestamp, pd.Timestamp]:
    local = (
        period_start.tz_convert(NY)
        if period_start.tzinfo is not None
        else period_start.tz_localize(NY)
    )
    monday = (local.normalize() - pd.Timedelta(days=int(local.weekday()))).normalize()
    return monday, monday + pd.Timedelta(days=7)


def analyze_market(
    market: MarketSpec,
    *,
    start: Optional[date] = None,
    end: Optional[date] = None,
) -> List[QuarterPath]:
    bars = load_1h(market)
    atr = wilder_atr(bars, ATR_LEN)
    bars = bars.assign(atr=atr)
    rows: List[QuarterPath] = []

    for year, month, m0, m1 in month_windows(bars, start, end):
        ow = opening_week_slice(bars, m0)
        empty = QuarterPath(
            market=market.symbol,
            year=year,
            quarter=month,  # month number stored in quarter field for shared selectors
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

        _, w1 = _week_end(m0)
        watch = bars[(bars.index >= max(w1, m0)) & (bars.index < m1)]
        base = QuarterPath(
            market=market.symbol,
            year=year,
            quarter=month,
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
        outcome, resolve_ts = _scan_path(
            path_bars, entry_side=first_side, target=target, fail=fail
        )
        base.first_outcome = outcome
        base.first_resolve_ts = resolve_ts

        if outcome != "win":
            rows.append(base)
            continue

        rev_side = "lower" if first_side == "upper" else "upper"
        rev_target = upper4 if first_side == "upper" else lower4
        rev_fail = lower8 if first_side == "upper" else upper8
        rev_start = None
        for j, ts in enumerate(path_bars.index):
            if str(ts) == resolve_ts:
                rev_start = j
                break
        rev_bars = path_bars.iloc[rev_start:] if rev_start is not None else path_bars.iloc[0:0]
        rev_out, rev_ts = _scan_path(
            rev_bars, entry_side=rev_side, target=rev_target, fail=rev_fail
        )
        base.reverse_outcome = rev_out
        base.reverse_resolve_ts = rev_ts
        rows.append(base)

    return rows


def select_best_paths(detail: Sequence[QuarterPath]) -> Tuple[List[dict], List[dict], List[dict]]:
    """Same WR / MAE tattoo logic as quarterly, but MAE measured on 1h bars."""
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

        def rank_key(c: dict) -> Tuple:
            prefer_first = 1 if c["trade_mode"] == "first_only" else 0
            prefer_lower = 1 if "lower" in str(c.get("entry_side") or "") else 0
            return (float(c["win_rate"]), int(c["n"]), prefer_first, prefer_lower)

        best = max(eligible, key=rank_key)
        if market not in bars_cache:
            bars_cache[market] = load_1h(MARKETS[market])
        bars = bars_cache[market]
        mae_list = _tattoo_rows(items, path_id=best["path_id"], bars=bars)
        tattoos.extend(mae_list)

        tattoo = mae_list[0] if mae_list else None
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
                "note": "max WR among n>=%d (1h monthly)" % MIN_PATH_N,
            }
        )
    return best_rows, all_cands, tattoos


def _rewrite_summary_md(output_root: Path) -> None:
    """Annotate SUMMARY.md that quarter column is calendar month."""
    path = output_root / "SUMMARY.md"
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    banner = (
        "# Monthly ±4×ATR opposite-path (1h)\n\n"
        "Period = **calendar month**. Opening-week mid ±4×ATR(14) on **1h** bars.\n"
        "In CSVs, the `quarter` field holds the **month number** (1–12).\n\n"
    )
    if text.startswith("#"):
        # drop first heading line then prepend
        lines = text.splitlines()
        rest = "\n".join(lines[1:]).lstrip("\n")
        path.write_text(banner + rest + ("\n" if not rest.endswith("\n") else ""), encoding="utf-8")
    else:
        path.write_text(banner + text, encoding="utf-8")


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
            _progress(output_root, "DONE %s months=%d" % (market.symbol, len(part)))
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
        _rewrite_summary_md(output_root)
        # Rewrite EMAIL header for monthly
        email_lines = [
            "potions: monthly ±4→opp4 path + best-path MAE complete (1h)",
            "",
            "Hub: %s" % output_root,
            "1h bars; calendar-month open week; min n=%d for WR path pick." % MIN_PATH_N,
            "",
        ]
        for b in best_paths:
            email_lines.append(
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
        email_lines += ["", "See SUMMARY.md / best_path.csv."]
        (output_root / "EMAIL.txt").write_text("\n".join(email_lines) + "\n", encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "period": "month",
                    "timeframe": "1h",
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
            "potions: monthly ±4 path study FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: monthly ±4 path study FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        send_email(
            subject="potions: monthly ±4→opp4 path + best-path MAE complete (1h)",
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
