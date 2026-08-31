"""HP condition + gate mill for NQ first-hour follow 3R **broker** book.

Profiles `nq_1h_first_hour_broker` follow_3r_all (Engine+PaperBroker fills) through
the futures HP feature mill, first-hour-native conditions, prior-opposed overlay,
London / prior-day-week sweep fade-follow buckets, composite gate stacks, and an
optional hourly ATR SuperTrend trailing-stop exit variant.

Diagnostic only — not a promotion gate.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_1h_first_hour_broker_ha --email
  python -m live.nq_1h_first_hour_broker_ha --email --smoke
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

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_v2b_london_ungated import REPO
from .futures_intraday_condition_profile import profile_book, score_nets, summarize_bucket
from .futures_intraday_hp_sizeup_lib import CONDITION_COLS, annotate_campaigns, ensure_tf_bars
from .notify_email import send_email
from .nq_1h_first_hour_ha import FH_CONDS, build_first_hour
from .nq_5m_large_candle_study import FEE, POINT_VALUE, TICK, load_rth_5m, summarize_book
from .nq_large_candle_ha_lib import (
    PO_CONDS,
    attach_po_context,
    attach_trade_po_labels,
    compare_current_hp,
    load_po_campaigns,
    po_buckets_table,
    profile_frame,
    write_ha_report,
)

HUB = REPO / "live" / "state" / "nq_1h_first_hour_broker_ha"
BROKER_HUB = REPO / "live" / "state" / "nq_1h_first_hour_broker"
NY = "America/New_York"
FAMILY = "nq_1h_first_hour_broker"
BOOK = "follow_3r_all"
MIN_N = 40
LONDON_OPEN = time(3, 0)
LONDON_END = time(9, 30)

SWEEP_CONDS: Sequence[Tuple[str, str]] = (
    ("pdh_sweep", "Prior-day high swept in FH"),
    ("pdl_sweep", "Prior-day low swept in FH"),
    ("pwh_sweep", "Prior-week high swept in FH"),
    ("pwl_sweep", "Prior-week low swept in FH"),
    ("london_hi_sweep", "London session high swept in FH"),
    ("london_lo_sweep", "London session low swept in FH"),
    ("sweep_fade_side", "Sweep fade side (short after hi / long after lo)"),
    ("sweep_stack", "Combined key-level sweep stack"),
)


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _to_ny(s: pd.Series) -> pd.Series:
    ts = pd.to_datetime(s, utc=True, errors="coerce")
    if ts.isna().any():
        raw = pd.to_datetime(s, errors="coerce")
        if getattr(raw.dt, "tz", None) is None:
            raw = raw.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            raw = raw.dt.tz_convert(NY)
        ts = ts.fillna(raw)
    else:
        ts = ts.dt.tz_convert(NY)
    return ts


def load_broker_campaigns(slug: str = BOOK) -> pd.DataFrame:
    """Unit trades from broker hub → campaign frame."""
    path = BROKER_HUB / "states" / ("nq_fh_%s" % slug) / "unit_trades.csv"
    if not path.exists():
        raise FileNotFoundError("missing broker unit_trades: %s" % path)
    raw = pd.read_csv(path)
    raw["entry_ts"] = _to_ny(raw["entry_ts"])
    raw["exit_ts"] = _to_ny(raw["exit_ts"])
    raw["side"] = raw["direction"].astype(str).str.lower()
    raw["net_usd"] = pd.to_numeric(raw["net_usd"], errors="coerce")
    raw["entry_price"] = pd.to_numeric(raw["entry_price"], errors="coerce")
    raw["session_date"] = raw["entry_ts"].dt.strftime("%Y-%m-%d")
    out = raw.rename(columns={"trade_id": "campaign_id"}).copy()
    out["book"] = slug
    out["symbol"] = "NQ"
    out["family"] = FAMILY
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["hour_ny"] = out["entry_ts"].dt.hour
    out["month"] = out["entry_ts"].dt.month
    out["year"] = out["entry_ts"].dt.year
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    return out.sort_values("entry_ts").reset_index(drop=True)


def build_london_session(df5: Optional[pd.DataFrame] = None) -> pd.DataFrame:
    """London pre-RTH window 03:00–09:29 NY per session day (full-session tape)."""
    src = ensure_tf_bars("NQ", "5m")
    if src is None or src.empty:
        src = df5
    if src is None or src.empty:
        return pd.DataFrame()
    if "session_date" not in src.columns:
        src = src.copy()
        src["session_date"] = src["ts"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    rows: List[dict] = []
    for day, sess in src.groupby("session_date", sort=False):
        st = sess["ts"].dt.tz_convert(NY).dt.time
        lon = sess[(st >= LONDON_OPEN) & (st < LONDON_END)]
        if len(lon) < 4:
            continue
        rows.append(
            {
                "session_date": str(day),
                "london_high": float(lon["high"].max()),
                "london_low": float(lon["low"].min()),
                "london_range": float(lon["high"].max() - lon["low"].min()),
                "london_close": float(lon["close"].iloc[-1]),
            }
        )
    return pd.DataFrame(rows)


def attach_sweep_features(camp: pd.DataFrame, fh: pd.DataFrame, london: pd.DataFrame) -> pd.DataFrame:
    """Prior day/week + London session sweep labels at first-hour close."""
    if camp.empty:
        return camp
    left = fh[
        [
            "session_date",
            "high",
            "low",
            "open",
            "close",
            "body",
            "dir",
            "fh_body",
            "fh_size",
            "fh_close_third",
            "fh_vs_prior",
            "or15_vs_fh",
            "gap_vs_fh",
        ]
    ].copy()
    left = left.rename(
        columns={"high": "fh_high", "low": "fh_low", "dir": "fh_dir", "body": "fh_body_pts", "open": "fh_open"}
    )
    lon = london.set_index("session_date") if not london.empty else pd.DataFrame()
    out = camp.merge(left, on="session_date", how="left")
    if not lon.empty:
        out["london_high"] = out["session_date"].map(lon["london_high"])
        out["london_low"] = out["session_date"].map(lon["london_low"])
    else:
        out["london_high"] = np.nan
        out["london_low"] = np.nan

    pdh = pd.to_numeric(out.get("prev_day_high"), errors="coerce")
    pdl = pd.to_numeric(out.get("prev_day_low"), errors="coerce")
    pwh = pd.to_numeric(out.get("w_high"), errors="coerce")
    pwl = pd.to_numeric(out.get("w_low"), errors="coerce")
    fh_h = pd.to_numeric(out["fh_high"], errors="coerce")
    fh_l = pd.to_numeric(out["fh_low"], errors="coerce")

    out["pdh_sweep"] = np.where(pdh.notna() & (fh_h >= pdh), "took_pdh", "no_pdh")
    out["pdl_sweep"] = np.where(pdl.notna() & (fh_l <= pdl), "took_pdl", "no_pdl")
    out["pwh_sweep"] = np.where(pwh.notna() & (fh_h >= pwh), "took_pwh", "no_pwh")
    out["pwl_sweep"] = np.where(pwl.notna() & (fh_l <= pwl), "took_pwl", "no_pwl")
    out["london_hi_sweep"] = np.where(
        out["london_high"].notna() & (fh_h >= out["london_high"]),
        "took_london_hi",
        "no_london_hi",
    )
    out["london_lo_sweep"] = np.where(
        out["london_low"].notna() & (fh_l <= out["london_low"]),
        "took_london_lo",
        "no_london_lo",
    )

    hi_sweep = (
        (out["pdh_sweep"] == "took_pdh")
        | (out["pwh_sweep"] == "took_pwh")
        | (out["london_hi_sweep"] == "took_london_hi")
    )
    lo_sweep = (
        (out["pdl_sweep"] == "took_pdl")
        | (out["pwl_sweep"] == "took_pwl")
        | (out["london_lo_sweep"] == "took_london_lo")
    )
    fade_short = hi_sweep & (out["side"] == "short")
    fade_long = lo_sweep & (out["side"] == "long")
    out["sweep_fade_side"] = np.where(
        fade_short | fade_long,
        "fade_follow_through",
        np.where(hi_sweep | lo_sweep, "sweep_with_side", "no_sweep"),
    )
    stack = []
    for _, r in out.iterrows():
        parts = []
        if r["pdh_sweep"] == "took_pdh":
            parts.append("pdh")
        if r["pdl_sweep"] == "took_pdl":
            parts.append("pdl")
        if r["pwh_sweep"] == "took_pwh":
            parts.append("pwh")
        if r["pwl_sweep"] == "took_pwl":
            parts.append("pwl")
        if r["london_hi_sweep"] == "took_london_hi":
            parts.append("lon_hi")
        if r["london_lo_sweep"] == "took_london_lo":
            parts.append("lon_lo")
        stack.append("+".join(parts) if parts else "none")
    out["sweep_stack"] = stack
    return out


def _hourly_st_asof(df5: pd.DataFrame, atr_len: int = 14, mult: float = 3.0) -> pd.DataFrame:
    """Hour-complete 1h ATR SuperTrend, shifted +1h for causal availability."""
    h1 = ensure_tf_bars("NQ", "1h")
    if h1 is None or h1.empty:
        h1 = df5.set_index("ts").resample("1h", label="left", closed="left").agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        ).dropna(subset=["close"]).reset_index()
        h1 = h1.rename(columns={"ts": "ts"})
    st = compute_supertrend(h1.copy(), atr_len=atr_len, multiplier=mult)
    st["available_at"] = st["ts"] + pd.Timedelta(hours=1)
    return st[["available_at", "supertrend", "supertrend_trend"]].dropna(subset=["supertrend"])


def simulate_st_trail_exits(
    camp: pd.DataFrame,
    df5: pd.DataFrame,
    *,
    atr_len: int = 14,
    mult: float = 3.0,
) -> pd.DataFrame:
    """Re-walk broker entries with hourly ST trail stop (+ fixed 3R TP, EOD flat)."""
    st = _hourly_st_asof(df5, atr_len=atr_len, mult=mult)
    if st.empty or camp.empty:
        return pd.DataFrame()
    rest_by: Dict[str, pd.DataFrame] = {}
    for day, sess in df5.groupby("session_date", sort=False):
        st_t = sess["ts"].dt.tz_convert(NY).dt.time
        rest = sess[st_t >= time(10, 30)].reset_index(drop=True)
        if not rest.empty:
            rest_by[str(day)] = rest

    rows: List[dict] = []
    for _, tr in camp.iterrows():
        day = str(tr["session_date"])
        rest = rest_by.get(day)
        if rest is None or rest.empty:
            continue
        side = str(tr["side"])
        entry = float(tr["entry_price"])
        direction = 1 if side == "long" else -1
        # Approximate body from FH if present on row; else 10pt default for TP distance
        body = float(tr.get("fh_body_pts") or 0) if "fh_body_pts" in tr.index else 0.0
        if not np.isfinite(body) or body < TICK:
            fh_open = float(tr.get("fh_open") or (entry - direction * 10))
            body = abs(entry - fh_open)
        tp = entry + direction * 3.0 * body
        fh_open = float(tr.get("fh_open") or (entry - direction * body))
        init_sl = fh_open
        trail = init_sl
        exit_px = float(rest["close"].iloc[-1])
        reason = "eod"
        for j in range(len(rest)):
            ts = rest["ts"].iloc[j]
            hi = float(rest["high"].iloc[j])
            lo = float(rest["low"].iloc[j])
            st_row = st[st["available_at"] <= ts]
            if not st_row.empty:
                st_px = float(st_row["supertrend"].iloc[-1])
                st_tr = int(st_row["supertrend_trend"].iloc[-1])
                if side == "long" and st_tr == 1:
                    trail = max(trail, st_px)
                elif side == "short" and st_tr == -1:
                    trail = min(trail, st_px)
            hit_sl = lo <= trail if side == "long" else hi >= trail
            hit_tp = hi >= tp if side == "long" else lo <= tp
            if hit_sl and hit_tp:
                exit_px, reason = trail, "st_trail"
                break
            if hit_sl:
                exit_px, reason = trail, "st_trail"
                break
            if hit_tp:
                exit_px, reason = tp, "target"
                break
        pts = (exit_px - entry) * direction
        net = pts * POINT_VALUE - FEE
        rows.append(
            {
                "session_date": day,
                "campaign_id": tr["campaign_id"],
                "side": side,
                "entry_price": entry,
                "exit_px": exit_px,
                "reason": reason,
                "r_mult": pts / body if body > TICK else 0.0,
                "net_usd": net,
                "win": net > 0,
                "book": "follow_3r_st_trail",
            }
        )
    return pd.DataFrame(rows)


def composite_gates(camp: pd.DataFrame, notables: List[dict]) -> pd.DataFrame:
    """Stack top dual-lift buckets + FH strong body; report gated subsamples."""
    if camp.empty:
        return pd.DataFrame()
    baseline = score_nets(camp["net_usd"].to_numpy(float))
    gates: List[Tuple[str, pd.Series]] = []

    # Always include first-hour strong body (known from prior HA / broker strong book).
    if "fh_body" in camp.columns:
        gates.append(("fh_body=strong", camp["fh_body"].astype(str) == "strong"))

    # Prior-day/week opposed (classic HP carry).
    if "day_half_align" in camp.columns:
        gates.append(("day_opposed", camp["day_half_align"] == "day_opposed"))
    if "week_half_align" in camp.columns:
        gates.append(("week_opposed", camp["week_half_align"] == "week_opposed"))

    # Sweep fade follow-through (user-requested).
    if "sweep_fade_side" in camp.columns:
        gates.append(
            ("sweep_fade_follow", camp["sweep_fade_side"] == "fade_follow_through")
        )

    # Top notables (unique condition=bucket).
    seen = set()
    for r in sorted(notables, key=lambda x: (x.get("z_wr", 0), x.get("avg_lift", 0)), reverse=True):
        title = str(r["condition"])
        bucket = str(r["bucket"])
        col = None
        for c, t in CONDITION_COLS + list(FH_CONDS) + list(SWEEP_CONDS) + list(PO_CONDS):
            if t == title:
                col = c
                break
        if col is None or col not in camp.columns:
            continue
        key = "%s=%s" % (col, bucket)
        if key in seen:
            continue
        seen.add(key)
        gates.append((key, camp[col].astype(str) == bucket))
        if len(seen) >= 8:
            break

    rows = []
    for name, mask in gates:
        sub = camp[mask]
        sc = score_nets(sub["net_usd"].to_numpy(float)) if not sub.empty else score_nets(np.array([]))
        rows.append(
            {
                "gate": name,
                "n": sc["n"],
                "wr": sc["wr"],
                "avg": sc["avg"],
                "net": sc["net"],
                "stress": sc["stress"],
                "ns": sc["ns"],
                "coverage": float(mask.mean()) if len(mask) else 0.0,
                "wr_lift_pp": 100.0 * (sc["wr"] - baseline["wr"]) if sc["n"] else 0.0,
                "avg_lift": sc["avg"] - baseline["avg"] if sc["n"] else 0.0,
            }
        )

    # Pair stacks from best singles
    singles = [g for g in rows if g["n"] >= MIN_N and g["ns"] > baseline["ns"]]
    singles = sorted(singles, key=lambda x: x["ns"], reverse=True)[:4]
    for i, a in enumerate(singles):
        for b in singles[i + 1 :]:
            ma = None
            mb = None
            for name, mask in gates:
                if name == a["gate"]:
                    ma = mask
                if name == b["gate"]:
                    mb = mask
            if ma is None or mb is None:
                continue
            combo = ma & mb
            sub = camp[combo]
            if len(sub) < MIN_N:
                continue
            sc = score_nets(sub["net_usd"].to_numpy(float))
            rows.append(
                {
                    "gate": "%s AND %s" % (a["gate"], b["gate"]),
                    "n": sc["n"],
                    "wr": sc["wr"],
                    "avg": sc["avg"],
                    "net": sc["net"],
                    "stress": sc["stress"],
                    "ns": sc["ns"],
                    "coverage": float(combo.mean()),
                    "wr_lift_pp": 100.0 * (sc["wr"] - baseline["wr"]),
                    "avg_lift": sc["avg"] - baseline["avg"],
                }
            )
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values(["ns", "n"], ascending=False).reset_index(drop=True)
    return out


def run(*, email: bool, smoke: bool) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    try:
        _progress("load broker campaigns ...")
        camp = load_broker_campaigns(BOOK)
        if smoke:
            camp = camp.tail(400).reset_index(drop=True)
        _progress("  n=%d baseline net=$%.0f" % (len(camp), camp["net_usd"].sum()))

        _progress("load 5m + first hour + London ...")
        df5 = load_rth_5m(progress=False)
        if smoke:
            keep = set(camp["session_date"].astype(str))
            df5 = df5[df5["session_date"].astype(str).isin(keep)].reset_index(drop=True)
        fh = build_first_hour(df5)
        london = build_london_session(df5)
        fh.to_csv(HUB / "first_hour_candles.csv", index=False)
        london.to_csv(HUB / "london_session.csv", index=False)

        po = load_po_campaigns(_progress)
        fh = attach_po_context(fh, po, p90_col="is_any", progress=_progress)

        _progress("annotate HP features ...")
        camp = annotate_campaigns(camp, "NQ")
        camp = attach_trade_po_labels(camp, fh)
        camp = attach_sweep_features(camp, fh, london)
        camp.to_csv(HUB / "follow_3r_all_campaigns.csv", index=False)

        extra = list(FH_CONDS) + list(SWEEP_CONDS)
        _progress("profile buckets ...")
        table, baseline, notables = profile_frame(camp, extra, MIN_N)
        if not table.empty:
            table.to_csv(HUB / "follow_3r_all_buckets.csv", index=False)
        pd.DataFrame(notables).to_csv(HUB / "follow_3r_all_notables.csv", index=False)

        hp_table, _, hp_notables = profile_book(camp.assign(book=BOOK), min_n=MIN_N)
        if not hp_table.empty:
            hp_table.to_csv(HUB / "follow_3r_all_hp_sizeup_matrix.csv", index=False)

        gates = composite_gates(camp, notables)
        if not gates.empty:
            gates.to_csv(HUB / "composite_gates.csv", index=False)

        _progress("ST trail exit variant ...")
        st_tr = simulate_st_trail_exits(camp, df5)
        st_summary = {}
        if not st_tr.empty:
            st_tr.to_csv(HUB / "follow_3r_st_trail_trades.csv", index=False)
            st_summary = summarize_book(st_tr, "follow 3R + 1h ST trail")
            pd.DataFrame([st_summary]).to_csv(HUB / "st_trail_summary.csv", index=False)

        current_cmp = compare_current_hp({BOOK: camp}, po_buckets_table())
        if not current_cmp.empty:
            current_cmp.to_csv(HUB / "vs_current_hp.csv", index=False)

        base_sc = score_nets(camp["net_usd"].to_numpy(float))
        core = [
            {
                "label": "follow 3R all first-hour (broker)",
                "n": base_sc["n"],
                "wr": base_sc["wr"],
                "avg": base_sc["avg"],
                "net": base_sc["net"],
                "stress": base_sc["stress"],
                "ns": base_sc["ns"],
                "pf": 0.0,
            }
        ]
        hp_sleeves = []
        if st_summary:
            hp_sleeves.append(st_summary)

        extra_notes = [
            "Tape: Engine+PaperBroker unit_trades from `%s`." % BROKER_HUB,
            "London window: 03:00–09:29 NY (pre-RTH). Sweep = first hour takes that session extreme.",
            "sweep_fade_side=fade_follow_through → short after hi sweep or long after lo sweep.",
            "Composite gates: singles + pairwise AND of top N/S lifts (see composite_gates.csv).",
            "ST trail: hourly ATR SuperTrend 14×3 stop replaces fixed open stop after entry; 3R TP + EOD retained.",
        ]
        write_ha_report(
            HUB,
            title="NQ first-hour follow 3R broker HA + gates",
            universe=(
                "Universe: **broker-like** NQ first-hour follow 3R (`nq_1h_first_hour_broker`, n=%d, "
                "WR=%.1f%%, net=$%.0f, N/S=%.2f). Full HP mill + FH native + London/prior sweep fade-follow + composite gates."
                % (base_sc["n"], 100 * base_sc["wr"], base_sc["net"], base_sc["ns"])
            ),
            email_subject="potions: NQ FH follow 3R broker HA + gates complete",
            core=core,
            hp_sleeves=hp_sleeves,
            notables_by_book={BOOK: notables},
            current_cmp=current_cmp,
            po_n=int(len(po)),
            extra_notes=extra_notes,
        )

        # Append gates + ST to SUMMARY
        summary_path = HUB / "SUMMARY.md"
        extra_lines = ["", "## Composite gates (broker tape)", ""]
        if gates.empty:
            extra_lines.append("_none_")
        else:
            extra_lines += [
                "| Gate | n | WR | avg | net | stress | N/S | cov |",
                "|---|---:|---:|---:|---:|---:|---:|---:|",
            ]
            for _, r in gates.head(20).iterrows():
                extra_lines.append(
                    "| %s | %d | %.1f%% | $%.0f | $%.0f | $%.0f | %.2f | %.0f%% |"
                    % (
                        r["gate"],
                        r["n"],
                        100 * r["wr"],
                        r["avg"],
                        r["net"],
                        r["stress"],
                        r["ns"],
                        100 * r["coverage"],
                    )
                )
        if st_summary:
            extra_lines += [
                "",
                "## Exit variant: 1h ATR SuperTrend trail",
                "",
                "| Book | n | WR | avg | net | stress | N/S |",
                "|---|---:|---:|---:|---:|---:|---:|",
                "| %s | %d | %.1f%% | $%.0f | $%.0f | $%.0f | %.2f |"
                % (
                    st_summary["label"],
                    st_summary["n"],
                    100 * st_summary["wr"],
                    st_summary["avg"],
                    st_summary["net"],
                    st_summary["stress"],
                    st_summary["ns"],
                ),
            ]
        summary_path.write_text(summary_path.read_text(encoding="utf-8") + "\n".join(extra_lines) + "\n", encoding="utf-8")

        email_path = HUB / "EMAIL.txt"
        email_body = email_path.read_text(encoding="utf-8")
        if not gates.empty:
            top = gates.iloc[0]
            email_body += "\nTop gate: %s n=%d N/S=%.2f\n" % (top["gate"], int(top["n"]), float(top["ns"]))
        if st_summary:
            email_body += "ST trail: n=%d N/S=%.2f vs baseline N/S=%.2f\n" % (
                st_summary["n"],
                st_summary["ns"],
                base_sc["ns"],
            )
        email_path.write_text(email_body, encoding="utf-8")

        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "smoke": smoke,
                    "n": int(len(camp)),
                    "baseline_ns": base_sc["ns"],
                    "notables": len(notables),
                    "gates": len(gates),
                    "st_trail_ns": st_summary.get("ns") if st_summary else None,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _progress("DONE n=%d notables=%d gates=%d" % (len(camp), len(notables), len(gates)))
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NQ FH broker HA FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(subject="potions: NQ FH broker HA FAILED", body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"))
        raise

    if email:
        send_email(
            subject="potions: NQ FH follow 3R broker HA + gates complete",
            body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress("email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(email=bool(args.email), smoke=bool(args.smoke))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
