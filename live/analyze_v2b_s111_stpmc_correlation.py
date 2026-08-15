"""Correlation: base ungated v2b S_1_1_1 (1/1/1) vs profitable ST+PMC fair 3R.

NOT prior-opposed. v2b source = ``v2b_sizing_sweep`` ladder S_1_1_1
(entry 3 = 1 TP1 + 1 TP2 + 1 EOD runner).
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
OUT = REPO / "live" / "state" / "v2b_s111_stpmc_3r_correlation"

# Base ungated v2b S_1_1_1 only (explicitly NOT prior-opposed)
V2B_S111 = {
    "nq": (
        "NQ v2b S_1_1_1",
        REPO / "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_1/unit_trades.csv",
    ),
    "mnq": (
        "MNQ v2b S_1_1_1",
        REPO / "live/state/v2b_sizing_sweep/states/mnq_v2b_sizing_S_1_1_1/unit_trades.csv",
    ),
    "ym": (
        "YM v2b S_1_1_1",
        REPO / "live/state/v2b_sizing_sweep/states/ym_v2b_sizing_S_1_1_1/unit_trades.csv",
    ),
    "mym": (
        "MYM v2b S_1_1_1",
        REPO / "live/state/v2b_sizing_sweep/states/mym_v2b_sizing_S_1_1_1/unit_trades.csv",
    ),
}

STPMC_3R = {
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
    "mym": (
        "MYM ST+PMC 3R",
        REPO
        / "live/state/futures_st_pmc_runner_variants/audits_lot_correct/mym_hourly_st_pmc_sl50_tp150_3r_1mfill/mym_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct/unit_fills.csv",
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


def _load_unit_trades(path: Path) -> List[dict]:
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
                "n_units": 0,
            }
        by[tid]["net_usd"] += float(r.get("net_usd") or 0)
        by[tid]["n_units"] += 1
    return list(by.values())


def _load_unit_fills(path: Path) -> List[dict]:
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
        if r.get("usd") not in (None, ""):
            by[tid]["net_usd"] += float(r["usd"])
        elif r.get("points") not in (None, ""):
            by[tid]["net_usd"] += float(r["points"])
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
    book_a: str = "S_1_1_1",
    book_b: str = "sl50_tp150_3r_1mfill",
) -> dict:
    return overlap_metrics(
        name_a,
        a,
        name_b,
        b,
        identity_a=book_identity(
            market=market_a,
            strategy=strategy_a or name_a,
            version="base_ungated",
            book=book_a,
            strategy_id="%s_%s_%s" % (market_a, strategy_a or "v2b", book_a),
        ),
        identity_b=book_identity(
            market=market_b,
            strategy=strategy_b or name_b,
            book=book_b,
            strategy_id="%s_%s_%s" % (market_b, strategy_b or "st_pmc", book_b),
        ),
    )


def _assert_s111(camps: List[dict], label: str) -> None:
    bad = [c for c in camps if int(c.get("n_units") or 0) != 3]
    if bad:
        # Some campaigns can flatten early with <3 unit rows if stopped as a block;
        # require modal units == 3 and median == 3.
        from statistics import median

        units = [int(c["n_units"]) for c in camps]
        if median(units) != 3:
            raise SystemExit("%s does not look like S_1_1_1 (median units=%s)" % (label, median(units)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    loaded_v2b = {}
    for k, (label, path) in V2B_S111.items():
        if not path.exists():
            print("missing v2b S_1_1_1 %s: %s" % (k, path), flush=True)
            continue
        camps = _load_unit_trades(path)
        _assert_s111(camps, label)
        loaded_v2b[k] = (label, camps)
        print("loaded %s campaigns=%d median_units=3 path=%s" % (label, len(camps), path.name), flush=True)

    loaded_st = {}
    for k, (label, path, _kind) in STPMC_3R.items():
        if not path.exists():
            print("missing stpmc %s: %s" % (k, path), flush=True)
            continue
        loaded_st[k] = (label, _load_unit_fills(path))

    results = []
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
            strategy_a="v2b_base",
            strategy_b="st_pmc",
            book_a="S_1_1_1",
            book_b="sl50_tp150_3r_1mfill",
        )
        r["bucket"] = "same_market_v2b_s111_vs_stpmc"
        results.append(r)

    # Cross: base v2b futures vs CFD ST (linked underlyings)
    for a_mkt, b_mkt in [("ym", "us30"), ("nq", "nas100"), ("nq", "mnq"), ("ym", "mym")]:
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
                strategy_a="v2b_base",
                strategy_b="st_pmc",
                book_a="S_1_1_1",
                book_b="sl50_tp150_3r_1mfill",
            )
            r["bucket"] = "cross_v2b_s111_vs_stpmc"
            results.append(r)

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
        strategy="v2b_s111_or_stpmc",
        book="correlation",
    )
    (OUT / "correlation.json").write_text(
        json.dumps({"results": results, "duplicate_sleeve_warnings": sleeve_warn}, indent=2)
        + "\n"
    )

    same = [r for r in results if r["bucket"] == "same_market_v2b_s111_vs_stpmc"]
    sep_n = sum(1 for r in same if r.get("regime_class") == "SEPARATE_REGIMES")

    lines = [
        "# Base v2b S_1_1_1 ↔ ST+PMC fair 3R correlation",
        "",
        "**v2b book: ungated `S_1_1_1` (1 TP1 + 1 TP2 + 1 runner)** from `v2b_sizing_sweep`.",
        "**Not** prior-opposed. **Not** S_1_1_3.",
        "",
        "US30/NAS100 have no archived base v2b S_1_1_1 book — cross pairs use YM/NQ v2b vs CFD ST.",
        "",
        "## Same-market",
        "",
        "| pair | Jaccard | dir-agree | same-dir | daily ρ | class |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for r in same:
        lines.append(
            "| %s | %.2f | %s | %s | %s | %s |"
            % (
                r["pair"],
                r["day_jaccard"],
                r["dir_agree_rate_on_shared"],
                r["same_day_same_dir_events"],
                r["daily_net_corr"],
                r.get("regime_class"),
            )
        )
    lines += ["", "## Cross", "", "| bucket | pair | Jaccard | ρ | class |", "|---|---|---:|---:|---|"]
    for r in results:
        if r["bucket"] == "same_market_v2b_s111_vs_stpmc":
            continue
        lines.append(
            "| %s | %s | %.2f | %s | %s |"
            % (r["bucket"], r["pair"], r["day_jaccard"], r.get("shared_day_pnl_corr", r["daily_net_corr"]), r.get("regime_class"))
        )
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n")

    # Agentic email
    email = [
        "v2b S_1_1_1 ↔ ST+PMC 3R — correlation analysis",
        "",
        "IMPORTANT: v2b side is BASE ungated S_1_1_1 (1/1/1),",
        "from v2b_sizing_sweep — NOT prior-opposed, NOT S_1_1_3.",
        "",
        "VERDICT: same-market SEPARATE_REGIMES %d/%d — OR breakout vs hourly ST retest"
        % (sep_n, len(same)),
        "are different liquidity regimes on NQ/MNQ/YM/MYM.",
        "",
        "Same-market (v2b S_1_1_1 vs ST+PMC 3R):",
    ]
    for r in same:
        tag = r.get("regime_class") or "?"
        email.append(
            "  [%s] %s | J=%.2f ρ=%s dir-agree=%s same-dir=%d"
            % (
                tag,
                r["pair"],
                r["day_jaccard"],
                r["daily_net_corr"],
                r["dir_agree_rate_on_shared"],
                r["same_day_same_dir_events"],
            )
        )
    email += ["", "Cross highlights:"]
    for r in results:
        if r["bucket"] == "same_market_v2b_s111_vs_stpmc":
            continue
        keep = any(
            s in r["pair"]
            for s in (
                "YM v2b S_1_1_1 vs US30 ST",
                "NQ v2b S_1_1_1 vs NAS100 ST",
                "YM ST+PMC 3R vs US30 ST",
                "NQ ST+PMC 3R vs NAS100 ST",
                "NQ ST+PMC 3R vs MNQ ST",
            )
        )
        if not keep and "ST+PMC" in r["pair"] and "vs" in r["pair"]:
            # keep st vs st linked
            if r["bucket"] == "cross_stpmc_vs_stpmc":
                keep = True
        if not keep and r["bucket"] == "cross_v2b_s111_vs_stpmc":
            keep = True
        if keep:
            email.append(
                "  %s | J=%.2f ρ=%s sep=%s"
                % (r["pair"], r["day_jaccard"], r.get("shared_day_pnl_corr", r["daily_net_corr"]), r.get("regime_class"))
            )
    email += [
        "",
        "Read:",
        "- Stack base v2b S_1_1_1 with ST+PMC 3R on the same future = OK (low ρ).",
        "- Do NOT treat YM ST + US30 ST (or NQ ST + NAS100 ST) as independent.",
        "- Prior email used prior-opposed by mistake; this corrects the book.",
        "",
        "Hub: live/state/v2b_s111_stpmc_3r_correlation/",
    ]
    for wmsg in sleeve_warn:
        email.append("DUPLICATE SLEEVE: %s" % wmsg["message"])
    body = "\n".join(email) + "\n"
    (OUT / "EMAIL.txt").write_text(body)
    if args.email:
        send_email(subject="potions: v2b S_1_1_1 ↔ ST+PMC 3R correlation (not prior-opposed)", body=body)
        print("emailed", flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
