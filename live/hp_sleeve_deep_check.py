"""Deep-check HP sleeves from condition-profile campaign tapes (linear size scaling).

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.hp_sleeve_deep_check --email
    python -m live.hp_sleeve_deep_check --email --only nq es eurusd
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
from live.futures_intraday_hp_size_liquidity_yearly import yearly_250k
from live.futures_intraday_hp_sizeup_lib import COND_COL as FUT_COND
from live.futures_intraday_hp_sizeup_lib import PROFILE_HUB as FUT_PROFILE
from live.intraday_condition_overlay import hp_mask, score_nets
from live.fx_v2b_london_ungated import REPO
from live.instrument_deep_check import (
    BookPaths,
    add_daily_atr,
    add_quartiles,
    add_range_width,
    exit_reason_contribution,
    rolling_metrics,
    summarize_group,
    timing_distributions,
    write_email_bodies,
    write_robustness_md,
    write_yearly_md,
    yearly_from_equity,
)
from live.notify_email import send_email

FX_PROFILE = REPO / "live" / "state" / "intraday_condition_profile"
HUB = REPO / "live" / "state" / "hp_sleeve_deep_check"
NY = "America/New_York"

SLEEVES = {
    "nq": (
        "NQ OR-norm @40×",
        "nq_prior_opposed_rl",
        "Opening 15m range vs ATR",
        "or_norm",
        "fut",
        40.0,
        "NQ",
    ),
    "es": (
        "ES ST-age>180m @40×",
        "es_prior_opposed_legacy",
        "ST-event age",
        "st_age_gt180m",
        "fut",
        40.0,
        "ES",
    ),
    "eurusd": (
        "EURUSD ST+PMC Thu @200k-stress",
        "eurusd_st_pmc_3r",
        "Day of week",
        "Thursday",
        "fx",
        None,  # computed from target stress
        "EURUSD",
    ),
}

EURUSD_STRESS_TARGET = 200_000.0


def _parse_exit(path: str, *, win: Optional[bool] = None) -> Tuple[str, bool, bool, bool]:
    if not path or (isinstance(path, float) and math.isnan(path)):
        if win is True:
            return "tp_or_runner", True, False, False
        if win is False:
            return "stop", False, False, True
        return "", False, False, False
    reasons = [p for p in str(path).split("|") if p]
    reason_set = sorted(set(reasons))
    stop_tags = {"wide_stop", "stop", "runner_stop", "be_stop"}
    hit_tp = any(r.startswith("tp") for r in reason_set)
    eod = any(r in {"eod_close", "eod"} for r in reason_set)
    full_initial_sl = bool(reason_set) and set(reason_set).issubset({"wide_stop", "stop"})
    return ",".join(reason_set), hit_tp, eod, full_initial_sl


def _load_profile(book: str, cond: str, bucket: str, kind: str) -> Tuple[pd.DataFrame, np.ndarray]:
    # FUT_COND maps profile titles → columns for both futures and FX books.
    overlay.COND_COL.clear()
    overlay.COND_COL.update(FUT_COND)
    prof = FUT_PROFILE if kind == "fut" else FX_PROFILE
    camp = pd.read_csv(prof / "all_campaigns.csv")
    camp["entry_ts"] = pd.to_datetime(camp["entry_ts"], utc=True).dt.tz_convert(NY)
    camp["exit_ts"] = pd.to_datetime(camp["exit_ts"], utc=True).dt.tz_convert(NY)
    df = camp[camp["book"] == book].sort_values("entry_ts").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("empty book %s" % book)
    m = hp_mask(df, cond, bucket)
    if not m.any():
        raise RuntimeError("empty HP mask %s %s=%s" % (book, cond, bucket))
    return df, np.asarray(m, dtype=bool)


def _mult_for_stress(df: pd.DataFrame, m: np.ndarray, target: float) -> float:
    base = df["net_usd"].to_numpy(float)
    ref = score_nets(base)
    if ref["stress"] <= 0:
        raise RuntimeError("baseline stress is zero")
    # Linear HP scaling: stress scales ~linearly with mult on HP-only uplift path.
    for probe in (40.0, 20.0, 10.0, 4.0, 2.0, 1.25):
        sized = base.copy()
        sized[m] = sized[m] * probe
        if score_nets(sized)["stress"] > 0:
            return probe * (target / score_nets(sized)["stress"])
    return target / ref["stress"]


def profile_to_campaigns(df: pd.DataFrame, m: np.ndarray, mult: float, symbol: str) -> pd.DataFrame:
    nets = df["net_usd"].to_numpy(float).copy()
    nets[m] = nets[m] * float(mult)
    rows = []
    for idx, row in df.iterrows():
        exit_reasons, hit_tp, eod, full_sl = _parse_exit(
            row.get("base_fill_path", ""),
            win=row.get("win") if "win" in df.columns else None,
        )
        rows.append(
            {
                "trade_id": str(row["trade_id"]),
                "session": str(row.get("session_date") or pd.Timestamp(row["entry_ts"]).date().isoformat()),
                "year": int(pd.Timestamp(row["entry_ts"]).year),
                "side": str(row.get("side") or "").lower(),
                "entry_ts": pd.Timestamp(row["entry_ts"]),
                "exit_ts": pd.Timestamp(row["exit_ts"]),
                "entry_price": float(row.get("entry_price") or 0.0),
                "entry_qty": int(row.get("entry_qty") or 1),
                "net_usd": float(nets[idx]),
                "exit_reasons": exit_reasons,
                "hit_tp": hit_tp,
                "eod_close": eod,
                "full_initial_sl": full_sl,
                "any_stop_exit": "stop" in exit_reasons or "wide_stop" in exit_reasons,
                "hp_flag": bool(m[idx]),
                "or15_width_pct": row.get("or15_width_pct"),
                "st_age_bucket": row.get("st_age_bucket"),
                "dow": row.get("dow"),
            }
        )
    return pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)


def _book_paths(slug: str, label: str, symbol: str, mult: float) -> BookPaths:
    strategy_id = "%s_hp_%sx" % (slug, str(mult).replace(".", "p"))
    out = HUB / slug
    daily = REPO / "fx" / ("%s_daily.csv" % symbol.lower())
    if symbol in {"NQ", "ES", "YM"}:
        daily = REPO / symbol.lower() / ("%s_daily.csv" % symbol.lower())
    from live.replay_audit import POINT_VALUES

    point_value = float(POINT_VALUES.get(symbol, 100_000.0))
    return BookPaths(
        state_root=HUB / slug,
        output_root=out,
        symbol=symbol,
        quote="USD",
        strategy_id=strategy_id,
        label=label,
        fills=None,
        unit_trades=None,
        equity_curve=None,
        orders=None,
        trades_csv=None,
        metrics=None,
        daily=daily if daily.exists() else None,
        point_value=point_value,
        tick=0.25 if symbol in {"NQ", "ES", "YM"} else 0.00001,
        fee_per_unit=1.5,
    )


def run_one(slug: str, *, email: bool = False) -> Path:
    label, book, cond, bucket, kind, mult_locked, symbol = SLEEVES[slug]
    df, m = _load_profile(book, cond, bucket, kind)
    mult = float(mult_locked) if mult_locked is not None else _mult_for_stress(df, m, EURUSD_STRESS_TARGET)
    if slug == "eurusd":
        label = "EURUSD ST+PMC Thu @%.2f× (~$200k stress)" % mult

    campaigns = profile_to_campaigns(df, m, mult, symbol)
    paths = _book_paths(slug, label, symbol, mult)
    if paths.output_root.exists():
        shutil.rmtree(paths.output_root)
    paths.output_root.mkdir(parents=True, exist_ok=True)

    campaigns = add_daily_atr(campaigns, paths.daily)
    campaigns = add_range_width(campaigns, paths)
    add_quartiles(campaigns, "atr14", "atr14_quartile")
    if campaigns["range_width"].notna().any():
        add_quartiles(campaigns, "range_width", "range_width_quartile")
    else:
        campaigns["range_width_quartile"] = ""

    yearly = yearly_from_equity(paths, campaigns)
    rolling = rolling_metrics(campaigns, 50)
    unit_contrib = exit_reason_contribution(paths, campaigns)
    stop_audit = pd.DataFrame()
    recovery = {
        "max_recovery_bars": 0.0,
        "max_recovery_calendar_days": 0.0,
        "unresolved_recovery_calendar_days": 0.0,
        "bars_in_drawdown_pct": 0.0,
    }
    entry_hour, exit_hour, timing = timing_distributions(campaigns)

    quartiles: Dict[str, pd.DataFrame] = {
        "ATR14 quartile": summarize_group(campaigns, "atr14_quartile"),
    }
    if campaigns["range_width_quartile"].astype(str).str.len().gt(0).any():
        quartiles["range quartile"] = summarize_group(campaigns, "range_width_quartile")
    if slug == "nq" and "or15_width_pct" in campaigns.columns:
        add_quartiles(campaigns, "or15_width_pct", "or_width_quartile")
        quartiles["OR width quartile"] = summarize_group(campaigns, "or_width_quartile")
    if slug == "es" and "st_age_bucket" in campaigns.columns:
        quartiles["ST age bucket"] = summarize_group(campaigns, "st_age_bucket")

    book = score_nets(campaigns["net_usd"].to_numpy(float))
    hp_only = score_nets(campaigns.loc[campaigns["hp_flag"], "net_usd"].to_numpy(float))
    meta = {
        "slug": slug,
        "label": label,
        "book": book,
        "hp_only": hp_only,
        "mult": mult,
        "hp_n": int(m.sum()),
        "n": int(len(df)),
        "condition": cond,
        "bucket": bucket,
    }
    (paths.output_root / "META.json").write_text(json.dumps(meta, indent=2) + "\n")

    campaigns.to_csv(paths.output_root / "campaigns_robustness.csv", index=False)
    yearly.to_csv(paths.output_root / "yearly_breakdown.csv", index=False)
    rolling.to_csv(paths.output_root / "rolling_50.csv", index=False)
    unit_contrib.to_csv(paths.output_root / "exit_reason_contribution.csv", index=False)
    entry_hour.to_csv(paths.output_root / "entry_hour_dist.csv", index=False)
    exit_hour.to_csv(paths.output_root / "exit_hour_dist.csv", index=False)
    campaigns.nlargest(10, "net_usd").to_csv(paths.output_root / "top_10_winners.csv", index=False)
    campaigns.nsmallest(10, "net_usd").to_csv(paths.output_root / "worst_10_losers.csv", index=False)
    for name, table in quartiles.items():
        table.to_csv(paths.output_root / ("%s.csv" % name.lower().replace(" ", "_")), index=False)

    write_yearly_md(paths, yearly, timing)
    write_robustness_md(
        paths,
        campaigns,
        yearly,
        rolling,
        unit_contrib,
        stop_audit,
        recovery,
        quartiles,
        timing,
        prior_opposed=slug in {"nq", "es"},
    )
    text, html_body = write_email_bodies(paths, yearly, timing, campaigns)
    (paths.output_root / "EMAIL.txt").write_text(text, encoding="utf-8")

    print("=== %s ===" % label, flush=True)
    print(
        "book net %s stress %s N/S %.2f | HP n=%d mult=%.2f×"
        % (
            "${:,.0f}".format(book["net"]),
            "${:,.0f}".format(book["stress"]),
            book["ns"],
            int(m.sum()),
            mult,
        ),
        flush=True,
    )
    print(text[:1200], flush=True)
    return paths.output_root


def run_all(*, only: Optional[Sequence[str]] = None, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    slugs = list(only) if only else list(SLEEVES)
    results = []
    for slug in slugs:
        if slug not in SLEEVES:
            raise ValueError("unknown sleeve %r (choose %s)" % (slug, ", ".join(SLEEVES)))
        results.append(run_one(slug, email=False))

    lines = [
        "potions: HP sleeve deep-check (no charts)",
        "",
        "Linear HP scaling on condition-profile campaign tapes. Research only.",
        "NQ/ES HP sleeves at 40×; EURUSD Thursday sleeve scaled to ~$200k book stress.",
        "",
    ]
    for slug in slugs:
        meta = json.loads((HUB / slug / "META.json").read_text())
        b = meta["book"]
        lines.append(
            "- %s: mult=%.2f× net $%s stress $%s N/S %.2f (HP %d / %d)"
            % (meta["label"], meta["mult"], "{:,.0f}".format(b["net"]), "{:,.0f}".format(b["stress"]), b["ns"], meta["hp_n"], meta["n"])
        )
        lines.append("  hub: live/state/hp_sleeve_deep_check/%s/" % slug)
    if "eurusd" in slugs:
        mult = json.loads((HUB / "eurusd" / "META.json").read_text())["mult"]
        lines.append("")
        lines.append("EURUSD scaled to ~$200k book stress → %.2f× (target $200,000)" % mult)
    body = "\n".join(lines) + "\n"
    (HUB / "EMAIL.txt").write_text(body)
    (HUB / "RUN_COMPLETE.json").write_text(json.dumps({"ok": True, "slugs": slugs}, indent=2) + "\n")
    print(body, flush=True)
    if email:
        send_email(subject="potions: HP sleeve deep-check (NQ/ES 40× + EURUSD ~200k stress)", body=body)
    return HUB


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--only", nargs="+", choices=sorted(SLEEVES))
    args = ap.parse_args(list(argv) if argv is not None else None)
    try:
        run_all(only=args.only, email=bool(args.email))
        return 0
    except Exception:
        if args.email:
            send_email(subject="potions: HP sleeve deep-check FAILED", body=traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
