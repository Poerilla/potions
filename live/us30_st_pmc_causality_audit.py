"""Causality and 1m-fill audit for the US30 ST+PMC runner-variant hub."""

from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
DEFAULT_HUB = REPO / "live" / "state" / "us30_st_pmc_runner_variants"
DEFAULT_1M = REPO / "fx" / "us30_1m.csv"
NY = "America/New_York"


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _write_csv(path: Path, rows: Iterable[Dict[str, object]], fields: List[str]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _to_float(value: object) -> Optional[float]:
    if value is None or str(value).strip() == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _ts_for_index(value: str, idx_tz) -> Optional[pd.Timestamp]:
    if value is None or str(value).strip() == "":
        return None
    try:
        ts = pd.Timestamp(str(value))
    except Exception:
        return None
    if idx_tz is not None:
        if ts.tzinfo is None:
            return ts.tz_localize(idx_tz)
        return ts.tz_convert(idx_tz)
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)
    return ts


def _ts_utc_naive(value: str) -> Optional[pd.Timestamp]:
    if value is None or str(value).strip() == "":
        return None
    try:
        ts = pd.Timestamp(str(value))
    except Exception:
        return None
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)
    return ts


def _feature_order_violations(features: List[Dict[str, str]]) -> int:
    violations = 0
    for row in features:
        event_ts = _ts_utc_naive(row.get("event_ts", ""))
        available_at = _ts_utc_naive(row.get("available_at_ts", ""))
        current_bar = _ts_utc_naive(row.get("current_bar_ts", ""))
        if event_ts is None or available_at is None or current_bar is None:
            violations += 1
            continue
        if event_ts > available_at or available_at > current_bar:
            violations += 1
    return violations


def _touch_ok(order: Dict[str, str], fill: Dict[str, str], bar: pd.Series) -> Tuple[bool, str]:
    order_type = str(order.get("order_type") or "").lower()
    side = str(fill.get("side") or order.get("side") or "").lower()
    price = _to_float(fill.get("price"))
    limit_price = _to_float(order.get("limit_price"))
    stop_price = _to_float(order.get("stop_price"))
    high = float(bar["high"])
    low = float(bar["low"])
    eps = 1e-9

    if order_type == "market":
        return True, ""
    if order_type == "limit":
        ref = limit_price if limit_price is not None else price
        if ref is None:
            return False, "missing_limit_reference"
        if side == "buy":
            return low <= ref + eps, "limit_not_touched"
        if side == "sell":
            return high >= ref - eps, "limit_not_touched"
        return False, "unknown_limit_side"
    if order_type == "stop":
        ref = stop_price if stop_price is not None else price
        if ref is None:
            return False, "missing_stop_reference"
        if side == "buy":
            return high >= ref - eps, "stop_not_touched"
        if side == "sell":
            return low <= ref + eps, "stop_not_touched"
        return False, "unknown_stop_side"
    return False, "unknown_order_type_%s" % order_type


def audit_state(state_root: Path, one_m: pd.DataFrame) -> Dict[str, object]:
    orders = _read_csv(state_root / "orders.csv")
    fills = _read_csv(state_root / "fills.csv")
    features = _read_csv(state_root / "feature_snapshots.csv")
    causal_rows = _read_csv(state_root / "causality_violations.csv")
    orders_by_id = {str(row.get("broker_order_id") or ""): row for row in orders}
    idx_tz = getattr(one_m.index, "tz", None)

    missing_1m = 0
    live_after_violations = 0
    touch_violations = 0
    unsupported_touch = 0
    entry_fills = 0
    min_entry_delay_s: Optional[float] = None
    same_ts_fills = 0

    sample_rows: List[Dict[str, object]] = []
    for fill in fills:
        fill_ts = _ts_for_index(fill.get("ts", ""), idx_tz)
        order = orders_by_id.get(str(fill.get("broker_order_id") or ""), {})
        if str(order.get("reduce_only") or "").lower() not in {"true", "1", "yes"}:
            entry_fills += 1
        if fill_ts is None or fill_ts not in one_m.index:
            missing_1m += 1
            continue

        live_after_raw = str(order.get("live_after_ts") or "")
        live_after = _ts_for_index(live_after_raw, idx_tz)
        if live_after is not None:
            delay = (fill_ts - live_after).total_seconds()
            if delay <= 0:
                live_after_violations += 1
                if delay == 0:
                    same_ts_fills += 1
            if str(order.get("reduce_only") or "").lower() not in {"true", "1", "yes"}:
                min_entry_delay_s = delay if min_entry_delay_s is None else min(min_entry_delay_s, delay)

        ok, reason = _touch_ok(order, fill, one_m.loc[fill_ts])
        if not ok:
            if reason.startswith("unknown_order_type"):
                unsupported_touch += 1
            else:
                touch_violations += 1
            if len(sample_rows) < 10:
                sample_rows.append(
                    {
                        "fill_id": fill.get("fill_id", ""),
                        "ts": fill.get("ts", ""),
                        "order_type": order.get("order_type", ""),
                        "side": fill.get("side", ""),
                        "price": fill.get("price", ""),
                        "limit_price": order.get("limit_price", ""),
                        "stop_price": order.get("stop_price", ""),
                        "reason": reason,
                    }
                )

    status = "PASS"
    blocking = []
    feature_order_violations = _feature_order_violations(features)
    if causal_rows:
        blocking.append("causality_violations_present")
    if feature_order_violations:
        blocking.append("feature_timestamp_order_violations")
    if missing_1m:
        blocking.append("fills_missing_1m_bar")
    if live_after_violations:
        blocking.append("fills_at_or_before_live_after")
    if touch_violations:
        blocking.append("fill_price_not_supported_by_1m_bar")
    if blocking:
        status = "FAIL"

    return {
        "variant": state_root.name.replace("us30_hourly_st_pmc_", ""),
        "state_root": str(state_root.relative_to(REPO)),
        "fills": len(fills),
        "entry_fills": entry_fills,
        "orders": len(orders),
        "feature_snapshots": len(features),
        "causality_violation_rows": len(causal_rows),
        "feature_order_violations": feature_order_violations,
        "fills_missing_1m_bar": missing_1m,
        "live_after_violations": live_after_violations,
        "same_timestamp_fills": same_ts_fills,
        "touch_violations": touch_violations,
        "unsupported_touch_checks": unsupported_touch,
        "min_entry_delay_seconds": "" if min_entry_delay_s is None else round(min_entry_delay_s, 3),
        "status": status,
        "blocking_reasons": ",".join(blocking),
        "_samples": sample_rows,
    }


