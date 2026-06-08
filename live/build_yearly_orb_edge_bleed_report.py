from __future__ import annotations

import argparse
import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .replay_audit import POINT_VALUES, units_from_live_fills


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_CSV = ROOT / "mnq" / "mnq_yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close.csv"
DEFAULT_BROKER_FILLS = ROOT / "live" / "state" / "broker_like_replays" / "states" / "mnq_yearly_orb_scaleout3" / "fills.csv"
DEFAULT_SUMMARY_CSV = ROOT / "live" / "state" / "broker_like_replays" / "summary.csv"
DEFAULT_OUTPUT_ROOT = ROOT / "live" / "state" / "broker_like_replays" / "charts" / "detail" / "mnq_yearly_orb_scaleout3"


@dataclass(frozen=True)
class ResearchTrade:
    year: int
    seq: int
    direction: str
    entry_date: str
    entry_price: float
    final_exit_date: str
    final_reason: str
    net_points: float
    mae_points: float
    mfe_points: float
    result: str


@dataclass(frozen=True)
class BrokerTrade:
    year: int
    seq: int
    trade_id: str
    direction: str
    entry_date: str
    entry_price: float
    final_exit_date: str
    final_reason: str
    net_points: float
    result: str


def build_report(
    *,
    research_csv: Path = DEFAULT_RESEARCH_CSV,
    broker_fills: Path = DEFAULT_BROKER_FILLS,
    summary_csv: Path = DEFAULT_SUMMARY_CSV,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    instrument: str = "MNQ",
) -> Path:
    point_value = POINT_VALUES[instrument]
    output_root.mkdir(parents=True, exist_ok=True)

    research = _read_research_trades(research_csv)
    broker = _read_broker_trades(broker_fills, point_value)
    broker_summary = _read_broker_summary(summary_csv, "mnq_yearly_orb_scaleout3")

    yearly_rows = _yearly_rows(research, broker, point_value)
    paired_rows = _paired_rows(research, broker, point_value)
    yearly_csv = output_root / "theoretical_vs_broker_like_yearly.csv"
    paired_csv = output_root / "theoretical_vs_broker_like_trade_pairs.csv"
    _write_csv(yearly_csv, yearly_rows)
    _write_csv(paired_csv, paired_rows)

    chart_path = output_root / "theoretical_vs_broker_like_by_year.png"
    _plot_yearly(yearly_rows, chart_path)

    report_path = output_root / "THEORETICAL_VS_BROKER_LIKE.md"
    report_path.write_text(
        _report_markdown(
            research=research,
            broker=broker,
            broker_summary=broker_summary,
            yearly_rows=yearly_rows,
            paired_rows=paired_rows,
            point_value=point_value,
            chart_path=chart_path.name,
            yearly_csv=yearly_csv.name,
            paired_csv=paired_csv.name,
        ),
        encoding="utf-8",
    )
    _ensure_index_link(output_root / "INDEX.md", report_path.name, chart_path.name)
    return report_path


def _read_research_trades(path: Path) -> List[ResearchTrade]:
    seq_by_year: Dict[int, int] = defaultdict(int)
    trades: List[ResearchTrade] = []
    for row in _read_csv(path):
        year = int(row["Period"])
        seq_by_year[year] += 1
        exit_dates = [
            row.get("Unit1_Exit_Date", ""),
            row.get("Unit2_Exit_Date", ""),
            row.get("Unit3_Exit_Date", ""),
        ]
        trades.append(
            ResearchTrade(
                year=year,
                seq=seq_by_year[year],
                direction=row.get("Trade_Direction", ""),
                entry_date=row.get("Entry_Date", ""),
                entry_price=float(row.get("Entry_Price") or 0),
                final_exit_date=max((d for d in exit_dates if d), default=""),
                final_reason=row.get("Final_Reason", ""),
                net_points=float(row.get("Trade_PL") or 0),
                mae_points=float(row.get("MAE_Position_Pts") or 0),
                mfe_points=float(row.get("MFE_Price_Pts") or 0),
                result=row.get("Result", ""),
            )
        )
    return trades


