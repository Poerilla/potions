"""Extreme HP size-up ~20×: US30 CFD + best non-CFD (NQ OR-norm).

Baselines (reference, not re-validated here):
  1. NQ prior-opposed OR-norm
  2. ES prior-opposed ST-age>180m
  3. EURUSD ST+PMC Thursday

Then crank linear HP scaling to ~20× for:
  - US30 Monday OR hour 11 (validated FX/CFD HP @1.25×)
  - NQ OR-norm (best non-CFD / futures HP)

Sensitivity + liquidity + yearly $250k only — **not** null-suite validation.

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.hp_extreme_20x_us30_nq --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Optional, Sequence, Tuple

import numpy as np
import pandas as pd

import live.intraday_condition_overlay as overlay
from live.futures_intraday_hp_size_liquidity_yearly import (
    _fmt_money,
    _fmt_pct,
    liquidity_1m,
    yearly_250k,
)
from live.futures_intraday_hp_sizeup_lib import COND_COL as _FUT_COND
from live.futures_intraday_hp_sizeup_lib import PROFILE_HUB as FUT_PROFILE
from live.fx_intraday_hp_size_liquidity_yearly import liquidity_1m_csv
from live.intraday_condition_overlay import COND_COL as _FX_COND
from live.intraday_condition_overlay import hp_mask, score_nets
from live.notify_email import send_email

FUT_COND = dict(_FUT_COND)
FX_COND = dict(_FX_COND)

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "hp_extreme_20x_us30_nq"
FX_PROFILE = REPO / "live" / "state" / "intraday_condition_profile"
NY = "America/New_York"

MULTS = (1.0, 1.25, 2.0, 4.0, 10.0, 15.0, 20.0)

# Three baselines (label, book, cond, bucket, profile, symbol notes)
BASELINES = (
    (
        "NQ OR-norm",
        "nq_prior_opposed_rl",
        "Opening 15m range vs ATR",
        "or_norm",
        "futures",
        "non-CFD futures — best HP",
    ),
    (
        "ES ST-age>180m",
        "es_prior_opposed_legacy",
        "ST-event age",
        "st_age_gt180m",
        "futures",
        "non-CFD futures — next-best non-NQ",
    ),
    (
        "EURUSD ST+PMC Thu",
        "eurusd_st_pmc_3r",
        "Day of week",
        "Thursday",
        "fx",
        "FX — next-best non-futures (VALIDATED @1.25×)",
    ),
)

US30 = (
    "us30_monday_or",
    "Entry hour (NY)",
    "11",
    "US30 Monday OR hour 11 (CFD)",
    "US30",
    1.0,  # $ / point
    500.0,  # rough IM per unit (order-of-magnitude)
    2,  # typical entry qty on M3_S3_R2 tape
)
NQ = (
    "nq_prior_opposed_rl",
    "Opening 15m range vs ATR",
    "or_norm",
    "NQ prior-opposed OR-norm (best non-CFD)",
    "NQ",
    20.0,
    20000.0,
    5,
)


def _load(profile: Path, book: str, cond: str, bucket: str, *, fut: bool) -> Tuple[pd.DataFrame, np.ndarray]:
    if fut:
        overlay.COND_COL.clear()
        overlay.COND_COL.update(FUT_COND)
    else:
        overlay.COND_COL.clear()
        overlay.COND_COL.update(FX_COND)
    camp = pd.read_csv(profile / "all_campaigns.csv")
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
                "delta_net": round(sc["net"] - base_sc["net"], 2),
                "delta_ns": round(sc["ns"] - base_sc["ns"], 3),
                "stress_x": round(sc["stress"] / base_sc["stress"], 4) if base_sc["stress"] > 1 else float("nan"),
                "approx_im": round(qty * im, 0),
            }
        )
    return pd.DataFrame(rows)


def baseline_row(label: str, note: str, df: pd.DataFrame, m: np.ndarray, mult: float = 4.0) -> dict:
    y, meta = yearly_250k(df, m, mult)
    return {
        "label": label,
        "note": note,
        "mult_ref": mult,
        "book_net": meta["book_net"],
        "book_stress": meta["book_stress"],
        "book_ns": meta["book_ns"],
        "final_250k": meta["final"],
        "cagr_span_pct": meta["cagr_span_pct"],
        "span_years": meta["span_years"],
        "hp_n": int(m.sum()),
        "n": int(len(df)),
    }


def render(
    baselines: pd.DataFrame,
    us30_sz: pd.DataFrame,
    us30_meta: dict,
    us30_liq: dict,
    us30_year: pd.DataFrame,
    nq_sz: pd.DataFrame,
    nq_meta: dict,
    nq_liq: dict,
    nq_year: pd.DataFrame,
) -> str:
    lines = [
        "# HP extreme ~20×: US30 CFD + NQ (best non-CFD)",
        "",
        "## Baselines (reference @4× sensitivity)",
        "",
        "Locked as the three reference sleeves from prior HP work:",
        "",
        "| Sleeve | Note | HP n | @4× net | stress | N/S | $250k→ | CAGR |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for _, r in baselines.iterrows():
        lines.append(
            "| {label} | {note} | {hp_n} | ${book_net:,.0f} | ${book_stress:,.0f} | {book_ns:.2f} | "
            "${final_250k:,.0f} | {cagr_span_pct:.1f}% |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "All 10×/15×/20× columns below are **linear sizing sensitivity only** — not validated.",
            "",
            "## US30 Monday OR hour 11 (CFD) — scale to **20×**",
            "",
            "| Mult | qty | Net | Stress | N/S | MTM DD | ΔN/S | stress× | ≈IM |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in us30_sz.iterrows():
        lines.append(
            "| {mult:g}× | {hp_qty} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | ${mtm_dd:,.0f} | "
            "{delta_ns:+.2f} | {stress_x:.2f}× | ${approx_im:,.0f} |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### US30 @20× yearly $250k",
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
            "### US30 @20× liquidity (1m tick vol — relative)",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Qty | {} |".format(us30_liq["qty"]),
            "| Med / p90 / max % entry bar | {} / {} / {} |".format(
                _fmt_pct(us30_liq["median_pct_bar"]),
                _fmt_pct(us30_liq["p90_pct_bar"]),
                _fmt_pct(us30_liq["max_pct_bar"]),
            ),
            "| Days >1% / >5% / >10% bar | {:.0%} / {:.0%} / {:.0%} |".format(
                us30_liq["frac_gt_1pct"], us30_liq["frac_gt_5pct"], us30_liq["frac_gt_10pct"]
            ),
            "| Med % ±5m / RTH | {} / {} |".format(
                _fmt_pct(us30_liq["median_pct_pm5"]), _fmt_pct(us30_liq["median_pct_rth"])
            ),
            "| Med notional / ≈IM | {} / {} |".format(
                _fmt_money(us30_liq["median_notional"]), _fmt_money(us30_liq["approx_im"])
            ),
            "",
            "## Best non-CFD: NQ OR-norm — scale to **20×**",
            "",
            "| Mult | qty | Net | Stress | N/S | MTM DD | ΔN/S | stress× | ≈IM |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in nq_sz.iterrows():
        lines.append(
            "| {mult:g}× | {hp_qty} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | ${mtm_dd:,.0f} | "
            "{delta_ns:+.2f} | {stress_x:.2f}× | ${approx_im:,.0f} |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### NQ @20× yearly $250k",
            "",
            "Book net **{}** / stress **{}** / N/S **{:.2f}** → end **{}** (CAGR span {:.1f}%).".format(
                _fmt_money(nq_meta["book_net"]),
                _fmt_money(nq_meta["book_stress"]),
                nq_meta["book_ns"],
                _fmt_money(nq_meta["final"]),
                nq_meta["cagr_span_pct"],
            ),
            "",
            "| Year | N | HP | Net | Stress | N/S | End | Year ret |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in nq_year.iterrows():
        lines.append(
            "| {year} | {n} | {hp_n} | ${net:,.0f} | ${stress:,.0f} | {ns:.2f} | "
            "${end_equity:,.0f} | {year_return_pct:.1f}% |".format(**r.to_dict())
        )
    lines.extend(
        [
            "",
            "### NQ @20× liquidity (1m CME)",
            "",
            "| Metric | Value |",
            "|---|---:|",
            "| Qty | {} |".format(nq_liq["qty"]),
            "| Med / p90 / max % entry bar | {} / {} / {} |".format(
                _fmt_pct(nq_liq["median_pct_bar"]),
                _fmt_pct(nq_liq["p90_pct_bar"]),
                _fmt_pct(nq_liq["max_pct_bar"]),
            ),
            "| Days >1% / >5% / >10% / >25% bar | {:.0%} / {:.0%} / {:.0%} / {:.0%} |".format(
                nq_liq["frac_gt_1pct"],
                nq_liq["frac_gt_5pct"],
                nq_liq["frac_gt_10pct"],
                nq_liq["frac_gt_25pct"],
            ),
            "| Med / p90 % ±5m | {} / {} |".format(
                _fmt_pct(nq_liq["median_pct_pm5"]), _fmt_pct(nq_liq["p90_pct_pm5"])
            ),
            "| Med notional / ≈IM | {} / {} |".format(
                _fmt_money(nq_liq["median_notional"]), _fmt_money(nq_liq["approx_im"])
            ),
            "",
            "## Stance",
            "",
            "- Baselines remain NQ / ES / EURUSD Thu (research refs @4×).",
            "- **US30 @20×:** CFD sensitivity — check N/S vs stress× and tick footprint; "
            "authorized HP mult is still **1.25×**.",
            "- **NQ @20×:** best non-CFD — liquidity + margin (~qty×IM) likely bind before "
            "any promotion; null standing only through provisional 1.25×/2×.",
            "",
            "Hub: `%s`" % HUB.relative_to(REPO),
            "",
        ]
    )
    return "\n".join(lines)


def build_email(baselines, us30_sz, us30_meta, us30_liq, nq_sz, nq_meta, nq_liq) -> str:
    u20 = us30_sz[us30_sz.mult == 20.0].iloc[0]
    n20 = nq_sz[nq_sz.mult == 20.0].iloc[0]
    lines = [
        "potions: HP extreme ~20× — US30 CFD + NQ (best non-CFD)",
        "",
        "Baselines @4×: "
        + "; ".join(
            "%s N/S %.2f ($250k→%s)"
            % (r.label, r.book_ns, _fmt_money(r.final_250k))
            for _, r in baselines.iterrows()
        ),
        "",
        "US30 Monday OR h11 @20× (qty={}): net {} / stress {} / N/S {:.2f}; "
        "$250k→{}; med/p90 entry-bar {}/{}; ≈IM {}.".format(
            int(u20.hp_qty),
            _fmt_money(us30_meta["book_net"]),
            _fmt_money(us30_meta["book_stress"]),
            us30_meta["book_ns"],
            _fmt_money(us30_meta["final"]),
            _fmt_pct(us30_liq["median_pct_bar"]),
            _fmt_pct(us30_liq["p90_pct_bar"]),
            _fmt_money(us30_liq["approx_im"]),
        ),
        "",
        "NQ OR-norm @20× (qty={}): net {} / stress {} / N/S {:.2f}; "
        "$250k→{}; med/p90 entry-bar {}/{}; >10% bar days {:.0%}; ≈IM {}.".format(
            int(n20.hp_qty),
            _fmt_money(nq_meta["book_net"]),
            _fmt_money(nq_meta["book_stress"]),
            nq_meta["book_ns"],
            _fmt_money(nq_meta["final"]),
            _fmt_pct(nq_liq["median_pct_bar"]),
            _fmt_pct(nq_liq["p90_pct_bar"]),
            nq_liq["frac_gt_10pct"],
            _fmt_money(nq_liq["approx_im"]),
        ),
        "",
        "Stance: sensitivity only — do not promote 20×. Hub: %s" % HUB.relative_to(REPO),
        "",
    ]
    return "\n".join(lines)


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)

    # Baselines @4×
    brows = []
    for label, book, cond, bucket, kind, note in BASELINES:
        if kind == "futures":
            df, m = _load(FUT_PROFILE, book, cond, bucket, fut=True)
        else:
            df, m = _load(FX_PROFILE, book, cond, bucket, fut=False)
        brows.append(baseline_row(label, note, df, m, 4.0))
    baselines = pd.DataFrame(brows)
    baselines.to_csv(HUB / "baselines_4x.csv", index=False)

    # US30 CFD extreme
    us30_df, us30_m = _load(FX_PROFILE, *US30[:3], fut=False)
    us30_sz = size_table(us30_df, us30_m, base_qty=US30[7], im=US30[6])
    us30_sz.to_csv(HUB / "us30_h11_size_sensitivity.csv", index=False)
    us30_year, us30_meta = yearly_250k(us30_df, us30_m, 20.0)
    us30_year.to_csv(HUB / "us30_h11_yearly_20x_250k.csv", index=False)
    (HUB / "us30_meta_20x.json").write_text(json.dumps(us30_meta, indent=2) + "\n")
    us30_camp, us30_liq = liquidity_1m_csv(
        us30_df,
        us30_m,
        symbol=US30[4],
        base_qty=US30[7],
        mult=20.0,
        point_value=US30[5],
        im_approx=US30[6],
    )
    # US30 notional = qty * price * $1/pt
    us30_camp["notional"] = us30_camp["entry_price"] * float(us30_liq["qty"]) * float(US30[5])
    us30_liq["median_notional"] = float(us30_camp["notional"].median())
    us30_camp.to_csv(HUB / "us30_h11_liq_20x_campaigns.csv", index=False)
    (HUB / "us30_liq_20x.json").write_text(json.dumps(us30_liq, indent=2) + "\n")

    # NQ best non-CFD extreme
    nq_df, nq_m = _load(FUT_PROFILE, *NQ[:3], fut=True)
    nq_sz = size_table(nq_df, nq_m, base_qty=NQ[7], im=NQ[6])
    nq_sz.to_csv(HUB / "nq_or_norm_size_sensitivity.csv", index=False)
    nq_year, nq_meta = yearly_250k(nq_df, nq_m, 20.0)
    nq_year.to_csv(HUB / "nq_or_norm_yearly_20x_250k.csv", index=False)
    (HUB / "nq_meta_20x.json").write_text(json.dumps(nq_meta, indent=2) + "\n")
    nq_camp, nq_liq = liquidity_1m(
        nq_df,
        nq_m,
        symbol=NQ[4],
        base_qty=NQ[7],
        mult=20.0,
        point_value=NQ[5],
        im_approx=NQ[6],
    )
    nq_camp.to_csv(HUB / "nq_or_norm_liq_20x_campaigns.csv", index=False)
    (HUB / "nq_liq_20x.json").write_text(json.dumps(nq_liq, indent=2) + "\n")

    md = render(
        baselines, us30_sz, us30_meta, us30_liq, us30_year, nq_sz, nq_meta, nq_liq, nq_year
    )
    email_body = build_email(baselines, us30_sz, us30_meta, us30_liq, nq_sz, nq_meta, nq_liq)
    (HUB / "SUMMARY.md").write_text(md, encoding="utf-8")
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(json.dumps({"ok": True}, indent=2) + "\n")
    print(email_body, flush=True)
    if email:
        send_email(
            subject="potions: HP ~20× US30 CFD + NQ (best non-CFD) extreme size",
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
            send_email(subject="potions: HP extreme 20× FAILED", body=tb)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
