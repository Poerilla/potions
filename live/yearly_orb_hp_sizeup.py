"""Yearly ORB HP size-up: profile NQ/ES/YM → 1.25×/2× nulls → LIVE_PLAN → charts.

Adds YM to the yearly/daily condition profile (previously NQ+ES only), then
runs the matched-added-exposure suite at exact 1.25× and 2×. Also recounts
the NQ L_4_1_1 campaign win rate from fills and emails best-outcome
daily charts (PNG attachments, not zip), one instrument per email batch.

``--causal-close`` rebuilds the same three books from the next-open range-close
PaperBroker tape (no same-bar-open scratches) into dedicated hubs.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.yearly_orb_hp_sizeup --email
  python -m live.yearly_orb_hp_sizeup --causal-close --email
"""

from __future__ import annotations

import argparse
import html
import json
import math
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
import live.intraday_hp_sizeup_nulls as fxnulls
from live.intraday_hp_sizeup_nulls import evaluate_pair, write_hub_reports
from live.notify_email import send_email
from live.yearly_daily_condition_profile import (
    CONDITION_COLS,
    Book,
    _default_books,
    refresh_yorb_from_sizing,
    run as profile_run,
)

from .fx_v2b_london_ungated import REPO

STUDY = "yearly_orb_hp_sizeup_v1"
PROFILE_HUB = REPO / "live" / "state" / "yearly_daily_condition_profile"
NULLS_HUB = REPO / "live" / "state" / "yearly_orb_hp_sizeup_nulls"
NULLS_HUB_2X = REPO / "live" / "state" / "yearly_orb_hp_sizeup_nulls_2x"
LIVE_HUB = REPO / "live" / "state" / "yearly_orb_hp_live_plan"
CHARTS_HUB = REPO / "live" / "state" / "yearly_orb_hp_charts"
CAUSAL_SIZING_HUB = REPO / "live" / "state" / "yearly_orb_sizing_sweep_futures_causal_close"
SEED = 20260817
FUTURES_YORB = ("nq_yorb", "es_yorb", "ym_yorb")
# Same cells as the pre-causal HP / bucket-chart study (not causal-best OCO).
CAUSAL_PINNED_SLUGS = (("nq_yorb", "NQ", "L_4_1_1"), ("es_yorb", "ES", "L_4_2_1"), ("ym_yorb", "YM", "L_4_1_1"))
MAX_PAIRS_PER_BOOK = 2
HP_COVERAGE_MAX = 0.35
HP_COVERAGE_MIN = 0.08
# Raw PNG budget per email (base64 inflates ~4/3; stay under ~25MB JSON).
PNG_BATCH_BYTES = 18 * 1024 * 1024
PNG_MAX_PER_EMAIL = 18
CAUSAL_CLOSE = False
CHART_SUBJECT = "yearly ORB"
DECISION_ALIAS = {
    "BORDERLINE PAPER": "PROVISIONAL PAPER",
    "RISK-BUDGET PROFILE": "RISK THROTTLE",
}


def _progress(msg: str, *, hub: Optional[Path] = None) -> None:
    dest = hub if hub is not None else LIVE_HUB
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(msg.rstrip() + "\n")
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        pass


def configure_causal_close() -> None:
    """Point HP / charts at the next-open range-close futures tape."""
    global STUDY, PROFILE_HUB, NULLS_HUB, NULLS_HUB_2X, LIVE_HUB, CHARTS_HUB
    global CAUSAL_CLOSE, CHART_SUBJECT
    STUDY = "yearly_orb_hp_sizeup_causal_close"
    PROFILE_HUB = REPO / "live" / "state" / "yearly_daily_condition_profile_futures_causal_close"
    NULLS_HUB = REPO / "live" / "state" / "yearly_orb_hp_sizeup_nulls_causal_close"
    NULLS_HUB_2X = REPO / "live" / "state" / "yearly_orb_hp_sizeup_nulls_2x_causal_close"
    LIVE_HUB = REPO / "live" / "state" / "yearly_orb_hp_live_plan_causal_close"
    CHARTS_HUB = REPO / "live" / "state" / "yearly_orb_hp_charts_causal_close"
    CAUSAL_CLOSE = True
    CHART_SUBJECT = "yearly ORB causal-close"


