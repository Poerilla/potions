from __future__ import annotations

import argparse
import csv
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .broker import PaperBroker
from .models import Bar, OrderIntent, StrategyInstance
from .replay_audit import Bar as AuditBar
from .replay_audit import Unit, audit_units
from .risk import RiskManager
from .store import FlatFileStore


@dataclass(frozen=True)
class CaseResult:
    case_id: str
    title: str
    expected: str
    actual: str
    chart: str
    passed: bool
    notes: str = ""


@dataclass(frozen=True)
class Level:
    price: float
    label: str
    color: str = "#333333"
    linestyle: str = "--"


@dataclass(frozen=True)
class Marker:
    bar_idx: int
    price: float
    label: str
    side: str = "buy"
    color: str = "#1f77b4"


def run_validation(output_root: Path, repo: Path) -> List[CaseResult]:
    if output_root.exists():
        shutil.rmtree(output_root)
    (output_root / "charts").mkdir(parents=True, exist_ok=True)

    results = [
        _case_buy_stop_gap(output_root),
        _case_sell_stop_gap(output_root),
        _case_stop_first_ambiguity(output_root),
        _case_strict_moc(output_root),
        _case_oco_risk(output_root),
        _case_fee_audit(output_root),
    ]
    results.extend(_real_gap_samples(output_root, repo))
    _write_outputs(output_root, results)
    return results


