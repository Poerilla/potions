"""Cross-market v2 quarterly-range: short path + 2w / 1w@2/week BB accumulate.

For each instrument hub with broker fills:
  - campaign attribution by side
  - short path MFE / early-fail diagnostics (same as NQ short issues)
  - accumulate counterfactuals: 2w_1perd_cap10 and 1w_2contracts_per_week

Hub root: ``live/state/quarterly_range_v2_cross_review/``
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from live.notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "live" / "state" / "quarterly_range_v2_cross_review"
FEE = 1.50

SPECS = {
    "YM": {
        "daily": REPO / "ym" / "ym_daily.csv",
        "h4": REPO / "ym" / "data" / "ym_front_month_4h_from_1m.csv",
        "pv": 5.0,
        "tick": 1.0,
        "broker_hub": REPO / "live" / "state" / "ym_quarterly_range_breakout_broker",
    },
    "MNQ": {
        "daily": REPO / "mnq" / "mnq_daily.csv",
        "h4": REPO / "mnq" / "data" / "mnq_front_month_4h_from_1m.csv",
        "pv": 2.0,
        "tick": 0.25,
        "broker_hub": REPO / "live" / "state" / "mnq_quarterly_range_breakout_broker",
    },
    "ES": {
        "daily": REPO / "es" / "es_daily.csv",
        "h4": REPO / "es" / "data" / "es_front_month_4h_from_1m.csv",
        "pv": 50.0,
        "tick": 0.25,
        "broker_hub": REPO / "live" / "state" / "es_quarterly_range_breakout_broker",
    },
    "NQ": {
        "daily": REPO / "nq" / "nq_daily.csv",
        "h4": REPO / "nq" / "data" / "nq_front_month_4h_from_1m.csv",
        "pv": 20.0,
        "tick": 0.25,
        "broker_hub": REPO / "live" / "state" / "nq_quarterly_range_breakout_broker",
    },
}


def parse_ts(s):
    ts = pd.to_datetime(str(s).replace("Z", ""), utc=False, errors="coerce")
    if getattr(ts, "tzinfo", None) is not None:
        try:
            ts = ts.tz_convert("America/New_York").tz_localize(None)
        except (TypeError, AttributeError, ValueError):
            ts = ts.tz_localize(None)
    return pd.Timestamp(ts)


def findcol(df, *names):
    low = {c.lower(): c for c in df.columns}
    for n in names:
        if n in low:
            return low[n]
    raise KeyError(names)


def load_daily(path: Path) -> pd.DataFrame:
    daily = pd.read_csv(path)
    ts_c = findcol(daily, "ts", "time", "date", "datetime")
    daily["ts"] = pd.to_datetime(daily[ts_c], errors="coerce")
    if getattr(daily["ts"].dt, "tz", None) is not None:
        daily["ts"] = daily["ts"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    daily = daily.sort_values("ts").reset_index(drop=True)
    for name in ("open", "high", "low", "close"):
        daily[name] = daily[findcol(daily, name)].astype(float)
    daily["date"] = daily["ts"].dt.normalize()
    daily["qkey"] = (
        daily["ts"].dt.year.astype(str)
        + "Q"
        + (((daily["ts"].dt.month - 1) // 3) + 1).astype(str)
    )
    return daily


def load_h4(path: Path, slip: float) -> pd.DataFrame:
    h4 = pd.read_csv(path)
    ts_c = findcol(h4, "time", "ts", "datetime")
    h4["ts"] = pd.to_datetime(h4[ts_c], errors="coerce", utc=True)
    # Keep exchange-local calendar date for day matching with daily bars.
    h4["ts"] = h4["ts"].dt.tz_convert("America/New_York").dt.tz_localize(None)
    h4 = h4.sort_values("ts").reset_index(drop=True)
    for name in ("open", "high", "low", "close"):
        h4[name] = h4[findcol(h4, name)].astype(float)
    h4["bb_mid"] = h4["close"].rolling(20).mean()
    if "date" in {c.lower() for c in h4.columns}:
        date_c = findcol(h4, "date")
        h4["date"] = pd.to_datetime(h4[date_c], errors="coerce").dt.normalize()
    else:
        h4["date"] = h4["ts"].dt.normalize()
    h4.attrs["slip"] = slip
    return h4


def fills_to_campaigns(fills_path: Path, pv: float) -> pd.DataFrame:
    fills = pd.read_csv(fills_path)
    fills["ts"] = fills["ts"].map(parse_ts)
    fills = fills.sort_values("ts").reset_index(drop=True)
    campaigns = []
    for trade_id, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entry_rows = g[g["reason"] == "entry"]
        if entry_rows.empty:
            continue
        er = entry_rows.iloc[0]
        side = "long" if str(er["side"]).lower() in ("buy", "long") else "short"
        lots: List[List[float]] = []
        realized = 0.0
        fees = 0.0
        exit_reasons = []
        scale_hits = []
        for _, r in g.iterrows():
            reason = str(r["reason"])
            px = float(r["price"])
            qty = int(r["quantity"])
            fees += FEE * qty
            is_buy = str(r["side"]).lower() == "buy"
            if side == "long":
                if is_buy:
                    lots.append([qty, px])
                else:
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
                        scale_hits.append(reason)
            else:
                if not is_buy:
                    lots.append([qty, px])
                else:
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
                        scale_hits.append(reason)
        rem = sum(q for q, _ in lots)
        if "stop" in exit_reasons and not any(x.startswith("tp") for x in exit_reasons):
            bucket = "stop_only"
        elif "stop" in exit_reasons:
            bucket = "scaled_then_stop"
        elif any(x in ("flatten", "quarter_close") for x in exit_reasons):
            bucket = (
                "scaled_then_eoq"
                if any(x.startswith("tp") for x in exit_reasons)
                else "eoq_only"
            )
        elif any(x.startswith("tp") for x in exit_reasons):
            bucket = "scaled_full"
        else:
            bucket = exit_reasons[-1] if exit_reasons else "unknown"
        campaigns.append(
            {
                "trade_id": trade_id,
                "side": side,
                "entry_ts": er["ts"],
                "exit_ts": g["ts"].iloc[-1],
                "entry_px": float(er["price"]),
                "year": int(er["ts"].year),
                "quarter": f"{er['ts'].year}Q{(er['ts'].month - 1) // 3 + 1}",
                "net_usd": realized - fees,
                "gross_usd": realized,
                "fees": fees,
                "exit_bucket": bucket,
                "exit_reasons": "|".join(exit_reasons),
                "hit_stop": int("stop" in exit_reasons),
                "rem_lots": rem,
            }
        )
    return pd.DataFrame(campaigns)


def prior_map_from_daily(daily: pd.DataFrame) -> pd.DataFrame:
    q_stats = (
        daily.groupby("qkey")
        .agg(q_high=("high", "max"), q_low=("low", "min"), q_start=("ts", "min"), q_end=("ts", "max"))
        .reset_index()
        .sort_values("q_start")
        .reset_index(drop=True)
    )
    q_stats["prior_high"] = q_stats["q_high"].shift(1)
    q_stats["prior_low"] = q_stats["q_low"].shift(1)
    q_stats["prior_mid"] = (q_stats["prior_high"] + q_stats["prior_low"]) / 2
    q_stats["prior_width"] = q_stats["prior_high"] - q_stats["prior_low"]
    return q_stats.set_index("qkey")


def broker_signals(cdf: pd.DataFrame, daily: pd.DataFrame, prior_map: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, camp in cdf.iterrows():
        et = camp["entry_ts"]
        prev = daily[daily["ts"] < et]
        if prev.empty:
            continue
        sig_row = prev.iloc[-1]
        qk = sig_row["qkey"]
        if qk not in prior_map.index:
            continue
        pr = prior_map.loc[qk]
        if not np.isfinite(pr["prior_width"]) or pr["prior_width"] <= 0:
            continue
        rows.append(
            {
                "signal_ts": sig_row["ts"],
                "entry_ts_allin": et,
                "direction": camp["side"],
                "prior_mid": float(pr["prior_mid"]),
                "prior_width": float(pr["prior_width"]),
                "prior_high": float(pr["prior_high"]),
                "prior_low": float(pr["prior_low"]),
                "qkey": qk,
                "v2_net": float(camp["net_usd"]),
                "v2_bucket": camp["exit_bucket"],
            }
        )
    return pd.DataFrame(rows)


def iso_week(d):
    t = pd.Timestamp(d)
    return (int(t.isocalendar()[0]), int(t.isocalendar()[1]))


@dataclass
class Lot:
    qty: int
    price: float


def path_profile(camp: pd.Series, daily: pd.DataFrame, prior_map: pd.DataFrame) -> dict:
    et, xt = camp["entry_ts"], camp["exit_ts"]
    side = camp["side"]
    entry = float(camp["entry_px"])
    prev = daily[daily["ts"] < et]
    if prev.empty:
        return {}
    qk = prev.iloc[-1]["qkey"]
    pr = prior_map.loc[qk]
    mid = float(pr["prior_mid"])
    W = float(pr["prior_width"])
    if W <= 0:
        return {}
    path = daily[(daily["ts"] >= et) & (daily["ts"] <= xt)].copy()
    if path.empty:
        return {}
    if side == "long":
        fav = (path["high"] - entry) / W
        adv = (entry - path["low"]) / W
        mid_hit = path["low"] <= mid
        mfe_R = (path["high"] - entry) / max(entry - mid, 1e-9)
    else:
        fav = (entry - path["low"]) / W
        adv = (path["high"] - entry) / W
        mid_hit = path["high"] >= mid
        mfe_R = (entry - path["low"]) / max(mid - entry, 1e-9)
    mfe_run = np.maximum.accumulate(fav.to_numpy())
    mfe_W = float(mfe_run[-1])
    mae = float(np.maximum.accumulate(adv.to_numpy())[-1])
    mid_idx = int(np.argmax(mid_hit.to_numpy())) if mid_hit.any() else None
    if mid_idx is not None and mid_hit.iloc[mid_idx]:
        mfe_before_mid = float(mfe_run[mid_idx])
        days_to_mid = mid_idx
    else:
        mfe_before_mid = mfe_W
        days_to_mid = None
    days_to_mfe = int(np.argmax(mfe_run))
    return {
        "trade_id": camp["trade_id"],
        "side": side,
        "entry_ts": et,
        "exit_ts": xt,
        "net_usd": float(camp["net_usd"]),
        "exit_bucket": camp["exit_bucket"],
        "winner": int(camp["net_usd"] > 0),
        "mfe_W": mfe_W,
        "mfe_before_mid_W": mfe_before_mid,
        "mae_R": mae,
        "days_to_mfe": days_to_mfe,
        "days_to_mid": days_to_mid if days_to_mid is not None else np.nan,
        "reached_0p2W": int(mfe_W >= 0.2),
        "reached_0p4W": int(mfe_W >= 0.4),
        "reached_0p6W": int(mfe_W >= 0.6),
        "reached_0p8W": int(mfe_W >= 0.8),
        "hit_mid": int(mid_hit.any()),
        "mfe_R_vs_mid": float(np.nanmax(mfe_R.to_numpy())),
    }


def early_fail_short_pnl(camp, daily, prior_map, min_mfe_W=0.2, patience_days=3) -> float:
    """Coarse: if short MFE < threshold by day N, flatten at that close (no ladder)."""
    if camp["side"] != "short":
        return float(camp["net_usd"])
    et = camp["entry_ts"]
    entry = float(camp["entry_px"])
    prev = daily[daily["ts"] < et]
    if prev.empty:
        return float(camp["net_usd"])
    pr = prior_map.loc[prev.iloc[-1]["qkey"]]
    W = float(pr["prior_width"])
    path = daily[(daily["ts"] >= et) & (daily["ts"] <= camp["exit_ts"])].reset_index(drop=True)
    if path.empty or W <= 0:
        return float(camp["net_usd"])
    fav = (entry - path["low"]) / W
    mfe_run = np.maximum.accumulate(fav.to_numpy())
    cut = min(patience_days, len(path) - 1)
    if mfe_run[cut] >= min_mfe_W:
        return float(camp["net_usd"])
    px = float(path.iloc[cut]["close"])
    # approx 8 lots flatten
    gross = (entry - px) * 8 * float(camp.get("_pv", 20.0) if False else SPECS.get("NQ", {}).get("pv", 20))
    # caller patches pv via attribute — use camp helper
    pv = float(camp.get("pv_override", 20.0))
    gross = (entry - px) * 8 * pv
    fees = FEE * 16
    return gross - fees


def simulate_allin(sig, daily, slip, pv):
    direction = sig["direction"]
    mid = sig["prior_mid"]
    W = sig["prior_width"]
    et = sig["entry_ts_allin"]
    q_end = quarter_end_ts(sig["qkey"], daily)
    entry_row = daily[daily["ts"] >= et].head(1)
    if entry_row.empty:
        return None
    entry_px = float(entry_row.iloc[0]["open"]) + (slip if direction == "long" else -slip)
    lots = [Lot(8, entry_px)]
    realized = 0.0
    fees = FEE * 8
    scales_done = 0
    targets = [
        entry_px + (1 if direction == "long" else -1) * k * 0.2 * W for k in range(1, 5)
    ]
    exit_parts = []
    mgmt = daily[(daily["ts"] >= et) & (daily["ts"] < q_end)]
    for _, bar in mgmt.iterrows():
        if not lots:
            break
        hi, lo = float(bar["high"]), float(bar["low"])
        if (lo <= mid) if direction == "long" else (hi >= mid):
            px = mid + (-slip if direction == "long" else slip)
            rem = sum(L.qty for L in lots)
            realized += sum(
                ((px - L.price) if direction == "long" else (L.price - px)) * L.qty * pv
                for L in lots
            )
            fees += FEE * rem
            lots = []
            exit_parts.append("stop")
            break
        while scales_done < 4 and lots:
            tgt = targets[scales_done]
            if not ((hi >= tgt) if direction == "long" else (lo <= tgt)):
                break
            take = min(2, sum(L.qty for L in lots))
            px = tgt + (-slip if direction == "long" else slip)
            left = take
            pnl = 0.0
            new = []
            for L in lots:
                if left <= 0:
                    new.append(L)
                    continue
                t = min(L.qty, left)
                pnl += ((px - L.price) if direction == "long" else (L.price - px)) * t * pv
                left -= t
                if L.qty > t:
                    new.append(Lot(L.qty - t, L.price))
            lots = new
            realized += pnl
            fees += FEE * take
            exit_parts.append(f"tp{scales_done+1}")
            scales_done += 1
    if lots:
        er = daily[daily["ts"] >= q_end].head(1)
        px = float(er.iloc[0]["open"]) if not er.empty else float(daily.iloc[-1]["close"])
        px = px + (-slip if direction == "long" else slip)
        rem = sum(L.qty for L in lots)
        realized += sum(
            ((px - L.price) if direction == "long" else (L.price - px)) * L.qty * pv
            for L in lots
        )
        fees += FEE * rem
        exit_parts.append("eod")
        lots = []
    return {"net": realized - fees, "avg_entry": entry_px, "exits": "|".join(exit_parts), "filled_qty": 8}


def quarter_end_ts(qkey, daily):
    sub = daily[daily["qkey"] == qkey]
    if sub.empty:
        return daily["ts"].iloc[-1] + pd.Timedelta(days=1)
    return sub["ts"].iloc[-1] + pd.Timedelta(hours=1)


def next_n_trading_days(tdays, after_ts, n=5):
    d0 = pd.Timestamp(after_ts).normalize()
    out = []
    for d in tdays:
        if d > d0:
            out.append(d)
        if len(out) >= n:
            break
    return out


def simulate_accum(
    sig,
    daily,
    h4,
    slip,
    pv,
    buy_qty_per_day=1,
    max_qty=10,
    window_days=5,
    max_buys_per_week=None,
):
    direction = sig["direction"]
    mid = sig["prior_mid"]
    W = sig["prior_width"]
    signal_ts = sig["signal_ts"]
    tdays = list(daily["date"].unique())
    days = next_n_trading_days(tdays, signal_ts, window_days)
    if not days:
        return None
    lots: List[Lot] = []
    realized = 0.0
    fees = 0.0
    filled = 0
    entry_ref = None
    scales_done = 0
    buys = []
    q_end = quarter_end_ts(sig["qkey"], daily)
    stopped = False
    week_buy_count: Dict = {}
    for d in days:
        if filled >= max_qty:
            break
        iso = iso_week(d)
        if max_buys_per_week is not None and week_buy_count.get(iso, 0) >= max_buys_per_week:
            continue
        day_bars = h4[(h4["date"] == d) & (h4["ts"] > signal_ts) & (h4["ts"] < q_end)]
        bought_today = False
        for _, bar in day_bars.iterrows():
            if not np.isfinite(bar["bb_mid"]):
                continue
            if lots:
                hit_stop = (
                    (float(bar["low"]) <= mid)
                    if direction == "long"
                    else (float(bar["high"]) >= mid)
                )
                if hit_stop:
                    px = mid + (-slip if direction == "long" else slip)
                    rem = sum(L.qty for L in lots)
                    realized += sum(
                        ((px - L.price) if direction == "long" else (L.price - px))
                        * L.qty
                        * pv
                        for L in lots
                    )
                    fees += FEE * rem
                    lots = []
                    stopped = True
                    break
            if bought_today or filled >= max_qty:
                continue
            if max_buys_per_week is not None and week_buy_count.get(iso, 0) >= max_buys_per_week:
                continue
            trigger = (
                (float(bar["low"]) <= float(bar["bb_mid"]))
                if direction == "long"
                else (float(bar["high"]) >= float(bar["bb_mid"]))
            )
            if not trigger:
                continue
            px = float(bar["close"]) + (slip if direction == "long" else -slip)
            q = min(buy_qty_per_day, max_qty - filled)
            lots.append(Lot(q, px))
            fees += FEE * q
            filled += q
            if entry_ref is None:
                entry_ref = px
            buys.append({"ts": bar["ts"], "px": px, "qty": q})
            bought_today = True
            week_buy_count[iso] = week_buy_count.get(iso, 0) + 1
        if stopped:
            break
    if filled == 0:
        return {"net": 0.0, "filled_qty": 0, "n_buys": 0, "avg_entry": None, "exits": "no_fill"}
    if stopped or not lots:
        return {
            "net": realized - fees,
            "filled_qty": filled,
            "n_buys": len(buys),
            "avg_entry": entry_ref,
            "exits": "stop_during_accum",
        }
    avg_entry = sum(L.price * L.qty for L in lots) / sum(L.qty for L in lots)
    targets = [
        entry_ref + (1 if direction == "long" else -1) * k * 0.2 * W for k in range(1, 5)
    ]
    first_buy_ts = buys[0]["ts"]
    exit_parts = [f"buys={len(buys)}"]
    mgmt = daily[
        (daily["ts"] >= pd.Timestamp(first_buy_ts).normalize()) & (daily["ts"] < q_end)
    ]
    for _, bar in mgmt.iterrows():
        if not lots:
            break
        hi, lo = float(bar["high"]), float(bar["low"])
        if (lo <= mid) if direction == "long" else (hi >= mid):
            px = mid + (-slip if direction == "long" else slip)
            rem = sum(L.qty for L in lots)
            realized += sum(
                ((px - L.price) if direction == "long" else (L.price - px)) * L.qty * pv
                for L in lots
            )
            fees += FEE * rem
            lots = []
            exit_parts.append("stop")
            break
        while scales_done < 4 and lots:
            tgt = targets[scales_done]
            if not ((hi >= tgt) if direction == "long" else (lo <= tgt)):
                break
            take = min(2, sum(L.qty for L in lots))
            px = tgt + (-slip if direction == "long" else slip)
            left = take
            pnl = 0.0
            new = []
            for L in lots:
                if left <= 0:
                    new.append(L)
                    continue
                t = min(L.qty, left)
                pnl += ((px - L.price) if direction == "long" else (L.price - px)) * t * pv
                left -= t
                if L.qty > t:
                    new.append(Lot(L.qty - t, L.price))
            lots = new
            realized += pnl
            fees += FEE * take
            exit_parts.append(f"tp{scales_done+1}")
            scales_done += 1
    if lots:
        er = daily[daily["ts"] >= q_end].head(1)
        px = float(er.iloc[0]["open"]) if not er.empty else float(daily.iloc[-1]["close"])
        px = px + (-slip if direction == "long" else slip)
        rem = sum(L.qty for L in lots)
        realized += sum(
            ((px - L.price) if direction == "long" else (L.price - px)) * L.qty * pv
            for L in lots
        )
        fees += FEE * rem
        exit_parts.append("eoq")
        lots = []
    return {
        "net": realized - fees,
        "filled_qty": filled,
        "n_buys": len(buys),
        "avg_entry": avg_entry,
        "exits": "|".join(exit_parts),
        "first_entry": entry_ref,
    }


def find_fills(broker_hub: Path, instrument: str) -> Path:
    candidates = list(broker_hub.glob("states/*/fills.csv"))
    if not candidates:
        raise FileNotFoundError("no fills under %s" % broker_hub)
    # Prefer non long_only for short study
    both = [p for p in candidates if "long_only" not in str(p)]
    if both:
        return both[0]
    return candidates[0]


def review_instrument(sym: str, out: Path) -> dict:
    spec = SPECS[sym]
    slip = float(spec["tick"])  # 1 tick slip in points
    pv = float(spec["pv"])
    fills = find_fills(spec["broker_hub"], sym)
    daily = load_daily(spec["daily"])
    h4 = load_h4(spec["h4"], slip)
    prior_map = prior_map_from_daily(daily)
    cdf = fills_to_campaigns(fills, pv)
    cdf.to_csv(out / "v2_campaigns.csv", index=False)

    by_side = (
        cdf.groupby("side")
        .agg(
            trades=("net_usd", "count"),
            net=("net_usd", "sum"),
            wr=("net_usd", lambda s: float((s > 0).mean()) if len(s) else 0.0),
            avg=("net_usd", "mean"),
        )
        .reset_index()
    )
    by_side.to_csv(out / "by_side.csv", index=False)

    profiles = []
    for _, camp in cdf.iterrows():
        profiles.append(path_profile(camp, daily, prior_map))
    pdf = pd.DataFrame([p for p in profiles if p])
    pdf.to_csv(out / "path_profile_all.csv", index=False)
    sp = pdf[pdf.side == "short"].copy() if len(pdf) else pdf
    sp.to_csv(out / "short_path_profile.csv", index=False)

    baseline = float(cdf["net_usd"].sum())
    longs_net = float(cdf.loc[cdf.side == "long", "net_usd"].sum()) if (cdf.side == "long").any() else 0.0
    shorts_net = float(cdf.loc[cdf.side == "short", "net_usd"].sum()) if (cdf.side == "short").any() else 0.0

    # early-fail shorts (coarse)
    early3 = 0.0
    early5 = 0.0
    for _, camp in cdf.iterrows():
        if camp["side"] != "short":
            early3 += float(camp["net_usd"])
            early5 += float(camp["net_usd"])
            continue
        et = camp["entry_ts"]
        entry = float(camp["entry_px"])
        prev = daily[daily["ts"] < et]
        if prev.empty:
            early3 += float(camp["net_usd"])
            early5 += float(camp["net_usd"])
            continue
        pr = prior_map.loc[prev.iloc[-1]["qkey"]]
        W = float(pr["prior_width"])
        path = daily[(daily["ts"] >= et) & (daily["ts"] <= camp["exit_ts"])].reset_index(drop=True)
        if path.empty or W <= 0:
            early3 += float(camp["net_usd"])
            early5 += float(camp["net_usd"])
            continue
        fav = (entry - path["low"]) / W
        mfe_run = np.maximum.accumulate(fav.to_numpy())

        def _cut(n):
            cut = min(n, len(path) - 1)
            if mfe_run[cut] >= 0.2:
                return float(camp["net_usd"])
            px = float(path.iloc[cut]["close"])
            return (entry - px) * 8 * pv - FEE * 16

        early3 += _cut(3)
        early5 += _cut(5)

    short_diag = {
        "n": int(len(sp)),
        "net": float(sp["net_usd"].sum()) if len(sp) else 0.0,
        "wr": float((sp["net_usd"] > 0).mean()) if len(sp) else 0.0,
        "med_mfe_W": float(sp["mfe_W"].median()) if len(sp) else None,
        "med_mfe_before_mid_W": float(sp["mfe_before_mid_W"].median()) if len(sp) else None,
        "losers_med_mfe_before_mid": (
            float(sp.loc[sp.winner == 0, "mfe_before_mid_W"].median())
            if len(sp) and (sp.winner == 0).any()
            else None
        ),
        "winners_med_mfe": (
            float(sp.loc[sp.winner == 1, "mfe_W"].median())
            if len(sp) and (sp.winner == 1).any()
            else None
        ),
        "reach_0p2": float(sp["reached_0p2W"].mean()) if len(sp) else None,
        "reach_0p4": float(sp["reached_0p4W"].mean()) if len(sp) else None,
        "reach_0p6": float(sp["reached_0p6W"].mean()) if len(sp) else None,
        "reach_0p8": float(sp["reached_0p8W"].mean()) if len(sp) else None,
        "stop_only_n": int(((sp.exit_bucket == "stop_only").sum()) if len(sp) else 0),
        "stop_only_net": float(sp.loc[sp.exit_bucket == "stop_only", "net_usd"].sum()) if len(sp) else 0.0,
        "skip_shorts_net": longs_net,
        "skip_shorts_delta": longs_net - baseline,
        "early_fail_d3_net": early3,
        "early_fail_d3_delta": early3 - baseline,
        "early_fail_d5_net": early5,
        "early_fail_d5_delta": early5 - baseline,
        "longs_net": longs_net,
        "shorts_net": shorts_net,
        "baseline_net": baseline,
        "adheres_to_nq_short_issue": bool(
            abs(shorts_net) < 0.15 * abs(longs_net) if abs(longs_net) > 1 else abs(shorts_net) < abs(baseline) * 0.05
        )
        and (float((sp["net_usd"] > 0).mean()) if len(sp) else 1.0) < 0.55,
    }

    bdf = broker_signals(cdf, daily, prior_map)
    results = []
    for _, sig in bdf.iterrows():
        a8 = simulate_allin(sig, daily, slip, pv)
        # the two user asked for:
        a2w = simulate_accum(
            sig, daily, h4, slip, pv, buy_qty_per_day=1, max_qty=10, window_days=10
        )  # 2-week period ~10 trading days
        a1w2 = simulate_accum(
            sig,
            daily,
            h4,
            slip,
            pv,
            buy_qty_per_day=2,
            max_qty=2,
            window_days=5,
            max_buys_per_week=1,
        )
        results.append(
            {
                "signal_ts": sig["signal_ts"],
                "direction": sig["direction"],
                "qkey": sig["qkey"],
                "v2_broker_net": sig["v2_net"],
                "allin_net": None if not a8 else a8["net"],
                "accum_2w_1perd_net": None if not a2w else a2w["net"],
                "accum_2w_1perd_qty": 0 if not a2w else a2w["filled_qty"],
                "accum_1w_2perweek_net": None if not a1w2 else a1w2["net"],
                "accum_1w_2perweek_qty": 0 if not a1w2 else a1w2["filled_qty"],
            }
        )
    rdf = pd.DataFrame(results)
    rdf.to_csv(out / "counterfactual_trades.csv", index=False)

    def pack(name, net_col, qty_col):
        sub = rdf.dropna(subset=[net_col])
        allin = float(rdf["allin_net"].sum())
        return {
            "label": name,
            "net": float(sub[net_col].sum()),
            "avg_qty": float(sub[qty_col].mean()) if len(sub) else 0.0,
            "vs_allin": float(sub[net_col].sum()) - allin,
            "no_fill": int((sub[qty_col] == 0).sum()) if len(sub) else 0,
            "better": int((sub[net_col] > rdf.loc[sub.index, "allin_net"]).sum()) if len(sub) else 0,
            "worse": int((sub[net_col] < rdf.loc[sub.index, "allin_net"]).sum()) if len(sub) else 0,
        }

    accum = {
        "allin": float(rdf["allin_net"].sum()) if len(rdf) else 0.0,
        "broker_v2": baseline,
        "variants": [
            pack("2w_1perd_cap10", "accum_2w_1perd_net", "accum_2w_1perd_qty"),
            pack("1w_2contracts_per_week", "accum_1w_2perweek_net", "accum_1w_2perweek_qty"),
        ],
    }
    accum_by_side = {}
    for label, net_col, qty_col in (
        ("2w_1perd", "accum_2w_1perd_net", "accum_2w_1perd_qty"),
        ("1w_2perweek", "accum_1w_2perweek_net", "accum_1w_2perweek_qty"),
    ):
        accum_by_side[label] = {}
        for side in ("long", "short"):
            mask = rdf["direction"] == side
            accum_by_side[label][side] = {
                "net": float(rdf.loc[mask, net_col].sum()),
                "avg_qty": float(rdf.loc[mask, qty_col].mean()) if mask.any() else 0.0,
                "n": int(mask.sum()),
            }

    summary = {
        "instrument": sym,
        "fills": str(fills),
        "n_trades": int(len(cdf)),
        "baseline_net": baseline,
        "by_side": by_side.to_dict(orient="records"),
        "short": short_diag,
        "accum": accum,
        "accum_by_side": accum_by_side,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf-8")

    lines = [
        f"# {sym} v2 short + accumulate review",
        "",
        f"Hub: `{out}`",
        f"Broker fills: `{fills}`",
        "",
        f"## Broker book: {len(cdf)} trades · net **${baseline:,.0f}**",
        "",
        "| side | n | net | WR |",
        "|---|---:|---:|---:|",
    ]
    for _, r in by_side.iterrows():
        lines.append(
            f"| {r['side']} | {int(r['trades'])} | ${r['net']:,.0f} | {100*r['wr']:.0f}% |"
        )
    lines += [
        "",
        "## Short issues (NQ-style)",
        "",
        f"- Shorts: n={short_diag['n']} · net **${short_diag['net']:,.0f}** · WR {100*(short_diag['wr'] or 0):.0f}%",
        f"- Median MFE {short_diag['med_mfe_W']}W · before mid {short_diag['med_mfe_before_mid_W']}W",
        f"- Reach 0.2/0.4/0.6/0.8W: {short_diag['reach_0p2']} / {short_diag['reach_0p4']} / {short_diag['reach_0p6']} / {short_diag['reach_0p8']}",
        f"- Stop-only shorts: {short_diag['stop_only_n']} · ${short_diag['stop_only_net']:,.0f}",
        f"- Skip shorts (longs only): **${short_diag['skip_shorts_net']:,.0f}** (Δ ${short_diag['skip_shorts_delta']:,.0f})",
        f"- Early-fail <0.2W by d3: ${short_diag['early_fail_d3_net']:,.0f} (Δ ${short_diag['early_fail_d3_delta']:,.0f})",
        f"- Adheres to NQ short pattern (shorts ~noise / weak WR): **{short_diag['adheres_to_nq_short_issue']}**",
        "",
        "## Accumulate (the two)",
        "",
        f"Pandas all-in 8: **${accum['allin']:,.0f}**",
        "",
    ]
    for v in accum["variants"]:
        lines.append(
            f"- **{v['label']}**: ${v['net']:,.0f} · avg qty {v['avg_qty']:.1f} · vs all-in ${v['vs_allin']:,.0f} · "
            f"no-fill {v['no_fill']} · better/worse {v['better']}/{v['worse']}"
        )
    lines += ["", "## Stance", ""]
    best = max(accum["variants"], key=lambda x: x["net"]) if accum["variants"] else None
    if best and best["net"] < accum["allin"]:
        lines.append(
            f"- Accumulate still lags all-in (best {best['label']} ${best['net']:,.0f} vs all-in ${accum['allin']:,.0f})."
        )
    elif best:
        lines.append(f"- Best accum {best['label']} beats all-in.")
    if abs(short_diag["skip_shorts_delta"]) < abs(baseline) * 0.05 or short_diag["skip_shorts_delta"] > 0:
        lines.append("- Skipping shorts is ~flat or better — shorts not earning keep.")
    else:
        lines.append("- Shorts contribute material net — NQ-style skip is not free here.")
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--instruments", default="YM,MNQ,ES", help="Comma list")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    ROOT.mkdir(parents=True, exist_ok=True)
    instruments = [s.strip().upper() for s in str(args.instruments).split(",") if s.strip()]
    all_sum = {}
    for sym in instruments:
        out = ROOT / sym.lower()
        out.mkdir(parents=True, exist_ok=True)
        print("REVIEW", sym, flush=True)
        all_sum[sym] = review_instrument(sym, out)

    (ROOT / "summary.json").write_text(json.dumps(all_sum, indent=2, default=str), encoding="utf-8")
    lines = ["# Quarterly range v2 cross-market short + accumulate", "", f"Hub: `{ROOT}`", ""]
    for sym, s in all_sum.items():
        sh = s["short"]
        lines.append(f"## {sym}")
        lines.append(
            f"- Broker net ${s['baseline_net']:,.0f} · longs ${sh['longs_net']:,.0f} · shorts ${sh['shorts_net']:,.0f} "
            f"(n={sh['n']}, WR {100*(sh['wr'] or 0):.0f}%)"
        )
        lines.append(
            f"- Skip shorts Δ ${sh['skip_shorts_delta']:,.0f} · adheres_short_issue={sh['adheres_to_nq_short_issue']}"
        )
        for v in s["accum"]["variants"]:
            lines.append(
                f"- {v['label']}: ${v['net']:,.0f} (vs all-in ${v['vs_allin']:,.0f}, avg qty {v['avg_qty']:.1f})"
            )
        lines.append("")
    (ROOT / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email_body = "\n".join(lines)
    (ROOT / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")
    if args.email:
        send_email(
            subject="potions: quarterly v2 cross YM/MNQ/ES short+accum",
            body=email_body,
        )
    print("DONE", ROOT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
