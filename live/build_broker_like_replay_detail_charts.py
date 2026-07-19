from __future__ import annotations

import argparse
import csv
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .models import Bar, StrategyInstance
from .replay_audit import POINT_VALUES
from .strategies.atr_supertrend_dca import _completed_weekly_bars, _parse_date, _supertrend


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPLAY_ROOT = ROOT / "live" / "state" / "broker_like_replays"
DEFAULT_OUTPUT_ROOT = DEFAULT_REPLAY_ROOT / "charts" / "detail"

REALISM_CAPTION = (
    "Realism baseline (2026-05-20): slippage=1 tick, fee=$1.50/RT, "
    "stop gap-through ON, stop-first same-bar, OCO-collapsed risk."
)
DEFAULT_INCLUDE = {
    "nq_atr_daily_ladder112221_10max",
    "mnq_atr_daily_ladder112221_10max",
    "nq_atr_daily_3initial_10max",
    "mnq_atr_daily_3initial_10max",
    "es_atr_weekly_2initial_3add_6max",
    "nq_atr_weekly_2initial_3add_6max",
    "mnq_atr_weekly_2initial_3add_6max",
    "es_monthly_orb_restricted_scaleout3",
    "nq_monthly_orb_restricted_scaleout3",
    "ym_monthly_orb_restricted_scaleout3",
    "mnq_monthly_orb_restricted_scaleout3_boundary_stop",
    "nq_yearly_orb_scaleout3",
    "mnq_yearly_orb_scaleout3",
    # Explicit bleed case requested by the user.
    "mnq_monthly_orb_restricted_scaleout3",
}


@dataclass(frozen=True)
class Fill:
    side: str
    quantity: int
    price: float
    ts: str
    reason: str
    trade_id: str

    @property
    def day(self) -> date:
        return _parse_any_date(self.ts)

    @property
    def is_entry(self) -> bool:
        return self.reason in {"entry", "runner_entry"}


@dataclass(frozen=True)
class SummaryRow:
    candidate: str
    slug: str
    instrument: str
    net_usd: float
    stress_dd_usd: float
    ratio: float
    rank: int


def build_detail_charts(
    replay_root: Path = DEFAULT_REPLAY_ROOT,
    output_root: Path = DEFAULT_OUTPUT_ROOT,
    include_all: bool = False,
    include_slugs: Optional[Sequence[str]] = None,
    exact: bool = False,
) -> List[Path]:
    summary = _summary_rows(replay_root / "summary.csv")
    selected = _selected_slugs(summary, include_all, include_slugs, exact)
    output_root.mkdir(parents=True, exist_ok=True)
    built: List[Path] = []

    for row in summary:
        if row.slug not in selected:
            continue
        state_dir = replay_root / "states" / row.slug
        if not state_dir.exists():
            continue
        instance = _read_instance(state_dir / "strategy_instances.csv")
        if instance is None:
            continue
        bars = _read_bars(state_dir / "bars" / f"{instance.instrument}_D.csv")
        fills = _read_fills(state_dir / "fills.csv")
        equity = _read_csv(replay_root / "audits" / row.slug / "equity_curve.csv")
        candidate_root = output_root / row.slug
        candidate_root.mkdir(parents=True, exist_ok=True)
        if instance.strategy_type == "atr_supertrend_dca":
            built.extend(_build_atr_charts(candidate_root, row, instance, bars, fills, equity))
        elif instance.strategy_type in {"monthly_orb_restricted_scaleout3", "monthly_orb_v2b_oco"}:
            built.extend(_build_monthly_orb_charts(candidate_root, row, instance, bars, fills, equity))
        elif instance.strategy_type == "yearly_orb_scaleout3":
            built.extend(_build_yearly_orb_charts(candidate_root, row, instance, bars, fills, equity))
        _write_candidate_index(candidate_root, row, built)

    _write_master_index(output_root, summary, selected)
    return built


