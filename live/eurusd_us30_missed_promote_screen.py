"""Screen missed EURUSD / US30 positives: month blackout + rolling WR/PF + stance.

Uses existing broker-like ``unit_fills.csv`` (or ``unit_trades.csv``) tapes — no
full re-replay. Filtered N/S uses closed-equity DD on taken campaigns (proxy);
unfiltered stress comes from the source SUMMARY when provided.

Hub → ``live/state/eurusd_us30_missed_promote_screen/``.
"""

from __future__ import annotations

import argparse
import html
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .asia_range_shadow import gate_blocks, profit_factor, win_rate
from .fx_v2b_asia_range_london_usdjpy_filters import audit_months, pick_skip_months
from .notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "eurusd_us30_missed_promote_screen"
NY = "America/New_York"


@dataclass(frozen=True)
class Candidate:
    key: str
    label: str
    symbol: str
    family: str
    unit_path: Path
    unfiltered_net: float
    unfiltered_stress: float
    unfiltered_ns: float
    sizing_note: str
    already_demoed: bool = False


def candidates() -> List[Candidate]:
    eurusd_st = (
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/eurusd/audits"
    )
    monday_us30 = REPO / "live/state/monday_or_sizing_sweep_broker_us30/audits"
    prior = REPO / "live/state/fx_v2b_london_prior_opposed/states"
    london4h = REPO / "live/state/fx_v2b_london_4h_or/states"
    monday_eur = (
        REPO
        / "live/state/monday_or_sizing_sweep_broker/audits"
    )
    return [
        Candidate(
            key="eurusd_st_pmc_3r",
            label="EURUSD ST+PMC 50/150 fair 3R",
            symbol="EURUSD",
            family="hourly_st_pmc",
            unit_path=eurusd_st
            / "eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill"
            / "eurusd_hourly_st_pmc_sl50_tp150_3r_1mfill"
            / "unit_fills.csv",
            unfiltered_net=64449.0,
            unfiltered_stress=-21432.0,
            unfiltered_ns=3.01,
            sizing_note="variant grid 3R / 2R→10R / indef (fx_index_metals_st_pmc_runner_variants)",
        ),
        Candidate(
            key="eurusd_st_pmc_2r10r",
            label="EURUSD ST+PMC 50/150 2R→10R",
            symbol="EURUSD",
            family="hourly_st_pmc",
            unit_path=eurusd_st
            / "eurusd_hourly_st_pmc_sl50_tp150_runners_2r_10r"
            / "eurusd_hourly_st_pmc_sl50_tp150_runners_2r_10r"
            / "unit_fills.csv",
            unfiltered_net=121157.0,
            unfiltered_stress=-67308.0,
            unfiltered_ns=1.80,
            sizing_note="variant grid 3R / 2R→10R / indef",
        ),
        Candidate(
            key="us30_monday_or_m3_s3_r3",
            label="US30 Monday OR M3_S3_R3",
            symbol="US30",
            family="monday_or",
            unit_path=monday_us30 / "us30_m3_s3_r3" / "us30_m3_s3_r3" / "unit_fills.csv",
            unfiltered_net=29891.0,
            unfiltered_stress=-15899.0,
            unfiltered_ns=1.88,
            sizing_note="27-cell Phase 1 sizing sweep (monday_or_sizing_sweep_broker_us30)",
        ),
        Candidate(
            key="us30_monday_or_m3_s3_r2",
            label="US30 Monday OR M3_S3_R2 (max 3/wk)",
            symbol="US30",
            family="monday_or",
            unit_path=monday_us30 / "us30_m3_s3_r2" / "us30_m3_s3_r2" / "unit_fills.csv",
            unfiltered_net=31330.0,
            unfiltered_stress=-16941.0,
            unfiltered_ns=1.85,
            sizing_note="27-cell Phase 1 sizing sweep #2",
        ),
        Candidate(
            key="us30_london_prior_opposed",
            label="US30 London prior-opposed S_1_1_3",
            symbol="US30",
            family="v2b_london",
            unit_path=prior / "us30_v2b_london_prior_opposed_S_1_1_3" / "unit_trades.csv",
            unfiltered_net=24369.95,
            unfiltered_stress=-3912.5,
            unfiltered_ns=6.23,
            sizing_note="London screen book S_1_1_3 (no dedicated sizing sweep)",
        ),
        Candidate(
            key="us30_london_4h_s111",
            label="US30 London 4h OR S_1_1_1",
            symbol="US30",
            family="v2b_london",
            unit_path=london4h / "us30_v2b_london_4h_or_S_1_1_1" / "unit_trades.csv",
            unfiltered_net=22708.25,
            unfiltered_stress=-14472.75,
            unfiltered_ns=1.57,
            sizing_note="London 4h screen; soft per tracker (≤~1.6)",
        ),
        Candidate(
            key="eurusd_monday_or_m1_s2_r2",
            label="EURUSD Monday OR M1_S2_R2 (Phase 2)",
            symbol="EURUSD",
            family="monday_or",
            unit_path=monday_eur / "eurusd_m1_s2_r2" / "eurusd_m1_s2_r2" / "unit_fills.csv",
            unfiltered_net=123271.0,
            unfiltered_stress=-70900.0,
            unfiltered_ns=1.74,
            sizing_note="Phase 1+2 hardened; tracker paper-only (sub-period FAIL)",
        ),
    ]


