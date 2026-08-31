"""Reclaim-as-primary MAE/MFE autopsy + annotated charts (email PNGs, no zip).

Treats ``failure_fade_reclaim`` legs as their own book. For each fill:

- MAE / MFE in R vs the 2×-risk stop
- Post-exit path MFE (would the loser have become a large winner if held /
  stopped wider?)
- Leftover runner MFE after early BE / scale exits

Hub: ``live/state/nq_failure_fade_reclaim_primary/``
"""

from __future__ import annotations

import argparse
import html as html_lib
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from .daily_ma50_yearly_charts import plot_candles
from .nq_quarterly_range_retrace_study import build_quarters, load_daily
from .notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
PLAYBOOK = REPO / "live" / "state" / "nq_quarterly_extreme_playbook"
DEFAULT_OUT = REPO / "live" / "state" / "nq_failure_fade_reclaim_primary"
DAILY = REPO / "nq" / "nq_daily.csv"
POINT_VALUE = 20.0
ENTRY_QTY = 10.0


def _fav(side: str, entry: float, hi: float, lo: float) -> float:
    return (hi - entry) if side == "long" else (entry - lo)


def _adv(side: str, entry: float, hi: float, lo: float) -> float:
    """Adverse excursion in pts (positive number)."""
    return (entry - lo) if side == "long" else (hi - entry)


def _path_excursions(
    bars: pd.DataFrame,
    *,
    side: str,
    entry: float,
    start: pd.Timestamp,
    end: Optional[pd.Timestamp] = None,
) -> Tuple[float, float]:
    """Return (mfe_pts, mae_pts) over [start, end] inclusive; mae as positive adverse."""
    if bars.empty:
        return 0.0, 0.0
    mask = bars["date"] >= start
    if end is not None:
        mask &= bars["date"] <= end
    window = bars.loc[mask]
    if window.empty:
        return 0.0, 0.0
    mfe = 0.0
    mae = 0.0
    for _, row in window.iterrows():
        mfe = max(mfe, _fav(side, entry, float(row["high"]), float(row["low"])))
        mae = max(mae, _adv(side, entry, float(row["high"]), float(row["low"])))
    return float(mfe), float(mae)


def _first_touch_date(
    bars: pd.DataFrame,
    *,
    side: str,
    level: float,
    start: pd.Timestamp,
    end: Optional[pd.Timestamp] = None,
) -> Optional[str]:
    mask = bars["date"] >= start
    if end is not None:
        mask &= bars["date"] <= end
    for _, row in bars.loc[mask].iterrows():
        hi, lo = float(row["high"]), float(row["low"])
        hit = (hi >= level) if side == "long" else (lo <= level)
        if hit:
            return str(pd.Timestamp(row["date"]).date())
    return None


def classify_row(row: pd.Series) -> str:
    """Failure-mode / opportunity tag for reclaim-as-primary."""
    exit_r = str(row["exit_reason"])
    net = float(row["net_usd"])
    post_mfe_r = float(row["post_exit_mfe_r"])
    left_r = float(row["leftover_mfe_r"])
    hit_tp2_post = bool(row["post_hit_tp2"])
    hit_tp1_post = bool(row["post_hit_tp1"])

    if net < 0 and (hit_tp2_post or post_mfe_r >= 2.0):
        return "stop_too_tight_big_winner"
    if net < 0 and (hit_tp1_post or post_mfe_r >= 1.0):
        return "stop_too_tight_recover"
    if net < 0:
        return "hard_loss"
    if exit_r in {"be_stop", "stop"} and left_r >= 1.0:
        return "runner_left_on_table"
    if exit_r == "tp2":
        return "full_tp2"
    if exit_r == "quarter_eod":
        return "quarter_hold"
    return "winner_ok"


