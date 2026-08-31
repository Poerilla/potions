"""Cross-market quarterly range honest breakout + prior-width Q4_large study.

Baseline: daily close outside prior-quarter H/L, mid SL, 8@entry + 2@0.2W ladder.
Post-run: prior-width quartiles (Q4_large) on the broker tape — same framing as
NQ/ES prior_width_study hubs.

Markets: FX (EURUSD, GBPUSD, USDJPY, AUDJPY), metals (XAUUSD, XAGUSD),
index CFDs (US30, NAS100).

Hub: ``live/state/quarterly_range_breakout_fx_metals_cfd/``

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.quarterly_range_breakout_fx_metals_cfd --email
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import quarterly_range_breakout_broker as qrb
from .notify_email import send_email
from .replay_audit import POINT_VALUES

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "quarterly_range_breakout_fx_metals_cfd"
ENTRY_QTY = qrb.ENTRY_QTY
FEE_DEFAULT = qrb.FEE


@dataclass(frozen=True)
class MarketSpec:
    symbol: str
    daily: Path
    point_value: float
    tick: float
    fee: float
    family: str  # fx | metal | cfd


def _spec(
    symbol: str,
    daily: str,
    point_value: float,
    tick: float,
    fee: float,
    family: str,
) -> MarketSpec:
    return MarketSpec(
        symbol=symbol,
        daily=REPO / daily,
        point_value=float(point_value),
        tick=float(tick),
        fee=float(fee),
        family=family,
    )


MARKETS: Dict[str, MarketSpec] = {
    "EURUSD": _spec("EURUSD", "fx/eurusd_daily.csv", 100_000.0, 0.00001, 1.50, "fx"),
    "GBPUSD": _spec("GBPUSD", "fx/gbpusd_daily.csv", 100_000.0, 0.00001, 7.0, "fx"),
    "USDJPY": _spec("USDJPY", "fx/usdjpy_daily.csv", 100_000.0, 0.001, 1.50, "fx"),
    "AUDJPY": _spec("AUDJPY", "fx/audjpy_daily.csv", 100_000.0, 0.001, 1.50, "fx"),
    "XAUUSD": _spec("XAUUSD", "fx/xauusd_daily.csv", 100.0, 0.01, 1.50, "metal"),
    "XAGUSD": _spec("XAGUSD", "fx/xagusd_daily.csv", 1000.0, 0.001, 1.50, "metal"),
    "US30": _spec("US30", "fx/us30_daily.csv", 1.0, 0.1, 1.50, "cfd"),
    "NAS100": _spec("NAS100", "fx/nas100_daily.csv", 1.0, 0.1, 1.50, "cfd"),
}

FX_SYMBOLS = [s for s, m in MARKETS.items() if m.family == "fx"]
METAL_SYMBOLS = [s for s, m in MARKETS.items() if m.family == "metal"]
CFD_SYMBOLS = [s for s, m in MARKETS.items() if m.family == "cfd"]


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _findcol(df: pd.DataFrame, *names: str) -> str:
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    raise KeyError(names)


def _spearman(x: pd.Series, y: pd.Series) -> Tuple[float, float]:
    xv = pd.to_numeric(x, errors="coerce")
    yv = pd.to_numeric(y, errors="coerce")
    mask = xv.notna() & yv.notna()
    if mask.sum() < 3:
        return float("nan"), float("nan")
    rx = xv[mask].rank()
    ry = yv[mask].rank()
    rho = float(np.corrcoef(rx, ry)[0, 1])
    n = int(mask.sum())
    if n < 3:
        return rho, float("nan")
    t = rho * np.sqrt((n - 2) / max(1e-12, 1 - rho * rho))
    from math import erfc, sqrt

    p = float(erfc(abs(t) / sqrt(2)))
    return rho, p


def _pctile_of_score(arr: np.ndarray, x: float) -> float:
    arr = np.asarray(arr, dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return float("nan")
    return float(100.0 * (arr <= x).sum() / len(arr))


def market_hub(root: Path, symbol: str) -> Path:
    return root / symbol.lower()


def strategy_id(symbol: str) -> str:
    return "%s_quarterly_range_breakout" % symbol.lower()


def _register_spec(m: MarketSpec) -> None:
    qrb._SPEC[m.symbol] = {"pv": m.point_value, "tick": m.tick}
    POINT_VALUES[m.symbol] = m.point_value


def run_broker(
    root: Path,
    m: MarketSpec,
    *,
    force: bool,
    slippage_ticks: float,
) -> Dict[str, object]:
    out = market_hub(root, m.symbol)
    _register_spec(m)
    qrb.run(
        output_root=out,
        daily_path=m.daily,
        instrument=m.symbol,
        force=force,
        slippage_ticks=slippage_ticks,
        email=False,
        entry_qty=ENTRY_QTY,
    )
    summary_path = out / "summary.csv"
    if not summary_path.exists():
        raise FileNotFoundError("Missing summary after replay: %s" % summary_path)
    with summary_path.open(encoding="utf-8") as fh:
        row = next(csv.DictReader(fh))
    return dict(row)


def prior_width_study(
    m: MarketSpec,
    broker_hub: Path,
) -> Dict[str, object]:
    sid = strategy_id(m.symbol)
    fills_path = broker_hub / "states" / sid / "fills.csv"
    bars_path = broker_hub / "states" / sid / "bars" / ("%s_D.csv" % m.symbol)
    out = broker_hub / "prior_width_study"
    out.mkdir(parents=True, exist_ok=True)

    if not fills_path.exists():
        raise FileNotFoundError(fills_path)
    if not bars_path.exists():
        raise FileNotFoundError(bars_path)

    pv, fee = m.point_value, m.fee
    fills = pd.read_csv(fills_path)
    fills["ts"] = pd.to_datetime(fills["ts"]).dt.tz_localize(None)
    fills = fills.sort_values("ts")

    daily = pd.read_csv(bars_path)
    tc = _findcol(daily, "ts", "time", "date", "datetime")
    daily["ts"] = pd.to_datetime(daily[tc]).dt.tz_localize(None)
    for name in ("open", "high", "low", "close"):
        daily[name] = daily[_findcol(daily, name)].astype(float)
    daily = daily.sort_values("ts").reset_index(drop=True)
    daily["qkey"] = (
        daily["ts"].dt.year.astype(str)
        + "Q"
        + (((daily["ts"].dt.month - 1) // 3) + 1).astype(str)
    )

    q_stats = (
        daily.groupby("qkey")
        .agg(q_high=("high", "max"), q_low=("low", "min"), q_start=("ts", "min"))
        .reset_index()
        .sort_values("q_start")
    )
    q_stats["prior_high"] = q_stats["q_high"].shift(1)
    q_stats["prior_low"] = q_stats["q_low"].shift(1)
    q_stats["prior_width"] = q_stats["prior_high"] - q_stats["prior_low"]
    q_stats["prior_mid"] = (q_stats["prior_high"] + q_stats["prior_low"]) / 2
    prior_map = q_stats.set_index("qkey")
    all_widths = q_stats["prior_width"].dropna()

    campaigns: List[Dict[str, object]] = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        er = g[g["reason"] == "entry"]
        if er.empty:
            continue
        er0 = er.iloc[0]
        side = "long" if str(er0["side"]).lower() == "buy" else "short"
        entry_ts = er0["ts"]
        prev = daily[daily["ts"] < entry_ts]
        if prev.empty:
            continue
        qk = prev.iloc[-1]["qkey"]
        if qk not in prior_map.index:
            continue
        pr = prior_map.loc[qk]
        width = float(pr["prior_width"])
        if not np.isfinite(width) or width <= 0:
            continue

        lots: List[List[float]] = []
        realized = 0.0
        fees = 0.0
        exit_reasons: List[str] = []
        for _, r in g.iterrows():
            reason = str(r["reason"])
            px = float(r["price"])
            qty = int(r["quantity"])
            is_buy = str(r["side"]).lower() == "buy"
            fees += fee * qty
            if side == "long":
                if is_buy:
                    lots.append([qty, px])
                    continue
                left = qty
                pnl = 0.0
                while left > 0 and lots:
                    q0, p0 = lots[0]
                    take = min(q0, left)
                    pnl += (px - p0) * take * pv
                    q0 -= take
                    left -= take
                    if q0 == 0:
                        lots.pop(0)
                    else:
                        lots[0][0] = q0
                realized += pnl
                if reason != "entry":
                    exit_reasons.append(reason)
            else:
                if not is_buy:
                    lots.append([qty, px])
                    continue
                left = qty
                pnl = 0.0
                while left > 0 and lots:
                    q0, p0 = lots[0]
                    take = min(q0, left)
                    pnl += (p0 - px) * take * pv
                    q0 -= take
                    left -= take
                    if q0 == 0:
                        lots.pop(0)
                    else:
                        lots[0][0] = q0
                realized += pnl
                if reason != "entry":
                    exit_reasons.append(reason)

        net = realized - fees
        known = q_stats[q_stats["q_start"] < prior_map.loc[qk, "q_start"]]["prior_width"].dropna()
        pct_causal = _pctile_of_score(known.values, width) if len(known) >= 4 else float("nan")
        pct_full = _pctile_of_score(all_widths.values, width)
        campaigns.append(
            {
                "trade_id": trade_id,
                "entry_ts": entry_ts,
                "side": side,
                "year": int(entry_ts.year),
                "qkey": qk,
                "prior_width": width,
                "prior_mid": float(pr["prior_mid"]),
                "width_pct_fullsample": pct_full,
                "width_pct_causal": pct_causal,
                "net_usd": net,
                "win": int(net > 0),
                "hit_stop": int("stop" in exit_reasons),
                "exit_mix": "|".join(exit_reasons),
            }
        )

    cdf = pd.DataFrame(campaigns)
    cdf.to_csv(out / "campaigns_with_width.csv", index=False)
    if cdf.empty:
        summary = {"n_trades": 0, "baseline_net": 0.0, "note": "no campaigns"}
        (out / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        (out / "SUMMARY.md").write_text(
            "# %s prior width\n\nNo campaigns on tape.\n" % m.symbol,
            encoding="utf-8",
        )
        return summary

    if len(cdf) >= 4:
        cdf["width_q"] = pd.qcut(
            cdf["prior_width"], 4, labels=["Q1_small", "Q2", "Q3", "Q4_large"]
        )
    else:
        cdf["width_q"] = "all"

    def summarize(g: pd.DataFrame) -> pd.Series:
        full_stop_risk = ENTRY_QTY * (g["prior_width"] / 2.0) * pv
        r_mult = g["net_usd"] / full_stop_risk.replace(0, np.nan)
        return pd.Series(
            {
                "n": len(g),
                "win_rate": float((g["net_usd"] > 0).mean()),
                "net": float(g["net_usd"].sum()),
                "avg_net": float(g["net_usd"].mean()),
                "avg_R": float(r_mult.mean()),
                "stop_rate": float(g["hit_stop"].mean()),
                "loss_n": int((g["net_usd"] <= 0).sum()),
                "loss_usd": float(g.loc[g["net_usd"] <= 0, "net_usd"].sum()),
                "w_min": float(g["prior_width"].min()),
                "w_max": float(g["prior_width"].max()),
                "w_med": float(g["prior_width"].median()),
            }
        )

    by_q = cdf.groupby("width_q", observed=True).apply(summarize).reset_index()
    by_q.to_csv(out / "by_width_quartile.csv", index=False)

    loss_df = cdf[cdf["net_usd"] <= 0]
    win_df = cdf[cdf["net_usd"] > 0]
    total_loss = float(loss_df["net_usd"].sum()) if len(loss_df) else 0.0
    if len(loss_df) and "loss_usd" not in by_q.columns:
        pass
    if len(loss_df):
        by_q["loss_share"] = by_q.apply(
            lambda r: (
                float(r["loss_usd"]) / total_loss
                if total_loss != 0 and pd.notna(r.get("loss_usd"))
                else 0.0
            ),
            axis=1,
        )

    spear = _spearman(cdf["prior_width"], cdf["net_usd"])
    q4 = cdf[cdf["width_q"] == "Q4_large"] if "Q4_large" in cdf["width_q"].astype(str).values else cdf.iloc[0:0]
    non_q4 = cdf[cdf["width_q"] != "Q4_large"] if len(q4) else cdf
    q4_net = float(q4["net_usd"].sum()) if len(q4) else 0.0
    non_q4_net = float(non_q4["net_usd"].sum()) if len(non_q4) else float(cdf["net_usd"].sum())
    skip_q4_delta = float(non_q4_net - cdf["net_usd"].sum())

    width_dist = {
        "p50": float(cdf["prior_width"].quantile(0.50)),
        "p75": float(cdf["prior_width"].quantile(0.75)),
        "p90": float(cdf["prior_width"].quantile(0.90)),
    }
    q4_bounds = (
        [float(q4["prior_width"].min()), float(q4["prior_width"].max())]
        if len(q4)
        else [float("nan"), float("nan")]
    )

    summary = {
        "n_trades": int(len(cdf)),
        "baseline_net": float(cdf["net_usd"].sum()),
        "spearman_width_vs_net": {"rho": spear[0], "pvalue_approx": spear[1]},
        "width_dist_at_trades": width_dist,
        "q4_large_range": q4_bounds,
        "q4_large": {
            "n": int(len(q4)),
            "win_rate": float((q4["net_usd"] > 0).mean()) if len(q4) else None,
            "net": q4_net,
            "loss_share": float(
                loss_df[loss_df["width_q"] == "Q4_large"]["net_usd"].sum() / total_loss
            )
            if len(loss_df) and len(q4)
            else None,
        },
        "skip_q4_keeps_net": non_q4_net,
        "skip_q4_delta_vs_baseline": skip_q4_delta,
        "by_quartile": by_q.to_dict("records"),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")
    loss_df.sort_values("net_usd").to_csv(out / "losers_ranked.csv", index=False)

    lines = [
        "# %s prior width vs losses" % m.symbol,
        "",
        "%s quarterly honest breakout (mid SL): prior-range width vs outcomes."
        % m.symbol,
        "",
        "Hub: `%s`" % out.relative_to(REPO),
        "",
        "What is large? Trade-sample p50=%.4g, p75=%.4g, p90=%.4g."
        % (width_dist["p50"], width_dist["p75"], width_dist["p90"]),
    ]
    if len(q4):
        lines.append(
            "Q4_large ~= W in [%.4g, %.4g] (%d trades, WR %.0f%%, net $%.0f)."
            % (
                q4_bounds[0],
                q4_bounds[1],
                len(q4),
                100 * float((q4["net_usd"] > 0).mean()),
                q4_net,
            )
        )
    lines.extend(
        [
            "",
            "Skip Q4 counterfactual: keep $%.0f (delta $%.0f vs baseline $%.0f)."
            % (non_q4_net, skip_q4_delta, float(cdf["net_usd"].sum())),
            "",
            "Spearman width↔net: rho=%.2f" % (spear[0] if np.isfinite(spear[0]) else 0.0),
            "",
            "## By width quartile",
            "",
            by_q.to_string(index=False),
            "",
        ]
    )
    if m.symbol == "USDJPY":
        lines.append(
            "_Note: USDJPY P&L uses repo POINT_VALUES convention (JPY per 1.0 move); "
            "cross-market $ ranks are indicative._"
        )
    (out / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
    return summary


def _write_cross_summary(root: Path, rows: List[Dict[str, object]]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with (root / "cross_market_summary.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    md = [
        "# Quarterly range breakout — FX / metals / CFDs",
        "",
        "Baseline: daily close outside prior-quarter H/L → market **8**; "
        "**SL = prior mid**; scale **2** @ 0.2× prior width; EOQ flatten.",
        "",
        "Prior-width **Q4_large** = top quartile of prior width on the trade tape.",
        "",
        "| Symbol | Family | Trades | Baseline net | N/S | Q4 n | Q4 net | Skip-Q4 Δ | ρ(W,net) |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        md.append(
            "| {symbol} | {family} | {trades} | ${baseline_net:,.0f} | {ns:.2f} | "
            "{q4_n} | ${q4_net:,.0f} | ${skip_q4_delta:,.0f} | {rho:.2f} |".format(
                symbol=r["symbol"],
                family=r["family"],
                trades=r["trades"],
                baseline_net=float(r["baseline_net"]),
                ns=float(r["ns"]),
                q4_n=r["q4_n"],
                q4_net=float(r["q4_net"]),
                skip_q4_delta=float(r["skip_q4_delta"]),
                rho=float(r["width_net_rho"]) if r["width_net_rho"] == r["width_net_rho"] else 0.0,
            )
        )
    md.extend(["", "Per-market hubs under this directory.", ""])
    (root / "SUMMARY.md").write_text("\n".join(md), encoding="utf-8")


def run_all(
    *,
    symbols: Sequence[str],
    force: bool,
    slippage_ticks: float,
    email: bool,
    skip_replay: bool,
) -> int:
    root = HUB
    root.mkdir(parents=True, exist_ok=True)
    _progress(root, "START quarterly breakout FX/metals/CFD cross-market (symbols=%s)" % ",".join(symbols))

    cross_rows: List[Dict[str, object]] = []
    for sym in symbols:
        m = MARKETS[sym.upper()]
        sym = m.symbol
        broker_out = market_hub(root, sym)
        try:
            if not skip_replay:
                _progress(root, "REPLAY %s daily=%s" % (sym, m.daily.name))
                broker_row = run_broker(root, m, force=force, slippage_ticks=slippage_ticks)
            else:
                with (broker_out / "summary.csv").open(encoding="utf-8") as fh:
                    broker_row = dict(next(csv.DictReader(fh)))

            _progress(root, "PRIOR_WIDTH %s" % sym)
            pw = prior_width_study(m, broker_out)
            q4 = pw.get("q4_large") or {}
            cross_rows.append(
                {
                    "symbol": sym,
                    "family": m.family,
                    "trades": broker_row.get("trades", pw.get("n_trades", 0)),
                    "baseline_net": float(broker_row.get("net_usd", pw.get("baseline_net", 0))),
                    "ns": float(broker_row.get("ns", 0)),
                    "stress_dd": float(broker_row.get("stress_dd", 0)),
                    "q4_n": q4.get("n", 0),
                    "q4_net": float(q4.get("net", 0) or 0),
                    "q4_wr": q4.get("win_rate"),
                    "skip_q4_delta": float(pw.get("skip_q4_delta_vs_baseline", 0) or 0),
                    "width_net_rho": (pw.get("spearman_width_vs_net") or {}).get("rho"),
                    "hub": str(broker_out.relative_to(REPO)),
                }
            )
            _progress(
                root,
                "DONE %s net=$%.0f Q4=$%.0f (n=%s)"
                % (sym, float(broker_row.get("net_usd", 0)), float(q4.get("net", 0) or 0), q4.get("n", 0)),
            )
        except Exception as exc:
            _progress(root, "FAILED %s: %s" % (sym, exc))
            fail = broker_out / "FAILED.txt"
            fail.parent.mkdir(parents=True, exist_ok=True)
            fail.write_text(traceback.format_exc(), encoding="utf-8")
            cross_rows.append(
                {
                    "symbol": sym,
                    "family": m.family,
                    "trades": 0,
                    "baseline_net": 0.0,
                    "ns": 0.0,
                    "stress_dd": 0.0,
                    "q4_n": 0,
                    "q4_net": 0.0,
                    "q4_wr": None,
                    "skip_q4_delta": 0.0,
                    "width_net_rho": float("nan"),
                    "hub": str(broker_out.relative_to(REPO)),
                    "error": str(exc),
                }
            )

    _write_cross_summary(root, cross_rows)
    email_lines = [
        "Quarterly range breakout — FX / metals / CFDs complete.",
        "",
        "Hub: %s" % root,
        "Baseline: mid SL honest breakout. Prior-width Q4_large quartile on tape.",
        "",
    ]
    for r in cross_rows:
        if r.get("error"):
            email_lines.append("%s FAILED: %s" % (r["symbol"], r["error"]))
            continue
        email_lines.append(
            "%s (%s): net $%.0f | N/S %.2f | Q4_large n=%s net $%.0f | skip-Q4 Δ $%.0f"
            % (
                r["symbol"],
                r["family"],
                float(r["baseline_net"]),
                float(r["ns"]),
                r["q4_n"],
                float(r["q4_net"]),
                float(r["skip_q4_delta"]),
            )
        )
    email_lines.extend(["", "Stance: research.", "SUMMARY: %s" % (root / "SUMMARY.md")])
    body = "\n".join(email_lines)
    (root / "EMAIL.txt").write_text(body + "\n", encoding="utf-8")
    _progress(root, "ALL DONE markets=%d" % len(symbols))
    if email:
        send_email(subject="potions: quarterly breakout FX/metals/CFD cross-market complete", body=body)
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--symbols",
        type=str,
        default=",".join(MARKETS.keys()),
        help="Comma list (default: all FX/metals/CFD).",
    )
    p.add_argument(
        "--family",
        type=str,
        default="",
        help="Optional filter: fx, metal, cfd (comma list).",
    )
    p.add_argument("--slippage-ticks", type=float, default=1.0)
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--skip-replay", action="store_true", help="Only prior-width study from existing hubs.")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)

    syms = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
    fams = {f.strip().lower() for f in str(args.family).split(",") if f.strip()}
    if fams:
        syms = [s for s in syms if MARKETS[s].family in fams]
    for s in syms:
        if s not in MARKETS:
            raise SystemExit("Unknown symbol: %s (have %s)" % (s, ", ".join(MARKETS)))
        if not MARKETS[s].daily.exists():
            raise SystemExit("Missing daily data: %s" % MARKETS[s].daily)

    try:
        return run_all(
            symbols=syms,
            force=bool(args.force),
            slippage_ticks=float(args.slippage_ticks),
            email=bool(args.email),
            skip_replay=bool(args.skip_replay),
        )
    except Exception:
        tb = traceback.format_exc()
        HUB.mkdir(parents=True, exist_ok=True)
        (HUB / "FAILED.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: quarterly breakout FX/metals/CFD FAILED",
                body="Hub: %s\n\n%s\n" % (HUB, tb[-4000:]),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
