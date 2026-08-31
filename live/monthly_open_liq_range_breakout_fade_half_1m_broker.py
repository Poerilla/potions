"""HP envelope range-breakout **fade** with scale-out at half the range (1m broker).

After ``t_liq``, envelope = range. On **4h close outside** the range:

- **Fade** the breakout (limit at broken boundary, opposite direction)
- SL = 2× liq-run (default)
- Scale **half** at range midpoint; runner at opposite boundary
- Max 2 attempts

Hub: ``live/state/monthly_open_atr_extension_band/liq_run_range_breakout_fade_half_hp_1m_broker/``
"""

from __future__ import annotations

import argparse
import json
import traceback
from pathlib import Path
from typing import Optional

from .monthly_open_liq_run_bandmax_and_range_breakout import (
    build_enriched_hp_plans,
    write_causality_md,
)
from .monthly_open_liq_run_bandmax_breakout_1m_broker import (
    BAND_ROOT,
    ENTRY_QTY,
    _breakout_plans,
    _progress,
    _run_engine,
    _write_hub_summary,
)
from .notify_email import send_email

REPO = Path(__file__).resolve().parents[1]
HUB = BAND_ROOT / "liq_run_range_breakout_fade_half_hp_1m_broker"
SID = "nq_liq_range_breakout_fade_half_hp_1m"
DSR = "TRL-2026-00147"


def run(*, email: bool = False, smoke: int = 0, force: bool = True, liq_days: int = 2) -> int:
    _progress(HUB, "BUILD enriched plans smoke=%d liq_days=%d" % (smoke, liq_days))
    enriched = build_enriched_hp_plans(liq_days=liq_days, smoke=smoke)
    write_causality_md(HUB / "CAUSALITY.md")
    _progress(HUB, "ENRICHED n=%d" % len(enriched))

    m = _run_engine(
        output_root=HUB,
        sid=SID,
        strategy_type="monthly_open_liq_range_breakout",
        plans=_breakout_plans(enriched),
        config_extra={
            "max_attempts": 2,
            "sl_mode": "2x_liq",
            "breakout_mode": "fade",
            "scale_half_range": True,
            "entry_qty": ENTRY_QTY,
        },
        smoke=0,
        force=force,
    )
    (HUB / "enriched_plans.json").write_text(
        json.dumps(enriched if smoke <= 0 else {k: enriched[k] for k in sorted(enriched)[:smoke]}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    summary = _write_hub_summary(
        HUB,
        m,
        title="NQ HP envelope range-breakout fade + half-range SO (1m broker)",
        bullets=[
            "Range = envelope of month open + up/dn bands + p_liq + 1R SL (known at t_liq)",
            "No signal during liq window; **4h close** outside → **fade** limit at boundary",
            "SL = **2x_liq**; **1/2** off at range mid; runner at opposite boundary; max **2** attempts",
            "Engine + PaperBroker 1m; slip 1 tick + spread",
        ],
        stance="fade sidecar research (half-range scale-out)",
        dsr=DSR,
        notes="range breakout fade half-range SO HP 1m broker",
    )
    _progress(HUB, "DONE fade_half %s" % json.dumps({k: m[k] for k in ("n_entries", "net_usd", "ns")}))
    if email:
        send_email(subject="potions: NQ range BO fade half-range SO", body=summary)
    return 0


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", type=int, default=0)
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--liq-days", type=int, default=2)
    args = p.parse_args(argv)
    try:
        return run(email=args.email, smoke=args.smoke, force=args.force, liq_days=args.liq_days)
    except Exception:
        tb = traceback.format_exc()
        _progress(HUB, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: range BO fade half FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