def load_us30_1m(path: Path) -> pd.DataFrame:
    by_day = load_fx_1m_by_ny_date(path, "US30")
    return concat_all_1m(by_day).sort_index()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hub", default=str(DEFAULT_HUB))
    ap.add_argument("--one-m", default=str(DEFAULT_1M))
    args = ap.parse_args()

    hub = Path(args.hub)
    one_m = load_us30_1m(Path(args.one_m))
    states = sorted((hub / "states").glob("us30_hourly_st_pmc_*"))
    rows = [audit_state(state, one_m) for state in states if state.is_dir()]

    fields = [
        "variant",
        "state_root",
        "fills",
        "entry_fills",
        "orders",
        "feature_snapshots",
        "causality_violation_rows",
        "feature_order_violations",
        "fills_missing_1m_bar",
        "live_after_violations",
        "same_timestamp_fills",
        "touch_violations",
        "unsupported_touch_checks",
        "min_entry_delay_seconds",
        "status",
        "blocking_reasons",
    ]
    _write_csv(hub / "causality_fill_audit.csv", [{k: v for k, v in row.items() if k in fields} for row in rows], fields)

    all_pass = all(row["status"] == "PASS" for row in rows)
    lines = [
        "# US30 ST+PMC Causality And 1m Fill Audit",
        "",
        "**Scope:** US30 ST+PMC fair 3R and runner variants in this hub.",
        "",
        "**Conclusion:** %s" % ("PASS" if all_pass else "FAIL"),
        "",
        "The replay now treats left-labeled hourly candles as completed one hour later. "
        "Signals are processed with `broker_fills=False`; fills are accepted only from the 1m tape.",
        "",
        "## Variant Audit Table",
        "",
        "| Variant | Fills | Entry fills | Feature snapshots | Causal rows | Feature order fails | Missing 1m | live_after fails | Touch fails | Min entry delay (s) | Status |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| `{variant}` | {fills} | {entry_fills} | {feature_snapshots} | {causality_violation_rows} | "
            "{feature_order_violations} | {fills_missing_1m_bar} | {live_after_violations} | "
            "{touch_violations} | {min_entry_delay_seconds} | **{status}** |".format(**row)
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "- `causality_violation_rows=0` means the engine-level `CausalityGuard` did not record feature/order causality errors.",
            "- `feature_order_fails=0` means every snapshot satisfied `event_ts <= available_at_ts <= current_bar_ts`.",
            "- `live_after_fails=0` means no fill occurred at or before the order's activation timestamp.",
            "- `missing_1m=0` and `touch_fails=0` mean every fill timestamp exists on the 1m source tape and the bar supports the fill type/price.",
            "- A low `min_entry_delay_seconds` is acceptable only if it is positive; it means price touched soon after a completed-hour signal, not before it.",
        ]
    )
    sample_lines = []
    for row in rows:
        samples = row.get("_samples") or []
        if samples:
            sample_lines.append("")
            sample_lines.append("### Unsupported Samples: `%s`" % row["variant"])
            for sample in samples:
                sample_lines.append("- `%s`" % sample)
    if sample_lines:
        lines.extend(["", "## Samples"] + sample_lines)
    (hub / "CAUSALITY_AUDIT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote", hub / "CAUSALITY_AUDIT.md")
    print("status", "PASS" if all_pass else "FAIL")
    return 0 if all_pass else 2


if __name__ == "__main__":
    raise SystemExit(main())