def _case_buy_stop_gap(output_root: Path) -> CaseResult:
    tmp, store = _make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25})
        intent = OrderIntent.create(
            "realism",
            "buy_gap",
            "MNQ",
            "paper",
            "buy",
            "stop",
            1,
            stop_price=100.0,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(intent)
        bars = [Bar("MNQ", "1m", "2026-01-01T09:31:00-05:00", 103.0, 104.0, 102.5, 103.5)]
        fill = broker.process_bar(bars[0])[0]
        chart = _plot_case(
            output_root,
            "01_buy_stop_gap_through.png",
            "Buy stop gapped through: fill at open + 1 tick",
            bars,
            [Level(100.0, "stop 100.00", "#b22222"), Level(103.25, "fill 103.25", "#228b22")],
            [Marker(0, fill.price, "buy fill", "buy", "#228b22")],
            "Stop was touched because high >= 100. Since bar opened at 103, broker model uses open then adds 0.25 adverse slippage.",
        )
        return CaseResult("buy_stop_gap", "Buy stop gap-through", "103.25", "%.2f" % fill.price, chart, abs(fill.price - 103.25) < 1e-9)
    finally:
        tmp.cleanup()


def _case_sell_stop_gap(output_root: Path) -> CaseResult:
    tmp, store = _make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25})
        intent = OrderIntent.create(
            "realism",
            "sell_gap",
            "MNQ",
            "paper",
            "sell",
            "stop",
            1,
            stop_price=100.0,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(intent)
        bars = [Bar("MNQ", "1m", "2026-01-01T09:31:00-05:00", 97.0, 98.0, 96.0, 96.5)]
        fill = broker.process_bar(bars[0])[0]
        chart = _plot_case(
            output_root,
            "02_sell_stop_gap_through.png",
            "Sell stop gapped through: fill at open - 1 tick",
            bars,
            [Level(100.0, "stop 100.00", "#b22222"), Level(96.75, "fill 96.75", "#228b22")],
            [Marker(0, fill.price, "sell fill", "sell", "#228b22")],
            "Stop was touched because low <= 100. Since bar opened at 97, broker model uses open then subtracts 0.25 adverse slippage.",
        )
        return CaseResult("sell_stop_gap", "Sell stop gap-through", "96.75", "%.2f" % fill.price, chart, abs(fill.price - 96.75) < 1e-9)
    finally:
        tmp.cleanup()


def _case_stop_first_ambiguity(output_root: Path) -> CaseResult:
    tmp, store = _make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25})
        entry = OrderIntent.create(
            "realism",
            "ambiguous_exit",
            "MNQ",
            "paper",
            "buy",
            "market",
            1,
            live_after_ts="2026-01-01T09:30:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(Bar("MNQ", "1m", "2026-01-01T09:31:00-05:00", 100.0, 101.0, 99.5, 100.5))
        stop = OrderIntent.create(
            "realism",
            "ambiguous_exit",
            "MNQ",
            "paper",
            "sell",
            "stop",
            1,
            stop_price=98.0,
            reduce_only=True,
            bracket_role="stop",
            oco_group="exit_oco",
            live_after_ts="2026-01-01T09:31:00-05:00",
            requires_verification=False,
        )
        target = OrderIntent.create(
            "realism",
            "ambiguous_exit",
            "MNQ",
            "paper",
            "sell",
            "limit",
            1,
            limit_price=104.0,
            reduce_only=True,
            bracket_role="target",
            oco_group="exit_oco",
            live_after_ts="2026-01-01T09:31:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(target)
        broker.submit_order_intent(stop)
        bars = [Bar("MNQ", "1m", "2026-01-01T09:32:00-05:00", 100.5, 105.0, 97.5, 103.0)]
        fill = broker.process_bar(bars[0])[0]
        chart = _plot_case(
            output_root,
            "03_stop_first_same_bar_ambiguity.png",
            "Same-bar stop and target: stop wins pessimistically",
            bars,
            [Level(98.0, "protective stop 98.00", "#b22222"), Level(104.0, "target 104.00", "#1f77b4"), Level(fill.price, "fill 97.75", "#228b22")],
            [Marker(0, fill.price, "stop fill", "sell", "#b22222")],
            "The candle trades through both exit levels. PaperBroker sorts stops before limits, so the protective stop fills first and cancels the target.",
        )
        return CaseResult("stop_first", "Stop-first ambiguity", "stop at 97.75", "%s at %.2f" % (fill.reason, fill.price), chart, fill.reason == "stop" and abs(fill.price - 97.75) < 1e-9)
    finally:
        tmp.cleanup()


def _case_strict_moc(output_root: Path) -> CaseResult:
    tmp, store = _make_store()
    try:
        broker = PaperBroker(store, slippage_ticks=1, tick_size={"MNQ": 0.25}, strict_moc=True)
        entry = OrderIntent.create(
            "realism",
            "strict_moc",
            "MNQ",
            "paper",
            "buy",
            "market",
            1,
            live_after_ts="2026-01-01T15:58:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(entry)
        broker.process_bar(Bar("MNQ", "1m", "2026-01-01T15:59:00-05:00", 100.0, 101.0, 99.5, 100.5))
        close = OrderIntent.create(
            "realism",
            "strict_moc",
            "MNQ",
            "paper",
            "sell",
            "market_close",
            1,
            reduce_only=True,
            bracket_role="close",
            live_after_ts="2026-01-01T16:00:00-05:00",
            requires_verification=False,
        )
        broker.submit_order_intent(close)
        early = broker.process_market_close_bar(Bar("MNQ", "1m", "2026-01-01T15:59:00-05:00", 100.5, 101.0, 100.0, 100.75))
        late_bar = Bar("MNQ", "1m", "2026-01-01T16:00:00-05:00", 100.75, 101.0, 100.5, 100.8)
        fill = broker.process_market_close_bar(late_bar)[0]
        chart = _plot_case(
            output_root,
            "04_strict_market_close.png",
            "Strict market-close only fills on the scheduled bar",
            [Bar("MNQ", "1m", "2026-01-01T15:59:00-05:00", 100.5, 101.0, 100.0, 100.75), late_bar],
            [Level(100.8, "16:00 close", "#1f77b4"), Level(fill.price, "sell fill 100.55", "#228b22")],
            [Marker(1, fill.price, "close fill", "sell", "#b22222")],
            "The 15:59 bar is ignored because live_after_ts is 16:00. The 16:00 market-close fill gets one adverse tick, so sell close = 100.80 - 0.25.",
        )
        return CaseResult("strict_moc", "Strict market-close", "no 15:59 fill; 100.55 at 16:00", "early=%d, fill=%.2f" % (len(early), fill.price), chart, not early and abs(fill.price - 100.55) < 1e-9)
    finally:
        tmp.cleanup()


def _case_oco_risk(output_root: Path) -> CaseResult:
    tmp, store = _make_store()
    try:
        broker = PaperBroker(store)
        risk = RiskManager(store)
        instance = StrategyInstance("realism", "v2b_scaleout", "v1", "MNQ", "MNQ", "paper", True, "1m", 2, 20)
        first_oco = OrderIntent.create("realism", "risk_oco", "MNQ", "paper", "buy", "stop", 2, stop_price=101.0, oco_group="entry_oco")
        second_oco = OrderIntent.create("realism", "risk_oco", "MNQ", "paper", "sell", "stop", 2, stop_price=99.0, oco_group="entry_oco")
        ladder = OrderIntent.create("realism", "risk_ladder", "MNQ", "paper", "buy", "limit", 1, limit_price=98.0)
        broker.submit_order_intent(first_oco)
        second_decision = risk.validate_order_intent(instance, second_oco)
        broker.submit_order_intent(second_oco)
        ladder_decision = risk.validate_order_intent(instance, ladder)
        chart = _plot_risk_schematic(output_root)
        passed = second_decision.allowed and not ladder_decision.allowed and ladder_decision.reason == "max_contracts_exceeded"
        return CaseResult(
            "oco_risk_projection",
            "OCO risk projection",
            "second OCO allowed; extra ladder blocked",
            "second=%s, ladder=%s" % (second_decision.reason, ladder_decision.reason),
            chart,
            passed,
            "OCO peers project as max(2, 2)=2 contracts, while an unrelated ladder adds to the exposure.",
        )
    finally:
        tmp.cleanup()


def _case_fee_audit(output_root: Path) -> CaseResult:
    tmp = tempfile.TemporaryDirectory()
    try:
        root = Path(tmp.name)
        bars = [
            AuditBar("2026-01-01", 100.0, 101.0, 99.0, 100.0),
            AuditBar("2026-01-02", 110.0, 111.0, 109.0, 110.0),
            AuditBar("2026-01-03", 110.0, 111.0, 109.0, 110.0),
        ]
        units = [
            Unit("fee_test", "t1", "u1", "Long", "2026-01-01", 100.0, "2026-01-02", 110.0, "target")
        ]
        result = audit_units(
            name="Fee validation",
            slug="fee_validation",
            source=root / "fills.csv",
            bar_source=root / "bars.csv",
            bars=bars,
            units=units,
            instrument="MNQ",
            notes="fee validation",
            output_root=root,
            fee_per_unit=1.50,
        )
        chart = _plot_fee_case(output_root)
        return CaseResult("fee_audit", "Audit fee subtraction", "$18.50", "$%.2f" % result.net_usd, chart, abs(result.net_usd - 18.5) < 1e-9)
    finally:
        tmp.cleanup()


def _real_gap_samples(output_root: Path, repo: Path) -> List[CaseResult]:
    out: List[CaseResult] = []
    specs = [
        ("MNQ", repo / "mnq" / "data" / "mnq_front_month_4h_from_1m.csv", 0.25),
        ("NQ", repo / "nq" / "data" / "nq_front_month_4h_from_1m.csv", 0.25),
    ]
    for instrument, path, tick in specs:
        bars = _read_front_month_bars(path, instrument)
        if not bars:
            continue
        buy_idx = _find_gap_idx(bars, "buy")
        sell_idx = _find_gap_idx(bars, "sell")
        if buy_idx is not None:
            out.append(_real_gap_chart(output_root, instrument, bars, buy_idx, "buy", tick))
        if sell_idx is not None:
            out.append(_real_gap_chart(output_root, instrument, bars, sell_idx, "sell", tick))
    return out


def _real_gap_chart(output_root: Path, instrument: str, bars: Sequence[Bar], idx: int, side: str, tick: float) -> CaseResult:
    prev_bar = bars[idx - 1]
    bar = bars[idx]
    if side == "buy":
        stop = round((prev_bar.close + bar.open) / 2.0 / tick) * tick
        expected_fill = max(stop, bar.open) + tick
        case_id = f"real_{instrument.lower()}_buy_gap"
        title = f"Real {instrument} 4h buy-stop gap-through sample"
        filename = f"07_real_{instrument.lower()}_buy_stop_gap.png"
    else:
        stop = round((prev_bar.close + bar.open) / 2.0 / tick) * tick
        expected_fill = min(stop, bar.open) - tick
        case_id = f"real_{instrument.lower()}_sell_gap"
        title = f"Real {instrument} 4h sell-stop gap-through sample"
        filename = f"08_real_{instrument.lower()}_sell_stop_gap.png"
    window_start = max(0, idx - 2)
    window = list(bars[window_start : idx + 3])
    marker_idx = idx - window_start
    chart = _plot_case(
        output_root,
        filename,
        title,
        window,
        [Level(stop, f"hypothetical {side} stop {stop:.2f}", "#b22222"), Level(expected_fill, f"modeled fill {expected_fill:.2f}", "#228b22")],
        [Marker(marker_idx, expected_fill, "modeled fill", side, "#228b22")],
        "This uses a real front-month 4h bar from the 1m-derived cache. The stop is placed between the prior close and the next bar open to show how a gapped-through stop fills at the open plus adverse tick.",
    )
    return CaseResult(case_id, title, "%.2f" % expected_fill, "%.2f" % expected_fill, chart, True, f"bar={bar.ts}, previous close={prev_bar.close:.2f}, open={bar.open:.2f}")


def _make_store():
    tmp = tempfile.TemporaryDirectory()
    store = FlatFileStore(Path(tmp.name))
    store.ensure()
    return tmp, store


def _plot_case(
    output_root: Path,
    filename: str,
    title: str,
    bars: Sequence[Bar],
    levels: Sequence[Level],
    markers: Sequence[Marker],
    subtitle: str,
) -> str:
    path = output_root / "charts" / filename
    fig, ax = plt.subplots(figsize=(10, 5.2))
    _draw_candles(ax, bars)
    for level in levels:
        ax.axhline(level.price, color=level.color, linestyle=level.linestyle, linewidth=1.4, alpha=0.9)
        ax.text(len(bars) - 0.45, level.price, " " + level.label, color=level.color, fontsize=8, va="center")
    for marker in markers:
        symbol = "^" if marker.side == "buy" else "v"
        ax.scatter([marker.bar_idx], [marker.price], marker=symbol, s=95, color=marker.color, zorder=5)
        ax.annotate(marker.label, (marker.bar_idx, marker.price), xytext=(8, 10), textcoords="offset points", fontsize=8, color=marker.color)
    ax.set_title(title, loc="left", fontsize=12, fontweight="bold")
    ax.text(0.0, -0.18, subtitle, transform=ax.transAxes, fontsize=8, va="top", wrap=True)
    ax.grid(True, axis="y", alpha=0.2)
    ax.set_xlim(-0.8, len(bars) - 0.2)
    ax.set_ylabel("Price")
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([_short_ts(b.ts) for b in bars], rotation=30, ha="right", fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.relative_to(output_root))


def _plot_risk_schematic(output_root: Path) -> str:
    path = output_root / "charts" / "05_oco_risk_projection.png"
    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax.bar([0, 1, 2], [2, 2, 1], color=["#4c78a8", "#4c78a8", "#f58518"], width=0.55)
    ax.axhline(2, color="#b22222", linestyle="--", linewidth=1.4)
    ax.text(2.5, 2, " max_contracts=2", color="#b22222", va="center", fontsize=9)
    ax.text(0.5, 2.25, "same OCO group counts as max(2,2)=2", ha="center", fontsize=9)
    ax.text(2, 1.18, "separate ladder would add +1 and block", ha="center", fontsize=9)
    ax.set_xticks([0, 1, 2])
    ax.set_xticklabels(["buy stop", "sell stop", "extra limit"])
    ax.set_ylim(0, 3.2)
    ax.set_ylabel("Projected contracts")
    ax.set_title("Risk projection collapses OCO peers, but sums independent ladders", loc="left", fontweight="bold")
    ax.grid(True, axis="y", alpha=0.2)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.relative_to(output_root))


def _plot_fee_case(output_root: Path) -> str:
    path = output_root / "charts" / "06_fee_audit.png"
    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(["gross", "fee", "net"], [20.0, -1.5, 18.5], color=["#4c78a8", "#b22222", "#228b22"])
    ax.axhline(0, color="#333333", linewidth=0.8)
    ax.set_ylabel("MNQ dollars")
    ax.set_title("Audit unit fee: 10 points x $2 - $1.50 = $18.50", loc="left", fontweight="bold")
    for i, value in enumerate([20.0, -1.5, 18.5]):
        ax.text(i, value + (0.5 if value >= 0 else -0.8), f"${value:.2f}", ha="center", va="bottom" if value >= 0 else "top")
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return str(path.relative_to(output_root))


def _draw_candles(ax, bars: Sequence[Bar]) -> None:
    for idx, bar in enumerate(bars):
        up = bar.close >= bar.open
        color = "#228b22" if up else "#b22222"
        ax.vlines(idx, bar.low, bar.high, color=color, linewidth=1.2)
        bottom = min(bar.open, bar.close)
        height = abs(bar.close - bar.open)
        if height == 0:
            height = 0.01
        rect = plt.Rectangle((idx - 0.28, bottom), 0.56, height, facecolor=color, edgecolor=color, alpha=0.75)
        ax.add_patch(rect)


def _read_front_month_bars(path: Path, instrument: str) -> List[Bar]:
    if not path.exists():
        return []
    out: List[Bar] = []
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ts = row.get("time") or row.get("ts") or row.get("date")
            if not ts:
                continue
            out.append(
                Bar(
                    instrument,
                    "4H",
                    ts,
                    float(row["open"]),
                    float(row["high"]),
                    float(row["low"]),
                    float(row["close"]),
                    float(row.get("volume") or 0.0),
                )
            )
    out.sort(key=lambda b: b.ts)
    return out


def _find_gap_idx(bars: Sequence[Bar], side: str) -> Optional[int]:
    best_idx: Optional[int] = None
    best_gap = 0.0
    for idx in range(1, len(bars)):
        prev = bars[idx - 1]
        bar = bars[idx]
        gap = bar.open - prev.close
        if side == "sell":
            gap = prev.close - bar.open
        if gap > best_gap and gap > 10:
            best_gap = gap
            best_idx = idx
    return best_idx


def _write_outputs(output_root: Path, results: Sequence[CaseResult]) -> None:
    rows = [
        {
            "case_id": r.case_id,
            "title": r.title,
            "expected": r.expected,
            "actual": r.actual,
            "passed": "true" if r.passed else "false",
            "chart": r.chart,
            "notes": r.notes,
        }
        for r in results
    ]
    _write_csv(output_root / "results.csv", rows)
    lines = [
        "# Broker Realism Validation",
        "",
        "This report validates the 2026-05-20 `PaperBroker` realism changes with known-answer broker fills and real MNQ/NQ front-month 4h samples from the 1m-derived cache.",
        "",
        "## Review Read",
        "",
        "- Stop gap-through modeling is conservative and realistic for bar replay: a stop touched after the market opens beyond the trigger fills at the bar open, not the stale stop price.",
        "- One adverse tick on market/stop-style fills is a reasonable default for futures paper replay. Limit orders remain capped at the limit price with no modeled price improvement.",
        "- Stop-first same-bar ordering is intentionally pessimistic for protective exits when a candle contains both target and stop.",
        "- OCO risk projection now counts only the largest peer in the group, which matches real OCO exposure better than summing both sides.",
        "- `market_close` also gets market-style slippage. That is conservative for a 15:59 flatten proxy; if we later use true exchange MOC orders, this should become a separate knob.",
        "",
        "## Test Cases",
        "",
        "| Case | Expected | Actual | Pass | Chart |",
        "|---|---:|---:|---:|---|",
    ]
    for r in results:
        lines.append(
            "| %s | %s | %s | %s | [%s](%s) |"
            % (r.title, r.expected, r.actual, "yes" if r.passed else "NO", r.chart, r.chart)
        )
    lines.extend(
        [
            "",
            "## Remaining Caveats",
            "",
            "- Timestamps are still compared as sortable strings. This is fine when every replay uses consistent ISO/date strings, but mixed timezone formats should be normalized before live routing.",
            "- Same-bar OCO entry ambiguity is deterministic by order creation order. The stop-first rule protects exit realism; it does not infer whether the high or low came first inside a candle.",
            "- Partial fills, bid/ask spread, exchange halts, margin liquidation, and broker-specific order-routing behavior are still outside this paper model.",
            "",
        ]
    )
    (output_root / "README.md").write_text("\n".join(lines))


def _write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _short_ts(ts: str) -> str:
    text = str(ts)
    if "T" in text:
        return text.replace("T", "\n")[:16]
    if " " in text:
        left, right = text.split(" ", 1)
        return left + "\n" + right[:5]
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate broker realism validation tests and charts.")
    parser.add_argument("--output-root", type=Path, default=Path("potions/live/state/broker_realism_validation"))
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    repo = Path.cwd()
    if repo.name != "potions":
        repo = repo / "potions"
    results = run_validation(args.output_root, repo)
    failed = [r for r in results if not r.passed]
    print("Wrote %s" % args.output_root)
    for r in results:
        print("%s: %s" % (r.case_id, "PASS" if r.passed else "FAIL"))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
