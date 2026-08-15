"""Build compact, phone-friendly job completion summaries with key numbers."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import List, Optional, Sequence

REPO = Path(__file__).resolve().parents[1]
FX_HUB = REPO / "live" / "state" / "fx_index_metals_st_pmc_runner_variants"
SWEEP_HUB = REPO / "live" / "state" / "st_pmc_runner_length_sweep"
US30_HUB = REPO / "live" / "state" / "us30_st_pmc_runner_variants"

VARIANT_LABEL = {
    "sl50_tp150_3r_1mfill": "3R",
    "sl50_tp150_runners_2r_10r": "2R→10R",
    "sl50_tp150_runners_2r_indef": "indef",
}


def _money(v: object) -> str:
    try:
        x = float(v)
    except Exception:
        return str(v)
    sign = "-" if x < 0 else ""
    ax = abs(x)
    if ax >= 1000:
        return "%s$%.1fk" % (sign, ax / 1000.0)
    return "%s$%.0f" % (sign, ax)


def _load_csv(path: Path) -> List[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _row_line(r: dict) -> str:
    v = VARIANT_LABEL.get(str(r.get("variant")), str(r.get("variant")))
    return (
        "%-7s %-7s  net=%-8s stress=%-8s N/S=%-6s  units=%s WR=%s%% max=%s EOY=%s"
        % (
            r.get("market"),
            v,
            _money(r.get("net_usd")),
            _money(r.get("stress_dd_usd")),
            ("%.2f" % float(r["ns"])) if r.get("ns") not in (None, "") else "?",
            r.get("units"),
            r.get("wr_pct"),
            r.get("max_open"),
            r.get("eoy_flatten_units"),
        )
    )


def fx_summary(
    *,
    markets: Optional[Sequence[str]] = None,
    variants: Optional[Sequence[str]] = None,
    title: str = "FX/index/metals ST+PMC",
) -> str:
    rows = _load_csv(FX_HUB / "summary.csv")
    # Also scrape Net= lines from logs if summary incomplete
    want_m = {m.lower() for m in markets} if markets else None
    want_v = set(variants) if variants else None
    filtered = []
    for r in rows:
        if want_m and str(r.get("market", "")).lower() not in want_m:
            continue
        if want_v and str(r.get("variant")) not in want_v:
            continue
        filtered.append(r)

    # Supplement from run logs / MTM for missing
    for m in sorted(want_m or []):
        for vname, label in VARIANT_LABEL.items():
            if want_v and vname not in want_v:
                continue
            if any(str(r.get("market")) == m and str(r.get("variant")) == vname for r in filtered):
                continue
            scraped = _scrape_log_net(m, vname) or _scrape_mtm(m, vname)
            if scraped:
                filtered.append(scraped)

    filtered.sort(key=lambda r: (str(r.get("market")), str(r.get("variant"))))
    lines = [title, "", "market  book     net      stress   N/S     units/WR/max/EOY", "-" * 72]
    if not filtered:
        lines.append("(no rows yet — check logs)")
    for r in filtered:
        lines.append(_row_line(r))

    # Rankable 3R snapshot for context
    three = [r for r in _load_csv(FX_HUB / "summary.csv") if r.get("variant") == "sl50_tp150_3r_1mfill"]
    us30 = _us30_3r_row()
    if us30:
        three.append(us30)
    if three:
        three.sort(key=lambda r: -float(r.get("ns") or 0))
        lines += ["", "Fair 3R leaderboard (rankable)", "-" * 40]
        for i, r in enumerate(three, 1):
            lines.append(
                "%d. %-7s N/S=%-6s net=%s stress=%s"
                % (i, r.get("market"), ("%.2f" % float(r["ns"])), _money(r.get("net_usd")), _money(r.get("stress_dd_usd")))
            )

    lines += ["", "Hub: %s" % FX_HUB]
    return "\n".join(lines) + "\n"


def _scrape_log_net(market: str, variant: str) -> Optional[dict]:
    # Prefer dedicated 3r log
    candidates = [
        FX_HUB / ("run_%s_3r.log" % market),
        FX_HUB / ("run_%s.log" % market),
    ]
    label = VARIANT_LABEL.get(variant, variant)
    for path in candidates:
        if not path.exists():
            continue
        text = path.read_text(errors="replace")
        # Match: EURUSD Net=$121157 Stress=$-67308 N/S=1.80 units=855 WR=17.1% max_open=3 EOY=0
        # Only keep the Net line that follows a done for this variant when possible
        blocks = re.split(r"\n(?=RUN )", text)
        relevant = [b for b in blocks if variant in b or ("3r" in variant and "3r" in b)]
        blob = relevant[-1] if relevant else text
        m = re.search(
            r"([A-Z0-9]+)\s+Net=\$([0-9.\-]+)\s+Stress=\$([0-9.\-]+)\s+N/S=([0-9.\-]+)\s+units=(\d+)\s+WR=([0-9.\-]+)%\s+max_open=(\d+)\s+EOY=(\d+)",
            blob,
        )
        if not m:
            continue
        # If multiple Net lines, take last in blob
        matches = re.findall(
            r"([A-Z0-9]+)\s+Net=\$([0-9.\-]+)\s+Stress=\$([0-9.\-]+)\s+N/S=([0-9.\-]+)\s+units=(\d+)\s+WR=([0-9.\-]+)%\s+max_open=(\d+)\s+EOY=(\d+)",
            blob,
        )
        if not matches:
            continue
        inst, net, stress, ns, units, wr, mx, eoy = matches[-1]
        return {
            "market": market,
            "instrument": inst,
            "variant": variant,
            "net_usd": float(net),
            "stress_dd_usd": float(stress),
            "ns": float(ns),
            "units": int(units),
            "wr_pct": float(wr),
            "max_open": int(mx),
            "eoy_flatten_units": int(eoy),
            "notes": "from log (%s)" % label,
        }
    return None


def _scrape_mtm(market: str, variant: str) -> Optional[dict]:
    sid = "%s_hourly_st_pmc_%s" % (market, variant)
    path = FX_HUB / market / "audits" / sid / sid / "reports" / "MTM_AUDIT.md"
    if not path.exists():
        return None
    t = path.read_text(errors="replace")

    def money(label: str) -> Optional[float]:
        m = re.search(r"\| %s \| \$([0-9,.\-]+) \|" % re.escape(label), t)
        return float(m.group(1).replace(",", "")) if m else None

    def num(label: str) -> Optional[float]:
        m = re.search(r"\| %s \| ([0-9.\-]+) \|" % re.escape(label), t)
        return float(m.group(1)) if m else None

    net = money("Net dollars")
    stress = money("Intrabar stress MTM DD")
    if net is None or stress is None:
        return None
    units = int(num("Units") or 0)
    wins = int(num("Winning units") or 0)
    mx = int(num("Max open units") or 0)
    ns = (net / abs(stress)) if stress else 0.0
    wr = 100.0 * wins / units if units else 0.0
    return {
        "market": market,
        "instrument": market.upper(),
        "variant": variant,
        "net_usd": net,
        "stress_dd_usd": stress,
        "ns": round(ns, 3),
        "units": units,
        "wr_pct": round(wr, 1),
        "max_open": mx,
        "eoy_flatten_units": 0,
        "notes": "from MTM_AUDIT",
    }


def _us30_3r_row() -> Optional[dict]:
    rows = _load_csv(US30_HUB / "summary.csv")
    for r in rows:
        if "3r" in str(r.get("variant", "")):
            r = dict(r)
            r["market"] = "us30"
            return r
    return None


def sweep_summary(*, markets: Optional[Sequence[str]] = None) -> str:
    lines = ["Runner length sweep (postprocess)", "", "market  best_k  N/S    net     stress  vs3R  vs10R  k10_ok", "-" * 72]
    want = {m.lower() for m in markets} if markets else None
    any_row = False
    for path in sorted(SWEEP_HUB.glob("*/result.json")):
        m = path.parent.name
        if want and m not in want:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("status") != "ok":
            lines.append("%-7s %s" % (m, data.get("status")))
            continue
        b = data.get("best_finite") or {}
        r10 = data.get("ref_10r") or {}
        v = data.get("validation") or {}
        vs3 = "YES" if b.get("beats_fair_3r_ns") else "no"
        vs10 = "YES" if (r10 and float(b.get("ns") or 0) > float(r10.get("ns") or 0)) else "no"
        ok = "yes" if v.get("ok_points") else ("—" if not v else "NO")
        lines.append(
            "%-7s k=%-4s  %-6s %-7s %-7s %-4s  %-4s   %s"
            % (
                m,
                b.get("k"),
                ("%.2f" % float(b["ns"])) if b.get("ns") is not None else "?",
                _money(b.get("net_usd")),
                _money(b.get("stress_usd")),
                vs3,
                vs10,
                ok,
            )
        )
        any_row = True
        # include compact grid of N/S by k
        ns_bits = []
        for row in data.get("rows") or []:
            if row.get("k") == "indef":
                continue
            ns_bits.append("%s:%.2f" % (row["k"], float(row["ns"])))
        if ns_bits:
            lines.append("         N/S by k: " + " ".join(ns_bits))
    if not any_row and want:
        lines.append("(waiting on indef tapes: %s)" % ", ".join(sorted(want)))
    lines += ["", "Hub: %s" % SWEEP_HUB]
    return "\n".join(lines) + "\n"


def progress_snapshot() -> str:
    lines = ["Live progress snapshot", "-" * 40]
    for m in ["eurusd", "gbpusd", "usdjpy", "audjpy", "xauusd", "xagusd"]:
        for suffix in ("_3r", ""):
            path = FX_HUB / ("run_%s%s.log" % (m, suffix))
            if not path.exists():
                continue
            text = path.read_text(errors="replace")
            prog = re.findall(r"(sl50_tp150_\S+)\s+hourly\s+(\d+)/(\d+)", text)
            done = re.findall(r"(sl50_tp150_\S+)\s+done:", text)
            if prog:
                v, a, b = prog[-1]
                lines.append("%s%s: %s %s/%s (%.0f%%) done=%s" % (m, suffix, v, a, b, 100 * int(a) / int(b), done))
            elif done:
                lines.append("%s%s: done=%s" % (m, suffix, done))
    return "\n".join(lines) + "\n"


def main(argv: Optional[Sequence[str]] = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--kind", choices=["fx", "fx3r", "sweep", "all", "progress"], default="all")
    ap.add_argument("--markets", nargs="*", default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    parts: List[str] = []
    if args.kind in ("fx", "all"):
        parts.append(fx_summary(markets=args.markets, title="FX/index/metals ST+PMC results"))
    if args.kind == "fx3r":
        parts.append(
            fx_summary(
                markets=args.markets or ["audjpy", "xauusd", "xagusd"],
                variants=["sl50_tp150_3r_1mfill"],
                title="Fair 3R complete",
            )
        )
    if args.kind in ("sweep", "all"):
        parts.append(sweep_summary(markets=args.markets))
    if args.kind == "progress":
        parts.append(progress_snapshot())
    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
