"""Correlation / session overlap: v2b prior-opposed vs profitable ST+PMC fair 3R.

Joins on NY session date (+ direction). Covers NQ/MNQ/YM/US30/NAS100 where
both sleeves exist. Classification uses SEPARATE_REGIMES / CONDITIONAL_OVERLAP /
SAME_SLEEVE / UNRESOLVED (never Jaccard-OR-|ρ|).
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set, Tuple

import pandas as pd

from .notify_email import send_email
from .regime_overlap import book_identity, duplicate_sleeve_warnings, overlap_metrics

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "v2b_stpmc_3r_correlation"

# (label, path, kind) kind in {unit_trades, unit_fills}
V2B = {
    "nq": (
        "NQ prior-opposed",
        REPO
        / "live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv",
        "unit_trades",
    ),
    "mnq": (
        "MNQ prior-opposed",
        REPO
        / "live/state/mnq_v2b_prior_opposed_stpmc_resting_limit/states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv",
        "unit_trades",
    ),
    "ym": (
        "YM prior-opposed",
        REPO
        / "live/state/ym_v2b_prior_opposed_stpmc_resting_limit/states/ym_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv",
        "unit_trades",
    ),
    "us30": (
        "US30 prior-opposed",
        REPO
        / "live/state/us30_futures_strats_sweep/states/us30_v2b_oco_prior_opposed_S_1_1_3/unit_trades.csv",
        "unit_trades",
    ),
    "nas100": (
        "NAS100 prior-opposed",
        REPO
        / "live/state/nas100_v2b_prior_opposed_stpmc_broker_like/states/nas100_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv",
        "unit_trades",
    ),
}

STPMC = {
    "nq": (
        "NQ ST+PMC 3R",
        REPO
        / "live/state/futures_st_pmc_runner_variants/audits_lot_correct/nq_hourly_st_pmc_sl50_tp150_3r_1mfill/nq_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct/unit_fills.csv",
        "unit_fills",
    ),
    "mnq": (
        "MNQ ST+PMC 3R",
        REPO
        / "live/state/futures_st_pmc_runner_variants/audits_lot_correct/mnq_hourly_st_pmc_sl50_tp150_3r_1mfill/mnq_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct/unit_fills.csv",
        "unit_fills",
    ),
    "ym": (
        "YM ST+PMC 3R",
        REPO
        / "live/state/futures_st_pmc_runner_variants/audits_lot_correct/ym_hourly_st_pmc_sl50_tp150_3r_1mfill/ym_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct/unit_fills.csv",
        "unit_fills",
    ),
    "us30": (
        "US30 ST+PMC 3R",
        REPO
        / "live/state/us30_st_pmc_runner_variants/audits_lot_correct/us30_hourly_st_pmc_sl50_tp150_3r_1mfill/us30_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct/unit_fills.csv",
        "unit_fills",
    ),
    "nas100": (
        "NAS100 ST+PMC 3R",
        REPO
        / "live/state/fx_index_metals_st_pmc_runner_variants/nas100/audits/nas100_hourly_st_pmc_sl50_tp150_3r_1mfill/nas100_hourly_st_pmc_sl50_tp150_3r_1mfill/unit_fills.csv",
        "unit_fills",
    ),
}

def _ny_day(ts: str) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return str(t.date())
    return str(t.tz_convert("America/New_York").date())


def _dir(d: str) -> str:
    return "L" if str(d).lower().startswith("l") else "S"


def _load(path: Path, kind: str) -> List[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by: Dict[str, dict] = {}
    for r in rows:
        tid = r["trade_id"]
        if tid not in by:
            by[tid] = {
                "trade_id": tid,
                "day": _ny_day(r["entry_ts"]),
                "dir": _dir(r["direction"]),
                "net_usd": 0.0,
            }
        if kind == "unit_fills":
            if r.get("usd") not in (None, ""):
                by[tid]["net_usd"] += float(r["usd"])
            elif r.get("points") not in (None, ""):
                by[tid]["net_usd"] += float(r["points"])
        else:
            by[tid]["net_usd"] += float(r.get("net_usd") or 0)
    return list(by.values())


def _day_set(camps: Sequence[dict]) -> Set[str]:
    return {c["day"] for c in camps}


def _day_dir_set(camps: Sequence[dict]) -> Set[Tuple[str, str]]:
    return {(c["day"], c["dir"]) for c in camps}


def _daily_net(camps: Sequence[dict]) -> Dict[str, float]:
    out: Dict[str, float] = defaultdict(float)
    for c in camps:
        out[c["day"]] += float(c["net_usd"])
    return dict(out)


def _corr(a: Dict[str, float], b: Dict[str, float]) -> Tuple[Optional[float], int]:
    keys = sorted(set(a) & set(b))
    if len(keys) < 5:
        return None, len(keys)
    xa = [a[k] for k in keys]
    xb = [b[k] for k in keys]
    ma = sum(xa) / len(xa)
    mb = sum(xb) / len(xb)
    num = sum((x - ma) * (y - mb) for x, y in zip(xa, xb))
    da = math.sqrt(sum((x - ma) ** 2 for x in xa))
    db = math.sqrt(sum((y - mb) ** 2 for y in xb))
    if da < 1e-12 or db < 1e-12:
        return None, len(keys)
    return num / (da * db), len(keys)


def _overlap(
    name_a: str,
    a: List[dict],
    name_b: str,
    b: List[dict],
    *,
    market_a: str = "",
    market_b: str = "",
    strategy_a: str = "",
    strategy_b: str = "",
    book_a: str = "",
    book_b: str = "",
) -> dict:
    return overlap_metrics(
        name_a,
        a,
        name_b,
        b,
        identity_a=book_identity(
            market=market_a,
            strategy=strategy_a or name_a,
            book=book_a,
            strategy_id="%s_%s_%s" % (market_a, strategy_a or "strat", book_a or "book"),
        ),
        identity_b=book_identity(
            market=market_b,
            strategy=strategy_b or name_b,
            book=book_b,
            strategy_id="%s_%s_%s" % (market_b, strategy_b or "strat", book_b or "book"),
        ),
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    loaded_v2b = {}
    loaded_st = {}
    for k, (label, path, kind) in V2B.items():
        if path.exists():
            loaded_v2b[k] = (label, _load(path, kind))
        else:
            print("missing v2b %s: %s" % (k, path), flush=True)
    for k, (label, path, kind) in STPMC.items():
        if path.exists():
            loaded_st[k] = (label, _load(path, kind))
        else:
            print("missing stpmc %s: %s" % (k, path), flush=True)

    results = []
    # Same-market: v2b PO vs ST+PMC 3R
    for k in sorted(set(loaded_v2b) & set(loaded_st)):
        la, a = loaded_v2b[k]
        lb, b = loaded_st[k]
        r = _overlap(
            la,
            a,
            lb,
            b,
            market_a=k,
            market_b=k,
            strategy_a="v2b_prior_opposed",
            strategy_b="st_pmc",
            book_a="S_1_1_3",
            book_b="sl50_tp150_3r_1mfill",
        )
        r["bucket"] = "same_market_v2b_vs_stpmc"
        results.append(r)

    # Cross-market: v2b of A vs ST+PMC of B
    for a_mkt, b_mkt in [("ym", "us30"), ("us30", "ym"), ("nq", "nas100"), ("nas100", "nq")]:
        if a_mkt in loaded_v2b and b_mkt in loaded_st:
            la, a = loaded_v2b[a_mkt]
            lb, b = loaded_st[b_mkt]
            r = _overlap(
                la,
                a,
                lb,
                b,
                market_a=a_mkt,
                market_b=b_mkt,
                strategy_a="v2b_prior_opposed",
                strategy_b="st_pmc",
                book_a="S_1_1_3",
                book_b="sl50_tp150_3r_1mfill",
            )
            r["bucket"] = "cross_v2b_vs_stpmc"
            results.append(r)

    # Linked underlyings: ST+PMC vs ST+PMC
    for a_mkt, b_mkt in [("ym", "us30"), ("nq", "nas100"), ("nq", "mnq")]:
        if a_mkt in loaded_st and b_mkt in loaded_st:
            la, a = loaded_st[a_mkt]
            lb, b = loaded_st[b_mkt]
            r = _overlap(
                la,
                a,
                lb,
                b,
                market_a=a_mkt,
                market_b=b_mkt,
                strategy_a="st_pmc",
                strategy_b="st_pmc",
                book_a="sl50_tp150_3r_1mfill",
                book_b="sl50_tp150_3r_1mfill",
            )
            r["bucket"] = "cross_stpmc_vs_stpmc"
            results.append(r)

    OUT.mkdir(parents=True, exist_ok=True)
    fields = [
        "bucket",
        "pair",
        "a_campaigns",
        "b_campaigns",
        "shared_days",
        "day_jaccard",
        "dir_agree_rate_on_shared",
        "same_day_same_dir_events",
        "daily_net_corr",
        "shared_day_pnl_corr",
        "union_day_pnl_corr",
        "corr_days",
        "regime_class",
        "recommended_sizing",
        "regime_separable",
    ]
    with (OUT / "correlation_summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in results:
            w.writerow(r)
    sleeve_warn = duplicate_sleeve_warnings(
        list(loaded_st.keys()) + list(loaded_v2b.keys()),
        strategy="st_pmc_or_v2b",
        book="3r_correlation",
    )
    (OUT / "correlation.json").write_text(
        json.dumps({"results": results, "duplicate_sleeve_warnings": sleeve_warn}, indent=2) + "\n"
    )

    lines = [
        "# v2b prior-opposed ↔ ST+PMC fair 3R correlation",
        "",
        "Join: NY session date (+ direction). Classes: SEPARATE_REGIMES | CONDITIONAL_OVERLAP | SAME_SLEEVE | UNRESOLVED.",
        "",
        "## Same-market (v2b PO vs ST+PMC 3R)",
        "",
        "| pair | Jaccard | dir-agree | same-dir events | daily ρ | class |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in results:
        if r["bucket"] != "same_market_v2b_vs_stpmc":
            continue
        lines.append(
            "| %s | %.2f | %s | %s | %s | %s |"
            % (
                r["pair"],
                r["day_jaccard"],
                r["dir_agree_rate_on_shared"],
                r["same_day_same_dir_events"],
                r.get("shared_day_pnl_corr", r["daily_net_corr"]),
                r.get("regime_class"),
            )
        )
    lines += [
        "",
        "## Cross-market",
        "",
        "| bucket | pair | Jaccard | daily ρ | class |",
        "|---|---|---:|---:|---|",
    ]
    for r in results:
        if r["bucket"] == "same_market_v2b_vs_stpmc":
            continue
        lines.append(
            "| %s | %s | %.2f | %s | %s |"
            % (
                r["bucket"],
                r["pair"],
                r["day_jaccard"],
                r.get("shared_day_pnl_corr", r["daily_net_corr"]),
                r.get("regime_class"),
            )
        )
    lines += [
        "",
        "## Read",
        "",
        "- Same-market PO vs ST should often be **SEPARATE_REGIMES** (OR/v2b vs hourly retest).",
        "- Cross ST+PMC on linked underlyings (YM↔US30, NQ↔NAS100) often **SAME_SLEEVE**.",
        "- Low Jaccard + high shared-day ρ → **CONDITIONAL_OVERLAP**, not separate.",
        "",
    ]
    for wmsg in sleeve_warn:
        lines.append("- **Duplicate sleeve:** %s" % wmsg["message"])
    lines += ["", "Hub: `live/state/v2b_stpmc_3r_correlation/`", ""]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    same = [r for r in results if r["bucket"] == "same_market_v2b_vs_stpmc"]
    sep_n = sum(1 for r in same if r.get("regime_class") == "SEPARATE_REGIMES")
    email = [
        "v2b ↔ ST+PMC 3R correlation",
        "",
        "Same-market PO vs ST+PMC: %d/%d SEPARATE_REGIMES" % (sep_n, len(same)),
        "",
    ]
    for r in same:
        email.append(
            "  %s | J=%.2f ρ=%s class=%s"
            % (
                r["pair"],
                r["day_jaccard"],
                r.get("shared_day_pnl_corr", r["daily_net_corr"]),
                r.get("regime_class"),
            )
        )
    email.append("")
    email.append("Cross (highlights):")
    for r in results:
        if r["bucket"] == "same_market_v2b_vs_stpmc":
            continue
        if "YM prior" in r["pair"] and "US30 ST" in r["pair"]:
            email.append(
                "  %s | J=%.2f ρ=%s class=%s"
                % (
                    r["pair"],
                    r["day_jaccard"],
                    r.get("shared_day_pnl_corr", r["daily_net_corr"]),
                    r.get("regime_class"),
                )
            )
        if "NQ ST" in r["pair"] and "NAS100 ST" in r["pair"]:
            email.append(
                "  %s | J=%.2f ρ=%s class=%s"
                % (
                    r["pair"],
                    r["day_jaccard"],
                    r.get("shared_day_pnl_corr", r["daily_net_corr"]),
                    r.get("regime_class"),
                )
            )
        if "YM ST" in r["pair"] and "US30 ST" in r["pair"]:
            email.append(
                "  %s | J=%.2f ρ=%s class=%s"
                % (
                    r["pair"],
                    r["day_jaccard"],
                    r.get("shared_day_pnl_corr", r["daily_net_corr"]),
                    r.get("regime_class"),
                )
            )
    for wmsg in sleeve_warn:
        email.append("DUPLICATE SLEEVE: %s" % wmsg["message"])
    email += ["", "Hub: live/state/v2b_stpmc_3r_correlation/"]
    body = "\n".join(email) + "\n"
    (OUT / "EMAIL.txt").write_text(body)
    if args.email:
        send_email(subject="potions: v2b ↔ ST+PMC 3R correlation", body=body)
        print("emailed correlation", flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
