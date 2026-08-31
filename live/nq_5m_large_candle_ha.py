"""HA mill for NQ 5m large-candle books + prior-opposed v2b overlay.

HA = high-probability *conditions* (same mill as midnight-open / futures HP).
Not Heikin Ashi.

Questions:
  1. Fade the p90 5m candle, and/or take 1R instead of 3R — does either beat follow-3R?
  2. Do current NQ prior-opposed HP buckets (or_norm, ST-age, RSI-against, …)
     also lift the 5m candle books?
  3. Counter-trend *during* prior-opposed v2b vs trend-continuation *after*
     it exits, using the PO campaign outcome as a causal condition (after exit only).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_5m_large_candle_ha --email
  python -m live.nq_5m_large_candle_ha --email --smoke
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

from .fx_v2b_london_ungated import REPO
from .futures_intraday_condition_profile import summarize_bucket
from .futures_intraday_hp_sizeup_lib import (
    CAUSAL_LIVE_READY,
    CONDITION_COLS,
    NEEDS_LIVE_PROXY,
    PROFILE_HUB as FUT_PROFILE,
    annotate_campaigns,
    book_by_key,
    feature_family,
    load_campaigns,
)
from .notify_email import send_email
from .nq_5m_large_candle_study import (
    HUB as CANDLE_HUB,
    classify,
    load_rth_5m,
    score_nets,
    summarize_book,
    walk_trades,
)

HUB = REPO / "live" / "state" / "nq_5m_large_candle_ha"
NY = "America/New_York"
MIN_N = 40
MIN_N_PO = 20
PO_BOOK = "nq_prior_opposed_rl"

# Current NQ prior-opposed HP shortlist / cross-book notables to compare.
CURRENT_HP = (
    ("or15_width_pct", "or_norm", "Opening 15m range vs ATR"),
    ("st_age_bucket", "st_age_30_90m", "ST-event age"),
    ("nq_es_disp", "disp_mid", "NQ-ES dispersion"),
    ("rsi_align", "rsi_against_side", "Hourly RSI vs trade"),
    ("ma5_align", "ma_aligned", "5m MA vs trade"),
    ("st_dir_align", "st_opposed_proxy", "ST-event direction vs trade"),
    ("week_of_month", "2", "Week of month"),
    ("dow", "Friday", "Day of week"),
)

PO_CONDS = (
    ("po_state", "PO v2b session state"),
    ("po_outcome", "PO v2b outcome (after exit)"),
    ("candle_vs_po", "Large-candle vs PO side"),
    ("trade_vs_po", "Trade side vs PO side"),
    ("regime", "PO regime"),
)

EXTRA_CONDS = PO_CONDS


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


def load_po_campaigns() -> pd.DataFrame:
    cached = FUT_PROFILE / "nq_prior_opposed_rl_campaigns.csv"
    if cached.exists():
        po = pd.read_csv(cached)
        _progress("PO campaigns from profile cache n=%d" % len(po))
    else:
        po = load_campaigns(book_by_key(PO_BOOK))
        _progress("PO campaigns from fills n=%d" % len(po))
    po = po.copy()
    po["entry_ts"] = _to_ny(po["entry_ts"])
    po["exit_ts"] = _to_ny(po["exit_ts"])
    if "session_date" not in po.columns:
        po["session_date"] = po["entry_ts"].dt.strftime("%Y-%m-%d")
    else:
        po["session_date"] = po["session_date"].astype(str)
    po["win"] = po["win"].astype(str).str.lower().isin(["true", "1"]) if po["win"].dtype == object else po["win"].astype(bool)
    po["side"] = po["side"].astype(str).str.lower()
    keep = [
        "session_date",
        "entry_ts",
        "exit_ts",
        "side",
        "win",
        "net_usd",
        "or15_width_pct",
        "st_age_bucket",
        "rsi_align",
        "ma5_align",
    ]
    cols = [c for c in keep if c in po.columns]
    return po[cols].sort_values("entry_ts").reset_index(drop=True)


def attach_po_context(bars: pd.DataFrame, po: pd.DataFrame) -> pd.DataFrame:
    """Causal PO state on each 5m bar (outcome only after that campaign's exit)."""
    df = bars.copy()
    df["session_date"] = df["session_date"].astype(str)
    left = df.sort_values(["session_date", "ts"]).reset_index(drop=True)
    right = po.sort_values(["session_date", "entry_ts"]).rename(
        columns={
            "entry_ts": "po_entry_ts",
            "exit_ts": "po_exit_ts",
            "side": "po_side_raw",
            "win": "po_win_raw",
            "net_usd": "po_net_usd",
        }
    )
    merged = pd.merge_asof(
        left,
        right[["session_date", "po_entry_ts", "po_exit_ts", "po_side_raw", "po_win_raw", "po_net_usd"]],
        left_on="ts",
        right_on="po_entry_ts",
        by="session_date",
        direction="backward",
    )
    has = merged["po_entry_ts"].notna()
    during = has & (merged["ts"] < merged["po_exit_ts"])
    after = has & (merged["ts"] >= merged["po_exit_ts"])
    state = np.where(during, "during_po", np.where(after, "after_po", "no_po"))
    outcome = np.where(
        after,
        np.where(merged["po_win_raw"].fillna(False).astype(bool), "po_win", "po_loss"),
        np.where(during, "pending", "no_po"),
    )
    po_side = np.where(has, merged["po_side_raw"].astype(str), "none")
    candle = merged["dir"].astype(str).to_numpy()
    po_ok = np.isin(po_side, ["long", "short"])
    c_ok = np.isin(candle, ["long", "short"])
    candle_vs = np.where(
        po_ok & c_ok,
        np.where(candle == po_side, "candle_with_po", "candle_against_po"),
        "no_po",
    )
    out = left.copy()
    out["po_state"] = state
    out["po_side"] = po_side
    out["po_outcome"] = outcome
    out["candle_vs_po"] = candle_vs
    # HP regime flags (signal-time, causal).
    p90 = out["is_p90"].fillna(False).astype(bool)
    out["hp_during_fade_st"] = p90 & (out["po_state"] == "during_po") & (out["candle_vs_po"] == "candle_against_po")
    out["hp_during_any"] = p90 & (out["po_state"] == "during_po")
    out["hp_after_follow_st"] = p90 & (out["po_state"] == "after_po") & (out["candle_vs_po"] == "candle_against_po")
    out["hp_after_loss_follow_st"] = out["hp_after_follow_st"] & (out["po_outcome"] == "po_loss")
    out["hp_after_win_fade_st"] = (
        p90 & (out["po_state"] == "after_po") & (out["po_outcome"] == "po_win") & (out["candle_vs_po"] == "candle_against_po")
    )
    n_d = int(out["hp_during_fade_st"].sum())
    n_a = int(out["hp_after_follow_st"].sum())
    _progress("PO overlay  during_fade_st bars=%d  after_follow_st bars=%d" % (n_d, n_a))
    return out


def trades_to_campaigns(tr: pd.DataFrame, book: str) -> pd.DataFrame:
    if tr is None or tr.empty:
        return pd.DataFrame()
    df = tr.copy()
    df["entry_ts"] = _to_ny(df["signal_ts"])
    df["exit_ts"] = _to_ny(df["exit_ts"])
    df["entry_price"] = pd.to_numeric(df["entry"], errors="coerce")
    df["book"] = book
    df["symbol"] = "NQ"
    df["family"] = "nq_5m_large_candle"
    df["dow"] = df["entry_ts"].dt.day_name()
    df["hour_ny"] = df["entry_ts"].dt.hour
    df["month"] = df["entry_ts"].dt.month
    df["year"] = df["entry_ts"].dt.year
    df["week_of_month"] = ((df["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    if "session_date" not in df.columns:
        df["session_date"] = df["entry_ts"].dt.strftime("%Y-%m-%d")
    return df


def attach_trade_po_labels(camp: pd.DataFrame, bars: pd.DataFrame) -> pd.DataFrame:
    """Copy bar-level PO labels onto trades via signal timestamp."""
    if camp.empty:
        return camp
    feat = bars[
        [
            "ts",
            "po_state",
            "po_side",
            "po_outcome",
            "candle_vs_po",
        ]
    ].rename(columns={"ts": "bar_ts"})
    left = camp.sort_values("entry_ts")
    merged = pd.merge_asof(
        left,
        feat.sort_values("bar_ts"),
        left_on="entry_ts",
        right_on="bar_ts",
        direction="backward",
    )
    out = camp.copy()
    for col in ("po_state", "po_side", "po_outcome", "candle_vs_po"):
        out[col] = merged[col].values
    out["trade_vs_po"] = np.where(
        out["po_side"].isin(["long", "short"]),
        np.where(out["side"] == out["po_side"], "trade_with_po", "trade_against_po"),
        "no_po",
    )
    out["regime"] = np.where(
        (out["po_state"] == "during_po") & (out["trade_vs_po"] == "trade_with_po"),
        "during_counter_with_po",
        np.where(
            (out["po_state"] == "during_po") & (out["trade_vs_po"] == "trade_against_po"),
            "during_with_prior_trend",
            np.where(
                (out["po_state"] == "after_po") & (out["trade_vs_po"] == "trade_against_po"),
                "after_continuation",
                np.where(
                    (out["po_state"] == "after_po") & (out["trade_vs_po"] == "trade_with_po"),
                    "after_still_fading",
                    "no_po",
                ),
            ),
        ),
    )
    return out


def profile_frame(df: pd.DataFrame, extra: Sequence[Tuple[str, str]], min_n: int) -> Tuple[pd.DataFrame, Dict[str, float], List[dict]]:
    if df is None or df.empty:
        return pd.DataFrame(), {"n": 0, "wr": 0.0, "avg": 0.0, "net": 0.0, "ns": 0.0}, []
    all_nets = df["net_usd"].to_numpy(float)
    baseline = score_nets(all_nets)
    rows: List[dict] = []
    notables: List[dict] = []
    cols = list(CONDITION_COLS) + list(extra)
    n0 = max(int(baseline["n"]), 1)
    for col, title in cols:
        if col not in df.columns:
            continue
        for val, g in df.groupby(col, dropna=False):
            stats = summarize_bucket(g, baseline)
            if stats.get("n", 0) < min_n:
                continue
            mask = (df[col].astype(str) == str(val)).to_numpy()
            cov = float(mask.mean()) if len(mask) else 0.0
            row = {
                "book": str(df["book"].iloc[0]) if "book" in df.columns else "",
                "condition": title,
                "bucket": str(val),
                "feature": feature_family(title) if title in dict(CONDITION_COLS).values() else "po_overlay",
                "coverage": cov,
                "causal_live_ready": title in CAUSAL_LIVE_READY or col.startswith("po_") or col in ("candle_vs_po", "trade_vs_po", "regime"),
                "needs_proxy": title in NEEDS_LIVE_PROXY,
                **stats,
            }
            row["ns"] = score_nets(g["net_usd"].to_numpy(float))["ns"]
            rows.append(row)
            scale = max(abs(baseline["avg"]), 1.0)
            notable = (
                stats["n"] >= min_n
                and stats["avg_lift"] > 0
                and stats["wr_lift_pp"] > 0
                and (abs(stats["z_wr"]) >= 1.64 or abs(stats["avg_lift"]) >= 0.35 * scale)
                and not str(val).endswith("_na")
                and str(val) not in {"na", "no_po", "pending", "none"}
            )
            if notable:
                notables.append(row)
    table = pd.DataFrame(rows)
    if not table.empty:
        table = table.sort_values(["z_wr", "avg_lift"], ascending=False).reset_index(drop=True)
    return table, baseline, notables


def compare_current_hp(books: Dict[str, pd.DataFrame], po_buckets: Optional[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    po_map = {}
    if po_buckets is not None and not po_buckets.empty:
        for _, r in po_buckets.iterrows():
            po_map[(str(r["condition"]), str(r["bucket"]))] = r
    for book_name, df in books.items():
        if df is None or df.empty:
            continue
        base = score_nets(df["net_usd"].to_numpy(float))
        for col, bucket, title in CURRENT_HP:
            if col not in df.columns:
                continue
            g = df[df[col].astype(str) == str(bucket)]
            sc = score_nets(g["net_usd"].to_numpy(float)) if len(g) else {"n": 0}
            po = po_map.get((title, str(bucket)))
            rows.append(
                {
                    "book": book_name,
                    "condition": title,
                    "bucket": bucket,
                    "n": sc.get("n", 0),
                    "wr": sc.get("wr", 0.0),
                    "avg": sc.get("avg", 0.0),
                    "net": sc.get("net", 0.0),
                    "ns": sc.get("ns", 0.0),
                    "wr_vs_book_pp": 100.0 * (sc["wr"] - base["wr"]) if sc.get("n", 0) else 0.0,
                    "avg_vs_book": (sc["avg"] - base["avg"]) if sc.get("n", 0) else 0.0,
                    "po_n": int(po["n"]) if po is not None else None,
                    "po_wr": float(po["wr"]) if po is not None else None,
                    "po_avg_lift": float(po["avg_lift"]) if po is not None else None,
                    "po_z_wr": float(po["z_wr"]) if po is not None else None,
                }
            )
    return pd.DataFrame(rows)


def _md_book_row(b: dict) -> str:
    if not b.get("n"):
        return "| %s | 0 | — | — | — | — | — | — |" % b.get("label", "")
    return "| %s | %d | %.1f%% | $%.0f | $%.0f | $%.0f | %.2f | %.2f |" % (
        b["label"],
        b["n"],
        100 * b["wr"],
        b["avg"],
        b["net"],
        b["stress"],
        b["ns"],
        b.get("pf", 0.0),
    )


def write_report(
    *,
    core: List[dict],
    hp_sleeves: List[dict],
    notables_by_book: Dict[str, List[dict]],
    current_cmp: pd.DataFrame,
    po_n: int,
) -> None:
    lines = [
        "# NQ 5m large-candle HA (high-probability conditions)",
        "",
        "Diagnostic only — not a promotion gate. HA here means **condition lift**, same mill as midnight-open / futures HP.",
        "",
        "Universe: NQ RTH 09:30–16:00 5m, **p90 range** candles (causal expanding threshold).",
        "Follow = candle direction from close, SL at open. Fade = opposite from close, SL = reflection of open across close (same body risk).",
        "1R target = 1× body; 3R = 3× body. Non-overlapping. Flatten 16:00. $1.50 fee, $20/pt.",
        "",
        "Prior-opposed overlay: NQ v2b resting-limit `nq_prior_opposed_rl` (%d campaigns). "
        "**during_po** = bar inside a live PO campaign. **after_po** = same session after that campaign's exit "
        "(outcome is then causal). Implied ST = opposite of PO side."
        % po_n,
        "",
        "Fair WR with no edge ≈ **25% at 3R**, ≈ **50% at 1R**.",
        "",
        "## Core books (all p90 large candles)",
        "",
        "| Book | n | WR | avg | net | stress | N/S | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email = [
        "potions: NQ 5m large-candle HA complete",
        "",
        "Hub: %s" % HUB.resolve(),
        "PO book: %s (%d campaigns)" % (PO_BOOK, po_n),
        "",
        "Core p90 books:",
    ]
    for b in core:
        lines.append(_md_book_row(b))
        if b.get("n"):
            email.append(
                "  %s  n=%d WR=%.0f%% net=$%.0f N/S=%.2f"
                % (b["label"], b["n"], 100 * b["wr"], b["net"], b["ns"])
            )
    lines += [
        "",
        "## HP regime sleeves (filtered signals, own non-overlap)",
        "",
        "during fade-ST = during PO, large candle *with implied ST*, **fade** it (counter-trend with PO).",
        "after follow-ST = after PO exit, large candle *with implied ST*, **follow** it (continuation).",
        "after-loss follow-ST = same continuation, only when PO already lost (trend punched through the fade).",
        "after-win fade-ST = after a PO win, fade remaining ST-direction candles (do not continue the old trend).",
        "",
        "| Sleeve | n | WR | avg | net | stress | N/S | PF |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    email.append("")
    email.append("HP regime sleeves:")
    for b in hp_sleeves:
        lines.append(_md_book_row(b))
        if b.get("n"):
            email.append(
                "  %s  n=%d WR=%.0f%% net=$%.0f N/S=%.2f"
                % (b["label"], b["n"], 100 * b["wr"], b["net"], b["ns"])
            )

    lines += [
        "",
        "## vs current NQ prior-opposed HP buckets",
        "",
        "Same condition=bucket that we already use on the PO book. Lift is vs **that 5m book’s** baseline, not vs PO.",
        "",
    ]
    if current_cmp is not None and not current_cmp.empty:
        lines += [
            "| 5m book | condition=bucket | n | WR | avg lift vs book | PO n | PO WR | PO avg lift |",
            "|---|---|---:|---:|---:|---:|---:|---:|",
        ]
        show = current_cmp.sort_values(["book", "wr_vs_book_pp"], ascending=[True, False])
        for _, r in show.iterrows():
            po_n_s = "—" if pd.isna(r.get("po_n", np.nan)) else str(int(r["po_n"]))
            po_wr_s = "—" if pd.isna(r.get("po_wr", np.nan)) else "%.0f%%" % (100 * float(r["po_wr"]))
            po_al = "—" if pd.isna(r.get("po_avg_lift", np.nan)) else "$%.0f" % float(r["po_avg_lift"])
            lines.append(
                "| %s | %s=%s | %d | %.1f%% | $%.0f | %s | %s | %s |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    int(r["n"]),
                    100 * float(r["wr"]),
                    float(r["avg_vs_book"]),
                    po_n_s,
                    po_wr_s,
                    po_al,
                )
            )
        lines.append("")

    lines += ["## Dual-lift notables (per 5m book)", ""]
    email.append("")
    email.append("Top notables:")
    for book, notes in notables_by_book.items():
        lines.append("### %s" % book)
        lines.append("")
        if not notes:
            lines.append("_none at min-N / dual-lift heuristic_")
            lines.append("")
            continue
        lines += [
            "| condition=bucket | n | WR lift pp | avg lift | z_WR | N/S |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        top = sorted(notes, key=lambda r: (r.get("z_wr", 0), r.get("avg_lift", 0)), reverse=True)[:12]
        for r in top:
            lines.append(
                "| %s=%s | %d | %+.1f | $%+.0f | %.2f | %.2f |"
                % (
                    r["condition"],
                    r["bucket"],
                    int(r["n"]),
                    float(r["wr_lift_pp"]),
                    float(r["avg_lift"]),
                    float(r["z_wr"]),
                    float(r.get("ns", 0.0)),
                )
            )
        lines.append("")
        if top:
            t0 = top[0]
            email.append(
                "  %s  %s=%s n=%d WRlift=%+.1fpp avglift=$%+.0f"
                % (book, t0["condition"], t0["bucket"], t0["n"], t0["wr_lift_pp"], t0["avg_lift"])
            )

    # Stance
    follow3 = next((b for b in core if b.get("label", "").startswith("follow 3R")), {})
    fade3 = next((b for b in core if b.get("label", "").startswith("fade 3R")), {})
    follow1 = next((b for b in core if b.get("label", "").startswith("follow 1R")), {})
    fade1 = next((b for b in core if b.get("label", "").startswith("fade 1R")), {})
    during = next((b for b in hp_sleeves if "during fade-ST 1R" in b.get("label", "")), {})
    after_loss = next((b for b in hp_sleeves if "after-loss" in b.get("label", "")), {})
    bits = []
    if fade1.get("n") and follow1.get("n"):
        bits.append(
            "1R fade WR %.0f%% vs follow %.0f%% (fair ~50%%)"
            % (100 * fade1["wr"], 100 * follow1["wr"])
        )
    if fade3.get("n") and follow3.get("n"):
        bits.append(
            "3R fade N/S %.2f vs follow %.2f (fair WR ~25%%)"
            % (fade3["ns"], follow3["ns"])
        )
    if during.get("n", 0) >= MIN_N_PO:
        bits.append(
            "during-PO fade-ST 1R n=%d WR=%.0f%% N/S=%.2f" % (during["n"], 100 * during["wr"], during["ns"])
        )
    if after_loss.get("n", 0) >= MIN_N_PO:
        bits.append(
            "after-PO-loss continuation 1R n=%d WR=%.0f%% N/S=%.2f"
            % (after_loss["n"], 100 * after_loss["wr"], after_loss["ns"])
        )
    stance = (
        "Curious diagnostic only. "
        + ("; ".join(bits) if bits else "See tables.")
        + " Do not promote from this mill alone."
    )
    lines += ["## Stance", "", stance, "", "Hub: `%s`" % HUB.resolve(), ""]
    email += ["", "Stance: %s" % stance, ""]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (HUB / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def run(*, email: bool, smoke: bool) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    try:
        _progress("load 5m ...")
        bars = load_rth_5m()
        if smoke:
            dates = bars["session_date"].drop_duplicates()
            keep = set(dates.tail(400))
            bars = bars[bars["session_date"].isin(keep)].reset_index(drop=True)
            _progress("SMOKE bars=%s" % f"{len(bars):,}")
        bars = classify(bars)
        ready = bars[bars["p90_thr"].notna()].copy()
        po = load_po_campaigns()
        if smoke:
            po = po[po["session_date"].isin(set(ready["session_date"]))].copy()
        ready = attach_po_context(ready, po)

        books_walk = [
            ("follow_3r", "follow 3R p90", "is_p90", 3.0, False),
            ("fade_3r", "fade 3R p90", "is_p90", 3.0, True),
            ("follow_1r", "follow 1R p90", "is_p90", 1.0, False),
            ("fade_1r", "fade 1R p90", "is_p90", 1.0, True),
        ]
        hp_walk = [
            ("hp_during_fade_st_3r", "during fade-ST 3R", "hp_during_fade_st", 3.0, True),
            ("hp_during_fade_st_1r", "during fade-ST 1R", "hp_during_fade_st", 1.0, True),
            ("hp_during_any_fade_1r", "during any fade 1R", "hp_during_any", 1.0, True),
            ("hp_after_follow_st_3r", "after follow-ST 3R", "hp_after_follow_st", 3.0, False),
            ("hp_after_follow_st_1r", "after follow-ST 1R", "hp_after_follow_st", 1.0, False),
            ("hp_after_loss_follow_st_1r", "after-loss follow-ST 1R", "hp_after_loss_follow_st", 1.0, False),
            ("hp_after_win_fade_st_1r", "after-win fade-ST 1R", "hp_after_win_fade_st", 1.0, True),
        ]

        walked: Dict[str, pd.DataFrame] = {}
        core_sum: List[dict] = []
        hp_sum: List[dict] = []
        for key, label, flag, r, fade in books_walk + hp_walk:
            _progress("walk %s ..." % key)
            tr = walk_trades(ready, flag, r_mult=r, fade=fade)
            walked[key] = tr
            if not tr.empty:
                tr.to_csv(HUB / ("trades_%s.csv" % key), index=False)
            _progress("  %s n=%d" % (key, len(tr)))
            sc = summarize_book(tr, label)
            if (key, label, flag, r, fade) in books_walk:
                core_sum.append(sc)
            else:
                hp_sum.append(sc)

        # Annotate core books with futures HP features (side-dependent aligns).
        annotated: Dict[str, pd.DataFrame] = {}
        notables_by_book: Dict[str, List[dict]] = {}
        for key, label, _, _, _ in books_walk:
            tr = walked[key]
            _progress("annotate %s n=%d ..." % (key, len(tr)))
            camp = trades_to_campaigns(tr, key)
            if camp.empty:
                annotated[key] = camp
                notables_by_book[key] = []
                continue
            camp = annotate_campaigns(camp, "NQ")
            camp = attach_trade_po_labels(camp, ready)
            camp.to_csv(HUB / ("%s_campaigns.csv" % key), index=False)
            table, _base, notables = profile_frame(camp, EXTRA_CONDS, MIN_N)
            if not table.empty:
                table.to_csv(HUB / ("%s_buckets.csv" % key), index=False)
            annotated[key] = camp
            notables_by_book[key] = notables
            _progress("  notables=%d" % len(notables))

        po_buckets = None
        ppath = FUT_PROFILE / "nq_prior_opposed_rl_buckets.csv"
        if ppath.exists():
            po_buckets = pd.read_csv(ppath)
        current_cmp = compare_current_hp(annotated, po_buckets)
        if not current_cmp.empty:
            current_cmp.to_csv(HUB / "vs_current_hp.csv", index=False)

        pd.DataFrame(core_sum + hp_sum).to_csv(HUB / "books.csv", index=False)
        write_report(
            core=core_sum,
            hp_sleeves=hp_sum,
            notables_by_book=notables_by_book,
            current_cmp=current_cmp,
            po_n=int(len(po)),
        )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "smoke": smoke, "po_n": int(len(po))}, indent=2) + "\n",
            encoding="utf-8",
        )
        _progress("DONE")
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NQ 5m large-candle HA FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ 5m large-candle HA FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: NQ 5m large-candle HA complete",
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
