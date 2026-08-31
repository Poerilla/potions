"""PnL attribution for yearly ORB exit-variant sizing hubs.

Reads broker-like audit ``unit_fills.csv`` under ``<hub>/audits/<slug>/`` and
attributes realized USD by exit reason, entry unit role, direction, and year.

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python3 -m live.yearly_orb_exit_attribution \\
      --hub live/state/yearly_orb_exit_variants_fx_metals --email
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from .notify_email import send_email
from .yearly_orb_sizing_sweep import FX_METALS_MARKETS

REPO = Path(__file__).resolve().parents[1]

# Books to always attribute: exit-mode baselines + pack leaders.
ALWAYS_SLUGS = {
    "L_1_1_1",
    "L_1_1_1_mid",
    "L_1_1_1_swing",
    "L_4_2_1",
    "L_4_2_1_mid",
    "L_4_2_1_swing",
}


@dataclass(frozen=True)
class BookRef:
    market: str
    instrument: str
    slug: str
    exit_mode: str
    label: str
    pnl_ccy: str
    usd_fx_approx: Optional[float]
    fee_per_unit: float
    net_usd_approx: float
    stress_usd_approx: float
    net_over_stress: float
    tp25_qty: int
    tp_qty: int
    runner_qty: int


def _f(v: object, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _load_summary(hub: Path) -> List[BookRef]:
    path = hub / "summary.csv"
    if not path.exists():
        raise FileNotFoundError("missing %s" % path)
    fee_by_mkt = {m.market: m for m in FX_METALS_MARKETS}
    out: List[BookRef] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            market = str(row.get("market") or "").lower()
            meta = fee_by_mkt.get(market)
            out.append(
                BookRef(
                    market=market,
                    instrument=str(row.get("instrument") or ""),
                    slug=str(row.get("slug") or ""),
                    exit_mode=str(row.get("exit_mode") or "range_close"),
                    label=str(row.get("label") or ""),
                    pnl_ccy=str(row.get("pnl_ccy") or (meta.pnl_ccy if meta else "USD")),
                    usd_fx_approx=(
                        meta.usd_fx_approx
                        if meta is not None
                        else (_f(row.get("usd_fx_approx")) or None)
                    ),
                    fee_per_unit=float(meta.fee_per_unit) if meta is not None else 1.5,
                    net_usd_approx=_f(row.get("net_usd_approx") or row.get("net_usd")),
                    stress_usd_approx=_f(row.get("stress_usd_approx") or row.get("intrabar_stress_dd_usd")),
                    net_over_stress=_f(row.get("net_over_stress_dd")),
                    tp25_qty=int(_f(row.get("tp25_qty"))),
                    tp_qty=int(_f(row.get("tp_qty"))),
                    runner_qty=int(_f(row.get("runner_qty"))),
                )
            )
    return out


def _select_books(all_books: Sequence[BookRef], *, top_n: int = 3) -> List[BookRef]:
    by_inst: Dict[str, List[BookRef]] = defaultdict(list)
    for b in all_books:
        by_inst[b.instrument].append(b)
    chosen: Dict[Tuple[str, str], BookRef] = {}
    for inst, rows in by_inst.items():
        ranked = sorted(rows, key=lambda r: r.net_over_stress, reverse=True)
        for b in ranked[:top_n]:
            chosen[(b.instrument, b.slug)] = b
        for slug in ALWAYS_SLUGS:
            hit = next((r for r in rows if r.slug == slug), None)
            if hit is not None:
                chosen[(hit.instrument, hit.slug)] = hit
    return sorted(chosen.values(), key=lambda b: (b.instrument, -b.net_over_stress, b.slug))


def _unit_role(entry_reason: str) -> str:
    er = str(entry_reason or "").lower()
    if "runner" in er:
        return "runner"
    if "tp25" in er:
        return "tp25"
    if er in {"entry", "long_tp_entry", "short_tp_entry"} or "tp_entry" in er:
        # scaleout3 posts two "entry" fills (tp25 + full TP) and one runner_entry.
        return "scaleout_or_tp"
    return er or "unknown"


def _bucket_exit(reason: str, exit_mode: str) -> str:
    r = str(reason or "").lower()
    if r in {"target", "tp", "tp1", "tp2"}:
        return "target"
    if r in {"stop", "protective_stop"}:
        return "stop"
    if r in {"runner_stop"}:
        return "runner_stop"
    if r in {"close", "range_close", "mid_close", "year_change"}:
        if r == "mid_close" or (r == "close" and exit_mode == "mid_close"):
            return "mid_close_flatten"
        if r == "range_close" or (r == "close" and exit_mode == "range_close"):
            return "range_close_flatten"
        if r == "year_change":
            return "year_change"
        # Generic market close under swing mode is usually year_change / forced flat.
        if exit_mode == "inside_swing_take":
            return "forced_close"
        return "close_flatten"
    if "stop" in r:
        return "stop_other"
    return r or "other"


def _to_usd(native: float, book: BookRef) -> float:
    if book.pnl_ccy == "USD" or not book.usd_fx_approx:
        return native
    return native / float(book.usd_fx_approx)


def _load_units(hub: Path, book: BookRef) -> List[Dict[str, object]]:
    candidates = [
        hub / "audits" / ("%s_yorb_sizing_%s" % (book.market, book.slug)) / "unit_fills.csv",
        hub / "audits" / book.slug / "unit_fills.csv",
    ]
    path = next((p for p in candidates if p.exists()), candidates[0])
    if not path.exists():
        raise FileNotFoundError("unit_fills missing for %s (%s)" % (book.slug, path))
    rows: List[Dict[str, object]] = []
    with path.open(encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            gross = _f(row.get("usd"))
            # unit_fills usd is gross of fees; apply same fee as sizing sweep.
            native_net = gross - float(book.fee_per_unit)
            rows.append(
                {
                    "trade_id": row.get("trade_id"),
                    "unit_id": row.get("unit_id"),
                    "direction": row.get("direction"),
                    "entry_ts": str(row.get("entry_ts") or ""),
                    "exit_ts": str(row.get("exit_ts") or ""),
                    "exit_reason": str(row.get("exit_reason") or ""),
                    "entry_reason": str(row.get("entry_reason") or ""),
                    "unit_role": _unit_role(str(row.get("entry_reason") or "")),
                    "exit_bucket": _bucket_exit(str(row.get("exit_reason") or ""), book.exit_mode),
                    "year": int(str(row.get("exit_ts") or "0")[:4] or 0),
                    "usd": _to_usd(native_net, book),
                    "gross_usd": _to_usd(gross, book),
                }
            )
    return rows


def _agg(rows: Sequence[Dict[str, object]], key: str) -> List[Dict[str, object]]:
    buckets: Dict[object, List[float]] = defaultdict(list)
    for r in rows:
        buckets[r.get(key)].append(_f(r.get("usd")))
    out = []
    for k, vals in buckets.items():
        wins = [v for v in vals if v > 0]
        losses = [v for v in vals if v < 0]
        out.append(
            {
                key: k,
                "n": len(vals),
                "net_usd": sum(vals),
                "wins": len(wins),
                "losses": len(losses),
                "win_usd": sum(wins),
                "loss_usd": sum(losses),
                "avg_usd": (sum(vals) / len(vals)) if vals else 0.0,
                "share_pct": 0.0,
            }
        )
    total = sum(_f(r["net_usd"]) for r in out) or 1.0
    for r in out:
        r["share_pct"] = 100.0 * _f(r["net_usd"]) / total
    return sorted(out, key=lambda r: -abs(_f(r["net_usd"])))


def _fmt(v: float) -> str:
    return "$%s" % ("{:,.0f}".format(v))


def attribute_book(hub: Path, book: BookRef) -> Dict[str, object]:
    units = _load_units(hub, book)
    by_exit = _agg(units, "exit_bucket")
    by_role = _agg(units, "unit_role")
    by_dir = _agg(units, "direction")
    by_year = _agg(units, "year")
    return {
        "book": {
            "instrument": book.instrument,
            "slug": book.slug,
            "exit_mode": book.exit_mode,
            "label": book.label,
            "sizing": "%s/%s/%s" % (book.tp25_qty, book.tp_qty, book.runner_qty),
            "summary_net_usd": book.net_usd_approx,
            "summary_stress_usd": book.stress_usd_approx,
            "summary_ns": book.net_over_stress,
        },
        "n_units": len(units),
        "attributed_net_usd": sum(_f(u["usd"]) for u in units),
        "by_exit_bucket": by_exit,
        "by_unit_role": by_role,
        "by_direction": by_dir,
        "by_year": by_year,
        "top_unit_wins": sorted(units, key=lambda u: -_f(u["usd"]))[:8],
        "top_unit_losses": sorted(units, key=lambda u: _f(u["usd"]))[:8],
    }


def _write_csv(path: Path, rows: Sequence[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    # Flatten nested for summary tables only
    flat = []
    for r in rows:
        flat.append({k: r[k] for k in r if not isinstance(r[k], (list, dict))})
    fields: List[str] = []
    for r in flat:
        for k in r:
            if k not in fields:
                fields.append(k)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in flat:
            w.writerow({k: r.get(k, "") for k in fields})


def render_md(hub: Path, reports: Sequence[Dict[str, object]]) -> str:
    lines = [
        "# Yearly ORB FX/metals exit-variant PnL attribution",
        "",
        "Hub: `%s`" % hub,
        "",
        "Source: audit `unit_fills.csv` (points × point_value − fee/unit; AUDJPY ÷110).",
        "Exit buckets map fill `exit_reason` (broker `close` → mid/range flatten by `exit_mode`).",
        "",
        "## Books covered",
        "",
        "| Instrument | Slug | Exit | Size | Summary N/S | Attributed net |",
        "|---|---|---|---:|---:|---:|",
    ]
    for rep in reports:
        b = rep["book"]
        lines.append(
            "| %s | `%s` | %s | %s | %.2f | %s |"
            % (
                b["instrument"],
                b["slug"],
                b["exit_mode"],
                b["sizing"],
                _f(b["summary_ns"]),
                _fmt(_f(rep["attributed_net_usd"])),
            )
        )

    # Cross-mode compare at L_1_1_1 / L_4_2_1
    lines.extend(["", "## Exit-mode compare (same sizing)", ""])
    for size_slug in ("L_1_1_1", "L_4_2_1"):
        lines.append("### %s family" % size_slug)
        lines.append("")
        lines.append(
            "| Instrument | Mode | Net | Targets | Stops | Runner stops | Mid/range flatten | Forced/year |"
        )
        lines.append("|---|---|---:|---:|---:|---:|---:|---:|")
        for rep in reports:
            slug = str(rep["book"]["slug"])
            if not (slug == size_slug or slug.startswith(size_slug + "_")):
                continue
            if slug not in ALWAYS_SLUGS:
                continue
            by = {r["exit_bucket"]: r for r in rep["by_exit_bucket"]}

            def _n(key: str) -> float:
                return _f(by.get(key, {}).get("net_usd"))

            flatten = _n("mid_close_flatten") + _n("range_close_flatten") + _n("close_flatten")
            forced = _n("forced_close") + _n("year_change")
            lines.append(
                "| %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    rep["book"]["instrument"],
                    rep["book"]["exit_mode"],
                    _fmt(_f(rep["attributed_net_usd"])),
                    _fmt(_n("target")),
                    _fmt(_n("stop")),
                    _fmt(_n("runner_stop")),
                    _fmt(flatten),
                    _fmt(forced),
                )
            )
        lines.append("")

    for rep in reports:
        b = rep["book"]
        lines.extend(
            [
                "## %s — `%s` (%s)" % (b["instrument"], b["slug"], b["exit_mode"]),
                "",
                "Sizing %s · summary N/S **%.2f** · attributed %s (n_units=%d)."
                % (b["sizing"], _f(b["summary_ns"]), _fmt(_f(rep["attributed_net_usd"])), int(rep["n_units"])),
                "",
                "### By exit bucket",
                "",
                "| Bucket | N | Net | Win$ | Loss$ | Share |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for r in rep["by_exit_bucket"]:
            lines.append(
                "| `%s` | %d | %s | %s | %s | %.0f%% |"
                % (
                    r["exit_bucket"],
                    int(r["n"]),
                    _fmt(_f(r["net_usd"])),
                    _fmt(_f(r["win_usd"])),
                    _fmt(_f(r["loss_usd"])),
                    _f(r["share_pct"]),
                )
            )
        lines.extend(
            [
                "",
                "### By unit role (entry_reason)",
                "",
                "| Role | N | Net | Share |",
                "|---|---:|---:|---:|",
            ]
        )
        for r in rep["by_unit_role"]:
            lines.append(
                "| `%s` | %d | %s | %.0f%% |"
                % (r["unit_role"], int(r["n"]), _fmt(_f(r["net_usd"])), _f(r["share_pct"]))
            )
        lines.extend(["", "### By direction", ""])
        for r in rep["by_direction"]:
            lines.append(
                "- **%s**: %s (n=%d)"
                % (r["direction"], _fmt(_f(r["net_usd"])), int(r["n"]))
            )
        years = sorted(rep["by_year"], key=lambda r: _f(r["net_usd"]))
        if years:
            worst = years[0]
            best = years[-1]
            lines.extend(
                [
                    "",
                    "### Year extremes",
                    "",
                    "- Best: **%s** %s (n=%d)"
                    % (best["year"], _fmt(_f(best["net_usd"])), int(best["n"])),
                    "- Worst: **%s** %s (n=%d)"
                    % (worst["year"], _fmt(_f(worst["net_usd"])), int(worst["n"])),
                ]
            )
        lines.append("")

    lines.extend(
        [
            "## Stance",
            "",
            "- Research / not promotion-safe.",
            "- Prefer books where **targets** (not flatten scratches) dominate net.",
            "- If mid_close N/S lift is mostly fewer stop scrapes vs true target alpha, sizing should favor TP/runner weight only after yearly robustness.",
            "- Next: deep-check + win/loss charts on metals mid/swing leaders; sit out AUDJPY until exit mix flips.",
            "",
        ]
    )
    return "\n".join(lines)


def render_email(hub: Path, reports: Sequence[Dict[str, object]]) -> str:
    lines = [
        "potions: yearly ORB FX/metals exit-variant PnL attribution",
        "",
        "Hub: %s" % hub,
        "",
        "Headline (where the $ comes from):",
        "",
    ]
    # Per-instrument leader attribution tip
    by_inst: Dict[str, List[Dict[str, object]]] = defaultdict(list)
    for rep in reports:
        by_inst[str(rep["book"]["instrument"])].append(rep)
    for inst in sorted(by_inst):
        ranked = sorted(by_inst[inst], key=lambda r: _f(r["book"]["summary_ns"]), reverse=True)
        lead = ranked[0]
        by = {r["exit_bucket"]: r for r in lead["by_exit_bucket"]}
        tgt = _f(by.get("target", {}).get("net_usd"))
        st = _f(by.get("stop", {}).get("net_usd")) + _f(by.get("runner_stop", {}).get("net_usd"))
        flat = sum(
            _f(by.get(k, {}).get("net_usd"))
            for k in ("mid_close_flatten", "range_close_flatten", "close_flatten", "forced_close", "year_change")
        )
        lines.append(
            "%s leader `%s` (%s, N/S=%.2f): targets %s · stops %s · flatten/year %s · total %s"
            % (
                inst,
                lead["book"]["slug"],
                lead["book"]["exit_mode"],
                _f(lead["book"]["summary_ns"]),
                _fmt(tgt),
                _fmt(st),
                _fmt(flat),
                _fmt(_f(lead["attributed_net_usd"])),
            )
        )
        # L_1_1_1 mode compare one-liner
        trio = [
            r
            for r in by_inst[inst]
            if str(r["book"]["slug"]) in {"L_1_1_1", "L_1_1_1_mid", "L_1_1_1_swing"}
        ]
        if len(trio) >= 2:
            bits = []
            for r in sorted(trio, key=lambda x: x["book"]["exit_mode"]):
                bb = {x["exit_bucket"]: x for x in r["by_exit_bucket"]}
                bits.append(
                    "%s: tgt %s / stop %s / flat %s"
                    % (
                        r["book"]["exit_mode"],
                        _fmt(_f(bb.get("target", {}).get("net_usd"))),
                        _fmt(
                            _f(bb.get("stop", {}).get("net_usd"))
                            + _f(bb.get("runner_stop", {}).get("net_usd"))
                        ),
                        _fmt(
                            sum(
                                _f(bb.get(k, {}).get("net_usd"))
                                for k in (
                                    "mid_close_flatten",
                                    "range_close_flatten",
                                    "close_flatten",
                                    "forced_close",
                                    "year_change",
                                )
                            )
                        ),
                    )
                )
            lines.append("  L_1_1_1 mix — " + " · ".join(bits))
        lines.append("")

    lines.extend(
        [
            "Stance: research. Metals mid/swing look target-driven; AUDJPY still stop-dominated.",
            "Full write-up: %s/PNL_ATTRIBUTION.md" % hub,
            "",
        ]
    )
    return "\n".join(lines)


def run(*, hub: Path, email: bool = False, top_n: int = 3) -> Path:
    hub = hub.resolve()
    out_root = hub / "pnl_attribution"
    out_root.mkdir(parents=True, exist_ok=True)
    books = _select_books(_load_summary(hub), top_n=top_n)
    reports: List[Dict[str, object]] = []
    for book in books:
        try:
            rep = attribute_book(hub, book)
            reports.append(rep)
            book_dir = out_root / ("%s_%s" % (book.market, book.slug))
            book_dir.mkdir(parents=True, exist_ok=True)
            _write_csv(book_dir / "by_exit_bucket.csv", rep["by_exit_bucket"])  # type: ignore[arg-type]
            _write_csv(book_dir / "by_unit_role.csv", rep["by_unit_role"])  # type: ignore[arg-type]
            _write_csv(book_dir / "by_direction.csv", rep["by_direction"])  # type: ignore[arg-type]
            _write_csv(book_dir / "by_year.csv", rep["by_year"])  # type: ignore[arg-type]
            (book_dir / "summary.json").write_text(json.dumps(rep, indent=2, default=str) + "\n")
            print(
                "attributed %s %s net=%s"
                % (book.instrument, book.slug, _fmt(_f(rep["attributed_net_usd"]))),
                flush=True,
            )
        except Exception:
            print("FAILED %s %s\n%s" % (book.instrument, book.slug, traceback.format_exc()), flush=True)
            raise

    md = render_md(hub, reports)
    email_body = render_email(hub, reports)
    (hub / "PNL_ATTRIBUTION.md").write_text(md, encoding="utf-8")
    (out_root / "PNL_ATTRIBUTION.md").write_text(md, encoding="utf-8")
    (hub / "EMAIL_PNL_ATTRIBUTION.txt").write_text(email_body, encoding="utf-8")
    (out_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (out_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "n_books": len(reports)}, indent=2) + "\n",
        encoding="utf-8",
    )
    if email:
        send_email(
            subject="potions: yearly ORB FX/metals exit-variant PnL attribution",
            body=email_body,
        )
    print("Wrote %s" % (hub / "PNL_ATTRIBUTION.md"), flush=True)
    return hub / "PNL_ATTRIBUTION.md"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--hub",
        type=Path,
        default=REPO / "live" / "state" / "yearly_orb_exit_variants_fx_metals",
    )
    p.add_argument("--top-n", type=int, default=3, help="Extra top N/S books per market beyond baselines")
    p.add_argument("--email", action="store_true")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    hub = args.hub if args.hub.is_absolute() else (Path.cwd() / args.hub).resolve()
    try:
        run(hub=hub, email=bool(args.email), top_n=int(args.top_n))
        return 0
    except Exception:
        tb = traceback.format_exc()
        if args.email:
            send_email(
                subject="potions: yearly ORB exit-variant PnL attribution FAILED",
                body="Hub: %s\n\n%s" % (hub, tb),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
