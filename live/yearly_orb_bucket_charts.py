"""Email yearly ORB condition-bucket daily charts as PNG attachments (not zip).

Default: NQ L_4_1_1 mixed-MA stack, wide OR, ATR q4 — every campaign in the
bucket, wins and losses. Split across emails when the PNG budget requires it.

``--causal-close`` charts the same buckets from the next-open range-close tape.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.yearly_orb_bucket_charts --email
  python -m live.yearly_orb_bucket_charts --causal-close --email
"""

from __future__ import annotations

import argparse
import html
import json
import shutil
import traceback
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import pandas as pd

from live.notify_email import send_email
from live.yearly_daily_condition_profile import Book
from live.yearly_orb_hp_sizeup import (
    CHARTS_HUB,
    PROFILE_HUB,
    _pack_png_batches,
    _progress,
    causal_futures_books,
    configure_causal_close,
    futures_yorb_books,
)
import live.yearly_orb_hp_sizeup as yorb_hp

STUDY = "yearly_orb_nq_bucket_charts"
HUB = CHARTS_HUB / "nq_buckets"
NQ_CAMPAIGNS = PROFILE_HUB / "nq_yorb_campaigns.csv"
SUBJECT_PREFIX = "NQ yearly ORB"

# (slug, column, value, human label) — NQ yearly ORB HP notables.
NQ_BUCKETS: List[Tuple[str, str, str, str]] = [
    ("ma_mixed", "ma_stack", "ma_mixed", "mixed MA stack"),
    ("or_wide", "or_width_bucket", "or_wide", "wide OR"),
    ("atr_q4", "atr_pct_bucket", "atr_pctl_q4", "ATR q4"),
]


def _nq_book() -> Book:
    src = causal_futures_books if yorb_hp.CAUSAL_CLOSE else futures_yorb_books
    books = [b for b in src() if b.key == "nq_yorb"]
    if not books:
        raise FileNotFoundError("nq_yorb book missing from yearly ORB sizing hubs")
    return books[0]


def _configure_hubs() -> None:
    global STUDY, HUB, NQ_CAMPAIGNS, SUBJECT_PREFIX
    STUDY = "yearly_orb_nq_bucket_charts_causal_close" if yorb_hp.CAUSAL_CLOSE else "yearly_orb_nq_bucket_charts"
    HUB = yorb_hp.CHARTS_HUB / "nq_buckets"
    NQ_CAMPAIGNS = yorb_hp.PROFILE_HUB / "nq_yorb_campaigns.csv"
    SUBJECT_PREFIX = "NQ yearly ORB causal-close" if yorb_hp.CAUSAL_CLOSE else "NQ yearly ORB"


