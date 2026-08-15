"""Winner path-MAE + percentile carry counterfactual for live OANDA books.

For each OANDA practice strategy research tape:
  1. Reconstruct path MAE (and MFE) on platform 1m bars between entry→exit.
  2. Summarize winner MAE (mean / median / p80 / p85 / p90 / p95).
  3. Counterfactual: stop at **pXX winner MAE** instead of the hard stop —
     any path that touches that adverse level is flattened at -pXX MAE pts;
     paths that never touch it keep their original PnL.

Sweep percentiles **80 / 85 / 90 / 95**. If any carry book is favorable vs
baseline hard-stop, recommend the best Δnet among favorables (tie-break:
lower percentile = tighter guard). Risk-guard daemon can overlay that thr.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.oanda_winner_mae_carry --email
  python -m live.oanda_winner_mae_carry --demo us30_hourly_st_pmc_sl50_tp150_3r_oanda
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass, fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email

HUB = REPO / "live" / "state" / "oanda_winner_mae_carry"
THRESHOLDS_CSV = REPO / "live" / "demo" / "oanda_practice_snapshot" / "strategy_avg_loss_mae_proxy.csv"
FX_DIR = REPO / "fx"

# Guard stop = this percentile of winning-trade path MAE.
CARRY_PERCENTILES: Tuple[int, ...] = (80, 85, 90, 95)

INSTRUMENT_1M = {
    "US30": FX_DIR / "us30_1m.csv",
    "NAS100": FX_DIR / "nas100_1m.csv",
    "EURUSD": FX_DIR / "eurusd_1m.csv",
    "USDJPY": FX_DIR / "usdjpy_1m.csv",
    "AUDJPY": FX_DIR / "audjpy_1m.csv",
    "XAUUSD": FX_DIR / "xauusd_1m.csv",
    "XAGUSD": FX_DIR / "xagusd_1m.csv",
    "GBPUSD": FX_DIR / "gbpusd_1m.csv",
}


@dataclass
class BookResult:
    demo: str
    instrument: str
    strategy_type: str
    tape: str
    n_units: int
    n_wins: int
    n_losses: int
    n_mae_ok: int
    avg_loss_usd: float
    winner_mae_mean_pts: float
    winner_mae_median_pts: float
    winner_mae_p80_pts: float
    winner_mae_p85_pts: float
    winner_mae_p90_pts: float
    winner_mae_p95_pts: float
    loser_mae_mean_pts: float
    baseline_net_usd: float
    baseline_pf: float
    p80_carry_net_usd: float
    p80_carry_pf: float
    p80_vs_baseline_net: float
    p80_favorable: bool
    p85_carry_net_usd: float
    p85_carry_pf: float
    p85_vs_baseline_net: float
    p85_favorable: bool
    p90_carry_net_usd: float
    p90_carry_pf: float
    p90_vs_baseline_net: float
    p90_favorable: bool
    p95_carry_net_usd: float
    p95_carry_pf: float
    p95_vs_baseline_net: float
    p95_favorable: bool
    favorable_for_daemon: bool
    recommended_threshold: str
    recommended_pct: int
    recommended_delta_net: float
    note: str = ""


def _utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _progress(msg: str) -> None:
    line = "[%s] %s" % (_utc(), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _pf(wins: float, losses_abs: float) -> float:
    if losses_abs <= 1e-12:
        return float("inf") if wins > 0 else 0.0
    return float(wins / losses_abs)


_BAR_CACHE: Dict[str, pd.DataFrame] = {}


def bars_for(instrument: str) -> pd.DataFrame:
    if instrument in _BAR_CACHE:
        return _BAR_CACHE[instrument]
    path = INSTRUMENT_1M.get(instrument)
    if path is None or not path.exists():
        raise FileNotFoundError("no 1m archive for %s (%s)" % (instrument, path))
    _progress("loading_bars %s %s" % (instrument, path.name))
    df = pd.read_csv(path, usecols=lambda c: c in {"ts_event", "open", "high", "low", "close", "symbol"})
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == instrument.upper()]
    df["ts"] = pd.to_datetime(df["ts_event"], utc=True)
    df = df.sort_values("ts").set_index("ts")
    out = df[["open", "high", "low", "close"]]
    _BAR_CACHE[instrument] = out
    return out


def _side_is_long(direction: object) -> bool:
    d = str(direction or "").strip().lower()
    return d.startswith("l") or d in {"buy", "+"}


def path_mae_mfe(
    bars: pd.DataFrame,
    *,
    entry_ts: pd.Timestamp,
    exit_ts: pd.Timestamp,
    entry_price: float,
    is_long: bool,
) -> Tuple[float, float, int]:
    if pd.isna(entry_ts) or pd.isna(exit_ts):
        return float("nan"), float("nan"), 0
    sl = bars.loc[(bars.index >= entry_ts) & (bars.index <= exit_ts)]
    if sl.empty:
        sl = bars.loc[(bars.index > entry_ts) & (bars.index <= exit_ts)]
    if sl.empty:
        return float("nan"), float("nan"), 0
    hi = sl["high"].to_numpy(dtype=float)
    lo = sl["low"].to_numpy(dtype=float)
    if is_long:
        mae = float(max(0.0, entry_price - float(np.min(lo))))
        mfe = float(max(0.0, float(np.max(hi)) - entry_price))
    else:
        mae = float(max(0.0, float(np.max(hi)) - entry_price))
        mfe = float(max(0.0, entry_price - float(np.min(lo))))
    return mae, mfe, int(len(sl))


def _pnl_col(df: pd.DataFrame) -> str:
    if "usd" in df.columns:
        return "usd"
    if "net_usd" in df.columns:
        return "net_usd"
    raise KeyError("no usd/net_usd column")


def _nan_carry() -> Dict[str, object]:
    out: Dict[str, object] = {}
    for pct in CARRY_PERCENTILES:
        out["winner_mae_p%d_pts" % pct] = float("nan")
        out["p%d_carry_net_usd" % pct] = float("nan")
        out["p%d_carry_pf" % pct] = float("nan")
        out["p%d_vs_baseline_net" % pct] = float("nan")
        out["p%d_favorable" % pct] = False
    return out


def _empty_result(row: pd.Series, note: str) -> BookResult:
    base = dict(
        demo=str(row["demo"]),
        instrument=str(row.get("instrument") or ""),
        strategy_type=str(row.get("strategy_type") or ""),
        tape=str(row.get("tape") or ""),
        n_units=0,
        n_wins=0,
        n_losses=0,
        n_mae_ok=0,
        avg_loss_usd=float(row.get("avg_loss_unit_usd") or 0),
        winner_mae_mean_pts=float("nan"),
        winner_mae_median_pts=float("nan"),
        loser_mae_mean_pts=float("nan"),
        baseline_net_usd=float("nan"),
        baseline_pf=float("nan"),
        favorable_for_daemon=False,
        recommended_threshold="avg_loss",
        recommended_pct=0,
        recommended_delta_net=float("nan"),
        note=note,
    )
    base.update(_nan_carry())
    return BookResult(**base)  # type: ignore[arg-type]


def _counterfactual_pnl(
    df: pd.DataFrame,
    *,
    pnl_c: str,
    stop_pts: float,
    dpp_med: float,
) -> pd.Series:
    cf_vals: List[float] = []
    for _, tr in df.iterrows():
        mae = float(tr["mae_pts"]) if tr["mae_pts"] == tr["mae_pts"] else float("nan")
        orig = float(tr[pnl_c])
        if not (mae == mae):
            cf_vals.append(orig)
            continue
        if mae >= stop_pts - 1e-12:
            cf_vals.append(-stop_pts * dpp_med)
        else:
            cf_vals.append(orig)
    return pd.Series(cf_vals, index=df.index)


def _is_favorable(
    *,
    cf_net: float,
    baseline_net: float,
    cf_pf: float,
    baseline_pf: float,
    n_mae_ok: int,
) -> bool:
    delta_pf = (cf_pf - baseline_pf) if np.isfinite(cf_pf) and np.isfinite(baseline_pf) else float("nan")
    return bool((cf_net > baseline_net) and (not np.isfinite(delta_pf) or delta_pf >= -0.05) and n_mae_ok >= 50)


def analyze_book(row: pd.Series) -> Tuple[BookResult, pd.DataFrame]:
    demo = str(row["demo"])
    instrument = str(row.get("instrument") or "")
    strategy_type = str(row.get("strategy_type") or "")
    tape_rel = str(row.get("tape") or "")
    tape = REPO / "live" / "state" / tape_rel
    note = ""
    if not tape.exists():
        return _empty_result(row, "missing_tape"), pd.DataFrame()

    df = pd.read_csv(tape)
    pnl_c = _pnl_col(df)
    df[pnl_c] = df[pnl_c].astype(float)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    df["exit_ts"] = pd.to_datetime(df["exit_ts"], utc=True)
    df["entry_price"] = df["entry_price"].astype(float)
    df["is_long"] = df["direction"].map(_side_is_long)
    df["is_win"] = df[pnl_c] > 0
    df["is_loss"] = df[pnl_c] < 0

    if "points" in df.columns:
        pts = df["points"].astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            dpp = (df[pnl_c] / pts).replace([np.inf, -np.inf], np.nan).abs()
        dpp_med = float(dpp.replace(0, np.nan).median()) if dpp.notna().any() else float("nan")
    else:
        dpp_med = float("nan")
    if not (dpp_med == dpp_med) or dpp_med <= 0:
        move = (df["exit_price"].astype(float) - df["entry_price"]).abs().replace(0, np.nan)
        dpp_med = float((df[pnl_c].abs() / move).median()) if move.notna().any() else 1.0

    bars = bars_for(instrument)
    maes: List[float] = []
    mfes: List[float] = []
    nbars: List[int] = []
    for _, tr in df.iterrows():
        mae, mfe, n = path_mae_mfe(
            bars,
            entry_ts=tr["entry_ts"],
            exit_ts=tr["exit_ts"],
            entry_price=float(tr["entry_price"]),
            is_long=bool(tr["is_long"]),
        )
        maes.append(mae)
        mfes.append(mfe)
        nbars.append(n)
    df["mae_pts"] = maes
    df["mfe_pts"] = mfes
    df["mae_bars"] = nbars
    ok = df["mae_pts"].notna()
    n_mae_ok = int(ok.sum())
    if n_mae_ok == 0:
        note = "no_mae_paths"

    wins = df[df["is_win"] & ok]
    losses = df[df["is_loss"] & ok]
    w_mae = wins["mae_pts"].astype(float)
    l_mae = losses["mae_pts"].astype(float)

    def _q(s: pd.Series, q: float) -> float:
        return float(s.quantile(q)) if len(s) else float("nan")

    w_mean = float(w_mae.mean()) if len(w_mae) else float("nan")
    w_med = float(w_mae.median()) if len(w_mae) else float("nan")
    l_mean = float(l_mae.mean()) if len(l_mae) else float("nan")

    baseline_net = float(df[pnl_c].sum())
    base_wins = float(df.loc[df[pnl_c] > 0, pnl_c].sum())
    base_loss_abs = float((-df.loc[df[pnl_c] < 0, pnl_c]).sum())
    baseline_pf = _pf(base_wins, base_loss_abs)

    carry: Dict[str, object] = {}
    best_pct = 0
    best_delta = float("-inf")
    any_fav = False

    for pct in CARRY_PERCENTILES:
        stop_pts = _q(w_mae, pct / 100.0)
        carry["winner_mae_p%d_pts" % pct] = stop_pts
        if not (stop_pts == stop_pts) or stop_pts <= 0:
            cf = df[pnl_c].copy()
            note = (note + "; " if note else "") + "p%d_unavailable" % pct
            cf_net = float(cf.sum())
            cf_pf = baseline_pf
            delta_net = 0.0
            fav = False
        else:
            cf = _counterfactual_pnl(df, pnl_c=pnl_c, stop_pts=float(stop_pts), dpp_med=dpp_med)
            cf_net = float(cf.sum())
            cf_wins = float(cf[cf > 0].sum())
            cf_loss_abs = float((-cf[cf < 0]).sum())
            cf_pf = _pf(cf_wins, cf_loss_abs)
            delta_net = cf_net - baseline_net
            fav = _is_favorable(
                cf_net=cf_net,
                baseline_net=baseline_net,
                cf_pf=cf_pf,
                baseline_pf=baseline_pf,
                n_mae_ok=n_mae_ok,
            )
        df["cf_p%d_usd" % pct] = cf
        carry["p%d_carry_net_usd" % pct] = cf_net
        carry["p%d_carry_pf" % pct] = cf_pf
        carry["p%d_vs_baseline_net" % pct] = delta_net
        carry["p%d_favorable" % pct] = fav
        if fav:
            any_fav = True
            # Prefer higher Δnet; tie-break lower percentile (tighter guard).
            if delta_net > best_delta + 1e-9 or (
                abs(delta_net - best_delta) <= 1e-9 and (best_pct == 0 or pct < best_pct)
            ):
                best_delta = float(delta_net)
                best_pct = pct

    recommended = "p%d_winner_mae" % best_pct if any_fav and best_pct else "avg_loss"

    result = BookResult(
        demo=demo,
        instrument=instrument,
        strategy_type=strategy_type,
        tape=tape_rel,
        n_units=int(len(df)),
        n_wins=int(df["is_win"].sum()),
        n_losses=int(df["is_loss"].sum()),
        n_mae_ok=n_mae_ok,
        avg_loss_usd=float(row.get("avg_loss_unit_usd") or 0),
        winner_mae_mean_pts=w_mean,
        winner_mae_median_pts=w_med,
        loser_mae_mean_pts=l_mean,
        baseline_net_usd=baseline_net,
        baseline_pf=baseline_pf,
        favorable_for_daemon=any_fav,
        recommended_threshold=recommended,
        recommended_pct=int(best_pct) if any_fav else 0,
        recommended_delta_net=float(best_delta) if any_fav else float("nan"),
        note=note,
        **carry,  # type: ignore[arg-type]
    )
    return result, df


def build_email(results: List[BookResult]) -> Tuple[str, str]:
    fav = [r for r in results if r.favorable_for_daemon]
    text = [
        "potions: OANDA winner MAE + percentile carry (p80/85/90/95)",
        "hub: live/state/oanda_winner_mae_carry/",
        "books: %d · favorable (any pct): %d" % (len(results), len(fav)),
        "daemon stays on avg_loss unless recommended_threshold=pXX_winner_mae",
        "",
    ]
    for r in results:
        bits = []
        for pct in CARRY_PERCENTILES:
            d = getattr(r, "p%d_vs_baseline_net" % pct)
            mark = "Y" if getattr(r, "p%d_favorable" % pct) else "n"
            bits.append("p%d Δ=$%.0f(%s)" % (pct, d if d == d else 0, mark))
        text.append(
            "%s | winMAE med/p80/p95=%.3f/%.3f/%.3f | base=$%.0f | %s | thr=%s"
            % (
                r.demo,
                r.winner_mae_median_pts,
                r.winner_mae_p80_pts,
                r.winner_mae_p95_pts,
                r.baseline_net_usd,
                " ".join(bits),
                r.recommended_threshold,
            )
        )
    body = "\n".join(text)

    rows = []
    for r in results:
        cells = [
            r.demo,
            r.instrument,
            str(r.n_mae_ok),
            "%.2f" % r.winner_mae_median_pts,
        ]
        for pct in CARRY_PERCENTILES:
            cells.append("%.3f" % getattr(r, "winner_mae_p%d_pts" % pct))
        cells.append("%.0f" % r.baseline_net_usd)
        for pct in CARRY_PERCENTILES:
            d = getattr(r, "p%d_vs_baseline_net" % pct)
            cells.append("%.0f" % (d if d == d else float("nan")))
            cells.append("Y" if getattr(r, "p%d_favorable" % pct) else "n")
        cells.append(r.recommended_threshold)
        cells.append("YES" if r.favorable_for_daemon else "no")
        rows.append("<tr>" + "".join("<td>%s</td>" % c for c in cells) + "</tr>")

    pct_headers = "".join("<th>p%d</th><th>Δ%d</th><th>fav%d</th>" % (p, p, p) for p in CARRY_PERCENTILES)
    # Actually cleaner: winMAE pts then Δ columns
    head_pts = "".join("<th>winMAE p%d</th>" % p for p in CARRY_PERCENTILES)
    head_delta = "".join("<th>Δp%d</th><th>fav</th>" % p for p in CARRY_PERCENTILES)
    html = """<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;line-height:1.4;color:#222">
