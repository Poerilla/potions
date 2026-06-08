from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NQ_DAILY = ROOT / "nq" / "nq_daily.csv"
DEFAULT_ES_DAILY = ROOT / "es" / "es_daily.csv"
DEFAULT_NQ_V2B_FILLS = (
    ROOT
    / "live"
    / "state"
    / "v2b_strategy_plugin_cross_market_requested"
    / "states"
    / "nq_v2b_scaleout_oco_then_reverse"
    / "fills.csv"
)
DEFAULT_ES_V2B_FILLS = (
    ROOT
    / "live"
    / "state"
    / "v2b_strategy_plugin_cross_market_requested"
    / "states"
    / "es_v2b_scaleout_oco_then_reverse"
    / "fills.csv"
)
DEFAULT_NQ_V2B_UNITS = (
    ROOT
    / "live"
    / "state"
    / "v2b_strategy_plugin_cross_market_requested"
    / "states"
    / "nq_v2b_scaleout_oco_then_reverse"
    / "unit_trades.csv"
)
DEFAULT_ES_V2B_UNITS = (
    ROOT
    / "live"
    / "state"
    / "v2b_strategy_plugin_cross_market_requested"
    / "states"
    / "es_v2b_scaleout_oco_then_reverse"
    / "unit_trades.csv"
)
DEFAULT_OUT = ROOT / "live" / "state" / "orb_divergence_daily_nq_es"


@dataclass(frozen=True)
class Bar:
    ts: datetime
    open: float
    high: float
    low: float
    close: float


@dataclass(frozen=True)
class BreakoutEvent:
    regime: str
    market: str
    side: str  # "up" | "down"
    ts: datetime
    period_key: str
    breakout_price: float
    or_high: Optional[float]
    or_low: Optional[float]
    trade_id: str = ""


@dataclass(frozen=True)
class Divergence:
    regime: str
    side: str  # "up" | "down"
    ts: datetime
    period_key: str
    leader: str
    lagger: str
    leader_breakout_price: float
    lagger_break_ts: Optional[datetime]
    lag_days: Optional[int]
    fakeout: Optional[bool]

    @property
    def kind(self) -> str:
        return "divergent_high" if self.side == "up" else "divergent_low"


@dataclass(frozen=True)
class OrbPeriod:
    key: str
    or_high: float
    or_low: float
    trade_bars: Tuple[Bar, ...]


def _parse_dt(value: str) -> datetime:
    text = str(value).strip()
    if " " in text and "T" not in text:
        text = text.replace(" ", "T", 1)
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


def _to_day(dt: datetime) -> datetime:
    return datetime(dt.year, dt.month, dt.day)


