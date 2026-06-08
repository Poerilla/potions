from __future__ import annotations

import argparse
import csv
import json
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .models import Bar, StrategyInstance
from .replay_audit import POINT_VALUES
from .strategies.atr_supertrend_dca import _supertrend


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPLAY_ROOT = ROOT / "live" / "state" / "monthly_overlap_st_retest_broker_like"
DEFAULT_OUTPUT_ROOT = DEFAULT_REPLAY_ROOT / "charts" / "detail"
DEFAULT_MARKETS = ("nq", "mnq")

REALISM_CAPTION = (
    "Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, "
    "stop gap-through ON, stop-first same-bar, OCO-collapsed risk."
)


@dataclass(frozen=True)
class Fill:
    trade_id: str
    side: str
    quantity: int
    price: float
    ts: str
    reason: str

    @property
    def dt(self) -> datetime:
        return _parse_dt(self.ts)

    @property
    def is_entry(self) -> bool:
        return self.side == "buy" and self.reason in {"entry", "runner_entry"}


@dataclass(frozen=True)
class UnitFill:
    trade_id: str
    entry_ts: str
    exit_ts: str
    exit_reason: str
    points: float
    usd: float


@dataclass(frozen=True)
class SummaryRow:
    slug: str
    candidate: str
    instrument: str
    net_usd: float
    stress_dd_usd: float
    ratio: float


def build_charts(
    replay_root: Path = DEFAULT_REPLAY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    markets: Iterable[str] = DEFAULT_MARKETS,
) -> List[Path]:
    csv.field_size_limit(100_000_000)
    summary = _summary_rows(replay_root / "summary.csv")
    built: List[Path] = []
    selected = [str(m).lower() for m in markets]
    output_root.mkdir(parents=True, exist_ok=True)

    for market in selected:
        slug = f"{market}_monthly_overlap_daily_st_retest5"
        state_dir = replay_root / "states" / slug
        audit_dir = replay_root / "audits" / slug
        if not state_dir.exists():
            continue
        instance = _read_instance(state_dir / "strategy_instances.csv")
        if instance is None:
            continue
        row = summary.get(slug) or SummaryRow(slug, slug, instance.instrument, 0.0, 0.0, 0.0)
        bars = _read_bars(state_dir / "bars" / f"{instance.instrument}_4H.csv")
        fills = _read_fills(state_dir / "fills.csv")
        unit_fills = _read_unit_fills(audit_dir / "unit_fills.csv")
        trades = _primary_trades(state_dir / "strategy_state.csv")
        cfg = _config(instance)
        daily_bars = _read_daily_bars(Path(str(cfg.get("daily_bars_path") or "")), instance.instrument)
        st_by_day = _confirmed_daily_supertrend(daily_bars, int(cfg.get("atr_len", 14)), float(cfg.get("atr_mult", 3.0)))
        candidate_root = output_root / slug
        candidate_root.mkdir(parents=True, exist_ok=True)
        built.extend(_build_candidate_charts(candidate_root, row, instance, bars, fills, unit_fills, trades, st_by_day))

    _write_master_index(output_root, summary, selected)
    return built


