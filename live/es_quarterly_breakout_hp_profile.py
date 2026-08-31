"""ES quarterly range breakout — broker-like HP profile + HTF nulls.

Usual futures HP condition checks on the promising ES quarterly breakout tape,
plus HTF structure tags:

  - Yearly ORB direction (up / down / inside)
  - Monthly OR direction (up / down / inside)
  - Prior quarter type (inside / break_up / break_down / both)
  - Weekly ATR SuperTrend align / oppose vs trade

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.es_quarterly_breakout_hp_profile --email
  python -m live.es_quarterly_breakout_hp_profile --email --profile-only
  python -m live.es_quarterly_breakout_hp_profile --email --nulls-only
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from live.futures_intraday_condition_profile import profile_book
from live.futures_intraday_hp_sizeup_lib import (
    FuturesBook,
    annotate_campaigns,
    feature_family,
    load_campaigns,
)
from live.futures_intraday_hp_sizeup_nulls import run as run_nulls
from live.notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
FILLS = (
    REPO
    / "live/state/es_quarterly_range_breakout_broker/states/es_quarterly_range_breakout/fills.csv"
)
PROFILE_HUB = REPO / "live/state/es_quarterly_breakout_hp_profile"
NULLS_HUB = REPO / "live/state/es_quarterly_breakout_hp_nulls"
BOOK_KEY = "es_quarterly_range_breakout"
STUDY = "es_quarterly_breakout_hp_v1"

MIN_N = 8
HP_COV_LO = 0.05
HP_COV_HI = 0.55

HTF_TITLES = (
    "Yearly ORB direction",
    "Monthly OR direction",
    "Prior quarter type",
    "Weekly ATR trend vs trade",
)

HTF_FORCE_BUCKETS = (
    ("Yearly ORB direction", "yor_up"),
    ("Yearly ORB direction", "yor_down"),
    ("Monthly OR direction", "mor_up"),
    ("Monthly OR direction", "mor_down"),
    ("Prior quarter type", "q_break_up"),
    ("Prior quarter type", "q_inside"),
    ("Prior quarter type", "q_break_down"),
    ("Weekly ATR trend vs trade", "w_atr_aligned"),
    ("Weekly ATR trend vs trade", "w_atr_opposed"),
)


def make_book() -> FuturesBook:
    return FuturesBook(
        key=BOOK_KEY,
        label="ES quarterly range honest breakout",
        symbol="ES",
        family="quarterly_breakout",
        fills=FILLS,
        tracker_ns=5.59,
        tracker_net=1_258_367.50,
        tracker_stress=225_184.0,
        campaigns_est=60,
        status="strongest-candidate",
        notes="broker-like daily QB; HTF HP study",
    )


def progress(msg: str, *, hub: Path) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg.rstrip() + "\n")
    print(msg, flush=True)


def shortlist_relaxed(
    matrix: pd.DataFrame, baseline: Dict[str, float], *, max_n: int = 5
) -> pd.DataFrame:
    if matrix.empty:
        return pd.DataFrame()
    base_ok = float(baseline.get("net", 0)) > 0 and float(baseline.get("ns", 0)) > 0
    ranked = matrix.sort_values(["inc_ns", "avg_lift", "z_wr"], ascending=False)
    seen: set = set()
    rows: List[dict] = []
    for _, r in ranked.iterrows():
        if not base_ok:
            break
        fam = str(r.get("family") or feature_family(str(r["condition"])))
        cov = float(r["coverage"])
        bucket = str(r["bucket"])
        if cov < HP_COV_LO or cov > HP_COV_HI:
            continue
        if float(r["avg_lift"]) <= 0 or float(r["wr_lift_pp"]) <= 0:
            continue
        if int(r["n"]) < MIN_N:
            continue
        if bucket.endswith("_na") or bucket == "na":
            continue
        if fam in seen:
            continue
        seen.add(fam)
        rows.append({**r.to_dict(), "source": "shortlist"})
        if len(rows) >= max_n:
            break

    htf = matrix[matrix["condition"].isin(HTF_TITLES)].copy()
    htf = htf[
        (htf["n"] >= MIN_N)
        & (htf["avg_lift"] > 0)
        & (htf["wr_lift_pp"] > 0)
        & ~htf["bucket"].astype(str).str.endswith("_na")
    ].sort_values(["inc_ns", "avg_lift"], ascending=False)
    have = {(str(r["condition"]), str(r["bucket"])) for r in rows}
    forced = 0
    for _, r in htf.iterrows():
        key = (str(r["condition"]), str(r["bucket"]))
        if key in have:
            continue
        rows.append({**r.to_dict(), "source": "htf_forced"})
        have.add(key)
        forced += 1
        if forced >= 4:
            break
    return pd.DataFrame(rows)


def build_null_pairs(
    book_key: str, short: pd.DataFrame, matrix: pd.DataFrame
) -> List[Tuple[str, str, str]]:
    pairs: List[Tuple[str, str, str]] = []
    for _, r in short.iterrows():
        pairs.append((book_key, str(r["condition"]), str(r["bucket"])))
    for cond, bucket in HTF_FORCE_BUCKETS:
        hit = matrix[(matrix["condition"] == cond) & (matrix["bucket"] == bucket)]
        if hit.empty or int(hit.iloc[0]["n"]) < MIN_N:
            continue
        tup = (book_key, cond, bucket)
        if tup not in pairs:
            pairs.append(tup)
    return pairs[:14]


def run_profile(*, email: bool = False) -> Tuple[Path, pd.DataFrame, List[Tuple[str, str, str]]]:
    hub = PROFILE_HUB
    hub.mkdir(parents=True, exist_ok=True)
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")
    progress("START %s profile" % STUDY, hub=hub)

    book = make_book()
    if not book.fills.exists():
        raise FileNotFoundError(book.fills)

    camp = load_campaigns(book)
    progress("campaigns=%d net=%+.0f" % (len(camp), float(camp["net_usd"].sum())), hub=hub)
    ann = annotate_campaigns(camp, book.symbol)
    if "year" not in ann.columns:
        ann["year"] = pd.to_datetime(ann["entry_ts"], utc=True).dt.year
    if "session_date" not in ann.columns:
        ann["session_date"] = pd.to_datetime(ann["entry_ts"], utc=True).dt.strftime("%Y-%m-%d")
    if "direction" not in ann.columns:
        ann["direction"] = np.where(ann["side"].astype(str) == "long", 1, -1)
    if "sleeve" not in ann.columns:
        ann["sleeve"] = "es"

    ann.to_csv(hub / ("%s_campaigns.csv" % book.key), index=False)
    ann.to_csv(hub / "all_campaigns.csv", index=False)

    table, baseline, notables = profile_book(ann, min_n=MIN_N)
    table.to_csv(hub / ("%s_buckets.csv" % book.key), index=False)
    table.to_csv(hub / "condition_matrix.csv", index=False)
    pd.DataFrame(notables).to_csv(hub / "notables.csv", index=False)
    (hub / "baselines.json").write_text(
        json.dumps({book.key: baseline}, indent=2, default=float), encoding="utf-8"
    )

    short = shortlist_relaxed(table, baseline, max_n=5)
    short.to_csv(hub / "shortlist.csv", index=False)

    htf = table[table["condition"].isin(HTF_TITLES)].sort_values(
        ["condition", "avg_lift"], ascending=[True, False]
    )
    htf.to_csv(hub / "htf_buckets.csv", index=False)

    (hub / "HTF_FEATURES.md").write_text(
        "\n".join(
            [
                "# ES quarterly breakout — HTF features (causal asof entry)",
                "",
                "Applied to the **quarterly range breakout** broker-like tape (n=%d)." % len(ann),
                "",
                "| Feature | Col | Buckets | Definition |",
                "|---------|-----|---------|------------|",
                "| Yearly ORB direction | `yor_dir` | `yor_up` / `yor_down` / `yor_inside` / `yor_both` / `yor_na` | Jan–Mar H/L OR; ready Apr 1. |",
                "| Monthly OR direction | `mor_dir` | `mor_up` / `mor_down` / `mor_inside` / `mor_both` / `mor_na` | First 3 sessions of month. |",
                "| Prior quarter type | `prior_q_type` | `q_inside` / `q_break_up` / `q_break_down` / `q_break_both` / `q_na` | Prior quarter vs its prior H/L. |",
                "| Weekly ATR vs trade | `w_atr_align` | `w_atr_aligned` / `w_atr_opposed` / `w_atr_na` | Weekly ATR SuperTrend (14, ×3). |",
                "",
                "Min bucket N=%d. Shortlist coverage %.0f–%.0f%%; HTF dual-lift tags force-included for nulls."
                % (MIN_N, 100 * HP_COV_LO, 100 * HP_COV_HI),
                "",
            ]
        ),
        encoding="utf-8",
    )

    pairs = build_null_pairs(book.key, short, table)
    (hub / "null_pairs.json").write_text(json.dumps(pairs, indent=2), encoding="utf-8")

    lines = [
        "# ES quarterly range breakout — HP + HTF condition profile",
        "",
        "Study: `%s`" % STUDY,
        "Hub: `live/state/es_quarterly_breakout_hp_profile/`",
        "Tape: `es_quarterly_range_breakout_broker` (Engine + PaperBroker, daily).",
        "",
        "## Baseline",
        "",
        "| n | WR | net | stress | N/S | avg |",
        "|---:|---:|---:|---:|---:|---:|",
        "| %d | %.1f%% | %+.0f | %.0f | %.2f | %+.0f |"
        % (
            baseline["n"],
            100 * baseline["wr"],
            baseline["net"],
            baseline["stress"],
            baseline["ns"],
            baseline["avg"],
        ),
        "",
        "## Shortlist / HTF null candidates",
        "",
    ]
    if short.empty:
        lines.append("_no coverage-band shortlist — HTF forced pairs still queued_")
    else:
        lines += [
            "| source | condition=bucket | n | cov | WR lift | avg lift | inc N/S |",
            "|---|---|---:|---:|---:|---:|---:|",
        ]
        for _, r in short.iterrows():
            lines.append(
                "| %s | %s=%s | %d | %.0f%% | %+.1fpp | %+.0f | %.2f |"
                % (
                    r.get("source", "shortlist"),
                    r["condition"],
                    r["bucket"],
                    r["n"],
                    100 * float(r["coverage"]),
                    float(r["wr_lift_pp"]),
                    float(r["avg_lift"]),
                    float(r["inc_ns"]),
                )
            )

    lines += [
        "",
        "## HTF bucket lifts",
        "",
        "| condition=bucket | n | cov | WR lift | avg lift | inc N/S |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for _, r in htf.iterrows():
        lines.append(
            "| %s=%s | %d | %.0f%% | %+.1fpp | %+.0f | %.2f |"
            % (
                r["condition"],
                r["bucket"],
                r["n"],
                100 * float(r["coverage"]),
                float(r["wr_lift_pp"]),
                float(r["avg_lift"]),
                float(r["inc_ns"]),
            )
        )

    lines += ["", "## Notables (dual-lift heuristic)", ""]
    if notables:
        lines += [
            "| condition=bucket | n | WR lift | avg lift | z_WR |",
            "|---|---:|---:|---:|---:|",
        ]
        for r in notables[:15]:
            lines.append(
                "| %s=%s | %d | %+.1fpp | %+.0f | %.2f |"
                % (r["condition"], r["bucket"], r["n"], r["wr_lift_pp"], r["avg_lift"], r["z_wr"])
            )
    else:
        lines.append("_none_")

    lines += [
        "",
        "## Stance (profile only)",
        "",
        "Diagnostic. Null suite @ 1.25× decides validation. Does **not** rewrite futures LIVE_PLAN.",
        "Null pairs: %d → `live/state/es_quarterly_breakout_hp_nulls/`" % len(pairs),
        "",
    ]
    summary = "\n".join(lines)
    (hub / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (hub / "ES_QB_HP_REPORT.md").write_text(summary, encoding="utf-8")

    email_body = "\n".join(
        [
            "potions: ES quarterly breakout HP profile",
            "hub: live/state/es_quarterly_breakout_hp_profile/",
            "n=%d net=%+.0f N/S=%.2f WR=%.1f%%"
            % (baseline["n"], baseline["net"], baseline["ns"], 100 * baseline["wr"]),
            "null pairs: %d" % len(pairs),
            "",
        ]
        + ["  %s | %s=%s" % p for p in pairs]
    )
    (hub / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    if email:
        send_email(subject="potions: ES quarterly breakout HP profile complete", body=email_body)

    progress("PROFILE DONE pairs=%d" % len(pairs), hub=hub)
    return hub, short, pairs


def run_null_suite(pairs: Sequence[Tuple[str, str, str]], *, email: bool = False) -> Path:
    NULLS_HUB.mkdir(parents=True, exist_ok=True)
    progress("NULLS START n_pairs=%d" % len(pairs), hub=NULLS_HUB)
    run_nulls(
        email=email,
        pairs_override=list(pairs),
        hub_override=NULLS_HUB.resolve(),
        profile_hub=PROFILE_HUB.resolve(),
        write_plan=False,
    )
    progress("NULLS DONE", hub=NULLS_HUB)
    return NULLS_HUB


def _stance_from_decisions(dec: pd.DataFrame) -> str:
    if dec.empty or "decision" not in dec.columns:
        return "PENDING"
    ds = dec["decision"].astype(str)
    if (ds == "SIZE-UP VALIDATED").any():
        return "SIZE-UP VALIDATED"
    if ds.str.contains("PROVISIONAL|BORDERLINE", regex=True).any():
        return "PROVISIONAL PAPER"
    if ds.str.contains("THROTTLE|RISK", regex=True).any():
        return "RISK THROTTLE"
    return "NOT VALIDATED"


def write_final_report(*, email: bool = False) -> Path:
    hub = PROFILE_HUB
    nulls = NULLS_HUB
    base = json.loads((hub / "baselines.json").read_text(encoding="utf-8"))[BOOK_KEY]
    htf = pd.read_csv(hub / "htf_buckets.csv") if (hub / "htf_buckets.csv").exists() else pd.DataFrame()
    short = pd.read_csv(hub / "shortlist.csv") if (hub / "shortlist.csv").exists() else pd.DataFrame()
    dec = pd.read_csv(nulls / "pair_decisions.csv") if (nulls / "pair_decisions.csv").exists() else pd.DataFrame()
    stance = _stance_from_decisions(dec)

    lines = [
        "# ES quarterly breakout — HP + HTF study",
        "",
        "Hubs:",
        "- Profile: `live/state/es_quarterly_breakout_hp_profile/`",
        "- Nulls @1.25×: `live/state/es_quarterly_breakout_hp_nulls/` (LIVE_PLAN not rewritten)",
        "",
        "Book: `%s` (n=%d, net=%+.0f, path N/S=%.2f, tracker N/S=5.59)."
        % (BOOK_KEY, base["n"], base["net"], base["ns"]),
        "",
        "## Stance",
        "",
        "**%s**" % stance,
        "",
        "## Null decisions @1.25×",
        "",
    ]
    if dec.empty:
        lines.append("_none_")
    else:
        lines += [
            "| decision | condition=bucket | hp% | ΔN/S | p_master |",
            "|---|---|---:|---:|---:|",
        ]
        for _, r in dec.iterrows():
            lines.append(
                "| %s | %s=%s | %.1f | %+.2f | %.3f |"
                % (
                    r["decision"],
                    r["condition"],
                    r["bucket"],
                    float(r.get("hp_pct", 0) or 0),
                    float(r.get("delta_ns", 0) or 0),
                    float(r.get("p_master", 1) or 1),
                )
            )

    lines += [
        "",
        "## HTF diagnostics",
        "",
        "| condition=bucket | n | cov | WR lift | avg lift |",
        "|---|---:|---:|---:|---:|",
    ]
    for _, r in htf.iterrows():
        lines.append(
            "| %s=%s | %d | %.0f%% | %+.1fpp | %+.0f |"
            % (
                r["condition"],
                r["bucket"],
                r["n"],
                100 * float(r["coverage"]),
                float(r["wr_lift_pp"]),
                float(r["avg_lift"]),
            )
        )

    if not short.empty:
        lines += [
            "",
            "## Coverage-band / forced shortlist",
            "",
            "| source | condition=bucket | n | avg lift | inc N/S |",
            "|---|---|---:|---:|---:|",
        ]
        for _, r in short.iterrows():
            lines.append(
                "| %s | %s=%s | %d | %+.0f | %.2f |"
                % (r.get("source", ""), r["condition"], r["bucket"], r["n"], r["avg_lift"], r["inc_ns"])
            )

    lines += [
        "",
        "## Takeaway",
        "",
        "Quarterly breakout remains a strong **baseline** book (tracker N/S 5.59).",
        "HP size-up needs null-suite pass on ΔN/S. HTF regime tags are often wide-coverage",
        "and may stay diagnostic even when WR lifts in-sample.",
        "",
        "Definitions: `HTF_FEATURES.md`.",
        "",
    ]
    text = "\n".join(lines)
    (hub / "ES_QB_HP_REPORT.md").write_text(text, encoding="utf-8")
    (nulls / "SUMMARY.md").write_text(text, encoding="utf-8")

    body_lines = [
        "potions: ES quarterly breakout HP complete",
        "stance: %s" % stance,
        "profile: live/state/es_quarterly_breakout_hp_profile/",
        "nulls: live/state/es_quarterly_breakout_hp_nulls/",
        "baseline: n=%d net=%+.0f N/S=%.2f" % (base["n"], base["net"], base["ns"]),
        "",
    ]
    if not dec.empty:
        keep = [c for c in ("decision", "condition", "bucket") if c in dec.columns]
        body_lines.append(dec[keep].to_string(index=False))
    body = "\n".join(body_lines) + "\n"
    (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
    (nulls / "EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(subject="potions: ES quarterly breakout HP complete — %s" % stance, body=body)
    return hub


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--nulls-only", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)

    try:
        if args.email and not args.nulls_only:
            send_email(
                subject="potions: ES quarterly breakout HP STARTED",
                body=(
                    "Study: ES quarterly range breakout HP + HTF\n"
                    "Profile hub: live/state/es_quarterly_breakout_hp_profile/\n"
                    "Nulls hub: live/state/es_quarterly_breakout_hp_nulls/\n"
                    "HTF: yearly ORB, monthly OR, prior-quarter type, weekly ATR align\n"
                ),
            )

        pairs: List[Tuple[str, str, str]]
        if not args.nulls_only:
            _, _, pairs = run_profile(email=False)
        else:
            pairs = [tuple(x) for x in json.loads((PROFILE_HUB / "null_pairs.json").read_text())]

        if args.profile_only:
            if args.email:
                send_email(
                    subject="potions: ES quarterly breakout HP profile complete",
                    body=(PROFILE_HUB / "EMAIL.txt").read_text(encoding="utf-8"),
                )
            return 0

        if not pairs:
            raise RuntimeError("no null pairs")
        run_null_suite(pairs, email=False)
        write_final_report(email=args.email)
        return 0
    except Exception:
        tb = traceback.format_exc()
        print(tb, flush=True)
        if args.email:
            send_email(subject="potions: ES quarterly breakout HP FAILED", body=tb[-4000:])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
