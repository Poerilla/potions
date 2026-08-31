"""Regenerate HP research capital lock v1 (NQ/ES @4× + EURUSD Thu @40×).

Usage::

    export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
    python -m live.hp_size_lock_v1 --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence

import pandas as pd

import live.intraday_condition_overlay as overlay
from live.futures_intraday_hp_size_liquidity_yearly import (
    _fmt_money,
    liquidity_1m,
    liquidity_daily,
    yearly_250k,
)
from live.futures_intraday_hp_sizeup_lib import COND_COL as _FUT
from live.futures_intraday_hp_sizeup_lib import PROFILE_HUB as FUT_PROFILE
from live.fx_intraday_hp_size_liquidity_yearly import liquidity_1m_csv
from live.intraday_condition_overlay import COND_COL as _FX
from live.intraday_condition_overlay import hp_mask
from live.notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "hp_size_lock_v1"
FX_PROFILE = REPO / "live" / "state" / "intraday_condition_profile"
FUT_COND = dict(_FUT)
FX_COND = dict(_FX)
NY = "America/New_York"

LOCK = (
    (
        "NQ OR-norm",
        "nq_prior_opposed_rl",
        "Opening 15m range vs ATR",
        "or_norm",
        "fut",
        4.0,
        "NQ",
        5,
        20.0,
        20000.0,
        "best futures HP; liq OK @4×; deploy auth still provisional ≤2×",
        "provisional ≤2×",
    ),
    (
        "ES ST-age>180m",
        "es_prior_opposed_legacy",
        "ST-event age",
        "st_age_gt180m",
        "fut",
        4.0,
        "ES",
        5,
        50.0,
        15000.0,
        "next-best non-NQ futures; NOT VALIDATED under ΔN/S — research capital only",
        "NOT VALIDATED research",
    ),
    (
        "EURUSD ST+PMC Thu",
        "eurusd_st_pmc_3r",
        "Day of week",
        "Thursday",
        "fx",
        40.0,
        "EURUSD",
        1,
        100000.0,
        2500.0,
        "best non-CFD/non-futures; locked research size 40×; deploy auth still 1.25×",
        "VALIDATED @1.25× only",
    ),
)


def _load(book: str, cond: str, bucket: str, kind: str):
    overlay.COND_COL.clear()
    overlay.COND_COL.update(FUT_COND if kind == "fut" else FX_COND)
    prof = FUT_PROFILE if kind == "fut" else FX_PROFILE
    camp = pd.read_csv(prof / "all_campaigns.csv")
    camp["entry_ts"] = pd.to_datetime(camp["entry_ts"], utc=True)
    df = camp[camp["book"] == book].sort_values("entry_ts").reset_index(drop=True)
    df["year"] = df["entry_ts"].dt.year
    df["session_date"] = df["entry_ts"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    m = hp_mask(df, cond, bucket).to_numpy()
    if not m.any():
        raise RuntimeError("empty HP %s" % book)
    return df, m


def run(*, email: bool = False) -> Path:
    HUB.mkdir(parents=True, exist_ok=True)
    rows = []
    for label, book, cond, bucket, kind, mult, sym, bq, pv, im, note, deploy in LOCK:
        df, m = _load(book, cond, bucket, kind)
        year, meta = yearly_250k(df, m, mult)
        slug = label.lower().replace(" ", "_").replace(">", "gt").replace("+", "p")
        year.to_csv(HUB / ("%s_yearly_%dx_250k.csv" % (slug, int(mult))), index=False)
        liq = {}
        try:
            if kind == "fut" and sym == "NQ":
                _, liq = liquidity_1m(
                    df, m, symbol=sym, base_qty=bq, mult=mult, point_value=pv, im_approx=im
                )
            elif kind == "fut" and sym == "ES":
                _, liq = liquidity_daily(
                    df, m, symbol=sym, base_qty=bq, mult=mult, point_value=pv, im_approx=im
                )
            else:
                _, liq = liquidity_1m_csv(
                    df, m, symbol=sym, base_qty=bq, mult=mult, point_value=pv, im_approx=im
                )
        except Exception as exc:
            liq = {"error": str(exc), "approx_im": bq * mult * im, "qty": int(bq * mult)}
        (HUB / ("%s_liq.json" % slug)).write_text(json.dumps(liq, indent=2) + "\n")
        rows.append(
            {
                "label": label,
                "book": book,
                "condition": cond,
                "bucket": bucket,
                "mult_locked": mult,
                "hp_n": int(m.sum()),
                "n": int(len(df)),
                "book_net": meta["book_net"],
                "book_stress": meta["book_stress"],
                "book_ns": meta["book_ns"],
                "final_250k": meta["final"],
                "cagr_span_pct": meta["cagr_span_pct"],
                "span_years": meta["span_years"],
                "qty": int(round(bq * mult)),
                "approx_im": float(liq.get("approx_im", bq * mult * im)),
                "note": note,
                "deploy_auth": deploy,
            }
        )

    pd.DataFrame(rows).to_csv(HUB / "LOCKED_SLEEVES.csv", index=False)
    payload = {
        "locked_at": datetime.now(timezone.utc).isoformat(),
        "kind": "research_capital_lock",
        "disclaimer": "Linear sensitivity sizes — not null-suite authorization.",
        "sleeves": rows,
        "excluded": {
            "US30 Monday OR h11": (
                "CFD; YM-proxy liquidity binds by ~80×. Keep deploy auth 1.25×."
            )
        },
    }
    (HUB / "LOCKED.json").write_text(json.dumps(payload, indent=2) + "\n")

    lines = [
        "# HP size lock v1 — research capital package",
        "",
        "Locked: **%s**." % datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "",
        "Research capital lock (linear HP scaling). Does **not** rewrite deploy auth:",
        "",
        "- Futures: NQ provisional **≤2×**; ES **NOT VALIDATED**",
        "- FX: EURUSD Thu + US30 h11 **VALIDATED @1.25×** only",
        "",
        "## Locked sleeves",
        "",
        "| Sleeve | Mult | qty | Net | Stress | N/S | $250k→ | ≈IM | Deploy auth |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| {label} | {mult_locked:g}× | {qty} | ${book_net:,.0f} | ${book_stress:,.0f} | "
            "{book_ns:.2f} | ${final_250k:,.0f} | ${approx_im:,.0f} | {deploy_auth} |".format(**r)
        )
    lines.extend(
        [
            "",
            "### Explicitly not locked at high size",
            "",
            "- **US30 Monday OR hour 11** — CFD; YM-proxy liq binds ~80×. Keep **1.25×**.",
            "",
            "Hub: `live/state/hp_size_lock_v1/`",
            "",
        ]
    )
    md = "\n".join(lines)
    (HUB / "LOCKED_PLAN.md").write_text(md)
    (HUB / "SUMMARY.md").write_text(md)

    email_body = "\n".join(
        [
            "potions: HP size LOCK v1 — NQ/ES @4× + EURUSD Thu @40×",
            "",
            "Research capital lock (NOT null-suite auth for these mults):",
            "",
        ]
        + [
            "- %s @%gx: net %s / stress %s / N/S %.2f; $250k→%s; ≈IM %s; deploy=%s"
            % (
                r["label"],
                r["mult_locked"],
                _fmt_money(r["book_net"]),
                _fmt_money(r["book_stress"]),
                r["book_ns"],
                _fmt_money(r["final_250k"]),
                _fmt_money(r["approx_im"]),
                r["deploy_auth"],
            )
            for r in rows
        ]
        + [
            "",
            "US30 high-size excluded. Hub: live/state/hp_size_lock_v1/",
            "",
        ]
    )
    (HUB / "EMAIL.txt").write_text(email_body)
    (HUB / "RUN_COMPLETE.json").write_text(json.dumps({"ok": True, "lock": "v1"}, indent=2) + "\n")
    print(email_body, flush=True)
    if email:
        send_email(subject="potions: HP size LOCK v1 (NQ/ES 4× + EURUSD 40×)", body=email_body)
    return HUB


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)
    try:
        run(email=bool(args.email))
        return 0
    except Exception:
        if args.email:
            send_email(subject="potions: HP size LOCK v1 FAILED", body=traceback.format_exc())
        raise


if __name__ == "__main__":
    raise SystemExit(main())
