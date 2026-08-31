"""Signal-hour attribution for retired US30 fair-3R ST+PMC campaigns.

Diagnostic only (no new strategy edge). Reconstructs each retired 1mfill
fair-3R trade against the signal hour that armed it under the old left-label
timing, and measures what remained after a causal hour close.

Source fills: ``live/state/us30_st_pmc_retest_add_experiment/.../sl50_tp150_3r_1mfill``
(pre–completed-hour fix; lot-correct N/S ≈ 29.39 / raw MTM ≈ 20.97).

Usage:
  python -m live.us30_st_pmc_signal_hour_attribution --email
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "us30_st_pmc_signal_hour_attribution"
RETIRED_STATE = (
    REPO
    / "live"
    / "state"
    / "us30_st_pmc_retest_add_experiment"
    / "states"
    / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"
)
ONE_M = REPO / "fx" / "us30_1m.csv"
SYM = "US30"
STOP_PTS = 50.0
TARGET_PTS = 150.0
NY = "America/New_York"
POST_CLOSE_LOOK_HOURS = 24


def _ts(value: object) -> Optional[pd.Timestamp]:
    if value is None or str(value).strip() == "":
        return None
    try:
        ts = pd.Timestamp(str(value))
    except Exception:
        return None
    if ts.tzinfo is None:
        return ts.tz_localize(NY)
    return ts.tz_convert(NY)


def _load_campaigns(state: Path) -> pd.DataFrame:
    fills = pd.read_csv(state / "fills.csv")
    orders = pd.read_csv(state / "orders.csv")
    entries = fills[fills["reason"] == "entry"].copy()
    exits = fills[fills["reason"].isin({"stop", "target"})].copy()
    merged = entries.merge(
        orders[
            [
                "broker_order_id",
                "live_after_ts",
                "limit_price",
                "created_at",
                "side",
            ]
        ],
        on="broker_order_id",
        how="left",
        suffixes=("", "_ord"),
    )
    exit_by_trade = (
        exits.sort_values("ts")
        .groupby("trade_id", as_index=False)
        .tail(1)[["trade_id", "ts", "price", "reason"]]
        .rename(columns={"ts": "exit_ts", "price": "exit_price", "reason": "exit_reason"})
    )
    out = merged.merge(exit_by_trade, on="trade_id", how="left")
    out["entry_ts"] = out["ts"].map(_ts)
    out["old_assumed_signal_ts"] = out["live_after_ts"].map(_ts)
    out["exit_ts"] = out["exit_ts"].map(_ts)
    out["old_entry_price"] = pd.to_numeric(out["price"], errors="coerce")
    out["limit_price"] = pd.to_numeric(out["limit_price"], errors="coerce")
    out["side"] = out["side"].astype(str).str.lower()
    return out.dropna(subset=["entry_ts", "old_assumed_signal_ts", "old_entry_price", "limit_price"])


def _slice_1m(one_m: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    lo = one_m.index.searchsorted(start, side="left")
    hi = one_m.index.searchsorted(end, side="left")
    if lo >= hi:
        return one_m.iloc[0:0]
    return one_m.iloc[lo:hi]


def _first_limit_touch(
    window: pd.DataFrame,
    *,
    side: str,
    limit: float,
) -> Tuple[Optional[pd.Timestamp], Optional[float]]:
    if window.empty:
        return None, None
    if side == "buy":
        hits = window[window["low"] <= limit + 1e-9]
    else:
        hits = window[window["high"] >= limit - 1e-9]
    if hits.empty:
        return None, None
    ts = pd.Timestamp(hits.index[0])
    return ts, float(limit)


def _mfe_mae(
    window: pd.DataFrame,
    *,
    side: str,
    entry: float,
) -> Tuple[float, float, bool, bool]:
    if window.empty:
        return 0.0, 0.0, False, False
    high = float(window["high"].max())
    low = float(window["low"].min())
    if side == "buy":
        fav = high - entry
        adv = entry - low
        target_hit = high >= entry + TARGET_PTS - 1e-9
        stop_hit = low <= entry - STOP_PTS + 1e-9
    else:
        fav = entry - low
        adv = high - entry
        target_hit = low <= entry - TARGET_PTS + 1e-9
        stop_hit = high >= entry + STOP_PTS - 1e-9
    return float(fav), float(adv), bool(target_hit), bool(stop_hit)


def _first_extreme_break(
    window: pd.DataFrame,
    *,
    side: str,
    hour_high: float,
    hour_low: float,
) -> Optional[pd.Timestamp]:
    if window.empty:
        return None
    if side == "buy":
        hits = window[window["high"] >= hour_high - 1e-9]
    else:
        hits = window[window["low"] <= hour_low + 1e-9]
    if hits.empty:
        return None
    return pd.Timestamp(hits.index[0])


def attribute_row(row: pd.Series, one_m: pd.DataFrame) -> Dict[str, Any]:
    side = str(row["side"])
    hour_start = pd.Timestamp(row["old_assumed_signal_ts"])
    hour_close = hour_start + pd.Timedelta(hours=1)
    entry_ts = pd.Timestamp(row["entry_ts"])
    limit = float(row["limit_price"])
    entry_px = float(row["old_entry_price"])

    intra = _slice_1m(one_m, hour_start, hour_close)
    hour_high = float(intra["high"].max()) if not intra.empty else float("nan")
    hour_low = float(intra["low"].min()) if not intra.empty else float("nan")

    fav, adv, tgt_before, stop_before = _mfe_mae(intra, side=side, entry=entry_px)

    post_end = hour_close + pd.Timedelta(hours=POST_CLOSE_LOOK_HOURS)
    post = _slice_1m(one_m, hour_close, post_end)
    causal_ts, causal_px = _first_limit_touch(post, side=side, limit=limit)
    retest_flag = causal_ts is not None
    time_to_retest_min = (
        (causal_ts - hour_close).total_seconds() / 60.0 if causal_ts is not None else float("nan")
    )

    break_ts = None
    if pd.notna(hour_high) and pd.notna(hour_low):
        break_ts = _first_extreme_break(post, side=side, hour_high=hour_high, hour_low=hour_low)
    cont_flag = break_ts is not None
    time_to_break_min = (
        (break_ts - hour_close).total_seconds() / 60.0 if break_ts is not None else float("nan")
    )

    same_hour = bool(entry_ts < hour_close)
    bucket = "same_hour_lookahead_fill" if same_hour else "post_close_fill_under_old_arming"
    if same_hour and tgt_before and not stop_before:
        bucket = "same_hour_target_before_close"
    elif same_hour and stop_before:
        bucket = "same_hour_stop_before_close"

    return {
        "trade_id": row["trade_id"],
        "side": side,
        "hour_start_ts": hour_start.isoformat(),
        "hour_close_ts": hour_close.isoformat(),
        "old_assumed_entry_ts": entry_ts.isoformat(),
        "earliest_causal_entry_ts": causal_ts.isoformat() if causal_ts is not None else "",
        "old_entry_price": round(entry_px, 6),
        "first_causal_executable_price": round(causal_px, 6) if causal_px is not None else "",
        "limit_price": round(limit, 6),
        "max_favorable_move_before_hour_close": round(fav, 4),
        "max_adverse_move_before_hour_close": round(adv, 4),
        "target_reached_before_hour_close": int(tgt_before),
        "stop_reached_before_hour_close": int(stop_before),
        "post_close_retest_flag": int(retest_flag),
        "post_close_continuation_flag": int(cont_flag),
        "post_close_time_to_retest_min": round(time_to_retest_min, 2)
        if pd.notna(time_to_retest_min)
        else "",
        "post_close_time_to_break_signal_hour_high_low_min": round(time_to_break_min, 2)
        if pd.notna(time_to_break_min)
        else "",
        "same_hour_fill": int(same_hour),
        "bucket": bucket,
        "exit_reason": str(row.get("exit_reason") or ""),
        "exit_ts": row["exit_ts"].isoformat() if pd.notna(row.get("exit_ts")) else "",
    }


def write_demo_decision(hub: Path) -> None:
    text = """# Demo decision — demo_us30_hourly_st_pmc

