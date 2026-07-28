"""XAUUSD Monday OR M2_S2_R3 — cluster, levels, skip-rule study.

Phases:
1. Trade-level streaks + calendar concentration + state-conditional WR
2. Prior week/month H/L proximity (entry-near + 15m path touch)
3. Cluster-informed skip-rule sweep (net pts / mean / coverage / max L / stress)

Artifacts → live/state/monday_or_phase2/xauusd_m2_s2_r3_cluster_skip/
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_data import load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

NY = pytz.timezone("America/New_York")
REPO = Path(__file__).resolve().parents[1]
FILLS = (
    REPO
    / "live"
    / "state"
    / "monday_or_sizing_sweep_broker_xauusd"
    / "states"
    / "xauusd_m2_s2_r3"
    / "fills.csv"
)
OUT = REPO / "live" / "state" / "monday_or_phase2" / "xauusd_m2_s2_r3_cluster_skip"
DAILY = REPO / "fx" / "xauusd_daily.csv"
MONTHLY = REPO / "fx" / "xauusd_monthly.csv"
ONE_M = REPO / "fx" / "xauusd_1m.csv"

# Entry-near thresholds (USD on gold).
NEAR_TIGHT = 5.0
NEAR_WIDE = 10.0


def _progress(msg: str) -> None:
    print(msg, flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def parse_ny(ts: str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    return t.tz_convert(NY) if t.tzinfo else t.tz_localize(NY)


def trade_outcomes(fills: pd.DataFrame) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for tid, g in fills.groupby("trade_id", sort=False):
        g = g.sort_values("ts")
        entries = g[g.reason == "entry"]
        if entries.empty:
            continue
        ent = entries.iloc[0]
        side = str(ent.side).lower()
        direction = "Long" if side == "buy" else "Short"
        lots: List[List[float]] = []
        realized = 0.0
        for _, f in g.iterrows():
            q = float(f.quantity)
            px = float(f.price)
            s = str(f.side).lower()
            signed = q if s == "buy" else -q
            if not lots:
                lots.append([q, px, 1.0 if s == "buy" else -1.0])
                continue
            inv_sign = lots[0][2]
            if (inv_sign > 0 and signed > 0) or (inv_sign < 0 and signed < 0):
                lots.append([q, px, inv_sign])
                continue
            remain = q
            while remain > 1e-12 and lots:
                lq, lpx, lsign = lots[0]
                take = min(lq, remain)
                if lsign > 0:
                    realized += (px - lpx) * take
                else:
                    realized += (lpx - px) * take
                lq -= take
                remain -= take
                if lq <= 1e-12:
                    lots.pop(0)
                else:
                    lots[0][0] = lq
            if remain > 1e-12:
                lots.append([remain, px, 1.0 if s == "buy" else -1.0])
        exit_reasons = [r for r in g.reason.tolist() if r != "entry"]
        rows.append(
            dict(
                trade_id=str(tid),
                entry_ts=str(ent.ts),
                exit_ts=str(g.iloc[-1].ts),
                entry_price=float(ent.price),
                direction=direction,
                net_pts=float(realized),
                win=realized > 0,
                flat=abs(realized) < 1e-12,
                primary_exit=exit_reasons[-1] if exit_reasons else "",
            )
        )
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    out["entry_dt"] = out["entry_ts"].map(parse_ny)
    out["exit_dt"] = out["exit_ts"].map(parse_ny)
    out = out[~out.flat].reset_index(drop=True)
    # Mon-start NY week label
    out["week_mon"] = out["entry_dt"].map(
        lambda d: (d.tz_localize(None).normalize() - pd.Timedelta(days=d.weekday())).date().isoformat()
    )
    out["month"] = out["entry_dt"].map(lambda d: d.strftime("%Y-%m"))
    return out


def streak_stats(wins: Sequence[bool]) -> Dict[str, Any]:
    if not wins:
        return {}
    streaks: List[Tuple[bool, int]] = []
    cur, n = wins[0], 1
    for w in wins[1:]:
        if w == cur:
            n += 1
        else:
            streaks.append((cur, n))
            cur, n = w, 1
    streaks.append((cur, n))
    w_s = [n for t, n in streaks if t]
    l_s = [n for t, n in streaks if not t]
    ww = wl = lw = ll = 0
    for a, b in zip(wins, wins[1:]):
        if a and b:
            ww += 1
        elif a and not b:
            wl += 1
        elif (not a) and b:
            lw += 1
        else:
            ll += 1

    def dist(xs: List[int]) -> Dict[str, int]:
        return {str(k): int(v) for k, v in sorted(Counter(xs).items())}

    return {
        "n": len(wins),
        "wins": int(sum(wins)),
        "losses": int(len(wins) - sum(wins)),
        "wr": round(100.0 * sum(wins) / len(wins), 1),
        "max_win_streak": max(w_s) if w_s else 0,
        "max_loss_streak": max(l_s) if l_s else 0,
        "mean_win_streak": round(float(np.mean(w_s)), 2) if w_s else 0,
        "mean_loss_streak": round(float(np.mean(l_s)), 2) if l_s else 0,
        "win_streak_dist": dist(w_s),
        "loss_streak_dist": dist(l_s),
        "p_w_given_w": round(ww / (ww + wl), 3) if (ww + wl) else None,
        "p_l_given_w": round(wl / (ww + wl), 3) if (ww + wl) else None,
        "p_w_given_l": round(lw / (lw + ll), 3) if (lw + ll) else None,
        "p_l_given_l": round(ll / (lw + ll), 3) if (lw + ll) else None,
        "transitions": {"WW": ww, "WL": wl, "LW": lw, "LL": ll},
        "loss_in_multi_streak_pct": round(
            100.0 * sum(n for t, n in streaks if (not t) and n >= 2) / max(1, sum(1 for w in wins if not w)),
            1,
        ),
        "win_in_multi_streak_pct": round(
            100.0 * sum(n for t, n in streaks if t and n >= 2) / max(1, sum(1 for w in wins if w)),
            1,
        ),
    }


def equity_stress(net_pts: Sequence[float]) -> Dict[str, float]:
    if not len(net_pts):
        return {"net": 0.0, "stress": 0.0, "ns": 0.0}
    eq = np.cumsum(np.asarray(net_pts, dtype=float))
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    stress = float(dd.min()) if len(dd) else 0.0
    net = float(eq[-1])
    ns = net / abs(stress) if stress < 0 else (float("inf") if net > 0 else 0.0)
    return {"net": round(net, 2), "stress": round(stress, 2), "ns": round(ns, 2) if ns != float("inf") else 999.0}


def summarize_book(df: pd.DataFrame, base_n: int) -> Dict[str, Any]:
    st = streak_stats(df.win.tolist())
    stress = equity_stress(df.net_pts.tolist())
    return {
        **st,
        "net_pts": round(float(df.net_pts.sum()), 2),
        "mean_pts": round(float(df.net_pts.mean()), 4) if len(df) else 0.0,
        "coverage_pct": round(100.0 * len(df) / base_n, 1) if base_n else 0.0,
        "stress_pts": stress["stress"],
        "ns_proxy": stress["ns"],
    }


def calendar_clustering(trades: pd.DataFrame) -> Dict[str, Any]:
    week = trades.groupby("week_mon", as_index=False).agg(
        n=("win", "size"),
        wins=("win", "sum"),
        net_pts=("net_pts", "sum"),
        losses=("win", lambda s: int((~s).sum())),
    )
    week["wr"] = (100.0 * week["wins"] / week["n"]).round(1)
    week = week.sort_values("net_pts", ascending=False)
    lifetime = float(week["net_pts"].sum())
    top = week.iloc[0]
    top_share = float(top["net_pts"]) / abs(lifetime) if lifetime else 0.0
    # top 5% weeks share of gross positive week PnL
    pos = week[week["net_pts"] > 0].sort_values("net_pts", ascending=False)
    n5 = max(1, int(round(0.05 * len(week))))
    top5_share = float(pos.head(n5)["net_pts"].sum()) / float(pos["net_pts"].sum()) if len(pos) else 0.0
    heat_by_loss = week.sort_values("losses", ascending=False).head(10)
    return {
        "weeks": int(len(week)),
        "lifetime_net_pts": round(lifetime, 2),
        "top_week": str(top["week_mon"]),
        "top_week_net": round(float(top["net_pts"]), 2),
        "top_week_share": round(top_share, 4),
        "top_5pct_weeks_n": n5,
        "top_5pct_share_of_gross_pos": round(top5_share, 4),
        "top_10_weeks": week.head(10)[["week_mon", "n", "wins", "losses", "wr", "net_pts"]].to_dict("records"),
        "top_10_loss_count_weeks": heat_by_loss[["week_mon", "n", "wins", "losses", "wr", "net_pts"]].to_dict(
            "records"
        ),
        "flag_concentrated": bool(top_share > 0.08 or top5_share > 0.50),
    }


def state_conditional_wr(trades: pd.DataFrame) -> Dict[str, Any]:
    wins = trades.win.tolist()
    nets = trades.net_pts.tolist()

    def after_exact_loss_run(k: int) -> Dict[str, Any]:
        idxs = []
        consec = 0
        for i, w in enumerate(wins):
            if consec == k and i > 0:
                idxs.append(i)
            consec = 0 if w else consec + 1
        if not idxs:
            return {"n": 0, "wr": None, "mean_pts": None}
        sub_w = [wins[i] for i in idxs]
        sub_n = [nets[i] for i in idxs]
        return {
            "n": len(idxs),
            "wr": round(100.0 * sum(sub_w) / len(sub_w), 1),
            "mean_pts": round(float(np.mean(sub_n)), 4),
        }

    def after_ge_loss_run(k: int) -> Dict[str, Any]:
        idxs = []
        consec = 0
        for i, w in enumerate(wins):
            if consec >= k:
                idxs.append(i)
            consec = 0 if w else consec + 1
        if not idxs:
            return {"n": 0, "wr": None, "mean_pts": None}
        sub_w = [wins[i] for i in idxs]
        sub_n = [nets[i] for i in idxs]
        return {
            "n": len(idxs),
            "wr": round(100.0 * sum(sub_w) / len(sub_w), 1),
            "mean_pts": round(float(np.mean(sub_n)), 4),
        }

    def after_exact_win_run(k: int) -> Dict[str, Any]:
        idxs = []
        consec = 0
        for i, w in enumerate(wins):
            if consec == k:
                idxs.append(i)
            consec = consec + 1 if w else 0
        if not idxs:
            return {"n": 0, "wr": None, "mean_pts": None}
        sub_w = [wins[i] for i in idxs]
        sub_n = [nets[i] for i in idxs]
        return {
            "n": len(idxs),
            "wr": round(100.0 * sum(sub_w) / len(sub_w), 1),
            "mean_pts": round(float(np.mean(sub_n)), 4),
        }

    # heat weeks = top 5% by net
    week_net = trades.groupby("week_mon")["net_pts"].sum().sort_values(ascending=False)
    n5 = max(1, int(round(0.05 * len(week_net))))
    heat_weeks = set(week_net.head(n5).index.tolist())
    in_heat = trades[trades.week_mon.isin(heat_weeks)]
    out_heat = trades[~trades.week_mon.isin(heat_weeks)]
    return {
        "after_exact_1L": after_exact_loss_run(1),
        "after_exact_2L": after_exact_loss_run(2),
        "after_exact_3L": after_exact_loss_run(3),
        "after_exact_4L": after_exact_loss_run(4),
        "after_ge_2L": after_ge_loss_run(2),
        "after_ge_3L": after_ge_loss_run(3),
        "after_exact_1W": after_exact_win_run(1),
        "after_exact_2W": after_exact_win_run(2),
        "in_top5pct_heat_weeks": {
            "n": int(len(in_heat)),
            "wr": round(100.0 * in_heat.win.mean(), 1) if len(in_heat) else None,
            "mean_pts": round(float(in_heat.net_pts.mean()), 4) if len(in_heat) else None,
            "net_pts": round(float(in_heat.net_pts.sum()), 2) if len(in_heat) else 0.0,
            "weeks": n5,
        },
        "outside_heat_weeks": {
            "n": int(len(out_heat)),
            "wr": round(100.0 * out_heat.win.mean(), 1) if len(out_heat) else None,
            "mean_pts": round(float(out_heat.net_pts.mean()), 4) if len(out_heat) else None,
            "net_pts": round(float(out_heat.net_pts.sum()), 2) if len(out_heat) else 0.0,
        },
    }


def build_prior_levels() -> Tuple[pd.DataFrame, pd.DataFrame]:
    daily = pd.read_csv(DAILY, parse_dates=["date"]).sort_values("date")
    daily["date"] = pd.to_datetime(daily["date"]).dt.normalize()
    daily = daily.set_index("date")
    # Mon-start weeks
    tmp = daily.reset_index()
    tmp["week_mon"] = tmp["date"] - pd.to_timedelta(tmp["date"].dt.weekday, unit="D")
    weekly = (
        tmp.groupby("week_mon", as_index=False)
        .agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .sort_values("week_mon")
    )
    weekly["prior_week_high"] = weekly["high"].shift(1)
    weekly["prior_week_low"] = weekly["low"].shift(1)
    monthly = pd.read_csv(MONTHLY, parse_dates=["date"]).sort_values("date")
    monthly["date"] = pd.to_datetime(monthly["date"]).dt.normalize()
    monthly["ym"] = monthly["date"].dt.strftime("%Y-%m")
    monthly["prior_month_high"] = monthly["high"].shift(1)
    monthly["prior_month_low"] = monthly["low"].shift(1)
    return weekly, monthly


def load_15m() -> Tuple[pd.DatetimeIndex, np.ndarray, np.ndarray]:
    _progress("loading XAUUSD 1m → 15m...")
    gby = load_fx_1m_by_ny_date(ONE_M, "XAUUSD")
    df1 = concat_all_1m(gby)
    m15 = (
        df1.resample("15min", label="left", closed="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .dropna(subset=["open"])
    )
    _progress("15m bars: %d" % len(m15))
    return m15.index, m15["high"].to_numpy(), m15["low"].to_numpy()


def annotate_levels(
    trades: pd.DataFrame,
    weekly: pd.DataFrame,
    monthly: pd.DataFrame,
    ts_idx: pd.DatetimeIndex,
    highs: np.ndarray,
    lows: np.ndarray,
) -> pd.DataFrame:
    week_map = weekly.set_index("week_mon")
    month_map = monthly.set_index("ym")
    rows = []
    for _, t in trades.iterrows():
        edt = t.entry_dt
        xdt = t.exit_dt
        ed_naive = edt.tz_localize(None).normalize()
        week_mon = ed_naive - pd.Timedelta(days=ed_naive.weekday())
        ym = edt.strftime("%Y-%m")
        pwh = pwl = pmh = pml = np.nan
        if week_mon in week_map.index:
            pwh = float(week_map.loc[week_mon, "prior_week_high"])
            pwl = float(week_map.loc[week_mon, "prior_week_low"])
        if ym in month_map.index:
            pmh = float(month_map.loc[ym, "prior_month_high"])
            pml = float(month_map.loc[ym, "prior_month_low"])

        i0 = ts_idx.searchsorted(edt)
        i1 = ts_idx.searchsorted(xdt, side="right")
        if i1 <= i0:
            ph = pl = float(t.entry_price)
        else:
            ph = float(highs[i0:i1].max())
            pl = float(lows[i0:i1].min())

        ep = float(t.entry_price)
        long = t.direction == "Long"

        def near(level: float, width: float) -> bool:
            if level != level:  # NaN
                return False
            return abs(ep - level) <= width

        def touch_high(level: float) -> bool:
            return level == level and ph >= level

        def touch_low(level: float) -> bool:
            return level == level and pl <= level

        # Directional: long cares highs; short cares lows
        touch_pw = touch_high(pwh) if long else touch_low(pwl)
        touch_pm = touch_high(pmh) if long else touch_low(pml)
        near_pw_t = near(pwh if long else pwl, NEAR_TIGHT)
        near_pw_w = near(pwh if long else pwl, NEAR_WIDE)
        near_pm_t = near(pmh if long else pml, NEAR_TIGHT)
        near_pm_w = near(pmh if long else pml, NEAR_WIDE)

        rows.append(
            {
                **{k: t[k] for k in t.index if k not in {"entry_dt", "exit_dt"}},
                "entry_dt": str(edt),
                "exit_dt": str(xdt),
                "path_high": ph,
                "path_low": pl,
                "prior_week_high": pwh,
                "prior_week_low": pwl,
                "prior_month_high": pmh,
                "prior_month_low": pml,
                "touch_prior_week_ext": bool(touch_pw),
                "touch_prior_month_ext": bool(touch_pm),
                "near_prior_week_5": bool(near_pw_t),
                "near_prior_week_10": bool(near_pw_w),
                "near_prior_month_5": bool(near_pm_t),
                "near_prior_month_10": bool(near_pm_w),
                "touch_any_wm": bool(touch_pw or touch_pm),
                "near_any_wm_10": bool(near_pw_w or near_pm_w),
            }
        )
    return pd.DataFrame(rows)


def bucket_stats(df: pd.DataFrame, mask: pd.Series, label: str) -> Dict[str, Any]:
    g = df[mask]
    if g.empty:
        return {"label": label, "n": 0}
    # loss-run incidence among this subset's chronological order is not meaningful;
    # report share that are part of a global multi-loss context via preceding losses later if needed.
    return {
        "label": label,
        "n": int(len(g)),
        "wins": int(g.win.sum()),
        "losses": int((~g.win).sum()),
        "wr": round(100.0 * g.win.mean(), 1),
        "mean_pts": round(float(g.net_pts.mean()), 4),
        "net_pts": round(float(g.net_pts.sum()), 2),
    }


def win_run_start_level_share(df: pd.DataFrame) -> Dict[str, Any]:
    """Share of win-run starts that have level touch vs base rate of touch."""
    wins = df.win.tolist()
    touches = df.touch_any_wm.tolist()
    start_idxs = []
    prev = False
    for i, w in enumerate(wins):
        if w and not prev:
            start_idxs.append(i)
        prev = w
    if not start_idxs:
        return {}
    start_touch = sum(1 for i in start_idxs if touches[i])
    base = sum(1 for t in touches if t) / len(touches)
    return {
        "n_win_run_starts": len(start_idxs),
        "starts_with_touch": start_touch,
        "share_starts_with_touch": round(start_touch / len(start_idxs), 3),
        "base_touch_rate": round(base, 3),
    }


# ---- skip simulators ----


def sim_skip_after_outcome(
    trades: pd.DataFrame,
    *,
    skip_after_win: int = 0,
    skip_after_loss: int = 0,
) -> List[bool]:
    take: List[bool] = []
    skip_rem = 0
    for _, t in trades.iterrows():
        if skip_rem > 0:
            take.append(False)
            skip_rem -= 1
            continue
        take.append(True)
        if t.win:
            skip_rem = skip_after_win
        else:
            skip_rem = skip_after_loss
    return take


def sim_skip_after_n_losses(
    trades: pd.DataFrame,
    n_losses: int,
    skip_n: int,
) -> List[bool]:
    """Skip skip_n after n consecutive *taken* losses; reset counter after fire."""
    take: List[bool] = []
    skip_rem = 0
    consec_loss = 0
    for _, t in trades.iterrows():
        if skip_rem > 0:
            take.append(False)
            skip_rem -= 1
            continue
        take.append(True)
        if t.win:
            consec_loss = 0
        else:
            consec_loss += 1
            if consec_loss >= n_losses:
                skip_rem = skip_n
                consec_loss = 0
    return take


def sim_skip_after_n_wins(trades: pd.DataFrame, n_wins: int, skip_n: int) -> List[bool]:
    take: List[bool] = []
    skip_rem = 0
    consec_win = 0
    for _, t in trades.iterrows():
        if skip_rem > 0:
            take.append(False)
            skip_rem -= 1
            continue
        take.append(True)
        if t.win:
            consec_win += 1
            if consec_win >= n_wins:
                skip_rem = skip_n
                consec_win = 0
        else:
            consec_win = 0
    return take


def sim_heat_sitout(trades: pd.DataFrame, *, after_week_net: float) -> List[bool]:
    """After a Mon-week's realized net (taken so far in that week) exceeds threshold, skip rest of week."""
    take: List[bool] = []
    week_net: Dict[str, float] = {}
    sitting: Dict[str, bool] = {}
    for _, t in trades.iterrows():
        w = t.week_mon
        if sitting.get(w):
            take.append(False)
            continue
        take.append(True)
        week_net[w] = week_net.get(w, 0.0) + float(t.net_pts)
        if week_net[w] >= after_week_net:
            sitting[w] = True
    return take