def _build_candidate_charts(
    out_root: Path,
    row: SummaryRow,
    instance: StrategyInstance,
    bars: List[Bar],
    fills: List[Fill],
    unit_fills: List[UnitFill],
    trades: List[Tuple[str, Dict[str, Any]]],
    st_by_day: Dict[str, Tuple[Optional[float], bool]],
) -> List[Path]:
    fill_by_trade: Dict[str, List[Fill]] = {}
    for fill in fills:
        fill_by_trade.setdefault(fill.trade_id, []).append(fill)
    unit_by_trade: Dict[str, List[UnitFill]] = {}
    for unit in unit_fills:
        unit_by_trade.setdefault(unit.trade_id, []).append(unit)

    built: List[Path] = []
    index_rows: List[Dict[str, str]] = []
    for seq, (trade_id, trade) in enumerate(trades, start=1):
        retest_trade_id = str(trade.get("retest_trade_id") or f"{trade_id}_retest")
        related_fills = sorted(fill_by_trade.get(trade_id, []) + fill_by_trade.get(retest_trade_id, []), key=lambda fill: fill.dt)
        related_units = unit_by_trade.get(trade_id, []) + unit_by_trade.get(retest_trade_id, [])
        pnl = sum(unit.usd for unit in related_units)
        outcome = "no_fill"
        if related_units:
            outcome = "win" if pnl > 0 else "loss" if pnl < 0 else "flat"
        elif related_fills:
            outcome = "open_or_unpaired"

        start_dt, end_dt = _chart_window(trade, related_fills, related_units)
        chart_bars = [bar for bar in bars if start_dt <= _parse_dt(bar.ts) <= end_dt]
        if not chart_bars:
            continue
        year = _trade_year(trade_id, chart_bars)
        out = out_root / f"{year}" / f"{seq:03d}_{_safe_trade_name(trade_id)}_{outcome}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        _plot_trade_chart(out, row, instance, trade_id, trade, chart_bars, related_fills, related_units, st_by_day, pnl, outcome)
        built.append(out)
        index_rows.append(
            {
                "year": str(year),
                "path": str(out.relative_to(out_root)),
                "trade_id": trade_id,
                "months": str(trade.get("months") or ""),
                "status": str(trade.get("status") or ""),
                "outcome": outcome,
                "pnl": f"{pnl:.2f}",
                "fills": str(len(related_fills)),
                "retest": "yes" if fill_by_trade.get(retest_trade_id) else "no",
            }
        )

    _write_candidate_index(out_root, row, instance, index_rows)
    return built


def _plot_trade_chart(
    out: Path,
    row: SummaryRow,
    instance: StrategyInstance,
    trade_id: str,
    trade: Dict[str, Any],
    bars: List[Bar],
    fills: List[Fill],
    unit_fills: List[UnitFill],
    st_by_day: Dict[str, Tuple[Optional[float], bool]],
    pnl: float,
    outcome: str,
) -> None:
    fig, (ax, eq_ax) = plt.subplots(
        2,
        1,
        figsize=(15.5, 8.5),
        sharex=True,
        gridspec_kw={"height_ratios": [4.4, 1]},
    )
    x_map = _plot_candles(ax, bars)
    range_high = float(trade["range_high"])
    range_low = float(trade["range_low"])
    range_size = float(trade["range_size"])
    tp50 = float(trade.get("tp50", range_high + range_size * 0.5))
    tp1 = float(trade.get("tp1", range_high + range_size))
    tp2 = float(trade.get("tp2", range_high + range_size * 2.0))
    close_stop = range_high - 0.25 * range_size

    ax.axhspan(range_low, range_high, color="#93c5fd", alpha=0.13, label="Combined overlap range")
    _hline(ax, range_high, "#2563eb", "Range high / breakout stop", 1.5)
    _hline(ax, range_low, "#7c3aed", "Range low", 1.3)
    _hline(ax, close_stop, "#f97316", "25% close-back line", 1.1, "--")
    _hline(ax, tp50, "#0ea5e9", "TP50", 1.0, ":")
    _hline(ax, tp1, "#22c55e", "TP1", 1.15, ":")
    _hline(ax, tp2, "#16a34a", "TP2 / runner target", 1.15, "--")
    _plot_daily_supertrend(ax, bars, st_by_day)
    _plot_fills(ax, x_map, fills)

    if fills:
        first = min(fill.dt for fill in fills)
        last = max(fill.dt for fill in fills)
        if _date_to_x(bars, first.date()) is not None:
            ax.axvline(_date_to_x(bars, first.date()), color="#111827", linewidth=0.9, alpha=0.35)
        if _date_to_x(bars, last.date()) is not None:
            ax.axvline(_date_to_x(bars, last.date()), color="#111827", linewidth=0.9, alpha=0.35)

    _plot_trade_pnl(eq_ax, unit_fills)
    title = (
        f"{instance.instrument} overlap daily-ST retest x5 - {trade_id}\n"
        f"months {trade.get('months')} | status {trade.get('status')} | {outcome} | "
        f"trade P/L ${pnl:,.2f} | replay net ${row.net_usd:,.0f}, stress DD ${row.stress_dd_usd:,.0f}, Net/DD {row.ratio:.2f}"
    )
    ax.set_title(title)
    ax.set_ylabel("Price")
    ax.grid(True, alpha=0.16)
    handles, labels = ax.get_legend_handles_labels()
    seen = set()
    uniq = [(h, l) for h, l in zip(handles, labels) if not (l in seen or seen.add(l))]
    ax.legend([h for h, _ in uniq], [l for _, l in uniq], loc="upper left", fontsize=7, ncol=2)
    _format_xaxis(ax, bars)
    fig.tight_layout()
    fig.text(0.01, 0.005, REALISM_CAPTION, fontsize=7, color="#475569", ha="left")
    fig.savefig(out, dpi=145)
    plt.close(fig)


