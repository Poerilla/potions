"""FX / metals / CFD width-aware intraday condition profile (Phase 1).

Futures-parity HP pipeline for non-futures books: calendar + width/structure +
quarterly-breakout HTF tags. Shortlists ≤3 candidates/book for Phase 2 nulls.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.fx_metals_cfd_intraday_condition_profile_v1 --email
  python -m live.fx_metals_cfd_intraday_condition_profile_v1 --book eurusd_st_pmc_3r --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Dict, List, Sequence

import pandas as pd

from .fx_metals_cfd_intraday_condition_profile_lib import (
    CAUSAL_LIVE_READY,
    COND_COL,
    CONDITION_COLS,
    DEFAULT_BOOKS,
    MIN_N,
    NEEDS_LIVE_PROXY,
    PROFILE_HUB,
    STUDY,
    annotate_campaigns,
    feature_family,
    load_campaigns,
)
from .futures_intraday_condition_profile import (
    HP_COV_HI,
    HP_COV_LO,
    profile_book,
    shortlist_candidates,
)
import live.futures_intraday_condition_profile as _ficp
from .notify_email import send_email

PLAN_PATH = PROFILE_HUB / "PLAN.md"


def render_profile(
    books_meta: list,
    baselines: Dict[str, dict],
    notables: List[dict],
    short: pd.DataFrame,
    matrix: pd.DataFrame,
) -> str:
    lines = [
        "# FX / metals / CFD intraday condition profile (width-aware)",
        "",
        "Study: `%s`" % STUDY,
        "",
        "Phase **1** — diagnostic + shortlist for 1.25× HP nulls (Phase 2).",
        "See [`PLAN.md`](PLAN.md) for full rollout including **quarterly breakout**.",
        "",
        "## Books",
        "",
        "| book | symbol | family | campaigns | baseline net | N/S |",
        "|---|---|---|---:|---:|---:|",
    ]
    for b in books_meta:
        base = baselines.get(b["key"], {})
        lines.append(
            "| %s | %s | %s | %d | %+.0f | %.2f |"
            % (
                b["key"],
                b["symbol"],
                b["family"],
                b.get("n_campaigns", 0),
                base.get("net", 0),
                base.get("ns", 0),
            )
        )
    lines.extend(["", "## Shortlisted candidates (≤3/book, ≤1/family, cov 5–35%)", ""])
    if short is None or short.empty:
        lines.append("_none_")
    else:
        lines.append("| book | condition=bucket | fam | cov | n | avg lift | inc N/S | z_WR |")
        lines.append("|---|---|---|---:|---:|---:|---:|---:|")
        for _, r in short.iterrows():
            lines.append(
                "| %s | %s=%s | %s | %.0f%% | %d | %+.0f | %.2f | %.2f |"
                % (
                    r["book"],
                    r["condition"],
                    r["bucket"],
                    r.get("family", feature_family(str(r["condition"]))),
                    100 * r["coverage"],
                    r["n"],
                    r["avg_lift"],
                    r["inc_ns"],
                    r["z_wr"],
                )
            )
    lines.extend(["", "## Width / HTF notables (positive dual-lift)", ""])
    width_titles = {
        "Prior-day range percentile",
        "ATR causal rolling percentile",
        "Prior-quarter range width",
        "London OR width vs ATR",
        "Monday session range vs ATR",
        "Yearly ORB direction",
        "Monthly OR direction",
        "Prior quarter type",
        "Weekly ATR trend vs trade",
    }
    w_notes = [n for n in notables if n.get("condition") in width_titles]
    if not w_notes:
        lines.append("_none cleared n≥%d heuristic_" % MIN_N)
    else:
        for n in sorted(w_notes, key=lambda x: (-x.get("avg_lift", 0), -x.get("wr_lift_pp", 0)))[:20]:
            lines.append(
                "- **%s** `%s=%s` n=%d WR lift %+0.1fpp avg lift $%+.0f inc N/S=%.2f"
                % (
                    n["book"],
                    n["condition"],
                    n["bucket"],
                    n["n"],
                    n.get("wr_lift_pp", 0),
                    n.get("avg_lift", 0),
                    n.get("inc_ns", 0),
                )
            )
    lines.extend(
        [
            "",
            "## Next (Phase 2)",
            "",
            "Run matched-added-exposure nulls on shortlist into `%s`." % (
                "live/state/fx_metals_cfd_intraday_hp_sizeup_nulls/"
            ),
            "Quarterly breakout books: prioritize `Prior-quarter range width` and HTF tags.",
            "",
            "## Caveats",
            "",
            "- Multiple comparisons — profile lift is hypothesis only.",
            "- Quarterly breakout uses daily entries; min bucket N may be lower on thin books.",
            "- ATR quartile in legacy profile is static; rolling `atr_pct_bucket` is preferred for HP.",
            "",
        ]
    )
    return "\n".join(lines)


def write_plan() -> None:
    text = """# FX / metals / CFD HP size-up — research plan

