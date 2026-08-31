"""HP condition mill for NQ opening-candle close-limit 3R (broker fills).

Reads the broker-like ``open1h_close_limit_3r`` tape from
``live/state/nq_opening_candle_close_limit/``, joins first-hour + futures HP
features, and ranks dual-lift notables.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_opening_candle_close_limit_hp --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd

from .nq_1h_first_hour_ha import FH_CONDS, attach_fh_labels, build_first_hour
from .nq_5m_large_candle_study import FEE, POINT_VALUE, load_rth_5m, score_nets, summarize_book
from .nq_large_candle_ha_lib import (
    MIN_N,
    annotate_campaigns,
    attach_po_context,
    attach_trade_po_labels,
    compare_current_hp,
    load_po_campaigns,
    po_buckets_table,
    profile_frame,
    trades_to_campaigns,
)
from .notify_email import send_email
from .v2b_strategy_replay import units_from_v2b_fills

REPO = Path(__file__).resolve().parents[1]
STUDY_HUB = REPO / "live" / "state" / "nq_opening_candle_close_limit"
HUB = STUDY_HUB / "hp"
BOOK = "open1h_close_limit_3r"
STRATEGY_ID = "nq_oc_%s" % BOOK
FAMILY = "nq_opening_candle_close_limit"
NY = "America/New_York"


def units_to_trades(fills_path: Path) -> pd.DataFrame:
    units = units_from_v2b_fills(fills_path, STRATEGY_ID)
    rows: List[dict] = []
    for u in units:
        sign = 1.0 if str(u.direction).lower().startswith("l") else -1.0
        pts = (float(u.exit_price) - float(u.entry_price)) * sign
        net = pts * POINT_VALUE - FEE
        side = "long" if sign > 0 else "short"
        entry_ts = pd.Timestamp(u.entry_ts)
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize(NY)
        else:
            entry_ts = entry_ts.tz_convert(NY)
        exit_ts = pd.Timestamp(u.exit_ts)
        if exit_ts.tzinfo is None:
            exit_ts = exit_ts.tz_localize(NY)
        else:
            exit_ts = exit_ts.tz_convert(NY)
        reason = str(u.exit_reason)
        if reason in {"tp", "tp1", "tp2", "tp3"}:
            reason = "target"
        elif reason in {"eod_close", "eod"}:
            reason = "eod"
        rows.append(
            {
                "session_date": entry_ts.strftime("%Y-%m-%d"),
                "signal_ts": entry_ts,
                "exit_ts": exit_ts,
                "side": side,
                "candle_side": side,
                "fade": False,
                "target_r": 3.0,
                "entry": float(u.entry_price),
                "exit_px": float(u.exit_price),
                "reason": reason,
                "r_mult": pts,  # points; body-normalized later if FH join provides body
                "net_usd": net,
                "win": net > 0,
                "trade_id": str(u.trade_id),
                "year": int(entry_ts.year),
                "hour": int(entry_ts.hour),
            }
        )
    return pd.DataFrame(rows)


def write_report(
    hub: Path,
    *,
    core: dict,
    table: pd.DataFrame,
    notables: List[dict],
    current_cmp: pd.DataFrame,
    yearly: pd.DataFrame,
) -> Tuple[Path, Path]:
    lines = [
        "# NQ opening-candle close-limit 3R — HP condition mill",
        "",
        "Diagnostic only — not a promotion gate. Built on **broker** fills "
        "(`%s`), not pandas walk." % BOOK,
        "",
        "Contract: 1h opening candle → limit @ close → SL=open → TP=3R.",
        "",
        "## Book",
        "",
        "| Book | n | WR | avg | net | stress | N/S | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
        "| {label} | {n} | {wr:.1f}% | ${avg:,.0f} | ${net:,.0f} | ${stress:,.0f} | "
        "{ns:.2f} | {pf:.2f} |".format(
            label=core.get("label", BOOK),
            n=int(core.get("n") or 0),
            wr=100.0 * float(core.get("wr") or 0.0),
            avg=float(core.get("avg") or 0.0),
            net=float(core.get("net") or 0.0),
            stress=float(core.get("stress") or 0.0),
            ns=float(core.get("ns") or 0.0),
            pf=float(core.get("pf") or 0.0),
        ),
        "",
        "## Yearly",
        "",
        "| Year | n | WR | net | N/S |",
        "|---:|---:|---:|---:|---:|",
    ]
    for _, r in yearly.iterrows():
        lines.append(
            "| {y} | {n} | {wr:.1f}% | ${net:,.0f} | {ns:.2f} |".format(
                y=int(r["year"]),
                n=int(r["n"]),
                wr=100.0 * float(r["wr"]),
                net=float(r["net"]),
                ns=float(r["ns"]),
            )
        )

    lines += [
        "",
        "## Top dual-lift notables (n≥%d, WR+avg lift)" % MIN_N,
        "",
        "| Condition | Bucket | n | WR | WR lift | avg | avg lift | z_WR | N/S |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "NQ opening-candle close-limit HP complete",
        "Hub: %s" % hub,
        "Book: %s" % BOOK,
        "",
        "Baseline: n=%d WR=%.1f%% net=$%+.0f N/S=%.2f"
        % (
            int(core.get("n") or 0),
            100.0 * float(core.get("wr") or 0.0),
            float(core.get("net") or 0.0),
            float(core.get("ns") or 0.0),
        ),
        "",
        "Top notables:",
    ]
    top = sorted(notables, key=lambda r: (float(r.get("z_wr") or 0), float(r.get("avg_lift") or 0)), reverse=True)[
        :25
    ]
    if not top:
        lines.append("| — | — | — | — | — | — | — | — | — |")
        email.append("  (none cleared dual-lift bar)")
    for r in top:
        lines.append(
            "| {c} | {b} | {n} | {wr:.1f}% | {wrl:+.1f}pp | ${avg:,.0f} | ${avgl:+,.0f} | "
            "{z:.2f} | {ns:.2f} |".format(
                c=r.get("condition"),
                b=r.get("bucket"),
                n=int(r.get("n") or 0),
                wr=100.0 * float(r.get("wr") or 0.0),
                wrl=float(r.get("wr_lift_pp") or 0.0),
                avg=float(r.get("avg") or 0.0),
                avgl=float(r.get("avg_lift") or 0.0),
                z=float(r.get("z_wr") or 0.0),
                ns=float(r.get("ns") or 0.0),
            )
        )
        email.append(
            "  %s=%s n=%d WR=%.0f%% (+%.1fpp) avg=$%+.0f N/S=%.2f"
            % (
                r.get("condition"),
                r.get("bucket"),
                int(r.get("n") or 0),
                100.0 * float(r.get("wr") or 0.0),
                float(r.get("wr_lift_pp") or 0.0),
                float(r.get("avg") or 0.0),
                float(r.get("ns") or 0.0),
            )
        )

    lines += [
        "",
        "## vs current NQ prior-opposed HP buckets",
        "",
    ]
    if current_cmp is None or current_cmp.empty:
        lines.append("_No overlapping current-HP buckets with enough n._")
        email += ["", "vs current PO HP: no overlap"]
    else:
        lines += [
            "| Condition | Bucket | book n | book WR lift | book avg lift | PO WR lift |",
            "|---|---|---:|---:|---:|---:|",
        ]
        email.append("")
        email.append("vs current PO HP:")
        for _, r in current_cmp.head(20).iterrows():
            wrl = float(r.get("wr_vs_book_pp") or r.get("wr_lift_pp") or 0.0)
            avgl = float(r.get("avg_vs_book") or r.get("avg_lift") or 0.0)
            lines.append(
                "| {c} | {b} | {n} | {wrl:+.1f}pp | ${avgl:+,.0f} | {pow} |".format(
                    c=r.get("condition"),
                    b=r.get("bucket"),
                    n=int(r.get("n") or 0),
                    wrl=wrl,
                    avgl=avgl,
                    pow=("%.1f%%" % (100.0 * float(r["po_wr"]))) if pd.notna(r.get("po_wr")) else "—",
                )
            )
            email.append(
                "  %s=%s n=%d book WR lift %+0.1fpp"
                % (r.get("condition"), r.get("bucket"), int(r.get("n") or 0), wrl)
            )

    lines += [
        "",
        "## Stance",
        "",
        "- Parent study: [`../SUMMARY.md`](../SUMMARY.md) — limit 1h **N/S 3.91** (works).",
        "- HP notes are **hypotheses only**; do not size-up from this mill without nulls.",
        "- Market-close twin remains stronger (N/S 5.57); limit is the fill-discipline variant.",
        "",
        "Hub: `%s`" % hub,
        "",
    ]
    email += [
        "",
        "Stance: HP diagnostic on working limit book; no size-up from notables alone.",
        "Parent hub: %s" % STUDY_HUB,
        "",
    ]
    summary = hub / "SUMMARY.md"
    summary.write_text("\n".join(lines), encoding="utf-8")
    email_path = hub / "EMAIL.txt"
    email_path.write_text("\n".join(email), encoding="utf-8")
    if not table.empty:
        table.to_csv(hub / "buckets.csv", index=False)
    if notables:
        pd.DataFrame(notables).to_csv(hub / "notables.csv", index=False)
    return summary, email_path


def yearly_table(tr: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for year, g in tr.groupby("year"):
        nets = g["net_usd"].to_numpy(float)
        sc = score_nets(nets)
        rows.append(
            {
                "year": int(year),
                "n": int(len(g)),
                "wr": float(g["win"].mean()) if len(g) else 0.0,
                "net": float(nets.sum()),
                "ns": float(sc.get("ns") or 0.0),
            }
        )
    return pd.DataFrame(rows).sort_values("year")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args(argv)

    hub = Path(args.out) if args.out else HUB
    hub.mkdir(parents=True, exist_ok=True)
    if (hub / "PROGRESS.log").exists():
        (hub / "PROGRESS.log").unlink()

    def progress(msg: str) -> None:
        line = msg.rstrip() + "\n"
        print(line, end="", flush=True)
        with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
            fh.write(line)

    try:
        fills = STUDY_HUB / "states" / STRATEGY_ID / "fills.csv"
        if not fills.exists():
            raise FileNotFoundError("missing broker fills: %s" % fills)

        progress("load fills %s" % fills)
        tr = units_to_trades(fills)
        if tr.empty:
            raise RuntimeError("no closed units from fills")
        tr.to_csv(hub / "trades.csv", index=False)
        core = summarize_book(tr, BOOK)
        progress(
            "trades n=%d WR=%.1f%% net=$%+.0f N/S=%.2f"
            % (core["n"], 100 * core["wr"], core["net"], core["ns"])
        )

        progress("load RTH 5m + first-hour features")
        df5 = load_rth_5m(progress=True)
        fh = build_first_hour(df5)
        fh.to_csv(hub / "first_hour_candles.csv", index=False)

        progress("annotate campaigns")
        camp = trades_to_campaigns(tr, BOOK, FAMILY)
        camp = attach_fh_labels(camp, fh)
        camp = annotate_campaigns(camp, "NQ")
        try:
            po = load_po_campaigns(progress=progress)
            if po is not None and not po.empty and "dir" in fh.columns:
                fh_po = attach_po_context(fh, po, p90_col="is_any", progress=progress)
                camp = attach_trade_po_labels(camp, fh_po)
            else:
                progress("skip PO overlay (empty or missing dir)")
        except Exception as po_exc:
            progress("skip PO overlay: %s" % po_exc)
        camp.to_csv(hub / "campaigns.csv", index=False)

        progress("profile conditions")
        table, _base, notables = profile_frame(camp, FH_CONDS, MIN_N)
        progress("notables=%d buckets=%d" % (len(notables), len(table)))

        current_cmp = compare_current_hp({BOOK: camp}, po_buckets_table())
        if not current_cmp.empty:
            current_cmp.to_csv(hub / "vs_current_hp.csv", index=False)

        yearly = yearly_table(tr)
        yearly.to_csv(hub / "yearly.csv", index=False)
        summary, email_path = write_report(
            hub,
            core=core,
            table=table,
            notables=notables,
            current_cmp=current_cmp,
            yearly=yearly,
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "book": BOOK,
                    "n": core.get("n"),
                    "ns": core.get("ns"),
                    "notables": len(notables),
                },
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: NQ opening-candle close-limit HP complete",
                body=email_path.read_text(encoding="utf-8"),
            )
        progress("COMPLETE notables=%d summary=%s" % (len(notables), summary))
        return 0
    except Exception as exc:
        tb = traceback.format_exc()
        progress("FAIL %s\n%s" % (exc, tb))
        fail = "NQ opening-candle close-limit HP FAILED\nHub: %s\n\n%s\n" % (hub, tb[-2500:])
        (hub / "EMAIL.txt").write_text(fail, encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": False, "error": str(exc)}, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.email:
            try:
                send_email(subject="potions: NQ opening-candle close-limit HP FAILED", body=fail)
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