def _plot_candles(ax: Any, bars: List[Bar]) -> Dict[str, int]:
    x_map: Dict[str, int] = {}
    width = 0.62 if len(bars) > 45 else 0.74
    for idx, bar in enumerate(bars):
        x_map[bar.ts] = idx
        up = bar.close >= bar.open
        color = "#089981" if up else "#f23645"
        ax.vlines(idx, bar.low, bar.high, color=color, linewidth=0.9, alpha=0.95)
        lower = min(bar.open, bar.close)
        height = abs(bar.close - bar.open)
        if height <= 0:
            height = max((bar.high - bar.low) * 0.012, 0.01)
        ax.add_patch(
            Rectangle(
                (idx - width / 2.0, lower),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.5,
                alpha=0.88,
            )
        )
    ax.set_xlim(-1, max(len(bars), 1))
    return x_map


def _plot_daily_supertrend(ax: Any, bars: List[Bar], st_by_day: Dict[str, Tuple[Optional[float], bool]]) -> None:
    first_bull = True
    first_bear = True
    for bullish in (True, False):
        xs: List[int] = []
        ys: List[float] = []
        for idx, bar in enumerate(bars):
            stop, is_bull = st_by_day.get(bar.ts[:10], (None, False))
            if stop is not None and is_bull == bullish:
                xs.append(idx)
                ys.append(float(stop))
            elif xs:
                label = "Confirmed daily ST bullish" if bullish and first_bull else "Confirmed daily ST bearish" if (not bullish and first_bear) else None
                ax.plot(xs, ys, color="#22c55e" if bullish else "#ef4444", linewidth=1.5, label=label)
                first_bull = first_bull and not bullish
                first_bear = first_bear and bullish
                xs = []
                ys = []
        if xs:
            label = "Confirmed daily ST bullish" if bullish and first_bull else "Confirmed daily ST bearish" if (not bullish and first_bear) else None
            ax.plot(xs, ys, color="#22c55e" if bullish else "#ef4444", linewidth=1.5, label=label)


