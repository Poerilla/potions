from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, Iterable, List, Optional


def read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    tmp.replace(path)


def money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return sign + f"{abs(value):,.2f}"


def percentile(values: List[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    pos = (len(ordered) - 1) * pct
    lo = int(pos)
    hi = min(lo + 1, len(ordered) - 1)
    frac = pos - lo
    return ordered[lo] * (1.0 - frac) + ordered[hi] * frac


def dd_events(equity_rows: Iterable[Dict[str, str]]) -> List[Dict[str, str]]:
    events: List[Dict[str, str]] = []
    current: Optional[Dict[str, object]] = None
    last_peak_ts = ""
    event_id = 0

    for row in equity_rows:
        ts = row.get("ts", "")
        intrabar_dd = float(row.get("intrabar_dd_usd") or 0.0)
        close_dd = float(row.get("close_dd_usd") or 0.0)

        if current is None and close_dd >= 0.0 and intrabar_dd >= 0.0:
            last_peak_ts = ts
            continue

        if intrabar_dd < 0.0 and current is None:
            event_id += 1
            current = {
                "event_id": event_id,
                "peak_ts": last_peak_ts or ts,
                "start_ts": ts,
                "trough_ts": ts,
                "trough_intrabar_dd_usd": intrabar_dd,
                "duration_bars": 0,
            }

        if current is None:
            continue

        current["duration_bars"] = int(current["duration_bars"]) + 1
        if intrabar_dd < float(current["trough_intrabar_dd_usd"]):
            current["trough_intrabar_dd_usd"] = intrabar_dd
            current["trough_ts"] = ts

        if close_dd >= 0.0:
            events.append(
                {
                    "event_id": str(current["event_id"]),
                    "peak_ts": str(current["peak_ts"]),
                    "start_ts": str(current["start_ts"]),
                    "trough_ts": str(current["trough_ts"]),
                    "recover_ts": ts,
                    "duration_bars": str(current["duration_bars"]),
                    "trough_intrabar_dd_usd": "%.2f" % float(current["trough_intrabar_dd_usd"]),
                    "recovered": "true",
                }
            )
            current = None
            last_peak_ts = ts

    if current is not None:
        events.append(
            {
                "event_id": str(current["event_id"]),
                "peak_ts": str(current["peak_ts"]),
                "start_ts": str(current["start_ts"]),
                "trough_ts": str(current["trough_ts"]),
                "recover_ts": "",
                "duration_bars": str(current["duration_bars"]),
                "trough_intrabar_dd_usd": "%.2f" % float(current["trough_intrabar_dd_usd"]),
                "recovered": "false",
            }
        )
    return events


def summarize_events(slug: str, meta: Dict[str, str], events: List[Dict[str, str]]) -> Dict[str, str]:
    values = [abs(float(event["trough_intrabar_dd_usd"])) for event in events]
    n = len(values)
    max_abs = max(values) if values else 0.0
    p50 = percentile(values, 0.50)
    p75 = percentile(values, 0.75)
    p90 = percentile(values, 0.90)
    p95 = percentile(values, 0.95)
    p99 = percentile(values, 0.99)
    q1 = percentile(values, 0.25)
    q3 = p75
    iqr = max(q3 - q1, 0.0)
    count_50 = len([v for v in values if max_abs and v >= 0.50 * max_abs])
    count_75 = len([v for v in values if max_abs and v >= 0.75 * max_abs])
    count_90 = len([v for v in values if max_abs and v >= 0.90 * max_abs])
    tail_signal = classify_tail(n, max_abs, p95, q3, iqr, count_75, count_90)
    return {
        "slug": slug,
        "candidate": meta.get("candidate", slug),
        "instrument": meta.get("instrument", ""),
        "events": str(n),
        "max_intrabar_stress_dd_usd": "%.2f" % -max_abs,
        "p50_abs_dd_usd": "%.2f" % p50,
        "p75_abs_dd_usd": "%.2f" % p75,
        "p90_abs_dd_usd": "%.2f" % p90,
        "p95_abs_dd_usd": "%.2f" % p95,
        "p99_abs_dd_usd": "%.2f" % p99,
        "events_ge_50pct_max": str(count_50),
        "events_ge_75pct_max": str(count_75),
        "events_ge_90pct_max": str(count_90),
        "tail_signal": tail_signal,
    }


def classify_tail(
    n: int,
    max_abs: float,
    p95: float,
    q3: float,
    iqr: float,
    count_75: int,
    count_90: int,
) -> str:
    if n == 0:
        return "no drawdown events"
    if n < 3:
        return "too few events to classify"
    if count_90 >= 2 or count_75 >= 3:
        return "large stress recurs"
    robust_outlier = iqr > 0 and max_abs > q3 + 1.5 * iqr
    p95_outlier = p95 > 0 and max_abs > 1.35 * p95
    if count_75 == 1 and (robust_outlier or p95_outlier):
        return "max stress is an outlier"
    if count_75 == 1:
        return "max stress is the dominant tail event"
    return "largest stress is elevated but recurring"


def build_report(replay_root: Path) -> List[Dict[str, str]]:
    audits_root = replay_root / "audits"
    summary_rows = read_csv(replay_root / "summary.csv")
    meta_by_slug = {row.get("slug", ""): row for row in summary_rows}
    rows: List[Dict[str, str]] = []
    for equity_path in sorted(audits_root.glob("*/equity_curve.csv")):
        slug = equity_path.parent.name
        events = dd_events(read_csv(equity_path))
        write_csv(equity_path.parent / "intrabar_stress_dd_events.csv", events)
        row = summarize_events(slug, meta_by_slug.get(slug, {}), events)
        write_csv(equity_path.parent / "intrabar_stress_dd_distribution.csv", [row])
        rows.append(row)
    rows.sort(key=lambda row: abs(float(row["max_intrabar_stress_dd_usd"])), reverse=True)
    write_csv(replay_root / "intrabar_stress_dd_distribution_summary.csv", rows)
    write_markdown(replay_root / "INTRABAR_STRESS_DD_DISTRIBUTIONS.md", rows)
    return rows


def write_markdown(path: Path, rows: List[Dict[str, str]]) -> None:
    lines = [
        "# Intrabar Stress DD Distributions",
        "",
        "Each event is one peak-to-trough intrabar stress cycle. The peak is based on close-equity highs; the trough uses the intrabar stress equity from the replay. Per-strategy event files live next to each `equity_curve.csv` as `intrabar_stress_dd_events.csv`.",
        "",
        "| Candidate | Instrument | Events | Max Stress DD | P50 | P75 | P90 | P95 | >=75% Max | >=90% Max | Tail Signal |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            "| %s | %s | %s | $%s | $%s | $%s | $%s | $%s | %s | %s | %s |"
            % (
                row["candidate"],
                row["instrument"],
                row["events"],
                money(float(row["max_intrabar_stress_dd_usd"])),
                money(float(row["p50_abs_dd_usd"])),
                money(float(row["p75_abs_dd_usd"])),
                money(float(row["p90_abs_dd_usd"])),
                money(float(row["p95_abs_dd_usd"])),
                row["events_ge_75pct_max"],
                row["events_ge_90pct_max"],
                row["tail_signal"],
            )
        )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Report peak-to-trough intrabar stress drawdown distributions.")
    parser.add_argument("--replay-root", type=Path, required=True)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    rows = build_report(args.replay_root)
    print("Wrote %d drawdown distribution rows under %s" % (len(rows), args.replay_root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
