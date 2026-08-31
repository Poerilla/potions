"""NQ RTH 15m large-candle study: percentile size + 3R follow from close.

Same contract as ``nq_5m_large_candle_study`` on left-label 15-minute bars
resampled from ``nq/nq_5min_rth.csv``.

Default sleeve is causal expanding **p90** (fallback p80). Pass ``--hi 99 --lo 95``
for the tail sleeve (fallback to p95 when p99 days/events are too rare).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_15m_large_candle_study --email
  python -m live.nq_15m_large_candle_study --email --hi 99 --lo 95
  python -m live.nq_15m_large_candle_study --email --smoke
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import time
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .nq_5m_large_candle_study import (
    MIN_EVENTS,
    RARE_DAY_FRAC,
    _plot_session,
    choose_chart_days,
    choose_pct_sleeve,
    classify,
    control_all_candles,
    day_coverage,
    hour_table,
    load_rth_5m,
    pct_name,
    resample_rth,
    summarize_book,
    walk_trades,
    yearly_table,
)

HUB = REPO / "live" / "state" / "nq_15m_large_candle"
ENTRY_CUTOFF = time(15, 30)
MIN_WARMUP = 26 * 60  # ~60 sessions of RTH 15m
MAX_CHARTS_DEFAULT = 220
TF = "15m"


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def write_report(
    *,
    cov: pd.DataFrame,
    hi_tr: pd.DataFrame,
    lo_tr: pd.DataFrame,
    hi_atr_tr: pd.DataFrame,
    ctrl_tr: pd.DataFrame,
    all_dir_tr: pd.DataFrame,
    flag: str,
    hi: str,
    lo: str,
    sleeve_meta: dict,
    chart_n: int,
    chart_days_n: int,
    n_bars: int,
    n_days: int,
) -> None:
    hi_days = int(cov["has_%s" % hi].sum()) if "has_%s" % hi in cov.columns else 0
    lo_days = int(cov["has_%s" % lo].sum()) if "has_%s" % lo in cov.columns else 0
    hi_frac = hi_days / max(n_days, 1)
    hi_bars = int(cov["n_%s" % hi].sum()) if "n_%s" % hi in cov.columns else 0
    lo_bars = int(cov["n_%s" % lo].sum()) if "n_%s" % lo in cov.columns else 0
    sleeve = "is_%s" % hi if flag == "is_%s" % hi else "is_%s" % lo
    sleeve_name = hi if flag == "is_%s" % hi else "%s (%s too rare: %s)" % (lo, hi, sleeve_meta.get("reason", ""))
    books = [
        summarize_book(hi_tr, "%s large 3R" % hi),
        summarize_book(lo_tr, "%s large 3R" % lo),
        summarize_book(hi_atr_tr, "%s ATR-norm range 3R" % hi),
        summarize_book(ctrl_tr, "matched non-large control"),
        summarize_book(all_dir_tr, "ALL directional 15m 3R (baseline)"),
    ]
    lines = [
        "# NQ 15m RTH large-candle study (%s / %s)" % (hi, lo),
        "",
        "Universe: NQ Regular Trading Hours 09:30–16:00, **15-minute** candles resampled from `nq/nq_5min_rth.csv`.",
        "Size = **high−low range**. Percentile = **causal expanding** of prior RTH 15m ranges "
        "(warmup 60 sessions; thresholds from history before the bar).",
        "Primary sleeve **%s**; fallback **%s** if days with ≥1 %s < %.0f%% of sessions or %s bars < %d."
        % (hi, lo, hi, 100 * RARE_DAY_FRAC, hi, MIN_EVENTS),
        "",
        "Trade: follow candle direction from **close**, SL at **open**, TP = **3× body**. "
        "Non-overlapping. Same-bar stop before target. Flatten 16:00. $1.50 fee, $20/pt.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| RTH 15m bars | %s |" % f"{n_bars:,}",
        "| Sessions | %s |" % f"{n_days:,}",
        "| Bars ≥%s | %s (%.1f%%) |" % (hi, f"{hi_bars:,}", 100.0 * hi_bars / max(n_bars, 1)),
        "| Days with ≥1 %s | %d (%.1f%% of days) |" % (hi, hi_days, 100 * hi_frac),
        "| Bars ≥%s | %s |" % (lo, f"{lo_bars:,}"),
        "| Days with ≥1 %s | %d (%.1f%% of days) |" % (lo, lo_days, 100 * lo_days / max(n_days, 1)),
        "| Sleeve pick | **%s** |" % sleeve_name,
        "| Charts written | %d / %d qualifying days (stratified sample: 50W/50L + yearly) |" % (chart_n, chart_days_n),
        "",
        "Fair 3R WR with no edge ≈ **25%**. If large-candle WR sits near that (or below the all-candle book), size is not a directional signal.",
        "",
        "## Books",
        "",
        "| Book | n | WR | avg | net | stress | N/S | PF | avg R | tgt/stop/eod |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "potions: NQ 15m large-candle 3R study complete (%s/%s)" % (hi, lo),
        "",
        "Hub: %s" % HUB.resolve(),
        "Sleeve: %s (%s)" % (sleeve, sleeve_meta.get("reason", "")),
        "Days with %s: %d / %d (%.0f%%)  bars=%d" % (hi, hi_days, n_days, 100 * hi_frac, hi_bars),
        "",
    ]
    for b in books:
        if not b.get("n"):
            lines.append("| %s | 0 | — | — | — | — | — | — | — | — |" % b["label"])
            continue
        lines.append(
            "| %s | %d | %.1f%% | $%.0f | $%.0f | $%.0f | %.2f | %.2f | %.2f | %d/%d/%d |"
            % (
                b["label"],
                b["n"],
                100 * b["wr"],
                b["avg"],
                b["net"],
                b["stress"],
                b["ns"],
                b["pf"],
                b["avg_r"],
                b.get("target_n", 0),
                b.get("stop_n", 0),
                b.get("eod_n", 0),
            )
        )
        email.append(
            "%s  n=%d WR=%.0f%% net=$%.0f N/S=%.2f PF=%.2f"
            % (b["label"], b["n"], 100 * b["wr"], b["net"], b["ns"], b["pf"])
        )
    sleeve_tr = hi_tr if flag == "is_%s" % hi else lo_tr
    sleeve_sc = books[0] if flag == "is_%s" % hi else books[1]
    stance = "no directional edge vs 25% fair 3R"
    if sleeve_sc.get("n", 0) >= 80:
        if sleeve_sc["wr"] >= 0.32 and sleeve_sc["ns"] >= 1.2:
            stance = "curious lift vs fair 3R — still diagnostic; do not promote"
        elif sleeve_sc["wr"] <= 0.22 or sleeve_sc["net"] < 0:
            stance = "large candles look like **exhaustion / mean-revert**, not follow-through"
        else:
            stance = "WR near fair 3R — size does not mean follow-through"
    lines += ["", "**Stance:** %s." % stance, "", "## Yearly (chart sleeve trades)", ""]
    email.append("")
    email.append("Stance: %s" % stance)
    yt = yearly_table(sleeve_tr)
    if not yt.empty:
        lines += ["| Year | n | WR | net | N/S |", "|---:|---:|---:|---:|---:|"]
        for _, r in yt.iterrows():
            lines.append(
                "| %d | %d | %.1f%% | $%.0f | %.2f |"
                % (int(r["year"]), int(r["n"]), 100 * float(r["wr"]), float(r["net"]), float(r["ns"]))
            )
        lines.append("")
    ht = hour_table(sleeve_tr)
    if not ht.empty:
        lines += [
            "## By NY hour (signal bar)",
            "",
            "| Hour | n | WR | avg | net |",
            "|---:|---:|---:|---:|---:|",
        ]
        for _, r in ht.iterrows():
            lines.append(
                "| %d | %d | %.1f%% | $%.0f | $%.0f |"
                % (int(r["hour"]), int(r["n"]), 100 * float(r["wr"]), float(r["avg"]), float(r["net"]))
            )
        lines.append("")
    lines += [
        "## Charts",
        "",
        "Gold highlight = large candle (chart sleeve). Blue/purple markers = 3R entry/exit.",
        "Index: [`charts/INDEX.md`](charts/INDEX.md).",
        "",
        "Hub: `%s`" % HUB.resolve(),
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HUB / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")
    if not yt.empty:
        yt.to_csv(HUB / "yearly.csv", index=False)
    if not ht.empty:
        ht.to_csv(HUB / "by_hour.csv", index=False)


def write_chart_index(days: Sequence[str], trades: pd.DataFrame, cov: pd.DataFrame, *, flag: str) -> None:
    root = HUB / "charts"
    name = flag[3:] if flag.startswith("is_") else flag
    n_col = "n_%s" % name
    lines = [
        "# NQ 15m RTH large-candle charts",
        "",
        "Full session 09:30–16:00. Gold = large candle. Only qualifying days (sampled if over cap).",
        "",
        "| # | Day | n large | 3R n | 3R net | Chart |",
        "|---:|---|---:|---:|---:|---|",
    ]
    cov_i = cov.set_index("session_date")
    for i, day in enumerate(days, 1):
        n_lg = 0
        if day in cov_i.index and n_col in cov_i.columns:
            n_lg = int(cov_i.loc[day, n_col])
        dtr = trades[trades["session_date"] == day] if trades is not None and not trades.empty else pd.DataFrame()
        net = float(dtr["net_usd"].sum()) if not dtr.empty else 0.0
        rel = "%s.png" % day
        lines.append("| %d | %s | %d | %d | $%.0f | [%s](%s) |" % (i, day, n_lg, len(dtr), net, rel, rel))
    (root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(
    *,
    email: bool,
    smoke: bool,
    max_charts: int,
    hi: int = 90,
    lo: int = 80,
    output_root: Optional[Path] = None,
) -> None:
    global HUB
    hi_name = pct_name(hi)
    lo_name = pct_name(lo)
    if output_root is not None:
        HUB = Path(output_root)
    elif hi_name != "p90":
        HUB = REPO / "live" / "state" / ("nq_15m_large_candle_%s" % hi_name)
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    try:
        df5 = load_rth_5m(progress=False)
        _progress("resample 15m from 5m bars=%s" % f"{len(df5):,}")
        df = resample_rth(df5, 15)
        if smoke:
            dates = df["session_date"].drop_duplicates()
            keep = set(dates.tail(400))
            df = df[df["session_date"].isin(keep)].reset_index(drop=True)
            _progress("SMOKE 15m bars=%s" % f"{len(df):,}")
        _progress("  RTH 15m bars=%s days=%s" % (f"{len(df):,}", df["session_date"].nunique()))
        extra = [] if hi_name == "p90" and lo_name == "p80" else [hi / 100.0 if hi > 1 else hi, lo / 100.0 if lo > 1 else lo]
        _progress("classify expanding %s/%s ..." % (hi_name, lo_name))
        df = classify(df, min_warmup=MIN_WARMUP, extra_qs=extra)
        ready_col = "%s_thr" % hi_name
        if ready_col not in df.columns:
            ready_col = "p90_thr"
        ready = df[df[ready_col].notna()].copy()
        n_bars = int(len(ready))
        n_days = int(ready["session_date"].nunique())
        cov = day_coverage(ready)
        cov.to_csv(HUB / "day_coverage.csv", index=False)
        flag, sleeve_meta = choose_pct_sleeve(cov, hi_name, lo_name)
        _progress(
            "%s day frac=%.1f%% bars=%d → chart flag %s (%s)"
            % (hi_name, 100 * sleeve_meta["hi_day_frac"], sleeve_meta["n_hi_bars"], flag, sleeve_meta["reason"])
        )
        ready.to_parquet(HUB / "candles.parquet", index=False)
        ready.head(5000).to_csv(HUB / "candles_head.csv", index=False)

        hi_flag = "is_%s" % hi_name
        lo_flag = "is_%s" % lo_name
        _progress("walk 3R %s ..." % hi_name)
        hi_tr = walk_trades(ready, hi_flag, entry_cutoff=ENTRY_CUTOFF)
        _progress("  %s trades=%d" % (hi_name, len(hi_tr)))
        _progress("walk 3R %s ..." % lo_name)
        lo_tr = walk_trades(ready, lo_flag, entry_cutoff=ENTRY_CUTOFF)
        _progress("  %s trades=%d" % (lo_name, len(lo_tr)))
        sleeve_tr = hi_tr if flag == hi_flag else lo_tr
        if not hi_tr.empty:
            hi_tr.to_csv(HUB / ("trades_%s.csv" % hi_name), index=False)
        if not lo_tr.empty:
            lo_tr.to_csv(HUB / ("trades_%s.csv" % lo_name), index=False)

        atr_flag = "is_%s_atr" % hi_name
        _progress("walk 3R %s-atr-norm ..." % hi_name)
        hi_atr_tr = walk_trades(ready, atr_flag, entry_cutoff=ENTRY_CUTOFF) if atr_flag in ready.columns else pd.DataFrame()
        _progress("  %s-atr trades=%d" % (hi_name, len(hi_atr_tr)))
        if not hi_atr_tr.empty:
            hi_atr_tr.to_csv(HUB / ("trades_%s_atr.csv" % hi_name), index=False)
        ctrl_tr = control_all_candles(
            ready, n_match=int(len(hi_tr)), entry_cutoff=ENTRY_CUTOFF, flag_col=hi_flag
        )
        if not ctrl_tr.empty:
            ctrl_tr.to_csv(HUB / "trades_control.csv", index=False)

        _progress("all-directional 3R baseline (non-overlap) ...")
        ready["is_any_dir"] = (ready["dir"] != "doji") & ready[ready_col].notna()
        all_dir_tr = walk_trades(ready, "is_any_dir", entry_cutoff=ENTRY_CUTOFF)
        if not all_dir_tr.empty:
            all_dir_tr.to_csv(HUB / "trades_all_directional.csv", index=False)
        _progress("  all-dir trades=%d" % len(all_dir_tr))

        has_col = "has_%s" % (hi_name if flag == hi_flag else lo_name)
        chart_pool = int(cov[has_col].sum()) if has_col in cov.columns else 0
        days = choose_chart_days(cov, sleeve_tr, flag=flag, max_charts=max_charts)
        _progress("charts %d days ..." % len(days))
        by_day = {d: g.reset_index(drop=True) for d, g in ready.groupby("session_date", sort=False)}
        charts_dir = HUB / "charts"
        if charts_dir.exists():
            shutil.rmtree(charts_dir)
        charts_dir.mkdir(parents=True, exist_ok=True)
        manifest = []
        for i, day in enumerate(days, 1):
            sess = by_day.get(day)
            if sess is None or sess.empty:
                continue
            path = charts_dir / ("%s.png" % day)
            _plot_session(
                sess,
                sleeve_tr,
                path,
                flag=flag,
                p80_also=flag == hi_flag,
                tf_label=TF,
                lo_flag=lo_flag,
            )
            manifest.append({"i": i, "session_date": day, "path": str(path)})
            if i % 25 == 0:
                _progress("  charted %d/%d" % (i, len(days)))
        pd.DataFrame(manifest).to_csv(HUB / "chart_manifest.csv", index=False)
        write_chart_index(days, sleeve_tr, cov, flag=flag)
        write_report(
            cov=cov,
            hi_tr=hi_tr,
            lo_tr=lo_tr,
            hi_atr_tr=hi_atr_tr,
            ctrl_tr=ctrl_tr,
            all_dir_tr=all_dir_tr,
            flag=flag,
            hi=hi_name,
            lo=lo_name,
            sleeve_meta=sleeve_meta,
            chart_n=len(manifest),
            chart_days_n=chart_pool,
            n_bars=n_bars,
            n_days=n_days,
        )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "flag": flag,
                    "hi": hi_name,
                    "lo": lo_name,
                    "sleeve": sleeve_meta,
                    "charts": len(manifest),
                    "smoke": smoke,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _progress("DONE")
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NQ 15m large-candle study FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ 15m large-candle study FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: NQ 15m large-candle 3R study complete (%s/%s)" % (hi_name, lo_name),
            body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress("email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-charts", type=int, default=MAX_CHARTS_DEFAULT)
    ap.add_argument("--hi", type=int, default=90, help="Primary percentile (90 or 99)")
    ap.add_argument("--lo", type=int, default=80, help="Fallback percentile if hi is too rare")
    ap.add_argument("--output-root", type=Path, default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        max_charts=int(args.max_charts),
        hi=int(args.hi),
        lo=int(args.lo),
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