```yaml
demo_us30_hourly_st_pmc:
  alpha_status: invalidated
  action_preferred: stop
  action_if_retained:
    purpose: "OANDA lifecycle / broker reconciliation control only"
    quantity: minimum
    risk_budget: zero
    performance_reporting: excluded
    deadline: "fixed — stop alpha reporting immediately; sunsets after 20 further campaigns or 2026-09-30, whichever first"
```

Do **not** continue calling it an alpha demo. Paper/live P&L from this book must not
affect conclusions about the US30 ST+PMC strategy. The old fair-3R N/S 29.39 record
is an audit lesson under invalid left-label timing; revival requires a **new**
causal mechanism (paths A/B/C), not an exit tweak.
"""
    (hub / "DEMO_DECISION.md").write_text(text, encoding="utf-8")


def write_summary(hub: Path, rows: List[Dict[str, Any]]) -> None:
    df = pd.DataFrame(rows)
    n = len(df)
    same = int(df["same_hour_fill"].sum()) if n else 0
    retest = int(df["post_close_retest_flag"].sum()) if n else 0
    cont = int(df["post_close_continuation_flag"].sum()) if n else 0
    tgt = int(df["target_reached_before_hour_close"].sum()) if n else 0
    stp = int(df["stop_reached_before_hour_close"].sum()) if n else 0
    bucket_counts = df["bucket"].value_counts().to_dict() if n else {}
    lines = [
        "# US30 ST+PMC signal-hour attribution (retired fair-3R)",
        "",
        "Source: pre–completed-hour `sl50_tp150_3r_1mfill` campaigns "
        "(N/S 29.39 lot-correct / ~20.97 raw MTM). Diagnostic only.",
        "",
        "## Headline",
        "",
        "- Campaigns attributed: **%d**" % n,
        "- Same-hour fills under old arming: **%d (%.1f%%)**" % (same, 100.0 * same / n if n else 0),
        "- Target reached before hour close: **%d**" % tgt,
        "- Stop reached before hour close: **%d**" % stp,
        "- Post-close ST-limit retest within %dh: **%d (%.1f%%)**"
        % (POST_CLOSE_LOOK_HOURS, retest, 100.0 * retest / n if n else 0),
        "- Post-close continuation (break signal-hour H/L) within %dh: **%d (%.1f%%)**"
        % (POST_CLOSE_LOOK_HOURS, cont, 100.0 * cont / n if n else 0),
        "",
        "## Buckets",
        "",
        "| bucket | n |",
        "|---|---:|",
    ]
    for k, v in sorted(bucket_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        lines.append("| `%s` | %d |" % (k, v))
    lines += [
        "",
        "## Fields",
        "",
        "Per-trade CSV: `attribution.csv` — hour_start/close, old vs earliest causal "
        "entry, MFE/MAE before hour close, post-close retest/continuation flags.",
        "",
        "## Demo decision",
        "",
        "See [`DEMO_DECISION.md`](DEMO_DECISION.md). Alpha status: **invalidated**.",
        "",
        "## Next",
        "",
        "Paths A/B/C are **new** causal strategies — hub "
        "`live/state/us30_st_pmc_causal_revival_abc/`.",
        "",
    ]
    (hub / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email = [
        "US30 ST+PMC signal-hour attribution complete.",
        "Hub: %s" % hub,
        "Campaigns: %d | same-hour fills: %d (%.1f%%) | post-close retest: %d | continuation: %d"
        % (n, same, 100.0 * same / n if n else 0, retest, cont),
        "Demo decision: alpha_status=invalidated; prefer stop (lifecycle-only if retained).",
        "Next: causal revival matrix A/B/C (no inheritance of N/S 29.39).",
    ]
    (hub / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="Optional row cap for smoke.")
    args = ap.parse_args()

    HUB.mkdir(parents=True, exist_ok=True)
    rid = begin_run(
        run_class="pandas",
        variant_slug="us30_st_pmc_signal_hour_attribution",
        instrument="US30",
        hub_path=str(HUB.relative_to(REPO)),
        notes="retired fair-3R signal-hour attribution",
        meta={"source": str(RETIRED_STATE)},
    )
    try:
        print("Loading retired campaigns…", flush=True)
        camps = _load_campaigns(RETIRED_STATE)
        if args.limit and args.limit > 0:
            camps = camps.head(int(args.limit))
        print("Campaigns: %d" % len(camps), flush=True)
        print("Loading US30 1m…", flush=True)
        gby = load_fx_1m_by_ny_date(ONE_M, SYM)
        one_m = concat_all_1m(gby)
        if one_m.index.tz is None:
            one_m.index = one_m.index.tz_localize(NY)
        else:
            one_m.index = one_m.index.tz_convert(NY)
        print("1m bars: %d" % len(one_m), flush=True)

        rows: List[Dict[str, Any]] = []
        for i, (_, row) in enumerate(camps.iterrows(), start=1):
            rows.append(attribute_row(row, one_m))
            if i % 100 == 0 or i == len(camps):
                print("  attributed %d/%d" % (i, len(camps)), flush=True)

        out_csv = HUB / "attribution.csv"
        with out_csv.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else ["trade_id"])
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        write_demo_decision(HUB)
        write_summary(HUB, rows)
        (HUB / "meta.json").write_text(
            json.dumps(
                {
                    "source_state": str(RETIRED_STATE),
                    "n": len(rows),
                    "stop_pts": STOP_PTS,
                    "target_pts": TARGET_PTS,
                    "post_close_look_hours": POST_CLOSE_LOOK_HOURS,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        df = pd.DataFrame(rows)
        complete_run(
            rid,
            trades=len(rows),
            meta={
                "same_hour_fills": int(df["same_hour_fill"].sum()) if len(df) else 0,
                "post_close_retest": int(df["post_close_retest_flag"].sum()) if len(df) else 0,
                "post_close_continuation": int(df["post_close_continuation_flag"].sum())
                if len(df)
                else 0,
            },
            notes="attribution diagnostic complete",
        )
        if args.email:
            send_email(
                subject="potions: US30 ST+PMC signal-hour attribution complete",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        print("Wrote %s" % HUB, flush=True)
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        if args.email:
            send_email(
                subject="potions: US30 ST+PMC signal-hour attribution FAILED",
                body="Hub: %s\nError: %s" % (HUB, exc),
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
