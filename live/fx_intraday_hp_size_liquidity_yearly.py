"""Quantify FX HP size liquidity + yearly $250k path @4×.

Focus: next-best **non-futures** HP sleeve by validated standing —
EURUSD ST+PMC Thursday (SIZE-UP VALIDATED @1.25×; 4× = sensitivity only).

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.fx_intraday_hp_size_liquidity_yearly --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import date as date_cls
from pathlib import Path
from typing import Dict, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from live.intraday_condition_overlay import hp_mask
from live.futures_intraday_hp_size_liquidity_yearly import (
    _fmt_money,
    _fmt_pct,
    _rth_mask,
    yearly_250k,
)
from live.notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
PROFILE_HUB = REPO / "live" / "state" / "intraday_condition_profile"
HUB = REPO / "live" / "state" / "fx_intraday_hp_size_liquidity_yearly"
NY = "America/New_York"

# Primary non-futures HP (validated @1.25×; sensitivity @4×)
EUR = (
    "eurusd_st_pmc_3r",
    "Day of week",
    "Thursday",
    "EURUSD ST+PMC Thursday (next-best non-futures HP)",
    "EURUSD",
    100_000.0,  # $ notional per 1.0 lot (POINT_VALUES)
    2_500.0,  # rough retail IM ~2.5% of $100k
    1,  # base qty in research fills
)
# Runner-up validated FX sleeve (report yearly only; thinner HP%)
US30 = (
    "us30_monday_or",
    "Entry hour (NY)",
    "11",
    "US30 Monday OR hour 11 (2nd validated FX HP)",
    "US30",
    1.0,  # index CFD $1/pt in research sizing — notional via entry_price*qty
    5_000.0,
    1,
)

CSV_1M = {
    "EURUSD": REPO / "fx" / "eurusd_1m.csv",
    "US30": REPO / "fx" / "us30_1m.csv",
}
DAILY_CSV = {
    "EURUSD": REPO / "fx" / "eurusd_daily.csv",
    "US30": REPO / "fx" / "us30_daily.csv",
}


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


def _load_fx_1m_by_day(path: Path, symbol: str) -> Dict[date_cls, pd.DataFrame]:
    """Load FX/index 1m CSV partitioned by NY calendar date (no futures root mask)."""
    print("Loading FX 1m CSV %s (%s) ..." % (path, symbol), flush=True)
    df = pd.read_csv(path, parse_dates=["ts_event"])
    if "symbol" in df.columns:
        df = df[df["symbol"].astype(str).str.upper() == symbol.upper()].copy()
    if df.empty:
        return {}
    if df["ts_event"].dt.tz is None:
        df["ts_event"] = df["ts_event"].dt.tz_localize("UTC")
    df["ts_event"] = df["ts_event"].dt.tz_convert(NY)
    df = df.set_index("ts_event").sort_index()
    gby = {d: g.copy() for d, g in df.groupby(df.index.date)}
    print("  %s NY dates with bars" % f"{len(gby):,}", flush=True)
    return gby


def liquidity_1m_csv(
    df: pd.DataFrame,
    m: np.ndarray,
    *,
    symbol: str,
    base_qty: int,
    mult: float,
    point_value: float,
    im_approx: float,
) -> Tuple[pd.DataFrame, dict]:
    path = CSV_1M.get(symbol)
    if path is None or not path.exists():
        raise FileNotFoundError("no 1m CSV for %s" % symbol)
    hp = df.loc[m].copy()
    hp["entry_ts_ny"] = pd.to_datetime(hp["entry_ts"], utc=True).dt.tz_convert(NY)
    hp["sess"] = hp["entry_ts_ny"].dt.strftime("%Y-%m-%d")
    by_day = _load_fx_1m_by_day(path.resolve(), symbol)
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
                "notional": float(qty) * float(point_value),
            }
        )
    camp = pd.DataFrame(rows)
    if camp.empty:
        raise RuntimeError("%s liquidity empty missing=%d" % (symbol, missing))
    pct = camp["pct_bar"]
    summary = {
        "source": "1m_tick_volume_csv",
        "symbol": symbol,
        "mult": mult,
        "qty": qty,
        "n": int(len(camp)),
        "missing": int(missing),
        "note": "FX CSV volume is tick volume (not lots) — participation is relative only.",
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
        notional = qty * px * point_value if symbol != "US30" else qty * px * point_value
        rows.append(
            {
                "session_date": sess,
                "day_vol": vol,
                "pct_day": 100.0 * qty / vol,
                "notional": notional,
            }
        )
    camp = pd.DataFrame(rows)
    if camp.empty:
        raise RuntimeError("%s daily liquidity empty" % symbol)
    pct = camp["pct_day"]
    summary = {
        "source": "daily_tick_adv",
        "symbol": symbol,
        "mult": mult,
        "qty": qty,
        "n": int(len(camp)),
        "missing": int(missing),
        "note": "Daily volume is tick ADV in these CSVs — share is relative only.",
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


def render(
    eur_year: pd.DataFrame,
    eur_meta: dict,
    eur_liq: dict,
    eur_daily: dict,
    us30_year: Optional[pd.DataFrame],
    us30_meta: Optional[dict],
) -> str:
    lines = [
        "# FX HP size liquidity + yearly $250k @4× (non-futures)",
        "",
        "Chosen as next-best **non-futures** HP by null-suite standing: "
        "**EURUSD ST+PMC Thursday** — SIZE-UP VALIDATED @ **1.25×** only. "
        "**4× is sizing sensitivity**, not validated (2× already RISK-BUDGET).",
        "",
        "## How we quantify liquidity (same stack as futures)",
        "",
        "1. Entry-minute share · 2. ±5m · 3. day ADV · 4. p90/p95/max + frac >1/5/10/25% · "
        "5. √participation · 6. notional / ≈IM.",
        "",
        "**Caveat:** FX/index CSV `volume` is usually **tick volume**, not exchange lots — "
        "participation % is a relative crowding proxy. Absolute liquidity gate for EURUSD "
        "spot/CFD at a few lots is market-spread / margin, not thinness.",
        "",
        "## EURUSD ST+PMC Thursday @ **4×** (qty=4 lots)",
        "",
        "Whole-book @4×: net **{}**, stress **{}**, N/S **{:.2f}**. "
        "$250k → **{}**. CAGR span **{:.1f}%** ({:.2f}y) / calendar-n **{:.1f}%**.".format(
            _fmt_money(eur_meta["book_net"]),
            _fmt_money(eur_meta["book_stress"]),
            eur_meta["book_ns"],
            _fmt_money(eur_meta["final"]),
            eur_meta["cagr_span_pct"],
            eur_meta["span_years"],
            eur_meta["cagr_n_pct"],
        ),
        "",
        "| Year | N | HP | Net | Stress | N/S | Start | End | Year ret |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in eur_year.iterrows():
        lines.append(
            "| {year} | {n} | {hp_n} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | "
            "${start_equity:,.0f} | ${end_equity:,.0f} | {year_return_pct:.1f}% |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### Liquidity scorecard (1m tick volume)",
            "",
            "| Metric | Value | Read |",
            "|---|---:|---|",
            "| Median entry-bar tick vol | {:,.0f} | |".format(eur_liq["median_entry_bar_vol"]),
            "| Median / p90 / p95 / max **% of entry bar** | {} / {} / {} / {} | relative |".format(
                _fmt_pct(eur_liq["median_pct_bar"]),
                _fmt_pct(eur_liq["p90_pct_bar"]),
                _fmt_pct(eur_liq["p95_pct_bar"]),
                _fmt_pct(eur_liq["max_pct_bar"]),
            ),
            "| Days >1% / >5% / >10% / >25% of entry bar | {:.0%} / {:.0%} / {:.0%} / {:.0%} | |".format(
                eur_liq["frac_gt_1pct"],
                eur_liq["frac_gt_5pct"],
                eur_liq["frac_gt_10pct"],
                eur_liq["frac_gt_25pct"],
            ),
            "| Median / p90 % of ±5m | {} / {} | |".format(
                _fmt_pct(eur_liq["median_pct_pm5"]), _fmt_pct(eur_liq["p90_pct_pm5"])
            ),
            "| Median % of RTH day (tick) | {} | |".format(_fmt_pct(eur_liq["median_pct_rth"])),
            "| Median notional / ≈IM | {} / {} | **capital** |".format(
                _fmt_money(eur_liq["median_notional"]), _fmt_money(eur_liq["approx_im"])
            ),
            "| Median / p90 √participation | {:.4f} / {:.4f} | |".format(
                eur_liq["median_sqrt_participation"], eur_liq["p90_sqrt_participation"]
            ),
            "",
            "### Daily ADV (tick)",
            "",
            "| Median / p90 / max % of day | {} / {} / {} |".format(
                _fmt_pct(eur_daily["median_pct_day"]),
                _fmt_pct(eur_daily["p90_pct_day"]),
                _fmt_pct(eur_daily["max_pct_day"]),
            ),
            "",
            "**Verdict @4× EURUSD:** tape/tick footprint is not the binding constraint "
            "(4 lots vs deep EURUSD). Binding gates: **null standing stops at 1.25×**, "
            "stress path, and margin — not liquidity.",
            "",
        ]
    )
    if us30_meta is not None and us30_year is not None:
        lines.extend(
            [
                "## Cross-check: US30 Monday OR hour 11 @4× (2nd validated FX HP)",
                "",
                "Whole-book @4×: net **{}**, stress **{}**, N/S **{:.2f}**. "
                "$250k → **{}**. CAGR span **{:.1f}%**.".format(
                    _fmt_money(us30_meta["book_net"]),
                    _fmt_money(us30_meta["book_stress"]),
                    us30_meta["book_ns"],
                    _fmt_money(us30_meta["final"]),
                    us30_meta["cagr_span_pct"],
                ),
                "",
                "| Year | N | HP | Net | Stress | N/S | End | Year ret |",
                "|---:|---:|---:|---:|---:|---:|---:|---:|",
            ]
        )
        for _, r in us30_year.iterrows():
            lines.append(
                "| {year} | {n} | {hp_n} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | "
                "${end_equity:,.0f} | {year_return_pct:.1f}% |".format(**r.to_dict())
            )
        lines.append("")
    lines.extend(
        [
            "## Stance",
            "",
            "- **EURUSD ST+PMC Thu @4×:** next-best non-futures by validation; liquidity OK; "
            "**do not promote 4×** — authorized HP mult remains **1.25×**.",
            "- US30 h11 is the second validated FX sleeve (weaker ΔN/S); same 4× caveat.",
            "",
            "Hub: `%s`" % HUB.relative_to(REPO),
            "",
        ]
    )
    return "\n".join(lines)


def build_email(eur_meta, eur_liq, eur_daily, us30_meta) -> str:
    lines = [
        "potions: FX HP @4× liquidity + yearly $250k (EURUSD ST+PMC Thursday)",
        "",
        "Next-best non-futures HP: EURUSD ST+PMC Thursday (VALIDATED @1.25× only; 4× = sensitivity).",
        "",
        "EURUSD @4× qty=4: book net {} / stress {} / N/S {:.2f}; $250k → {}; CAGR span {:.1f}%.".format(
            _fmt_money(eur_meta["book_net"]),
            _fmt_money(eur_meta["book_stress"]),
            eur_meta["book_ns"],
            _fmt_money(eur_meta["final"]),
            eur_meta["cagr_span_pct"],
        ),
        "Liquidity (1m tick): med/p90 entry-bar {}/{} ; >10% bar days {:.0%}; ≈IM {}. "
        "Daily tick ADV med share {}. Tape not binding.".format(
            _fmt_pct(eur_liq["median_pct_bar"]),
            _fmt_pct(eur_liq["p90_pct_bar"]),
            eur_liq["frac_gt_10pct"],
            _fmt_money(eur_liq["approx_im"]),
            _fmt_pct(eur_daily["median_pct_day"]),
        ),
        "",
    ]
    if us30_meta is not None:
        lines.append(
            "US30 h11 @4× cross-check: net {} / stress {} / N/S {:.2f}; end {}.".format(
                _fmt_money(us30_meta["book_net"]),
                _fmt_money(us30_meta["book_stress"]),
                us30_meta["book_ns"],
                _fmt_money(us30_meta["final"]),
            )
        )
        lines.append("")
    lines.extend(
        [
            "Stance: liquidity OK; do not promote 4× — keep authorized 1.25×.",
            "Hub: %s" % HUB.relative_to(REPO),
            "",
        ]
    )
    return "\n".join(lines)


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)

    eur_df, eur_m = _load_book(*EUR[:3])
    eur_year, eur_meta = yearly_250k(eur_df, eur_m, 4.0)
    eur_year.to_csv(HUB / "eurusd_st_pmc_thu_yearly_4x_250k.csv", index=False)
    (HUB / "eurusd_meta.json").write_text(json.dumps(eur_meta, indent=2) + "\n")

    eur_camp, eur_liq = liquidity_1m_csv(
        eur_df,
        eur_m,
        symbol=EUR[4],
        base_qty=EUR[7],
        mult=4.0,
        point_value=EUR[5],
        im_approx=EUR[6],
    )
    eur_camp.to_csv(HUB / "eurusd_st_pmc_thu_liq_4x_campaigns.csv", index=False)
    (HUB / "eurusd_liq_4x.json").write_text(json.dumps(eur_liq, indent=2) + "\n")

    eur_d_camp, eur_daily = liquidity_daily(
        eur_df,
        eur_m,
        symbol=EUR[4],
        base_qty=EUR[7],
        mult=4.0,
        point_value=EUR[5],
        im_approx=EUR[6],
    )
    eur_d_camp["notional"] = float(EUR[7] * 4.0) * float(EUR[5])
    eur_daily["median_notional"] = float(eur_d_camp["notional"].median())
    eur_d_camp.to_csv(HUB / "eurusd_st_pmc_thu_liq_4x_daily.csv", index=False)
    (HUB / "eurusd_daily_liq_4x.json").write_text(json.dumps(eur_daily, indent=2) + "\n")

    us30_year = us30_meta = None
    try:
        us30_df, us30_m = _load_book(*US30[:3])
        us30_year, us30_meta = yearly_250k(us30_df, us30_m, 4.0)
        us30_year.to_csv(HUB / "us30_monday_h11_yearly_4x_250k.csv", index=False)
        (HUB / "us30_meta.json").write_text(json.dumps(us30_meta, indent=2) + "\n")
    except Exception as exc:
        print("US30 yearly skipped: %s" % exc, flush=True)

    md = render(eur_year, eur_meta, eur_liq, eur_daily, us30_year, us30_meta)
    email_body = build_email(eur_meta, eur_liq, eur_daily, us30_meta)
    (HUB / "SUMMARY.md").write_text(md, encoding="utf-8")
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(json.dumps({"ok": True, "book": EUR[0]}, indent=2) + "\n")
    print(email_body, flush=True)
    if email:
        send_email(
            subject="potions: FX HP @4× liquidity (EURUSD ST+PMC Thu) + yearly $250k",
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
            send_email(subject="potions: FX HP liquidity yearly FAILED", body=tb)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