Study: `fx_metals_cfd_intraday_condition_profile_v1`

Futures received a full **width-aware condition profile → HP shortlist → matched-null
validation** pipeline. This plan brings FX, index CFDs, metals, and **quarterly
range breakout** to the same standard.

Hub layout:

| Phase | Hub | Driver |
|-------|-----|--------|
| 1 — profile | `live/state/fx_metals_cfd_intraday_condition_profile/` | `fx_metals_cfd_intraday_condition_profile_v1` |
| 2 — nulls | `live/state/fx_metals_cfd_intraday_hp_sizeup_nulls/` | TBD (`intraday_hp_sizeup_nulls` fork) |
| 3 — deploy | `live/state/fx_metals_cfd_intraday_hp_live_plan/` | LIVE_PLAN after null pass |

## Book universe

| Family | Books | Width / structure features |
|--------|-------|---------------------------|
| Monday OR | EURUSD, USDJPY, US30, GBPUSD, AUDJPY, XAUUSD | Monday range vs 60d pct; prior-day range pct |
| v2b / London | EURUSD, NAS100, US30 prior-opposed | London OR width vs ATR; prior-day range pct |
| Asia-range | USDJPY S_3_1_3 | London OR width; prior-day range pct |
| ST+PMC 3R | EURUSD, GBPUSD, USDJPY, AUDJPY, NAS100, US30, XAUUSD, XAGUSD | Prior-day range pct; rolling ATR pct |
| **Quarterly breakout** | EURUSD, GBPUSD, USDJPY, AUDJPY, XAUUSD, XAGUSD, US30, NAS100 | **Prior-quarter range width Q1–Q4**; YOR/MOR/prior-Q type; weekly ATR align |

Baseline tapes: broker-like research fills under `live/state/` (not thin live demo tapes).

## Phase 1 — width-aware condition profile ✅

```bash
python -m live.fx_metals_cfd_intraday_condition_profile_v1 --email
```

Deliverables:

- Annotated `*_campaigns.csv` with calendar + width + HTF columns
- `condition_matrix.csv`, `shortlist.csv` (≤3/book, cov 5–35%, dual lift)
- `COND_COL` map in `fx_metals_cfd_intraday_condition_profile_lib.py`

**Quarterly breakout** is first-class in Phase 1 (not a siloed prior_width_study only).
Existing Q4_large toxicity on EURUSD is a hypothesis to test under nulls — not a live gate.

## Phase 2 — HP nulls on width shortlist

Same ΔN/S gate stack as `intraday_hp_sizeup_nulls.py`:

- Matched placebo (never stratify on test feature)
- Clustered timing shift
- Selection-aware master null
- Nested walk-forward; coverage ≤35%

Priority pairs (analogous to futures NQ `or_norm`):

| Family | First null candidates |
|--------|----------------------|
| Monday OR | `Monday session range vs ATR` narrow/norm/wide |
| ST+PMC | `Prior-day range percentile` + `ATR causal rolling percentile` |
| v2b / London | `London OR width vs ATR` |
| **Quarterly breakout** | `Prior-quarter range width` Q4_large / Q1_small; `Monthly OR direction`; `Prior quarter type` |