def _read_broker_trades(path: Path, point_value: float) -> List[BrokerTrade]:
    units = units_from_live_fills(path, "mnq_yearly_orb_scaleout3")
    grouped: Dict[str, List] = defaultdict(list)
    for unit in units:
        grouped[unit.trade_id].append(unit)
    trades: List[BrokerTrade] = []
    for trade_id, trade_units in grouped.items():
        parts = trade_id.rsplit("_", 2)
        year = int(parts[-2])
        seq = int(parts[-1])
        entry_prices = [u.entry_price for u in trade_units]
        exit_dates = [u.exit_ts[:10] for u in trade_units]
        reasons = Counter(u.exit_reason for u in trade_units)
        net_points = sum(u.points for u in trade_units)
        reason = "+".join(reason for reason, _count in reasons.most_common())
        trades.append(
            BrokerTrade(
                year=year,
                seq=seq,
                trade_id=trade_id,
                direction=trade_units[0].direction,
                entry_date=min(u.entry_ts[:10] for u in trade_units),
                entry_price=sum(entry_prices) / len(entry_prices),
                final_exit_date=max(exit_dates),
                final_reason=reason,
                net_points=net_points,
                result="Win" if round(net_points * point_value, 2) > 0 else "Loss",
            )
        )
    trades.sort(key=lambda t: (t.year, t.seq))
    return trades


def _yearly_rows(research: List[ResearchTrade], broker: List[BrokerTrade], point_value: float) -> List[Dict[str, str]]:
    years = sorted({t.year for t in research} | {t.year for t in broker})
    out: List[Dict[str, str]] = []
    for year in years:
        r = [t for t in research if t.year == year]
        b = [t for t in broker if t.year == year]
        r_points = sum(t.net_points for t in r)
        b_points = sum(t.net_points for t in b)
        out.append(
            {
                "year": str(year),
                "research_trades": str(len(r)),
                "broker_trades": str(len(b)),
                "research_net_usd": "%.2f" % (r_points * point_value),
                "broker_like_net_usd": "%.2f" % (b_points * point_value),
                "edge_bleed_usd": "%.2f" % ((b_points - r_points) * point_value),
                "research_wins": str(sum(1 for t in r if t.net_points > 0)),
                "broker_wins": str(sum(1 for t in b if t.net_points > 0)),
            }
        )
    return out


def _paired_rows(
    research: List[ResearchTrade],
    broker: List[BrokerTrade],
    point_value: float,
) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    by_research = {(t.year, t.seq): t for t in research}
    by_broker = {(t.year, t.seq): t for t in broker}
    keys = sorted(set(by_research) | set(by_broker))
    for year, seq in keys:
        r = by_research.get((year, seq))
        b = by_broker.get((year, seq))
        r_points = r.net_points if r else 0.0
        b_points = b.net_points if b else 0.0
        out.append(
            {
                "year": str(year),
                "seq": str(seq),
                "research_entry": r.entry_date if r else "",
                "broker_entry": b.entry_date if b else "",
                "research_exit": r.final_exit_date if r else "",
                "broker_exit": b.final_exit_date if b else "",
                "research_reason": r.final_reason if r else "missing",
                "broker_reason": b.final_reason if b else "missing",
                "research_net_usd": "%.2f" % (r_points * point_value),
                "broker_like_net_usd": "%.2f" % (b_points * point_value),
                "delta_usd": "%.2f" % ((b_points - r_points) * point_value),
            }
        )
    return out


