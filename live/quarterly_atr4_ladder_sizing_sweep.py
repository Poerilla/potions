"""Runner-heavy sizing sweep for quarterly ATR4 fade-ladder stress top-5.

Uses exit-mix contribution shares (flatten / tp4 / tp3 / tp2 / tp1) to size
the ATR ladder, with runner ≥8 on most cells. Broker-like Engine+PaperBroker
replays per (market × sizing) cell.

Stress-board books (path / mode / risk unchanged; only entry/scale qtys vary):
  GBPUSD, NAS100, NQ, EURUSD — best_path
  XAUUSD — family first_lower (stress board)

Artifacts → live/state/quarterly_atr4_ladder_sizing_sweep/
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .quarterly_atr4_fade_broker import MARKETS
from .quarterly_atr4_fade_ladder_broker import (
    DEFAULT_BEST_PATH,
    _base_book,
    _fx_metal_book,
    load_books_from_best_path,
    run_one,
    _progress,
)
from .replay_manifest import write_run_manifest

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_ladder_sizing_sweep"

# Stress / yearly board names (EXIT_MIX.md).
TOP5: List[Tuple[str, str]] = [
    ("GBPUSD", "best_path"),
    ("NAS100", "best_path"),
    ("NQ", "best_path"),
    ("EURUSD", "best_path"),
    ("XAUUSD", "family_first_lower"),
]

# Board-wide share of positive exit PnL (EXIT_MIX.md).
CONTRIB_SHARES = {
    "flatten": 0.308,
    "tp4": 0.249,
    "tp3": 0.199,
    "tp2": 0.160,
    "tp1": 0.085,
}


@dataclass(frozen=True)
class SizeCell:
    tag: str
    entry_qty: int
    scale_qtys: Tuple[int, int, int, int]  # tp1..tp4 at +2/+4/+6/+8 ATR
    note: str

    @property
    def runner(self) -> int:
        return int(self.entry_qty) - sum(int(x) for x in self.scale_qtys)

    @property
    def label(self) -> str:
        a, b, c, d = self.scale_qtys
        return "%d/%d/%d/%d/%d" % (a, b, c, d, self.runner)


def _round_shares_to_qtys(total: int, runner_floor: int = 8) -> Tuple[int, int, int, int, int]:
    """Allocate ``total`` contracts by CONTRIB_SHARES with runner ≥ floor."""
    keys = ["tp1", "tp2", "tp3", "tp4", "flatten"]
    shares = [CONTRIB_SHARES[k] for k in keys]
    raw = [total * s for s in shares]
    qtys = [int(x) for x in raw]
    # Largest-remainder seats for unused contracts.
    rem = total - sum(qtys)
    order = sorted(range(5), key=lambda i: (raw[i] - qtys[i]), reverse=True)
    for i in range(rem):
        qtys[order[i % 5]] += 1
    # Enforce runner floor by stealing from front of ladder (weakest contrib first).
    if total >= runner_floor and qtys[4] < runner_floor:
        need = runner_floor - qtys[4]
        for i in range(4):
            take = min(qtys[i], need)
            qtys[i] -= take
            qtys[4] += take
            need -= take
            if need <= 0:
                break
    return (qtys[0], qtys[1], qtys[2], qtys[3], qtys[4])


def sizing_grid() -> List[SizeCell]:
    """Contribution-informed runner-heavy grid (runner ≥8 on most cells)."""
    cells: List[SizeCell] = [
        SizeCell("baseline_2_2_2_2_2", 10, (2, 2, 2, 2), "control equal ladder"),
        SizeCell(
            "contrib_1_2_2_3_8",
            16,
            (1, 2, 2, 3),
            "contrib-shaped among scales; runner=8 (~share-weighted)",
        ),
        SizeCell(
            "contrib_1_2_3_4_8",
            18,
            (1, 2, 3, 4),
            "steeper back-weight + runner=8",
        ),
        SizeCell(
            "contrib_2_3_4_5_8",
            22,
            (2, 3, 4, 5),
            "contrib ratios scaled up; runner=8",
        ),
        SizeCell("runner_1_1_1_1_8", 12, (1, 1, 1, 1), "flat early; fat runner"),
        SizeCell("runner_1_1_2_2_8", 14, (1, 1, 2, 2), "mild back-load; runner=8"),
        SizeCell("runner_2_2_2_2_8", 16, (2, 2, 2, 2), "same early as baseline; fat runner"),
        SizeCell("skip_tp1_0_1_2_3_8", 14, (0, 1, 2, 3), "drop weakest contrib (tp1)"),
        SizeCell("backload_0_0_2_4_8", 14, (0, 0, 2, 4), "only +6/+8 + runner"),
        SizeCell("runner_1_1_1_2_10", 15, (1, 1, 1, 2), "runner=10"),
        SizeCell("runner_1_2_2_3_10", 18, (1, 2, 2, 3), "contrib-shaped; runner=10"),
        SizeCell("runner_1_1_2_2_12", 18, (1, 1, 2, 2), "runner=12"),
    ]
    # Exact share round at total=16 and total=20 with runner floor 8.
    for total in (16, 20, 26):
        t1, t2, t3, t4, r = _round_shares_to_qtys(total, runner_floor=8)
        tag = "share_%d_%d_%d_%d_%d" % (t1, t2, t3, t4, r)
        if any(c.tag == tag for c in cells):
            continue
        cells.append(
            SizeCell(
                tag,
                total,
                (t1, t2, t3, t4),
                "rounded board contrib shares @ total=%d (runner≥8)" % total,
            )
        )
    return cells


def _book_for_market(sym: str, source: str, best_books: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    if source == "family_first_lower":
        b = _fx_metal_book()
        b["path_id"] = "family / first_only_lower"
        return b
    b = dict(best_books[sym])
    return b


def _apply_sizing(book: Dict[str, Any], cell: SizeCell) -> Dict[str, Any]:
    out = dict(book)
    out["entry_qty"] = int(cell.entry_qty)
    out["scale_qtys"] = list(cell.scale_qtys)
    out["scale_qty"] = int(cell.scale_qtys[0] or 1)  # unused when scale_qtys set
    out.pop("path_id", None)
    out.pop("path_win_rate", None)
    return out


def write_summary(output_root: Path, rows: List[dict]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    fields = [
        "market",
        "book_source",
        "sizing_tag",
        "sizing_label",
        "entry_qty",
        "runner_qty",
        "scale_qtys",
        "path_id",
        "trade_mode",
        "risk_atr_mult",
        "net_usd",
        "stress_dd",
        "net_over_stress",
        "net_per_10ct",
        "stress_per_10ct",
        "ns_risk_norm",
        "trades",
        "units",
        "win_rate",
        "profit_factor",
        "note",
    ]
    path = output_root / "summary.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in fields})

    # Per-market best by risk-normalized N/S then raw N/S.
    lines = [
        "# Quarterly ATR4 ladder — runner-heavy sizing sweep",
        "",
        "Stress top-5 books; ladder ATR rungs fixed (+2/+4/+6/+8); only contract",
        "allocation changes. Runner-heavy cells target residual ≥8.",
        "",
        "Contribution priors (board +PnL share): flatten 30.8% · tp4 24.9% · "
        "tp3 19.9% · tp2 16.0% · tp1 8.5%.",
        "",
        "`net_per_10ct` / `ns_risk_norm` scale PnL & stress to a 10-contract entry "
        "so larger books are comparable to baseline `2/2/2/2/2`.",
        "",
    ]
    by_m: Dict[str, List[dict]] = {}
    for r in rows:
        by_m.setdefault(str(r["market"]), []).append(r)

    lines.append("## Per-market ranking (by ns_risk_norm)")
    lines.append("")
    for m in [t[0] for t in TOP5]:
        cells = sorted(
            by_m.get(m, []),
            key=lambda r: (
                float(r.get("ns_risk_norm") or -1e18),
                float(r.get("net_per_10ct") or -1e18),
            ),
            reverse=True,
        )
        lines.append("### %s" % m)
        lines.append("")
        lines.append(
            "| sizing | entry | net | stress | N/S | net/10ct | N/Sₙ | WR | note |"
        )
        lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in cells:
            lines.append(
                "| `%s` | %d | $%s | $%s | %.2f | $%s | %.2f | %.0f%% | %s |"
                % (
                    r.get("sizing_label"),
                    int(r.get("entry_qty") or 0),
                    f"{float(r.get('net_usd') or 0.0):,.0f}",
                    f"{float(r.get('stress_dd') or 0.0):,.0f}",
                    float(r.get("net_over_stress") or 0.0),
                    f"{float(r.get('net_per_10ct') or 0.0):,.0f}",
                    float(r.get("ns_risk_norm") or 0.0),
                    100.0 * float(r.get("win_rate") or 0.0),
                    r.get("note") or "",
                )
            )
        lines.append("")

    # Board aggregate risk-normalized.
    lines.append("## Board aggregate (sum net/10ct; worst stress/10ct)")
    lines.append("")
    tags = sorted({str(r["sizing_tag"]) for r in rows})
    board_rows = []
    for tag in tags:
        subset = [r for r in rows if r["sizing_tag"] == tag]
        if len(subset) < len(TOP5):
            continue
        net10 = sum(float(r.get("net_per_10ct") or 0.0) for r in subset)
        # portfolio stress proxy: sum of per-market stress (conservative)
        st10 = sum(float(r.get("stress_per_10ct") or 0.0) for r in subset)
        ns = (net10 / abs(st10)) if st10 else 0.0
        lab = subset[0].get("sizing_label")
        note = subset[0].get("note")
        board_rows.append((ns, net10, st10, lab, tag, note))
    board_rows.sort(reverse=True)
    lines.append("| sizing | Σ net/10ct | Σ stress/10ct | N/Sₙ | note |")
    lines.append("|---|---:|---:|---:|---|")
    for ns, net10, st10, lab, tag, note in board_rows:
        lines.append(
            "| `%s` | $%s | $%s | %.2f | %s |"
            % (lab, f"{net10:,.0f}", f"{st10:,.0f}", ns, note or tag)
        )
    lines.append("")
    lines.append("Hub: `%s`" % output_root.as_posix())
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = [
        "potions: quarterly ATR4 ladder runner-heavy sizing sweep complete",
        "",
        "Hub: %s" % output_root,
        "Markets: %s" % ", ".join(t[0] for t in TOP5),
        "",
        "Board leaders (risk-normalized):",
    ]
    for ns, net10, st10, lab, tag, note in board_rows[:5]:
        email.append(
            "  %s  Σnet/10=$%s  N/Sₙ=%.2f  (%s)"
            % (lab, f"{net10:,.0f}", ns, note or tag)
        )
    email += ["", "See SUMMARY.md for per-market tables."]
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run_sweep(
    *,
    output_root: Path,
    force: bool,
    email: bool,
    markets: Optional[Sequence[str]] = None,
    tags: Optional[Sequence[str]] = None,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    best_books = load_books_from_best_path(DEFAULT_BEST_PATH)
    cells = sizing_grid()
    if tags:
        want = {t.lower() for t in tags}
        cells = [c for c in cells if c.tag.lower() in want or c.label.replace("/", "_") in want]
    market_filter = {m.upper() for m in markets} if markets else None

    rows: List[dict] = []
    try:
        for sym, source in TOP5:
            if market_filter and sym not in market_filter:
                continue
            base = _book_for_market(sym, source, best_books)
            path_id = str(base.get("path_id") or source)
            for cell in cells:
                if cell.runner < 0:
                    raise SystemExit("bad cell %s runner=%d" % (cell.tag, cell.runner))
                book = _apply_sizing(base, cell)
                # Isolate each cell under its own output subtree so caches don't collide.
                cell_root = output_root / "cells" / cell.tag
                _progress(
                    output_root,
                    "RUN %s %s (%s) entry=%d runner=%d"
                    % (sym, cell.label, cell.tag, cell.entry_qty, cell.runner),
                )
                metrics = run_one(
                    output_root=cell_root,
                    market=MARKETS[sym],
                    force=force,
                    book=book,
                )
                entry = float(cell.entry_qty)
                net = float(metrics.get("net_usd") or 0.0)
                stress = float(metrics.get("stress_dd") or 0.0)
                scale = 10.0 / entry if entry else 1.0
                net10 = net * scale
                st10 = stress * scale
                ns_raw = float(metrics.get("net_over_stress") or 0.0)
                ns_norm = (net10 / abs(st10)) if st10 else 0.0
                row = {
                    "market": sym,
                    "book_source": source,
                    "sizing_tag": cell.tag,
                    "sizing_label": cell.label,
                    "entry_qty": cell.entry_qty,
                    "runner_qty": cell.runner,
                    "scale_qtys": json.dumps(list(cell.scale_qtys)),
                    "path_id": path_id,
                    "trade_mode": book.get("trade_mode"),
                    "risk_atr_mult": book.get("risk_atr_mult"),
                    "net_usd": net,
                    "stress_dd": stress,
                    "net_over_stress": ns_raw,
                    "net_per_10ct": net10,
                    "stress_per_10ct": st10,
                    "ns_risk_norm": ns_norm,
                    "trades": metrics.get("trades"),
                    "units": metrics.get("units"),
                    "win_rate": metrics.get("win_rate"),
                    "profit_factor": metrics.get("profit_factor"),
                    "note": cell.note,
                }
                rows.append(row)
                write_summary(output_root, rows)

        write_summary(output_root, rows)
        write_run_manifest(
            output_root,
            data_inputs=[MARKETS[s].csv for s, _ in TOP5],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={
                "plugin": "quarterly_atr4_fade_ladder",
                "contrib_shares": CONTRIB_SHARES,
                "cells": [
                    {
                        "tag": c.tag,
                        "entry_qty": c.entry_qty,
                        "scale_qtys": list(c.scale_qtys),
                        "runner": c.runner,
                        "note": c.note,
                    }
                    for c in cells
                ],
            },
            broker_realism_config={"slippage_ticks": 1.0},
            extra={"markets": [s for s, _ in TOP5]},
        )
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "n_rows": len(rows)}, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: quarterly ATR4 ladder sizing sweep FAILED\n\nHub: %s\n\n%s\n"
            % (output_root, err),
            encoding="utf-8",
        )
        if email:
            from .notify_email import send_email

            send_email(
                subject="potions: quarterly ATR4 ladder sizing sweep FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        from .notify_email import send_email

        send_email(
            subject="potions: quarterly ATR4 ladder runner-heavy sizing sweep complete",
            body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress(output_root, "email sent")
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--symbol", action="append", default=None)
    ap.add_argument("--tag", action="append", default=None, help="Restrict to sizing tag(s)")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument(
        "--list-cells",
        action="store_true",
        help="Print sizing grid and exit",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.list_cells:
        for c in sizing_grid():
            print("%s  %s  entry=%d  note=%s" % (c.tag, c.label, c.entry_qty, c.note))
        return 0
    run_sweep(
        output_root=args.output_root,
        force=args.force,
        email=args.email,
        markets=args.symbol,
        tags=args.tag,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