def autopsy_frame(trades: pd.DataFrame, daily: pd.DataFrame, quarters: Dict) -> pd.DataFrame:
    reclaims = trades[trades["setup"] == "failure_fade_reclaim"].sort_values("entry_date").reset_index(drop=True)
    rows: List[dict] = []
    for i, t in enumerate(reclaims.itertuples(), 1):
        risk = abs(float(t.entry_price) - float(t.stop0))
        entry = float(t.entry_price)
        side = str(t.side)
        entry_dt = pd.Timestamp(t.entry_date)
        exit_dt = pd.Timestamp(t.exit_date) if pd.notna(t.exit_date) and str(t.exit_date) not in ("", "nan") else entry_dt
        nxt = quarters[t.next_label]
        chart_end = max(pd.Timestamp(nxt.end) + pd.Timedelta(days=21), exit_dt + pd.Timedelta(days=45))

        # In-trade excursions from playbook (mae stored signed ≤0).
        mfe_in = float(t.mfe_pts)
        mae_in = abs(float(t.mae_pts))
        # Post-exit: from day after exit through chart_end, measured from original entry.
        post_start = exit_dt + pd.Timedelta(days=1)
        post_mfe, post_mae = _path_excursions(
            daily, side=side, entry=entry, start=post_start, end=chart_end
        )
        # Full hold MFE if never stopped (entry → chart_end).
        hold_mfe, hold_mae = _path_excursions(
            daily, side=side, entry=entry, start=entry_dt, end=chart_end
        )
        # Leftover after actual exit: max(0, hold_mfe - mfe_in) approx, or post path from exit price.
        leftover = max(0.0, hold_mfe - mfe_in)

        post_hit_tp1 = _first_touch_date(
            daily, side=side, level=float(t.tp1), start=post_start, end=chart_end
        )
        post_hit_tp2 = _first_touch_date(
            daily, side=side, level=float(t.tp2), start=post_start, end=chart_end
        )
        # Hypothetical full book to TP2 if held with infinite stop (diagnostic only).
        hypo_tp2_date = _first_touch_date(
            daily, side=side, level=float(t.tp2), start=entry_dt, end=chart_end
        )
        # Wider stop = 3R / 4R: would original stop have been skipped?
        wider3 = risk * 3.0
        wider4 = risk * 4.0
        # Adverse from entry on exit bar path through exit — already stopped at ~1R.
        # Would a 3R stop have survived until TP2?
        survive_3r = hold_mae < wider3 - 1e-9
        survive_4r = hold_mae < wider4 - 1e-9
        reach_tp2_if_3r = bool(survive_3r and hypo_tp2_date)
        reach_tp2_if_4r = bool(survive_4r and hypo_tp2_date)

        rec = {
            "i": i,
            "next_label": t.next_label,
            "side": side,
            "exit_reason": t.exit_reason,
            "parent_exit_reason": t.parent_exit_reason,
            "entry_date": str(t.entry_date),
            "exit_date": str(t.exit_date),
            "entry_price": entry,
            "stop0": float(t.stop0),
            "tp1": float(t.tp1),
            "tp2": float(t.tp2),
            "risk_pts": risk,
            "net_usd": float(t.net_usd),
            "net_pts": float(t.net_pts),
            "mfe_pts": mfe_in,
            "mae_pts": mae_in,
            "mfe_r": mfe_in / risk if risk > 1e-9 else 0.0,
            "mae_r": mae_in / risk if risk > 1e-9 else 0.0,
            "post_exit_mfe_pts": post_mfe,
            "post_exit_mfe_r": post_mfe / risk if risk > 1e-9 else 0.0,
            "hold_mfe_pts": hold_mfe,
            "hold_mfe_r": hold_mfe / risk if risk > 1e-9 else 0.0,
            "hold_mae_pts": hold_mae,
            "hold_mae_r": hold_mae / risk if risk > 1e-9 else 0.0,
            "leftover_mfe_pts": leftover,
            "leftover_mfe_r": leftover / risk if risk > 1e-9 else 0.0,
            "post_hit_tp1": bool(post_hit_tp1),
            "post_hit_tp1_date": post_hit_tp1 or "",
            "post_hit_tp2": bool(post_hit_tp2),
            "post_hit_tp2_date": post_hit_tp2 or "",
            "hypo_tp2_date": hypo_tp2_date or "",
            "survive_3r_to_hold_end": bool(survive_3r),
            "survive_4r_to_hold_end": bool(survive_4r),
            "reach_tp2_if_stop_3r": bool(reach_tp2_if_3r),
            "reach_tp2_if_stop_4r": bool(reach_tp2_if_4r),
            "chart_end": str(chart_end.date()),
            "prior_label": t.prior_label,
            "parent_stop0": float(t.parent_stop0),
            "be_armed_date": str(t.be_armed_date) if pd.notna(t.be_armed_date) else "",
        }
        rec["failure_mode"] = classify_row(pd.Series(rec))
        # Rough hypo net if full 10 lots to TP2 (fees ignored diagnostic).
        if hypo_tp2_date and side == "long":
            pts = float(t.tp2) - entry
        elif hypo_tp2_date:
            pts = entry - float(t.tp2)
        else:
            pts = hold_mfe if float(t.net_usd) < 0 else float(t.net_pts) / ENTRY_QTY
        rec["hypo_full_tp2_usd"] = pts * POINT_VALUE * ENTRY_QTY if hypo_tp2_date else 0.0
        rows.append(rec)
    return pd.DataFrame(rows)