def _read_daily(path: Path, ts_field: str = "date") -> List[Bar]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: List[Bar] = []
    for row in rows:
        dt = _to_day(_parse_dt(row[ts_field]))
        out.append(
            Bar(
                ts=dt,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
        )
    out.sort(key=lambda b: b.ts)
    return out


def _align_daily(nq: List[Bar], es: List[Bar]) -> Tuple[List[Bar], List[Bar]]:
    nq_by = {b.ts: b for b in nq}
    es_by = {b.ts: b for b in es}
    common = sorted(set(nq_by).intersection(es_by))
    return [nq_by[ts] for ts in common], [es_by[ts] for ts in common]


def _monthly_periods(bars: Sequence[Bar], or_sessions: int = 3) -> Dict[str, OrbPeriod]:
    by_month: Dict[str, List[Bar]] = {}
    for b in bars:
        key = f"{b.ts.year:04d}-{b.ts.month:02d}"
        by_month.setdefault(key, []).append(b)
    out: Dict[str, OrbPeriod] = {}
    for key, month_bars in sorted(by_month.items()):
        month_bars = sorted(month_bars, key=lambda b: b.ts)
        if len(month_bars) <= or_sessions:
            continue
        orb = month_bars[:or_sessions]
        trade = month_bars[or_sessions:]
        hi = max(b.high for b in orb)
        lo = min(b.low for b in orb)
        if hi <= lo:
            continue
        out[key] = OrbPeriod(key=key, or_high=hi, or_low=lo, trade_bars=tuple(trade))
    return out


def _yearly_periods(
    bars: Sequence[Bar],
    or_start_month: int = 1,
    or_end_month: int = 3,
    trade_start_month: int = 4,
    trade_end_month: int = 12,
) -> Dict[str, OrbPeriod]:
    by_year: Dict[int, List[Bar]] = {}
    for b in bars:
        by_year.setdefault(b.ts.year, []).append(b)
    out: Dict[str, OrbPeriod] = {}
    for year, year_bars in sorted(by_year.items()):
        ybars = sorted(year_bars, key=lambda b: b.ts)
        orb = [b for b in ybars if or_start_month <= b.ts.month <= or_end_month]
        trade = [b for b in ybars if trade_start_month <= b.ts.month <= trade_end_month]
        if not orb or not trade:
            continue
        hi = max(b.high for b in orb)
        lo = min(b.low for b in orb)
        if hi <= lo:
            continue
        key = f"{year:04d}"
        out[key] = OrbPeriod(key=key, or_high=hi, or_low=lo, trade_bars=tuple(trade))
    return out


def _first_breakouts(regime: str, market: str, periods: Dict[str, OrbPeriod]) -> Dict[Tuple[str, str], BreakoutEvent]:
    out: Dict[Tuple[str, str], BreakoutEvent] = {}
    for period_key, period in sorted(periods.items()):
        up: Optional[BreakoutEvent] = None
        down: Optional[BreakoutEvent] = None
        for b in period.trade_bars:
            if up is None and b.high > period.or_high:
                up = BreakoutEvent(
                    regime=regime,
                    market=market,
                    side="up",
                    ts=b.ts,
                    period_key=period_key,
                    breakout_price=b.high,
                    or_high=period.or_high,
                    or_low=period.or_low,
                )
            if down is None and b.low < period.or_low:
                down = BreakoutEvent(
                    regime=regime,
                    market=market,
                    side="down",
                    ts=b.ts,
                    period_key=period_key,
                    breakout_price=b.low,
                    or_high=period.or_high,
                    or_low=period.or_low,
                )
            if up is not None and down is not None:
                break
        if up is not None:
            out[(period_key, "up")] = up
        if down is not None:
            out[(period_key, "down")] = down
    return out


def _read_v2b_entries(path: Path, market: str) -> List[BreakoutEvent]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    best: Dict[Tuple[str, str], Tuple[datetime, Dict[str, str]]] = {}
    for row in rows:
        if row.get("reason") != "entry":
            continue
        dt = _parse_dt(row["ts"])
        day = _to_day(dt)
        side = "up" if row.get("side") == "buy" else "down"
        k = (day.date().isoformat(), side)
        prior = best.get(k)
        if prior is None or dt < prior[0]:
            best[k] = (dt, row)
    out: List[BreakoutEvent] = []
    for (day_key, side), (_, row) in sorted(best.items()):
        day_ts = _to_day(_parse_dt(row["ts"]))
        out.append(
            BreakoutEvent(
                regime="v2b",
                market=market,
                side=side,
                ts=day_ts,
                period_key=day_key,
                breakout_price=float(row["price"]),
                or_high=None,
                or_low=None,
                trade_id=row.get("trade_id", ""),
            )
        )
    out.sort(key=lambda e: (e.ts, e.market, e.side))
    return out


def _read_trade_net(path: Path) -> Dict[str, float]:
    with path.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out: Dict[str, float] = {}
    for row in rows:
        tid = row.get("trade_id", "")
        if not tid:
            continue
        out[tid] = out.get(tid, 0.0) + float(row.get("net_usd", "0") or 0.0)
    return out


def _fakeout_from_daily(
    event: BreakoutEvent,
    period: Optional[OrbPeriod],
    lookahead_days: int,
) -> Optional[bool]:
    if period is None or event.or_high is None or event.or_low is None:
        return None
    end_ts = event.ts + timedelta(days=lookahead_days)
    for b in period.trade_bars:
        if b.ts < event.ts or b.ts > end_ts:
            continue
        if event.side == "up" and b.close <= event.or_high:
            return True
        if event.side == "down" and b.close >= event.or_low:
            return True
    return False


def _detect_period_divergences(
    regime: str,
    nq_events: Dict[Tuple[str, str], BreakoutEvent],
    es_events: Dict[Tuple[str, str], BreakoutEvent],
    nq_periods: Dict[str, OrbPeriod],
    es_periods: Dict[str, OrbPeriod],
    confirm_window_days: int,
    fakeout_lookahead_days: int,
) -> List[Divergence]:
    out: List[Divergence] = []
    keys = sorted(set(nq_events.keys()).union(es_events.keys()))
    for key in keys:
        period_key, side = key
        nq_ev = nq_events.get(key)
        es_ev = es_events.get(key)
        if nq_ev is not None and es_ev is not None:
            if nq_ev.ts <= es_ev.ts:
                lag_days = (es_ev.ts - nq_ev.ts).days
                if lag_days > confirm_window_days:
                    out.append(
                        Divergence(
                            regime=regime,
                            side=side,
                            ts=nq_ev.ts,
                            period_key=period_key,
                            leader="NQ",
                            lagger="ES",
                            leader_breakout_price=nq_ev.breakout_price,
                            lagger_break_ts=es_ev.ts,
                            lag_days=lag_days,
                            fakeout=_fakeout_from_daily(
                                nq_ev, nq_periods.get(period_key), fakeout_lookahead_days
                            ),
                        )
                    )
            else:
                lag_days = (nq_ev.ts - es_ev.ts).days
                if lag_days > confirm_window_days:
                    out.append(
                        Divergence(
                            regime=regime,
                            side=side,
                            ts=es_ev.ts,
                            period_key=period_key,
                            leader="ES",
                            lagger="NQ",
                            leader_breakout_price=es_ev.breakout_price,
                            lagger_break_ts=nq_ev.ts,
                            lag_days=lag_days,
                            fakeout=_fakeout_from_daily(
                                es_ev, es_periods.get(period_key), fakeout_lookahead_days
                            ),
                        )
                    )
        elif nq_ev is not None:
            out.append(
                Divergence(
                    regime=regime,
                    side=side,
                    ts=nq_ev.ts,
                    period_key=period_key,
                    leader="NQ",
                    lagger="ES",
                    leader_breakout_price=nq_ev.breakout_price,
                    lagger_break_ts=None,
                    lag_days=None,
                    fakeout=_fakeout_from_daily(nq_ev, nq_periods.get(period_key), fakeout_lookahead_days),
                )
            )
        elif es_ev is not None:
            out.append(
                Divergence(
                    regime=regime,
                    side=side,
                    ts=es_ev.ts,
                    period_key=period_key,
                    leader="ES",
                    lagger="NQ",
                    leader_breakout_price=es_ev.breakout_price,
                    lagger_break_ts=None,
                    lag_days=None,
                    fakeout=_fakeout_from_daily(es_ev, es_periods.get(period_key), fakeout_lookahead_days),
                )
            )
    out.sort(key=lambda d: (d.ts, d.regime, d.leader, d.side))
    return out


def _nearest_days(ts: datetime, others: Sequence[BreakoutEvent]) -> Tuple[Optional[int], Optional[datetime]]:
    best: Optional[int] = None
    best_ts: Optional[datetime] = None
    for ev in others:
        d = abs((ev.ts - ts).days)
        if best is None or d < best:
            best = d
            best_ts = ev.ts
    return best, best_ts


def _detect_v2b_divergences(
    nq_events: List[BreakoutEvent],
    es_events: List[BreakoutEvent],
    confirm_window_days: int,
    nq_trade_net: Dict[str, float],
    es_trade_net: Dict[str, float],
) -> List[Divergence]:
    out: List[Divergence] = []
    for side in ("up", "down"):
        nq_side = [e for e in nq_events if e.side == side]
        es_side = [e for e in es_events if e.side == side]
        for ev in nq_side:
            nearest_days, nearest_ts = _nearest_days(ev.ts, es_side)
            if nearest_days is not None and nearest_days <= confirm_window_days:
                continue
            pnl = nq_trade_net.get(ev.trade_id) if ev.trade_id else None
            out.append(
                Divergence(
                    regime="v2b",
                    side=side,
                    ts=ev.ts,
                    period_key=ev.period_key,
                    leader="NQ",
                    lagger="ES",
                    leader_breakout_price=ev.breakout_price,
                    lagger_break_ts=nearest_ts,
                    lag_days=nearest_days,
                    fakeout=(pnl <= 0.0) if pnl is not None else None,
                )
            )
        for ev in es_side:
            nearest_days, nearest_ts = _nearest_days(ev.ts, nq_side)
            if nearest_days is not None and nearest_days <= confirm_window_days:
                continue
            pnl = es_trade_net.get(ev.trade_id) if ev.trade_id else None
            out.append(
                Divergence(
                    regime="v2b",
                    side=side,
                    ts=ev.ts,
                    period_key=ev.period_key,
                    leader="ES",
                    lagger="NQ",
                    leader_breakout_price=ev.breakout_price,
                    lagger_break_ts=nearest_ts,
                    lag_days=nearest_days,
                    fakeout=(pnl <= 0.0) if pnl is not None else None,
                )
            )
    out.sort(key=lambda d: (d.ts, d.leader, d.side))
    uniq: Dict[Tuple[str, datetime, str, str, str], Divergence] = {}
    for d in out:
        uniq[(d.regime, d.ts, d.side, d.leader, d.period_key)] = d
    return list(sorted(uniq.values(), key=lambda d: (d.ts, d.leader, d.side)))


def _add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=y, month=m, day=1, hour=0, minute=0, second=0, microsecond=0)