def _build_atr_charts(
    out_root: Path,
    row: SummaryRow,
    instance: StrategyInstance,
    bars: List[Bar],
    fills: List[Fill],
    equity: List[Dict[str, str]],
) -> List[Path]:
    if not bars:
        return []
    cfg = _config(instance)
    daily_points = _supertrend(bars, int(cfg.get("atr_len", 14)), float(cfg.get("atr_mult", 3.0)))
    daily_by_ts = {p.ts[:10]: p for p in daily_points}
    weekly_by_ts: Dict[str, Any] = {}
    for idx, bar in enumerate(bars):
        points = _supertrend(
            _completed_weekly_bars(bars[: idx + 1], _parse_date(bar.ts)),
            int(cfg.get("atr_len", 14)),
            float(cfg.get("atr_mult", 3.0)),
        )
        if points:
            weekly_by_ts[bar.ts[:10]] = points[-1]

    built: List[Path] = []
    for year in sorted({_parse_any_date(bar.ts).year for bar in bars}):
        year_bars = [bar for bar in bars if _parse_any_date(bar.ts).year == year]
        if not year_bars:
            continue
        year_fills = [fill for fill in fills if fill.day.year == year]
        year_equity = [eq for eq in equity if _parse_any_date(eq["ts"]).year == year]
        out = out_root / f"{year}" / f"{year}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig, (ax, dd_ax) = plt.subplots(
            2,
            1,
            figsize=(15, 8),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1]},
        )
        x_map = _plot_candles(ax, year_bars)
        xs = [x_map[bar.ts[:10]] for bar in year_bars if bar.ts[:10] in x_map]
        daily_vals = [daily_by_ts.get(bar.ts[:10]) for bar in year_bars]
        weekly_vals = [weekly_by_ts.get(bar.ts[:10]) for bar in year_bars]
        _plot_supertrend(ax, xs, daily_vals, bullish_color="#06b6d4", bearish_color="#f97316", linewidth=1.2, label="Daily ST")
        _plot_supertrend(ax, xs, weekly_vals, bullish_color="#22c55e", bearish_color="#ef4444", linewidth=2.0, label="Weekly ST")
        _plot_fill_markers(ax, x_map, year_fills)
        _plot_equity_panel(dd_ax, year_equity, point_value=POINT_VALUES.get(instance.instrument, 1.0))
        ax.set_title(
            f"{row.candidate} broker-like replay - {year}\n"
            f"rank {row.rank}, net ${row.net_usd:,.0f}, stress DD ${row.stress_dd_usd:,.0f}, ratio {row.ratio:.2f}"
        )
        ax.set_ylabel("Price")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.18)
        _format_xaxis(ax, year_bars)
        fig.tight_layout()
        fig.text(0.01, 0.005, REALISM_CAPTION, fontsize=7, color="#475569", ha="left")
        fig.savefig(out, dpi=150)
        plt.close(fig)
        built.append(out)
    return built


def _build_monthly_orb_charts(
    out_root: Path,
    row: SummaryRow,
    instance: StrategyInstance,
    bars: List[Bar],
    fills: List[Fill],
    equity: List[Dict[str, str]],
) -> List[Path]:
    built: List[Path] = []
    months = sorted({(_parse_any_date(bar.ts).year, _parse_any_date(bar.ts).month) for bar in bars})
    for year, month in months:
        month_bars = [bar for bar in bars if (_parse_any_date(bar.ts).year, _parse_any_date(bar.ts).month) == (year, month)]
        if not month_bars:
            continue
        month_fills = [fill for fill in fills if (fill.day.year, fill.day.month) == (year, month)]
        month_equity = [eq for eq in equity if (_parse_any_date(eq["ts"]).year, _parse_any_date(eq["ts"]).month) == (year, month)]
        out = out_root / f"{year}" / f"{year}-{month:02d}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig, (ax, dd_ax) = plt.subplots(
            2,
            1,
            figsize=(14, 7),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1]},
        )
        x_map = _plot_candles(ax, month_bars)
        range_bars = month_bars[: int(_config(instance).get("or_sessions", 3))]
        if range_bars:
            rh = max(bar.high for bar in range_bars)
            rl = min(bar.low for bar in range_bars)
            rv = rh - rl
            ax.axhline(rh, color="#2563eb", linewidth=1.5, label="OR high")
            ax.axhline(rl, color="#9333ea", linewidth=1.5, label="OR low")
            ax.axhline(rh + rv, color="#2563eb", linestyle=":", linewidth=1.0, label="Long TP1")
            ax.axhline(rl - rv, color="#9333ea", linestyle=":", linewidth=1.0, label="Short TP1")
            if len(range_bars) < len(month_bars):
                split = len(range_bars) - 0.5
                ax.axvline(split, color="#64748b", linewidth=1.0, alpha=0.7)
        _plot_fill_markers(ax, x_map, month_fills)
        _plot_equity_panel(dd_ax, month_equity, point_value=POINT_VALUES.get(instance.instrument, 1.0))
        ax.set_title(
            f"{row.candidate} broker-like replay - {year}-{month:02d}\n"
            f"fills {len(month_fills)}, rank {row.rank}, net ${row.net_usd:,.0f}, stress DD ${row.stress_dd_usd:,.0f}"
        )
        ax.set_ylabel("Price")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.18)
        _format_xaxis(ax, month_bars)
        fig.tight_layout()
        fig.text(0.01, 0.005, REALISM_CAPTION, fontsize=7, color="#475569", ha="left")
        fig.savefig(out, dpi=150)
        plt.close(fig)
        built.append(out)
    return built