def _plot_fills(ax: Any, x_map: Dict[str, int], fills: List[Fill]) -> None:
    if not fills:
        return
    prices = [fill.price for fill in fills]
    y_span = max(prices) - min(prices)
    if y_span <= 0:
        y_span = max(prices[0] * 0.01, 1.0)
    bump = y_span * 0.04
    for fill in fills:
        x = _nearest_x_for_ts(x_map, fill.ts)
        if x is None:
            continue
        is_retest = "_retest" in fill.trade_id
        if fill.side == "buy":
            marker = "^"
            color = "#16a34a" if not is_retest else "#0f766e"
            label = "Primary entry" if not is_retest else "ST retest add"
            y_text = fill.price + bump
            va = "bottom"
        else:
            marker = "v"
            color = "#dc2626" if fill.reason not in {"tp50", "tp1", "runner_target"} else "#2563eb"
            label = "Exit"
            y_text = fill.price - bump
            va = "top"
        size = 60 if fill.quantity <= 1 else 90
        ax.scatter([x], [fill.price], marker=marker, s=size, color=color, edgecolor="black", linewidth=0.4, zorder=6, label=label)
        txt = f"{fill.reason} x{fill.quantity}"
        ax.text(x, y_text, txt, fontsize=6.4, ha="center", va=va, color=color)


def _plot_trade_pnl(ax: Any, unit_fills: List[UnitFill]) -> None:
    if not unit_fills:
        ax.axis("off")
        ax.text(0.02, 0.5, "No fills", transform=ax.transAxes, fontsize=9, color="#475569")
        return
    units = sorted(unit_fills, key=lambda u: (u.exit_ts, u.trade_id))
    xs = list(range(len(units)))
    cumulative: List[float] = []
    total = 0.0
    colors = []
    for unit in units:
        total += unit.usd
        cumulative.append(total)
        colors.append("#0f766e" if unit.usd >= 0 else "#dc2626")
    ax.bar(xs, [unit.usd for unit in units], color=colors, alpha=0.5, label="Unit P/L")
    ax.plot(xs, cumulative, color="#111827", linewidth=1.2, marker="o", markersize=3, label="Trade cumulative")
    ax.axhline(0, color="#64748b", linewidth=0.8)
    ax.grid(True, alpha=0.16)
    ax.set_ylabel("USD")
    ax.legend(loc="upper left", fontsize=7)


def _hline(ax: Any, y: float, color: str, label: str, linewidth: float, linestyle: str = "-") -> None:
    ax.axhline(y, color=color, linewidth=linewidth, linestyle=linestyle, label=label)


def _nearest_x_for_ts(x_map: Dict[str, int], ts: str) -> Optional[int]:
    if ts in x_map:
        return x_map[ts]
    target = _parse_dt(ts)
    best_key: Optional[str] = None
    best_delta: Optional[float] = None
    for key in x_map:
        delta = abs((_parse_dt(key) - target).total_seconds())
        if best_delta is None or delta < best_delta:
            best_key = key
            best_delta = delta
    return x_map[best_key] if best_key is not None and best_delta is not None and best_delta <= 12 * 3600 else None


def _date_to_x(bars: List[Bar], d: Any) -> Optional[int]:
    for idx, bar in enumerate(bars):
        if _parse_dt(bar.ts).date() >= d:
            return idx
    return None


