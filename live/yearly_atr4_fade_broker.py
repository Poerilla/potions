"""Broker-like Engine+PaperBroker: yearly first-month ±4×ATR fade on daily bars.

Plausibility test on the FX/metals yearly-ORB names (AUDJPY, XAUUSD, XAGUSD):

After January completes, fade first touch of ``anchor ± 4 × first-month ATR``.
First-month ATR = mean daily true range of January. Default anchor = year open
(market open); ``fm_mid`` is the quarterly-4ATR analogue (January mid).

2 lots; 1@anchor + runner@opposite; reverse once on runner; risk 2×ATR;
flatten at year change. Market entries/exits use ``live_after_ts`` so fills
occur on the next daily open.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore
from .yearly_orb_sizing_sweep import FX_METALS_MARKETS, SweepMarket

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "yearly_atr4_fade_fx_metals"


@dataclass(frozen=True)
class FadeBook:
    slug: str
    label: str
    anchor: str
    atr_source: str = "jan_mean_tr"
    atr_mult: float = 4.0
    risk_atr_mult: float = 2.0
    entry_qty: int = 2
    tp1_qty: int = 1
    max_trades_per_year: int = 2

    def to_config(self, tick: float) -> Dict[str, Any]:
        return {
            "tick_size": tick,
            "entry_qty": int(self.entry_qty),
            "tp1_qty": int(self.tp1_qty),
            "atr_len": 14,
            "atr_mult": float(self.atr_mult),
            "risk_atr_mult": float(self.risk_atr_mult),
            "anchor": self.anchor,
            "atr_source": self.atr_source,
            "max_trades_per_year": int(self.max_trades_per_year),
            "allowed_sides": None,
            "timeframe": "D",
            "record_levels": False,
            "suppress_alerts": True,
        }


BOOKS: List[FadeBook] = [
    FadeBook(
        slug="year_open_jan_mean_tr",
        label="year-open ±4×Jan mean TR",
        anchor="year_open",
        atr_source="jan_mean_tr",
    ),
    FadeBook(
        slug="fm_mid_jan_mean_tr",
        label="Jan mid ±4×Jan mean TR",
        anchor="fm_mid",
        atr_source="jan_mean_tr",
    ),
]


@dataclass
class FadeResult:
    market: str
    instrument: str
    book: FadeBook
    bars: int
    units: int
    trades: int
    net_native: float
    closed_dd_native: float
    intrabar_stress_dd_native: float
    win_units: int
    loss_units: int
    pnl_ccy: str
    usd_fx_approx: Optional[float]

    @property
    def net_over_stress(self) -> float:
        if not self.intrabar_stress_dd_native:
            return 0.0
        return self.net_native / abs(self.intrabar_stress_dd_native)

    @property
    def net_usd_approx(self) -> float:
        if self.pnl_ccy == "USD" or not self.usd_fx_approx:
            return self.net_native
        return self.net_native / float(self.usd_fx_approx)

    @property
    def stress_usd_approx(self) -> float:
        if self.pnl_ccy == "USD" or not self.usd_fx_approx:
            return self.intrabar_stress_dd_native
        return self.intrabar_stress_dd_native / float(self.usd_fx_approx)

    @property
    def win_rate(self) -> float:
        n = int(self.units)
        if n <= 0:
            return 0.0
        return float(self.win_units) / float(n)


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _fmt_money(value: float, ccy: str) -> str:
    if ccy == "JPY":
        return "¥%s" % f"{value:,.0f}"
    return "$%s" % f"{value:,.2f}"


def run_one(
    *,
    output_root: Path,
    market: SweepMarket,
    book: FadeBook,
    force: bool,
    slippage_ticks: float,
) -> FadeResult:
    strategy_id = "%s_yatr4_%s" % (market.market, book.slug)
    state_root = output_root / "states" / strategy_id
    audits_root = output_root / "audits"
    if force and state_root.exists():
        shutil.rmtree(state_root)

    POINT_VALUES[market.instrument] = POINT_VALUES[market.instrument]
    if market.tick is not None:
        DEFAULT_TICK_SIZE[market.instrument] = market.tick

    bars = bars_from_csv(market.daily_path, market.instrument, "D", source=str(market.daily_path))
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    tick = float(market.tick if market.tick is not None else 0.01)
    payload = book.to_config(tick)
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="yearly_atr4_fade",
                    version="v1",
                    instrument=market.instrument,
                    broker_instrument=market.instrument,
                    account_mode="paper",
                    enabled=True,
                    timeframes="D",
                    max_contracts=max(int(book.entry_qty), 1),
                    max_open_orders=32,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    tick_kw = {"tick_size": {market.instrument: tick}} if market.tick is not None else {}
    engine = Engine(store=store, slippage_ticks=slippage_ticks, persist_health=False, **tick_kw)
    engine.replay_bars(bars)
    store.flush_tables()
    if bars:
        generate_market_close_report(store, bars[-1].ts[:10])

    bar_path = state_root / "bars" / ("%s_D.csv" % market.instrument)
    replay_bars = read_bars(bar_path, "ts")
    units = units_from_live_fills(
        state_root / "fills.csv",
        strategy_id,
        replay_bars[-1].ts if replay_bars else "",
        replay_bars[-1].close if replay_bars else None,
    )
    audit = audit_units(
        name="%s yearly ATR4 fade %s" % (market.instrument, book.label),
        slug=strategy_id,
        source=state_root / "fills.csv",
        bar_source=bar_path,
        bars=replay_bars,
        units=units,
        instrument=market.instrument,
        notes=(
            "First-month ±4×ATR fade. anchor=%s atr_source=%s atr_mult=%s risk=%s×ATR. "
            "Realism: slippage=%g tick, fee=%.2f %s/unit."
            % (
                book.anchor,
                book.atr_source,
                book.atr_mult,
                book.risk_atr_mult,
                slippage_ticks,
                market.fee_per_unit,
                market.pnl_ccy,
            )
        ),
        output_root=audits_root,
        fee_per_unit=float(market.fee_per_unit),
    )
    return FadeResult(
        market=market.market,
        instrument=market.instrument,
        book=book,
        bars=len(replay_bars),
        units=audit.units,
        trades=audit.trades,
        net_native=audit.net_usd,
        closed_dd_native=audit.close_mtm_dd_usd,
        intrabar_stress_dd_native=audit.intrabar_mtm_dd_usd,
        win_units=audit.win_units,
        loss_units=audit.loss_units,
        pnl_ccy=market.pnl_ccy,
        usd_fx_approx=market.usd_fx_approx,
    )


def write_summary(output_root: Path, rows: Sequence[FadeResult], slippage_ticks: float) -> None:
    ranked = sorted(rows, key=lambda r: r.net_over_stress, reverse=True)
    csv_rows: List[Dict[str, str]] = []
    for rank, r in enumerate(ranked, start=1):
        csv_rows.append(
            {
                "rank": str(rank),
                "market": r.market,
                "instrument": r.instrument,
                "slug": r.book.slug,
                "label": r.book.label,
                "anchor": r.book.anchor,
                "atr_source": r.book.atr_source,
                "atr_mult": "%.2f" % r.book.atr_mult,
                "risk_atr_mult": "%.2f" % r.book.risk_atr_mult,
                "bars": str(r.bars),
                "units": str(r.units),
                "trades": str(r.trades),
                "win_units": str(r.win_units),
                "loss_units": str(r.loss_units),
                "win_rate": "%.4f" % r.win_rate,
                "pnl_ccy": r.pnl_ccy,
                "net_native": "%.2f" % r.net_native,
                "closed_dd_native": "%.2f" % r.closed_dd_native,
                "intrabar_stress_dd_native": "%.2f" % r.intrabar_stress_dd_native,
                "net_usd_approx": "%.2f" % r.net_usd_approx,
                "stress_usd_approx": "%.2f" % r.stress_usd_approx,
                "net_over_stress": "%.2f" % r.net_over_stress,
            }
        )
    _write_csv(output_root / "summary.csv", csv_rows)

    lines = [
        "# Yearly first-month ±4×ATR fade (FX/metals)",
        "",
        "Engine + PaperBroker on **daily** bars. January mean daily TR is the first-month ATR.",
        "After January completes, fade first touch of **anchor ± 4×ATR**. 2 lots; 1@anchor +",
        "runner@opposite; reverse once; risk 2×ATR; flatten at year change.",
        "",
        "Causal market entry/flatten: `live_after_ts=decision_bar.ts` (next daily open).",
        "Realism: `slippage_ticks=%g`, metals $1.50/unit, AUDJPY ¥7/unit. AUDJPY ~USD uses ÷110."
        % slippage_ticks,
        "",
        "Rank by Net/Stress. Research / not promotion-safe.",
        "",
        "| Rank | Market | Book | Trades | Units | Net | Stress DD | N/S | WR |",
        "|---:|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for i, r in enumerate(ranked, start=1):
        usd_note = ""
        if r.pnl_ccy != "USD" and r.usd_fx_approx:
            usd_note = " (~%s)" % _fmt_money(r.net_usd_approx, "USD")
        lines.append(
            "| %d | %s | %s | %d | %d | %s%s | %s | %.2f | %.1f%% |"
            % (
                i,
                r.instrument,
                r.book.label,
                r.trades,
                r.units,
                _fmt_money(r.net_native, r.pnl_ccy),
                usd_note,
                _fmt_money(r.intrabar_stress_dd_native, r.pnl_ccy),
                r.net_over_stress,
                100.0 * r.win_rate,
            )
        )
    lines += ["", "## Per-market", ""]
    by_m: Dict[str, List[FadeResult]] = {}
    for r in rows:
        by_m.setdefault(r.instrument, []).append(r)
    for inst in sorted(by_m):
        lines.append("### %s" % inst)
        lines.append("")
        for r in sorted(by_m[inst], key=lambda x: x.net_over_stress, reverse=True):
            extra = ""
            if r.pnl_ccy != "USD" and r.usd_fx_approx:
                extra = " (~%s / %s @%g)" % (
                    _fmt_money(r.net_usd_approx, "USD"),
                    _fmt_money(r.stress_usd_approx, "USD"),
                    r.usd_fx_approx,
                )
            lines.append(
                "- **%s** N/S=%.2f net=%s stress=%s trades=%d units=%d WR=%.1f%%%s"
                % (
                    r.book.label,
                    r.net_over_stress,
                    _fmt_money(r.net_native, r.pnl_ccy),
                    _fmt_money(r.intrabar_stress_dd_native, r.pnl_ccy),
                    r.trades,
                    r.units,
                    100.0 * r.win_rate,
                    extra,
                )
            )
        lines.append("")
    lines += [
        "Hub: `%s`" % output_root.as_posix().replace(str(REPO) + "/", ""),
        "",
        "Stance: research only. Compare to yearly ORB breakout on the same names;",
        "do not promote without a causality audit and yearly N/S split.",
        "",
    ]
    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def write_email(output_root: Path, rows: Sequence[FadeResult]) -> Path:
    by_m: Dict[str, List[FadeResult]] = {}
    for r in rows:
        by_m.setdefault(r.instrument, []).append(r)
    lines = [
        "potions: yearly first-month ±4×ATR fade (FX/metals) complete",
        "",
        "Hub: live/state/yearly_atr4_fade_fx_metals",
        "Book: after January, fade first touch of anchor ±4×Jan mean daily TR.",
        "2 lots; 1@anchor + runner@opposite; reverse once; risk 2×ATR; EOY flatten.",
        "Daily Engine+PaperBroker. AUDJPY ~USD @110. Rank by N/S.",
        "",
    ]
    for inst in sorted(by_m):
        ranked = sorted(by_m[inst], key=lambda x: x.net_over_stress, reverse=True)
        best = ranked[0]
        lines.append(
            "%s best: %s N/S=%.2f net=%s stress=%s trades=%d WR=%.0f%%"
            % (
                inst,
                best.book.label,
                best.net_over_stress,
                _fmt_money(best.net_native, best.pnl_ccy),
                _fmt_money(best.intrabar_stress_dd_native, best.pnl_ccy),
                best.trades,
                100.0 * best.win_rate,
            )
        )
        for r in ranked:
            extra = ""
            if r.pnl_ccy != "USD" and r.usd_fx_approx:
                extra = " (~%s)" % _fmt_money(r.net_usd_approx, "USD")
            lines.append(
                "  %s  N/S=%.2f net=%s%s trades=%d units=%d"
                % (
                    r.book.slug,
                    r.net_over_stress,
                    _fmt_money(r.net_native, r.pnl_ccy),
                    extra,
                    r.trades,
                    r.units,
                )
            )
    n_pos = sum(1 for r in rows if r.net_over_stress > 0)
    lines += [
        "",
        "Positive N/S rows: %d / %d." % (n_pos, len(rows)),
        "Stance: %s"
        % (
            "research — plausible base on some names; not promotion-safe."
            if n_pos
            else "reject as a standalone base — N/S not positive on this pack."
        ),
        "",
    ]
    path = output_root / "EMAIL.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
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


def run_batch(
    *,
    output_root: Path,
    markets: Sequence[SweepMarket],
    books: Sequence[FadeBook],
    force: bool,
    email: bool,
    slippage_ticks: float,
) -> List[FadeResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    rows: List[FadeResult] = []
    try:
        for market in markets:
            for book in books:
                _progress(output_root, "START %s %s" % (market.instrument, book.slug))
                res = run_one(
                    output_root=output_root,
                    market=market,
                    book=book,
                    force=force,
                    slippage_ticks=slippage_ticks,
                )
                rows.append(res)
                extra = ""
                if res.pnl_ccy != "USD" and res.usd_fx_approx:
                    extra = " (~%s)" % _fmt_money(res.net_usd_approx, "USD")
                _progress(
                    output_root,
                    "DONE %s %s net=%s%s N/S=%.2f trades=%d units=%d"
                    % (
                        market.instrument,
                        book.slug,
                        _fmt_money(res.net_native, res.pnl_ccy),
                        extra,
                        res.net_over_stress,
                        res.trades,
                        res.units,
                    ),
                )
                write_summary(output_root, rows, slippage_ticks)
        write_summary(output_root, rows, slippage_ticks)
        write_run_manifest(
            output_root,
            data_inputs=[m.daily_path for m in markets],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={
                "plugin": "yearly_atr4_fade",
                "books": [b.slug for b in books],
                "atr_mult": 4.0,
                "risk_atr_mult": 2.0,
                "entry_qty": 2,
                "timeframe": "D",
            },
            broker_realism_config={"slippage_ticks": slippage_ticks},
            extra={"markets": [m.instrument for m in markets]},
        )
        email_path = write_email(output_root, rows)
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "n": len(rows),
                    "markets": [m.instrument for m in markets],
                    "books": [b.slug for b in books],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: yearly first-month ±4×ATR fade (FX/metals) complete",
                body=email_path.read_text(encoding="utf-8"),
            )
            _progress(output_root, "email sent")
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: yearly first-month ±4×ATR fade FAILED\n\nHub: %s\n\n%s\n"
            % (output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: yearly first-month ±4×ATR fade FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise
    return rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--markets",
        default="audjpy,xauusd,xagusd",
        help="Comma-separated: audjpy,xauusd,xagusd",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--slippage-ticks", type=float, default=1.0)
    args = ap.parse_args(list(argv) if argv is not None else None)
    wanted = {m.strip().lower() for m in str(args.markets).split(",") if m.strip()}
    markets = [m for m in FX_METALS_MARKETS if m.market in wanted]
    if not markets:
        raise SystemExit("No markets matched %s" % sorted(wanted))
    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = (Path.cwd() / output_root).resolve()
    run_batch(
        output_root=output_root,
        markets=markets,
        books=BOOKS,
        force=True,
        email=bool(args.email),
        slippage_ticks=float(args.slippage_ticks),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