<h2>Winner MAE + percentile carry (p80 / p85 / p90 / p95)</h2>
<p>Hub: <code>live/state/oanda_winner_mae_carry/</code></p>
<p>Books: <b>%d</b> · Favorable at any percentile: <b>%d</b></p>
<p>Counterfactual: flatten at <b>pXX winner MAE</b> whenever path MAE reaches that level;
otherwise keep original unit PnL. Recommend best Δnet among favorables (tie → tighter pct).</p>
<table cellpadding="5" cellspacing="0" border="1" style="border-collapse:collapse;font-size:11px">
<thead><tr>
<th>demo</th><th>inst</th><th>n_mae</th><th>med</th>
%s
<th>base net</th>
%s
<th>daemon thr</th><th>favor</th>
</tr></thead>
<tbody>
%s
</tbody></table>
</body></html>""" % (
        len(results),
        len(fav),
        head_pts,
        head_delta,
        "\n".join(rows),
    )
    # silence unused (pct_headers kept out of template intentionally)
    _ = pct_headers
    return body, html


def run(demos: Optional[Sequence[str]] = None, *, email: bool = False) -> int:
    HUB.mkdir(parents=True, exist_ok=True)
    meta = pd.read_csv(THRESHOLDS_CSV)
    if demos:
        want = set(demos)
        meta = meta[meta["demo"].astype(str).isin(want)].copy()
    results: List[BookResult] = []
    detail_dir = HUB / "per_book"
    detail_dir.mkdir(parents=True, exist_ok=True)

    for _, row in meta.iterrows():
        demo = str(row["demo"])
        _progress("start %s" % demo)
        try:
            result, detail = analyze_book(row)
            results.append(result)
            if not detail.empty:
                keep = [
                    c
                    for c in [
                        "trade_id",
                        "unit_id",
                        "direction",
                        "entry_ts",
                        "exit_ts",
                        "entry_price",
                        "exit_price",
                        "exit_reason",
                        "points",
                        "usd",
                        "net_usd",
                        "mae_pts",
                        "mfe_pts",
                        "mae_bars",
                    ]
                    + ["cf_p%d_usd" % p for p in CARRY_PERCENTILES]
                    if c in detail.columns
                ]
                detail[keep].to_csv(detail_dir / ("%s_units.csv" % demo), index=False)
            _progress(
                "done %s n=%d thr=%s Δbest=%.0f fav_any=%s"
                % (
                    demo,
                    result.n_mae_ok,
                    result.recommended_threshold,
                    result.recommended_delta_net if result.recommended_delta_net == result.recommended_delta_net else 0,
                    result.favorable_for_daemon,
                )
            )
        except Exception:
            tb = traceback.format_exc()
            _progress("FAIL %s\n%s" % (demo, tb[-2500:]))
            results.append(_empty_result(row, "exception"))

    out = pd.DataFrame([asdict(r) for r in results])
    out.to_csv(HUB / "summary.csv", index=False)
    (HUB / "SUMMARY.json").write_text(
        json.dumps([asdict(r) for r in results], indent=2, default=str),
        encoding="utf-8",
    )

    fav = [r for r in results if r.favorable_for_daemon]
    md = [
        "# OANDA winner MAE + percentile carry (p80/85/90/95)",
        "",
        "Generated: `%s`" % _utc(),
        "",
        "Counterfactual stop = **pXX of winning-trade path MAE**. Sweep **80 / 85 / 90 / 95**.",
        "Daemon stays on avg loss unless a percentile is favorable; recommend best Δnet (tie → tighter).",
        "",
        "| demo | inst | p80 | Δ80 | p85 | Δ85 | p90 | Δ90 | p95 | Δ95 | thr | favor |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in results:
        cells = [r.demo, r.instrument]
        for pct in CARRY_PERCENTILES:
            pts = getattr(r, "winner_mae_p%d_pts" % pct)
            d = getattr(r, "p%d_vs_baseline_net" % pct)
            cells.append("%.3f" % (pts if pts == pts else float("nan")))
            cells.append("%.0f" % (d if d == d else float("nan")))
        cells.append(r.recommended_threshold)
        cells.append("YES" if r.favorable_for_daemon else "no")
        md.append("| %s |" % " | ".join(cells))

    md.extend(
        [
            "",
            "Favorable books (any pct): **%d / %d**" % (len(fav), len(results)),
            "",
            "## Favorable detail",
            "",
        ]
    )
    if not fav:
        md.append("_None — keep avg_loss thresholds._")
    else:
        md.append("| demo | recommended | Δnet |")
        md.append("|---|---|---:|")
        for r in fav:
            md.append(
                "| %s | %s | %.0f |"
                % (r.demo, r.recommended_threshold, r.recommended_delta_net)
            )
    md.append("")
    (HUB / "SUMMARY.md").write_text("\n".join(md), encoding="utf-8")
    (HUB / "PERCENTILE_SWEEP.md").write_text("\n".join(md), encoding="utf-8")

    body, html = build_email(results)
    (HUB / "EMAIL.txt").write_text(body, encoding="utf-8")
    (HUB / "EMAIL.html").write_text(html, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(
        json.dumps(
            {
                "finished_at": _utc(),
                "n_books": len(results),
                "n_favorable": len(fav),
                "percentiles": list(CARRY_PERCENTILES),
                "hub": str(HUB),
                "field_names": [f.name for f in fields(BookResult)],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    if email:
        send_email(
            subject="potions: winner MAE pct sweep p80/85/90/95 (%d books, %d favorable)"
            % (len(results), len(fav)),
            body=body,
            html=html,
        )
        _progress("email_sent")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--demo", action="append", default=None, help="Limit to demo folder name (repeatable)")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)
    try:
        return run(args.demo, email=args.email)
    except Exception:
        tb = traceback.format_exc()
        _progress("FATAL\n%s" % tb)
        if args.email:
            send_email(
                subject="potions: winner MAE percentile sweep FAILED",
                body=tb[-4000:],
                html="<pre>%s</pre>" % tb[-4000:],
            )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