def _chart_bucket(
    book: Book,
    rows: pd.DataFrame,
    *,
    slug: str,
    label: str,
) -> Path:
    """Daily ORB window charts for every campaign in ``rows`` (wins + losses)."""
    from live.instrument_deep_check import _resolve_paths
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

    out = HUB / slug
    if out.exists():
        shutil.rmtree(out)
    charts_dir = out / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)
    paths = _resolve_paths(book.fills.parent, out, book.label)
    daily_candles = _load_daily_candles(paths)
    if daily_candles.empty:
        raise FileNotFoundError("No daily candles for %s" % book.key)
    if getattr(daily_candles.index, "tz", None) is not None:
        daily_candles.index = daily_candles.index.tz_localize(None)
    fill_groups = _load_daily_fill_groups(paths.fills) if paths.fills is not None else {}

    work = rows.copy()
    work["net_usd"] = pd.to_numeric(work["net_usd"], errors="coerce")
    work = work.sort_values("net_usd", ascending=False).reset_index(drop=True)
    index_rows = []
    for i, row in enumerate(work.itertuples(index=False), start=1):
        fills_df = fill_groups.get(str(row.trade_id))
        entry_plot_ts, exit_plot_ts = _daily_trade_dates(row, fills_df)
        start, end = _window_for_yorb_daily(entry_plot_ts, exit_plot_ts)
        candles = daily_candles[(daily_candles.index >= start) & (daily_candles.index <= end)]
        if candles.empty:
            continue
        session = entry_plot_ts.date()
        outcome = "win" if float(row.net_usd) > 0 else "loss"
        fname = "%03d_%s_%s_%s.png" % (i, session.isoformat(), row.side, outcome)
        fig, ax = plt.subplots(figsize=(16, 7))
        _plot_candles(ax, candles, width_days=0.65)
        _add_yorb_levels(ax, candles, entry_plot_ts)
        _draw_daily_trade(ax, row, fills_df, entry_plot_ts, exit_plot_ts)
        ax.set_title(
            "%s | %s | %s %s | %s | net %+.0f"
            % (
                book.symbol,
                label,
                session.isoformat(),
                row.side,
                outcome.upper(),
                float(row.net_usd),
            )
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
                "outcome": outcome,
                "net_usd": float(row.net_usd),
                "trade_id": str(row.trade_id),
                "chart": fname,
            }
        )
        if i % 10 == 0:
            print("  %s %s charted %d/%d" % (book.symbol, slug, i, len(work)), flush=True)

    idx = pd.DataFrame(index_rows)
    idx.to_csv(out / "INDEX.csv", index=False)
    n_win = int((idx["outcome"] == "win").sum()) if not idx.empty else 0
    n_loss = int((idx["outcome"] == "loss").sum()) if not idx.empty else 0
    lines = [
        "# NQ yearly ORB — %s" % label,
        "",
        "Every campaign in this bucket (wins + losses). Daily Jan–Mar OR / ±1R / ±2R.",
        "",
        "n=%d  wins=%d  losses=%d  avg net=$%+.0f"
        % (
            len(idx),
            n_win,
            n_loss,
            float(idx["net_usd"].mean()) if not idx.empty else 0.0,
        ),
        "",
        "| # | session | side | out | net | chart |",
        "|---:|---|---|---|---:|---|",
    ]
    for r in index_rows:
        lines.append(
            "| %d | %s | %s | %s | %+.0f | %s |"
            % (r["seq"], r["session"], r["side"], r["outcome"], r["net_usd"], r["chart"])
        )
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def email_bucket_batches(
    book: Book,
    chart_dir: Path,
    *,
    label: str,
    n_bucket: int,
    wr: float,
    avg_lift: float,
    email: bool,
) -> int:
    pngs = sorted(chart_dir.joinpath("charts").glob("*.png"))
    batches = _pack_png_batches(pngs)
    idx = pd.read_csv(chart_dir / "INDEX.csv") if (chart_dir / "INDEX.csv").exists() else pd.DataFrame()
    n_sent = 0
    headline = (
        "NQ L_4_1_1 %s%s: n=%d  WR=%.1f%%  avg lift vs book $%+.0f. "
        "PNGs attached (not zipped)."
        % (
            label,
            " (causal next-open close)" if yorb_hp.CAUSAL_CLOSE else "",
            n_bucket,
            100.0 * wr,
            avg_lift,
        )
    )
    if not batches:
        body = "\n".join(
            [
                "potions: %s %s charts" % (SUBJECT_PREFIX, label),
                "",
                headline,
                "No PNG charts produced. Hub: %s" % chart_dir,
            ]
        )
        (chart_dir / "EMAIL.txt").write_text(body + "\n", encoding="utf-8")
        if email:
            send_email(subject="potions: %s %s charts (none)" % (SUBJECT_PREFIX, label), body=body)
        return 0

    for bi, batch in enumerate(batches, start=1):
        names = [p.name for p in batch]
        batch_names = {p.name for p in batch}
        body = "\n".join(
            [
                "potions: %s %s charts (%d/%d)" % (SUBJECT_PREFIX, label, bi, len(batches)),
                "",
                book.label,
                headline,
                "This email: %d of %d charts." % (len(batch), len(pngs)),
                "Hub: %s" % chart_dir,
                "",
                "Daily window with Jan–Mar OR / ±1R / ±2R + scale-out markers.",
                "Largest-net first. Includes losses when the bucket is not 100%% WR.",
                "",
                "Attached: " + ", ".join(names[:10]) + (" …" if len(names) > 10 else ""),
            ]
        )
        if not idx.empty and "chart" in idx.columns:
            sub = idx[idx["chart"].isin(batch_names)]
        else:
            sub = idx.head(25)
        rows_html = "\n".join(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%+.0f</td></tr>"
            % (
                html.escape(str(r.session)),
                html.escape(str(r.side)),
                html.escape(str(r.outcome)),
                float(r.net_usd),
            )
            for r in sub.itertuples(index=False)
        )
        html_body = """<!DOCTYPE html><html><body style="font-family:Georgia,serif">
<h2>%s — %s</h2>
<p>%s</p>
<p>Email %d/%d — %d PNG attachments (not zipped). Hub <code>%s</code>.</p>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:12px">
<tr><th>session</th><th>side</th><th>out</th><th>net</th></tr>
%s
</table></body></html>""" % (
            html.escape(SUBJECT_PREFIX),
            html.escape(label),
            html.escape(headline),
            bi,
            len(batches),
            len(batch),
            html.escape(str(chart_dir)),
            rows_html,
        )
        (chart_dir / ("EMAIL_%d.txt" % bi)).write_text(body + "\n", encoding="utf-8")
        if email:
            send_email(
                subject="potions: %s %s charts (%d/%d)"
                % (SUBJECT_PREFIX, label, bi, len(batches)),
                body=body,
                html=html_body,
                attachments=batch,
            )
            n_sent += 1
            _progress(
                "emailed NQ %s batch %d/%d (%d pngs)" % (label, bi, len(batches), len(batch)),
                hub=HUB,
            )
    return n_sent


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument(
        "--causal-close",
        action="store_true",
        help="Chart buckets from the next-open range-close tape.",
    )
    args = p.parse_args(list(argv) if argv is not None else None)

    if args.causal_close:
        configure_causal_close()
    _configure_hubs()

    HUB.mkdir(parents=True, exist_ok=True)
    book = _nq_book()
    if not NQ_CAMPAIGNS.exists():
        raise FileNotFoundError(
            "Need %s — run yearly_orb_hp_sizeup%s first"
            % (NQ_CAMPAIGNS, " --causal-close" if args.causal_close else "")
        )
    camps = pd.read_csv(NQ_CAMPAIGNS)
    baseline_avg = float(pd.to_numeric(camps["net_usd"], errors="coerce").mean())
    start_body = "\n".join(
        [
            "potions: %s STARTED" % STUDY,
            "",
            "Chart every NQ L_4_1_1 campaign in mixed MA stack / wide OR / ATR q4.",
            "Tape: %s."
            % (
                "causal next-open range-close (broker-like PaperBroker)"
                if args.causal_close
                else "pre-causal sizing hub"
            ),
            "PNG attachments, not zip; split emails if needed.",
            "Hub: %s" % HUB,
            "Fills: %s" % book.fills,
            "Campaigns: %s" % NQ_CAMPAIGNS,
        ]
    )
    (HUB / "EMAIL_START.txt").write_text(start_body + "\n", encoding="utf-8")
    if args.email:
        send_email(subject="potions: %s STARTED" % STUDY, body=start_body)

    try:
        summary_rows = []
        n_emails = 0
        for slug, col, value, label in NQ_BUCKETS:
            g = camps[camps[col].astype(str) == value].copy()
            n = int(len(g))
            wins = int(pd.to_numeric(g["win"], errors="coerce").fillna(False).astype(bool).sum())
            wr = (wins / n) if n else 0.0
            avg = float(pd.to_numeric(g["net_usd"], errors="coerce").mean()) if n else 0.0
            lift = avg - baseline_avg
            _progress("CHART NQ %s n=%d WR=%.1f%% lift=$%+.0f" % (label, n, 100.0 * wr, lift), hub=HUB)
            chart_dir = _chart_bucket(book, g, slug=slug, label=label)
            n_emails += email_bucket_batches(
                book,
                chart_dir,
                label=label,
                n_bucket=n,
                wr=wr,
                avg_lift=lift,
                email=args.email,
            )
            summary_rows.append(
                {
                    "slug": slug,
                    "label": label,
                    "n": n,
                    "wins": wins,
                    "wr": wr,
                    "avg_net": avg,
                    "avg_lift": lift,
                    "charts": len(list((chart_dir / "charts").glob("*.png"))),
                    "hub": str(chart_dir),
                }
            )

        summary = pd.DataFrame(summary_rows)
        summary.to_csv(HUB / "SUMMARY.csv", index=False)
        id_sets = {
            slug: set(camps.loc[camps[col].astype(str) == value, "trade_id"].astype(str))
            for slug, col, value, _label in NQ_BUCKETS
        }
        ma, wide, atr = id_sets["ma_mixed"], id_sets["or_wide"], id_sets["atr_q4"]
        union = ma | wide | atr
        union_losses = int((~camps.loc[camps["trade_id"].astype(str).isin(union), "win"].astype(bool)).sum()) if union else 0
        lines = [
            "# NQ yearly ORB condition-bucket charts%s"
            % (" (causal close)" if yorb_hp.CAUSAL_CLOSE else ""),
            "",
            "Every campaign in each notable bucket (not a 50/50 sample). PNGs emailed separately, not zipped.",
            "",
            "| bucket | n | WR | avg $ | avg lift | charts | hub |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
        for r in summary.itertuples(index=False):
            lines.append(
                "| %s | %d | %.1f%% | $%+.0f | $%+.0f | %d | `%s` |"
                % (r.label, r.n, 100.0 * r.wr, r.avg_net, r.avg_lift, r.charts, r.hub)
            )
        lines.extend(
            [
                "",
                "Overlaps: mixed-MA ∩ wide-OR = %d; mixed-MA ∩ ATR-q4 = %d; wide-OR ∩ ATR-q4 = %d; all three = %d."
                % (len(ma & wide), len(ma & atr), len(wide & atr), len(ma & wide & atr)),
                "Unique union = %d campaigns (%d losses). Charts are per-bucket, so overlap trades appear in more than one email."
                % (len(union), union_losses),
            ]
        )
        (HUB / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        done = "\n".join(
            [
                "potions: %s complete" % STUDY,
                "",
                "Hub: %s" % HUB,
                "Emails sent: %d (PNG attachments, not zip)." % n_emails,
                "",
                summary.to_string(index=False),
                "",
                "Diagnostic only — HP size-up on these buckets is NOT VALIDATED.",
            ]
        )
        (HUB / "EMAIL.txt").write_text(done + "\n", encoding="utf-8")
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "study": STUDY, "emails": n_emails, "rows": summary_rows}, indent=2)
            + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(subject="potions: %s complete" % STUDY, body=done)
        return 0
    except Exception:
        tb = traceback.format_exc()
        (HUB / "FAIL.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(subject="potions: %s FAILED" % STUDY, body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