def _window_bounds(start: datetime, end: datetime, months: int = 6) -> List[Tuple[datetime, datetime]]:
    cur = start.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    out: List[Tuple[datetime, datetime]] = []
    while cur <= end:
        nxt = _add_months(cur, months)
        out.append((cur, nxt))
        cur = nxt
    return out


def _norm_close(bars: Sequence[Bar]) -> List[float]:
    if not bars:
        return []
    base = bars[0].close if bars[0].close else 1.0
    return [100.0 * (b.close / base) for b in bars]


def _plot_window(
    out: Path,
    regime: str,
    nq: List[Bar],
    es: List[Bar],
    events: List[Divergence],
    window_start: datetime,
    window_end: datetime,
) -> None:
    nq_win = [b for b in nq if window_start <= b.ts < window_end]
    es_win = [b for b in es if window_start <= b.ts < window_end]
    if not nq_win or not es_win:
        return
    ev_win = [e for e in events if window_start <= _to_day(e.ts) < window_end]
    nq_norm = _norm_close(nq_win)
    es_norm = _norm_close(es_win)
    nq_by_ts = {b.ts: v for b, v in zip(nq_win, nq_norm)}
    es_by_ts = {b.ts: v for b, v in zip(es_win, es_norm)}

    fig, ax = plt.subplots(figsize=(15, 7))
    ax.plot([b.ts for b in nq_win], nq_norm, color="#2563eb", linewidth=1.25, label="NQ close (normalized)")
    ax.plot([b.ts for b in es_win], es_norm, color="#7c3aed", linewidth=1.25, label="ES close (normalized)")

    red_x: List[datetime] = []
    red_y: List[float] = []
    green_x: List[datetime] = []
    green_y: List[float] = []
    for e in ev_win:
        day_ts = _to_day(e.ts)
        y_val = nq_by_ts.get(day_ts) if e.leader == "NQ" else es_by_ts.get(day_ts)
        if y_val is None:
            continue
        if e.side == "up":
            red_x.append(day_ts)
            red_y.append(y_val)
        else:
            green_x.append(day_ts)
            green_y.append(y_val)

    if red_x:
        ax.scatter(red_x, red_y, color="#dc2626", s=24, zorder=5, label="Divergent high breakout")
    if green_x:
        ax.scatter(green_x, green_y, color="#16a34a", s=24, zorder=5, label="Divergent low breakout")

    end_label = (window_end - timedelta(seconds=1)).date()
    ax.set_title(
        f"NQ vs ES {regime.upper()} ORB divergence (daily charts)\n"
        f"Window {window_start.date()} to {end_label} | red={len(red_x)} green={len(green_x)}"
    )
    ax.set_ylabel("Normalized close (start=100)")
    ax.grid(True, alpha=0.2)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.autofmt_xdate(rotation=45)
    handles, labels = ax.get_legend_handles_labels()
    if handles:
        ax.legend(loc="upper left", fontsize=8)
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150)
    plt.close(fig)