def _draw_levels(ax, prior, nxt) -> None:
    x0 = mdates.date2num(pd.Timestamp(nxt.start).to_pydatetime())
    x1 = mdates.date2num(pd.Timestamp(nxt.end).to_pydatetime())
    ax.hlines(prior.high, x0, x1, colors="#1f77b4", linestyles="--", linewidth=1.3, label="%s H" % prior.label)
    ax.hlines(prior.low, x0, x1, colors="#1f77b4", linestyles="-", linewidth=1.3, label="%s L" % prior.label)


def build_charts(
    autopsy: pd.DataFrame,
    trades: pd.DataFrame,
    daily: pd.DataFrame,
    quarters: Dict,
    out: Path,
) -> List[dict]:
    out.mkdir(parents=True, exist_ok=True)
    fades = trades[trades["setup"] == "failure_fade"]
    chart_rows: List[dict] = []
    for _, row in autopsy.iterrows():
        t = trades[
            (trades["setup"] == "failure_fade_reclaim") & (trades["next_label"] == row["next_label"])
        ].iloc[0]
        prior = quarters[t.prior_label]
        nxt = quarters[t.next_label]
        parent = fades[fades["next_label"] == t.next_label]
        dates = [t.entry_date, t.exit_date]
        if len(parent):
            dates.append(parent.iloc[0].touch_date)
            dates.append(parent.iloc[0].exit_date)
        dates = [pd.Timestamp(d) for d in dates if pd.notna(d) and str(d) not in ("", "nan")]
        start = min(dates) - pd.Timedelta(days=35)
        end = pd.Timestamp(row["chart_end"])
        pad = daily[(daily["date"] >= start) & (daily["date"] <= end)].copy()

        fig, ax = plt.subplots(figsize=(15, 7.4))
        plot_candles(ax, pad)
        _draw_levels(ax, prior, nxt)
        ax.axhline(float(t.parent_stop0), color="#9467bd", linewidth=1.4, label="reclaim lvl %.2f" % float(t.parent_stop0))
        ax.axhline(float(t.entry_price), color="#111111", linewidth=1.0, label="entry %.2f" % float(t.entry_price))
        ax.axhline(float(t.stop0), color="#c43d3d", linewidth=1.0, label="SL 2x %.2f" % float(t.stop0))
        ax.axhline(float(t.tp1), color="#168a5a", linewidth=1.0, linestyle=":", label="TP1 %.2f" % float(t.tp1))
        ax.axhline(float(t.tp2), color="#168a5a", linewidth=1.2, label="TP2 %.2f" % float(t.tp2))
        # MAE / MFE extremes during open trade (approx from entry bar extremes).
        risk = float(row["risk_pts"])
        side = str(t.side)
        entry = float(t.entry_price)
        if side == "long":
            mae_px = entry - float(row["mae_pts"])
            mfe_px = entry + float(row["mfe_pts"])
        else:
            mae_px = entry + float(row["mae_pts"])
            mfe_px = entry - float(row["mfe_pts"])
        ax.axhline(mae_px, color="#d62728", linewidth=0.9, linestyle="-.", alpha=0.85, label="MAE %.1fpt (%.2fR)" % (float(row["mae_pts"]), float(row["mae_r"])))
        ax.axhline(mfe_px, color="#2ca02c", linewidth=0.9, linestyle="-.", alpha=0.85, label="MFE %.1fpt (%.2fR)" % (float(row["mfe_pts"]), float(row["mfe_r"])))

        ax.axvline(pd.Timestamp(t.entry_date), color="#111", linewidth=0.9, linestyle="--", alpha=0.7)
        if pd.notna(t.exit_date) and t.exit_date:
            ax.axvline(pd.Timestamp(t.exit_date), color="#888", linewidth=0.9, linestyle=":")
        if str(row.get("be_armed_date") or "") not in ("", "nan"):
            ax.axvline(pd.Timestamp(row["be_armed_date"]), color="#ff7f0e", linewidth=1.0, alpha=0.85, label="BE arm")
        ax.scatter(
            [pd.Timestamp(t.entry_date)],
            [entry],
            marker="^" if side == "long" else "v",
            s=90,
            color="#6a3d9a",
            zorder=5,
            label="reclaim entry",
        )
        mode = str(row["failure_mode"])
        title = (
            "reclaim PRIMARY #%d/%d  %s  %s  [%s]\n"
            "exit %s  net $%s  |  MAE %.2fR  MFE %.2fR  |  post-exit MFE %.2fR  leftover %.2fR"
            % (
                int(row["i"]),
                len(autopsy),
                row["next_label"],
                side.upper(),
                mode,
                row["exit_reason"],
                "{:,.0f}".format(float(row["net_usd"])),
                float(row["mae_r"]),
                float(row["mfe_r"]),
                float(row["post_exit_mfe_r"]),
                float(row["leftover_mfe_r"]),
            )
        )
        ax.set_title(title)
        ax.set_ylabel("NQ")
        ax.grid(True, color="#e1e1e1", linewidth=0.5)
        ax.legend(loc="best", fontsize=7.5, ncol=2, framealpha=0.9)
        ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        for lab in ax.get_xticklabels():
            lab.set_rotation(55)
            lab.set_fontsize(7)
        fname = "%02d_%s_%s_%s_%s.png" % (
            int(row["i"]),
            row["next_label"],
            side,
            row["exit_reason"],
            mode,
        )
        fig.savefig(out / fname, dpi=130, bbox_inches="tight")
        plt.close(fig)
        chart_rows.append(
            {
                "i": int(row["i"]),
                "file": fname,
                "next_label": row["next_label"],
                "side": side,
                "exit_reason": row["exit_reason"],
                "failure_mode": mode,
                "net_usd": float(row["net_usd"]),
                "mae_r": float(row["mae_r"]),
                "mfe_r": float(row["mfe_r"]),
                "post_exit_mfe_r": float(row["post_exit_mfe_r"]),
                "leftover_mfe_r": float(row["leftover_mfe_r"]),
                "reach_tp2_if_stop_3r": bool(row["reach_tp2_if_stop_3r"]),
                "reach_tp2_if_stop_4r": bool(row["reach_tp2_if_stop_4r"]),
            }
        )
        print(fname, flush=True)
    return chart_rows


