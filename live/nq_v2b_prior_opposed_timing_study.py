"""NQ prior-opposed timing autopsy + honest baselines.

Joins banked hourly-stamp vs 1m-touch campaigns, attributes net to lookahead
victims vs timing-valid sleeves, and writes an INDEX under
``live/state/nq_v2b_prior_opposed_timing_study/``.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from .nq_v2b_prior_opposed_replay import NY, _to_ny_ts
from .v2b_st_pmc_alignment_study import REPO


BANKED_ROOT = REPO / "live/state/nq_v2b_prior_opposed_stpmc_broker_like"
TOUCH_ROOT = REPO / "live/state/nq_v2b_prior_opposed_stpmc_1m_touch"
DEFAULT_OUT = REPO / "live/state/nq_v2b_prior_opposed_timing_study"


def _camp(units: pd.DataFrame) -> pd.DataFrame:
    g = (
        units.groupby("trade_id")
        .agg(
            entry_ts=("entry_ts", "first"),
            exit_ts=("exit_ts", "max"),
            direction=("direction", "first"),
            net_usd=("net_usd", "sum"),
            entry_price=("entry_price", "first"),
            units=("unit_id", "count"),
        )
        .reset_index()
    )
    g["entry_ts"] = pd.to_datetime(g["entry_ts"], utc=True).dt.tz_convert(NY)
    g["exit_ts"] = pd.to_datetime(g["exit_ts"], utc=True).dt.tz_convert(NY)
    g["day"] = g["entry_ts"].dt.date.astype(str)
    g["side"] = g["direction"].astype(str).str.lower().map({"long": "long", "short": "short"})
    return g


def _load_events(touch_state: Path) -> Dict[str, List[Dict[str, str]]]:
    cfg = pd.read_csv(touch_state / "strategy_instances.csv")
    return json.loads(cfg.iloc[0]["config_json"])["dynamic_sizing_events"]


def _best_prior(
    events: List[Dict[str, str]],
    *,
    wanted: str,
    entry_ts: pd.Timestamp,
    ts_key: str,
) -> Optional[Dict[str, str]]:
    priors = []
    for event in events:
        if str(event.get("side", "")).lower() != wanted:
            continue
        try:
            event_ts = _to_ny_ts(event.get(ts_key) or event.get("ts"))
        except Exception:
            continue
        if event_ts < entry_ts:
            priors.append(event)
    if not priors:
        return None
    return max(priors, key=lambda e: _to_ny_ts(e.get(ts_key) or e.get("ts")))


def build_campaign_tape(
    banked_units: Path,
    touch_units: Path,
    touch_state: Path,
) -> pd.DataFrame:
    bc = _camp(pd.read_csv(banked_units))
    tc = _camp(pd.read_csv(touch_units))
    events = _load_events(touch_state)
    merged = bc.merge(tc, on="day", how="outer", suffixes=("_banked", "_touch"), indicator=True)
    merged = merged.rename(columns={"_merge": "merge_side"})
    rows: List[Dict[str, Any]] = []
    for _, row in merged.iterrows():
        day = str(row["day"])
        day_events = events.get(day, [])
        merge_side = str(row["merge_side"])
        has_banked = merge_side in {"both", "left_only"} and not pd.isna(row.get("entry_ts_banked"))
        has_touch = merge_side in {"both", "right_only"} and not pd.isna(row.get("entry_ts_touch"))
        side = str(row.get("side_banked") or row.get("side_touch") or "")
        wanted = "short" if side == "long" else "long" if side == "short" else ""
        entry_b = None if not has_banked else _to_ny_ts(row["entry_ts_banked"])
        entry_t = None if not has_touch else _to_ny_ts(row["entry_ts_touch"])
        hourly_prior = None
        touch_prior_for_banked = None
        touch_prior_for_touch = None
        if wanted and entry_b is not None:
            hourly_prior = _best_prior(day_events, wanted=wanted, entry_ts=entry_b, ts_key="fill_ts_hourly")
            touch_prior_for_banked = _best_prior(day_events, wanted=wanted, entry_ts=entry_b, ts_key="ts")
        if wanted and entry_t is not None:
            touch_prior_for_touch = _best_prior(day_events, wanted=wanted, entry_ts=entry_t, ts_key="ts")

        gate_hourly = None if hourly_prior is None else _to_ny_ts(hourly_prior["fill_ts_hourly"])
        gate_1m_at_banked = None if touch_prior_for_banked is None else _to_ny_ts(touch_prior_for_banked["ts"])
        # Prefer same fill event's refined touch when available
        if hourly_prior is not None and hourly_prior.get("ts"):
            gate_1m_same_event = _to_ny_ts(hourly_prior["ts"])
        else:
            gate_1m_same_event = gate_1m_at_banked

        lookahead_victim = bool(
            entry_b is not None and gate_1m_same_event is not None and entry_b <= gate_1m_same_event
        )
        timing_valid = bool(
            entry_b is not None and gate_1m_same_event is not None and entry_b > gate_1m_same_event
        )
        window_span = (
            None
            if gate_hourly is None or gate_1m_same_event is None
            else (gate_1m_same_event - gate_hourly).total_seconds() / 60.0
        )
        into_window = (
            None
            if entry_b is None or gate_hourly is None
            else (entry_b - gate_hourly).total_seconds() / 60.0
        )
        window_frac = (
            None
            if window_span is None or window_span <= 0 or into_window is None
            else into_window / window_span
        )
        net_b = None if not has_banked else float(row["net_usd_banked"])
        net_t = None if not has_touch else float(row["net_usd_touch"])
        rows.append(
            {
                "day": day,
                "merge": merge_side,
                "side": side,
                "entry_ts_banked": "" if entry_b is None else entry_b.isoformat(),
                "entry_ts_touch": "" if entry_t is None else entry_t.isoformat(),
                "entry_delay_min": ""
                if entry_b is None or entry_t is None
                else "%.2f" % ((entry_t - entry_b).total_seconds() / 60.0),
                "net_usd_banked": "" if net_b is None else "%.2f" % net_b,
                "net_usd_touch": "" if net_t is None else "%.2f" % net_t,
                "pnl_delta": ""
                if net_b is None or net_t is None
                else "%.2f" % (net_t - net_b),
                "gate_hourly": "" if gate_hourly is None else gate_hourly.isoformat(),
                "gate_1m": "" if gate_1m_same_event is None else gate_1m_same_event.isoformat(),
                "gate_delay_min": ""
                if gate_hourly is None or gate_1m_same_event is None
                else "%.2f" % ((gate_1m_same_event - gate_hourly).total_seconds() / 60.0),
                "arm_lag_hourly_min": ""
                if entry_b is None or gate_hourly is None
                else "%.2f" % ((entry_b - gate_hourly).total_seconds() / 60.0),
                "optimistic_window_span_min": "" if window_span is None else "%.2f" % window_span,
                "optimistic_window_into_min": "" if into_window is None else "%.2f" % into_window,
                "optimistic_window_frac": "" if window_frac is None else "%.4f" % window_frac,
                "lookahead_victim": str(lookahead_victim).lower(),
                "timing_valid": str(timing_valid).lower(),
                "banked_win": "" if net_b is None else str(net_b > 0).lower(),
                "touch_win": "" if net_t is None else str(net_t > 0).lower(),
            }
        )
    return pd.DataFrame(rows).sort_values("day")


def _sum_net(series: pd.Series) -> float:
    return float(pd.to_numeric(series, errors="coerce").fillna(0.0).sum())


def _win_rate(series: pd.Series) -> float:
    vals = pd.to_numeric(series, errors="coerce").dropna()
    if vals.empty:
        return 0.0
    return 100.0 * float((vals > 0).mean())


def write_baselines(tape: pd.DataFrame, output_root: Path) -> Dict[str, Any]:
    both = tape[tape["merge"] == "both"].copy()
    victims = both[both["lookahead_victim"] == "true"]
    valid = both[both["timing_valid"] == "true"]
    same_entry = both[pd.to_numeric(both["entry_delay_min"], errors="coerce").fillna(-1) == 0]
    delayed = both[pd.to_numeric(both["entry_delay_min"], errors="coerce").fillna(0) > 0]

    banked_all = _sum_net(both["net_usd_banked"])
    touch_all = _sum_net(both["net_usd_touch"])
    victim_net = _sum_net(victims["net_usd_banked"])
    valid_net = _sum_net(valid["net_usd_banked"])
    valid_touch_net = _sum_net(valid["net_usd_touch"])

    baselines = {
        "overlapping_campaigns": int(len(both)),
        "banked_net_usd": banked_all,
        "touch_net_usd": touch_all,
        "lookahead_victims_n": int(len(victims)),
        "lookahead_victims_banked_net_usd": victim_net,
        "lookahead_victims_banked_win_pct": _win_rate(victims["net_usd_banked"]),
        "lookahead_victims_share_of_banked_net_pct": (100.0 * victim_net / banked_all) if banked_all else 0.0,
        "timing_valid_n": int(len(valid)),
        "timing_valid_banked_net_usd": valid_net,
        "timing_valid_banked_win_pct": _win_rate(valid["net_usd_banked"]),
        "timing_valid_touch_net_usd": valid_touch_net,
        "timing_valid_touch_win_pct": _win_rate(valid["net_usd_touch"]),
        "same_entry_minute_n": int(len(same_entry)),
        "same_entry_minute_net_usd": _sum_net(same_entry["net_usd_banked"]),
        "delayed_entry_n": int(len(delayed)),
        "delayed_entry_banked_net_usd": _sum_net(delayed["net_usd_banked"]),
        "delayed_entry_touch_net_usd": _sum_net(delayed["net_usd_touch"]),
    }
    with (output_root / "honest_baselines.csv").open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(baselines.keys()))
        writer.writeheader()
        writer.writerow({k: (f"{v:.4f}" if isinstance(v, float) else str(v)) for k, v in baselines.items()})
    victims.to_csv(output_root / "lookahead_victims.csv", index=False)
    valid.to_csv(output_root / "timing_valid_banked_subset.csv", index=False)
    return baselines


def write_index(output_root: Path, baselines: Dict[str, Any], tape: pd.DataFrame) -> None:
    b = baselines
    lines = [
        "# NQ Prior-Opposed Timing Autopsy",
        "",
        "Compares the banked hourly left-label ST gate tape to the 1m first-touch gate tape.",
        "",
        "## Sources",
        "",
        f"- Banked hourly stamp: `{BANKED_ROOT.relative_to(REPO)}`",
        f"- 1m first-touch: `{TOUCH_ROOT.relative_to(REPO)}`",
        "",
        "## Edge attribution (overlapping campaign days)",
        "",
        f"- Overlapping campaigns: **{b['overlapping_campaigns']}**",
        f"- Banked net: **${b['banked_net_usd']:,.2f}**",
        f"- 1m-touch net: **${b['touch_net_usd']:,.2f}**",
        "",
        "| Sleeve | N | Banked net | Banked win % | Notes |",
        "|---|---:|---:|---:|---|",
        (
            f"| Lookahead victims (`entry_banked <= gate_1m`) | {b['lookahead_victims_n']} | "
            f"${b['lookahead_victims_banked_net_usd']:,.2f} | {b['lookahead_victims_banked_win_pct']:.1f} | "
            f"{b['lookahead_victims_share_of_banked_net_pct']:.1f}% of banked net |"
        ),
        (
            f"| Timing-valid (`entry_banked > gate_1m`) | {b['timing_valid_n']} | "
            f"${b['timing_valid_banked_net_usd']:,.2f} | {b['timing_valid_banked_win_pct']:.1f} | "
            f"1m-touch net on same days ${b['timing_valid_touch_net_usd']:,.2f} / "
            f"{b['timing_valid_touch_win_pct']:.1f}% win |"
        ),
        (
            f"| Same entry minute | {b['same_entry_minute_n']} | "
            f"${b['same_entry_minute_net_usd']:,.2f} |  | identical PnL under both stamps |"
        ),
        (
            f"| Delayed entries | {b['delayed_entry_n']} | "
            f"${b['delayed_entry_banked_net_usd']:,.2f} |  | "
            f"1m-touch ${b['delayed_entry_touch_net_usd']:,.2f} |"
        ),
        "",
        "## Honest baselines",
        "",
        "1. **Strict causal prior-opposed:** 1m first-touch fill gate "
        f"({TOUCH_ROOT.name}) — full-book net "
        f"**${b['touch_net_usd']:,.2f}** on overlapping days.",
        "2. **Timing-valid banked subset:** banked campaigns with "
        f"`entry > true 1m gate` — **{b['timing_valid_n']}** campaigns / "
        f"**${b['timing_valid_banked_net_usd']:,.2f}** net / "
        f"**{b['timing_valid_banked_win_pct']:.1f}%** win. This is the diagnostic "
        "upper bound on “same rule, no lookahead.”",
        "",
        "Read: most of the banked headline was early arming inside "
        "`[hourly_stamp, first_1m_touch)`, not a durable day filter.",
        "",
        "## Files",
        "",
        "- `campaign_timing_tape.csv`",
        "- `honest_baselines.csv`",
        "- `lookahead_victims.csv`",
        "- `timing_valid_banked_subset.csv`",
    ]
    (output_root / "INDEX.md").write_text("\n".join(lines) + "\n")


def run(output_root: Path) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    tape = build_campaign_tape(
        BANKED_ROOT / "states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv",
        TOUCH_ROOT / "states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/unit_trades.csv",
        TOUCH_ROOT / "states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3",
    )
    tape.to_csv(output_root / "campaign_timing_tape.csv", index=False)
    baselines = write_baselines(tape, output_root)
    write_index(output_root, baselines, tape)
    return output_root / "INDEX.md"


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args(argv)
    path = run(args.output_root)
    print("Wrote %s" % path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
