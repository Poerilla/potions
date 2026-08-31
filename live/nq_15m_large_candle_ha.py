"""HA mill for NQ 15m large-candle books + prior-opposed v2b overlay.

HA = high-probability *conditions* (same mill as midnight-open / futures HP).
Not Heikin Ashi. 15-minute analogue of ``nq_5m_large_candle_ha``.

Default sleeve is p90. Pass ``--hi 99 --lo 95`` for the tail sleeve (fallback
to p95 when p99 days/events are too rare).

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_15m_large_candle_ha --email
  python -m live.nq_15m_large_candle_ha --email --hi 99 --lo 95
  python -m live.nq_15m_large_candle_ha --email --smoke
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email
from .nq_15m_large_candle_study import ENTRY_CUTOFF, MIN_WARMUP
from .nq_5m_large_candle_study import (
    choose_pct_sleeve,
    classify,
    day_coverage,
    load_rth_5m,
    pct_name,
    resample_rth,
    summarize_book,
    walk_trades,
)
from .nq_large_candle_ha_lib import (
    PO_CONDS,
    annotate_campaigns,
    attach_po_context,
    attach_trade_po_labels,
    compare_current_hp,
    load_po_campaigns,
    po_buckets_table,
    profile_frame,
    trades_to_campaigns,
    write_ha_report,
)

HUB = REPO / "live" / "state" / "nq_15m_large_candle_ha"
FAMILY = "nq_15m_large_candle"
MIN_N = 40


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def run(*, email: bool, smoke: bool, hi: int = 90, lo: int = 80, output_root: Optional[Path] = None) -> None:
    global HUB
    hi_name = pct_name(hi)
    lo_name = pct_name(lo)
    if output_root is not None:
        HUB = Path(output_root)
    elif hi_name != "p90":
        HUB = REPO / "live" / "state" / ("nq_15m_large_candle_ha_%s" % hi_name)
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    try:
        _progress("load 5m → 15m ...")
        bars5 = load_rth_5m(progress=False)
        bars = resample_rth(bars5, 15)
        if smoke:
            dates = bars["session_date"].drop_duplicates()
            keep = set(dates.tail(400))
            bars = bars[bars["session_date"].isin(keep)].reset_index(drop=True)
            _progress("SMOKE bars=%s" % f"{len(bars):,}")
        extra = [] if hi_name == "p90" and lo_name == "p80" else [hi / 100.0 if hi > 1 else hi, lo / 100.0 if lo > 1 else lo]
        bars = classify(bars, min_warmup=MIN_WARMUP, extra_qs=extra)
        ready_col = "%s_thr" % hi_name
        if ready_col not in bars.columns:
            ready_col = "p90_thr"
        ready = bars[bars[ready_col].notna()].copy()
        cov = day_coverage(ready)
        flag, sleeve_meta = choose_pct_sleeve(cov, hi_name, lo_name)
        _progress(
            "sleeve %s (%s)  %s days=%.1f%% bars=%d"
            % (flag, sleeve_meta["reason"], hi_name, 100 * sleeve_meta["hi_day_frac"], sleeve_meta["n_hi_bars"])
        )
        po = load_po_campaigns(_progress)
        if smoke:
            po = po[po["session_date"].isin(set(ready["session_date"]))].copy()
        ready = attach_po_context(ready, po, p90_col=flag, progress=_progress)

        hi_flag = "is_%s" % hi_name
        lo_flag = "is_%s" % lo_name
        books_walk = [
            ("follow_3r", "follow 3R %s" % hi_name, hi_flag, 3.0, False),
            ("fade_3r", "fade 3R %s" % hi_name, hi_flag, 3.0, True),
            ("follow_1r", "follow 1R %s" % hi_name, hi_flag, 1.0, False),
            ("fade_1r", "fade 1R %s" % hi_name, hi_flag, 1.0, True),
            ("follow_3r_lo", "follow 3R %s" % lo_name, lo_flag, 3.0, False),
            ("fade_3r_lo", "fade 3R %s" % lo_name, lo_flag, 3.0, True),
        ]
        hp_walk = [
            ("hp_during_fade_st_3r", "during fade-ST 3R", "hp_during_fade_st", 3.0, True),
            ("hp_during_fade_st_1r", "during fade-ST 1R", "hp_during_fade_st", 1.0, True),
            ("hp_during_any_fade_1r", "during any fade 1R", "hp_during_any", 1.0, True),
            ("hp_after_follow_st_3r", "after follow-ST 3R", "hp_after_follow_st", 3.0, False),
            ("hp_after_follow_st_1r", "after follow-ST 1R", "hp_after_follow_st", 1.0, False),
            ("hp_after_loss_follow_st_1r", "after-loss follow-ST 1R", "hp_after_loss_follow_st", 1.0, False),
            ("hp_after_win_fade_st_1r", "after-win fade-ST 1R", "hp_after_win_fade_st", 1.0, True),
        ]

        walked: Dict[str, pd.DataFrame] = {}
        core_sum: List[dict] = []
        hp_sum: List[dict] = []
        for key, label, flag, r, fade in books_walk + hp_walk:
            _progress("walk %s ..." % key)
            tr = walk_trades(ready, flag, r_mult=r, fade=fade, entry_cutoff=ENTRY_CUTOFF)
            walked[key] = tr
            if not tr.empty:
                tr.to_csv(HUB / ("trades_%s.csv" % key), index=False)
            _progress("  %s n=%d" % (key, len(tr)))
            sc = summarize_book(tr, label)
            if (key, label, flag, r, fade) in books_walk:
                core_sum.append(sc)
            else:
                hp_sum.append(sc)

        annotated: Dict[str, pd.DataFrame] = {}
        notables_by_book: Dict[str, List[dict]] = {}
        for key, label, _, _, _ in books_walk:
            tr = walked[key]
            _progress("annotate %s n=%d ..." % (key, len(tr)))
            camp = trades_to_campaigns(tr, key, FAMILY)
            if camp.empty:
                annotated[key] = camp
                notables_by_book[key] = []
                continue
            camp = annotate_campaigns(camp, "NQ")
            camp = attach_trade_po_labels(camp, ready)
            camp.to_csv(HUB / ("%s_campaigns.csv" % key), index=False)
            table, _base, notables = profile_frame(camp, PO_CONDS, MIN_N)
            if not table.empty:
                table.to_csv(HUB / ("%s_buckets.csv" % key), index=False)
            annotated[key] = camp
            notables_by_book[key] = notables
            _progress("  notables=%d" % len(notables))

        current_cmp = compare_current_hp(annotated, po_buckets_table())
        if not current_cmp.empty:
            current_cmp.to_csv(HUB / "vs_current_hp.csv", index=False)

        pd.DataFrame(core_sum + hp_sum).to_csv(HUB / "books.csv", index=False)
        write_ha_report(
            HUB,
            title="NQ 15m large-candle HA (high-probability conditions, %s/%s)" % (hi_name, lo_name),
            universe=(
                "Universe: NQ RTH 09:30–16:00 **15m**, **%s range** candles "
                "(causal expanding threshold, resampled from 5m). Fallback **%s** if %s is too rare (%s)."
                % (hi_name, lo_name, hi_name, sleeve_meta.get("reason", ""))
            ),
            email_subject="potions: NQ 15m large-candle HA complete (%s/%s)" % (hi_name, lo_name),
            core=core_sum,
            hp_sleeves=hp_sum,
            notables_by_book=notables_by_book,
            current_cmp=current_cmp,
            po_n=int(len(po)),
        )
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "smoke": smoke,
                    "po_n": int(len(po)),
                    "hi": hi_name,
                    "lo": lo_name,
                    "flag": flag,
                    "sleeve": sleeve_meta,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _progress("DONE")
    except Exception:
        err = traceback.format_exc()
        _progress("CRASH\n%s" % err)
        (HUB / "EMAIL.txt").write_text(
            "potions: NQ 15m large-candle HA FAILED\n\nHub: %s\n\n%s\n" % (HUB, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: NQ 15m large-candle HA FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise

    if email:
        send_email(
            subject="potions: NQ 15m large-candle HA complete (%s/%s)" % (hi_name, lo_name),
            body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress("email sent")


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--hi", type=int, default=90, help="Primary percentile (90 or 99)")
    ap.add_argument("--lo", type=int, default=80, help="Fallback percentile if hi is too rare")
    ap.add_argument("--output-root", type=Path, default=None)
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        hi=int(args.hi),
        lo=int(args.lo),
        output_root=args.output_root,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
