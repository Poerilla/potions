"""Post-process: add one 10R runner unit onto existing prior-opposed S_1_1_3 books.

For each campaign, keep the archived 5-unit PnL frozen and simulate one extra
contract from the same entry:
  - R inferred per campaign (wide_stop distance, else TP1 distance, else median)
  - Target = entry ± 10R
  - After TP1 time: stop → BE; before: hard stop at 1R
  - Else exit at session EOD / last unit exit

Writes hub ``live/state/prior_opposed_10r_addon/`` and optional email body.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .ym_hourly_st_pmc_retest_replay import concat_all_1m, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "live" / "state" / "prior_opposed_10r_addon"


@dataclass(frozen=True)
class Spec:
    key: str
    instrument: str
    unit_trades: Path
    one_m: Path
    source: str  # fx_csv | dbn
    point_value: float
    baseline_net: float
    baseline_stress: float
    baseline_ns: float
    fee_per_unit: float = 0.0


def _specs() -> List[Spec]:
    st = REPO / "live" / "state"
    return [
        Spec(
            "nq",
            "NQ",
            st
            / "nq_v2b_prior_opposed_causal_proxies"
            / "resting_limit"
            / "states"
            / "nq_v2b_prior_opposed_stpmc_only_S_1_1_3"
            / "unit_trades.csv",
            REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
            "dbn",
            20.0,
            1330920.0,
            -68610.0,
            19.40,
        ),
        Spec(
            "mnq",
            "MNQ",
            st
            / "mnq_v2b_prior_opposed_stpmc_resting_limit"
            / "states"
            / "mnq_v2b_prior_opposed_stpmc_only_S_1_1_3"
            / "unit_trades.csv",
            # MNQ prior-opposed prices are NQ-scale; use NQ 1m tape
            REPO / "nq" / "raw" / "glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
            "dbn",
            2.0,
            128360.0,
            -6960.0,
            18.44,
        ),
        Spec(
            "us30",
            "US30",
            st
            / "us30_futures_strats_sweep"
            / "states"
            / "us30_v2b_oco_prior_opposed_S_1_1_3"
            / "unit_trades.csv",
            REPO / "fx" / "us30_1m.csv",
            "fx_csv",
            1.0,
            6300.0,
            -10700.0,
            0.59,
        ),
        Spec(
            "nas100",
            "NAS100",
            st
            / "nas100_v2b_prior_opposed_stpmc_broker_like"
            / "states"
            / "nas100_v2b_prior_opposed_stpmc_only_S_1_1_3"
            / "unit_trades.csv",
            REPO / "fx" / "nas100_1m.csv",
            "fx_csv",
            1.0,
            923.0,
            -7900.0,
            0.12,
        ),
    ]


_ONE_M_CACHE: Dict[Tuple[str, str], pd.DataFrame] = {}


def _load_1m(spec: Spec) -> pd.DataFrame:
    load_instr = "nq" if spec.key in {"nq", "mnq"} else spec.instrument.lower()
    key = (str(spec.one_m), spec.source + ":" + load_instr)
    cached = _ONE_M_CACHE.get(key)
    if cached is not None:
        return cached
    if spec.source == "fx_csv":
        gby = load_fx_1m_by_ny_date(spec.one_m, spec.instrument)
        df = concat_all_1m(gby)
    else:
        # NQ DBN used for both NQ and MNQ prior-opposed (same price scale)
        gby = load_1m_by_ny_date_any(spec.one_m, load_instr)
        df = concat_all_1m(gby)
    if not isinstance(df.index, pd.DatetimeIndex):
        df = df.copy()
        df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    _ONE_M_CACHE[key] = df
    return df


def _slice(df: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    s = pd.Timestamp(start)
    e = pd.Timestamp(end)
    if df.index.tz is not None and s.tzinfo is None:
        s = s.tz_localize(df.index.tz)
        e = e.tz_localize(df.index.tz)
    elif df.index.tz is None and s.tzinfo is not None:
        s = s.tz_convert("UTC").tz_localize(None)
        e = e.tz_convert("UTC").tz_localize(None)
    return df.loc[(df.index >= s) & (df.index <= e)]


def _campaigns(path: Path) -> List[dict]:
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    by: Dict[str, List[dict]] = defaultdict(list)
    for r in rows:
        by[r["trade_id"]].append(r)
    out = []
    for tid, us in by.items():
        us = sorted(us, key=lambda x: x["exit_ts"])
        direction = us[0]["direction"]
        entry_ts = us[0]["entry_ts"]
        entry_px = float(us[0]["entry_price"])
        is_long = direction.lower().startswith("l")
        signed = []
        tp1_ts = ""
        r_cands = []
        for u in us:
            pts = (float(u["exit_price"]) - entry_px) if is_long else (entry_px - float(u["exit_price"]))
            signed.append(pts)
            if u["exit_reason"] == "tp1" and not tp1_ts:
                tp1_ts = u["exit_ts"]
                r_cands.append(abs(pts))
            if u["exit_reason"] == "wide_stop":
                r_cands.append(abs(pts))
        baseline_usd = sum(float(u["net_usd"]) for u in us)
        exit_last = max(u["exit_ts"] for u in us)
        out.append(
            {
                "trade_id": tid,
                "direction": direction,
                "entry_ts": entry_ts,
                "entry_price": entry_px,
                "tp1_ts": tp1_ts,
                "exit_last": exit_last,
                "baseline_usd": baseline_usd,
                "r_cands": r_cands,
                "n_units": len(us),
            }
        )
    return out


def _default_r(campaigns: Sequence[dict]) -> float:
    vals = [c for camp in campaigns for c in camp["r_cands"] if c > 1e-9]
    if not vals:
        return 50.0
    vals = sorted(vals)
    return float(vals[len(vals) // 2])


def _sim_10r(
    bars: pd.DataFrame,
    *,
    direction: str,
    entry: float,
    r: float,
    be_ts: str,
    tick: float = 0.25,
) -> Tuple[float, str]:
    if bars is None or len(bars) == 0 or r <= 0:
        return 0.0, "no_bars"
    is_long = direction.lower().startswith("l")
    hard = entry - r if is_long else entry + r
    target = entry + 10.0 * r if is_long else entry - 10.0 * r
    be = entry
    be_t = pd.Timestamp(be_ts) if be_ts else None
    if be_t is not None:
        if bars.index.tz is not None and be_t.tzinfo is None:
            be_t = be_t.tz_localize(bars.index.tz)
        elif bars.index.tz is None and be_t.tzinfo is not None:
            be_t = be_t.tz_convert("UTC").tz_localize(None)

    opens = bars["open"].to_numpy(dtype=float)
    highs = bars["high"].to_numpy(dtype=float)
    lows = bars["low"].to_numpy(dtype=float)
    index = bars.index
    for i in range(len(index)):
        ts = index[i]
        o, h, l = opens[i], highs[i], lows[i]
        after_be = bool(be_t is not None and ts > be_t)
        stop = be if after_be else hard
        if is_long:
            stop_hit = l <= stop
            tgt_hit = h >= target
        else:
            stop_hit = h >= stop
            tgt_hit = l <= target
        if stop_hit:
            fill = stop - tick if is_long else stop + tick
            if is_long and o < stop:
                fill = o - tick
            if (not is_long) and o > stop:
                fill = o + tick
            pts = (fill - entry) if is_long else (entry - fill)
            return pts, "runner_stop" if after_be else "stop"
        if tgt_hit:
            return (10.0 * r), "target_10r"
    # mark at last close
    last = bars.iloc[-1]
    px = float(last["close"])
    pts = (px - entry) if is_long else (entry - px)
    return pts, "eod_mark"


def analyze_market(spec: Spec) -> dict:
    if not spec.unit_trades.exists():
        return {"market": spec.key, "status": "missing_unit_trades"}
    print("Loading 1m %s…" % spec.instrument, flush=True)
    one_m = _load_1m(spec)
    print("  bars=%d" % len(one_m), flush=True)
    camps = _campaigns(spec.unit_trades)
    r_def = _default_r(camps)
    print("  campaigns=%d default_R=%.2f" % (len(camps), r_def), flush=True)

    addon_rows = []
    addon_usd = 0.0
    hits = 0
    stops = 0
    eods = 0
    baseline_sum = 0.0
    for c in camps:
        baseline_sum += c["baseline_usd"]
        r = float(c["r_cands"][0]) if c["r_cands"] else r_def
        r = max(r, 1e-6)
        bars = _slice(one_m, c["entry_ts"], c["exit_last"])
        pts, reason = _sim_10r(
            bars,
            direction=c["direction"],
            entry=c["entry_price"],
            r=r,
            be_ts=c["tp1_ts"],
        )
        usd = pts * spec.point_value - spec.fee_per_unit
        addon_usd += usd
        if reason == "target_10r":
            hits += 1
        elif reason in {"stop", "runner_stop"}:
            stops += 1
        else:
            eods += 1
        addon_rows.append(
            {
                "trade_id": c["trade_id"],
                "direction": c["direction"],
                "entry_ts": c["entry_ts"],
                "r": round(r, 4),
                "addon_pts": round(pts, 4),
                "addon_usd": round(usd, 2),
                "exit_reason": reason,
                "had_tp1": bool(c["tp1_ts"]),
                "baseline_campaign_usd": round(c["baseline_usd"], 2),
            }
        )

    # Stress proxy: baseline stress + extra 1R inventory risk on campaigns without TP1
    # (after TP1, BE → ~0 incremental stop risk). Conservative.
    extra_stress = 0.0
    for c in camps:
        r = float(c["r_cands"][0]) if c["r_cands"] else r_def
        if not c["tp1_ts"]:
            extra_stress -= r * spec.point_value  # worst concurrent open risk contribution (stacking upper bound)
    # Cap extra stress magnitude to something sane: use max single-R * sqrt-ish — instead use
    # reachable: only count max open of 1 extra unit → stress delta ≈ -R*PV (one unit)
    extra_stress_reachable = -r_def * spec.point_value
    new_net = baseline_sum + addon_usd
    # Prefer published baseline stress for apples-to-apples; add one-unit R risk
    new_stress = spec.baseline_stress + extra_stress_reachable
    if abs(new_stress) < 1e-9:
        new_stress = -1.0
    new_ns = new_net / abs(new_stress)
    base_ns = spec.baseline_ns

    result = {
        "market": spec.key,
        "instrument": spec.instrument,
        "status": "ok",
        "campaigns": len(camps),
        "default_r": round(r_def, 3),
        "baseline_net": round(baseline_sum, 2),
        "baseline_net_published": spec.baseline_net,
        "baseline_stress": spec.baseline_stress,
        "baseline_ns": base_ns,
        "addon_net": round(addon_usd, 2),
        "combined_net": round(new_net, 2),
        "combined_stress": round(new_stress, 2),
        "combined_ns": round(new_ns, 3),
        "delta_net": round(addon_usd, 2),
        "delta_ns": round(new_ns - base_ns, 3),
        "beats_baseline_ns": bool(new_ns > base_ns),
        "beats_baseline_net": bool(new_net > baseline_sum),
        "addon_10r_hits": hits,
        "addon_stops": stops,
        "addon_eod": eods,
        "hit_rate_pct": round(100.0 * hits / len(camps), 1) if camps else 0.0,
        "note": "Extra unit only; archived S_1_1_3 book frozen. Stress += one-unit −R.",
    }
    return {"result": result, "rows": addon_rows}


def write_hub(all_results: Sequence[dict], *, email: bool) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    summary = []
    for blob in all_results:
        res = blob.get("result") or blob
        summary.append(res)
        m = res["market"]
        mdir = OUT / m
        mdir.mkdir(parents=True, exist_ok=True)
        (mdir / "result.json").write_text(json.dumps(blob, indent=2, default=str) + "\n")
        rows = blob.get("rows") or []
        if rows:
            with (mdir / "addon_units.csv").open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)

    fields = [
        "market",
        "instrument",
        "campaigns",
        "baseline_net",
        "addon_net",
        "combined_net",
        "baseline_ns",
        "combined_ns",
        "delta_ns",
        "beats_baseline_ns",
        "addon_10r_hits",
        "hit_rate_pct",
        "combined_stress",
    ]
    with (OUT / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in summary:
            if r.get("status") == "ok":
                w.writerow(r)

    lines = [
        "# Prior-opposed + single 10R runner add-on",
        "",
        "Frozen S_1_1_3 book (1 TP1 + 1 TP2 + 3 EOD runners). **Add one** contract targeting **10×R**",
        "(R = campaign wide-stop / TP1 distance; BE after TP1).",
        "",
        "| market | baseline net | addon net | combined | base N/S | new N/S | Δ N/S | 10R hits | promote? |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for r in summary:
        if r.get("status") != "ok":
            lines.append("| `%s` | — | — | — | — | — | — | — | %s |" % (r.get("market"), r.get("status")))
            continue
        promo = "YES" if r["beats_baseline_ns"] and r["beats_baseline_net"] else "no"
        lines.append(
            "| `%s` | $%.0f | $%.0f | $%.0f | %.2f | **%.2f** | %+.2f | %d (%.0f%%) | %s |"
            % (
                r["market"],
                r["baseline_net"],
                r["addon_net"],
                r["combined_net"],
                r["baseline_ns"],
                r["combined_ns"],
                r["delta_ns"],
                r["addon_10r_hits"],
                r["hit_rate_pct"],
                promo,
            )
        )
    lines += [
        "",
        "## Stance",
        "",
        "- Promote the 10R add-on only if **combined N/S** beats baseline prior-opposed N/S with bounded inventory (+1 unit).",
        "- US30/NAS100 prior-opposed baselines are weak; a 10R sleeve cannot rescue a bad gate.",
        "- NQ/MNQ already have strong N/S (~19); add-on must not dilute N/S.",
        "",
        "## Artifacts",
        "",
        "- `summary.csv`, per-market `addon_units.csv`",
        "",
    ]
    (OUT / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    winners = [r for r in summary if r.get("beats_baseline_ns") and r.get("beats_baseline_net")]
    losers = [r for r in summary if r.get("status") == "ok" and r not in winners]
    email_lines = [
        "Prior-opposed +1×10R runner — analysis",
        "",
        "Question: freeze the S_1_1_3 book (1 TP1 + 1 TP2 + 3 EOD runners)",
        "and add ONE extra contract targeting 10×R (BE after TP1).",
        "Does combined Net/Stress beat the published prior-opposed baseline?",
        "",
        "VERDICT: %s"
        % (
            "PROMOTE on " + ", ".join(r["market"].upper() for r in winners)
            if winners
            else "DO NOT PROMOTE — add-on fails N/S gate on all tested markets"
        ),
        "",
        "Per market:",
    ]
    for r in summary:
        if r.get("status") != "ok":
            email_lines.append("  %s: %s" % (r.get("market"), r.get("status")))
            continue
        tag = "PASS" if r in winners else "FAIL"
        email_lines.append(
            "  [%s] %s  N/S %.2f → %.2f (Δ%+.2f)  net $%.0f%+.0f → $%.0f  10R hits %d/%d (%.0f%%)"
            % (
                tag,
                r["market"].upper(),
                r["baseline_ns"],
                r["combined_ns"],
                r["delta_ns"],
                r["baseline_net"],
                r["addon_net"],
                r["combined_net"],
                r["addon_10r_hits"],
                r["campaigns"],
                r["hit_rate_pct"],
            )
        )
    email_lines += ["", "Read:"]
    if losers and not winners:
        email_lines.append(
            "- Takeaway: 10R hits too rare vs extra stop inventory — keep S_1_1_3 as-is."
        )
    email_lines += [
        "- NQ/MNQ already print ~19 N/S; only promote if ΔN/S > 0 with +1 inventory.",
        "- US30/NAS100 prior-opposed baselines are weak; a 10R sleeve cannot rescue the gate.",
        "- Stress model: published stress + one-unit −R (conservative).",
        "",
        "Hub: live/state/prior_opposed_10r_addon/",
    ]
    body = "\n".join(email_lines) + "\n"
    (OUT / "EMAIL.txt").write_text(body, encoding="utf-8")
    if email:
        send_email(subject="potions: prior-opposed +10R add-on — verdict", body=body)
        print("emailed 10R analysis", flush=True)
    print("Wrote %s" % (OUT / "SUMMARY.md"), flush=True)
    return OUT


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--markets", nargs="*", default=None)
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    want = {m.lower() for m in args.markets} if args.markets else None
    # Prefer FX first (faster), then NQ before MNQ so DBN cache warms once.
    order = ["us30", "nas100", "nq", "mnq"]
    specs = {s.key: s for s in _specs()}
    keys = [k for k in order if k in specs and (not want or k in want)]
    keys += [k for k in specs if k not in keys and (not want or k in want)]
    blobs = []
    for key in keys:
        print("ANALYZE %s" % key, flush=True)
        blobs.append(analyze_market(specs[key]))
    write_hub(blobs, email=bool(args.email))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