```bash
# Phase 2 (after shortlist review)
python -m live.fx_metals_cfd_intraday_hp_sizeup_nulls --priority-1-25 --email
```

## Phase 3 — deployment plan

Only after nulls pass — same tier rules as futures:

- **Tier A** — SIZE-UP VALIDATED @ 1.25×
- **Tier B** — provisional paper (0.05 < p_master ≤ 0.10)
- **Tier C** — shadow / risk throttle only

Do **not** promote from profile lift alone. Quarterly breakout baseline books may stay
ungated even when width filters look good in-sample (see ES MOR-up NOT VALIDATED precedent).

Portfolio rules (draft):

- At most one HP multiplier per symbol sleeve per session/day.
- Quarterly breakout: no stacking with intraday HP on same symbol without overlap pass.
- Metals ST+PMC books may be thin — require n≥40 in profile bucket before null queue.

## Expectations

- Width can help (futures NQ `or_norm`) or fail strict nulls (ES/YM width demoted).
- EURUSD quarterly Q4_large loses money on baseline tape — width is book-specific.
- XAGUSD ST+PMC is very thin; profile may not clear n≥40.

## References

- Futures pipeline: `live/state/futures_intraday_condition_profile/`
- Quarterly baseline: `live/state/quarterly_range_breakout_fx_metals_cfd/`
- ES quarterly HP precedent: `live/state/es_quarterly_breakout_hp_profile/`
"""
    PLAN_PATH.parent.mkdir(parents=True, exist_ok=True)
    PLAN_PATH.write_text(text, encoding="utf-8")


def run(books: Sequence, *, email: bool = False, min_n: int = MIN_N) -> Path:
    hub = PROFILE_HUB
    hub.mkdir(parents=True, exist_ok=True)
    write_plan()

    _saved_cols = _ficp.CONDITION_COLS
    _ficp.CONDITION_COLS = CONDITION_COLS
    try:
        all_campaigns = []
        matrices = []
        notables: List[dict] = []
        baselines: Dict[str, dict] = {}
        books_meta = []
        causal_audit_rows = []
        feat_cache = {}

        for book in books:
            print("BOOK %s ..." % book.key, flush=True)
            if not book.fills.exists():
                print("  SKIP missing fills %s" % book.fills, flush=True)
                continue
            try:
                camp = load_campaigns(book)
            except KeyError:
                print("  SKIP empty/malformed campaign tape", flush=True)
                continue
            if camp.empty:
                print("  empty campaigns — skip", flush=True)
                continue
            print("  campaigns=%d — annotating ..." % len(camp), flush=True)
            if book.symbol not in feat_cache:
                from .intraday_condition_profile import build_feature_frames

                feat_cache[book.symbol] = build_feature_frames(book.symbol)
            ann = annotate_campaigns(camp, book.symbol, family=book.family, feats=feat_cache[book.symbol])
            ann.to_csv(hub / ("%s_campaigns.csv" % book.key), index=False)
            all_campaigns.append(ann)

            for col, title in CONDITION_COLS:
                if col not in ann.columns:
                    continue
                causal_audit_rows.append(
                    {
                        "book": book.key,
                        "family": book.family,
                        "condition": title,
                        "feature_col": col,
                        "n": int(ann[col].notna().sum()),
                        "n_unique": int(ann[col].astype(str).nunique()),
                        "causal_live_ready": title in CAUSAL_LIVE_READY,
                        "needs_proxy": title in NEEDS_LIVE_PROXY,
                        "family_tag": feature_family(title),
                    }
                )

            book_min_n = 20 if book.family == "quarterly_breakout" else min_n
            table, baseline, book_notables = profile_book(ann, min_n=book_min_n)
            baseline["book"] = book.key
            baselines[book.key] = baseline
            table.to_csv(hub / ("%s_buckets.csv" % book.key), index=False)
            matrices.append(table)
            notables.extend(book_notables)
            books_meta.append(
                {
                    "key": book.key,
                    "symbol": book.symbol,
                    "family": book.family,
                    "n_campaigns": len(ann),
                }
            )
            print(
                "  baseline net=%+.0f N/S=%.2f notables=%d"
                % (baseline["net"], baseline["ns"], len(book_notables)),
                flush=True,
            )

        if not all_campaigns:
            raise RuntimeError("no campaigns loaded")

        campaigns = pd.concat(all_campaigns, ignore_index=True)
        campaigns.to_csv(hub / "all_campaigns.csv", index=False)
        matrix = pd.concat(matrices, ignore_index=True) if matrices else pd.DataFrame()
        matrix.to_csv(hub / "condition_matrix.csv", index=False)
        pd.DataFrame(notables).to_csv(hub / "notables.csv", index=False)
        pd.DataFrame(causal_audit_rows).to_csv(hub / "causal_feature_audit.csv", index=False)

        short, ledger = shortlist_candidates(matrix, baselines, max_per_book=3)
        if not ledger.empty:
            ledger.to_csv(hub / "candidate_ledger.csv", index=False)
        if not short.empty:
            short.to_csv(hub / "shortlist.csv", index=False)

        (hub / "baselines.json").write_text(json.dumps(baselines, indent=2), encoding="utf-8")
        (hub / "BOOKS.json").write_text(
            json.dumps({"study": STUDY, "books": books_meta}, indent=2),
            encoding="utf-8",
        )
        (hub / "COND_COL.json").write_text(json.dumps(COND_COL, indent=2), encoding="utf-8")

        summary = render_profile(books_meta, baselines, notables, short, matrix)
        (hub / "SUMMARY.md").write_text(summary, encoding="utf-8")
        (hub / "PROFILE.md").write_text(summary, encoding="utf-8")

        email_lines = [
            "potions: fx_metals_cfd_intraday_condition_profile_v1 complete",
            "Hub: %s" % hub,
            "Books: %d" % len(books_meta),
            "Shortlist: %d candidates" % (0 if short is None or short.empty else len(short)),
            "Plan: %s" % PLAN_PATH,
            "",
        ]
        if short is not None and not short.empty:
            for _, r in short.head(15).iterrows():
                email_lines.append(
                    "%s | %s=%s | cov=%.0f%% incN/S=%.2f"
                    % (r["book"], r["condition"], r["bucket"], 100 * r["coverage"], r["inc_ns"])
                )
        qb_short = (
            short[short["book"].astype(str).str.contains("quarterly")]
            if short is not None and not short.empty
            else pd.DataFrame()
        )
        if not qb_short.empty:
            email_lines.append("")
            email_lines.append("Quarterly breakout shortlist:")
            for _, r in qb_short.iterrows():
                email_lines.append("  %s | %s=%s" % (r["book"], r["condition"], r["bucket"]))
        email_lines.append("")
        email_lines.append("Phase 2: nulls on shortlist (see PLAN.md).")
        body = "\n".join(email_lines)
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        if email:
            send_email(subject="potions: FX/metals/CFD width profile complete", body=body)
        print("wrote %s" % (hub / "SUMMARY.md"), flush=True)
        return hub / "SUMMARY.md"
    finally:
        _ficp.CONDITION_COLS = _saved_cols


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--book", action="append", default=[], help="Book key (repeatable)")
    parser.add_argument("--email", action="store_true")
    parser.add_argument("--min-n", type=int, default=25, help="Min bucket N for intraday books (quarterly uses 20)")
    args = parser.parse_args(argv)
    books = DEFAULT_BOOKS
    if args.book:
        wanted = set(args.book)
        books = tuple(b for b in DEFAULT_BOOKS if b.key in wanted)
        missing = wanted - {b.key for b in books}
        if missing:
            raise SystemExit("unknown books: %s" % sorted(missing))
    hub = PROFILE_HUB
    try:
        run(books, email=bool(args.email), min_n=int(args.min_n))
        return 0
    except Exception:
        tb = traceback.format_exc()
        hub.mkdir(parents=True, exist_ok=True)
        (hub / "FAIL.txt").write_text(tb, encoding="utf-8")
        if args.email:
            send_email(subject="potions: FX/metals/CFD width profile FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
