"""USDJPY Asia-range London — month blackout + rolling WR/PF gate study.

1. Audit calendar-month PnL on existing sizing tapes → lock skip months.
2. Run unfiltered ``S_3_3_3`` (equal 3/3/3) for a baseline tape.
3. Broker-replay top sizing books + ``S_3_3_3`` with:
   - ``skip_entry_months`` (default: January)
   - rolling 50-campaign shadow gate: sit out when prior-50 WR < 40% or PF < 1

Rolling gate uses the **unfiltered** campaign tape as a shadow book so the
window keeps advancing (taken-only windows freeze after the first PF dip).

Hub → ``live/state/fx_v2b_asia_range_london_usdjpy_filters/``.
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import session_bars
from .fx_v2b_asia_range_london import (
    LONDON,
    REPO,
    build_session_asia_ranges,
    run_one,
    write_summary,
)
from .fx_v2b_london_ungated import (
    JPY_USD,
    MARKETS,
    _has_london_session,
    _progress,
    _regime_dates,
)

SIZING_HUB = REPO / "live" / "state" / "fx_v2b_asia_range_london_usdjpy_sizing"
FILTER_HUB = REPO / "live" / "state" / "fx_v2b_asia_range_london_usdjpy_filters"
BEST_BOOKS = ("S_0_5_0", "S_3_1_3")  # top N/S from sizing sweep
CURIOUS_BOOK = "S_3_3_3"
ALL_FILTER_BOOKS = BEST_BOOKS + (CURIOUS_BOOK,)


def _campaigns_from_unit_trades(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    g = (
        df.groupby("trade_id", as_index=False)
        .agg(entry_ts=("entry_ts", "first"), net_usd=("net_usd", "sum"))
        .sort_values("entry_ts")
        .reset_index(drop=True)
    )
    g["entry_ts"] = pd.to_datetime(g["entry_ts"], utc=True)
    g["entry_ny"] = g["entry_ts"].dt.tz_convert("America/New_York")
    g["session"] = g["entry_ny"].dt.date
    g["month"] = g["entry_ny"].dt.month
    g["year"] = g["entry_ny"].dt.year
    g["win"] = g["net_usd"] > 0
    return g


def _profit_factor(pnl: pd.Series) -> float:
    gains = float(pnl[pnl > 0].sum())
    losses = float((-pnl[pnl < 0]).sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def audit_months(campaigns: pd.DataFrame) -> pd.DataFrame:
    by_m = campaigns.groupby("month").agg(net=("net_usd", "sum"), n=("net_usd", "count"), wins=("win", "sum"))
    by_m["wr"] = by_m["wins"] / by_m["n"]
    by_m["avg"] = by_m["net"] / by_m["n"]
    year_month = campaigns.groupby(["year", "month"])["net_usd"].sum().unstack(fill_value=0.0)
    by_m["neg_frac_years"] = (year_month < 0).mean()
    by_m["years_neg"] = (year_month < 0).sum()
    by_m["mean_yr_net"] = year_month.mean()
    by_m["med_yr_net"] = year_month.median()
    by_m["net_usd"] = by_m["net"] / JPY_USD
    return by_m.reset_index()


def pick_skip_months(audit: pd.DataFrame, *, min_neg_frac: float = 0.55) -> List[int]:
    """Months that are net-negative on average and negative in most years."""
    bad = audit[(audit["neg_frac_years"] >= min_neg_frac) & (audit["mean_yr_net"] < 0)]
    return sorted(int(m) for m in bad["month"].tolist())


def write_month_audit(output_root: Path, audits: Dict[str, pd.DataFrame], skip_months: List[int]) -> None:
    lines = [
        "# USDJPY Asia-range London — calendar month audit",
        "",
        "Campaign PnL by NY calendar month on unfiltered sizing tapes.",
        "**Consistently negative** lock: `neg_frac_years >= 0.55` and `mean_yr_net < 0`.",
        "",
        "Skip months for this study: **%s**"
        % (", ".join(date(2000, m, 1).strftime("%B") for m in skip_months) if skip_months else "(none)"),
        "",
    ]
    for book, audit in audits.items():
        lines.extend(
            [
                "## %s" % book,
                "",
                "| Month | N | Net≈USD | WR | Neg years | Neg frac | Mean yr net≈USD |",
                "|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, r in audit.sort_values("month").iterrows():
            m = int(r["month"])
            flag = " **SKIP**" if m in skip_months else ""
            lines.append(
                "| %s | %d | $%.0f | %.1f%% | %d | %.2f | $%.0f |%s"
                % (
                    date(2000, m, 1).strftime("%b"),
                    int(r["n"]),
                    float(r["net_usd"]),
                    100.0 * float(r["wr"]),
                    int(r["years_neg"]),
                    float(r["neg_frac_years"]),
                    float(r["mean_yr_net"]) / JPY_USD,
                    flag,
                )
            )
        lines.append("")
    (output_root / "MONTH_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def shadow_skip_sessions(
    campaigns: pd.DataFrame,
    *,
    skip_months: Sequence[int],
    window: int = 50,
    min_wr: float = 0.40,
    min_pf: float = 1.0,
) -> Tuple[Set[date], dict]:
    """Sessions to sit out under month blackout + shadow rolling WR/PF gate."""
    skip_m = set(int(x) for x in skip_months)
    skip: Set[date] = set()
    reasons = {"month": 0, "wr": 0, "pf": 0, "both": 0}
    g = campaigns.reset_index(drop=True)
    for i, row in g.iterrows():
        sess = row["session"]
        month_block = int(row["month"]) in skip_m
        roll_block = False
        bad_wr = bad_pf = False
        if i >= window:
            hist = g.iloc[i - window : i]
            wr = float(hist["win"].mean())
            p = _profit_factor(hist["net_usd"])
            bad_wr = wr < min_wr
            bad_pf = p < min_pf
            roll_block = bad_wr or bad_pf
        if month_block:
            reasons["month"] += 1
            skip.add(sess)
        elif roll_block:
            if bad_wr and bad_pf:
                reasons["both"] += 1
            elif bad_wr:
                reasons["wr"] += 1
            else:
                reasons["pf"] += 1
            skip.add(sess)
    return skip, reasons


def baseline_unit_trades_path(book: str, output_root: Path) -> Path:
    if book == CURIOUS_BOOK:
        return output_root / "states" / ("usdjpy_v2b_asia_range_london_%s" % book) / "unit_trades.csv"
    return SIZING_HUB / "states" / ("usdjpy_v2b_asia_range_london_%s" % book) / "unit_trades.csv"


def filtered_book_tag(book: str) -> str:
    return "%s_flt" % book


def run_study(
    *,
    output_root: Path,
    start: date,
    force: bool,
    max_days: Optional[int],
    email: bool,
    skip_months: Optional[List[int]],
    window: int,
    min_wr: float,
    min_pf: float,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    market = MARKETS["USDJPY"]
    one_m = REPO / "fx" / "usdjpy_1m.csv"
    daily = REPO / "fx" / "usdjpy_daily.csv"

    # --- Month audit on existing top tapes ---
    audits: Dict[str, pd.DataFrame] = {}
    for book in BEST_BOOKS:
        ut = baseline_unit_trades_path(book, output_root)
        if not ut.exists():
            raise FileNotFoundError("Missing sizing tape for %s: %s" % (book, ut))
        audits[book] = audit_months(_campaigns_from_unit_trades(ut))
    auto_skip = sorted(set().union(*[set(pick_skip_months(a)) for a in audits.values()]))
    locked_skip = sorted(skip_months) if skip_months is not None else auto_skip
    if not locked_skip:
        locked_skip = [1]  # January is the clear seasonal hole across tapes
    write_month_audit(output_root, audits, locked_skip)
    _progress(output_root, "MONTH_AUDIT skip_months=%s" % locked_skip)

    # --- Load bars once ---
    _progress(output_root, "LOAD USDJPY...")
    gby = load_fx_1m_by_ny_date(one_m, market.symbol)
    eff_start = start if market.start is None else max(start, market.start)
    regime_dates = [d for d in _regime_dates(daily, gby, eff_start) if _has_london_session(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    session_asia_ranges = build_session_asia_ranges(gby, regime_dates)
    regime_dates = [d for d in regime_dates if d.isoformat() in session_asia_ranges]
    session_frames: Dict[date, pd.DataFrame] = {
        day: session_bars(gby.get(day), day, LONDON, dense=True) for day in regime_dates
    }
    _progress(output_root, "  sessions=%d asia_ranges=%d" % (len(regime_dates), len(session_asia_ranges)))

    rows: List[dict] = []
    errors: List[str] = []

    # --- Unfiltered S_3_3_3 baseline ---
    try:
        base = run_one(
            output_root=output_root,
            market=market,
            book=CURIOUS_BOOK,
            start=start,
            force=force,
            max_days=max_days,
            gby=gby,
            regime_dates=regime_dates,
            session_frames=session_frames,
            session_asia_ranges=session_asia_ranges,
        )
        base = dict(base)
        base["sizing"] = CURIOUS_BOOK
        base["variant"] = "unfiltered"
        base["skip_months"] = ""
        base["roll_window"] = 0
        base["skipped_campaigns"] = 0
        rows.append(base)
        write_summary(output_root, rows)
    except Exception as exc:
        errors.append("%s unfiltered: %s" % (CURIOUS_BOOK, exc))
        (output_root / ("ERROR_%s_unfiltered.txt" % CURIOUS_BOOK)).write_text(
            traceback.format_exc(), encoding="utf-8"
        )

    # --- Filtered broker replays ---
    gate_meta = []
    for book in ALL_FILTER_BOOKS:
        ut = baseline_unit_trades_path(book, output_root)
        if not ut.exists():
            errors.append("missing baseline tape %s" % ut)
            continue
        camps = _campaigns_from_unit_trades(ut)
        skip_sess, reasons = shadow_skip_sessions(
            camps,
            skip_months=locked_skip,
            window=window,
            min_wr=min_wr,
            min_pf=min_pf,
        )
        # Also black out month sessions with no campaign fill.
        for d in regime_dates:
            if d.month in locked_skip:
                skip_sess.add(d)
        allowed = [d for d in regime_dates if d not in skip_sess]
        meta = {
            "book": book,
            "skip_months": locked_skip,
            "window": window,
            "min_wr": min_wr,
            "min_pf": min_pf,
            "baseline_campaigns": len(camps),
            "skip_sessions": len(skip_sess),
            "allowed_sessions": len(allowed),
            "reasons": reasons,
        }
        gate_meta.append(meta)
        (output_root / ("gate_%s.json" % book)).write_text(json.dumps(meta, indent=2), encoding="utf-8")
        _progress(
            output_root,
            "GATE %s allowed=%d skip=%d reasons=%s" % (book, len(allowed), len(skip_sess), reasons),
        )
        try:
            # run_one derives strategy_id from book; use distinct output via book tag in a copy.
            # We pass a synthetic book name S_*_flt by running under aliased state via book string
            # that resolve_book understands — use real sizing book but redirect state by wrapping.
            row = _run_filtered(
                output_root=output_root,
                market=market,
                book=book,
                start=start,
                force=force,
                max_days=max_days,
                gby=gby,
                regime_dates=allowed,
                session_frames={d: session_frames[d] for d in allowed if d in session_frames},
                session_asia_ranges={d.isoformat(): session_asia_ranges[d.isoformat()] for d in allowed if d.isoformat() in session_asia_ranges},
                skip_months=locked_skip,
                window=window,
                min_wr=min_wr,
                min_pf=min_pf,
                skipped_campaigns=int(sum(reasons.values())),
            )
            rows = [r for r in rows if not (str(r.get("book")) == filtered_book_tag(book))]
            rows.append(row)
            write_summary(output_root, rows)
        except Exception as exc:
            errors.append("%s filtered: %s" % (book, exc))
            _progress(output_root, "ERROR %s filtered: %s" % (book, exc))
            (output_root / ("ERROR_%s_filtered.txt" % book)).write_text(
                traceback.format_exc(), encoding="utf-8"
            )

    (output_root / "GATE_META.json").write_text(json.dumps(gate_meta, indent=2), encoding="utf-8")
    _write_filter_index(output_root, rows, locked_skip, window, min_wr, min_pf, gate_meta)
    if email:
        _send_email(output_root, errors)
    return rows


def _run_filtered(
    *,
    output_root: Path,
    market,
    book: str,
    start: date,
    force: bool,
    max_days: Optional[int],
    gby,
    regime_dates: List[date],
    session_frames,
    session_asia_ranges,
    skip_months: List[int],
    window: int,
    min_wr: float,
    min_pf: float,
    skipped_campaigns: int,
) -> dict:
    """Run broker replay into ``*_flt`` state; preserve any unfiltered tree for ``book``."""
    import shutil

    from .fx_v2b_london_ungated import resolve_book

    tag = filtered_book_tag(book)
    src = output_root / "states" / ("usdjpy_v2b_asia_range_london_%s" % book)
    dst = output_root / "states" / ("usdjpy_v2b_asia_range_london_%s" % tag)
    stash = output_root / "states" / ("usdjpy_v2b_asia_range_london_%s__stash" % book)

    # Preserve unfiltered baseline (needed for S_3_3_3 tape + INDEX row).
    if src.exists():
        if stash.exists():
            shutil.rmtree(stash)
        shutil.move(str(src), str(stash))
    if dst.exists() and force:
        shutil.rmtree(dst)

    raw = run_one(
        output_root=output_root,
        market=market,
        book=book,
        start=start,
        force=force,
        max_days=max_days,
        gby=gby,
        regime_dates=regime_dates,
        session_frames=session_frames,
        session_asia_ranges=session_asia_ranges,
    )

    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.move(str(src), str(dst))
    if stash.exists():
        shutil.move(str(stash), str(src))

    sizing = resolve_book(book)
    row = dict(raw)
    row["book"] = tag
    row["sizing"] = book
    row["strategy_id"] = "usdjpy_v2b_asia_range_london_%s" % tag
    row["variant"] = "skip_months+roll50_wr40_pf1"
    row["skip_months"] = ",".join(str(m) for m in skip_months)
    row["roll_window"] = window
    row["min_wr"] = min_wr
    row["min_pf"] = min_pf
    row["skipped_campaigns"] = skipped_campaigns
    row["entry_qty"] = sizing["entry_qty"]
    row["state_root"] = str(dst)
    (dst / "metrics.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    return row


def _write_filter_index(
    output_root: Path,
    rows: List[dict],
    skip_months: List[int],
    window: int,
    min_wr: float,
    min_pf: float,
    gate_meta: list,
) -> None:
    ranked = sorted(rows, key=lambda r: float(r.get("net_over_stress") or 0.0), reverse=True)
    month_names = ", ".join(date(2000, m, 1).strftime("%b") for m in skip_months)
    lines = [
        "# USDJPY Asia-range London — month + rolling WR/PF filters",
        "",
        "Filters:",
        "- Skip entry months: **%s** (consistently negative on sizing tapes)" % month_names,
        "- Shadow rolling %d campaigns: sit out when WR < %.0f%% or PF < %.2f"
        % (window, 100.0 * min_wr, min_pf),
        "",
        "| Rank | Book | Variant | Sessions | Trades | Net≈USD | Stress≈USD | N/S | Win% | PF |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        lines.append(
            "| %d | %s | %s | %d | %d | $%.0f | $%.0f | %.2f | %.1f | %.3f |"
            % (
                i,
                r.get("sizing") or r.get("book"),
                r.get("variant") or "—",
                int(r.get("regime_days") or 0),
                int(r.get("trades") or 0),
                float(r.get("net_usd") or 0),
                float(r.get("stress_dd_usd") or 0),
                float(r.get("net_over_stress") or 0),
                float(r.get("win_rate") or 0),
                float(r.get("profit_factor") or 0),
            )
        )
    lines.extend(["", "## Gate skips", ""])
    for g in gate_meta:
        lines.append(
            "- **%s**: allowed=%d skip_sessions=%d reasons=%s"
            % (g["book"], g["allowed_sessions"], g["skip_sessions"], g["reasons"])
        )
    lines.extend(["", "- Hub: `%s`" % output_root.as_posix(), ""])
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(rows).to_csv(output_root / "summary.csv", index=False)

    email = [
        "potions: USDJPY Asia-range month+rolling filters complete",
        "",
        "Skip months: %s" % month_names,
        "Rolling gate: last %d campaigns WR<%.0f%% or PF<%.2f (shadow unfiltered tape)"
        % (window, 100.0 * min_wr, min_pf),
        "",
        "Results by N/S:",
    ]
    for r in ranked:
        email.append(
            "  %s [%s]  N/S=%.2f  net≈$%.0f  trades=%d  wr=%.1f  pf=%.3f"
            % (
                r.get("sizing") or r.get("book"),
                r.get("variant"),
                float(r.get("net_over_stress") or 0),
                float(r.get("net_usd") or 0),
                int(r.get("trades") or 0),
                float(r.get("win_rate") or 0),
                float(r.get("profit_factor") or 0),
            )
        )
    email.extend(["", "Hub: %s" % output_root])
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def _send_email(output_root: Path, errors: List[str]) -> None:
    try:
        from .notify_email import send_email

        body = (output_root / "EMAIL.txt").read_text(encoding="utf-8")
        if errors:
            body += "\n\nErrors:\n" + "\n".join(errors)
        send_email(subject="potions: USDJPY Asia-range filters complete", body=body)
        _progress(output_root, "EMAIL sent")
    except Exception as exc:
        _progress(output_root, "EMAIL failed: %s" % exc)


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=FILTER_HUB)
    p.add_argument("--start", default="2015-01-02")
    p.add_argument("--max-days", type=int, default=None)
    p.add_argument("--no-force", action="store_true")
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--skip-months",
        default="",
        help="Comma months 1-12 (default: auto from audit, falls back to January).",
    )
    p.add_argument("--roll-window", type=int, default=50)
    p.add_argument("--min-wr", type=float, default=0.40)
    p.add_argument("--min-pf", type=float, default=1.0)
    args = p.parse_args(argv)
    skip = [int(x) for x in args.skip_months.split(",") if x.strip()] or None
    run_study(
        output_root=args.output_root,
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
        email=args.email,
        skip_months=skip,
        window=args.roll_window,
        min_wr=args.min_wr,
        min_pf=args.min_pf,
    )
    print("Wrote %s" % (args.output_root / "INDEX.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
