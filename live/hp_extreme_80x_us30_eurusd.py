"""Extreme HP ~80×: US30 CFD liquidity + best non-CFD/non-futures (EURUSD Thu).

US30 Monday OR hour 11 — scale to 80×. US30 CSV volume is zero, so liquidity
uses **YM CME 1m as a DJIA depth proxy** at the same entry timestamps
(raw CFD units / YM bar vol, and $ /pt–equivalent units = CFD_qty / 5).

Best non-CFD **and** non-futures HP: EURUSD ST+PMC Thursday (VALIDATED @1.25×)
— same 80× sensitivity + EURUSD 1m tick participation + yearly $250k.

Sensitivity only — not null-suite validation.

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.hp_extreme_80x_us30_eurusd --email
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

import live.intraday_condition_overlay as overlay
from live.futures_intraday_hp_size_liquidity_yearly import (
    _fmt_money,
    _fmt_pct,
    _rth_mask,
    yearly_250k,
)
from live.futures_intraday_hp_sizeup_lib import DBN_1M
from live.fx_intraday_hp_size_liquidity_yearly import liquidity_1m_csv
from live.intraday_condition_overlay import COND_COL as _FX_COND
from live.intraday_condition_overlay import hp_mask, score_nets
from live.notify_email import send_email
from live.v2b_strategy_cross_market_replay import load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "hp_extreme_80x_us30_eurusd"
FX_PROFILE = REPO / "live" / "state" / "intraday_condition_profile"
NY = "America/New_York"
FX_COND = dict(_FX_COND)

MULTS = (1.0, 1.25, 2.0, 4.0, 10.0, 20.0, 40.0, 80.0)

US30 = (
    "us30_monday_or",
    "Entry hour (NY)",
    "11",
    "US30",
    1.0,
    500.0,
    2,  # base entry qty
)
EUR = (
    "eurusd_st_pmc_3r",
    "Day of week",
    "Thursday",
    "EURUSD",
    100_000.0,
    2_500.0,
    1,
)

# YM $5/pt vs US30 CFD $1/pt → risk-equivalent contracts ≈ CFD_qty / 5
YM_PT = 5.0
US30_PT = 1.0


def _load(book: str, cond: str, bucket: str) -> Tuple[pd.DataFrame, np.ndarray]:
    overlay.COND_COL.clear()
    overlay.COND_COL.update(FX_COND)
    camp = pd.read_csv(FX_PROFILE / "all_campaigns.csv")
    camp["entry_ts"] = pd.to_datetime(camp["entry_ts"], utc=True)
    df = camp[camp["book"] == book].sort_values("entry_ts").reset_index(drop=True)
    if df.empty:
        raise RuntimeError("empty %s" % book)
    if "year" not in df.columns:
        df["year"] = df["entry_ts"].dt.year
    if "session_date" not in df.columns:
        df["session_date"] = df["entry_ts"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    else:
        df["session_date"] = df["session_date"].astype(str)
    m = hp_mask(df, cond, bucket)
    if not m.any():
        raise RuntimeError("empty HP %s %s=%s" % (book, cond, bucket))
    return df, m.to_numpy()


def size_table(df: pd.DataFrame, m: np.ndarray, *, base_qty: int, im: float) -> pd.DataFrame:
    base = df["net_usd"].to_numpy(float)
    base_sc = score_nets(base)
    rows = []
    for mult in MULTS:
        sized = base.copy()
        if float(mult) != 1.0:
            sized[m] = sized[m] * float(mult)
        sc = score_nets(sized)
        cum = np.cumsum(sized)
        peak = np.maximum.accumulate(cum)
        mtm_dd = float((cum - peak).min()) if len(cum) else 0.0
        qty = int(round(base_qty * float(mult)))
        rows.append(
            {
                "mult": float(mult),
                "hp_n": int(m.sum()),
                "hp_pct": round(100.0 * float(m.mean()), 2),
                "hp_qty": qty,
                "net": round(sc["net"], 2),
                "stress": round(sc["stress"], 2),
                "ns": round(sc["ns"], 3),
                "mtm_dd": round(mtm_dd, 2),
                "delta_ns": round(sc["ns"] - base_sc["ns"], 3),
                "stress_x": round(sc["stress"] / base_sc["stress"], 4) if base_sc["stress"] > 1 else float("nan"),
                "approx_im": round(qty * im, 0),
            }
        )
    return pd.DataFrame(rows)


def us30_ym_proxy_liq(
    df: pd.DataFrame,
    m: np.ndarray,
    *,
    mult: float,
    base_qty: int,
    im_approx: float,
) -> Tuple[pd.DataFrame, dict]:
    """Liquidity via YM CME 1m at US30 HP entry times."""
    dbn = DBN_1M.get("YM")
    if dbn is None or not Path(dbn).exists():
        raise FileNotFoundError("YM 1m missing for US30 proxy")
    hp = df.loc[m].copy()
    hp["entry_ts_ny"] = pd.to_datetime(hp["entry_ts"], utc=True).dt.tz_convert(NY)
    hp["sess"] = hp["entry_ts_ny"].dt.strftime("%Y-%m-%d")
    print("loading YM 1m (US30 depth proxy) ...", flush=True)
    by_day = load_1m_by_ny_date_any(Path(dbn).resolve(), "ym")
    qty = int(round(base_qty * float(mult)))
    qty_ym_eq = qty * US30_PT / YM_PT  # $ /pt equivalent YM contracts
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
        px = float(row.get("entry_price") or 0.0)
        win = bars[
            (bars["ts"] >= entry_floor - pd.Timedelta(minutes=5))
            & (bars["ts"] <= entry_floor + pd.Timedelta(minutes=5))
        ]
        rth = bars[_rth_mask(bars["ts"])]
        rth_vol = float(rth["volume"].sum()) if not rth.empty else float(bars["volume"].sum())
        pm5 = float(win["volume"].sum())
        rows.append(
            {
                "session_date": sess,
                "ym_entry_bar_vol": entry_vol,
                "ym_pm5_vol": pm5,
                "ym_rth_vol": rth_vol,
                "entry_price": px,
                "pct_bar_raw_cfd": 100.0 * qty / entry_vol if entry_vol > 0 else float("nan"),
                "pct_bar_ym_eq": 100.0 * qty_ym_eq / entry_vol if entry_vol > 0 else float("nan"),
                "pct_pm5_ym_eq": 100.0 * qty_ym_eq / pm5 if pm5 > 0 else float("nan"),
                "pct_rth_ym_eq": 100.0 * qty_ym_eq / rth_vol if rth_vol > 0 else float("nan"),
                "notional_cfd": qty * px * US30_PT,
            }
        )
    camp = pd.DataFrame(rows)
    if camp.empty:
        raise RuntimeError("US30/YM proxy empty missing=%d" % missing)
    pct = camp["pct_bar_ym_eq"]
    summary = {
        "source": "ym_cme_1m_proxy_for_us30_cfd",
        "mult": mult,
        "qty_cfd": qty,
        "qty_ym_risk_eq": qty_ym_eq,
        "n": int(len(camp)),
        "missing": int(missing),
        "note": (
            "US30 CSV volume is zero. Proxy = YM CME 1m at same NY minute. "
            "ym_eq contracts = CFD_qty × ($1/$5). Raw CFD/YM also reported."
        ),
        "median_ym_entry_bar_vol": float(camp["ym_entry_bar_vol"].median()),
        "p10_ym_entry_bar_vol": float(camp["ym_entry_bar_vol"].quantile(0.10)),
        "median_pct_bar_ym_eq": float(pct.median()),
        "p90_pct_bar_ym_eq": float(pct.quantile(0.90)),
        "p95_pct_bar_ym_eq": float(pct.quantile(0.95)),
        "max_pct_bar_ym_eq": float(pct.max()),
        "median_pct_bar_raw_cfd": float(camp["pct_bar_raw_cfd"].median()),
        "p90_pct_bar_raw_cfd": float(camp["pct_bar_raw_cfd"].quantile(0.90)),
        "frac_gt_1pct": float((pct > 1).mean()),
        "frac_gt_5pct": float((pct > 5).mean()),
        "frac_gt_10pct": float((pct > 10).mean()),
        "frac_gt_25pct": float((pct > 25).mean()),
        "median_pct_pm5_ym_eq": float(camp["pct_pm5_ym_eq"].median()),
        "p90_pct_pm5_ym_eq": float(camp["pct_pm5_ym_eq"].quantile(0.90)),
        "median_pct_rth_ym_eq": float(camp["pct_rth_ym_eq"].median()),
        "median_notional": float(camp["notional_cfd"].median()),
        "approx_im": float(qty * im_approx),
        "median_sqrt_participation": float(np.sqrt((pct.clip(lower=0) / 100.0).median())),
        "p90_sqrt_participation": float(np.sqrt((pct.clip(lower=0) / 100.0).quantile(0.90))),
    }
    return camp, summary


def render(
    us30_sz: pd.DataFrame,
    us30_meta: dict,
    us30_liq: dict,
    us30_year: pd.DataFrame,
    eur_sz: pd.DataFrame,
    eur_meta: dict,
    eur_liq: dict,
    eur_year: pd.DataFrame,
) -> str:
    lines = [
        "# HP extreme ~80×: US30 CFD + EURUSD (best non-CFD / non-futures)",
        "",
        "Clarification: **non-CFD and non-futures** = FX sleeve → **EURUSD ST+PMC Thursday** "
        "(not NQ). US30 remains the CFD crank case.",
        "",
        "All large multipliers are **linear sensitivity only** — authorized HP mult stays **1.25×**.",
        "",
        "## US30 Monday OR hour 11 → **80×**",
        "",
        "| Mult | qty | Net | Stress | N/S | MTM DD | ΔN/S | stress× | ≈IM |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in us30_sz.iterrows():
        lines.append(
            "| {mult:g}× | {hp_qty} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | ${mtm_dd:,.0f} | "
            "{delta_ns:+.2f} | {stress_x:.2f}× | ${approx_im:,.0f} |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### US30 @80× yearly $250k",
            "",
            "Book net **{}** / stress **{}** / N/S **{:.2f}** → end **{}** (CAGR span {:.1f}%).".format(
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
    lines.extend(
        [
            "",
            "### US30 @80× liquidity — YM CME proxy (CSV volume is zero)",
            "",
            "Qty CFD **{}** ≈ **{:.0f}** YM risk-equivalent contracts ($1 vs $5 /pt).".format(
                us30_liq["qty_cfd"], us30_liq["qty_ym_risk_eq"]
            ),
            "",
            "| Metric | Value | Read |",
            "|---|---:|---|",
            "| Med YM entry-bar vol | {:,.0f} | |".format(us30_liq["median_ym_entry_bar_vol"]),
            "| Med / p90 / max **% YM bar (risk-eq)** | {} / {} / {} | |".format(
                _fmt_pct(us30_liq["median_pct_bar_ym_eq"]),
                _fmt_pct(us30_liq["p90_pct_bar_ym_eq"]),
                _fmt_pct(us30_liq["max_pct_bar_ym_eq"]),
            ),
            "| Med / p90 **% YM bar (raw CFD units)** | {} / {} | conservative upper |".format(
                _fmt_pct(us30_liq["median_pct_bar_raw_cfd"]),
                _fmt_pct(us30_liq["p90_pct_bar_raw_cfd"]),
            ),
            "| Days >1% / >5% / >10% / >25% YM bar (risk-eq) | {:.0%} / {:.0%} / {:.0%} / {:.0%} | |".format(
                us30_liq["frac_gt_1pct"],
                us30_liq["frac_gt_5pct"],
                us30_liq["frac_gt_10pct"],
                us30_liq["frac_gt_25pct"],
            ),
            "| Med / p90 % ±5m (risk-eq) | {} / {} | |".format(
                _fmt_pct(us30_liq["median_pct_pm5_ym_eq"]),
                _fmt_pct(us30_liq["p90_pct_pm5_ym_eq"]),
            ),
            "| Med notional / ≈IM | {} / {} | capital |".format(
                _fmt_money(us30_liq["median_notional"]),
                _fmt_money(us30_liq["approx_im"]),
            ),
            "",
            "## Best non-CFD / non-futures: EURUSD ST+PMC Thursday → **80×**",
            "",
            "| Mult | qty | Net | Stress | N/S | MTM DD | ΔN/S | stress× | ≈IM |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in eur_sz.iterrows():
        lines.append(
            "| {mult:g}× | {hp_qty} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | ${mtm_dd:,.0f} | "
            "{delta_ns:+.2f} | {stress_x:.2f}× | ${approx_im:,.0f} |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### EURUSD @80× yearly $250k",
            "",
            "Book net **{}** / stress **{}** / N/S **{:.2f}** → end **{}** (CAGR span {:.1f}%).".format(
                _fmt_money(eur_meta["book_net"]),
                _fmt_money(eur_meta["book_stress"]),
                eur_meta["book_ns"],
                _fmt_money(eur_meta["final"]),
                eur_meta["cagr_span_pct"],
            ),
            "",
            "| Year | N | HP | Net | Stress | N/S | End | Year ret |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in eur_year.iterrows():
        lines.append(
            "| {year} | {n} | {hp_n} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | "
            "${end_equity:,.0f} | {year_return_pct:.1f}% |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### EURUSD @80× liquidity (1m tick volume — relative)",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Qty | {} lots |".format(eur_liq["qty"]),
            "| Med / p90 / max % entry bar | {} / {} / {} |".format(
                _fmt_pct(eur_liq["median_pct_bar"]),
                _fmt_pct(eur_liq["p90_pct_bar"]),
                _fmt_pct(eur_liq["max_pct_bar"]),
            ),
            "| Days >1% / >5% / >10% bar | {:.0%} / {:.0%} / {:.0%} |".format(
                eur_liq["frac_gt_1pct"], eur_liq["frac_gt_5pct"], eur_liq["frac_gt_10pct"]
            ),
            "| Med notional / ≈IM | {} / {} |".format(
                _fmt_money(eur_liq["median_notional"]), _fmt_money(eur_liq["approx_im"])
            ),
            "",
            "## Stance",
            "",
            "- **US30 @80×:** use YM proxy for depth; capital/stress bind before promotion. "
            "Authorized remains **1.25×**.",
            "- **EURUSD @80×:** best non-CFD/non-futures; EURUSD spot depth is not the issue — "
            "null standing + margin/path risk are.",
            "",
            "Hub: `%s`" % HUB.relative_to(REPO),
            "",
        ]
    )
    return "\n".join(lines)


def build_email(us30_meta, us30_liq, us30_sz, eur_meta, eur_liq, eur_sz) -> str:
    u = us30_sz[us30_sz.mult == 80.0].iloc[0]
    e = eur_sz[eur_sz.mult == 80.0].iloc[0]
    return "\n".join(
        [
            "potions: HP ~80× US30 CFD (YM liquidity proxy) + EURUSD (non-CFD/non-futures)",
            "",
            "US30 h11 @80× qty={}: net {} / stress {} / N/S {:.2f}; $250k→{}. "
            "YM-proxy med/p90 risk-eq entry-bar {}/{}; >10% days {:.0%}; "
            "raw-CFD med {}; notional {}; ≈IM {}.".format(
                int(u.hp_qty),
                _fmt_money(us30_meta["book_net"]),
                _fmt_money(us30_meta["book_stress"]),
                us30_meta["book_ns"],
                _fmt_money(us30_meta["final"]),
                _fmt_pct(us30_liq["median_pct_bar_ym_eq"]),
                _fmt_pct(us30_liq["p90_pct_bar_ym_eq"]),
                us30_liq["frac_gt_10pct"],
                _fmt_pct(us30_liq["median_pct_bar_raw_cfd"]),
                _fmt_money(us30_liq["median_notional"]),
                _fmt_money(us30_liq["approx_im"]),
            ),
            "",
            "EURUSD Thu @80× qty={}: net {} / stress {} / N/S {:.2f}; $250k→{}; "
            "tick med/p90 entry-bar {}/{}; ≈IM {}. Tape not binding.".format(
                int(e.hp_qty),
                _fmt_money(eur_meta["book_net"]),
                _fmt_money(eur_meta["book_stress"]),
                eur_meta["book_ns"],
                _fmt_money(eur_meta["final"]),
                _fmt_pct(eur_liq["median_pct_bar"]),
                _fmt_pct(eur_liq["p90_pct_bar"]),
                _fmt_money(eur_liq["approx_im"]),
            ),
            "",
            "Stance: sensitivity only — do not promote 80×. Hub: %s" % HUB.relative_to(REPO),
            "",
        ]
    )


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)

    us30_df, us30_m = _load(*US30[:3])
    us30_sz = size_table(us30_df, us30_m, base_qty=US30[6], im=US30[5])
    us30_sz.to_csv(HUB / "us30_h11_size_sensitivity.csv", index=False)
    us30_year, us30_meta = yearly_250k(us30_df, us30_m, 80.0)
    us30_year.to_csv(HUB / "us30_h11_yearly_80x_250k.csv", index=False)
    (HUB / "us30_meta_80x.json").write_text(json.dumps(us30_meta, indent=2) + "\n")
    us30_camp, us30_liq = us30_ym_proxy_liq(
        us30_df, us30_m, mult=80.0, base_qty=US30[6], im_approx=US30[5]
    )
    us30_camp.to_csv(HUB / "us30_h11_liq_80x_ym_proxy.csv", index=False)
    (HUB / "us30_liq_80x.json").write_text(json.dumps(us30_liq, indent=2) + "\n")

    eur_df, eur_m = _load(*EUR[:3])
    eur_sz = size_table(eur_df, eur_m, base_qty=EUR[6], im=EUR[5])
    eur_sz.to_csv(HUB / "eurusd_thu_size_sensitivity.csv", index=False)
    eur_year, eur_meta = yearly_250k(eur_df, eur_m, 80.0)
    eur_year.to_csv(HUB / "eurusd_thu_yearly_80x_250k.csv", index=False)
    (HUB / "eurusd_meta_80x.json").write_text(json.dumps(eur_meta, indent=2) + "\n")
    eur_camp, eur_liq = liquidity_1m_csv(
        eur_df,
        eur_m,
        symbol=EUR[3],
        base_qty=EUR[6],
        mult=80.0,
        point_value=EUR[4],
        im_approx=EUR[5],
    )
    eur_camp.to_csv(HUB / "eurusd_thu_liq_80x_campaigns.csv", index=False)
    (HUB / "eurusd_liq_80x.json").write_text(json.dumps(eur_liq, indent=2) + "\n")

    md = render(us30_sz, us30_meta, us30_liq, us30_year, eur_sz, eur_meta, eur_liq, eur_year)
    email_body = build_email(us30_meta, us30_liq, us30_sz, eur_meta, eur_liq, eur_sz)
    (HUB / "SUMMARY.md").write_text(md, encoding="utf-8")
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(json.dumps({"ok": True}, indent=2) + "\n")
    print(email_body, flush=True)
    if email:
        send_email(
            subject="potions: HP ~80× US30 (YM liq proxy) + EURUSD non-CFD/non-futures",
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
            send_email(subject="potions: HP extreme 80× FAILED", body=tb)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