def _write_divergences_csv(path: Path, events: Iterable[Divergence]) -> None:
    rows = []
    for e in events:
        rows.append(
            {
                "regime": e.regime,
                "ts": e.ts.isoformat(),
                "period_key": e.period_key,
                "kind": e.kind,
                "side": e.side,
                "leader": e.leader,
                "lagger": e.lagger,
                "leader_breakout_price": f"{e.leader_breakout_price:.4f}",
                "lagger_break_ts": e.lagger_break_ts.isoformat() if e.lagger_break_ts else "",
                "lag_days": "" if e.lag_days is None else str(e.lag_days),
                "fakeout": "" if e.fakeout is None else ("1" if e.fakeout else "0"),
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_summary_csv(path: Path, events: Iterable[Divergence]) -> None:
    groups: Dict[Tuple[str, str, str], List[Divergence]] = {}
    for e in events:
        groups.setdefault((e.regime, e.leader, e.side), []).append(e)
    rows = []
    for (regime, leader, side), vals in sorted(groups.items()):
        known_fakeout = [v for v in vals if v.fakeout is not None]
        fakeouts = [v for v in known_fakeout if v.fakeout]
        rows.append(
            {
                "regime": regime,
                "leader": leader,
                "side": side,
                "divergence_count": str(len(vals)),
                "fakeout_count": str(len(fakeouts)) if known_fakeout else "",
                "fakeout_rate": (
                    f"{(len(fakeouts) / len(known_fakeout) * 100.0):.2f}" if known_fakeout else ""
                ),
            }
        )
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _write_regime_index(
    out_root: Path,
    regime: str,
    events: List[Divergence],
    charts: List[Path],
    confirm_window_days: int,
    fakeout_lookahead_days: int,
) -> None:
    highs = [e for e in events if e.side == "up"]
    lows = [e for e in events if e.side == "down"]
    known_fakeout = [e for e in events if e.fakeout is not None]
    fakeouts = [e for e in known_fakeout if e.fakeout]
    fakeout_rate = (len(fakeouts) / len(known_fakeout) * 100.0) if known_fakeout else None
    lines = [
        f"# {regime.upper()} ORB Divergence Study (NQ vs ES)",
        "",
        "Rules:",
        "",
        f"- Divergence: one market breaks OR boundary while the other fails to break the same side within {confirm_window_days} days.",
        "- Red dots: divergent high breakout (upside break without confirmation).",
        "- Green dots: divergent low breakout (downside break without confirmation).",
        "",
        f"- Total divergences: **{len(events)}**",
        f"- Divergent highs (red): **{len(highs)}**",
        f"- Divergent lows (green): **{len(lows)}**",
        (
            f"- Fakeout rate (lookahead {fakeout_lookahead_days} days): **{fakeout_rate:.2f}%** "
            f"({len(fakeouts)}/{len(known_fakeout)})"
            if fakeout_rate is not None
            else "- Fakeout rate: **n/a**"
        ),
        "",
        "## Charts",
        "",
    ]
    by_year: Dict[int, List[Path]] = {}
    for p in charts:
        year = int(p.parent.name)
        by_year.setdefault(year, []).append(p)
    for year in sorted(by_year):
        lines.append(f"### {year}")
        lines.append("")
        for p in sorted(by_year[year]):
            rel = p.relative_to(out_root)
            lines.append(f"- [{p.stem}]({rel.as_posix()})")
        lines.append("")
    lines.extend(
        [
            "## Files",
            "",
            "- [events.csv](events.csv)",
            "- [summary.csv](summary.csv)",
            "",
        ]
    )
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _write_top_index(out_root: Path, regimes: Sequence[str], totals: Dict[str, int]) -> None:
    lines = [
        "# NQ vs ES ORB Divergence Study (Daily Charts)",
        "",
        "Includes monthly ORB, yearly ORB, and v2b breakout divergence scans.",
        "",
        "## Regimes",
        "",
    ]
    for regime in regimes:
        lines.append(f"- [{regime.upper()}](./{regime}/INDEX.md) - divergences: **{totals.get(regime, 0)}**")
    lines.append("")
    (out_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")


def _run_regime_charts(
    out_root: Path,
    regime: str,
    nq_bars: List[Bar],
    es_bars: List[Bar],
    events: List[Divergence],
) -> List[Path]:
    if not nq_bars or not es_bars:
        return []
    if events:
        start = min(e.ts for e in events)
        end = max(e.ts for e in events)
    else:
        start = nq_bars[0].ts
        end = nq_bars[-1].ts
    windows = _window_bounds(start, end, months=6)
    charts: List[Path] = []
    for start, end in windows:
        out = (
            out_root
            / regime
            / "charts"
            / f"{start.year:04d}"
            / f"{start.year:04d}_{start.month:02d}_to_{end.year:04d}_{end.month:02d}.png"
        )
        _plot_window(out, regime, nq_bars, es_bars, events, start, end)
        if out.exists():
            charts.append(out)
    return charts


def run(
    nq_daily_path: Path = DEFAULT_NQ_DAILY,
    es_daily_path: Path = DEFAULT_ES_DAILY,
    nq_v2b_fills: Path = DEFAULT_NQ_V2B_FILLS,
    es_v2b_fills: Path = DEFAULT_ES_V2B_FILLS,
    nq_v2b_units: Path = DEFAULT_NQ_V2B_UNITS,
    es_v2b_units: Path = DEFAULT_ES_V2B_UNITS,
    output_root: Path = DEFAULT_OUT,
    regimes: Sequence[str] = ("monthly", "yearly", "v2b"),
    confirm_window_days: int = 2,
    fakeout_lookahead_days: int = 5,
) -> Dict[str, int]:
    nq_daily = _read_daily(nq_daily_path)
    es_daily = _read_daily(es_daily_path)
    nq_daily, es_daily = _align_daily(nq_daily, es_daily)
    if not nq_daily or not es_daily:
        raise ValueError("No overlapping NQ/ES daily bars found.")

    totals: Dict[str, int] = {}
    grand_events: List[Divergence] = []
    output_root.mkdir(parents=True, exist_ok=True)

    for regime in regimes:
        if regime == "monthly":
            nq_periods = _monthly_periods(nq_daily, or_sessions=3)
            es_periods = _monthly_periods(es_daily, or_sessions=3)
            nq_events = _first_breakouts("monthly", "NQ", nq_periods)
            es_events = _first_breakouts("monthly", "ES", es_periods)
            events = _detect_period_divergences(
                "monthly",
                nq_events,
                es_events,
                nq_periods,
                es_periods,
                confirm_window_days=confirm_window_days,
                fakeout_lookahead_days=fakeout_lookahead_days,
            )
        elif regime == "yearly":
            nq_periods = _yearly_periods(nq_daily)
            es_periods = _yearly_periods(es_daily)
            nq_events = _first_breakouts("yearly", "NQ", nq_periods)
            es_events = _first_breakouts("yearly", "ES", es_periods)
            events = _detect_period_divergences(
                "yearly",
                nq_events,
                es_events,
                nq_periods,
                es_periods,
                confirm_window_days=confirm_window_days,
                fakeout_lookahead_days=fakeout_lookahead_days,
            )
        elif regime == "v2b":
            nq_events = _read_v2b_entries(nq_v2b_fills, "NQ")
            es_events = _read_v2b_entries(es_v2b_fills, "ES")
            nq_trade_net = _read_trade_net(nq_v2b_units)
            es_trade_net = _read_trade_net(es_v2b_units)
            events = _detect_v2b_divergences(
                nq_events,
                es_events,
                confirm_window_days=confirm_window_days,
                nq_trade_net=nq_trade_net,
                es_trade_net=es_trade_net,
            )
        else:
            raise ValueError(f"Unknown regime: {regime}")

        charts = _run_regime_charts(output_root, regime, nq_daily, es_daily, events)
        regime_out = output_root / regime
        _write_divergences_csv(regime_out / "events.csv", events)
        _write_summary_csv(regime_out / "summary.csv", events)
        _write_regime_index(
            regime_out,
            regime,
            events,
            charts,
            confirm_window_days=confirm_window_days,
            fakeout_lookahead_days=fakeout_lookahead_days,
        )
        totals[regime] = len(events)
        grand_events.extend(events)

    _write_divergences_csv(output_root / "events_all.csv", grand_events)
    _write_summary_csv(output_root / "summary_all.csv", grand_events)
    _write_top_index(output_root, regimes, totals)
    totals["all"] = len(grand_events)
    return totals


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="NQ/ES ORB divergence study with monthly/yearly/v2b modes.")
    p.add_argument("--nq-daily-path", type=Path, default=DEFAULT_NQ_DAILY)
    p.add_argument("--es-daily-path", type=Path, default=DEFAULT_ES_DAILY)
    p.add_argument("--nq-v2b-fills", type=Path, default=DEFAULT_NQ_V2B_FILLS)
    p.add_argument("--es-v2b-fills", type=Path, default=DEFAULT_ES_V2B_FILLS)
    p.add_argument("--nq-v2b-units", type=Path, default=DEFAULT_NQ_V2B_UNITS)
    p.add_argument("--es-v2b-units", type=Path, default=DEFAULT_ES_V2B_UNITS)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--regimes", type=str, default="monthly,yearly,v2b")
    p.add_argument("--confirm-window-days", type=int, default=2)
    p.add_argument("--fakeout-lookahead-days", type=int, default=5)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    regimes = [x.strip().lower() for x in args.regimes.split(",") if x.strip()]
    totals = run(
        nq_daily_path=args.nq_daily_path,
        es_daily_path=args.es_daily_path,
        nq_v2b_fills=args.nq_v2b_fills,
        es_v2b_fills=args.es_v2b_fills,
        nq_v2b_units=args.nq_v2b_units,
        es_v2b_units=args.es_v2b_units,
        output_root=args.output_root,
        regimes=regimes,
        confirm_window_days=args.confirm_window_days,
        fakeout_lookahead_days=args.fakeout_lookahead_days,
    )
    summary = ", ".join([f"{k}={v}" for k, v in totals.items()])
    print(f"ORB divergence study complete: {summary}")
    print(f"Wrote {args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