def _load_campaigns(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    usd_col = "usd" if "usd" in df.columns else ("net_usd" if "net_usd" in df.columns else None)
    if usd_col is None:
        raise ValueError("no usd/net_usd in %s" % path)
    g = (
        df.groupby("trade_id", as_index=False)
        .agg(entry_ts=("entry_ts", "first"), net_usd=(usd_col, "sum"))
        .sort_values("entry_ts")
        .reset_index(drop=True)
    )
    g["entry_ts"] = pd.to_datetime(g["entry_ts"], utc=True)
    g["entry_ny"] = g["entry_ts"].dt.tz_convert(NY)
    g["session"] = g["entry_ny"].dt.date
    g["month"] = g["entry_ny"].dt.month
    g["year"] = g["entry_ny"].dt.year
    g["win"] = g["net_usd"] > 0
    return g


def _closed_dd(nets: Sequence[float]) -> float:
    if not nets:
        return 0.0
    eq = pd.Series(nets).cumsum()
    dd = (eq - eq.cummax()).min()
    return float(dd)


def gate_params_for(family: str) -> Tuple[float, float]:
    """ST+PMC is low-WR / high-R:R — do not use Asia-range 40% WR floor."""
    if family == "hourly_st_pmc":
        return 0.22, 1.0
    return 0.40, 1.0


def apply_filters(
    campaigns: pd.DataFrame,
    *,
    skip_months: Sequence[int],
    window: int = 50,
    min_wr: float = 0.40,
    min_pf: float = 1.0,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    skip_m = set(int(x) for x in skip_months)
    hist: List[float] = []
    rows = []
    reasons = {"month": 0, "roll": 0, "take": 0, "warmup": 0}
    for _, row in campaigns.iterrows():
        net = float(row["net_usd"])
        month_block = int(row["month"]) in skip_m
        roll_block, meta = gate_blocks(hist, window=window, min_wr=min_wr, min_pf=min_pf)
        take = (not month_block) and (not roll_block)
        if month_block:
            reasons["month"] += 1
            reason = "month"
        elif roll_block:
            reasons["roll"] += 1
            reason = "roll"
        elif float(meta.get("warmup") or 0.0) >= 1.0:
            reasons["warmup"] += 1
            reasons["take"] += 1
            reason = "warmup_take"
        else:
            reasons["take"] += 1
            reason = "take"
        rows.append(
            {
                "trade_id": row["trade_id"],
                "entry_ts": row["entry_ts"].isoformat(),
                "session": str(row["session"]),
                "month": int(row["month"]),
                "net_usd": net,
                "take": take,
                "reason": reason,
                "shadow_wr": float(meta.get("wr") or 0.0),
                "shadow_pf": float(meta.get("pf") or 0.0),
            }
        )
        # Shadow book advances on ALL campaigns (unfiltered).
        hist.append(net)
    out = pd.DataFrame(rows)
    taken = out[out["take"]]
    taken_nets = taken["net_usd"].tolist()
    filt_net = float(sum(taken_nets))
    filt_dd = _closed_dd(taken_nets)
    filt_stress = filt_dd if filt_dd < 0 else -1e-9
    filt_ns = filt_net / abs(filt_stress) if filt_stress < 0 else 0.0
    stats = {
        "n_campaigns": int(len(out)),
        "n_taken": int(len(taken)),
        "n_skipped": int((~out["take"]).sum()),
        "reasons": reasons,
        "filtered_net": filt_net,
        "filtered_closed_dd": filt_dd,
        "filtered_ns_proxy": filt_ns,
        "filtered_wr": win_rate(taken_nets),
        "filtered_pf": profit_factor(taken_nets),
        "unfiltered_wr": win_rate(out["net_usd"].tolist()),
        "unfiltered_pf": profit_factor(out["net_usd"].tolist()),
        "unfiltered_closed_dd": _closed_dd(out["net_usd"].tolist()),
    }
    return out, stats


def stance_for(c: Candidate, stats: Dict[str, Any], skip_months: List[int]) -> Dict[str, Any]:
    """Promote / half_size / reject using filtered proxy + unfiltered anchors."""
    u_ns = float(c.unfiltered_ns)
    f_ns = float(stats["filtered_ns_proxy"])
    f_net = float(stats["filtered_net"])
    # Prefer filtered when it improves; else unfiltered.
    best_ns = max(u_ns, f_ns)
    filters_help = f_ns >= u_ns * 1.05 and f_net > 0
    note_bits = []
    if skip_months:
        note_bits.append("skip months %s" % skip_months)
    else:
        note_bits.append("no month blackout")
    if filters_help:
        note_bits.append("filters lift N/S %.2f→%.2f" % (u_ns, f_ns))
    else:
        note_bits.append("filters N/S proxy %.2f vs unfilt %.2f" % (f_ns, u_ns))

    if c.key == "eurusd_monday_or_m1_s2_r2":
        return {
            "stance": "paper_half",
            "size_mult": 0.5,
            "reason": "Phase 2 hardened but sub-period FAIL — paper-only @ 1/2 size; "
            + "; ".join(note_bits),
        }
    if c.family == "v2b_london" and c.key == "us30_london_prior_opposed":
        # High headline N/S but tracker curiosity — only promote if filters hold AND n large.
        if stats["n_taken"] >= 80 and f_ns >= 2.0 and f_net > 0:
            return {
                "stance": "half_size",
                "size_mult": 0.5,
                "reason": "prior-opposed curiosity survives filters — 1/2 size demo; "
                + "; ".join(note_bits),
            }
        return {
            "stance": "reject",
            "size_mult": 0.0,
            "reason": "prior-opposed fails filter robustness / sparse taken book; "
            + "; ".join(note_bits),
        }
    if best_ns >= 2.5 and f_net > 0 and u_ns >= 2.0:
        return {
            "stance": "promote",
            "size_mult": 1.0,
            "reason": "strong unfiltered N/S + positive filtered book; " + "; ".join(note_bits),
        }
    if best_ns >= 1.5 and f_net > 0 and u_ns >= 1.5:
        # Mid pack: full size if filters help or unfilt >= 1.8; else half.
        if u_ns >= 1.8 and (filters_help or f_ns >= 1.5):
            return {
                "stance": "promote",
                "size_mult": 1.0,
                "reason": "solid mid N/S; " + "; ".join(note_bits),
            }
        return {
            "stance": "half_size",
            "size_mult": 0.5,
            "reason": "marginal / soft after filters — 1/2 size; " + "; ".join(note_bits),
        }
    if best_ns >= 1.0 and f_net > 0 and u_ns >= 1.0:
        return {
            "stance": "half_size",
            "size_mult": 0.5,
            "reason": "marginally positive — 1/2 size; " + "; ".join(note_bits),
        }
    return {
        "stance": "reject",
        "size_mult": 0.0,
        "reason": "fails promote gates; " + "; ".join(note_bits),
    }


def write_month_audit(path: Path, audit: pd.DataFrame, skip_months: List[int], title: str) -> None:
    lines = [
        "# %s — calendar month audit" % title,
        "",
        "Skip lock: `neg_frac_years >= 0.55` and `mean_yr_net < 0`.",
        "Skip months: **%s**"
        % (", ".join(date(2000, m, 1).strftime("%B") for m in skip_months) if skip_months else "(none)"),
        "",
        "| Month | N | Net $ | WR | Neg years | Neg frac | Mean yr net |",
        "|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in audit.sort_values("month").iterrows():
        m = int(r["month"])
        flag = " **SKIP**" if m in skip_months else ""
        lines.append(
            "| %s | %d | $%.0f | %.1f%% | %d | %.2f | $%.0f |%s"
            % (
                date(2000, m, 1).strftime("%b"),
                int(r["n"]),
                float(r["net"]),
                100.0 * float(r["wr"]),
                int(r["years_neg"]),
                float(r["neg_frac_years"]),
                float(r["mean_yr_net"]),
                flag,
            )
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def html_report(rows: List[Dict[str, Any]], dropped: List[str]) -> str:
    body_rows = []
    for r in rows:
        stance = r["stance"]
        color = {
            "promote": "#0a7a2f",
            "half_size": "#9a6700",
            "paper_half": "#9a6700",
            "reject": "#a40e26",
        }.get(stance, "#333")
        body_rows.append(
            "<tr>"
            "<td>%s</td><td>%s</td>"
            "<td style='text-align:right'>%.2f</td><td style='text-align:right'>$%.0f</td>"
            "<td style='text-align:right'>%.2f</td><td style='text-align:right'>$%.0f</td>"
            "<td style='text-align:right'>%d→%d</td>"
            "<td style='color:%s;font-weight:600'>%s</td>"
            "<td>%s</td></tr>"
            % (
                html.escape(r["label"]),
                html.escape(r["symbol"]),
                r["unfiltered_ns"],
                r["unfiltered_net"],
                r["filtered_ns_proxy"],
                r["filtered_net"],
                r["n_campaigns"],
                r["n_taken"],
                color,
                html.escape(stance),
                html.escape(r["reason"][:160]),
            )
        )
    drop_li = "".join("<li>%s</li>" % html.escape(x) for x in dropped)
    return """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>EURUSD/US30 missed promote screen</title></head>
<body style="font-family:Segoe UI,Helvetica,Arial,sans-serif;max-width:1100px;margin:24px auto;color:#222">
<h1>EURUSD / US30 — drop ungated + missed positives</h1>
<p>Stopped <b>EURUSD/US30 v2b ungated</b> paper+OANDA daemons (live sleeve losers).
Screened missed positives with sizing context, calendar-month blackout, rolling 50 WR≥40%% / PF≥1
on the <b>unfiltered</b> campaign book, then stance for demo paper+OANDA.</p>
<h2>Dropped</h2><ul>%s</ul>
<h2>Screen board</h2>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;font-size:13px">
<thead><tr>
<th>Book</th><th>Sym</th><th>Unfilt N/S</th><th>Unfilt net</th>
<th>Filt N/S*</th><th>Filt net</th><th>Camp→taken</th><th>Stance</th><th>Why</th>
</tr></thead>
<tbody>%s</tbody>
</table>
<p style="font-size:12px;color:#555">*Filtered N/S uses closed-equity DD on taken campaigns (proxy), not full reachable stress re-replay.</p>
<p>Hub: <code>live/state/eurusd_us30_missed_promote_screen/</code></p>
</body></html>""" % (
        drop_li,
        "\n".join(body_rows),
    )


def text_report(rows: List[Dict[str, Any]], dropped: List[str]) -> str:
    lines = [
        "EURUSD/US30 missed promote screen",
        "",
        "Dropped ungated daemons:",
    ]
    lines.extend("- %s" % d for d in dropped)
    lines.append("")
    lines.append(
        "%-42s %8s %10s %8s %10s %10s %s"
        % ("book", "uN/S", "uNet", "fN/S", "fNet", "stance", "size")
    )
    for r in rows:
        lines.append(
            "%-42s %8.2f %10.0f %8.2f %10.0f %10s x%.1f"
            % (
                r["key"][:42],
                r["unfiltered_ns"],
                r["unfiltered_net"],
                r["filtered_ns_proxy"],
                r["filtered_net"],
                r["stance"],
                r["size_mult"],
            )
        )
        lines.append("  %s" % r["reason"])
    lines.append("")
    lines.append("Hub: live/state/eurusd_us30_missed_promote_screen/")
    return "\n".join(lines) + "\n"


def run(*, email: bool) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    dropped = [
        "eurusd_v2b_ungated_{paper,oanda}",
        "us30_v2b_ungated_{paper,oanda}",
    ]
    board: List[Dict[str, Any]] = []
    for c in candidates():
        out_dir = HUB / c.key
        out_dir.mkdir(parents=True, exist_ok=True)
        if not c.unit_path.exists():
            board.append(
                {
                    "key": c.key,
                    "label": c.label,
                    "symbol": c.symbol,
                    "unfiltered_ns": c.unfiltered_ns,
                    "unfiltered_net": c.unfiltered_net,
                    "filtered_ns_proxy": 0.0,
                    "filtered_net": 0.0,
                    "n_campaigns": 0,
                    "n_taken": 0,
                    "stance": "reject",
                    "size_mult": 0.0,
                    "reason": "missing unit tape: %s" % c.unit_path,
                    "skip_months": [],
                    "family": c.family,
                    "unit_path": str(c.unit_path),
                    "sizing_note": c.sizing_note,
                }
            )
            continue
        camps = _load_campaigns(c.unit_path)
        # audit_months expects net_usd column and win; reuse shared helper with USD=1 scale
        audit = audit_months(camps)
        # audit_months divides net_usd by JPY_USD for display column net_usd — we use 'net'
        skip_months = pick_skip_months(audit)
        write_month_audit(out_dir / "MONTH_AUDIT.md", audit, skip_months, c.label)
        min_wr, min_pf = gate_params_for(c.family)
        decisions, stats = apply_filters(
            camps, skip_months=skip_months, min_wr=min_wr, min_pf=min_pf
        )
        stats["gate_min_wr"] = min_wr
        stats["gate_min_pf"] = min_pf
        decisions.to_csv(out_dir / "filter_decisions.csv", index=False)
        stance = stance_for(c, stats, skip_months)
        payload = {
            "candidate": c.key,
            "label": c.label,
            "symbol": c.symbol,
            "family": c.family,
            "sizing_note": c.sizing_note,
            "unit_path": str(c.unit_path),
            "skip_months": skip_months,
            "unfiltered_net": c.unfiltered_net,
            "unfiltered_stress": c.unfiltered_stress,
            "unfiltered_ns": c.unfiltered_ns,
            **stats,
            **stance,
        }
        (out_dir / "RESULT.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        board.append(
            {
                "key": c.key,
                "label": c.label,
                "symbol": c.symbol,
                "unfiltered_ns": c.unfiltered_ns,
                "unfiltered_net": c.unfiltered_net,
                "filtered_ns_proxy": stats["filtered_ns_proxy"],
                "filtered_net": stats["filtered_net"],
                "n_campaigns": stats["n_campaigns"],
                "n_taken": stats["n_taken"],
                "stance": stance["stance"],
                "size_mult": stance["size_mult"],
                "reason": stance["reason"],
                "skip_months": skip_months,
                "family": c.family,
                "unit_path": str(c.unit_path),
                "sizing_note": c.sizing_note,
                "filtered_wr": stats["filtered_wr"],
                "filtered_pf": stats["filtered_pf"],
            }
        )

    pd.DataFrame(board).to_csv(HUB / "summary.csv", index=False)
    (HUB / "summary.json").write_text(json.dumps(board, indent=2) + "\n", encoding="utf-8")

    # Markdown SUMMARY
    md = [
        "# EURUSD / US30 missed promote screen",
        "",
        "Dropped live ungated v2b daemons (paper+OANDA) for EURUSD and US30.",
        "",
        "Filter contract: calendar-month blackout (`neg_frac_years≥0.55` & mean yr net&lt;0) "
        "+ shadow roll50 WR≥40% / PF≥1 on **unfiltered** campaign nets.",
        "",
        "| Book | Sym | Unfilt N/S | Filt N/S* | Skip months | Stance | Size |",
        "|---|---|---:|---:|---|---|---:|",
    ]
    for r in board:
        md.append(
            "| %s | %s | %.2f | %.2f | %s | **%s** | ×%.1f |"
            % (
                r["label"],
                r["symbol"],
                r["unfiltered_ns"],
                r["filtered_ns_proxy"],
                ",".join(str(m) for m in r.get("skip_months") or []) or "—",
                r["stance"],
                r["size_mult"],
            )
        )
    md.extend(
        [
            "",
            "\\* Filtered N/S = filtered net / |closed-equity DD| on taken campaigns.",
            "",
            "## Stance detail",
            "",
        ]
    )
    for r in board:
        md.append("- **%s** — `%s`: %s" % (r["label"], r["stance"], r["reason"]))
    (HUB / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    html_body = html_report(board, dropped)
    text_body = text_report(board, dropped)
    (HUB / "EMAIL.html").write_text(html_body, encoding="utf-8")
    (HUB / "EMAIL.txt").write_text(text_body, encoding="utf-8")
    if email:
        send_email(
            subject="potions: EURUSD/US30 ungated dropped + missed promote screen",
            body=text_body,
            html=html_body,
        )
    return HUB


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)
    hub = run(email=bool(args.email))
    print("wrote", hub)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