def _build_yearly_orb_charts(
    out_root: Path,
    row: SummaryRow,
    instance: StrategyInstance,
    bars: List[Bar],
    fills: List[Fill],
    equity: List[Dict[str, str]],
) -> List[Path]:
    built: List[Path] = []
    cfg = _config(instance)
    or_start = int(cfg.get("or_start_month", 1))
    or_end = int(cfg.get("or_end_month", 3))
    for year in sorted({_parse_any_date(bar.ts).year for bar in bars}):
        year_bars = [bar for bar in bars if _parse_any_date(bar.ts).year == year]
        if not year_bars:
            continue
        year_fills = [fill for fill in fills if fill.day.year == year]
        year_equity = [eq for eq in equity if _parse_any_date(eq["ts"]).year == year]
        out = out_root / f"{year}" / f"{year}.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        fig, (ax, dd_ax) = plt.subplots(
            2,
            1,
            figsize=(15, 8),
            sharex=True,
            gridspec_kw={"height_ratios": [4, 1]},
        )
        x_map = _plot_candles(ax, year_bars)
        or_bars = [bar for bar in year_bars if or_start <= _parse_any_date(bar.ts).month <= or_end]
        if or_bars:
            rh = max(bar.high for bar in or_bars)
            rl = min(bar.low for bar in or_bars)
            rv = rh - rl
            ax.axhline(rh, color="#2563eb", linewidth=1.5, label="Year OR high")
            ax.axhline(rl, color="#9333ea", linewidth=1.5, label="Year OR low")
            ax.axhline(rh + rv, color="#2563eb", linestyle=":", linewidth=1.0, label="Long TP1")
            ax.axhline(rl - rv, color="#9333ea", linestyle=":", linewidth=1.0, label="Short TP1")
            last_or = max(x_map.get(bar.ts[:10], 0) for bar in or_bars if bar.ts[:10] in x_map)
            ax.axvline(last_or + 0.5, color="#64748b", linewidth=1.0, alpha=0.7)
        _plot_fill_markers(ax, x_map, year_fills)
        _plot_equity_panel(dd_ax, year_equity, point_value=POINT_VALUES.get(instance.instrument, 1.0))
        ax.set_title(
            f"{row.candidate} broker-like replay - {year}\n"
            f"rank {row.rank}, net ${row.net_usd:,.0f}, stress DD ${row.stress_dd_usd:,.0f}, ratio {row.ratio:.2f}"
        )
        ax.set_ylabel("Price")
        ax.legend(loc="upper left", fontsize=8)
        ax.grid(True, alpha=0.18)
        _format_xaxis(ax, year_bars)
        fig.tight_layout()
        fig.text(0.01, 0.005, REALISM_CAPTION, fontsize=7, color="#475569", ha="left")
        fig.savefig(out, dpi=150)
        plt.close(fig)
        built.append(out)
    return built


def _plot_candles(ax: Any, bars: List[Bar]) -> Dict[str, int]:
    x_map: Dict[str, int] = {}
    width = 0.62 if len(bars) > 40 else 0.72
    # Min body must scale with price (hard 0.01 pts is fine on NQ, but 100 pips on EURUSD).
    if bars:
        price_span = max(bar.high for bar in bars) - min(bar.low for bar in bars)
        min_body = max(price_span * 0.001, 1e-8)
    else:
        min_body = 1e-8
    for idx, bar in enumerate(bars):
        key = bar.ts[:10]
        x_map[key] = idx
        up = bar.close >= bar.open
        color = "#089981" if up else "#f23645"
        ax.vlines(idx, bar.low, bar.high, color=color, linewidth=1.0, alpha=0.95)
        lower = min(bar.open, bar.close)
        height = max(abs(bar.close - bar.open), max((bar.high - bar.low) * 0.015, min_body))
        ax.add_patch(
            Rectangle(
                (idx - width / 2.0, lower),
                width,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.7,
                alpha=0.9,
            )
        )
    ax.set_xlim(-1, max(len(bars), 1))
    return x_map


