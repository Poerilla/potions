"""Shadow HP size-up annotator for authorized 1.25× calendar rules.

Logs ``hp_flag`` / ``would_size_mult`` on entry fills without changing order size.
Integer qty books cannot apply 1.25× cleanly — see hub ROLLOUT.md.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.hp_size_shadow --once
  python -m live.hp_size_shadow --once --email
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pandas as pd
import pytz

from .fx_v2b_london_ungated import REPO
from .notify_email import send_email

NY = pytz.timezone("America/New_York")
HUB = REPO / "live" / "state" / "intraday_hp_sizeup_nulls"

@dataclass(frozen=True)
class ShadowTarget:
    demo_rel: str
    book: str
    condition: str
    bucket: str
    size_mult: float
    decision: str


# Authorized primary paper tests (strict SIZE-UP VALIDATED @ 1.25×).
TARGETS: Sequence[ShadowTarget] = (
    ShadowTarget(
        demo_rel="live/demo/eurusd_hourly_st_pmc_sl50_tp150_3r_paper",
        book="eurusd_st_pmc_3r",
        condition="Day of week",
        bucket="Thursday",
        size_mult=1.25,
        decision="SIZE-UP VALIDATED",
    ),
    ShadowTarget(
        demo_rel="live/demo/us30_monday_or_m3_s3_r2_half_paper",
        book="us30_monday_or",
        condition="Entry hour (NY)",
        bucket="11",
        size_mult=1.25,
        decision="SIZE-UP VALIDATED",
    ),
)

SHADOW_COLS = [
    "entry_ts",
    "trade_id",
    "side",
    "quantity",
    "price",
    "hp_flag",
    "hp_condition",
    "hp_bucket",
    "would_size_mult",
    "decision",
    "mode",
    "annotated_at",
]


def _parse_ts(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    s = str(raw).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def hp_match(ts: datetime, *, condition: str, bucket: str) -> bool:
    local = ts.astimezone(NY)
    if condition == "Day of week":
        # Monday=0 … Sunday=6; research bucket uses English weekday name.
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        return names[local.weekday()] == str(bucket)
    if condition == "Entry hour (NY)":
        return int(local.hour) == int(bucket)
    return False


def _entry_fills(fills_path: Path) -> pd.DataFrame:
    if not fills_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(fills_path)
    if df.empty:
        return df
    reason = df["reason"].astype(str).str.lower() if "reason" in df.columns else pd.Series([""] * len(df))
    # Prefer explicit entry reasons; fall back to non-reduce fills if schema is thin.
    mask = reason.str.contains("entry", na=False)
    if not mask.any() and "bracket_role" in df.columns:
        mask = df["bracket_role"].astype(str).str.lower().eq("entry")
    if not mask.any():
        # No entries yet — return empty typed frame
        return df.iloc[0:0].copy()
    return df.loc[mask].copy()


def annotate_target(target: ShadowTarget) -> Dict[str, object]:
    demo = REPO / target.demo_rel
    state = demo / "state"
    fills_path = state / "fills.csv"
    out_path = state / "hp_shadow.csv"
    meta_path = demo / "HP_SIZEUP_SHADOW.json"

    entries = _entry_fills(fills_path)
    rows: List[dict] = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for _, fill in entries.iterrows():
        ts = _parse_ts(str(fill.get("ts") or fill.get("created_at") or ""))
        if ts is None:
            continue
        hit = hp_match(ts, condition=target.condition, bucket=target.bucket)
        rows.append(
            {
                "entry_ts": ts.isoformat(),
                "trade_id": fill.get("trade_id", ""),
                "side": fill.get("side", ""),
                "quantity": fill.get("quantity", ""),
                "price": fill.get("price", ""),
                "hp_flag": bool(hit),
                "hp_condition": target.condition,
                "hp_bucket": target.bucket,
                "would_size_mult": target.size_mult if hit else 1.0,
                "decision": target.decision,
                "mode": "shadow",
                "annotated_at": now,
            }
        )

    state.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=SHADOW_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    meta = {
        "book": target.book,
        "condition": target.condition,
        "bucket": target.bucket,
        "size_mult": target.size_mult,
        "decision": target.decision,
        "mode": "shadow",
        "demo": str(demo),
        "n_entry_fills": len(rows),
        "n_hp_hits": int(sum(1 for r in rows if r["hp_flag"])),
        "updated_at": now,
        "note": (
            "Shadow only — no order size change. Integer qty=1 cannot apply 1.25×; "
            "see live/state/intraday_hp_sizeup_nulls/ROLLOUT.md"
        ),
    }
    meta_path.write_text(
        __import__("json").dumps(meta, indent=2) + "\n",
        encoding="utf-8",
    )
    return meta


def run_once(*, email: bool = False) -> Path:
    lines = [
        "potions: HP size-up shadow armed (1.25× primary)",
        "hub: %s" % HUB,
        "rollout: %s" % (HUB / "ROLLOUT.md"),
        "",
    ]
    for t in TARGETS:
        m = annotate_target(t)
        lines.append(
            "- %s | %s=%s @%.2f× mode=shadow entries=%d hp_hits=%d"
            % (
                t.book,
                t.condition,
                t.bucket,
                t.size_mult,
                int(m["n_entry_fills"]),
                int(m["n_hp_hits"]),
            )
        )
    lines.append("")
    lines.append("Stance: 2 pair(s) SIZE-UP VALIDATED @1.25× — shadow first; no 2× deploy.")
    body = "\n".join(lines) + "\n"
    (HUB / "SHADOW_EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(subject="potions: HP size-up shadow armed @1.25×", body=body)
    return HUB / "ROLLOUT.md"


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="Annotate demos once and exit")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    if not args.once:
        p.error("pass --once (watcher loop not implemented yet)")
    run_once(email=bool(args.email))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
