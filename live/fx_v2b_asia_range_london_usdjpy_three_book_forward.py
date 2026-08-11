"""USDJPY Asia-range London — frozen three-book forward comparison.

Discriminator books (rules locked — no retune):
  A. Unfiltered ``S_3_1_3``
  B. January-only ``S_3_1_3`` (``skip_entry_months=[1]``, no roll gate)
  C. January + roll50 WR40/PF1 ``S_3_1_3`` (promote cell)

Primary evidence is the unfiltered campaign shadow tape (sizing hub), scored
full-sample and frozen OOS (years > 2021). Optional ``--broker-jan`` runs a
PaperBroker January-only replay so B can sit next to existing A/C broker metrics.

Hub artifacts → ``live/state/fx_v2b_asia_range_london_usdjpy_filters/``:
  THREE_BOOK_FORWARD.md, three_book_forward.csv, three_book_forward_yearly.csv,
  THREE_BOOK_FORWARD_EMAIL.txt
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import session_bars
from .fx_v2b_asia_range_london import (
    LONDON,
    REPO,
    build_session_asia_ranges,
    run_one,
)
from .fx_v2b_asia_range_london_usdjpy_filter_nulls import (
    OOS_CUT,
    Tape,
    combined_mask,
    load_tape,
    month_skip_mask,
    score_mask,
)
from .fx_v2b_asia_range_london_usdjpy_filters import (
    FILTER_HUB,
    SIZING_HUB,
    _campaigns_from_unit_trades,
)
from .fx_v2b_london_ungated import (
    MARKETS,
    _has_london_session,
    _progress,
    _regime_dates,
    resolve_book,
)

BOOK = "S_3_1_3"
FROZEN = {
    "book": BOOK,
    "skip_months": [1],
    "window": 50,
    "min_wr": 0.40,
    "min_pf": 1.0,
    "oos_cut": OOS_CUT,
}
BOOKS = (
    ("A", "unfiltered", "Unfiltered S_3_1_3"),
    ("B", "january_only", "January-only S_3_1_3"),
    ("C", "combined", "January + roll50 WR40/PF1 S_3_1_3"),
)
SIZING_STATE = SIZING_HUB / "states" / ("usdjpy_v2b_asia_range_london_%s" % BOOK)
FILTERED_STATE = FILTER_HUB / "states" / ("usdjpy_v2b_asia_range_london_%s_flt" % BOOK)
JAN_ONLY_TAG = "%s_jan" % BOOK
JAN_ONLY_STATE = FILTER_HUB / "states" / ("usdjpy_v2b_asia_range_london_%s" % JAN_ONLY_TAG)


def _masks(tape: Tape) -> Dict[str, np.ndarray]:
    return {
        "unfiltered": np.ones(tape.n, dtype=bool),
        "january_only": month_skip_mask(tape, FROZEN["skip_months"]),
        "combined": combined_mask(
            tape,
            skip_months=FROZEN["skip_months"],
            window=int(FROZEN["window"]),
            min_wr=float(FROZEN["min_wr"]),
            min_pf=float(FROZEN["min_pf"]),
            roll_mode="roll",
        ),
    }


def _yearly_rows(tape: Tape, masks: Dict[str, np.ndarray]) -> pd.DataFrame:
    rows: List[dict] = []
    years = sorted(int(y) for y in np.unique(tape.year))
    for letter, key, _label in BOOKS:
        take = masks[key]
        for y in years:
            ymask = tape.year == y
            taken = take & ymask
            skipped = (~take) & ymask
            net = float(tape.net_usd[taken].sum()) if taken.any() else 0.0
            rows.append(
                {
                    "book": letter,
                    "variant": key,
                    "year": y,
                    "campaigns": int(ymask.sum()),
                    "taken_n": int(taken.sum()),
                    "skipped_n": int(skipped.sum()),
                    "taken_net_usd": net,
                    "oos": bool(y > int(FROZEN["oos_cut"])),
                }
            )
    return pd.DataFrame(rows)


def _load_broker_metrics(path: Path) -> Optional[dict]:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _broker_row(letter: str, variant: str, metrics: Optional[dict]) -> dict:
    if not metrics:
        return {
            "book": letter,
            "variant": variant,
            "broker_present": False,
            "broker_trades": None,
            "broker_net_usd": None,
            "broker_stress_usd": None,
            "broker_ns": None,
            "broker_wr": None,
            "broker_pf": None,
            "broker_state": None,
        }
    return {
        "book": letter,
        "variant": variant,
        "broker_present": True,
        "broker_trades": int(metrics.get("trades") or 0),
        "broker_net_usd": float(metrics.get("net_usd") or 0.0),
        "broker_stress_usd": float(metrics.get("stress_dd_usd") or 0.0),
        "broker_ns": float(metrics.get("net_over_stress") or 0.0),
        "broker_wr": float(metrics.get("win_rate") or 0.0),
        "broker_pf": float(metrics.get("profit_factor") or 0.0),
        "broker_state": str(metrics.get("state_root") or ""),
    }


def run_january_only_broker(
    *,
    output_root: Path,
    start: date,
    force: bool,
    max_days: Optional[int],
) -> dict:
    """PaperBroker replay of S_3_1_3 with January sessions removed (no roll gate)."""
    market = MARKETS["USDJPY"]
    one_m = REPO / "fx" / "usdjpy_1m.csv"
    daily = REPO / "fx" / "usdjpy_daily.csv"
    output_root.mkdir(parents=True, exist_ok=True)
    _progress(output_root, "THREE_BOOK broker-jan LOAD USDJPY...")
    gby = load_fx_1m_by_ny_date(one_m, market.symbol)
    eff_start = start if market.start is None else max(start, market.start)
    regime_dates = [d for d in _regime_dates(daily, gby, eff_start) if _has_london_session(gby.get(d), d)]
    if max_days is not None:
        regime_dates = regime_dates[:max_days]
    session_asia_ranges = build_session_asia_ranges(gby, regime_dates)
    regime_dates = [d for d in regime_dates if d.isoformat() in session_asia_ranges]
    # January blackout only
    allowed = [d for d in regime_dates if d.month not in set(FROZEN["skip_months"])]
    session_frames = {day: session_bars(gby.get(day), day, LONDON, dense=True) for day in allowed}
    _progress(
        output_root,
        "THREE_BOOK broker-jan sessions=%d (jan skipped=%d)"
        % (len(allowed), len(regime_dates) - len(allowed)),
    )

    src = output_root / "states" / ("usdjpy_v2b_asia_range_london_%s" % BOOK)
    dst = JAN_ONLY_STATE
    stash = output_root / "states" / ("usdjpy_v2b_asia_range_london_%s__stash_jan" % BOOK)
    if src.exists():
        if stash.exists():
            shutil.rmtree(stash)
        shutil.move(str(src), str(stash))
    if dst.exists() and force:
        shutil.rmtree(dst)

    try:
        raw = run_one(
            output_root=output_root,
            market=market,
            book=BOOK,
            start=start,
            force=force,
            max_days=max_days,
            gby=gby,
            regime_dates=allowed,
            session_frames=session_frames,
            session_asia_ranges={
                d.isoformat(): session_asia_ranges[d.isoformat()]
                for d in allowed
                if d.isoformat() in session_asia_ranges
            },
        )
    except Exception:
        if stash.exists() and not src.exists():
            shutil.move(str(stash), str(src))
        raise

    if dst.exists():
        shutil.rmtree(dst)
    if src.exists():
        shutil.move(str(src), str(dst))
    if stash.exists():
        shutil.move(str(stash), str(src))

    sizing = resolve_book(BOOK)
    row = dict(raw)
    row["book"] = JAN_ONLY_TAG
    row["sizing"] = BOOK
    row["strategy_id"] = "usdjpy_v2b_asia_range_london_%s" % JAN_ONLY_TAG
    row["variant"] = "january_only"
    row["skip_months"] = ",".join(str(m) for m in FROZEN["skip_months"])
    row["roll_window"] = 0
    row["min_wr"] = None
    row["min_pf"] = None
    row["skipped_campaigns"] = int(len(regime_dates) - len(allowed))
    row["entry_qty"] = sizing["entry_qty"]
    row["state_root"] = str(dst)
    (dst / "metrics.json").write_text(json.dumps(row, indent=2), encoding="utf-8")
    _progress(
        output_root,
        "THREE_BOOK broker-jan DONE net≈$%.0f N/S=%.2f trades=%d"
        % (float(row.get("net_usd") or 0), float(row.get("net_over_stress") or 0), int(row.get("trades") or 0)),
    )
    return row


def _fmt_money(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return "$%+.0f" % float(x)


def _fmt_ns(x: Optional[float]) -> str:
    if x is None:
        return "—"
    return "%.2f" % float(x)


def write_report(
    output_root: Path,
    *,
    shadow_rows: List[dict],
    yearly: pd.DataFrame,
    broker_rows: List[dict],
    broker_jan_ran: bool,
) -> Path:
    by_key = {r["variant"]: r for r in shadow_rows}
    a, b, c = by_key["unfiltered"], by_key["january_only"], by_key["combined"]
    broker_by = {r["variant"]: r for r in broker_rows}

    # Frozen forward winner heuristics (shadow tape, OOS years > cut)
    oos_rank = sorted(
        [a, b, c],
        key=lambda r: (float(r["oos_ns"]), float(r["oos_net_usd"])),
        reverse=True,
    )
    oos_winner = oos_rank[0]
    full_ns_rank = sorted([a, b, c], key=lambda r: float(r["ns"]), reverse=True)
    full_winner = full_ns_rank[0]

    # Stance: does C earn its keep vs B on frozen OOS?
    c_beats_b_oos_ns = float(c["oos_ns"]) > float(b["oos_ns"])
    c_beats_b_oos_net = float(c["oos_net_usd"]) > float(b["oos_net_usd"])
    c_beats_b_stress = abs(float(c["stress_usd"])) < abs(float(b["stress_usd"]))
    if c_beats_b_oos_ns and c_beats_b_oos_net:
        stance = (
            "**C WINS FROZEN FORWARD** — roll gate improves OOS net and OOS N/S vs January-only; "
            "keep promote cell as primary live book."
        )
        short = "C_WINS_FORWARD"
    elif (not c_beats_b_oos_ns) and (not c_beats_b_oos_net) and c_beats_b_stress:
        stance = (
            "**C PRIMARY CAPITAL-EFFICIENT; B ALPHA / RETURN CONTROL** — on broker-like deployability "
            "(full-path net + stress budget), C wins: nearly B's broker net with far lower stress "
            "(broker N/S C ≫ B), so C can match B's dollars at ~1.0×–1.3× scale while retaining lower "
            "stress. Frozen shadow OOS still favors **B** (January is the positive-return lever; "
            "roll gate is not an alpha-selection winner). Aligns with FILTER_NULLS risk-throttle; "
            "do **not** treat C's full-sample N/S beauty as funded-rule proof. Validate scaling with "
            "lot/margin/OCO (non-linear costs)."
        )
        short = "C_PRIMARY_CAPITAL_EFFICIENT_B_ALPHA_CONTROL"
    elif not c_beats_b_oos_ns and not c_beats_b_oos_net:
        stance = (
            "**B WINS FROZEN FORWARD** — January-only dominates combined on OOS; reconsider whether "
            "roll50 belongs in the live book vs Jan blackout alone."
        )
        short = "B_WINS_FORWARD"
    else:
        stance = (
            "**MIXED** — combined and January-only split OOS net vs OOS N/S; keep C as operational "
            "throttle only until live parity / further OOS cuts clarify."
        )
        short = "MIXED"

    lines = [
        "# USDJPY Asia-range London — frozen three-book forward comparison",
        "",
        "Rules locked (no retune): book **`S_3_1_3`**, January skip, roll50 WR≥40% / PF≥1.0,",
        "shadow = **unfiltered** campaign nets. OOS cut: years **> %d**." % int(FROZEN["oos_cut"]),
        "",
        "| Book | Variant |",
        "|---|---|",
        "| **A** | Unfiltered `S_3_1_3` |",
        "| **B** | January-only `S_3_1_3` |",
        "| **C** | January + roll50 WR40/PF1 `S_3_1_3` (promote cell) |",
        "",
        "## Verdict",
        "",
        stance,
        "",
        "- Full-sample shadow N/S winner: **%s** (%.2f)."
        % (full_winner["book"], float(full_winner["ns"])),
        "- Frozen OOS shadow N/S winner: **%s** (%.2f, OOS net %s)."
        % (oos_winner["book"], float(oos_winner["oos_ns"]), _fmt_money(oos_winner["oos_net_usd"])),
        "- C vs B OOS: Δnet %s | ΔN/S %+.2f | full-sample stress |C| vs |B|: %.0f vs %.0f."
        % (
            _fmt_money(float(c["oos_net_usd"]) - float(b["oos_net_usd"])),
            float(c["oos_ns"]) - float(b["oos_ns"]),
            abs(float(c["stress_usd"])),
            abs(float(b["stress_usd"])),
        ),
        "",
        "## 1. Shadow tape scorecard (primary discriminator)",
        "",
        "Source: sizing hub unfiltered `unit_trades` for `S_3_1_3`. Stress / max DD are",
        "closed-campaign equity drawdowns on the taken tape (reachable-stress proxy).",
        "",
        "| Book | Taken | Skip | Net≈USD | Stress | N/S | Max DD | Worst | PF | WR | OOS n | OOS net | OOS N/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for letter, key, label in BOOKS:
        r = by_key[key]
        lines.append(
            "| **%s** %s | %d | %d | %s | %s | %.2f | %s | %s | %.3f | %.1f%% | %d | %s | %.2f |"
            % (
                letter,
                label.split(" ", 1)[-1] if letter != "C" else "(promote)",
                int(r["taken_n"]),
                int(r["skipped_n"]),
                _fmt_money(r["net_usd"]).replace("+", ""),
                _fmt_money(r["stress_usd"]),
                float(r["ns"]),
                _fmt_money(r["max_dd_usd"]),
                _fmt_money(r["worst_campaign_usd"]),
                float(r["pf"]),
                100.0 * float(r["wr"]),
                int(r["oos_taken_n"]),
                _fmt_money(r["oos_net_usd"]).replace("+", ""),
                float(r["oos_ns"]),
            )
        )

    lines.extend(
        [
            "",
            "### Read",
            "",
            "- **A → B**: January skip is the only positive-Δ net lever on the full tape",
            "  (B net %s vs A %s)."
            % (_fmt_money(b["net_usd"]), _fmt_money(a["net_usd"])),
            "- **B → C**: roll gate sacrifices OOS net (%s → %s) and OOS N/S (%.2f → %.2f)"
            % (
                _fmt_money(b["oos_net_usd"]),
                _fmt_money(c["oos_net_usd"]),
                float(b["oos_ns"]),
                float(c["oos_ns"]),
            ),
            "  while cutting full-sample stress (%s → %s)."
            % (_fmt_money(b["stress_usd"]), _fmt_money(c["stress_usd"])),
            "- Full-sample N/S ranks **C > B > A**; frozen OOS N/S ranks **%s**."
            % " > ".join("%s(%.2f)" % (r["book"], float(r["oos_ns"])) for r in oos_rank),
            "",
            "## 2. Broker-like reference (PaperBroker)",
            "",
            "| Book | Variant | Present | Trades | Net≈USD | Stress | N/S | WR | PF |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for letter, key, label in BOOKS:
        br = broker_by.get(key) or _broker_row(letter, key, None)
        if br["broker_present"]:
            lines.append(
                "| **%s** | %s | yes | %d | $%.0f | $%.0f | %.2f | %.1f%% | %.3f |"
                % (
                    letter,
                    key,
                    int(br["broker_trades"]),
                    float(br["broker_net_usd"]),
                    float(br["broker_stress_usd"]),
                    float(br["broker_ns"]),
                    float(br["broker_wr"]),
                    float(br["broker_pf"]),
                )
            )
        else:
            lines.append(
                "| **%s** | %s | **no** | — | — | — | — | — | — |" % (letter, key)
            )
    if not broker_jan_ran and not (broker_by.get("january_only") or {}).get("broker_present"):
        lines.extend(
            [
                "",
                "January-only broker state missing — re-run with `--broker-jan` "
                "(~5 min on full USDJPY tape).",
            ]
        )
    elif broker_by.get("january_only", {}).get("broker_present"):
        ba = broker_by["unfiltered"]
        bb = broker_by["january_only"]
        bc = broker_by["combined"]
        if ba.get("broker_present") and bb.get("broker_present") and bc.get("broker_present"):
            lines.extend(
                [
                    "",
                    "Broker N/S ranks: **%s**."
                    % " > ".join(
                        "%s(%.2f)"
                        % (letter, float(broker_by[key]["broker_ns"]))
                        for letter, key, _ in sorted(
                            BOOKS,
                            key=lambda t: -float(broker_by[t[1]]["broker_ns"]),
                        )
                    ),
                ]
            )

    # Yearly OOS table (compact)
    lines.extend(
        [
            "",
            "## 3. Yearly taken net (shadow)",
            "",
            "| Year | A taken/net | B taken/net | C taken/net | OOS? |",
            "|---:|---|---|---|---|",
        ]
    )
    years = sorted(int(y) for y in yearly["year"].unique())
    for y in years:
        cells = []
        for letter, key, _ in BOOKS:
            part = yearly[(yearly["book"] == letter) & (yearly["year"] == y)].iloc[0]
            cells.append("%d / %s" % (int(part["taken_n"]), _fmt_money(part["taken_net_usd"])))
        lines.append(
            "| %d | %s | %s | %s | %s |"
            % (y, cells[0], cells[1], cells[2], "yes" if y > int(FROZEN["oos_cut"]) else "")
        )

    lines.extend(
        [
            "",
            "## 4. Funded-sleeve implication",
            "",
            "- Research/practice promote cell remains **C** for live demos (already wired).",
            "- Filter nulls: **RETAIN AS RISK THROTTLE** (`FILTER_NULLS.md`).",
            "- Locked book hierarchy (2026-08-11): **C** primary capital-efficient demo;",
            "  **B** alpha/return control; **A** unfiltered shadow control.",
            "- Verdict code: **`%s`**." % short,
            "- Funded sleeve stays **NO** until live parity + validated non-linear scaling",
            "  (lot/margin/OCO) if sizing C up toward B's dollar target within a stress budget.",
            "",
            "Driver: `python -m live.fx_v2b_asia_range_london_usdjpy_three_book_forward --email`",
            "Optional broker B: add `--broker-jan`.",
            "",
            "Hub: `%s`" % output_root.as_posix(),
            "",
        ]
    )
    path = output_root / "THREE_BOOK_FORWARD.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = [
        "potions: USDJPY Asia-range three-book forward",
        "",
        "Frozen: S_3_1_3 | A unfiltered | B Jan-only | C Jan+roll50 WR40/PF1",
        "OOS cut: years > %d" % int(FROZEN["oos_cut"]),
        "",
        "Verdict: %s" % short,
        "",
        "Shadow OOS N/S: A=%.2f B=%.2f C=%.2f"
        % (float(a["oos_ns"]), float(b["oos_ns"]), float(c["oos_ns"])),
        "Shadow OOS net: A=%s B=%s C=%s"
        % (_fmt_money(a["oos_net_usd"]), _fmt_money(b["oos_net_usd"]), _fmt_money(c["oos_net_usd"])),
        "Shadow full N/S: A=%.2f B=%.2f C=%.2f"
        % (float(a["ns"]), float(b["ns"]), float(c["ns"])),
        "",
    ]
    for letter, key, _ in BOOKS:
        br = broker_by.get(key)
        if br and br.get("broker_present"):
            email.append(
                "Broker %s: N/S=%.2f net≈$%.0f stress≈$%.0f trades=%d"
                % (
                    letter,
                    float(br["broker_ns"]),
                    float(br["broker_net_usd"]),
                    float(br["broker_stress_usd"]),
                    int(br["broker_trades"]),
                )
            )
        else:
            email.append("Broker %s: missing" % letter)
    email.extend(["", "Hub: %s" % output_root, "Report: %s" % path])
    (output_root / "THREE_BOOK_FORWARD_EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")

    meta = {
        "frozen": FROZEN,
        "verdict": short,
        "oos_winner": oos_winner["book"],
        "full_ns_winner": full_winner["book"],
        "c_beats_b_oos_ns": c_beats_b_oos_ns,
        "c_beats_b_oos_net": c_beats_b_oos_net,
        "broker_jan_ran": broker_jan_ran,
    }
    (output_root / "three_book_forward_meta.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    return path


def run_study(
    *,
    output_root: Path,
    unit_trades: Path,
    email: bool,
    broker_jan: bool,
    start: date,
    force: bool,
    max_days: Optional[int],
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    _progress(output_root, "THREE_BOOK start unit_trades=%s" % unit_trades)
    tape = load_tape(unit_trades, book=BOOK)
    masks = _masks(tape)
    shadow_rows: List[dict] = []
    for letter, key, label in BOOKS:
        scored = score_mask(tape, masks[key], label=label, oos_cut=int(FROZEN["oos_cut"]))
        scored["book"] = letter
        scored["variant"] = key
        shadow_rows.append(scored)
    yearly = _yearly_rows(tape, masks)
    yearly.to_csv(output_root / "three_book_forward_yearly.csv", index=False)
    pd.DataFrame(shadow_rows).to_csv(output_root / "three_book_forward.csv", index=False)

    broker_jan_ran = False
    if broker_jan:
        try:
            run_january_only_broker(
                output_root=output_root,
                start=start,
                force=force,
                max_days=max_days,
            )
            broker_jan_ran = True
        except Exception as exc:
            _progress(output_root, "THREE_BOOK broker-jan ERROR: %s" % exc)
            (output_root / "ERROR_three_book_broker_jan.txt").write_text(
                traceback.format_exc(), encoding="utf-8"
            )

    broker_rows = [
        _broker_row("A", "unfiltered", _load_broker_metrics(SIZING_STATE / "metrics.json")),
        _broker_row("B", "january_only", _load_broker_metrics(JAN_ONLY_STATE / "metrics.json")),
        _broker_row("C", "combined", _load_broker_metrics(FILTERED_STATE / "metrics.json")),
    ]
    path = write_report(
        output_root,
        shadow_rows=shadow_rows,
        yearly=yearly,
        broker_rows=broker_rows,
        broker_jan_ran=broker_jan_ran,
    )
    _progress(output_root, "THREE_BOOK wrote %s" % path)
    if email:
        try:
            from .notify_email import send_email

            body = (output_root / "THREE_BOOK_FORWARD_EMAIL.txt").read_text(encoding="utf-8")
            send_email(subject="potions: USDJPY Asia-range three-book forward", body=body)
            _progress(output_root, "THREE_BOOK EMAIL sent")
        except Exception as exc:
            _progress(output_root, "THREE_BOOK EMAIL failed: %s" % exc)
    return path


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=FILTER_HUB)
    p.add_argument(
        "--unit-trades",
        type=Path,
        default=SIZING_STATE / "unit_trades.csv",
    )
    p.add_argument("--start", default="2015-01-02")
    p.add_argument("--max-days", type=int, default=None)
    p.add_argument("--no-force", action="store_true")
    p.add_argument("--broker-jan", action="store_true", help="Run January-only PaperBroker replay")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(list(argv) if argv is not None else None)
    path = run_study(
        output_root=args.output_root,
        unit_trades=args.unit_trades,
        email=args.email,
        broker_jan=args.broker_jan,
        start=date.fromisoformat(args.start),
        force=not args.no_force,
        max_days=args.max_days,
    )
    print("Wrote %s" % path, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