def write_reports(out: Path, autopsy: pd.DataFrame, chart_rows: Sequence[dict]) -> Tuple[str, str]:
    out.mkdir(parents=True, exist_ok=True)
    charts_dir = out / "charts"
    autopsy.to_csv(out / "autopsy.csv", index=False)
    pd.DataFrame(chart_rows).to_csv(charts_dir / "index.csv", index=False)

    n = len(autopsy)
    net = float(autopsy["net_usd"].sum())
    losers = autopsy[autopsy["net_usd"] < 0]
    winners = autopsy[autopsy["net_usd"] >= 0]
    big = autopsy[autopsy["failure_mode"] == "stop_too_tight_big_winner"]
    recover = autopsy[autopsy["failure_mode"] == "stop_too_tight_recover"]
    hard = autopsy[autopsy["failure_mode"] == "hard_loss"]
    left = autopsy[autopsy["failure_mode"] == "runner_left_on_table"]
    reach3_n = int(autopsy["reach_tp2_if_stop_3r"].astype(bool).sum())
    reach4_n = int(autopsy["reach_tp2_if_stop_4r"].astype(bool).sum())

    mode_counts = autopsy["failure_mode"].value_counts().to_dict()

    lines = [
        "# NQ failure_fade_reclaim as PRIMARY — MAE / MFE autopsy",
        "",
        "Reclaim legs only (not gated behind fade PnL). Source tape: playbook `trades.csv`.",
        "",
        "- N: **%d**" % n,
        "- Net: **$%s**" % "{:,.2f}".format(net),
        "- Losers: **%d** · Winners: **%d**" % (len(losers), len(winners)),
        "",
        "## Failure modes",
        "",
        "| Mode | N | Meaning |",
        "|---|---:|---|",
        "| stop_too_tight_big_winner | %d | Stopped, then post-exit path still tagged TP2 or ≥2R from entry |"
        % len(big),
        "| stop_too_tight_recover | %d | Stopped, then recovered ≥1R / TP1 |" % len(recover),
        "| hard_loss | %d | Stopped and did not recover |" % len(hard),
        "| runner_left_on_table | %d | Winner (often BE) that left ≥1R of hold-MFE |" % len(left),
        "| full_tp2 / quarter_hold / winner_ok | %d | Captured intended runner |"
        % (n - len(big) - len(recover) - len(hard) - len(left)),
        "",
        "Counts: `%s`" % mode_counts,
        "",
        "## Could losers turn into large winners?",
        "",
        "- Losers that later reached TP2 or ≥2R post-exit: **%d / %d**" % (len(big), len(losers)),
        "- Losers that recovered ≥1R / TP1 post-exit (incl. big): **%d / %d**"
        % (len(big) + len(recover), len(losers)),
        "- Reach TP2 if stop were **3R** (path MAE < 3R and TP2 tagged): **%d / %d**"
        % (reach3_n, n),
        "- Reach TP2 if stop were **4R**: **%d / %d**" % (reach4_n, n),
        "",
        "## Per-trade",
        "",
        "| # | Q | Side | Exit | Net | MAE R | MFE R | Post MFE R | Left R | Mode | 3R→TP2 |",
        "|---:|---|---|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for _, r in autopsy.iterrows():
        lines.append(
            "| %d | %s | %s | %s | $%s | %.2f | %.2f | %.2f | %.2f | %s | %s |"
            % (
                int(r["i"]),
                r["next_label"],
                r["side"],
                r["exit_reason"],
                "{:,.0f}".format(float(r["net_usd"])),
                float(r["mae_r"]),
                float(r["mfe_r"]),
                float(r["post_exit_mfe_r"]),
                float(r["leftover_mfe_r"]),
                r["failure_mode"],
                "Y" if r["reach_tp2_if_stop_3r"] else "",
            )
        )
    lines.extend(
        [
            "",
            "## Charts",
            "",
            "Annotated PNGs in `charts/` (MAE/MFE lines + failure-mode in title).",
            "",
            "| # | Chart | Mode | Net |",
            "|---:|---|---|---:|",
        ]
    )
    for c in chart_rows:
        lines.append(
            "| %d | [%s](charts/%s) | %s | $%s |"
            % (c["i"], c["file"], c["file"], c["failure_mode"], "{:,.0f}".format(c["net_usd"]))
        )
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "MAE_MFE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Plain email body
    email_lines = [
        "NQ reclaim-as-PRIMARY MAE/MFE autopsy (charts attached, no zip).",
        "",
        "Hub: %s" % out,
        "N=%d  net=$%s  losers=%d  winners=%d" % (n, "{:,.0f}".format(net), len(losers), len(winners)),
        "",
        "Failure modes:",
        "  stop_too_tight_big_winner (loser→large winner path): %d" % len(big),
        "  stop_too_tight_recover: %d" % len(recover),
        "  hard_loss: %d" % len(hard),
        "  runner_left_on_table (could run harder): %d" % len(left),
        "",
        "Losers that could have been large winners (post-exit ≥2R or TP2): %d / %d"
        % (len(big), max(len(losers), 1)),
        "Reach TP2 with 3R stop: %d/%d · with 4R stop: %d/%d"
        % (reach3_n, n, reach4_n, n),
        "",
        "Per trade:",
    ]
    for _, r in autopsy.iterrows():
        email_lines.append(
            "  #%d %s %s %s net=$%s MAE=%.2fR MFE=%.2fR post=%.2fR left=%.2fR [%s]%s"
            % (
                int(r["i"]),
                r["next_label"],
                r["side"],
                r["exit_reason"],
                "{:,.0f}".format(float(r["net_usd"])),
                float(r["mae_r"]),
                float(r["mfe_r"]),
                float(r["post_exit_mfe_r"]),
                float(r["leftover_mfe_r"]),
                r["failure_mode"],
                " 3R→TP2" if r["reach_tp2_if_stop_3r"] else "",
            )
        )
    email_lines.extend(["", "SUMMARY: %s" % (out / "SUMMARY.md")])
    text = "\n".join(email_lines) + "\n"
    (out / "EMAIL.txt").write_text(text, encoding="utf-8")

    # HTML with inline notes (attachments carry PNGs)
    rows_html = []
    for c in chart_rows:
        rows_html.append(
            "<tr><td>%d</td><td>%s</td><td>%s</td><td>%s</td><td>$%s</td>"
            "<td>%.2f</td><td>%.2f</td><td>%.2f</td><td>%.2f</td><td><code>%s</code></td></tr>"
            % (
                c["i"],
                html_lib.escape(str(c["next_label"])),
                html_lib.escape(str(c["side"])),
                html_lib.escape(str(c["exit_reason"])),
                "{:,.0f}".format(c["net_usd"]),
                c["mae_r"],
                c["mfe_r"],
                c["post_exit_mfe_r"],
                c["leftover_mfe_r"],
                html_lib.escape(str(c["failure_mode"])),
            )
        )
    html_body = """<!DOCTYPE html><html><body style="font-family:system-ui,sans-serif;line-height:1.4">
<h2>NQ reclaim as PRIMARY — MAE / MFE</h2>
<p>Hub <code>%s</code>. All %d annotated charts attached as PNGs (no zip).</p>
<ul>
<li><b>%d</b> losers that still ran ≥2R / TP2 after the stop (stop too tight → large winner path)</li>
<li><b>%d</b> additional recoveries ≥1R / TP1</li>
<li><b>%d</b> hard losses</li>
<li><b>%d</b> winners that left ≥1R of runner on the table</li>
<li>TP2 reachable with 3R stop: <b>%d/%d</b>; with 4R: <b>%d/%d</b></li>
</ul>
<table border="1" cellpadding="4" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<thead><tr><th>#</th><th>Q</th><th>Side</th><th>Exit</th><th>Net</th><th>MAE R</th><th>MFE R</th><th>Post R</th><th>Left R</th><th>Mode</th></tr></thead>
<tbody>%s</tbody></table>
<p>Net book $%s.</p>
</body></html>""" % (
        html_lib.escape(str(out)),
        n,
        len(big),
        len(recover),
        len(hard),
        len(left),
        reach3_n,
        n,
        reach4_n,
        n,
        "\n".join(rows_html),
        "{:,.0f}".format(net),
    )
    (out / "EMAIL.html").write_text(html_body, encoding="utf-8")
    return text, html_body


def run(*, playbook: Path, output_root: Path, daily_path: Path, email: bool) -> int:
    daily = load_daily(daily_path)
    quarters = {q.label: q for q in build_quarters(daily)}
    trades = pd.read_csv(playbook / "trades.csv")
    autopsy = autopsy_frame(trades, daily, quarters)
    charts_dir = output_root / "charts"
    if charts_dir.exists():
        for p in charts_dir.glob("*.png"):
            p.unlink()
    chart_rows = build_charts(autopsy, trades, daily, quarters, charts_dir)
    text, html_body = write_reports(output_root, autopsy, chart_rows)
    print("Wrote %s (%d charts)" % (output_root, len(chart_rows)), flush=True)

    if email:
        atts = sorted(charts_dir.glob("*.png"))
        # Stay under typical attachment budgets: send in one shot if <7.5MB else two batches.
        total = sum(p.stat().st_size for p in atts)
        if total < 7.5 * 1024 * 1024:
            send_email(
                subject="potions: reclaim-as-primary MAE/MFE charts (%d png)" % len(atts),
                body=text,
                html=html_body,
                attachments=atts,
            )
            print("email sent attachments=%d bytes=%d" % (len(atts), total), flush=True)
        else:
            mid = (len(atts) + 1) // 2
            send_email(
                subject="potions: reclaim MAE/MFE charts 1/2",
                body=text + "\n(part 1/%d)\n" % 2,
                html=html_body,
                attachments=atts[:mid],
            )
            send_email(
                subject="potions: reclaim MAE/MFE charts 2/2",
                body=text + "\n(part 2/%d)\n" % 2,
                html=html_body,
                attachments=atts[mid:],
            )
            print("email sent in 2 parts attachments=%d" % len(atts), flush=True)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--playbook", type=Path, default=PLAYBOOK)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--daily", type=Path, default=DAILY)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        return run(
            playbook=args.playbook,
            output_root=args.output_root,
            daily_path=args.daily,
            email=bool(args.email),
        )
    except Exception:
        if args.email:
            import traceback

            tb = traceback.format_exc()
            try:
                send_email(
                    subject="potions: reclaim MAE/MFE autopsy FAILED",
                    body="Hub: %s\n\n%s" % (args.output_root, tb[-4000:]),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
