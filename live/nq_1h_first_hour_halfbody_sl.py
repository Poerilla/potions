"""NQ first-hour follow: tighter SL (0.5× body) + 1R/2R/3R + 2-lot scaleout.

Interprets "SL at 0.5% of the body" as **0.5 × body** from close entry
(half-body stop). Entry still at FH close (follow).

Books:
  - baseline: SL=open, TP=3×body, 1 lot (reference)
  - 1 lot: SL = entry ± 0.5×body, TP = kR for k in {1,2,3}
  - 2 lots: same SL; 1 lot TP at FH high (long) / FH low (short);
    runner TP = kR for k in {1,2,3}

Diagnostic 5m walk only.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_1h_first_hour_halfbody_sl --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .nq_1h_first_hour_ha import FH_CLOSE, build_first_hour
from .nq_5m_large_candle_study import FEE, POINT_VALUE, TICK, load_rth_5m, score_nets

HUB = REPO / "live" / "state" / "nq_1h_first_hour_halfbody_sl"
NY = "America/New_York"
SL_BODY_FRAC = 0.5  # default half-body
R_MULTS = (1.0, 2.0, 3.0)


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _rest_by_day(df5: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    out: Dict[str, pd.DataFrame] = {}
    for day, sess in df5.groupby("session_date", sort=False):
        st = sess["ts"].dt.tz_convert(NY).dt.time
        rest = sess[st >= FH_CLOSE].reset_index(drop=True)
        if not rest.empty:
            out[str(day)] = rest
    return out


def _walk_units(
    highs: np.ndarray,
    lows: np.ndarray,
    closes: np.ndarray,
    *,
    side: str,
    entry: float,
    sl: float,
    targets: List[Tuple[float, int]],
) -> List[dict]:
    """Walk remaining bars; ``targets`` = list of (price, qty) sorted by proximity.

    Same-bar SL+TP → stop first. Returns one row per unit filled/exited.
    """
    remaining = list(targets)
    open_qty = sum(q for _, q in remaining)
    rows: List[dict] = []
    direction = 1 if side == "long" else -1

    def _emit(exit_px: float, reason: str, qty: int, j: int, role: str) -> None:
        pts = (exit_px - entry) * direction
        net = pts * POINT_VALUE * qty - FEE * qty
        rows.append(
            {
                "qty": qty,
                "exit_px": float(exit_px),
                "reason": reason,
                "role": role,
                "exit_i": j,
                "pts": pts,
                "net_usd": net,
                "r_mult": pts / abs(entry - sl) if abs(entry - sl) > TICK else 0.0,
            }
        )

    for j in range(len(closes)):
        if open_qty <= 0:
            break
        hit_sl = (lows[j] <= sl) if side == "long" else (highs[j] >= sl)
        # Collect targets touched this bar (favorable first)
        hit_tgts: List[Tuple[float, int]] = []
        still: List[Tuple[float, int]] = []
        for px, q in remaining:
            touched = (highs[j] >= px) if side == "long" else (lows[j] <= px)
            if touched:
                hit_tgts.append((px, q))
            else:
                still.append((px, q))
        if hit_sl and hit_tgts:
            # stop first — flatten all remaining at SL
            _emit(sl, "stop", open_qty, j, "stop_all")
            open_qty = 0
            remaining = []
            break
        if hit_sl:
            _emit(sl, "stop", open_qty, j, "stop_all")
            open_qty = 0
            remaining = []
            break
        if hit_tgts:
            # fill nearer targets first
            if side == "long":
                hit_tgts.sort(key=lambda t: t[0])
            else:
                hit_tgts.sort(key=lambda t: -t[0])
            for px, q in hit_tgts:
                role = "tp1" if abs(px - targets[0][0]) < TICK * 0.5 or (
                    len(targets) > 1 and abs(px - targets[0][0]) <= abs(px - targets[-1][0])
                ) else "runner"
                # label by matching original target list order
                role = "tp1" if (px, q) == targets[0] or (
                    len(targets) >= 1 and abs(px - targets[0][0]) < 1e-9
                ) else "runner"
                _emit(px, "target", q, j, role)
                open_qty -= q
            remaining = still

    if open_qty > 0:
        _emit(float(closes[-1]), "eod", open_qty, len(closes) - 1, "eod")
    return rows


def walk_book(
    df5: pd.DataFrame,
    fh: pd.DataFrame,
    *,
    sl_mode: str,
    r_mult: float,
    qty: int,
    scaleout_extreme: bool,
    sl_body_frac: float = SL_BODY_FRAC,
    tp_mode: str = "r_mult",  # r_mult | body_mult
    scaleout_r_ladder: bool = False,  # 1@1R + 1@2R + 1@3R (qty should be 3)
    flag_col: str = "is_any",
) -> pd.DataFrame:
    """One row per session (aggregated PnL) + unit detail columns."""
    rest_by = _rest_by_day(df5)
    rows: List[dict] = []
    for _, sig in fh.iterrows():
        if not bool(sig.get(flag_col, False)):
            continue
        candle_side = str(sig["dir"])
        if candle_side not in ("long", "short"):
            continue
        day = str(sig["session_date"])
        rest = rest_by.get(day)
        if rest is None or rest.empty:
            continue
        body = float(sig["body"])
        if body < TICK:
            continue
        o = float(sig["open"])
        h = float(sig["high"])
        l = float(sig["low"])
        c = float(sig["close"])
        side = candle_side
        entry = c
        direction = 1 if side == "long" else -1
        if sl_mode == "open":
            sl = o
            risk = abs(entry - sl)
            if risk < TICK:
                continue
            r_px = body if tp_mode == "body_mult" else risk
            risk_basis = "open"
        else:
            r_px = float(sl_body_frac) * body
            if r_px < TICK:
                continue
            sl = entry - r_px if side == "long" else entry + r_px
            risk = r_px
            risk_basis = "body_frac_%.2f" % float(sl_body_frac)

        if tp_mode == "body_mult":
            # Classic baseline-style target: k × body from entry (ignore SL distance).
            runner_tp = entry + direction * r_mult * body
        else:
            runner_tp = entry + direction * r_mult * r_px

        targets: List[Tuple[float, int]]
        if scaleout_r_ladder:
            # 1 lot each at 1R / 2R / 3R (R = stop distance).
            r_stop = abs(entry - sl)
            if r_stop < TICK:
                continue
            targets = [
                (entry + direction * 1.0 * r_stop, 1),
                (entry + direction * 2.0 * r_stop, 1),
                (entry + direction * 3.0 * r_stop, 1),
            ]
            scale_mode = "ladder_1r_2r_3r"
            qty = 3
        elif scaleout_extreme and qty >= 2:
            tp1 = h if side == "long" else l
            if side == "long" and tp1 <= entry + TICK:
                targets = [(runner_tp, qty)]
                scale_mode = "runner_only_no_tp1_room"
            elif side == "short" and tp1 >= entry - TICK:
                targets = [(runner_tp, qty)]
                scale_mode = "runner_only_no_tp1_room"
            else:
                targets = [(tp1, 1), (runner_tp, qty - 1)]
                scale_mode = "tp1_extreme_plus_runner"
        else:
            targets = [(runner_tp, qty)]
            scale_mode = "single"

        highs = rest["high"].to_numpy(float)
        lows = rest["low"].to_numpy(float)
        closes = rest["close"].to_numpy(float)
        unit_rows = _walk_units(highs, lows, closes, side=side, entry=entry, sl=sl, targets=targets)
        net = float(sum(u["net_usd"] for u in unit_rows))
        reasons = [u["reason"] for u in unit_rows]
        rows.append(
            {
                "session_date": day,
                "side": side,
                "entry": entry,
                "sl": sl,
                "runner_tp": runner_tp,
                "tp1": targets[0][0] if len(targets) > 1 else float("nan"),
                "qty": qty,
                "r_mult": r_mult,
                "sl_mode": sl_mode,
                "sl_body_frac": float(sl_body_frac) if sl_mode != "open" else float("nan"),
                "tp_mode": tp_mode,
                "risk_px": risk,
                "risk_basis": risk_basis,
                "scale_mode": scale_mode,
                "body": body,
                "fh_high": h,
                "fh_low": l,
                "net_usd": net,
                "win": net > 0,
                "n_units": len(unit_rows),
                "reasons": "|".join(reasons),
                "unit_nets": "|".join("%.2f" % u["net_usd"] for u in unit_rows),
            }
        )
    return pd.DataFrame(rows)


def book_row(label: str, trades: pd.DataFrame) -> dict:
    sc = score_nets(trades["net_usd"].to_numpy(float) if not trades.empty else np.array([]))
    return {
        "label": label,
        "n": sc["n"],
        "wr": sc["wr"],
        "avg": sc["avg"],
        "net": sc["net"],
        "stress": sc["stress"],
        "ns": sc["ns"],
        "pf": sc["pf"],
        "avg_risk_px": float(trades["risk_px"].mean()) if not trades.empty else float("nan"),
    }


def write_summary(hub: Path, books: List[dict]) -> Path:
    lines = [
        "# NQ first-hour follow — body-fraction SL + scaleout",
        "",
        "Diagnostic 5m walk. Entry at FH close (follow). Flatten leftover at 16:00.",
        "",
        "- **half-body** books: SL = 0.5 × body; R = that distance; TP = kR.",
        "- **0.75-body** books: SL = 0.75 × body.",
        "  - 1-lot baseline-style: TP = **3 × body** (not 3R).",
        "  - 3-lot ladder: 1@1R + 1@2R + 1@3R (R = 0.75×body stop).",
        "- 2-lot extreme books: 1 at FH high/low; runner at kR.",
        "",
        "| Book | n | WR | avg $ | net | stress | N/S | PF | avg risk pts |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in books:
        lines.append(
            "| {label} | {n} | {wr:.1f}% | ${avg:,.0f} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | {pf:.2f} | {risk:.1f} |".format(
                label=b["label"],
                n=b["n"],
                wr=100.0 * float(b["wr"]),
                avg=float(b["avg"]),
                net=float(b["net"]),
                stress=float(b["stress"]),
                ns=float(b["ns"]),
                pf=float(b["pf"]),
                risk=float(b["avg_risk_px"]) if np.isfinite(b["avg_risk_px"]) else float("nan"),
            )
        )
    lines += [
        "",
        "## Stance",
        "",
        "Research / diagnostic. Rebuild on Engine+PaperBroker before promote.",
        "",
        "Hub: `%s`" % hub,
        "",
    ]
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(books).to_csv(hub / "summary.csv", index=False)
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(argv)

    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    if (hub / "PROGRESS.log").exists():
        (hub / "PROGRESS.log").unlink()

    try:
        df5 = load_rth_5m(progress=True)
        if args.smoke:
            cut = pd.Timestamp(df5["ts"].max()).tz_convert(NY) - pd.Timedelta(days=400)
            df5 = df5[df5["ts"] >= cut].reset_index(drop=True)
            _progress("SMOKE from %s" % cut.date())
        fh = build_first_hour(df5)
        _progress("fh days=%d" % len(fh))

        specs: List[Tuple[str, dict]] = [
            (
                "baseline SL=open TP=3×body 1-lot",
                dict(sl_mode="open", r_mult=3.0, qty=1, scaleout_extreme=False, tp_mode="body_mult"),
            ),
        ]
        for k in R_MULTS:
            specs.append(
                (
                    "half-body SL + %gR 1-lot" % k,
                    dict(
                        sl_mode="half_body",
                        r_mult=k,
                        qty=1,
                        scaleout_extreme=False,
                        sl_body_frac=0.5,
                        tp_mode="r_mult",
                    ),
                )
            )
        for k in R_MULTS:
            specs.append(
                (
                    "half-body SL + TP1@FH extreme + runner %gR 2-lot" % k,
                    dict(
                        sl_mode="half_body",
                        r_mult=k,
                        qty=2,
                        scaleout_extreme=True,
                        sl_body_frac=0.5,
                        tp_mode="r_mult",
                    ),
                )
            )
        specs.append(
            (
                "0.75-body SL + TP=3×body 1-lot",
                dict(
                    sl_mode="body_frac",
                    r_mult=3.0,
                    qty=1,
                    scaleout_extreme=False,
                    sl_body_frac=0.75,
                    tp_mode="body_mult",
                ),
            )
        )
        specs.append(
            (
                "0.75-body SL + 1R/2R/3R ladder 3-lot",
                dict(
                    sl_mode="body_frac",
                    r_mult=3.0,
                    qty=3,
                    scaleout_extreme=False,
                    sl_body_frac=0.75,
                    tp_mode="r_mult",
                    scaleout_r_ladder=True,
                ),
            )
        )

        books: List[dict] = []
        for label, kw in specs:
            _progress("RUN %s ..." % label)
            tr = walk_book(df5, fh, **kw)
            slug = (
                label.lower()
                .replace(" ", "_")
                .replace("+", "plus")
                .replace("=", "")
                .replace("/", "_")
                .replace("×", "x")
                .replace("%", "pct")
                .replace(",", "")
            )
            tr.to_csv(hub / ("trades_%s.csv" % slug[:80]), index=False)
            row = book_row(label, tr)
            books.append(row)
            _progress(
                "  n=%d WR=%.1f%% net=$%+.0f N/S=%.2f"
                % (row["n"], 100 * row["wr"], row["net"], row["ns"])
            )

        write_summary(hub, books)
        email_lines = [
            "NQ first-hour half-body SL + scaleout complete",
            "Hub: %s" % hub,
            "Note: SL = 0.5 × body from close (interpreted from “0.5% of the body”).",
            "",
        ]
        for b in books:
            email_lines.append(
                "%s: n=%d WR=%.1f%% net=$%+.0f N/S=%.2f"
                % (b["label"], b["n"], 100 * b["wr"], b["net"], b["ns"])
            )
        email_lines += ["", "Stance: diagnostic only.", ""]
        (hub / "EMAIL.txt").write_text("\n".join(email_lines), encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "books": books, "sl_body_frac": SL_BODY_FRAC}, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: NQ FH half-body SL + scaleout complete",
                body=(hub / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress("FAIL\n" + tb)
        fail = hub / "EMAIL_FAIL.txt"
        fail.write_text(tb, encoding="utf-8")
        try:
            send_email(subject="potions: NQ FH half-body SL FAILED", body=tb)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
