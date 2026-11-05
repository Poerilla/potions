"""TOP3 (Asia Range + Monday OR + NAS100 Clean Break x10) calendar-year return cap on the joint 1m tape.

Walks the full-history union of USDJPY 1m and NAS100 RTH 1m bars over each
sleeve's Engine+PaperBroker fill units (same loader as
``top3_joint_1m_broker_portfolio``). Paper equity starts at $100,000 and
compounds by calendar year (America/New_York).

Cap rule: at each minute close, basket YTD = (realized + open close-MTM) minus
the mark at the year's first minute. Once YTD >= cap_pct x year-start paper
equity, every open unit is flattened at that minute's close (1 tick adverse,
round-trip fee) and every later unit entry is blocked until the next calendar
year. No downside limit.

Variants:

- ``baseline``   — no cap (validates the walk vs the published book)
- ``cap_fixed``  — cap on research lot size (as published)
- ``cap_scaled`` — cap with lot size scaled by year-start paper / $100k

Hub::

  live/state/top3_active_demo_portfolio/ytd_cap5_1m/

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.top3_ytd_cap_1m --cap-pct 0.05 --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run
from .top3_joint_1m_broker_portfolio import NY, _parse_ts, load_sleeve_units

PORTFOLIO = REPO / "live" / "state" / "top3_active_demo_portfolio"
START_EQUITY = 100_000.0
TICK = {"USDJPY": 0.001, "NAS100": 0.1}
INST_CODE = {"USDJPY": 0, "NAS100": 1}
VARIANTS = ("baseline", "cap_fixed", "cap_scaled")


def _hub(cap_pct: float) -> Path:
    return PORTFOLIO / ("ytd_cap%d_1m" % int(round(cap_pct * 100)))


def _progress(hub: Path, msg: str) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg.rstrip() + "\n")
    print(msg, flush=True)


def _load_1m(path: Path, rth_only: bool, lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    df = pd.read_csv(path, usecols=["ts_event", "high", "low", "close"])
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    df = df.assign(ts=ts).dropna(subset=["ts", "high", "low", "close"])
    df = df[(df["ts"] >= lo) & (df["ts"] <= hi)]
    local = df["ts"].dt.tz_convert(NY)
    if rth_only:
        t = local.dt.time
        keep = (local.dt.weekday < 5) & (t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())
        df = df[keep]
    return df.sort_values("ts")


def build_cache(hub: Path) -> Path:
    """Persist lots + merged 1m events as npz so variant workers load fast."""
    units = load_sleeve_units()
    rows = []
    for u in units:
        rows.append(
            {
                "sleeve": u.sleeve,
                "trade_id": u.unit.trade_id,
                "unit_id": u.unit.unit_id,
                "inst": INST_CODE[u.instrument],
                "sign": u.sign,
                "entry_ns": int(_parse_ts(u.entry_ts).value),
                "exit_ns": int(_parse_ts(u.exit_ts).value),
                "entry_px": float(u.unit.entry_price),
                "exit_px": float(u.unit.exit_price),
                "scale": u.point_value * u.size_mult / u.usd_div,
                "fee_usd": u.fee * u.size_mult / u.usd_div,
                "natural_usd": u.realized_usd(),
                "exit_reason": u.unit.exit_reason,
            }
        )
    lots = pd.DataFrame(rows)
    lots.to_csv(hub / "_cache_lots.csv", index=False)
    lo = pd.Timestamp(int(lots["entry_ns"].min()), tz="UTC") - pd.Timedelta(days=1)
    hi = pd.Timestamp(int(lots["exit_ns"].max()), tz="UTC") + pd.Timedelta(days=2)
    _progress(hub, "lots=%d natural net=$%.2f window %s → %s" % (len(lots), lots["natural_usd"].sum(), lo, hi))

    jpy = _load_1m(REPO / "fx" / "usdjpy_1m.csv", False, lo, hi)
    nas = _load_1m(REPO / "fx" / "nas100_1m.csv", True, lo, hi)
    _progress(hub, "USDJPY 1m=%d NAS100 RTH 1m=%d" % (len(jpy), len(nas)))
    def _ns(s: pd.Series) -> np.ndarray:
        return s.dt.tz_convert("UTC").dt.tz_localize(None).astype("datetime64[ns]").astype("int64").to_numpy()

    ts = np.concatenate([_ns(jpy["ts"]), _ns(nas["ts"])])
    inst = np.concatenate([np.zeros(len(jpy), dtype=np.int8), np.ones(len(nas), dtype=np.int8)])
    close = np.concatenate([jpy["close"].to_numpy(float), nas["close"].to_numpy(float)])
    high = np.concatenate([jpy["high"].to_numpy(float), nas["high"].to_numpy(float)])
    low = np.concatenate([jpy["low"].to_numpy(float), nas["low"].to_numpy(float)])
    order = np.lexsort((inst, ts))
    ts, inst, close, high, low = ts[order], inst[order], close[order], high[order], low[order]
    local = pd.DatetimeIndex(pd.to_datetime(ts, utc=True)).tz_convert(NY)
    year = local.year.to_numpy(np.int32)
    day = (local.year * 10000 + local.month * 100 + local.day).to_numpy(np.int32)
    path = hub / "_cache_events.npz"
    np.savez(path, ts=ts, inst=inst, close=close, high=high, low=low, year=year, day=day)
    return path


def walk(hub_str: str, variant: str, cap_pct: float) -> Dict[str, object]:
    hub = Path(hub_str)
    lots = pd.read_csv(hub / "_cache_lots.csv")
    ev = np.load(hub / "_cache_events.npz")
    ts_a = ev["ts"].tolist()
    inst_a = ev["inst"].tolist()
    close_a = ev["close"].tolist()
    high_a = ev["high"].tolist()
    low_a = ev["low"].tolist()
    year_a = ev["year"].tolist()
    day_a = ev["day"].tolist()
    capped = variant != "baseline"
    scaled = variant == "cap_scaled"

    n_lots = len(lots)
    l_inst = lots["inst"].tolist()
    l_sign = lots["sign"].tolist()
    l_entry_ns = lots["entry_ns"].tolist()
    l_exit_ns = lots["exit_ns"].tolist()
    l_entry_px = lots["entry_px"].tolist()
    l_scale = lots["scale"].tolist()
    l_fee = lots["fee_usd"].tolist()
    l_nat = lots["natural_usd"].tolist()
    tick = [TICK["USDJPY"], TICK["NAS100"]]

    by_entry = sorted(range(n_lots), key=lambda k: l_entry_ns[k])
    by_exit = sorted(range(n_lots), key=lambda k: l_exit_ns[k])
    status = [0] * n_lots  # 0 pending, 1 active, 2 natural exit, 3 cap flatten, 4 blocked
    mult = [1.0] * n_lots
    pnl = [0.0] * n_lots
    exit_ts_out = [0] * n_lots
    entry_i = exit_i = 0
    active: List[int] = []
    last_c = [math.nan, math.nan]
    last_h = [math.nan, math.nan]
    last_l = [math.nan, math.nan]

    realized = 0.0
    close_eq = 0.0
    cur_year: Optional[int] = None
    ys_eq = 0.0
    paper0 = START_EQUITY
    cap_usd = math.inf
    locked = False
    year_peak = 0.0
    year_dd = 0.0
    year_max_ytd = 0.0
    lock_info: Dict[str, object] = {}
    peak = 0.0
    close_dd = 0.0
    stress_dd = 0.0
    years: List[dict] = []
    daily: List[dict] = []
    cur_day: Optional[int] = None
    day_close = day_stress = day_real = 0.0
    day_open = 0
    day_ts = 0

    def _close_year() -> None:
        years.append(
            {
                "year": cur_year,
                "start_paper": paper0,
                "start_mark_usd": ys_eq,
                "cap_usd": cap_usd if capped else math.nan,
                "net_usd": close_eq - ys_eq,
                "return": (close_eq - ys_eq) / paper0,
                "max_ytd_return": year_max_ytd / paper0,
                "stress_dd_usd": year_dd,
                "stress_dd_pct": year_dd / paper0,
                "locked": bool(locked),
                **lock_info,
            }
        )

    n_ev = len(ts_a)
    for i in range(n_ev):
        t = ts_a[i]
        k = inst_a[i]
        last_c[k] = close_a[i]
        last_h[k] = high_a[i]
        last_l[k] = low_a[i]

        d = day_a[i]
        if d != cur_day:
            if cur_day is not None:
                daily.append(
                    {
                        "ts_ns": day_ts,
                        "realized_usd": day_real,
                        "open_units": day_open,
                        "close_equity_usd": day_close,
                        "intrabar_stress_equity_usd": day_stress,
                    }
                )
            cur_day = d
            day_stress = math.inf
            y = year_a[i]
            if y != cur_year:
                if cur_year is not None:
                    _close_year()
                cur_year = y
                ys_eq = close_eq
                paper0 = START_EQUITY + ys_eq
                cap_usd = cap_pct * paper0 if capped else math.inf
                locked = False
                year_peak = close_eq
                year_dd = 0.0
                year_max_ytd = 0.0
                lock_info = {}

        exited = False
        while exit_i < n_lots and l_exit_ns[by_exit[exit_i]] < t:
            j = by_exit[exit_i]
            exit_i += 1
            if status[j] == 1:
                status[j] = 2
                pnl[j] = l_nat[j] * mult[j]
                exit_ts_out[j] = l_exit_ns[j]
                realized += pnl[j]
                exited = True
        while entry_i < n_lots and l_entry_ns[by_entry[entry_i]] <= t:
            j = by_entry[entry_i]
            entry_i += 1
            if status[j] != 0:
                continue
            if locked:
                status[j] = 4
                lock_info["blocked_units"] = lock_info.get("blocked_units", 0) + 1
                lock_info["blocked_natural_usd"] = lock_info.get("blocked_natural_usd", 0.0) + l_nat[j] * (
                    paper0 / START_EQUITY if scaled else 1.0
                )
                continue
            status[j] = 1
            mult[j] = paper0 / START_EQUITY if scaled else 1.0
            active.append(j)
        if exited:
            active = [j for j in active if status[j] == 1]

        if active:
            mtm = 0.0
            imtm = 0.0
            for j in active:
                q = l_inst[j]
                c = last_c[q]
                if c != c:
                    continue
                sc = l_scale[j] * mult[j] * l_sign[j]
                mtm += (c - l_entry_px[j]) * sc
                px = last_l[q] if l_sign[j] > 0 else last_h[q]
                imtm += (px - l_entry_px[j]) * sc
            close_eq = realized + mtm
            stress_eq = realized + imtm
        else:
            close_eq = realized
            stress_eq = realized

        if capped and not locked and active and close_eq - ys_eq >= cap_usd:
            forced_usd = 0.0
            for j in active:
                q = l_inst[j]
                px = last_c[q] - l_sign[j] * tick[q]
                v = ((px - l_entry_px[j]) * l_scale[j] * l_sign[j] - l_fee[j]) * mult[j]
                pnl[j] = v
                status[j] = 3
                exit_ts_out[j] = t
                forced_usd += v
                lock_info["natural_of_forced_usd"] = lock_info.get("natural_of_forced_usd", 0.0) + l_nat[j] * mult[j]
            realized += forced_usd
            lock_info.update(
                {
                    "lock_ts": pd.Timestamp(t, tz="UTC").tz_convert(NY).isoformat(),
                    "ytd_mark_at_trigger_usd": close_eq - ys_eq,
                    "forced_units": len(active),
                    "forced_usd": forced_usd,
                }
            )
            active = []
            close_eq = realized
            stress_eq = min(stress_eq, realized)
            locked = True
        elif capped and not locked and not active and close_eq - ys_eq >= cap_usd:
            lock_info.update(
                {
                    "lock_ts": pd.Timestamp(t, tz="UTC").tz_convert(NY).isoformat(),
                    "ytd_mark_at_trigger_usd": close_eq - ys_eq,
                    "forced_units": 0,
                    "forced_usd": 0.0,
                }
            )
            locked = True

        stress_dd = min(stress_dd, stress_eq - peak)
        close_dd = min(close_dd, close_eq - peak)
        peak = max(peak, close_eq)
        year_dd = min(year_dd, stress_eq - year_peak)
        year_peak = max(year_peak, close_eq)
        year_max_ytd = max(year_max_ytd, close_eq - ys_eq)
        day_close = close_eq
        day_stress = min(day_stress, stress_eq)
        day_real = realized
        day_open = len(active)
        day_ts = t

    if cur_day is not None:
        daily.append(
            {
                "ts_ns": day_ts,
                "realized_usd": day_real,
                "open_units": day_open,
                "close_equity_usd": day_close,
                "intrabar_stress_equity_usd": day_stress,
            }
        )
    if cur_year is not None:
        _close_year()
    # Units exiting after the last bar realize at their natural price.
    for j in active:
        pnl[j] = l_nat[j] * mult[j]
        status[j] = 2
        exit_ts_out[j] = l_exit_ns[j]
        realized += pnl[j]
    close_eq = realized

    out = lots.copy()
    out["status"] = pd.Series(status).map({0: "never", 1: "open", 2: "natural", 3: "cap_flatten", 4: "blocked"})
    out["size_mult"] = mult
    out["net_usd"] = pnl
    out["walk_exit_ns"] = exit_ts_out
    vdir = hub / variant
    vdir.mkdir(parents=True, exist_ok=True)
    out.to_csv(vdir / "units_walked.csv", index=False)
    pd.DataFrame(years).to_csv(vdir / "yearly_cap_board.csv", index=False)
    pd.DataFrame(daily).to_csv(vdir / "equity_daily.csv", index=False)
    res = {
        "variant": variant,
        "cap_pct": cap_pct if capped else None,
        "net_usd": realized,
        "close_mtm_dd_usd": close_dd,
        "intrabar_stress_dd_usd": stress_dd,
        "net_over_stress": realized / abs(stress_dd) if stress_dd else 0.0,
        "units_taken": int(sum(1 for s in status if s in (2, 3))),
        "units_blocked": int(sum(1 for s in status if s == 4)),
        "units_cap_flatten": int(sum(1 for s in status if s == 3)),
        "events": n_ev,
    }
    (vdir / "walk_metrics.json").write_text(json.dumps(res, indent=2), encoding="utf-8")
    return res


def write_state(hub: Path, variant: str, cap_pct: float) -> Path:
    """Deep-check state root: synthetic buy/sell fills + authoritative unit_trades nets."""
    vdir = hub / variant
    units = pd.read_csv(vdir / "units_walked.csv")
    units = units[units["status"].isin(["natural", "cap_flatten"])].copy()
    sid = "top3_cb10x_ytd_cap%d_1m_%s" % (int(round(cap_pct * 100)), variant)
    state = PORTFOLIO / "states" / sid
    state.mkdir(parents=True, exist_ok=True)

    def _iso(ns: pd.Series) -> pd.Series:
        return pd.to_datetime(ns.astype("int64"), utc=True).dt.tz_convert(NY).map(lambda x: x.isoformat())

    units["entry_ts"] = _iso(units["entry_ns"])
    units["exit_ts"] = _iso(units["walk_exit_ns"])
    units["reason"] = np.where(units["status"] == "cap_flatten", "ytd_cap_flatten", units["exit_reason"].astype(str))
    units["trade_id"] = units["sleeve"] + "::" + units["trade_id"].astype(str).str.split("::").str[-1]

    fills = []
    for r in units.itertuples(index=False):
        for kind, ts, side, reason in (("e", r.entry_ts, "buy", "entry"), ("x", r.exit_ts, "sell", r.reason)):
            fills.append(
                {
                    "fill_id": "%s_%s_%s" % (kind, r.trade_id, r.unit_id),
                    "broker_order_id": "",
                    "intent_id": "",
                    "strategy_id": sid,
                    "trade_id": r.trade_id,
                    "instrument": "MULTI",
                    "account_mode": "paper",
                    "side": side,
                    "quantity": 1,
                    "price": 0.0,
                    "ts": ts,
                    "reason": reason,
                }
            )
    pd.DataFrame(fills).to_csv(state / "fills.csv", index=False)
    ut = pd.DataFrame(
        {
            "trade_id": units["trade_id"],
            "entry_ts": units["entry_ts"],
            "exit_ts": units["exit_ts"],
            "side": np.where(units["sign"] > 0, "long", "short"),
            "net_usd": units["net_usd"],
            "sleeve": units["sleeve"],
            "candidate": units["sleeve"],
            "unit_id": units["unit_id"],
            "direction": np.where(units["sign"] > 0, "long", "short"),
            "entry_price": 0.0,
            "exit_price": 0.0,
            "exit_reason": units["reason"],
        }
    )
    ut.to_csv(state / "unit_trades.csv", index=False)

    eq = pd.read_csv(vdir / "equity_daily.csv")
    eq["ts"] = _iso(eq["ts_ns"])
    peak = eq["close_equity_usd"].cummax().clip(lower=0.0)
    eq["close_dd_usd"] = eq["close_equity_usd"] - peak
    eq["intrabar_stress_dd_usd"] = eq["intrabar_stress_equity_usd"] - peak
    eq[
        [
            "ts",
            "realized_usd",
            "open_units",
            "close_equity_usd",
            "intrabar_stress_equity_usd",
            "close_dd_usd",
            "intrabar_stress_dd_usd",
        ]
    ].to_csv(state / "equity_curve.csv", index=False)
    wm = json.loads((vdir / "walk_metrics.json").read_text())
    (state / "metrics.json").write_text(
        json.dumps(
            {
                "symbol": "NAS100",
                "quote": "USD",
                "strategy_id": sid,
                "instrument": "PORTFOLIO",
                "variant_slug": sid,
                "label": "TOP3 x10 YTD cap %d%% (%s, joint 1m)" % (int(round(cap_pct * 100)), variant),
                "net_usd": wm["net_usd"],
                "closed_dd_usd": wm["close_mtm_dd_usd"],
                "stress_dd_usd": wm["intrabar_stress_dd_usd"],
                "net_over_stress": wm["net_over_stress"],
                "note": "Asia Range + Monday OR + NAS100 Clean Break x10 Engine fill units on a joint 1m clock; "
                "basket flattened and entries blocked for the rest of the calendar year once YTD mark >= cap.",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return state


def _money(x: float) -> str:
    return "%s$%s" % ("-" if x < 0 else "", f"{abs(x):,.0f}")


def _pct(x: float) -> str:
    return "%+.2f%%" % (100.0 * x)


def cagr_stats(board: pd.DataFrame, first_ns: int, last_ns: int) -> Dict[str, float]:
    end = START_EQUITY + float(board["net_usd"].sum())
    span_years = (last_ns - first_ns) / (365.25 * 86400e9)
    full = board[(board["year"] > board["year"].min()) & (board["year"] < board["year"].max())]
    full_growth = float(np.prod(1.0 + full["return"].to_numpy()))
    return {
        "end_equity": end,
        "span_years": span_years,
        "cagr_time": (end / START_EQUITY) ** (1.0 / span_years) - 1.0,
        "full_years": f"{int(full['year'].min())}-{int(full['year'].max())}",
        "n_full_years": int(len(full)),
        "cagr_full_years": full_growth ** (1.0 / len(full)) - 1.0,
        "median_full_year_return": float(full["return"].median()),
        "years_locked": int(board["locked"].sum()),
        "losing_years": int((board["return"] < 0).sum()),
        "worst_year_return": float(board["return"].min()),
        "worst_year_stress_pct": float(board["stress_dd_pct"].min()),
    }


def report(hub: Path, cap_pct: float, results: Dict[str, dict], deep: Dict[str, Path]) -> str:
    lots = pd.read_csv(hub / "_cache_lots.csv")
    first_ns, last_ns = int(lots["entry_ns"].min()), int(lots["exit_ns"].max())
    boards = {v: pd.read_csv(hub / v / "yearly_cap_board.csv") for v in VARIANTS}
    stats = {v: cagr_stats(boards[v], first_ns, last_ns) for v in VARIANTS}
    rows = []
    for v in VARIANTS:
        rows.append({"variant": v, **results[v], **stats[v]})
    pd.DataFrame(rows).to_csv(hub / "comparison.csv", index=False)
    cp = int(round(cap_pct * 100))

    lines = [
        "# TOP3 x10 calendar-year %d%% cap on the joint 1m tape" % cp,
        "",
        "Book: USDJPY Asia Range `S_3_1_3_flt` + USDJPY Monday OR `M2_S3_R1` (skip Aug/Sep) + NAS100 Clean Break "
        "`trail06_m4_e2_out_be` x10. Engine+PaperBroker fill units, full history %s → %s."
        % (
            pd.Timestamp(first_ns, tz="UTC").tz_convert(NY).date(),
            pd.Timestamp(last_ns, tz="UTC").tz_convert(NY).date(),
        ),
        "",
        "## Rule",
        "",
        "- Paper equity starts at $100,000 and compounds by NY calendar year.",
        "- Each minute close: basket YTD = realized + open close-MTM, minus the mark at the year's first minute.",
        "- When YTD >= %d%% of year-start paper equity, all open units are flattened at that minute's close "
        "(1 tick adverse + fee) and every later entry that year is blocked. No downside limit." % cp,
        "- `cap_fixed` keeps the published research lot sizes. `cap_scaled` scales lots by year-start paper / $100k.",
        "",
        "## Headline",
        "",
        "| variant | end equity | net | time CAGR | full-year CAGR (%s) | median full year | years capped | losing years | worst year | worst year stress | joint stress DD | N/S |"
        % stats["baseline"]["full_years"],
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for v in VARIANTS:
        s, r = stats[v], results[v]
        lines.append(
            "| %s | %s | %s | %s | %s | %s | %d | %d | %s | %s | %s | %.2f |"
            % (
                v,
                _money(s["end_equity"]),
                _money(r["net_usd"]),
                _pct(s["cagr_time"]),
                _pct(s["cagr_full_years"]),
                _pct(s["median_full_year_return"]),
                s["years_locked"],
                s["losing_years"],
                _pct(s["worst_year_return"]),
                _pct(s["worst_year_stress_pct"]),
                _money(r["intrabar_stress_dd_usd"]),
                r["net_over_stress"],
            )
        )
    lines += ["", "Time CAGR uses the elapsed span (%.2f years, partial first/last years included)." % stats["baseline"]["span_years"], ""]

    for v in ("cap_fixed", "cap_scaled"):
        b = boards[v]
        lines += [
            "## %s — yearly" % v,
            "",
            "| year | start paper | return | max YTD | stress % | cap hit (NY) | trigger YTD | forced units | forced $ | forced natural $ | blocked units | blocked natural $ |",
            "|---:|---:|---:|---:|---:|:---|---:|---:|---:|---:|---:|---:|",
        ]
        for g in b.to_dict("records"):
            lines.append(
                "| %d | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |"
                % (
                    g["year"],
                    _money(g["start_paper"]),
                    _pct(g["return"]),
                    _pct(g["max_ytd_return"]),
                    _pct(g["stress_dd_pct"]),
                    str(g.get("lock_ts"))[:16] if isinstance(g.get("lock_ts"), str) else "",
                    _pct(g["ytd_mark_at_trigger_usd"] / g["start_paper"]) if pd.notna(g.get("ytd_mark_at_trigger_usd")) else "",
                    "%d" % g["forced_units"] if pd.notna(g.get("forced_units")) else "",
                    _money(g["forced_usd"]) if pd.notna(g.get("forced_usd")) else "",
                    _money(g["natural_of_forced_usd"]) if pd.notna(g.get("natural_of_forced_usd")) else "",
                    "%d" % g["blocked_units"] if pd.notna(g.get("blocked_units")) else "",
                    _money(g["blocked_natural_usd"]) if pd.notna(g.get("blocked_natural_usd")) else "",
                )
            )
        lines.append("")

    lines += ["## Deep-check (no charts)", ""]
    for v, p in deep.items():
        y = pd.read_csv(p / "yearly_breakdown.csv")
        end = float(y["end_equity_100k"].iloc[-1])
        n = len(y)
        lines.append(
            "- `%s`: `%s` — entry-year compound end %s over %d year rows → %s/yr; avg yearly N/S %.2f; worst year %s"
            % (
                v,
                p.relative_to(REPO),
                _money(end),
                n,
                _pct((end / START_EQUITY) ** (1.0 / n) - 1.0),
                float(y["net_over_stress"].mean()),
                _pct(float(y["return_on_start_equity"].min())),
            )
        )
    lines.append("")
    text = "\n".join(lines) + "\n"
    (hub / "SUMMARY.md").write_text(text, encoding="utf-8")
    (hub / "run_meta.json").write_text(json.dumps({"cap_pct": cap_pct, "stats": stats, "results": results}, indent=2, default=str))
    return text


def run(cap_pct: float, email: bool) -> None:
    hub = _hub(cap_pct)
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")
    rid = begin_run(
        run_class="broker_like",
        variant_slug="top3_cb10x_ytd_cap%d_1m" % int(round(cap_pct * 100)),
        instrument="PORTFOLIO",
        hub_path=str(hub),
        meta={"cap_pct": cap_pct, "variants": list(VARIANTS), "sleeves": ["asia_range", "monday_or", "clean_break"]},
    )
    try:
        _progress(hub, "Building lot + 1m event cache ...")
        build_cache(hub)
        _progress(hub, "Walking variants %s in parallel ..." % ", ".join(VARIANTS))
        with ProcessPoolExecutor(max_workers=len(VARIANTS)) as ex:
            futs = {v: ex.submit(walk, str(hub), v, cap_pct) for v in VARIANTS}
            results = {v: f.result() for v, f in futs.items()}
        for v, r in results.items():
            _progress(hub, "  %s net=%s stress=%s N/S=%.2f blocked=%d flattened=%d" % (
                v, _money(r["net_usd"]), _money(r["intrabar_stress_dd_usd"]), r["net_over_stress"],
                r["units_blocked"], r["units_cap_flatten"]))

        from .instrument_deep_check import run_deep_check

        deep: Dict[str, Path] = {}
        for v in ("cap_fixed", "cap_scaled"):
            state = write_state(hub, v, cap_pct)
            deep[v] = run_deep_check(
                state,
                label="TOP3 x10 YTD cap %d%% %s (joint 1m)" % (int(round(cap_pct * 100)), v),
                email=False,
                charts=False,
            )
        text = report(hub, cap_pct, results, deep)
        for name in ("_cache_events.npz", "_cache_lots.csv"):
            (hub / name).unlink(missing_ok=True)
        r = results["cap_fixed"]
        complete_run(
            rid,
            net_usd=float(r["net_usd"]),
            stress_dd_usd=float(r["intrabar_stress_dd_usd"]),
            close_mtm_dd_usd=float(r["close_mtm_dd_usd"]),
            ns=float(r["net_over_stress"]),
            trades=int(r["units_taken"]),
            yearly_csv_path=deep["cap_fixed"] / "yearly_breakdown.csv",
            meta={"cap_pct": cap_pct, "results": results},
        )
        (hub / "EMAIL.txt").write_text("Hub: %s\n\n%s" % (hub, text), encoding="utf-8")
        _progress(hub, "DONE")
        if email:
            send_email(
                subject="potions: TOP3 YTD %d%% cap joint 1m + deep-check complete" % int(round(cap_pct * 100)),
                body=(hub / "EMAIL.txt").read_text(encoding="utf-8"),
            )
    except Exception:
        fail_run(rid, notes=traceback.format_exc()[-2000:])
        (hub / "FAIL.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if email:
            send_email(
                subject="potions: TOP3 YTD cap joint 1m FAILED",
                body="Hub: %s\n\n%s" % (hub, traceback.format_exc()[-3000:]),
            )
        raise


def main() -> None:
    ap = argparse.ArgumentParser(description="TOP3 x10 calendar-year return cap on the joint 1m tape")
    ap.add_argument("--cap-pct", type=float, default=0.05)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    run(cap_pct=float(args.cap_pct), email=bool(args.email))


if __name__ == "__main__":
    main()