def causal_futures_books() -> List[Book]:
    """NQ L_4_1_1 / ES L_4_2_1 / YM L_4_1_1 on the causal-close sizing hub."""
    books: List[Book] = []
    for key, symbol, slug in CAUSAL_PINNED_SLUGS:
        fills = CAUSAL_SIZING_HUB / "states" / ("%s_yorb_sizing_%s" % (symbol.lower(), slug)) / "fills.csv"
        if not fills.exists():
            raise FileNotFoundError(fills)
        books.append(
            Book(
                key=key,
                label="%s Yearly ORB %s causal close" % (symbol, slug),
                symbol=symbol,
                fills=fills,
                family="yearly_orb",
            )
        )
    return books


def futures_yorb_books() -> List[Book]:
    books = [b for b in _default_books() if b.key in FUTURES_YORB]
    for extra in (
        REPO / "live" / "state" / "yearly_orb_sizing_sweep",
        REPO / "live" / "state" / "yearly_orb_sizing_sweep_micro",
    ):
        books = refresh_yorb_from_sizing(books, extra)
    return books


def all_profile_books() -> List[Book]:
    """Keep the existing FX/metals/ATR profile and add YM yearly ORB."""
    books = _default_books()
    for extra in (
        REPO / "live" / "state" / "yearly_orb_sizing_sweep_fx_metals",
        REPO / "live" / "state" / "yearly_orb_sizing_sweep",
        REPO / "live" / "state" / "yearly_orb_sizing_sweep_micro",
    ):
        books = refresh_yorb_from_sizing(books, extra)
    return books


def _patch_yearly_nulls(hub: Path) -> None:
    overlay.PROFILE_HUB = PROFILE_HUB
    overlay.COND_COL.clear()
    overlay.COND_COL.update({col: col for col, _title in CONDITION_COLS})
    overlay.COND_COL.update({title: col for col, title in CONDITION_COLS})
    overlay.CAUSAL_LIVE_READY.clear()
    ready = {col for col, _t in CONDITION_COLS if col != "hold_bucket"}
    ready |= {title for col, title in CONDITION_COLS if col != "hold_bucket"}
    overlay.CAUSAL_LIVE_READY.update(ready)
    overlay.NEEDS_LIVE_PROXY.clear()
    fxnulls.HUB = hub
    fxnulls.PROFILE_HUB = PROFILE_HUB
    fxnulls.OVERLAY_HUB = PROFILE_HUB


def _alias_decisions(results: List[dict]) -> None:
    for r in results:
        r["decision"] = DECISION_ALIAS.get(r["decision"], r["decision"])


def select_hp_pairs(notables: pd.DataFrame, campaigns: pd.DataFrame) -> List[Tuple[str, str, str]]:
    pairs: List[Tuple[str, str, str]] = []
    n_by_book = campaigns.groupby("book").size().to_dict()
    for book in FUTURES_YORB:
        g = notables[notables["book"] == book].copy()
        if g.empty:
            continue
        n_book = int(n_by_book.get(book, 0)) or 1
        scored = []
        for _, r in g.iterrows():
            cond = str(r["condition"])
            if cond == "hold_bucket":
                continue
            n = int(r["n"])
            cov = n / float(n_book)
            if cov < HP_COVERAGE_MIN or cov >= HP_COVERAGE_MAX:
                continue
            if float(r.get("wr_lift_pp") or 0) <= 0 or float(r.get("avg_lift") or 0) <= 0:
                continue
            scored.append(
                (
                    float(r.get("z_wr") or 0.0),
                    float(r.get("ns") or 0.0),
                    n,
                    cond,
                    str(r["bucket"]),
                )
            )
        scored.sort(reverse=True)
        seen = set()
        for _z, _ns, _n, cond, bucket in scored:
            key = (cond, bucket)
            if key in seen:
                continue
            seen.add(key)
            pairs.append((book, cond, bucket))
            if len(seen) >= MAX_PAIRS_PER_BOOK:
                break
    return pairs


