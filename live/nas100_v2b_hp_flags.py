"""NAS100 v2b HP flag shadow logger (RSI-against / ST-opposed / both / neither).

Annotates entry fills on the NAS100 v2b paper + OANDA demos without changing
size. Research ST-opposed for prior_opposed books is an RSI proxy
(``st_opposed_proxy``); that identity is preserved here and labeled.

Outputs per demo::

  state/hp_flags.csv
  HP_FLAGS.json

Also appends ``HP_FLAGS ...`` lines to ``PROGRESS.log`` for newly seen trades.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nas100_v2b_hp_flags --once
  python -m live.nas100_v2b_hp_flags --once --email
"""

from __future__ import annotations

import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd
import pytz

from .fx_v2b_london_ungated import REPO
from .futures_intraday_hp_sizeup_lib import rsi
from .notify_email import send_email

NY = pytz.timezone("America/New_York")
HUB = REPO / "live" / "state" / "futures_intraday_hp_nas100_nq_lead"

DEMOS: Sequence[str] = (
    "live/demo/nas100_v2b_ungated_paper",
    "live/demo/nas100_v2b_ungated_oanda",
)

FLAG_COLS = [
    "entry_ts",
    "trade_id",
    "side",
    "quantity",
    "price",
    "rsi14",
    "rsi_against_side",
    "st_opposed",
    "st_source",
    "both_flags",
    "neither_flags",
    "would_size_mult",
    "decision",
    "mode",
    "annotated_at",
]


def _parse_ts(raw: object) -> Optional[datetime]:
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return None
    s = str(raw).strip()
    if not s:
        return None
    # OANDA fill stamps can carry nanoseconds; normalize to microseconds for fromisoformat.
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if "." in s:
            head, rest = s.split(".", 1)
            frac = ""
            tz = ""
            for i, ch in enumerate(rest):
                if ch.isdigit():
                    frac += ch
                else:
                    tz = rest[i:]
                    break
            frac = (frac + "000000")[:6]
            s = "%s.%s%s" % (head, frac, tz)
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        try:
            ts = pd.to_datetime(raw, utc=True)
            if pd.isna(ts):
                return None
            return ts.to_pydatetime()
        except Exception:
            return None


def _entry_fills(fills_path: Path) -> pd.DataFrame:
    if not fills_path.exists():
        return pd.DataFrame()
    df = pd.read_csv(fills_path)
    if df.empty:
        return df
    reason = df["reason"].astype(str).str.lower() if "reason" in df.columns else pd.Series([""] * len(df))
    mask = reason.str.contains("entry", na=False)
    if not mask.any() and "bracket_role" in df.columns:
        mask = df["bracket_role"].astype(str).str.lower().eq("entry")
    if not mask.any():
        return df.iloc[0:0].copy()
    return df.loc[mask].copy()


def _load_hourly_rsi(bars_1m_path: Path) -> pd.DataFrame:
    """Build completed 1h bars from 1m CSV and return ts + rsi14 (known at bar close)."""
    if not bars_1m_path.exists():
        return pd.DataFrame(columns=["ts", "rsi14"])
    raw = pd.read_csv(bars_1m_path)
    if raw.empty or "ts" not in raw.columns or "close" not in raw.columns:
        return pd.DataFrame(columns=["ts", "rsi14"])
    df = raw.copy()
    df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    df = df.dropna(subset=["ts"]).sort_values("ts")
    if df.empty:
        return pd.DataFrame(columns=["ts", "rsi14"])
    # Localize to NY for RTH-ish hourly buckets, then keep UTC timestamps.
    local = df["ts"].dt.tz_convert(NY)
    df = df.assign(_local=local)
    df["_hour"] = df["_local"].dt.floor("h")
    agg = (
        df.groupby("_hour", sort=True)
        .agg(
            open=("open", "first") if "open" in df.columns else ("close", "first"),
            high=("high", "max") if "high" in df.columns else ("close", "max"),
            low=("low", "min") if "low" in df.columns else ("close", "min"),
            close=("close", "last"),
        )
        .reset_index()
        .rename(columns={"_hour": "ts_local"})
    )
    # Hour bar is known only at its close; use next hour start as availability, or bar end.
    agg["ts"] = agg["ts_local"].dt.tz_convert("UTC") + pd.Timedelta(hours=1)
    agg["rsi14"] = rsi(agg["close"].astype(float), 14)
    # Shift so asof uses last *completed* hour RSI (no same-bar look-ahead).
    agg["rsi14"] = agg["rsi14"].shift(1)
    return agg[["ts", "rsi14"]].dropna(subset=["ts"])