def _plot_yearly(rows: List[Dict[str, str]], out: Path) -> None:
    years = [row["year"] for row in rows]
    research = [float(row["research_net_usd"]) for row in rows]
    broker = [float(row["broker_like_net_usd"]) for row in rows]
    delta = [float(row["edge_bleed_usd"]) for row in rows]
    x = list(range(len(years)))
    width = 0.36
    fig, (ax, delta_ax) = plt.subplots(2, 1, figsize=(12, 7), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    ax.bar([i - width / 2 for i in x], research, width=width, label="Research/theoretical", color="#2563eb")
    ax.bar([i + width / 2 for i in x], broker, width=width, label="Broker-like replay", color="#16a34a")
    ax.axhline(0, color="#334155", linewidth=0.8)
    ax.set_ylabel("Net USD")
    ax.set_title("MNQ yearly ORB scaleout3: theoretical vs broker-like replay")
    ax.legend(loc="upper left")
    ax.grid(True, axis="y", alpha=0.22)
    colors = ["#16a34a" if value >= 0 else "#dc2626" for value in delta]
    delta_ax.bar(x, delta, color=colors)
    delta_ax.axhline(0, color="#334155", linewidth=0.8)
    delta_ax.set_ylabel("Delta")
    delta_ax.set_xticks(x)
    delta_ax.set_xticklabels(years)
    delta_ax.grid(True, axis="y", alpha=0.22)
    fig.tight_layout()
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _report_markdown(
    *,
    research: List[ResearchTrade],
    broker: List[BrokerTrade],
    broker_summary: Dict[str, str],
    yearly_rows: List[Dict[str, str]],
    paired_rows: List[Dict[str, str]],
    point_value: float,
    chart_path: str,
    yearly_csv: str,
    paired_csv: str,
) -> str:
    research_net = sum(t.net_points for t in research) * point_value
    broker_net = sum(t.net_points for t in broker) * point_value
    research_wins = sum(1 for t in research if t.net_points > 0)
    broker_wins = sum(1 for t in broker if t.net_points > 0)
    largest_bleeds = sorted(paired_rows, key=lambda row: float(row["delta_usd"]))[:8]
    lines = [
        "# MNQ Yearly ORB: Theoretical vs Broker-Like Replay",
        "",
        "This compares the original `yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close` research CSV against the live-runtime `StrategyPlugin` + `PaperBroker` fill book. The trade-pair table is aligned by yearly sequence, so years where broker-like timing skips a campaign should be read as an audit guide rather than a perfect one-to-one fill match.",
        "",
        f"![Theoretical vs broker-like by year]({chart_path})",
        "",
        "## Headline",
        "",
        "| Book | Trades | Wins | Net | Stress / DD note |",
        "|---|---:|---:|---:|---|",
        f"| Research/theoretical CSV | {len(research)} | {research_wins} | {_money(research_net)} | Research one-page sheet reports -$4,604 MTM/open-heat stress. |",
        f"| Broker-like replay fills | {len(broker)} | {broker_wins} | {_money(broker_net)} | Replay summary stress DD: {_money(float(broker_summary.get('intrabar_mtm_dd_usd', '0')))}. |",
        f"| Difference | {len(broker) - len(research)} | {broker_wins - research_wins} | {_money(broker_net - research_net)} | Timing and order-state realism cost both profit and heat profile. |",
        "",
        "## Yearly Delta",
        "",
        "| Year | Research Trades | Broker Trades | Research Net | Broker-Like Net | Delta |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for row in yearly_rows:
        lines.append(
            "| {year} | {research_trades} | {broker_trades} | {research_net_usd} | {broker_like_net_usd} | {edge_bleed_usd} |".format(
                year=row["year"],
                research_trades=row["research_trades"],
                broker_trades=row["broker_trades"],
                research_net_usd=_money(float(row["research_net_usd"])),
                broker_like_net_usd=_money(float(row["broker_like_net_usd"])),
                edge_bleed_usd=_money(float(row["edge_bleed_usd"])),
            )
        )
    lines.extend(
        [
            "",
            "## Largest Sequence-Level Bleeds",
            "",
            "| Year | Seq | Research Entry -> Exit | Broker Entry -> Exit | Research Reason | Broker Reason | Delta |",
            "|---:|---:|---|---|---|---|---:|",
        ]
    )
    for row in largest_bleeds:
        lines.append(
            "| {year} | {seq} | {re} -> {rx} | {be} -> {bx} | {rr} | {br} | {delta} |".format(
                year=row["year"],
                seq=row["seq"],
                re=row["research_entry"] or "missing",
                rx=row["research_exit"] or "missing",
                be=row["broker_entry"] or "missing",
                bx=row["broker_exit"] or "missing",
                rr=row["research_reason"],
                br=row["broker_reason"],
                delta=_money(float(row["delta_usd"])),
            )
        )
    lines.extend(
        [
            "",
            "## Where Value Bleeds",
            "",
            "- The research CSV can record a boundary entry on the breakout/retest day. The broker-like plugin only submits orders after a completed daily close confirms the condition, so fills often occur on a later retest or are skipped.",
            "- Research range-close exits use the daily close level in the CSV. The broker-like strategy currently emits a `market` close intent after the completed daily bar, so the fill is the next tradable daily open in the paper broker.",
            "- Broker bracket stops are active once the parent fills. Some campaigns that were small range-close losses in the research book become full swing-stop losses under broker-like sequencing.",
            "- The broker-like book has fewer filled packages: skipped or delayed entries reduce the number of large runner campaigns that paid for churn in the theoretical result.",
            "",
            "## Artifacts",
            "",
            f"- Yearly comparison CSV: [{yearly_csv}]({yearly_csv})",
            f"- Sequence comparison CSV: [{paired_csv}]({paired_csv})",
            "- Existing broker-like charts: [INDEX.md](INDEX.md)",
            "- Existing theoretical charts: ../../../../../../mnq/case_studies/yearly_orb_swing_stop_scaleout3_inside_range_swing_range_close/INDEX.md",
            "",
            "Potential next experiment: add an explicit `market_close` close-intent mode for daily range-close exits and rerun the broker-like replay. That isolates how much damage comes from next-open fills versus delayed entry/order activation.",
            "",
        ]
    )
    return "\n".join(lines)


def _read_broker_summary(path: Path, slug: str) -> Dict[str, str]:
    for row in _read_csv(path):
        if row.get("slug") == slug:
            return row
    return {}


def _ensure_index_link(index_path: Path, report_name: str, chart_name: str) -> None:
    if not index_path.exists():
        return
    text = index_path.read_text(encoding="utf-8")
    marker = "## Edge-Bleed Audit"
    block = "\n".join(
        [
            marker,
            "",
            f"- [Theoretical vs broker-like comparison]({report_name})",
            f"- [Yearly delta chart]({chart_name})",
            "",
        ]
    )
    if marker in text:
        head = text.split(marker)[0].rstrip()
        tail = "\n".join(text.split(marker)[1].splitlines()[5:])
        text = head + "\n\n" + block + tail
    else:
        text = text.rstrip() + "\n\n" + block
    index_path.write_text(text, encoding="utf-8")


def _read_csv(path: Path) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _money(value: float) -> str:
    sign = "-" if value < 0 else ""
    return "%s$%s" % (sign, f"{abs(value):,.2f}")


def main(argv: Optional[Iterable[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Build yearly ORB theoretical vs broker-like comparison artifacts.")
    parser.add_argument("--research-csv", type=Path, default=DEFAULT_RESEARCH_CSV)
    parser.add_argument("--broker-fills", type=Path, default=DEFAULT_BROKER_FILLS)
    parser.add_argument("--summary-csv", type=Path, default=DEFAULT_SUMMARY_CSV)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    args = parser.parse_args(list(argv) if argv is not None else None)
    report = build_report(
        research_csv=args.research_csv,
        broker_fills=args.broker_fills,
        summary_csv=args.summary_csv,
        output_root=args.output_root,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
