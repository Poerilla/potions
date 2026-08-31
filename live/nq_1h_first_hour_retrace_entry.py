"""NQ first-hour follow: MAE of close-entry + retracement-limit entries.

Base book: enter at FH close, SL at open, TP = 3× body (diagnostic walk).

This study:
  1. MAE / max retracement of that close-entry path (pts, /body, /range).
  2. Limit entries at 32% / 50% / 72% retracement of the FH **body** from close
     toward open; SL = candle bottom/top (FH low/high); R = |entry−SL|; TP = 3R.
     Missed if price never tags the limit before EOD (or before stopping through SL).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_1h_first_hour_retrace_entry --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .nq_1h_first_hour_ha import FH_CLOSE, FH_OPEN, MIN_FH_BARS, build_first_hour
from .nq_5m_large_candle_study import FEE, POINT_VALUE, TICK, load_rth_5m, score_nets

HUB = REPO / "live" / "state" / "nq_1h_first_hour_retrace_entry"
NY = "America/New_York"
RTH_CLOSE = time(16, 0)
RETRACE_FRACS = (0.32, 0.50, 0.72)


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


def walk_close_entry_with_mae(
    df5: pd.DataFrame,
    fh: pd.DataFrame,
    *,
    flag_col: str = "is_any",
) -> pd.DataFrame:
    """Base follow 3R close-entry + path MAE / retracement depth."""
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
        rng = float(sig["range"])
        if body < TICK or rng < TICK:
            continue
        o = float(sig["open"])
        h = float(sig["high"])
        l = float(sig["low"])
        c = float(sig["close"])
        side = candle_side
        entry = c
        sl = o
        direction = 1 if side == "long" else -1
        tp = entry + direction * 3.0 * body
        highs = rest["high"].to_numpy(float)
        lows = rest["low"].to_numpy(float)
        closes = rest["close"].to_numpy(float)
        times = rest["ts"]
        reason = "eod"
        exit_px = float(closes[-1])
        exit_i = len(rest) - 1
        # MAE from entry (adverse); MFE favorable
        if side == "long":
            mae_px = 0.0
            mfe_px = 0.0
            min_lo = entry
            max_hi = entry
        else:
            mae_px = 0.0
            mfe_px = 0.0
            min_lo = entry
            max_hi = entry
        for j in range(len(rest)):
            if side == "long":
                min_lo = min(min_lo, float(lows[j]))
                max_hi = max(max_hi, float(highs[j]))
                mae_px = max(mae_px, entry - float(lows[j]))
                mfe_px = max(mfe_px, float(highs[j]) - entry)
                hit_sl = lows[j] <= sl
                hit_tp = highs[j] >= tp
            else:
                min_lo = min(min_lo, float(lows[j]))
                max_hi = max(max_hi, float(highs[j]))
                mae_px = max(mae_px, float(highs[j]) - entry)
                mfe_px = max(mfe_px, entry - float(lows[j]))
                hit_sl = highs[j] >= sl
                hit_tp = lows[j] <= tp
            if hit_sl and hit_tp:
                exit_px, reason, exit_i = sl, "stop", j
                break
            if hit_sl:
                exit_px, reason, exit_i = sl, "stop", j
                break
            if hit_tp:
                exit_px, reason, exit_i = tp, "target", j
                break
        # Truncate MAE/MFE to exit bar (path until exit)
        # Recompute on [0..exit_i] for honesty
        if side == "long":
            path_lo = float(lows[: exit_i + 1].min()) if exit_i >= 0 else entry
            path_hi = float(highs[: exit_i + 1].max()) if exit_i >= 0 else entry
            mae_px = max(0.0, entry - path_lo)
            mfe_px = max(0.0, path_hi - entry)
            # Retracement of body from close toward open (and toward low)
            retrace_body = mae_px / body
            retrace_range = mae_px / rng
            # Did price tag open / low before exit?
            tagged_open = path_lo <= o + TICK
            tagged_low = path_lo <= l + TICK
        else:
            path_lo = float(lows[: exit_i + 1].min()) if exit_i >= 0 else entry
            path_hi = float(highs[: exit_i + 1].max()) if exit_i >= 0 else entry
            mae_px = max(0.0, path_hi - entry)
            mfe_px = max(0.0, entry - path_lo)
            retrace_body = mae_px / body
            retrace_range = mae_px / rng
            tagged_open = path_hi >= o - TICK
            tagged_low = path_hi >= h - TICK  # tagged high extreme
        pts = (exit_px - entry) * direction
        net = pts * POINT_VALUE - FEE
        rows.append(
            {
                "session_date": day,
                "side": side,
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "exit_px": float(exit_px),
                "reason": reason,
                "net_usd": net,
                "win": net > 0,
                "body": body,
                "range": rng,
                "fh_open": o,
                "fh_high": h,
                "fh_low": l,
                "fh_close": c,
                "mae_px": mae_px,
                "mfe_px": mfe_px,
                "mae_over_body": retrace_body,
                "mae_over_range": retrace_range,
                "tagged_open": bool(tagged_open),
                "tagged_extreme": bool(tagged_low),
                "fh_body": sig.get("fh_body"),
            }
        )
    return pd.DataFrame(rows)


def walk_retrace_entry(
    df5: pd.DataFrame,
    fh: pd.DataFrame,
    *,
    ret_frac: float,
    flag_col: str = "is_any",
    use_range: bool = False,
) -> pd.DataFrame:
    """Limit at ret_frac retracement; SL at candle extreme; TP = 3R."""
    rest_by = _rest_by_day(df5)
    rows: List[dict] = []
    n_signal = n_armed = n_fill = n_miss = 0
    for _, sig in fh.iterrows():
        if not bool(sig.get(flag_col, False)):
            continue
        candle_side = str(sig["dir"])
        if candle_side not in ("long", "short"):
            continue
        n_signal += 1
        day = str(sig["session_date"])
        rest = rest_by.get(day)
        if rest is None or rest.empty:
            continue
        body = float(sig["body"])
        rng = float(sig["range"])
        if body < TICK or rng < TICK:
            continue
        o = float(sig["open"])
        h = float(sig["high"])
        l = float(sig["low"])
        c = float(sig["close"])
        side = candle_side
        span = rng if use_range else body
        if side == "long":
            # Retrace from close toward open (body) or from high toward low (range)
            entry = (h - ret_frac * span) if use_range else (c - ret_frac * span)
            sl = l  # bottom of candle
            if entry <= sl + TICK:
                n_miss += 1
                continue
            direction = 1
        else:
            entry = (l + ret_frac * span) if use_range else (c + ret_frac * span)
            sl = h  # top of candle
            if entry >= sl - TICK:
                n_miss += 1
                continue
            direction = -1
        risk = abs(entry - sl)
        if risk < TICK:
            n_miss += 1
            continue
        tp = entry + direction * 3.0 * risk
        n_armed += 1
        highs = rest["high"].to_numpy(float)
        lows = rest["low"].to_numpy(float)
        closes = rest["close"].to_numpy(float)
        times = rest["ts"]
        filled = False
        fill_i = -1
        # Walk: wait for limit touch; if price hits SL before fill, miss
        for j in range(len(rest)):
            if side == "long":
                if lows[j] <= sl:
                    # swept SL before fill
                    break
                if lows[j] <= entry:
                    filled = True
                    fill_i = j
                    break
            else:
                if highs[j] >= sl:
                    break
                if highs[j] >= entry:
                    filled = True
                    fill_i = j
                    break
        if not filled:
            n_miss += 1
            continue
        n_fill += 1
        # From fill bar onward; same-bar SL+TP → stop first
        reason = "eod"
        exit_px = float(closes[-1])
        exit_i = len(rest) - 1
        for j in range(fill_i, len(rest)):
            if side == "long":
                hit_sl = lows[j] <= sl
                hit_tp = highs[j] >= tp
            else:
                hit_sl = highs[j] >= sl
                hit_tp = lows[j] <= tp
            if hit_sl and hit_tp:
                exit_px, reason, exit_i = sl, "stop", j
                break
            if hit_sl:
                exit_px, reason, exit_i = sl, "stop", j
                break
            if hit_tp:
                exit_px, reason, exit_i = tp, "target", j
                break
        pts = (exit_px - entry) * direction
        net = pts * POINT_VALUE - FEE
        rows.append(
            {
                "session_date": day,
                "side": side,
                "ret_frac": ret_frac,
                "basis": "range" if use_range else "body",
                "entry": entry,
                "sl": sl,
                "tp": tp,
                "risk_px": risk,
                "exit_px": float(exit_px),
                "reason": reason,
                "net_usd": net,
                "win": net > 0,
                "body": body,
                "range": rng,
                "fh_open": o,
                "fh_high": h,
                "fh_low": l,
                "fh_close": c,
                "fill_i": fill_i,
                "exit_i": int(exit_i),
                "r_mult": pts / risk if risk else 0.0,
                "fh_body": sig.get("fh_body"),
            }
        )
    meta = {"n_signal": n_signal, "n_armed": n_armed, "n_fill": n_fill, "n_miss": n_miss + (n_armed - n_fill)}
    # fix miss count: signals that armed but didn't fill + invalid geometry
    meta["n_miss"] = n_signal - n_fill
    out = pd.DataFrame(rows)
    out.attrs["meta"] = meta
    return out


def mae_summary(base: pd.DataFrame) -> Dict[str, float]:
    if base.empty:
        return {}
    mae_b = base["mae_over_body"].to_numpy(float)
    mae_r = base["mae_over_range"].to_numpy(float)
    mae_px = base["mae_px"].to_numpy(float)
    return {
        "n": len(base),
        "mae_px_median": float(np.median(mae_px)),
        "mae_px_p75": float(np.percentile(mae_px, 75)),
        "mae_px_p90": float(np.percentile(mae_px, 90)),
        "mae_body_median": float(np.median(mae_b)),
        "mae_body_p75": float(np.percentile(mae_b, 75)),
        "mae_body_p90": float(np.percentile(mae_b, 90)),
        "mae_range_median": float(np.median(mae_r)),
        "mae_range_p75": float(np.percentile(mae_r, 75)),
        "mae_range_p90": float(np.percentile(mae_r, 90)),
        "frac_mae_ge_032": float((mae_b >= 0.32).mean()),
        "frac_mae_ge_050": float((mae_b >= 0.50).mean()),
        "frac_mae_ge_072": float((mae_b >= 0.72).mean()),
        "frac_tagged_open": float(base["tagged_open"].mean()),
        "frac_tagged_extreme": float(base["tagged_extreme"].mean()),
        "wins_mae_body_median": float(base.loc[base["win"], "mae_over_body"].median()) if base["win"].any() else float("nan"),
        "losses_mae_body_median": float(base.loc[~base["win"], "mae_over_body"].median()) if (~base["win"]).any() else float("nan"),
    }


def book_row(label: str, trades: pd.DataFrame, meta: Optional[dict] = None) -> dict:
    sc = score_nets(trades["net_usd"].to_numpy(float) if not trades.empty else np.array([]))
    row = {
        "label": label,
        "n": sc["n"],
        "wr": sc["wr"],
        "avg": sc["avg"],
        "net": sc["net"],
        "stress": sc["stress"],
        "ns": sc["ns"],
        "pf": sc["pf"],
        "fill_rate": None,
        "n_signal": None,
        "n_miss": None,
        "stop_n": int((trades["reason"] == "stop").sum()) if not trades.empty else 0,
        "target_n": int((trades["reason"] == "target").sum()) if not trades.empty else 0,
        "eod_n": int((trades["reason"] == "eod").sum()) if not trades.empty else 0,
        "avg_r": float(trades["r_mult"].mean()) if (not trades.empty and "r_mult" in trades.columns) else float("nan"),
        "avg_risk_px": float(trades["risk_px"].mean()) if (not trades.empty and "risk_px" in trades.columns) else float("nan"),
    }
    if meta:
        row["n_signal"] = meta.get("n_signal")
        row["n_miss"] = meta.get("n_miss")
        row["fill_rate"] = (meta["n_fill"] / meta["n_signal"]) if meta.get("n_signal") else 0.0
    return row


def write_summary(hub: Path, mae: dict, books: List[dict]) -> Path:
    lines = [
        "# NQ first-hour follow — MAE + retracement entries",
        "",
        "Diagnostic only (5m walk). Not a promotion gate.",
        "",
        "Universe: NQ RTH first hour 09:30–10:30; follow candle direction.",
        "Base: entry at FH **close**, SL at FH **open**, TP = 3× body, flatten 16:00.",
        "Retrace books: limit at `close − ret×body` (long) / `close + ret×body` (short);",
        "SL = candle **low/high**; R = |entry−SL|; TP = 3R. Miss if limit never tagged (or SL swept first).",
        "",
        "## Base close-entry MAE (path until exit)",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    for k, v in mae.items():
        if isinstance(v, float):
            lines.append("| %s | %.3f |" % (k, v))
        else:
            lines.append("| %s | %s |" % (k, v))
    lines += [
        "",
        "Read: `frac_mae_ge_032` = share of base trades whose adverse path ≥ 32% of body",
        "(i.e. price *would have* tagged a 32% retrace limit).",
        "",
        "## Books",
        "",
        "| Book | n | fill% | WR | avg $ | net | stress | N/S | PF | avg R |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for b in books:
        fill = "" if b.get("fill_rate") is None else "%.0f%%" % (100.0 * float(b["fill_rate"]))
        lines.append(
            "| {label} | {n} | {fill} | {wr:.1f}% | ${avg:,.0f} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | {pf:.2f} | {avg_r:.2f} |".format(
                label=b["label"],
                n=b["n"],
                fill=fill or "—",
                wr=100.0 * float(b["wr"]),
                avg=float(b["avg"]),
                net=float(b["net"]),
                stress=float(b["stress"]),
                ns=float(b["ns"]),
                pf=float(b["pf"]),
                avg_r=float(b["avg_r"]) if np.isfinite(b.get("avg_r", np.nan)) else float("nan"),
            )
        )
    lines += [
        "",
        "## Stance",
        "",
        "Research / diagnostic. Promote only after broker-like Engine+PaperBroker rebuild.",
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
            _progress("SMOKE from %s bars=%d" % (cut.date(), len(df5)))
        _progress("build first-hour candles ...")
        fh = build_first_hour(df5)
        fh.to_csv(hub / "first_hour_candles.csv", index=False)
        _progress("  fh days=%d" % len(fh))

        _progress("base close-entry + MAE ...")
        base = walk_close_entry_with_mae(df5, fh)
        base.to_csv(hub / "base_close_entry_mae.csv", index=False)
        mae = mae_summary(base)
        pd.Series(mae).to_csv(hub / "mae_summary.csv", header=["value"])
        _progress(
            "  MAE body median=%.2f p75=%.2f p90=%.2f | frac≥32/50/72=%.0f/%.0f/%.0f%%"
            % (
                mae.get("mae_body_median", 0),
                mae.get("mae_body_p75", 0),
                mae.get("mae_body_p90", 0),
                100 * mae.get("frac_mae_ge_032", 0),
                100 * mae.get("frac_mae_ge_050", 0),
                100 * mae.get("frac_mae_ge_072", 0),
            )
        )

        books: List[dict] = []
        books.append(book_row("close entry 3×body (base)", base))

        for ret in RETRACE_FRACS:
            _progress("retrace body %.0f%% ..." % (100 * ret))
            tr = walk_retrace_entry(df5, fh, ret_frac=ret, use_range=False)
            meta = dict(tr.attrs.get("meta") or {})
            tr.to_csv(hub / ("retrace_body_%02d.csv" % int(round(100 * ret))), index=False)
            books.append(
                book_row(
                    "retrace body %.0f%% → SL extreme → 3R" % (100 * ret),
                    tr,
                    meta=meta,
                )
            )
            _progress(
                "  fills=%d miss=%d WR=%.1f%% net=$%+.0f N/S=%.2f"
                % (
                    meta.get("n_fill", len(tr)),
                    meta.get("n_miss", 0),
                    100 * books[-1]["wr"],
                    books[-1]["net"],
                    books[-1]["ns"],
                )
            )

        # Range-based fib as secondary (same fracs)
        for ret in RETRACE_FRACS:
            _progress("retrace range %.0f%% ..." % (100 * ret))
            tr = walk_retrace_entry(df5, fh, ret_frac=ret, use_range=True)
            meta = dict(tr.attrs.get("meta") or {})
            tr.to_csv(hub / ("retrace_range_%02d.csv" % int(round(100 * ret))), index=False)
            books.append(
                book_row(
                    "retrace range %.0f%% → SL extreme → 3R" % (100 * ret),
                    tr,
                    meta=meta,
                )
            )

        write_summary(hub, mae, books)
        email = hub / "EMAIL.txt"
        body_lines = [
            "NQ first-hour MAE + retrace entries complete",
            "Hub: %s" % hub,
            "",
            "Base MAE (body): median=%.2f p75=%.2f p90=%.2f | ≥32/50/72=%.0f/%.0f/%.0f%%"
            % (
                mae.get("mae_body_median", 0),
                mae.get("mae_body_p75", 0),
                mae.get("mae_body_p90", 0),
                100 * mae.get("frac_mae_ge_032", 0),
                100 * mae.get("frac_mae_ge_050", 0),
                100 * mae.get("frac_mae_ge_072", 0),
            ),
            "",
        ]
        for b in books:
            fill = ""
            if b.get("fill_rate") is not None:
                fill = " fill=%.0f%%" % (100 * float(b["fill_rate"]))
            body_lines.append(
                "%s: n=%d%s WR=%.1f%% net=$%+.0f N/S=%.2f"
                % (b["label"], b["n"], fill, 100 * b["wr"], b["net"], b["ns"])
            )
        body_lines += ["", "Stance: diagnostic — rebuild broker-like before promote.", ""]
        email.write_text("\n".join(body_lines), encoding="utf-8")
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "mae": mae, "books": books}, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.email:
            send_email(
                subject="potions: NQ FH MAE + retrace entries complete",
                body=email.read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress("FAIL\n" + tb)
        fail = hub / "EMAIL_FAIL.txt"
        fail.write_text("NQ FH retrace FAILED\n%s\n" % tb, encoding="utf-8")
        try:
            send_email(subject="potions: NQ FH retrace FAILED", body=fail.read_text())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