def _plot_supertrend(
    ax: Any,
    xs: List[int],
    points: List[Any],
    *,
    bullish_color: str,
    bearish_color: str,
    linewidth: float,
    label: str,
) -> None:
    first = True
    for bullish in (True, False):
        seg_x: List[int] = []
        seg_y: List[float] = []
        for x, point in zip(xs, points):
            if point is not None and point.bullish == bullish:
                seg_x.append(x)
                seg_y.append(float(point.stop))
            elif seg_x:
                ax.plot(
                    seg_x,
                    seg_y,
                    color=bullish_color if bullish else bearish_color,
                    linewidth=linewidth,
                    label=label if first else None,
                    solid_capstyle="round",
                )
                first = False
                seg_x = []
                seg_y = []
        if seg_x:
            ax.plot(
                seg_x,
                seg_y,
                color=bullish_color if bullish else bearish_color,
                linewidth=linewidth,
                label=label if first else None,
                solid_capstyle="round",
            )
            first = False


def _plot_fill_markers(ax: Any, x_map: Dict[str, int], fills: List[Fill]) -> None:
    y_span = ax.get_ylim()[1] - ax.get_ylim()[0]
    bump = y_span * 0.018 if y_span else 1.0
    label_count = 0
    for fill in fills:
        key = fill.ts[:10]
        if key not in x_map:
            continue
        x = x_map[key]
        marker = "^" if fill.side == "buy" else "v"
        color = "#16a34a" if fill.is_entry else "#dc2626"
        if fill.side == "sell" and fill.is_entry:
            color = "#9333ea"
        if fill.side == "buy" and not fill.is_entry:
            color = "#f97316"
        y = fill.price + (bump if marker == "^" else -bump)
        ax.scatter([x], [fill.price], marker=marker, s=52, color=color, edgecolor="black", linewidth=0.35, zorder=5)
        if label_count < 90:
            txt = f"{fill.side[0].upper()}{fill.quantity} {fill.reason[:7]}"
            ax.text(x, y, txt, fontsize=6, ha="center", va="bottom" if marker == "^" else "top", color=color)
            label_count += 1


def _plot_equity_panel(ax: Any, equity: List[Dict[str, str]], point_value: float) -> None:
    if not equity:
        ax.axis("off")
        return
    xs = list(range(len(equity)))
    eq = [float(row["close_equity_points"]) * point_value for row in equity]
    dd = [float(row["intrabar_dd_usd"]) for row in equity]
    ax.plot(xs, eq, color="#0f766e", linewidth=1.4, label="Close equity")
    ax.fill_between(xs, dd, 0, color="#dc2626", alpha=0.18, label="Stress DD")
    ax.axhline(0, color="#64748b", linewidth=0.8)
    ax.set_ylabel("USD")
    ax.grid(True, alpha=0.16)
    ax.legend(loc="upper left", fontsize=7)


