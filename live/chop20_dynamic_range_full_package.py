"""Full CHOP20 boundary60 package: cross-market 1m → HA mill → causality → email.

Narrative completion email covers path from daily walkthrough → loss profile →
1m proof → cross-market → HA → causality.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  export POTIONS_RUN_LEDGER="/home/tester/hsm/potions/data/validation/broker_run_ledger.csv"
  python -m live.chop20_dynamic_range_full_package --email
  python -m live.chop20_dynamic_range_full_package --email --smoke
  python -m live.chop20_dynamic_range_full_package --email --skip-replay  # HA+audit only
"""

from __future__ import annotations

import argparse
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import chop20_dynamic_range_1m_cross_market as xmarket
from . import chop20_dynamic_range_causality_audit as causality
from . import chop20_dynamic_range_ha_conditions as ha
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "chop20_dynamic_range_full_package"
NQ_1M_HUB = REPO / "live" / "state" / "nq_chop20_dynamic_range_1m_boundary60"
LOSS_HUB = REPO / "live" / "state" / "nq_chop20_dynamic_range_breakout_walkthrough" / "loss_profile"
WALK_HUB = REPO / "live" / "state" / "nq_chop20_dynamic_range_breakout_walkthrough"


def _progress(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.exists() else "_missing_"


def _board_table(path: Path) -> str:
    if not path.exists():
        return "_missing summary board_"
    df = pd.read_csv(path)
    if df.empty:
        return "_empty_"
    cols = [c for c in ("market", "trades", "net_usd", "mtm_drawdown", "net_stress", "win_rate") if c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "|" + "|".join(["---:"] * len(cols)) + "|"]
    # fix header alignment
    lines[1] = "| " + " | ".join("---" if c == "market" else "---:" for c in cols) + " |"
    for _, r in df.iterrows():
        cells = []
        for c in cols:
            v = r[c]
            if c in ("net_usd", "mtm_drawdown"):
                cells.append("$%+.0f" % float(v))
            elif c == "net_stress":
                cells.append("%.2f" % float(v))
            elif c == "win_rate":
                cells.append("%.0f%%" % float(v))
            elif c == "trades":
                cells.append("%d" % int(v))
            else:
                cells.append(str(v))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def build_narrative(*, smoke: bool) -> str:
    board_path = xmarket.HUB / "summary_board.csv"
    lines = [
        "# CHOP20 Dynamic Range — Full Package Results",
        "",
        "Generated: %s" % datetime.now().isoformat(timespec="seconds"),
        "",
        "## How we got here",
        "",
        "1. **Daily walkthrough** (`%s`) — naive close-back-inside exits:" % WALK_HUB.name,
        "   NQ ~59 trades, +$329k / −$251k MTM / N/S 1.31. Signal present; failure rule too loose.",
        "2. **Loss profile + structure sweep** (`%s`) — losers dominated by" % LOSS_HUB.parent.name,
        "   `range_close_cancel`. Best structure matching 0.5/1/4R:",
        "   **boundary stop + 60-bar max age** → daily diagnostic ~+$484k / −$57k / N/S 8.47.",
        "3. **NQ 1m path proof** (`%s`, DSR TRL-2026-00176) — same structure on 1m" % NQ_1M_HUB.name,
        "   stop-first tape: +$470k / −$69k / N/S 6.84 / 69 trades. Structure survives finer tape.",
        "4. **This package** — cross-market 1m (NQ/YM/MYM/MNQ) → HA mill → causality audit.",
        "",
        "## Best structure under test",
        "",
        "- Variant: `touch_broken_boundary_max_age_60`",
        "- Daily CHOP20 range + close breakout = **signal only**",
        "- Entry: last RTH 1m of signal day @ daily close ±1 tick",
        "- Stop: touch broken range boundary (OR near side)",
        "- Targets: 0.5R / 1R / 4R scale-out",
        "- Freshness: max range age 60 daily bars",
        "- Same-bar: **stop-first**",
        "",
        "## Cross-market 1m board",
        "",
        _board_table(board_path),
        "",
        "Hub: `%s`" % xmarket.HUB,
        "DSR: `TRL-2026-00177`",
        "",
        "## HA mill (high-probability conditions)",
        "",
        _read(ha.HUB / "SUMMARY.md"),
        "",
        "## Causality / LOOKAHEAD",
        "",
        _read(causality.HUB / "LOOKAHEAD_REVIEW.md"),
        "",
        "## Variant ladder (NQ path)",
        "",
        "| Stage | Tape | Net | MTM DD | N/S | Trades | Note |",
        "|---|---|---:|---:|---:|---:|---|",
        "| Base daily close-back-inside | daily | +$329k | −$251k | 1.31 | 59 | too loose |",
        "| Boundary+age60+4R (daily diag) | daily | +$484k | −$57k | 8.47 | 75 | loss-profile best match |",
        "| Boundary+age60+2R (daily diag) | daily | +$594k | −$61k | 9.71 | — | stronger but changes runner |",
        "| Boundary+age60+4R (NQ 1m) | 1m | +$470k | −$69k | 6.84 | 69 | path proof |",
        "",
        "## Stance",
        "",
        "- **Research / provisional** — NQ 1m path supports the structure; cross-market board above.",
        "- HA size-ups are diagnostic on thin N; only promote if nulls say VALIDATED/PROVISIONAL.",
        "- Causality path audit must PASS before StrategyPlugin port.",
        "- Not funded production until Engine plugin + Guard snapshots exist.",
        "",
        "Package hub: `%s`" % HUB,
        "Smoke=%s" % smoke,
        "",
    ]
    return "\n".join(lines)


def run(*, email: bool, smoke: bool, skip_replay: bool, markets: str) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    rid = begin_run(
        run_class="other",
        variant_slug="chop20_boundary60_full_package",
        instrument="MULTI",
        hub_path=str(HUB.relative_to(REPO)),
        notes="full package running",
        meta={"smoke": smoke, "skip_replay": skip_replay},
    )
    try:
        market_list = [m.strip().lower() for m in markets.split(",") if m.strip()]
        if smoke and not skip_replay:
            # Smoke: NQ only for replay time; HA uses smoke nulls.
            market_list = ["nq"]
            _progress("SMOKE: replay markets=%s" % market_list)

        if not skip_replay:
            _progress("PHASE 1 — cross-market 1m replay")
            xmarket.run(markets=market_list, email=False)
        else:
            _progress("PHASE 1 — skip replay (using existing hubs)")

        _progress("PHASE 2 — HA mill")
        ha.run(
            email=False,
            smoke=smoke,
            profile_only=False,
            overlay_only=False,
            nulls_only=False,
        )

        _progress("PHASE 3 — causality audit")
        causality.run(email=False)

        _progress("PHASE 4 — narrative package")
        body = build_narrative(smoke=smoke)
        (HUB / "SUMMARY.md").write_text(body, encoding="utf-8")
        (HUB / "EMAIL.txt").write_text(
            "potions: CHOP20 full package complete\n\n" + body, encoding="utf-8"
        )
        complete_run(rid, notes="full package complete")
        if email:
            send_email(
                subject="potions: CHOP20 boundary60 full package (xmarket+HA+causality)",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
            _progress("email sent")
        _progress("DONE full package")
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        (HUB / "EMAIL.txt").write_text(
            "potions: CHOP20 full package FAILED\n\n%s\n" % err[-6000:], encoding="utf-8"
        )
        if email:
            send_email(
                subject="potions: CHOP20 full package FAILED",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--skip-replay", action="store_true")
    ap.add_argument("--markets", default="nq,ym,mym,mnq")
    args = ap.parse_args()
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        skip_replay=bool(args.skip_replay),
        markets=args.markets,
    )


if __name__ == "__main__":
    main()