def sim_heat_sitout_after_losses(trades: pd.DataFrame, *, n_losses_in_week: int) -> List[bool]:
    take: List[bool] = []
    week_losses: Dict[str, int] = {}
    sitting: Dict[str, bool] = {}
    for _, t in trades.iterrows():
        w = t.week_mon
        if sitting.get(w):
            take.append(False)
            continue
        take.append(True)
        if not t.win:
            week_losses[w] = week_losses.get(w, 0) + 1
            if week_losses[w] >= n_losses_in_week:
                sitting[w] = True
    return take


def run_skip_grid(trades: pd.DataFrame) -> List[Dict[str, Any]]:
    base_n = len(trades)
    rules: List[Tuple[str, List[bool]]] = []
    rules.append(("take_all", [True] * base_n))
    rules.append(("skip1_after_W", sim_skip_after_outcome(trades, skip_after_win=1, skip_after_loss=0)))
    rules.append(("skip1_after_2W", sim_skip_after_n_wins(trades, 2, 1)))
    rules.append(("skip1_after_1L", sim_skip_after_outcome(trades, skip_after_win=0, skip_after_loss=1)))
    rules.append(("skip1_after_2L", sim_skip_after_n_losses(trades, 2, 1)))
    rules.append(("skip1_after_3L", sim_skip_after_n_losses(trades, 3, 1)))
    rules.append(("skip2_after_2L", sim_skip_after_n_losses(trades, 2, 2)))
    rules.append(("skip2_after_3L", sim_skip_after_n_losses(trades, 3, 2)))
    # heat: sit out rest of week after +50 / +100 pts in-week (gold points)
    rules.append(("sitout_week_after_+50pts", sim_heat_sitout(trades, after_week_net=50.0)))
    rules.append(("sitout_week_after_+100pts", sim_heat_sitout(trades, after_week_net=100.0)))
    rules.append(("sitout_week_after_3L", sim_heat_sitout_after_losses(trades, n_losses_in_week=3)))
    rules.append(("sitout_week_after_4L", sim_heat_sitout_after_losses(trades, n_losses_in_week=4)))

    out = []
    for name, mask in rules:
        taken = trades[mask]
        skipped = trades[[not m for m in mask]]
        row = {"rule": name, **summarize_book(taken, base_n)}
        if len(skipped):
            row["skipped_n"] = int(len(skipped))
            row["skipped_wr"] = round(100.0 * skipped.win.mean(), 1)
            row["skipped_net_pts"] = round(float(skipped.net_pts.sum()), 2)
            row["skipped_mean_pts"] = round(float(skipped.net_pts.mean()), 4)
        else:
            row["skipped_n"] = 0
            row["skipped_wr"] = None
            row["skipped_net_pts"] = 0.0
            row["skipped_mean_pts"] = None
        out.append(row)
        _progress(
            "  %s n=%d WR=%.1f net=%.1f mean=%.4f maxL=%s cover=%.1f ns=%.2f"
            % (
                name,
                row["n"],
                row["wr"],
                row["net_pts"],
                row["mean_pts"],
                row.get("max_loss_streak"),
                row["coverage_pct"],
                row["ns_proxy"],
            )
        )
    return out