def wilson_ci(wins: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    if n <= 0:
        return (float("nan"), float("nan"))
    p = wins / n
    den = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / den
    half = z * math.sqrt((p * (1.0 - p) + z * z / (4.0 * n)) / n) / den
    return (max(0.0, centre - half), min(1.0, centre + half))


def recount_winrate(campaigns: pd.DataFrame) -> Tuple[pd.DataFrame, List[dict]]:
    rows = []
    for book in FUTURES_YORB:
        df = campaigns[campaigns["book"] == book]
        if df.empty:
            continue
        n = int(len(df))
        wins = int((df["net_usd"] > 0).sum())
        wr = wins / n if n else 0.0
        lo, hi = wilson_ci(wins, n)
        yearly = (
            df.groupby(df["entry_ts"].dt.year)
            .agg(n=("net_usd", "count"), wins=("net_usd", lambda s: int((s > 0).sum())))
            .reset_index()
            .rename(columns={"entry_ts": "year"})
        )
        yearly["wr"] = yearly["wins"] / yearly["n"]
        rows.append(
            {
                "book": book,
                "n": n,
                "wins": wins,
                "losses": n - wins,
                "wr": wr,
                "wr_lo": lo,
                "wr_hi": hi,
                "net": float(df["net_usd"].sum()),
                "avg_net": float(df["net_usd"].mean()),
                "yearly": yearly.to_dict("records"),
            }
        )
    flat_rows = []
    for r in rows:
        flat = {k: v for k, v in r.items() if k != "yearly"}
        flat["yearly_json"] = json.dumps(r["yearly"])
        flat_rows.append(flat)
    return pd.DataFrame(flat_rows), rows


def run_nulls(
    *,
    pairs: List[Tuple[str, str, str]],
    extra: float,
    hub: Path,
    email: bool,
    note: str,
    n_placebo: int,
    n_shift: int,
    n_master: int,
    n_wf_placebo: int,
) -> List[dict]:
    _patch_yearly_nulls(hub)
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")
    campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
    notables = pd.read_csv(PROFILE_HUB / "notables.csv")
    singles = pd.DataFrame()
    crosses = pd.DataFrame()
    results: List[dict] = []
    for book, cond, bucket in pairs:
        res = evaluate_pair(
            campaigns,
            notables,
            singles,
            crosses,
            book=book,
            condition=cond,
            bucket=bucket,
            extra=extra,
            n_placebo=n_placebo,
            n_shift=n_shift,
            n_master=n_master,
            n_wf_placebo=n_wf_placebo,
            seed=SEED,
        )
        results.append(res)
    _alias_decisions(results)
    write_hub_reports(
        results,
        pd.DataFrame(),
        email=email,
        note=note,
        n_placebo=n_placebo,
        n_shift=n_shift,
        n_master=n_master,
        extra=extra,
        seed=SEED,
    )
    return results


def write_live_plan(
    results_125: List[dict],
    results_2x: List[dict],
    wr_rows: List[dict],
    pairs: List[Tuple[str, str, str]],
) -> None:
    LIVE_HUB.mkdir(parents=True, exist_ok=True)

    def _tier(results: List[dict], label: str) -> Tuple[List[dict], List[dict], List[dict]]:
        validated = [r for r in results if r["decision"] == "SIZE-UP VALIDATED"]
        provisional = [r for r in results if r["decision"] == "PROVISIONAL PAPER"]
        shadow = [r for r in results if r["decision"] == "RISK THROTTLE"]
        del label
        return validated, provisional, shadow

    a125, b125, c125 = _tier(results_125, "1.25")
    a2, b2, c2 = _tier(results_2x, "2x")

    nq_wr = next((r for r in wr_rows if r["book"] == "nq_yorb"), None)

    def _tbl(rows: List[dict], mult: str) -> List[str]:
        if not rows:
            return ["_None._", ""]
        out = [
            "| book | condition=bucket | mult | hp% | ΔN/S | p_plac | p_shift | p_master |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        for r in rows:
            out.append(
                "| %s | %s=%s | %s | %.0f%% | %+.2f | %.3f | %.3f | %.3f |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    mult,
                    100.0 * float(r["boost_frac"]),
                    float(r.get("sleeve_delta_ns") or 0),
                    float(r.get("p_placebo_delta_ns") or 1),
                    float(r.get("p_shift_delta_ns") or 1),
                    float(r.get("p_master_delta_ns") or 1),
                )
            )
        out.append("")
        return out

    tape_note = (
        "Causal next-open range-close (`live_after_ts=decision_bar.ts`). "
        "Same NQ `L_4_1_1` / ES `L_4_2_1` / YM `L_4_1_1` cells as the pre-causal HP study — "
        "not the causal-best OCO cells."
        if CAUSAL_CLOSE
        else "Books from pre-causal sizing hubs (same-bar-open range-close still in the tape)."
    )
    lines = [
        "# Yearly ORB HP live plan (`%s`)" % STUDY,
        "",
        "Hub: `%s/`" % LIVE_HUB.relative_to(REPO),
        "Profile: `%s/`" % PROFILE_HUB.relative_to(REPO),
        "Nulls 1.25×: `%s/`" % NULLS_HUB.relative_to(REPO),
        "Nulls 2×: `%s/`" % NULLS_HUB_2X.relative_to(REPO),
        "",
        "**Books:** NQ L_4_1_1, ES L_4_2_1, YM L_4_1_1.",
        tape_note,
        "Canonical objective: whole-book **ΔN/S**. Δnet is report-only.",
        "Do **not** infer 2× from a 1.25× pass.",
        "",
        "## NQ win-rate audit",
        "",
    ]
    if nq_wr:
        lines.extend(
            [
                "Recounted from broker-like campaign tape (`nq_yorb` fills, net>0):",
                "",
                "- **%d / %d = %.1f%%** (Wilson 95%% CI **%.1f–%.1f%%**)"
                % (
                    nq_wr["wins"],
                    nq_wr["n"],
                    100.0 * nq_wr["wr"],
                    100.0 * nq_wr["wr_lo"],
                    100.0 * nq_wr["wr_hi"],
                ),
                "- Net $%s  avg $%s"
                % ("{:,.0f}".format(nq_wr["net"]), "{:,.0f}".format(nq_wr["avg_net"])),
                "",
                "This is the **baseline book** win rate, not an HP size-up claim.",
                "Size-up still needs the matched-added-exposure gates below.",
                "",
                "Year-by-year WR:",
                "",
                "| year | n | wins | WR |",
                "|---:|---:|---:|---:|",
            ]
        )
        for y in nq_wr["yearly"]:
            lines.append(
                "| %s | %d | %d | %.1f%% |"
                % (y["year"], int(y["n"]), int(y["wins"]), 100.0 * float(y["wr"]))
            )
        lines.append("")
    else:
        lines.append("_NQ tape missing — WR audit failed._")
        lines.append("")

    lines.extend(
        [
            "## Baseline WR (all three)",
            "",
            "| book | n | wins | WR | Wilson 95% | net |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for r in wr_rows:
        lines.append(
            "| %s | %d | %d | %.1f%% | %.1f–%.1f%% | $%s |"
            % (
                r["book"],
                r["n"],
                r["wins"],
                100.0 * r["wr"],
                100.0 * r["wr_lo"],
                100.0 * r["wr_hi"],
                "{:,.0f}".format(r["net"]),
            )
        )
    lines.extend(
        [
            "",
            "## HP pairs tested",
            "",
        ]
    )
    for book, cond, bucket in pairs:
        lines.append("- `%s` %s=%s" % (book, cond, bucket))
    lines.extend(["", "## Tier A — paper 1.25× (SIZE-UP VALIDATED)", ""])
    lines.extend(_tbl(a125, "1.25×"))
    lines.extend(["## Tier B — provisional paper 1.25×", ""])
    lines.extend(_tbl(b125, "1.25×"))
    lines.extend(["## Exact 2× (separate hub)", ""])
    lines.extend(_tbl(a2 + b2, "2.00×"))
    lines.extend(
        [
            "## Tier C / not validated",
            "",
            "All remaining pairs (including coverage-fail and master-fail) stay **no size change**.",
            "",
            "## Stance",
            "",
            "- Highest-conviction yearly ORB HP size-up is whatever survives ΔN/S gates above.",
            "- Book WR is a **tape recount**, not a promotion of 1.25×/2×.",
            "- At most one HP multiplier per index sleeve per session.",
            (
                "- Causal-close tape: do not compare these WRs to the pre-causal 86%/76%/90% recount."
                if CAUSAL_CLOSE
                else "- Pre-causal tape still includes same-bar-open range-close scratches."
            ),
            "",
        ]
    )
    (LIVE_HUB / "LIVE_PLAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (LIVE_HUB / "DEPLOYMENT_PLAN.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = [
        "potions: yearly ORB HP size-up LIVE_PLAN complete",
        "",
        "Study: %s" % STUDY,
        "Hub: %s" % LIVE_HUB,
        "",
    ]
    if nq_wr:
        email.append(
            "NQ WR recount: %d/%d = %.1f%% (95%% CI %.1f–%.1f%%)."
            % (
                nq_wr["wins"],
                nq_wr["n"],
                100.0 * nq_wr["wr"],
                100.0 * nq_wr["wr_lo"],
                100.0 * nq_wr["wr_hi"],
            )
        )
        email.append(
            "86%% claim: %s (CI %s 86%%)."
            % (
                "HOLDS" if nq_wr["wr"] >= 0.86 else "DOES NOT HOLD",
                "covers" if nq_wr["wr_lo"] <= 0.86 <= nq_wr["wr_hi"] else "does not cover",
            )
        )
    email.append("")
    email.append("1.25× decisions:")
    for r in results_125:
        email.append(
            "  %s  %s %s=%s  ΔN/S=%+.2f  p_master=%.3f"
            % (
                r["decision"],
                r["book"],
                r["condition"],
                r["bucket"],
                float(r.get("sleeve_delta_ns") or 0),
                float(r.get("p_master_delta_ns") or 1),
            )
        )
    email.append("2× decisions:")
    for r in results_2x:
        email.append(
            "  %s  %s %s=%s  ΔN/S=%+.2f  p_master=%.3f"
            % (
                r["decision"],
                r["book"],
                r["condition"],
                r["bucket"],
                float(r.get("sleeve_delta_ns") or 0),
                float(r.get("p_master_delta_ns") or 1),
            )
        )
    a_n = len(a125)
    b_n = len(b125)
    if a_n:
        email.append("Stance: %d SIZE-UP VALIDATED @1.25× — paper only at that multiplier." % a_n)
    elif b_n:
        email.append("Stance: no Tier A; %d PROVISIONAL @1.25× — controlled paper only." % b_n)
    else:
        email.append("Stance: no yearly-ORB HP size-up validated — baseline 1.0× only.")
    (LIVE_HUB / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    (LIVE_HUB / "hp_size_rules.json").write_text(
        json.dumps(
            {
                "study": STUDY,
                "pairs": [{"book": b, "condition": c, "bucket": k} for b, c, k in pairs],
                "tier_a_1_25": [
                    {"book": r["book"], "condition": r["condition"], "bucket": r["bucket"]}
                    for r in a125
                ],
                "tier_b_1_25": [
                    {"book": r["book"], "condition": r["condition"], "bucket": r["bucket"]}
                    for r in b125
                ],
                "provisional_2x": [
                    {"book": r["book"], "condition": r["condition"], "bucket": r["bucket"]}
                    for r in a2 + b2
                ],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _state_root_for_book(book: Book) -> Path:
    return book.fills.parent


def chart_best_outcomes(book: Book, *, n_best: int = 80) -> Path:
    """Chart largest-net winning campaigns (daily ORB window). Returns chart dir."""
    from live.instrument_winloss_charts import (
        _add_yorb_levels,
        _daily_trade_dates,
        _draw_daily_trade,
        _load_daily_candles,
        _load_daily_fill_groups,
        _window_for_yorb_daily,
    )
    from live.nq_v2b_prior_opposed_15m_charts import _plot_candles
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.dates as mdates
    import matplotlib.pyplot as plt

    from live.instrument_deep_check import load_campaigns, _resolve_paths

    state_root = _state_root_for_book(book)
    out = CHARTS_HUB / book.key
    if out.exists():
        import shutil

        shutil.rmtree(out)
    charts_dir = out / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    paths = _resolve_paths(state_root, out, book.label)
    campaigns = load_campaigns(paths).sort_values("net_usd", ascending=False).reset_index(drop=True)
    wins = campaigns[campaigns["net_usd"] > 0].head(n_best).copy()
    daily_candles = _load_daily_candles(paths)
    if daily_candles.empty:
        raise FileNotFoundError("No daily candles for %s" % book.key)
    if getattr(daily_candles.index, "tz", None) is not None:
        daily_candles.index = daily_candles.index.tz_localize(None)
    fill_groups = _load_daily_fill_groups(paths.fills) if paths.fills is not None else {}
    index_rows = []
    for i, row in enumerate(wins.itertuples(index=False), start=1):
        fills_df = fill_groups.get(str(row.trade_id))
        entry_plot_ts, exit_plot_ts = _daily_trade_dates(row, fills_df)
        start, end = _window_for_yorb_daily(entry_plot_ts, exit_plot_ts)
        candles = daily_candles[(daily_candles.index >= start) & (daily_candles.index <= end)]
        if candles.empty:
            continue
        session = entry_plot_ts.date()
        fname = "%03d_%s_%s_win.png" % (i, session.isoformat(), row.side)
        fig, ax = plt.subplots(figsize=(16, 7))
        _plot_candles(ax, candles, width_days=0.65)
        _add_yorb_levels(ax, candles, entry_plot_ts)
        _draw_daily_trade(ax, row, fills_df, entry_plot_ts, exit_plot_ts)
        ax.set_title(
            "%s | %s | %s %s | WIN | net %+.0f"
            % (book.symbol, book.label, session.isoformat(), row.side, float(row.net_usd))
        )
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        ax.grid(True, alpha=0.25)
        fig.autofmt_xdate()
        fig.savefig(charts_dir / fname, dpi=110, bbox_inches="tight")
        plt.close(fig)
        index_rows.append(
            {
                "seq": i,
                "session": session.isoformat(),
                "side": row.side,
                "net_usd": float(row.net_usd),
                "chart": str(charts_dir / fname),
            }
        )
        if i % 15 == 0:
            print("  %s charted %d/%d" % (book.key, i, len(wins)), flush=True)
    pd.DataFrame(index_rows).to_csv(out / "INDEX.csv", index=False)
    lines = [
        "# %s — best-outcome wins (top %d by net)" % (book.label, n_best),
        "",
        "| # | session | side | net | chart |",
        "|---:|---|---|---:|---|",
    ]
    for r in index_rows:
        lines.append(
            "| %d | %s | %s | %+.0f | %s |"
            % (r["seq"], r["session"], r["side"], r["net_usd"], Path(r["chart"]).name)
        )
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def _pack_png_batches(paths: List[Path]) -> List[List[Path]]:
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in paths:
        if not p.exists() or not p.is_file():
            continue
        sz = p.stat().st_size
        if sz > 8 * 1024 * 1024:
            continue
        overflow = cur and (
            len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES
        )
        if overflow:
            batches.append(cur)
            cur = []
            cur_bytes = 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    return batches


def email_chart_batches(
    book: Book,
    chart_dir: Path,
    wr_row: Optional[dict],
    *,
    email: bool,
) -> int:
    pngs = sorted(chart_dir.joinpath("charts").glob("*.png"))
    batches = _pack_png_batches(pngs)
    idx = pd.read_csv(chart_dir / "INDEX.csv") if (chart_dir / "INDEX.csv").exists() else pd.DataFrame()
    n_sent = 0
    wr_line = ""
    if wr_row:
        wr_line = "Tape WR %d/%d = %.1f%% (Wilson 95%% %.1f–%.1f%%)." % (
            wr_row["wins"],
            wr_row["n"],
            100.0 * wr_row["wr"],
            100.0 * wr_row["wr_lo"],
            100.0 * wr_row["wr_hi"],
        )
    if not batches:
        body = "\n".join(
            [
                "potions: %s best-outcome charts %s" % (CHART_SUBJECT, book.symbol),
                "",
                wr_line,
                "No PNG charts produced. Hub: %s" % chart_dir,
            ]
        )
        (chart_dir / "EMAIL.txt").write_text(body + "\n", encoding="utf-8")
        if email:
            send_email(subject="potions: %s charts %s (none)" % (CHART_SUBJECT, book.symbol), body=body)
        return 0
    for bi, batch in enumerate(batches, start=1):
        names = [p.name for p in batch]
        body = "\n".join(
            [
                "potions: %s best-outcome charts %s (%d/%d)"
                % (CHART_SUBJECT, book.symbol, bi, len(batches)),
                "",
                book.label,
                wr_line,
                "PNGs (not zipped): %d of %d total charts." % (len(batch), len(pngs)),
                "Hub: %s" % chart_dir,
                "",
                "Largest-net wins first. Scale-out markers + Jan–Mar OR / ±1R / ±2R.",
                "",
                "Attached: " + ", ".join(names[:8]) + (" …" if len(names) > 8 else ""),
            ]
        )
        rows_html = ""
        if not idx.empty:
            sub = idx.head(25)
            rows_html = "\n".join(
                "<tr><td>%s</td><td>%s</td><td>%+.0f</td></tr>"
                % (html.escape(str(r.session)), html.escape(str(r.side)), float(r.net_usd))
                for r in sub.itertuples(index=False)
            )
        html_body = """<!DOCTYPE html><html><body style="font-family:Georgia,serif">
<h2>%s best-outcome yearly ORB charts</h2>
<p>%s</p>
<p>Email %d/%d — %d PNG attachments (not zipped).</p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px">
<tr><th>session</th><th>side</th><th>net</th></tr>
%s
</table></body></html>""" % (
            html.escape(book.symbol),
            html.escape(wr_line),
            bi,
            len(batches),
            len(batch),
            rows_html,
        )
        (chart_dir / ("EMAIL_%d.txt" % bi)).write_text(body + "\n", encoding="utf-8")
        if email:
            send_email(
                subject="potions: %s best charts %s (%d/%d)"
                % (CHART_SUBJECT, book.symbol, bi, len(batches)),
                body=body,
                html=html_body,
                attachments=batch,
            )
            n_sent += 1
            _progress("emailed %s charts batch %d (%d pngs)" % (book.symbol, bi, len(batch)))
    return n_sent


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--profile-only", action="store_true")
    p.add_argument("--nulls-only", action="store_true")
    p.add_argument("--charts-only", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument(
        "--causal-close",
        action="store_true",
        help="Use next-open range-close fills throughout (dedicated hubs).",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.causal_close:
        configure_causal_close()

    LIVE_HUB.mkdir(parents=True, exist_ok=True)
    n_placebo, n_shift, n_master, n_wf = (5000, 1000, 500, 200)
    if args.smoke:
        n_placebo, n_shift, n_master, n_wf = (200, 80, 80, 30)

    if CAUSAL_CLOSE:
        books = causal_futures_books()
        profile_books = books
    else:
        books = futures_yorb_books()
        profile_books = all_profile_books()
    if args.email and not args.charts_only:
        send_email(
            subject="potions: %s STARTED" % STUDY,
            body=(
                "Study: %s\n"
                "Books: NQ L_4_1_1 / ES L_4_2_1 / YM L_4_1_1\n"
                "Tape: %s\n"
                "Sequence: yearly condition profile → HP shortlist → "
                "1.25× nulls → 2× nulls → LIVE_PLAN → best-outcome PNG charts "
                "(separate emails per instrument, not zipped).\n"
                "NQ WR will be recounted from fills.\n"
                "Smoke=%s\n"
                "Hubs:\n  %s\n  %s\n  %s\n  %s\n  %s\n"
            )
            % (
                STUDY,
                (
                    "causal next-open range-close (broker-like PaperBroker)"
                    if CAUSAL_CLOSE
                    else "pre-causal sizing hubs"
                ),
                args.smoke,
                PROFILE_HUB,
                NULLS_HUB,
                NULLS_HUB_2X,
                LIVE_HUB,
                CHARTS_HUB,
            ),
        )

    try:
        if not args.nulls_only and not args.charts_only:
            _progress("PROFILE NQ/ES/YM yearly ORB …")
            rc = profile_run(books=profile_books, hub=PROFILE_HUB, min_n=12, email=False)
            if rc != 0:
                return rc

        campaigns = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
        campaigns["entry_ts"] = pd.to_datetime(campaigns["entry_ts"], utc=True)
        notables = pd.read_csv(PROFILE_HUB / "notables.csv") if (PROFILE_HUB / "notables.csv").exists() else pd.DataFrame()
        wr_df, wr_rows = recount_winrate(campaigns)
        wr_df.to_csv(LIVE_HUB / "winrate_audit.csv", index=False)
        nq = next((r for r in wr_rows if r["book"] == "nq_yorb"), None)
        if nq:
            _progress(
                "NQ WR recount %d/%d = %.1f%% (CI %.1f–%.1f%%)%s"
                % (
                    nq["wins"],
                    nq["n"],
                    100.0 * nq["wr"],
                    100.0 * nq["wr_lo"],
                    100.0 * nq["wr_hi"],
                    " causal-close"
                    if CAUSAL_CLOSE
                    else " 86%%=%s" % ("HOLD" if nq["wr"] >= 0.86 else "MISS"),
                )
            )

        if args.profile_only:
            if args.email:
                send_email(
                    subject="potions: %s profile complete" % STUDY,
                    body=(PROFILE_HUB / "EMAIL.txt").read_text(encoding="utf-8")
                    if (PROFILE_HUB / "EMAIL.txt").exists()
                    else "profile done",
                )
            return 0

        pairs = select_hp_pairs(notables, campaigns)
        (LIVE_HUB / "pairs.json").write_text(json.dumps(pairs, indent=2) + "\n", encoding="utf-8")
        _progress("HP pairs: %s" % pairs)

        results_125: List[dict] = []
        results_2x: List[dict] = []
        if not args.charts_only:
            if not pairs:
                _progress("no HP pairs under coverage cap — nulls skipped")
            else:
                _progress("NULLS 1.25× …")
                results_125 = run_nulls(
                    pairs=pairs,
                    extra=0.25,
                    hub=NULLS_HUB,
                    email=args.email,
                    note="yearly-orb 1.25x",
                    n_placebo=n_placebo,
                    n_shift=n_shift,
                    n_master=n_master,
                    n_wf_placebo=n_wf,
                )
                _progress("NULLS 2.00× …")
                results_2x = run_nulls(
                    pairs=pairs,
                    extra=1.0,
                    hub=NULLS_HUB_2X,
                    email=args.email,
                    note="yearly-orb 2.00x",
                    n_placebo=n_placebo,
                    n_shift=n_shift,
                    n_master=n_master,
                    n_wf_placebo=n_wf,
                )
            write_live_plan(results_125, results_2x, wr_rows, pairs)
            if args.email:
                send_email(
                    subject="potions: %s LIVE_PLAN complete" % STUDY,
                    body=(LIVE_HUB / "EMAIL.txt").read_text(encoding="utf-8"),
                )

        wr_by_book = {r["book"]: r for r in wr_rows}
        for book in books:
            _progress("CHARTS %s best outcomes …" % book.key)
            chart_dir = chart_best_outcomes(book, n_best=80)
            email_chart_batches(
                book,
                chart_dir,
                wr_by_book.get(book.key),
                email=args.email,
            )

        (LIVE_HUB / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "pairs": pairs, "study": STUDY}, indent=2) + "\n",
            encoding="utf-8",
        )
        _progress("DONE")
        return 0
    except Exception:
        tb = traceback.format_exc()
        (LIVE_HUB / "FAIL.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(subject="potions: %s FAILED" % STUDY, body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