def _format_xaxis(ax: Any, bars: List[Bar]) -> None:
    if not bars:
        return
    step = max(len(bars) // 9, 1)
    ticks = list(range(0, len(bars), step))
    if ticks[-1] != len(bars) - 1:
        ticks.append(len(bars) - 1)
    labels = [_parse_dt(bars[idx].ts).strftime("%Y-%m-%d") for idx in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=28, ha="right", fontsize=8)


def _chart_window(trade: Dict[str, Any], fills: List[Fill], unit_fills: List[UnitFill]) -> Tuple[datetime, datetime]:
    months = _trade_months(trade)
    if months:
        first_month = months[0]
        last_month = months[-1]
        start = datetime(first_month[0], first_month[1], 1) - timedelta(days=4)
        end_day = monthrange(last_month[0], last_month[1])[1]
        end = datetime(last_month[0], last_month[1], end_day, 23, 59) + timedelta(days=7)
    else:
        start = datetime(2000, 1, 1)
        end = datetime(2000, 1, 31)
    for fill in fills:
        start = min(start, fill.dt - timedelta(days=7))
        end = max(end, fill.dt + timedelta(days=7))
    for unit in unit_fills:
        start = min(start, _parse_dt(unit.entry_ts) - timedelta(days=7))
        end = max(end, _parse_dt(unit.exit_ts) + timedelta(days=7))
    # Keep very long runners readable while still showing the important exit.
    if (end - start).days > 250 and fills:
        start = min(fill.dt for fill in fills) - timedelta(days=20)
    return start, end


def _trade_months(trade: Dict[str, Any]) -> List[Tuple[int, int]]:
    raw = str(trade.get("months") or "")
    months: List[Tuple[int, int]] = []
    for part in raw.split("+"):
        if len(part) >= 7:
            months.append((int(part[:4]), int(part[5:7])))
    return months


def _trade_year(trade_id: str, bars: List[Bar]) -> int:
    parts = trade_id.split("_")
    for part in parts:
        if len(part) == 8 and part.isdigit():
            return int(part[:4])
    return _parse_dt(bars[0].ts).year


def _safe_trade_name(trade_id: str) -> str:
    parts = trade_id.split("_")
    compact = "_".join(parts[-3:]) if len(parts) >= 3 else trade_id
    return "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in compact)


def _primary_trades(path: Path) -> List[Tuple[str, Dict[str, Any]]]:
    rows = _read_csv(path)
    if not rows:
        return []
    state = json.loads(rows[0]["state_json"])
    trades = state.get("trades", {})
    out = [(trade_id, trade) for trade_id, trade in trades.items() if trade.get("kind") == "primary"]
    out.sort(key=lambda kv: (_trade_sort_key(kv[0]), kv[0]))
    return out


def _trade_sort_key(trade_id: str) -> str:
    for part in trade_id.split("_"):
        if len(part) == 8 and part.isdigit():
            return part
    return trade_id


def _confirmed_daily_supertrend(daily_bars: List[Bar], atr_len: int, atr_mult: float) -> Dict[str, Tuple[Optional[float], bool]]:
    points = _supertrend(daily_bars, atr_len, atr_mult)
    by_day = {point.ts[:10]: point for point in points}
    out: Dict[str, Tuple[Optional[float], bool]] = {}
    previous = None
    for bar in daily_bars:
        day = bar.ts[:10]
        out[day] = (previous.stop, previous.bullish) if previous is not None else (None, False)
        previous = by_day.get(day, previous)
    return out


def _read_daily_bars(path: Path, instrument: str) -> List[Bar]:
    out: List[Bar] = []
    for row in _read_csv(path):
        out.append(
            Bar(
                instrument=instrument,
                timeframe="D",
                ts=str(row.get("date") or row.get("ts")),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume") or 0.0),
                complete=True,
                source=str(path),
            )
        )
    out.sort(key=lambda bar: bar.ts)
    return out


def _read_bars(path: Path) -> List[Bar]:
    bars = [Bar.from_row(row) for row in _read_csv(path)]
    bars.sort(key=lambda bar: bar.ts)
    return bars


def _read_fills(path: Path) -> List[Fill]:
    fills: List[Fill] = []
    for row in _read_csv(path):
        fills.append(
            Fill(
                trade_id=str(row["trade_id"]),
                side=str(row["side"]),
                quantity=int(float(row["quantity"] or 0)),
                price=float(row["price"] or 0),
                ts=str(row["ts"]),
                reason=str(row["reason"]),
            )
        )
    fills.sort(key=lambda fill: (fill.ts, fill.trade_id, fill.reason))
    return fills


def _read_unit_fills(path: Path) -> List[UnitFill]:
    out: List[UnitFill] = []
    for row in _read_csv(path):
        out.append(
            UnitFill(
                trade_id=str(row["trade_id"]),
                entry_ts=str(row["entry_ts"]),
                exit_ts=str(row["exit_ts"]),
                exit_reason=str(row["exit_reason"]),
                points=float(row["points"] or 0),
                usd=float(row["usd"] or 0),
            )
        )
    return out


def _read_instance(path: Path) -> Optional[StrategyInstance]:
    rows = _read_csv(path)
    return StrategyInstance.from_row(rows[0]) if rows else None


def _summary_rows(path: Path) -> Dict[str, SummaryRow]:
    out: Dict[str, SummaryRow] = {}
    for row in _read_csv(path):
        out[str(row["slug"])] = SummaryRow(
            slug=str(row["slug"]),
            candidate=str(row["candidate"]),
            instrument=str(row["instrument"]),
            net_usd=float(row["net_usd"]),
            stress_dd_usd=float(row["intrabar_mtm_dd_usd"]),
            ratio=float(row["net_over_stress_dd"]),
        )
    return out


def _config(instance: StrategyInstance) -> Dict[str, Any]:
    try:
        return json.loads(instance.config_json or "{}")
    except json.JSONDecodeError:
        return {}


def _read_csv(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _parse_dt(value: str) -> datetime:
    text = str(value).replace("T", " ").replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


def _write_candidate_index(out_root: Path, row: SummaryRow, instance: StrategyInstance, rows: List[Dict[str, str]]) -> None:
    by_year: Dict[str, List[Dict[str, str]]] = {}
    for item in rows:
        by_year.setdefault(item["year"], []).append(item)
    lines = [
        f"# {instance.instrument} Monthly Overlap Daily-ST Retest x5",
        "",
        "Broker-like 4h validation charts generated from persisted `Engine` + `PaperBroker` fills.",
        "",
        f"> {REALISM_CAPTION}",
        "",
        f"- Candidate: {row.candidate}",
        f"- Net: `${row.net_usd:,.2f}`",
        f"- Intrabar stress DD: `${row.stress_dd_usd:,.2f}`",
        f"- Net / stress DD: `{row.ratio:.2f}`",
        f"- Charts: `{len(rows)}` primary overlap attempts, including no-fill cancelled attempts.",
        "",
    ]
    for year in sorted(by_year):
        lines.append(f"## {year}")
        lines.append("")
        lines.append("| Chart | Months | Status | Outcome | P/L | Fills | Retest |")
        lines.append("|---|---|---|---|---:|---:|---|")
        for item in by_year[year]:
            lines.append(
                f"| [{item['trade_id']}]({item['path']}) | {item['months']} | {item['status']} | "
                f"{item['outcome']} | ${float(item['pnl']):,.2f} | {item['fills']} | {item['retest']} |"
            )
        lines.append("")
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_master_index(output_root: Path, summary: Dict[str, SummaryRow], markets: List[str]) -> None:
    lines = [
        "# Monthly Overlap Daily-ST Retest x5 Charts",
        "",
        "Focused validation chart packs for the broker-like 4h replay. Candles are replay bars; fills are persisted `PaperBroker` fills; the green/red line is the confirmed daily Supertrend stop available to the strategy.",
        "",
        f"> {REALISM_CAPTION}",
        "",
        "| Market | Net | Stress DD | Net/DD | Charts |",
        "|---|---:|---:|---:|---|",
    ]
    for market in markets:
        slug = f"{market}_monthly_overlap_daily_st_retest5"
        row = summary.get(slug)
        index = output_root / slug / "INDEX.md"
        if row is None or not index.exists():
            continue
        lines.append(
            f"| {row.instrument} | ${row.net_usd:,.2f} | ${row.stress_dd_usd:,.2f} | "
            f"{row.ratio:.2f} | [{slug}]({slug}/INDEX.md) |"
        )
    lines.append("")
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build monthly overlap ST-retest validation charts.")
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--markets", default=",".join(DEFAULT_MARKETS), help="Comma-separated market list, e.g. nq,mnq")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    markets = [part.strip().lower() for part in str(args.markets).split(",") if part.strip()]
    built = build_charts(args.replay_root, args.output_root, markets)
    print(f"Wrote {len(built)} charts under {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
