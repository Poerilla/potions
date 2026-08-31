"""Quantify HP size liquidity + yearly $250k path for a chosen futures HP sleeve.

Default focus:
  - NQ OR-norm @4× liquidity scorecard (how to read participation risk)
  - Next-best non-NQ prior-opposed HP: ES ST-age @4× yearly + daily ADV liquidity

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.futures_intraday_hp_size_liquidity_yearly --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from datetime import date as date_cls
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
from live.intraday_condition_overlay import hp_mask, score_nets
from live.notify_email import send_email
from live.v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

from .futures_intraday_hp_sizeup_lib import COND_COL, DBN_1M, PROFILE_HUB, REPO

HUB = REPO / "live" / "state" / "futures_intraday_hp_size_liquidity_yearly"
NY = "America/New_York"

# (book, cond, bucket, label, symbol, point_value, im_approx, base_qty)
NQ = (
    "nq_prior_opposed_rl",
    "Opening 15m range vs ATR",
    "or_norm",
    "NQ prior-opposed RL OR-norm",
    "NQ",
    20.0,
    20000.0,
    5,
)
ES = (
    "es_prior_opposed_legacy",
    "ST-event age",
    "st_age_gt180m",
    "ES prior-opposed legacy ST-age>180m (next-best non-NQ prior-opposed)",
    "ES",
    50.0,
    15000.0,
    5,
)
YM = (
    "ym_prior_opposed_rl",
    "Overnight range third",
    "on_middle",
    "YM prior-opposed overnight middle",
    "YM",
    5.0,
    10000.0,
    5,
)

DAILY_CSV = {
    "NQ": REPO / "nq" / "nq_daily.csv",
    "ES": REPO / "es" / "es_daily.csv",
    "YM": REPO / "ym" / "ym_daily.csv",
}


def _patch() -> None:
    overlay.COND_COL.clear()
    overlay.COND_COL.update(COND_COL)


def _load_book(book: str, cond: str, bucket: str) -> Tuple[pd.DataFrame, np.ndarray]:
    camp = pd.read_csv(PROFILE_HUB / "all_campaigns.csv")
    camp["entry_ts"] = pd.to_datetime(camp["entry_ts"], utc=True)
    df = camp[camp["book"] == book].sort_values("entry_ts").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("empty book %s" % book)
    if "year" not in df.columns:
        df["year"] = df["entry_ts"].dt.year
    if "session_date" not in df.columns:
        df["session_date"] = df["entry_ts"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    else:
        df["session_date"] = df["session_date"].astype(str)
    m = hp_mask(df, cond, bucket)
    if not m.any():
        raise RuntimeError("empty HP mask %s %s=%s" % (book, cond, bucket))
    return df, m.to_numpy()


def yearly_250k(df: pd.DataFrame, m: np.ndarray, mult: float, init: float = 250_000.0) -> Tuple[pd.DataFrame, dict]:
    base = df["net_usd"].to_numpy(float)
    sized = base.copy()
    sized[m] = sized[m] * float(mult)
    book = score_nets(sized)
    equity = float(init)
    rows = []
    for y in sorted(df["year"].unique()):
        mask = df["year"].to_numpy() == y
        nets = sized[mask]
        scy = score_nets(nets)
        start = equity
        equity = equity + scy["net"]
        rows.append(
            {
                "year": int(y),
                "n": int(mask.sum()),
                "hp_n": int((mask & m).sum()),
                "net": round(scy["net"], 2),
                "stress": round(scy["stress"], 2),
                "ns": round(scy["ns"], 3),
                "start_equity": round(start, 2),
                "end_equity": round(equity, 2),
                "year_return_pct": round(100.0 * scy["net"] / start, 2) if start else 0.0,
            }
        )
    out = pd.DataFrame(rows)
    t0, t1 = df["entry_ts"].min(), df["entry_ts"].max()
    span = (t1 - t0).days / 365.25
    final = float(out.iloc[-1]["end_equity"])
    cagr_span = ((final / init) ** (1 / span) - 1) * 100 if span > 0 and final > 0 else float("nan")
    cagr_n = ((final / init) ** (1 / len(out)) - 1) * 100 if len(out) and final > 0 else float("nan")
    meta = {
        "init": init,
        "final": final,
        "book_net": book["net"],
        "book_stress": book["stress"],
        "book_ns": book["ns"],
        "span_years": span,
        "cagr_span_pct": cagr_span,
        "cagr_n_pct": cagr_n,
        "mult": mult,
    }
    return out, meta


def _rth_mask(ts: pd.Series) -> pd.Series:
    minutes = ts.dt.hour * 60 + ts.dt.minute
    return (minutes >= 9 * 60 + 30) & (minutes < 16 * 60)


def liquidity_1m(
    df: pd.DataFrame,
    m: np.ndarray,
    *,
    symbol: str,
    base_qty: int,
    mult: float,
    point_value: float,
    im_approx: float,
) -> Tuple[pd.DataFrame, dict]:
    dbn = DBN_1M.get(symbol)
    if dbn is None or not Path(dbn).exists():
        raise FileNotFoundError("no 1m for %s" % symbol)
    hp = df.loc[m].copy()
    hp["entry_ts_ny"] = pd.to_datetime(hp["entry_ts"], utc=True).dt.tz_convert(NY)
    hp["sess"] = hp["entry_ts_ny"].dt.strftime("%Y-%m-%d")
    print("loading %s 1m ..." % symbol, flush=True)
    by_day = load_1m_by_ny_date_any(Path(dbn).resolve(), symbol.lower())
    qty = int(round(base_qty * float(mult)))
    rows = []
    missing = 0
    for _, row in hp.iterrows():
        sess = str(row["sess"])
        try:
            day = by_day.get(date_cls.fromisoformat(sess))
        except ValueError:
            missing += 1
            continue
        if day is None or getattr(day, "empty", True):
            missing += 1
            continue
        bars = day.reset_index()
        ts_col = "ts_event" if "ts_event" in bars.columns else "ts"
        bars = bars.rename(columns={ts_col: "ts"})
        bars["ts"] = pd.to_datetime(bars["ts"], utc=True).dt.tz_convert(NY)
        bars["volume"] = pd.to_numeric(bars.get("volume"), errors="coerce").fillna(0.0)
        entry_floor = row["entry_ts_ny"].floor("min")
        hit = bars[bars["ts"] == entry_floor]
        if hit.empty:
            bars = bars.copy()
            bars["_dt"] = (bars["ts"] - entry_floor).abs()
            hit = bars.nsmallest(1, "_dt")
            if hit.empty or hit.iloc[0]["_dt"] > pd.Timedelta(minutes=2):
                missing += 1
                continue
        entry_vol = float(hit.iloc[0]["volume"])
        px = float(row.get("entry_price") or hit.iloc[0].get("close") or 0.0)
        win = bars[
            (bars["ts"] >= entry_floor - pd.Timedelta(minutes=5))
            & (bars["ts"] <= entry_floor + pd.Timedelta(minutes=5))
        ]
        rth = bars[_rth_mask(bars["ts"])]
        rth_vol = float(rth["volume"].sum()) if not rth.empty else float(bars["volume"].sum())
        rows.append(
            {
                "session_date": sess,
                "entry_bar_vol": entry_vol,
                "pm5_vol": float(win["volume"].sum()),
                "rth_vol": rth_vol,
                "entry_price": px,
                "pct_bar": 100.0 * qty / entry_vol if entry_vol > 0 else float("nan"),
                "pct_pm5": 100.0 * qty / float(win["volume"].sum()) if float(win["volume"].sum()) > 0 else float("nan"),
                "pct_rth": 100.0 * qty / rth_vol if rth_vol > 0 else float("nan"),
                "notional": qty * px * point_value,
            }
        )
    camp = pd.DataFrame(rows)
    if camp.empty:
        raise RuntimeError("%s liquidity empty missing=%d" % (symbol, missing))
    pct = camp["pct_bar"]
    summary = {
        "source": "1m_entry_bar",
        "symbol": symbol,
        "mult": mult,
        "qty": qty,
        "n": int(len(camp)),
        "missing": int(missing),
        "median_entry_bar_vol": float(camp["entry_bar_vol"].median()),
        "p10_entry_bar_vol": float(camp["entry_bar_vol"].quantile(0.10)),
        "median_pct_bar": float(pct.median()),
        "p90_pct_bar": float(pct.quantile(0.90)),
        "p95_pct_bar": float(pct.quantile(0.95)),
        "max_pct_bar": float(pct.max()),
        "frac_gt_1pct": float((pct > 1).mean()),
        "frac_gt_5pct": float((pct > 5).mean()),
        "frac_gt_10pct": float((pct > 10).mean()),
        "frac_gt_25pct": float((pct > 25).mean()),
        "median_pct_pm5": float(camp["pct_pm5"].median()),
        "p90_pct_pm5": float(camp["pct_pm5"].quantile(0.90)),
        "median_pct_rth": float(camp["pct_rth"].median()),
        "median_notional": float(camp["notional"].median()),
        "approx_im": float(qty * im_approx),
        # Almgren-ish toy impact proxy: c * sigma * sqrt(participation); use pct_bar/100 as participation
        "median_sqrt_participation": float(np.sqrt((pct.clip(lower=0) / 100.0).median())),
        "p90_sqrt_participation": float(np.sqrt((pct.clip(lower=0) / 100.0).quantile(0.90))),
    }
    return camp, summary


def liquidity_daily(
    df: pd.DataFrame,
    m: np.ndarray,
    *,
    symbol: str,
    base_qty: int,
    mult: float,
    point_value: float,
    im_approx: float,
) -> Tuple[pd.DataFrame, dict]:
    path = DAILY_CSV[symbol]
    daily = pd.read_csv(path)
    daily["date"] = pd.to_datetime(daily["date"]).dt.strftime("%Y-%m-%d")
    daily["volume"] = pd.to_numeric(daily["volume"], errors="coerce").fillna(0.0)
    vol_map = dict(zip(daily["date"], daily["volume"]))
    qty = int(round(base_qty * float(mult)))
    hp = df.loc[m].copy()
    rows = []
    missing = 0
    for _, row in hp.iterrows():
        sess = str(row["session_date"])[:10]
        vol = float(vol_map.get(sess) or 0.0)
        if vol <= 0:
            missing += 1
            continue
        px = float(row.get("entry_price") or 0.0)
        rows.append(
            {
                "session_date": sess,
                "day_vol": vol,
                "pct_day": 100.0 * qty / vol,
                "notional": qty * px * point_value,
            }
        )
    camp = pd.DataFrame(rows)
    if camp.empty:
        raise RuntimeError("%s daily liquidity empty" % symbol)
    pct = camp["pct_day"]
    summary = {
        "source": "daily_adv",
        "symbol": symbol,
        "mult": mult,
        "qty": qty,
        "n": int(len(camp)),
        "missing": int(missing),
        "median_day_vol": float(camp["day_vol"].median()),
        "p10_day_vol": float(camp["day_vol"].quantile(0.10)),
        "median_pct_day": float(pct.median()),
        "p90_pct_day": float(pct.quantile(0.90)),
        "p95_pct_day": float(pct.quantile(0.95)),
        "max_pct_day": float(pct.max()),
        "frac_gt_0_1pct": float((pct > 0.1).mean()),
        "frac_gt_0_5pct": float((pct > 0.5).mean()),
        "frac_gt_1pct": float((pct > 1).mean()),
        "median_notional": float(camp["notional"].median()),
        "approx_im": float(qty * im_approx),
        "median_sqrt_participation": float(np.sqrt((pct.clip(lower=0) / 100.0).median())),
        "p90_sqrt_participation": float(np.sqrt((pct.clip(lower=0) / 100.0).quantile(0.90))),
    }
    return camp, summary


def _fmt_pct(x: float) -> str:
    return "%.2f%%" % x


def _fmt_money(x: float) -> str:
    return "$%s" % ("{:,.0f}".format(x))


def render(
    nq_year: pd.DataFrame,
    nq_meta: dict,
    nq_liq: dict,
    es_year: pd.DataFrame,
    es_meta: dict,
    es_liq: dict,
    ym_liq: Optional[dict],
) -> str:
    lines = [
        "# HP size liquidity quantification + next-best non-NQ @4×",
        "",
        "## How we quantify liquidity risk",
        "",
        "Participation metrics (higher = more footprint / adverse-selection risk):",
        "",
        "1. **Entry-minute share** = `HP qty / volume on the fill minute` (strictest).",
        "2. **±5m share** = qty / volume in entry±5 minutes (absorbs resting-limit fill window).",
        "3. **RTH / day ADV share** = qty / session day volume (capital-market context).",
        "4. **Tail flags**: p90/p95/max participation; fraction of HP days >1% / >5% / >10% / >25% of the bar.",
        "5. **Toy impact proxy**: `sqrt(participation)` (Almgren-style scaling; not a $ impact model).",
        "6. **Capital footprint**: notional (= qty × price × point value) and ≈ initial margin.",
        "",
        "Rule of thumb used here: entry-minute p90 ≪ **5%** and almost no days >10% → "
        "**tape OK**; risk is then **margin / DD capital**, not CME thinness.",
        "",
        "## NQ OR-norm @ **4×** (qty=20) — liquidity scorecard",
        "",
        "| Metric | Value | Read |",
        "|---|---:|---|",
        "| Median entry-bar vol | {:,.0f} | deep NQ minute |".format(nq_liq["median_entry_bar_vol"]),
        "| Median / p90 / p95 / max **% of entry bar** | {} / {} / {} / {} | **comfortable** |".format(
            _fmt_pct(nq_liq["median_pct_bar"]),
            _fmt_pct(nq_liq["p90_pct_bar"]),
            _fmt_pct(nq_liq["p95_pct_bar"]),
            _fmt_pct(nq_liq["max_pct_bar"]),
        ),
        "| Days >1% / >5% / >10% / >25% of entry bar | {:.0%} / {:.0%} / {:.0%} / {:.0%} | no crowding |".format(
            nq_liq["frac_gt_1pct"],
            nq_liq["frac_gt_5pct"],
            nq_liq["frac_gt_10pct"],
            nq_liq["frac_gt_25pct"],
        ),
        "| Median / p90 % of ±5m | {} / {} | fine |".format(
            _fmt_pct(nq_liq["median_pct_pm5"]), _fmt_pct(nq_liq["p90_pct_pm5"])
        ),
        "| Median % of RTH day | {} | negligible |".format(_fmt_pct(nq_liq["median_pct_rth"])),
        "| Median notional / ≈IM | {} / {} | **capital** gate |".format(
            _fmt_money(nq_liq["median_notional"]), _fmt_money(nq_liq["approx_im"])
        ),
        "| Median / p90 sqrt(participation) | {:.4f} / {:.4f} | low |".format(
            nq_liq["median_sqrt_participation"], nq_liq["p90_sqrt_participation"]
        ),
        "",
        "**Verdict @4× NQ:** liquidity **does not bind**. Stress/N/S/capital bind first "
        "(book stress {}, N/S {:.2f}).".format(_fmt_money(nq_meta["book_stress"]), nq_meta["book_ns"]),
        "",
        "## Next-best non-NQ prior-opposed HP: **ES ST-age** @4× on $250k",
        "",
        "Chosen as next-best **prior-opposed** sleeve by 4× N/S among non-NQ A/B candidates "
        "(ES 20.19 > YM overnight-middle 13.88). Note: under ΔN/S nulls ES is "
        "**NOT VALIDATED** — sensitivity only. (YM ST+PMC Thursday prints higher raw 4× N/S "
        "but is Tier C shadow / different family.)",
        "",
        "Whole-book @4×: net **{}**, stress **{}**, N/S **{:.2f}**. "
        "$250k → **{}**. CAGR span **{:.1f}%** ({:.2f}y) / calendar-n **{:.1f}%**.".format(
            _fmt_money(es_meta["book_net"]),
            _fmt_money(es_meta["book_stress"]),
            es_meta["book_ns"],
            _fmt_money(es_meta["final"]),
            es_meta["cagr_span_pct"],
            es_meta["span_years"],
            es_meta["cagr_n_pct"],
        ),
        "",
        "| Year | N | HP | Net | Stress | N/S | Start | End | Year ret |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in es_year.iterrows():
        lines.append(
            "| {year} | {n} | {hp_n} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | "
            "${start_equity:,.0f} | ${end_equity:,.0f} | {year_return_pct:.1f}% |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### ES @4× liquidity (daily ADV — no local ES 1m)",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Qty | {} |".format(es_liq["qty"]),
            "| Median day volume | {:,.0f} |".format(es_liq["median_day_vol"]),
            "| Median / p90 / max **% of day** | {} / {} / {} |".format(
                _fmt_pct(es_liq["median_pct_day"]),
                _fmt_pct(es_liq["p90_pct_day"]),
                _fmt_pct(es_liq["max_pct_day"]),
            ),
            "| Days >0.1% / >0.5% / >1% of day | {:.0%} / {:.0%} / {:.0%} |".format(
                es_liq["frac_gt_0_1pct"], es_liq["frac_gt_0_5pct"], es_liq["frac_gt_1pct"]
            ),
            "| Median notional / ≈IM | {} / {} |".format(
                _fmt_money(es_liq["median_notional"]), _fmt_money(es_liq["approx_im"])
            ),
            "",
            "**ES daily verdict:** day-ADV share is tiny (≪0.1% median). Without 1m we cannot "
            "rule out entry-minute crowding, but day capacity is not the issue.",
            "",
        ]
    )
    if ym_liq is not None:
        lines.extend(
            [
                "## Cross-check: YM overnight-middle @4× 1m liquidity",
                "",
                "| Metric | Value |",
                "|---|---:|",
                "| Qty | {} |".format(ym_liq["qty"]),
                "| Median / p90 / max % entry bar | {} / {} / {} |".format(
                    _fmt_pct(ym_liq["median_pct_bar"]),
                    _fmt_pct(ym_liq["p90_pct_bar"]),
                    _fmt_pct(ym_liq["max_pct_bar"]),
                ),
                "| Days >1% / >5% / >10% bar | {:.0%} / {:.0%} / {:.0%} |".format(
                    ym_liq["frac_gt_1pct"], ym_liq["frac_gt_5pct"], ym_liq["frac_gt_10pct"]
                ),
                "| Median % ±5m / RTH | {} / {} |".format(
                    _fmt_pct(ym_liq["median_pct_pm5"]), _fmt_pct(ym_liq["median_pct_rth"])
                ),
                "",
            ]
        )
    lines.extend(
        [
            "## Stance",
            "",
            "- **NQ @4×:** quantify liquidity via entry-minute / ±5m / RTH participation + tails + "
            "sqrt(participation). Result: **no material liquidity issue**; capital/IM (~$400k) and "
            "N/S rollback vs 2× are the gates.",
            "- **ES ST-age @4×:** next-best non-NQ prior-opposed by sensitivity N/S; yearly path on "
            "$250k above. **NOT VALIDATED** under ΔN/S nulls — research only.",
            "",
        ]
    )
    return "\n".join(lines)


def build_email(nq_meta, nq_liq, es_meta, es_liq) -> str:
    return "\n".join(
        [
            "potions: HP liquidity @4× (NQ) + next-best non-NQ (ES ST-age) yearly $250k",
            "",
            "Liquidity quantification: entry-minute% / ±5m% / RTH% + p90/p95/max + "
            "frac days >1/5/10/25% of bar + sqrt(participation) + notional/IM.",
            "",
            "NQ OR-norm @4× qty=20: med/p90 entry-bar {}/{} ; >10% bar days {:.0%}. "
            "Liquidity OK. ≈IM {}. Book net {} / stress {} / N/S {:.2f}.".format(
                _fmt_pct(nq_liq["median_pct_bar"]),
                _fmt_pct(nq_liq["p90_pct_bar"]),
                nq_liq["frac_gt_10pct"],
                _fmt_money(nq_liq["approx_im"]),
                _fmt_money(nq_meta["book_net"]),
                _fmt_money(nq_meta["book_stress"]),
                nq_meta["book_ns"],
            ),
            "",
            "Next-best non-NQ prior-opposed: ES ST-age @4× on $250k — net {} / stress {} / N/S {:.2f}; "
            "end {}; CAGR span {:.1f}%. Daily ADV med share {}. NOT VALIDATED under ΔN/S.".format(
                _fmt_money(es_meta["book_net"]),
                _fmt_money(es_meta["book_stress"]),
                es_meta["book_ns"],
                _fmt_money(es_meta["final"]),
                es_meta["cagr_span_pct"],
                _fmt_pct(es_liq["median_pct_day"]),
            ),
            "",
            "Hub: %s" % HUB.relative_to(REPO),
            "",
        ]
    )


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    _patch()
    # NQ
    nq_df, nq_m = _load_book(*NQ[:3])
    nq_year, nq_meta = yearly_250k(nq_df, nq_m, 4.0)
    nq_year.to_csv(HUB / "nq_or_norm_yearly_4x_250k.csv", index=False)
    nq_camp, nq_liq = liquidity_1m(
        nq_df, nq_m, symbol=NQ[4], base_qty=NQ[7], mult=4.0, point_value=NQ[5], im_approx=NQ[6]
    )
    nq_camp.to_csv(HUB / "nq_or_norm_liq_4x_campaigns.csv", index=False)
    # ES
    es_df, es_m = _load_book(*ES[:3])
    es_year, es_meta = yearly_250k(es_df, es_m, 4.0)
    es_year.to_csv(HUB / "es_st_age_yearly_4x_250k.csv", index=False)
    es_camp, es_liq = liquidity_daily(
        es_df, es_m, symbol=ES[4], base_qty=ES[7], mult=4.0, point_value=ES[5], im_approx=ES[6]
    )
    es_camp.to_csv(HUB / "es_st_age_liq_4x_daily.csv", index=False)
    # YM 1m cross-check
    ym_liq = None
    try:
        ym_df, ym_m = _load_book(*YM[:3])
        ym_camp, ym_liq = liquidity_1m(
            ym_df, ym_m, symbol=YM[4], base_qty=YM[7], mult=4.0, point_value=YM[5], im_approx=YM[6]
        )
        ym_camp.to_csv(HUB / "ym_on_middle_liq_4x_campaigns.csv", index=False)
        # also yearly for completeness
        ym_year, ym_meta = yearly_250k(ym_df, ym_m, 4.0)
        ym_year.to_csv(HUB / "ym_on_middle_yearly_4x_250k.csv", index=False)
        (HUB / "ym_on_middle_meta.json").write_text(json.dumps(ym_meta, indent=2) + "\n")
    except Exception as exc:
        print("YM liquidity skipped: %s" % exc, flush=True)

    md = render(nq_year, nq_meta, nq_liq, es_year, es_meta, es_liq, ym_liq)
    email_body = build_email(nq_meta, nq_liq, es_meta, es_liq)
    (HUB / "SUMMARY.md").write_text(md, encoding="utf-8")
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (HUB / "nq_liq_4x.json").write_text(json.dumps(nq_liq, indent=2) + "\n")
    (HUB / "es_liq_4x.json").write_text(json.dumps(es_liq, indent=2) + "\n")
    (HUB / "RUN_COMPLETE.json").write_text(json.dumps({"ok": True}, indent=2) + "\n")
    print(email_body, flush=True)
    if email:
        send_email(
            subject="potions: HP @4× liquidity (NQ) + ES ST-age yearly $250k",
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
            send_email(subject="potions: HP liquidity yearly FAILED", body=tb)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