def cluster_verdict(cond: Dict[str, Any], base_wr: float) -> List[str]:
    notes = []
    a1 = cond.get("after_exact_1L") or {}
    a2 = cond.get("after_exact_2L") or {}
    a1w = cond.get("after_exact_1W") or {}
    if a1.get("wr") is not None and a1["wr"] >= base_wr - 0.5:
        notes.append(
            "After exactly 1L, next WR=%.1f (≥≈baseline %.1f) → skip-after-1L likely toxic."
            % (a1["wr"], base_wr)
        )
    if a2.get("wr") is not None:
        if a2["wr"] < base_wr - 1.0:
            notes.append(
                "After exactly 2L, next WR=%.1f (soft vs %.1f) → skip-1-after-2L is a candidate."
                % (a2["wr"], base_wr)
            )
        else:
            notes.append(
                "After exactly 2L, next WR=%.1f (~baseline) → skip-after-2L may be near-neutral."
                % a2["wr"]
            )
    if a1w.get("wr") is not None and a1w["wr"] < base_wr - 1.0:
        notes.append(
            "After exactly 1W, next WR=%.1f (soft) → skip-1-after-W is a candidate." % a1w["wr"]
        )
    heat = cond.get("in_top5pct_heat_weeks") or {}
    outh = cond.get("outside_heat_weeks") or {}
    if heat.get("net_pts") and outh.get("n"):
        notes.append(
            "Top-5%% heat weeks: n=%s WR=%s net=%.1f vs outside net=%.1f — calendar concentration is structural."
            % (heat.get("n"), heat.get("wr"), heat.get("net_pts") or 0, outh.get("net_pts") or 0)
        )
    return notes


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    _progress("START XAUUSD M2_S2_R3 cluster/levels/skip study")

    fills = pd.read_csv(FILLS)
    trades = trade_outcomes(fills)
    base_n = len(trades)
    _progress("trades: %d" % base_n)

    # ---- Phase 1 ----
    streaks = streak_stats(trades.win.tolist())
    cal = calendar_clustering(trades)
    cond = state_conditional_wr(trades)
    base_book = summarize_book(trades, base_n)
    verdict = cluster_verdict(cond, base_book["wr"])
    phase1 = {
        "baseline": base_book,
        "streaks": streaks,
        "calendar": cal,
        "state_conditional": cond,
        "verdict_notes": verdict,
        "first": str(trades.entry_dt.iloc[0]),
        "last": str(trades.entry_dt.iloc[-1]),
    }
    (OUT / "phase1_cluster.json").write_text(json.dumps(phase1, indent=2, default=str), encoding="utf-8")
    for n in verdict:
        _progress("VERDICT: " + n)

    # ---- Phase 2 ----
    weekly, monthly = build_prior_levels()
    ts_idx, highs, lows = load_15m()
    ann = annotate_levels(trades, weekly, monthly, ts_idx, highs, lows)
    ann.to_csv(OUT / "trades_annotated.csv", index=False)

    level_buckets = [
        bucket_stats(ann, ann.touch_prior_week_ext, "path_touch_prior_week_ext"),
        bucket_stats(ann, ~ann.touch_prior_week_ext, "no_path_touch_prior_week_ext"),
        bucket_stats(ann, ann.touch_prior_month_ext, "path_touch_prior_month_ext"),
        bucket_stats(ann, ~ann.touch_prior_month_ext, "no_path_touch_prior_month_ext"),
        bucket_stats(ann, ann.touch_any_wm, "path_touch_week_or_month_ext"),
        bucket_stats(ann, ~ann.touch_any_wm, "no_path_touch_week_or_month"),
        bucket_stats(ann, ann.near_prior_week_5, "entry_near_prior_week_ext_$5"),
        bucket_stats(ann, ann.near_prior_week_10, "entry_near_prior_week_ext_$10"),
        bucket_stats(ann, ann.near_prior_month_5, "entry_near_prior_month_ext_$5"),
        bucket_stats(ann, ann.near_prior_month_10, "entry_near_prior_month_ext_$10"),
        bucket_stats(ann, ann.near_any_wm_10, "entry_near_week_or_month_$10"),
        bucket_stats(ann, ~ann.near_any_wm_10, "entry_not_near_week_or_month_$10"),
        # long/short splits for week touch
        bucket_stats(
            ann,
            (ann.direction == "Long") & ann.touch_prior_week_ext,
            "long_path_touch_prior_week_high",
        ),
        bucket_stats(
            ann,
            (ann.direction == "Short") & ann.touch_prior_week_ext,
            "short_path_touch_prior_week_low",
        ),
        bucket_stats(
            ann,
            (ann.direction == "Long") & ann.touch_prior_month_ext,
            "long_path_touch_prior_month_high",
        ),
        bucket_stats(
            ann,
            (ann.direction == "Short") & ann.touch_prior_month_ext,
            "short_path_touch_prior_month_low",
        ),
    ]
    win_start = win_run_start_level_share(ann)
    phase2 = {"buckets": level_buckets, "win_run_starts_vs_touch": win_start}
    (OUT / "phase2_levels.json").write_text(json.dumps(phase2, indent=2, default=str), encoding="utf-8")
    _progress("levels done; win-run start touch share=%s" % win_start)

    # ---- Phase 3 ----
    _progress("skip grid...")
    skip_rows = run_skip_grid(trades)
    pd.DataFrame(skip_rows).to_csv(OUT / "skip_grid.csv", index=False)
    (OUT / "phase3_skip_grid.json").write_text(json.dumps(skip_rows, indent=2), encoding="utf-8")

    # rank by ns_proxy then mean_pts among rules with coverage >= 50%
    ranked = sorted(
        [r for r in skip_rows if r.get("coverage_pct", 0) >= 50],
        key=lambda r: (r.get("ns_proxy") or 0, r.get("mean_pts") or 0, r.get("net_pts") or 0),
        reverse=True,
    )
    summary = {
        "baseline_broker_ns_usd": 1.90,
        "phase1_verdict": verdict,
        "best_skip_rules_cov_ge_50": ranked[:5],
        "take_all": next(r for r in skip_rows if r["rule"] == "take_all"),
    }
    (OUT / "SUMMARY.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md = [
        "# XAUUSD M2_S2_R3 — cluster / levels / skip",
        "",
        "## Baseline (trade pts)",
        "- n=%d WR=%.1f%% net_pts=%.1f mean=%.4f maxL=%s stress=%.1f N/S_proxy=%.2f"
        % (
            base_book["n"],
            base_book["wr"],
            base_book["net_pts"],
            base_book["mean_pts"],
            base_book.get("max_loss_streak"),
            base_book["stress_pts"],
            base_book["ns_proxy"],
        ),
        "",
        "## Cluster verdict",
    ]
    md.extend(["- " + v for v in verdict])
    md.extend(
        [
            "",
            "## Calendar",
            "- top week %s net=%.1f share=%.1f%%"
            % (cal["top_week"], cal["top_week_net"], 100 * cal["top_week_share"]),
            "- top 5%% weeks share of gross + = %.1f%%" % (100 * cal["top_5pct_share_of_gross_pos"]),
            "",
            "## Skip grid (coverage ≥ 50%, ranked by N/S proxy)",
            "",
            "| rule | n | WR | net | mean | maxL | cover | stress | N/S |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for r in ranked[:8]:
        md.append(
            "| %s | %s | %s | %s | %s | %s | %s | %s | %s |"
            % (
                r["rule"],
                r["n"],
                r["wr"],
                r["net_pts"],
                r["mean_pts"],
                r.get("max_loss_streak"),
                r["coverage_pct"],
                r["stress_pts"],
                r["ns_proxy"],
            )
        )
    (OUT / "SUMMARY.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    _progress("DONE → %s" % OUT)


if __name__ == "__main__":
    main()