def _rsi_against(side: str, rsi14: Optional[float]) -> Optional[bool]:
    if rsi14 is None or (isinstance(rsi14, float) and np.isnan(rsi14)):
        return None
    s = str(side).strip().lower()
    if s in ("buy", "long"):
        if rsi14 <= 45:
            return True
        if rsi14 >= 55:
            return False
        return False  # neutral → not against
    if s in ("sell", "short"):
        if rsi14 >= 55:
            return True
        if rsi14 <= 45:
            return False
        return False
    return None


def _asof_rsi(entry_ts: datetime, hourly: pd.DataFrame) -> Optional[float]:
    if hourly.empty:
        return None
    t = pd.Timestamp(entry_ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    sub = hourly.loc[hourly["ts"] <= t]
    if sub.empty:
        return None
    val = sub.iloc[-1]["rsi14"]
    if pd.isna(val):
        return None
    return float(val)


def _append_progress(output_root: Path, message: str) -> None:
    path = output_root / "PROGRESS.log"
    output_root.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    with path.open("a", encoding="utf-8") as fh:
        fh.write("[%s] %s\n" % (ts, message))


def annotate_demo(demo_rel: str, *, log_progress: bool = True) -> Dict[str, Any]:
    demo = REPO / demo_rel
    state = demo / "state"
    fills_path = state / "fills.csv"
    bars_path = state / "bars" / "NAS100_1m.csv"
    out_path = state / "hp_flags.csv"
    meta_path = demo / "HP_FLAGS.json"

    prev_ids: set = set()
    if out_path.exists():
        try:
            prev = pd.read_csv(out_path)
            if "trade_id" in prev.columns:
                prev_ids = set(prev["trade_id"].astype(str))
        except Exception:
            prev_ids = set()

    entries = _entry_fills(fills_path)
    hourly = _load_hourly_rsi(bars_path)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows: List[dict] = []
    new_rows: List[dict] = []

    for _, fill in entries.iterrows():
        ts = _parse_ts(fill.get("ts") or fill.get("created_at") or "")
        if ts is None:
            continue
        side = str(fill.get("side") or "")
        rsi14 = _asof_rsi(ts, hourly)
        against = _rsi_against(side, rsi14)
        # Research identity: ST-opposed proxy mirrors RSI-against on prior_opposed family.
        st_opposed = against
        st_source = "rsi_proxy"
        both = bool(against) and bool(st_opposed) if against is not None else False
        neither = (against is False) and (st_opposed is False)
        hit = bool(against)
        row = {
            "entry_ts": ts.isoformat(),
            "trade_id": str(fill.get("trade_id", "")),
            "side": side,
            "quantity": fill.get("quantity", ""),
            "price": fill.get("price", ""),
            "rsi14": ("" if rsi14 is None else round(float(rsi14), 4)),
            "rsi_against_side": bool(against) if against is not None else "",
            "st_opposed": bool(st_opposed) if st_opposed is not None else "",
            "st_source": st_source,
            "both_flags": both,
            "neither_flags": neither,
            "would_size_mult": 1.25 if hit else 1.0,
            "decision": "RISK THROTTLE",
            "mode": "shadow",
            "annotated_at": now,
        }
        rows.append(row)
        if str(row["trade_id"]) not in prev_ids:
            new_rows.append(row)

    state.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=FLAG_COLS)
        w.writeheader()
        for r in rows:
            w.writerow(r)

    if log_progress and new_rows:
        for r in new_rows:
            _append_progress(
                demo,
                "HP_FLAGS trade=%s side=%s rsi14=%s rsi_against=%s st_opposed=%s both=%s neither=%s st_source=%s"
                % (
                    r["trade_id"],
                    r["side"],
                    r["rsi14"],
                    r["rsi_against_side"],
                    r["st_opposed"],
                    r["both_flags"],
                    r["neither_flags"],
                    r["st_source"],
                ),
            )

    n_against = sum(1 for r in rows if r["rsi_against_side"] is True)
    n_both = sum(1 for r in rows if r["both_flags"] is True)
    n_neither = sum(1 for r in rows if r["neither_flags"] is True)
    meta = {
        "demo": str(demo),
        "book": "nas100_nq_lead_prior_opposed",
        "conditions": ["rsi_against_side", "st_opposed_proxy", "both_flags", "neither_flags"],
        "st_note": (
            "st_opposed uses research rsi_proxy (identical to rsi_against_side on "
            "prior_opposed family). both/neither collapse to against/not-against until "
            "a true ST-direction tape is wired."
        ),
        "decision": "RISK THROTTLE",
        "size_mult_if_hit": 1.25,
        "mode": "shadow",
        "n_entry_fills": len(rows),
        "n_rsi_against": n_against,
        "n_st_opposed": n_against,
        "n_both_flags": n_both,
        "n_neither_flags": n_neither,
        "n_newly_logged": len(new_rows),
        "updated_at": now,
        "artifacts": {"hp_flags_csv": str(out_path)},
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def write_master_null_competitors(*, email: bool = False) -> Path:
    """Identify buckets that beat RSI ΔN/S under the selection-aware master null."""
    pair = (
        HUB
        / "nulls"
        / "pairs"
        / "nas100_nq_lead_prior_opposed__Hourly_RSI_vs_trade__rsi_against_side"
    )
    out_dir = HUB / "nulls"
    out_dir.mkdir(parents=True, exist_ok=True)

    actual_dns = 1.600728
    actual_inc_ns = 21.244709
    mn = pd.read_csv(pair / "master_null.csv")
    led = pd.read_csv(HUB / "profile" / "candidate_ledger.csv")
    led = led.copy()
    led["delta_ns"] = led["book_ns_sized"] - led["book_ns_base"]

    beat = mn[mn["delta_ns"] >= actual_dns].copy()
    freq = (
        beat.groupby(["winner_condition", "winner_bucket"], as_index=False)
        .agg(
            n_perms=("perm_i", "count"),
            median_delta_ns=("delta_ns", "median"),
            mean_delta_ns=("delta_ns", "mean"),
            max_delta_ns=("delta_ns", "max"),
            median_inc_ns=("inc_ns", "median"),
            max_inc_ns=("inc_ns", "max"),
            median_book_ns=("book_ns", "median"),
            max_book_ns=("book_ns", "max"),
        )
        .sort_values(["n_perms", "median_delta_ns"], ascending=False)
    )
    freq["frac_of_beatters"] = freq["n_perms"] / max(len(beat), 1)
    hit_stats = (
        beat.assign(
            _inc25=(beat["inc_ns"] >= 25).astype(int),
            _book25=(beat["book_ns"] >= 25).astype(int),
        )
        .groupby(["winner_condition", "winner_bucket"], as_index=False)
        .agg(hits_inc_ns_ge_25=("_inc25", "sum"), hits_book_ns_ge_25=("_book25", "sum"))
    )
    freq = freq.merge(hit_stats, on=["winner_condition", "winner_bucket"], how="left")
    freq["hits_inc_ns_ge_25"] = freq["hits_inc_ns_ge_25"].fillna(0).astype(int)
    freq["hits_book_ns_ge_25"] = freq["hits_book_ns_ge_25"].fillna(0).astype(int)
    freq_path = out_dir / "master_null_beater_frequency.csv"
    freq.to_csv(freq_path, index=False)

    hi = mn[(mn["inc_ns"] >= 25) | (mn["book_ns"] >= 25)].copy()
    hi_path = out_dir / "master_null_ns_ge25_winners.csv"
    hi.sort_values(["inc_ns", "book_ns"], ascending=False).to_csv(hi_path, index=False)

    real_rank = led.sort_values(["delta_ns", "ns"], ascending=False)[
        [
            "condition",
            "bucket",
            "coverage",
            "n",
            "ns",
            "inc_ns",
            "delta_ns",
            "book_ns_sized",
            "status",
            "shortlisted",
        ]
    ]
    real_path = out_dir / "real_ledger_ranked_by_delta_ns.csv"
    real_rank.to_csv(real_path, index=False)

    # Real buckets that beat RSI on the actual selection score (ΔN/S)
    beaters_real = real_rank[real_rank["delta_ns"] > actual_dns + 1e-9]

    lines = [
        "# NAS100 NQ-lead — selection-aware master competitors",
        "",
        "Actual shortlisted HP: `Hourly RSI vs trade=rsi_against_side` @1.25×",
        "(identical mask to `ST-event direction=st_opposed_proxy`).",
        "",
        "```",
        "actual ΔN/S = +%.3f" % actual_dns,
        "actual sleeve N/S = %.2f" % actual_inc_ns,
        "p_master_delta_NS = %.3f  (%d / %d perms beat actual)"
        % (len(beat) / max(len(mn), 1), len(beat), len(mn)),
        "candidate ledger size = %d" % len(led),
        "```",
        "",
        "## What “other candidates” means",
        "",
        "The master null does **not** mean other *historical* buckets have higher",
        "realized sleeve N/S than 21.24. It means: after scrambling the",
        "outcome↔condition link and re-running the **same search over all 68",
        "ledger buckets**, ~70%% of permutations still find some winner with",
        "ΔN/S ≥ +1.60. Those winners are the competitors.",
        "",
        "## Real ledger (frozen history) — none ≥ N/S 25",
        "",
        "Max sleeve N/S in the ledger is **21.24** (RSI-against / ST-proxy).",
        "No bucket reaches sleeve or full-book N/S ≥ 25 on the real tape.",
        "",
        "Buckets that beat RSI on **ΔN/S** (selection score) on the real tape:",
        "",
        "| condition=bucket | cov | n | sleeve N/S | ΔN/S | status |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for _, r in beaters_real.iterrows():
        lines.append(
            "| %s=%s | %.0f%% | %d | %.2f | %+.2f | %s |"
            % (
                r["condition"],
                r["bucket"],
                100.0 * float(r["coverage"]),
                int(r["n"]),
                float(r["ns"]),
                float(r["delta_ns"]),
                r["status"],
            )
        )
    if beaters_real.empty:
        lines.append("| _(none)_ | | | | | |")

    lines.extend(
        [
            "",
            "## Master-null beater frequency (top 15)",
            "",
            "How often each bucket wins a null permutation with ΔN/S ≥ actual:",
            "",
            "| condition=bucket | n_perms | frac | med ΔN/S | max sleeve N/S | hits sleeve≥25 | hits book≥25 |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in freq.head(15).iterrows():
        lines.append(
            "| %s=%s | %d | %.2f | %+.2f | %.1f | %d | %d |"
            % (
                r["winner_condition"],
                r["winner_bucket"],
                int(r["n_perms"]),
                float(r["frac_of_beatters"]),
                float(r["median_delta_ns"]),
                float(r["max_inc_ns"]),
                int(r["hits_inc_ns_ge_25"]),
                int(r["hits_book_ns_ge_25"]),
            )
        )

    lines.extend(
        [
            "",
            "## Quantify / further-process",
            "",
            "1. **Frequency rank** — `master_null_beater_frequency.csv` (stable snooping competitors).",
            "2. **Chance N/S≥25** — `master_null_ns_ge25_winners.csv` (null-only gems; not promote).",
            "3. **Real ΔN/S board** — `real_ledger_ranked_by_delta_ns.csv` (coverage/status still bind).",
            "4. **Next tests** — pick top-frequency beaters with cov 5–35%% + causal_live_ready,",
            "   freeze each as its own 1.25× pair, rerun matched placebo/shift/master/WF.",
            "   Do **not** promote from null max N/S; those are scrambled-outcome artifacts.",
            "",
            "Artifacts: `%s` · `%s` · `%s`"
            % (freq_path.name, hi_path.name, real_path.name),
            "",
        ]
    )
    md_path = out_dir / "MASTER_NULL_COMPETITORS.md"
    body = "\n".join(lines) + "\n"
    md_path.write_text(body, encoding="utf-8")
    (out_dir / "EMAIL.txt").write_text(
        "NAS100 HP master-null competitors\nhub: %s\n%s\n" % (out_dir, body[:2500]),
        encoding="utf-8",
    )
    if email:
        send_email(
            subject="potions: NAS100 HP master-null competitors + flag logger",
            body=body,
        )
    return md_path


def run_once(*, email: bool = False, competitors: bool = True) -> Tuple[Path, List[Dict[str, Any]]]:
    metas: List[Dict[str, Any]] = []
    lines = [
        "potions: NAS100 v2b HP flags (RSI-against / ST-opposed / both / neither)",
        "hub: %s" % HUB,
        "mode: shadow (no size change); st_opposed = rsi_proxy",
        "",
    ]
    for demo in DEMOS:
        m = annotate_demo(demo, log_progress=True)
        metas.append(m)
        lines.append(
            "- %s entries=%d rsi_against=%d both=%d neither=%d new=%d"
            % (
                Path(demo).name,
                int(m["n_entry_fills"]),
                int(m["n_rsi_against"]),
                int(m["n_both_flags"]),
                int(m["n_neither_flags"]),
                int(m["n_newly_logged"]),
            )
        )
    md = None
    if competitors:
        md = write_master_null_competitors(email=False)
        lines.append("")
        lines.append("competitors: %s" % md)
    body = "\n".join(lines) + "\n"
    (HUB / "HP_FLAGS_EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        extra = ""
        if md and md.exists():
            extra = "\n\n" + md.read_text(encoding="utf-8")[:3500]
        send_email(subject="potions: NAS100 v2b HP flags armed (shadow)", body=body + extra)
    return HUB, metas


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--once", action="store_true", help="Annotate demos once and exit")
    p.add_argument("--competitors-only", action="store_true", help="Only write master-null competitor tables")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    if args.competitors_only:
        write_master_null_competitors(email=bool(args.email))
        return 0
    if not args.once:
        p.error("pass --once (or --competitors-only)")
    run_once(email=bool(args.email), competitors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
