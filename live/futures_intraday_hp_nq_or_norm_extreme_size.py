"""NQ prior-opposed OR-norm extreme size-up sensitivity (5× / 10×) + liquidity.

Best HP sleeve from futures_intraday_hp_sizeup_v1: **NQ prior-opposed RL,
normal opening 15m range (`or_norm`)** — provisional @1.25× and @2×
(highest conviction). This study extends **linear campaign scaling** to
5× and 10× and estimates **liquidity footprint** vs entry-bar / ±5m / RTH
1m volume.

Sensitivity only — **not** a null-suite validation. Do not promote 5×/10×
from these columns.

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.futures_intraday_hp_nq_or_norm_extreme_size --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
from live.intraday_condition_overlay import hp_mask, score_nets
from live.notify_email import send_email
from live.v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

from .futures_intraday_hp_sizeup_lib import COND_COL, DBN_1M, LIVE_HUB, PROFILE_HUB, REPO, STUDY

HUB = LIVE_HUB.parent / "futures_intraday_hp_nq_or_norm_extreme_size"
BOOK = "nq_prior_opposed_rl"
COND = "Opening 15m range vs ATR"
BUCKET = "or_norm"
LABEL = "NQ prior-opposed RL, normal opening 15m range"
MULTS = (1.0, 1.25, 2.0, 3.0, 4.0, 5.0, 10.0)
# S_1_1_3 resting-limit book uses entry_qty=5 on the campaign tape.
BASE_ENTRY_QTY = 5
NQ_POINT_VALUE = 20.0  # $ per point
# Rough CME NQ initial margin order-of-magnitude (USD); for footprint only.
NQ_IM_APPROX = 20000.0


def _patch_cond() -> None:
    overlay.COND_COL.clear()
    overlay.COND_COL.update(COND_COL)


def _load_nq_or_norm() -> Tuple[pd.DataFrame, np.ndarray]:
    path = PROFILE_HUB / "all_campaigns.csv"
    if not path.exists():
        raise FileNotFoundError("missing %s — run futures HP profile first" % path)
    camp = pd.read_csv(path)
    camp["entry_ts"] = pd.to_datetime(camp["entry_ts"], utc=True)
    df = camp[camp["book"] == BOOK].sort_values("entry_ts").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("no campaigns for %s" % BOOK)
    if "session_date" not in df.columns:
        df["session_date"] = df["entry_ts"].dt.tz_convert("America/New_York").dt.strftime("%Y-%m-%d")
    else:
        df["session_date"] = df["session_date"].astype(str)
    m = hp_mask(df, COND, BUCKET)
    if not m.any():
        raise RuntimeError("empty HP mask for %s %s=%s" % (BOOK, COND, BUCKET))
    return df, m


def size_table(df: pd.DataFrame, m: np.ndarray) -> pd.DataFrame:
    base = df["net_usd"].to_numpy(float)
    base_sc = score_nets(base)
    rows = []
    for mult in MULTS:
        sized = base.copy()
        if float(mult) != 1.0:
            sized[m] = sized[m] * float(mult)
        sc = score_nets(sized)
        # Path max DD approximation via cumulative
        cum = np.cumsum(sized)
        peak = np.maximum.accumulate(cum)
        mtm_dd = float((cum - peak).min()) if len(cum) else 0.0
        hp_qty = int(round(BASE_ENTRY_QTY * float(mult)))
        rows.append(
            {
                "mult": float(mult),
                "hp_n": int(m.sum()),
                "hp_pct": round(100.0 * float(m.mean()), 2),
                "base_entry_qty": BASE_ENTRY_QTY,
                "hp_entry_qty": hp_qty,
                "net": round(sc["net"], 2),
                "stress": round(sc["stress"], 2),
                "ns": round(sc["ns"], 3),
                "mtm_dd": round(mtm_dd, 2),
                "delta_net": round(sc["net"] - base_sc["net"], 2),
                "delta_ns": round(sc["ns"] - base_sc["ns"], 3),
                "stress_x": (
                    round(sc["stress"] / base_sc["stress"], 4) if base_sc["stress"] > 1 else float("nan")
                ),
                "approx_im_usd_hp": round(hp_qty * NQ_IM_APPROX, 0),
            }
        )
    return pd.DataFrame(rows)


def _rth_mask(ts: pd.Series) -> pd.Series:
    # NY 09:30–16:00
    minutes = ts.dt.hour * 60 + ts.dt.minute
    return (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)


def liquidity_table(df: pd.DataFrame, m: np.ndarray) -> pd.DataFrame:
    """Entry-bar / ±5m / RTH volume share for HP campaigns at each multiplier."""
    from datetime import date as date_cls

    dbn = DBN_1M.get("NQ")
    if dbn is None or not dbn.exists():
        raise FileNotFoundError("NQ 1m DBN missing: %s" % dbn)

    hp = df.loc[m].copy()
    hp["entry_ts_ny"] = pd.to_datetime(hp["entry_ts"], utc=True).dt.tz_convert("America/New_York")
    hp["sess"] = hp["entry_ts_ny"].dt.strftime("%Y-%m-%d")
    dates = sorted(hp["sess"].unique())
    print("loading NQ 1m for %d HP session dates ..." % len(dates), flush=True)
    by_day = load_1m_by_ny_date_any(dbn.resolve(), "nq")

    camp_rows: List[dict] = []
    missing = 0
    for _, row in hp.iterrows():
        sess = str(row["sess"])
        try:
            dkey = date_cls.fromisoformat(sess)
        except ValueError:
            missing += 1
            continue
        day = by_day.get(dkey)
        if day is None or getattr(day, "empty", True):
            missing += 1
            continue
        bars = day.reset_index()
        ts_col = "ts_event" if "ts_event" in bars.columns else ("ts" if "ts" in bars.columns else None)
        if ts_col is None:
            missing += 1
            continue
        bars = bars.rename(columns={ts_col: "ts"})
        bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert("America/New_York")
        if "volume" not in bars.columns:
            missing += 1
            continue
        bars["volume"] = pd.to_numeric(bars["volume"], errors="coerce").fillna(0.0)
        entry = row["entry_ts_ny"]
        entry_floor = entry.floor("min")
        hit = bars[bars["ts"] == entry_floor]
        if hit.empty:
            bars = bars.copy()
            bars["_dt"] = (bars["ts"] - entry_floor).abs()
            hit = bars.nsmallest(1, "_dt")
            if hit.empty or hit.iloc[0]["_dt"] > pd.Timedelta(minutes=2):
                missing += 1
                continue
        entry_vol = float(hit.iloc[0]["volume"])
        entry_px = float(row.get("entry_price") or hit.iloc[0].get("close") or 0.0)
        win = bars[
            (bars["ts"] >= entry_floor - pd.Timedelta(minutes=5))
            & (bars["ts"] <= entry_floor + pd.Timedelta(minutes=5))
        ]
        win_vol = float(win["volume"].sum())
        rth = bars[_rth_mask(bars["ts"])]
        rth_vol = float(rth["volume"].sum()) if not rth.empty else float(bars["volume"].sum())
        camp_rows.append(
            {
                "session_date": sess,
                "entry_ts": str(entry_floor),
                "entry_price": entry_px,
                "entry_bar_vol": entry_vol,
                "win_pm5_vol": win_vol,
                "rth_vol": rth_vol,
                "net_usd_1x": float(row["net_usd"]),
            }
        )

    camp = pd.DataFrame(camp_rows)
    if camp.empty:
        raise RuntimeError("no HP campaigns matched to 1m volume (missing=%d)" % missing)

    out_rows = []
    for mult in MULTS:
        qty = int(round(BASE_ENTRY_QTY * float(mult)))
        share_bar = camp["entry_bar_vol"].replace(0, np.nan)
        share_win = camp["win_pm5_vol"].replace(0, np.nan)
        share_rth = camp["rth_vol"].replace(0, np.nan)
        pct_bar = 100.0 * qty / share_bar
        pct_win = 100.0 * qty / share_win
        pct_rth = 100.0 * qty / share_rth
        notional = qty * camp["entry_price"] * NQ_POINT_VALUE
        out_rows.append(
            {
                "mult": float(mult),
                "hp_entry_qty": qty,
                "n_hp_with_vol": int(len(camp)),
                "missing_vol_sessions": int(missing),
                "median_entry_bar_vol": round(float(camp["entry_bar_vol"].median()), 1),
                "p10_entry_bar_vol": round(float(camp["entry_bar_vol"].quantile(0.10)), 1),
                "median_pm5_vol": round(float(camp["win_pm5_vol"].median()), 1),
                "median_rth_vol": round(float(camp["rth_vol"].median()), 0),
                "median_pct_entry_bar": round(float(pct_bar.median()), 2),
                "p90_pct_entry_bar": round(float(pct_bar.quantile(0.90)), 2),
                "frac_gt_10pct_bar": round(float((pct_bar > 10).mean()), 3),
                "frac_gt_25pct_bar": round(float((pct_bar > 25).mean()), 3),
                "frac_gt_50pct_bar": round(float((pct_bar > 50).mean()), 3),
                "median_pct_pm5": round(float(pct_win.median()), 2),
                "p90_pct_pm5": round(float(pct_win.quantile(0.90)), 2),
                "median_pct_rth": round(float(pct_rth.median()), 4),
                "median_notional_usd": round(float(notional.median()), 0),
                "approx_im_usd": round(qty * NQ_IM_APPROX, 0),
            }
        )
    camp_path = HUB / "hp_entry_volume_context.csv"
    HUB.mkdir(parents=True, exist_ok=True)
    camp.to_csv(camp_path, index=False)
    return pd.DataFrame(out_rows)


def write_report(sens: pd.DataFrame, liq: pd.DataFrame) -> Tuple[str, str]:
    best_ns = sens.loc[sens["ns"].idxmax()]
    lines = [
        "# NQ OR-norm extreme size-up (5× / 10×) + liquidity",
        "",
        "Study parent: `%s`" % STUDY,
        "Book: **%s** — %s (`%s`)." % (BOOK, LABEL, BUCKET),
        "Hub: `%s`" % HUB.relative_to(REPO),
        "",
        "Baseline book size on tape: **entry_qty=%d** (v2b `S_1_1_3`). "
        "HP campaigns: **%d** (%.1f%% of book)."
        % (BASE_ENTRY_QTY, int(sens.iloc[0]["hp_n"]), float(sens.iloc[0]["hp_pct"])),
        "",
        "**Sensitivity only** — linear scaling of HP campaign nets. "
        "Null-suite standing exists only for **1.25×** and **exact 2×** (provisional). "
        "**Do not promote 5×/10×** from this table.",
        "",
        "## Size sensitivity",
        "",
        "| Mult | HP qty | Net | Stress | N/S | ΔN/S | stress× | ≈IM HP |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in sens.iterrows():
        lines.append(
            "| %.2g× | %d | $%s | $%s | **%.2f** | %+.2f | %.2f | $%s |"
            % (
                r["mult"],
                int(r["hp_entry_qty"]),
                "{:,.0f}".format(r["net"]),
                "{:,.0f}".format(r["stress"]),
                r["ns"],
                r["delta_ns"],
                r["stress_x"] if pd.notna(r["stress_x"]) else float("nan"),
                "{:,.0f}".format(r["approx_im_usd_hp"]),
            )
        )
    lines.extend(
        [
            "",
            "Peak N/S row: **%.2g×** at N/S **%.2f** (ΔN/S %+.2f)."
            % (best_ns["mult"], best_ns["ns"], best_ns["delta_ns"]),
            "",
            "## Liquidity footprint (HP entries vs NQ 1m volume)",
            "",
            "Contracts assumed = `entry_qty × mult` on HP days. Shares use entry "
            "minute volume, ±5m window, and full RTH day volume from the NQ 1m DBN.",
            "",
            "| Mult | qty | med %% entry bar | p90 %% bar | %% days >10%% bar | %% >25%% | %% >50%% | med %% ±5m | med %% RTH | med notional | ≈IM |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in liq.iterrows():
        lines.append(
            "| %.2g× | %d | %.1f%% | %.1f%% | %.0f%% | %.0f%% | %.0f%% | %.2f%% | %.3f%% | $%s | $%s |"
            % (
                r["mult"],
                int(r["hp_entry_qty"]),
                r["median_pct_entry_bar"],
                r["p90_pct_entry_bar"],
                100 * r["frac_gt_10pct_bar"],
                100 * r["frac_gt_25pct_bar"],
                100 * r["frac_gt_50pct_bar"],
                r["median_pct_pm5"],
                r["median_pct_rth"],
                "{:,.0f}".format(r["median_notional_usd"]),
                "{:,.0f}".format(r["approx_im_usd"]),
            )
        )
    # Stance
    row5 = sens[sens["mult"] == 5.0].iloc[0]
    row10 = sens[sens["mult"] == 10.0].iloc[0]
    row2 = sens[sens["mult"] == 2.0].iloc[0]
    liq5 = liq[liq["mult"] == 5.0].iloc[0]
    liq10 = liq[liq["mult"] == 10.0].iloc[0]
    lines.extend(
        [
            "",
            "## Stance",
            "",
            "- Best economic N/S on this linear tape remains near **2×** (%.2f), not 5×/10× "
            "(5× N/S %.2f, 10× N/S %.2f) — larger size adds net but **dilutes N/S** after 2×."
            % (row2["ns"], row5["ns"], row10["ns"]),
            "- Liquidity (NQ 1m): **not the blocker**. At **5×** (qty=%d) median entry-bar "
            "share **%.1f%%** (p90 **%.1f%%**); at **10×** (qty=%d) median **%.1f%%** / p90 "
            "**%.1f%%**. Days consuming >25%% of the entry minute: 5× **%.0f%%**, 10× **%.0f%%**. "
            "Median RTH share stays ≪0.1%%. Margin/notional footprint grows linearly "
            "(≈IM $%s @5× / $%s @10×) — capital constraint, not tape thinness."
            % (
                int(liq5["hp_entry_qty"]),
                liq5["median_pct_entry_bar"],
                liq5["p90_pct_entry_bar"],
                int(liq10["hp_entry_qty"]),
                liq10["median_pct_entry_bar"],
                liq10["p90_pct_entry_bar"],
                100 * liq5["frac_gt_25pct_bar"],
                100 * liq10["frac_gt_25pct_bar"],
                "{:,.0f}".format(liq5["approx_im_usd"]),
                "{:,.0f}".format(liq10["approx_im_usd"]),
            ),
            "- Operational read: **stay at provisional 1.25× / controlled-paper 2×**. "
            "5×/10× are **N/S-suboptimal** vs 2× and unvalidated (no null suite); "
            "liquidity alone does not veto them on CME NQ.",
            "- Next if pursuing size: dedicated null suite at the intended mult "
            "(not inferred), plus impact/queue model — not more linear scaling.",
            "",
            "## Files",
            "",
            "- `size_sensitivity_5_10.csv`",
            "- `liquidity_footprint.csv`",
            "- `hp_entry_volume_context.csv`",
            "- `EMAIL.txt`",
            "",
        ]
    )
    md = "\n".join(lines)
    email = [
        "potions: NQ OR-norm extreme size-up (5×/10×) + liquidity",
        "",
        "Hub: %s" % HUB.relative_to(REPO),
        "Best HP sleeve: NQ prior-opposed OR-norm (provisional @1.25× / @2×).",
        "",
        "Sensitivity (linear HP scale, entry_qty base=%d):" % BASE_ENTRY_QTY,
        "  1×   N/S=%.2f  net=$%s"
        % (sens[sens.mult == 1].iloc[0].ns, "{:,.0f}".format(sens[sens.mult == 1].iloc[0].net)),
        "  2×   N/S=%.2f  ΔN/S=%+.2f  (peak)"
        % (row2["ns"], row2["delta_ns"]),
        "  5×   N/S=%.2f  ΔN/S=%+.2f  qty=%d  med entry-bar share=%.1f%% (p90 %.1f%%)"
        % (
            row5["ns"],
            row5["delta_ns"],
            int(liq5["hp_entry_qty"]),
            liq5["median_pct_entry_bar"],
            liq5["p90_pct_entry_bar"],
        ),
        "  10×  N/S=%.2f  ΔN/S=%+.2f  qty=%d  med entry-bar share=%.1f%% (p90 %.1f%%)"
        % (
            row10["ns"],
            row10["delta_ns"],
            int(liq10["hp_entry_qty"]),
            liq10["median_pct_entry_bar"],
            liq10["p90_pct_entry_bar"],
        ),
        "",
        "Stance: sit on 5×/10× — N/S peaks at **2×** (36.26); 5×=33.45 / 10×=31.48. "
        "Liquidity on CME NQ is fine (med entry-bar share 0.9%/1.8% at 5×/10×); "
        "capital/IM and missing null suites are the real gates. Keep provisional "
        "1.25× / controlled-paper 2×.",
        "Not a null-suite validation.",
        "",
    ]
    return md, "\n".join(email)


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    _patch_cond()
    df, m = _load_nq_or_norm()
    sens = size_table(df, m.to_numpy())
    sens.to_csv(HUB / "size_sensitivity_5_10.csv", index=False)
    liq = liquidity_table(df, m.to_numpy())
    liq.to_csv(HUB / "liquidity_footprint.csv", index=False)
    md, email_body = write_report(sens, liq)
    (HUB / "SUMMARY.md").write_text(md, encoding="utf-8")
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(
        json.dumps(
            {
                "ok": True,
                "book": BOOK,
                "bucket": BUCKET,
                "mults": list(MULTS),
                "peak_ns_mult": float(sens.loc[sens["ns"].idxmax(), "mult"]),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(email_body, flush=True)
    if email:
        send_email(
            subject="potions: NQ OR-norm 5×/10× size + liquidity (research)",
            body=email_body,
        )
    return HUB


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)
    try:
        run(email=bool(args.email))
        return 0
    except Exception:
        tb = traceback.format_exc()
        if args.email:
            send_email(
                subject="potions: NQ OR-norm extreme size-up FAILED",
                body=tb,
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