def _format_xaxis(ax: Any, bars: List[Bar]) -> None:
    if not bars:
        return
    step = max(len(bars) // 8, 1)
    ticks = list(range(0, len(bars), step))
    if ticks[-1] != len(bars) - 1:
        ticks.append(len(bars) - 1)
    labels = [bars[idx].ts[:10] for idx in ticks]
    ax.set_xticks(ticks)
    ax.set_xticklabels(labels, rotation=30, ha="right", fontsize=8)


def _write_candidate_index(candidate_root: Path, row: SummaryRow, built_paths: List[Path]) -> None:
    local = [path for path in built_paths if candidate_root in path.parents]
    by_year: Dict[str, List[Path]] = {}
    for path in sorted(local):
        by_year.setdefault(path.parent.name, []).append(path)
    lines = [
        f"# {row.candidate}",
        "",
        "Broker-like replay detail charts. These use the persisted bars and fills generated by the live-runtime `PaperBroker` path.",
        "",
        f"> {REALISM_CAPTION}",
        "",
        f"- Rank: {row.rank}",
        f"- Instrument: `{row.instrument}`",
        f"- Net: `${row.net_usd:,.2f}`",
        f"- Intrabar stress DD: `${row.stress_dd_usd:,.2f}`",
        f"- Net / stress DD: `{row.ratio:.2f}`",
        "",
    ]
    for year, paths in by_year.items():
        lines.append(f"## {year}")
        lines.append("")
        for path in paths:
            rel = path.relative_to(candidate_root)
            lines.append(f"- [{path.stem}]({rel.as_posix()})")
        lines.append("")
    (candidate_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_master_index(output_root: Path, summary: List[SummaryRow], selected: set[str]) -> None:
    lines = [
        "# Broker-Like Replay Detail Charts",
        "",
        "These chart packs are generated from the new broker-like replay standard: strategy intents flow through the engine, paper broker, persisted orders, and persisted fills. The older theoretical charts remain in their original case-study folders.",
        "",
        f"> {REALISM_CAPTION}",
        "",
        "| Rank | Candidate | Instrument | Net | Stress DD | Net / Stress DD | Charts |",
        "|---:|---|---|---:|---:|---:|---|",
    ]
    for row in summary:
        if row.slug not in selected:
            continue
        index = output_root / row.slug / "INDEX.md"
        if not index.exists():
            continue
        lines.append(
            f"| {row.rank} | {row.candidate} | {row.instrument} | ${row.net_usd:,.2f} | "
            f"${row.stress_dd_usd:,.2f} | {row.ratio:.2f} | [{row.slug}]({row.slug}/INDEX.md) |"
        )
    lines.extend(
        [
            "",
            "## Reference Comparison",
            "",
            "- Existing summary chart: [MNQ ATR daily ladder theoretical vs broker-like](../mnq_atr_daily_ladder112221_theoretical_vs_broker_like.png)",
            "- Existing summary chart: [MNQ ATR weekly 2-initial broker-like](../mnq_atr_weekly_2initial_3add_6max_broker_like.png)",
            "",
        ]
    )
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _selected_slugs(summary: List[SummaryRow], include_all: bool, include_slugs: Optional[Sequence[str]], exact: bool = False) -> set[str]:
    if include_all:
        return {row.slug for row in summary}
    if exact:
        if include_slugs:
            return set(include_slugs)
        return {row.slug for row in summary[:10]}
    selected = set(include_slugs or [])
    selected.update(DEFAULT_INCLUDE)
    for row in summary[:12]:
        selected.add(row.slug)
    return selected


def _summary_rows(path: Path) -> List[SummaryRow]:
    rows: List[SummaryRow] = []
    for idx, row in enumerate(_read_csv(path), start=1):
        rows.append(
            SummaryRow(
                candidate=row["candidate"],
                slug=row["slug"],
                instrument=row["instrument"],
                net_usd=float(row["net_usd"]),
                stress_dd_usd=float(row["intrabar_mtm_dd_usd"]),
                ratio=float(row["net_over_stress_dd"]),
                rank=idx,
            )
        )
    return rows


def _read_instance(path: Path) -> Optional[StrategyInstance]:
    rows = _read_csv(path)
    if not rows:
        return None
    return StrategyInstance.from_row(rows[0])


def _read_bars(path: Path) -> List[Bar]:
    rows = _read_csv(path)
    bars = [Bar.from_row(row) for row in rows]
    bars.sort(key=lambda bar: bar.ts)
    return bars


def _read_fills(path: Path) -> List[Fill]:
    fills: List[Fill] = []
    for row in _read_csv(path):
        fills.append(
            Fill(
                side=row["side"],
                quantity=int(float(row["quantity"] or 0)),
                price=float(row["price"] or 0),
                ts=str(row["ts"]),
                reason=str(row["reason"]),
                trade_id=str(row["trade_id"]),
            )
        )
    fills.sort(key=lambda fill: (fill.ts, fill.trade_id, fill.reason))
    return fills


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


def _parse_any_date(value: str) -> date:
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return datetime.fromisoformat(text[:10]).date()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Build broker-like replay detail chart packs.")
    parser.add_argument("--replay-root", type=Path, default=DEFAULT_REPLAY_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--all", action="store_true", help="Generate detail charts for every broker-like replay candidate.")
    parser.add_argument("--slug", action="append", default=[], help="Specific replay slug to include. Can be repeated.")
    parser.add_argument("--exact", action="store_true", help="Only generate requested slugs, or the current top 10 if no slugs are provided.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    built = build_detail_charts(
        replay_root=args.replay_root,
        output_root=args.output_root,
        include_all=args.all,
        include_slugs=args.slug,
        exact=args.exact,
    )
    print(f"Wrote {len(built)} charts under {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
