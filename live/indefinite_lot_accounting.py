"""Lot-correct indefinite / multi-campaign accounting (post-process).

Rebuilds ST+PMC runner books **without cross-trade FIFO**:

1. **Continuous-inventory book** — trade-matched realized + mark of every still-open
   lot at the terminal sample close. Open inventory reported separately.
2. **Forced-flat book** — same mark, plus fee (+ optional tick slip) on liquidating
   every remaining lot. This is the only version comparable to flat 3R / 10R rows.
3. **Reachable stress** — intrabar adverse clipped to the live protective stop
   (hard SL or BE after TP1), with gap-open fill when the bar opens beyond the stop.

Indefinite variants with 45–137 concurrent units are **not rankable** on the legacy
FIFO net/stress until these figures replace them.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from .hourly_st_pmc_strategyplugin_variants import MARKET_CONFIGS, TICK_SIZE, load_hourly_bars
from .models import Bar as EngineBar
from .replay_audit import (
    POINT_VALUES,
    Bar,
    Unit,
    audit_units,
    units_from_live_fills,
)

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STOP_PTS = 50.0
DEFAULT_FEE = 1.5
DEFAULT_SLIP_TICKS = 1.0

INDEF_VARIANT = "sl50_tp150_runners_2r_indef"
RANKABLE_VARIANTS = ("sl50_tp150_3r_1mfill", "sl50_tp150_runners_2r_10r")


@dataclass
class LotBookResult:
    market: str
    instrument: str
    variant: str
    strategy_id: str
    rankable: bool
    closed_units: int
    open_lots_terminal: int
    trade_matched_realized_usd: float
    continuous_terminal_equity_usd: float
    forced_flat_equity_usd: float
    forced_flat_friction_usd: float
    reachable_stress_dd_usd: float
    raw_intrabar_stress_dd_usd: float
    close_mtm_dd_usd: float
    ns_forced_flat_reachable: float
    max_open_units: int
    max_gross_notional: float
    terminal_ts: str
    terminal_px: float
    notes: str = ""


def _engine_bars_to_audit(bars: Sequence[EngineBar]) -> List[Bar]:
    return [Bar(ts=b.ts, open=b.open, high=b.high, low=b.low, close=b.close) for b in bars]


def _split_closed_open(units: Sequence[Unit]) -> Tuple[List[Unit], List[Unit]]:
    closed = [u for u in units if u.exit_reason not in {"open_mark", "forced_flat_eod", "forced_flat"}]
    opened = [u for u in units if u.exit_reason in {"open_mark", "forced_flat_eod", "forced_flat"}]
    return closed, opened


def reaudit_book(
    *,
    market: str,
    instrument: str,
    variant: str,
    fills_path: Path,
    strategy_id: str,
    bars: Sequence[Bar],
    stop_pts: float = DEFAULT_STOP_PTS,
    runner_be_after_tp1: bool = True,
    fee_per_unit: float = DEFAULT_FEE,
    slip_ticks: float = DEFAULT_SLIP_TICKS,
    output_root: Optional[Path] = None,
) -> LotBookResult:
    if not bars:
        raise ValueError("bars required for %s/%s" % (market, variant))
    terminal_ts = bars[-1].ts
    terminal_px = float(bars[-1].close)
    tick = float(TICK_SIZE.get(instrument.upper(), 0.25))
    pv = float(POINT_VALUES[instrument])

    # Closed-only (continuous inventory components)
    closed_units = units_from_live_fills(
        fills_path,
        strategy_id,
        match_within_trade_id=True,
        stop_pts=stop_pts,
        runner_be_after_tp1=runner_be_after_tp1,
    )
    # Forced-flat: mark remaining lots at terminal close
    flat_units = units_from_live_fills(
        fills_path,
        strategy_id,
        mark_open_ts=terminal_ts,
        mark_open_price=terminal_px,
        match_within_trade_id=True,
        stop_pts=stop_pts,
        runner_be_after_tp1=runner_be_after_tp1,
        mark_exit_reason="forced_flat_eod",
    )
    closed_only, open_marked = _split_closed_open(flat_units)
    assert len(closed_only) == len(closed_units)

    realized = sum(u.points for u in closed_only) * pv - len(closed_only) * fee_per_unit
    open_mtm = sum(u.points for u in open_marked) * pv  # mark at terminal close, no fee yet
    continuous = realized + open_mtm
    # Forced-flat friction: fee + 1 tick adverse slip per open lot
    slip_pts = slip_ticks * tick
    friction = 0.0
    for u in open_marked:
        friction += fee_per_unit + slip_pts * pv
    forced_flat = continuous - friction

    # Reachable stress audit on forced-flat unit set (open lots marked through terminal)
    audit = audit_units(
        name="%s %s lot-correct forced-flat" % (instrument, variant),
        slug=strategy_id + "_lot_correct",
        source=fills_path,
        bar_source=Path("terminal_mark"),
        bars=list(bars),
        units=flat_units,
        instrument=instrument,
        notes="trade_id match; reachable stop stress; forced_flat_eod mark",
        output_root=output_root or (fills_path.parent.parent.parent / "audits_lot_correct" / strategy_id),
        fee_per_unit=fee_per_unit,
    )

    # Raw (unclipped) stress for comparison — temporary units without stops
    raw_units = [
        Unit(
            candidate=u.candidate,
            trade_id=u.trade_id,
            unit_id=u.unit_id,
            direction=u.direction,
            entry_ts=u.entry_ts,
            entry_price=u.entry_price,
            exit_ts=u.exit_ts,
            exit_price=u.exit_price,
            exit_reason=u.exit_reason,
            entry_reason=u.entry_reason,
            hard_stop_price=None,
            be_after_ts="",
        )
        for u in flat_units
    ]
    raw_audit = audit_units(
        name="%s %s raw intrabar (diagnostic)" % (instrument, variant),
        slug=strategy_id + "_raw_stress",
        source=fills_path,
        bar_source=Path("terminal_mark"),
        bars=list(bars),
        units=raw_units,
        instrument=instrument,
        notes="diagnostic: unclipped intrabar stress",
        output_root=output_root or (fills_path.parent.parent.parent / "audits_lot_correct" / strategy_id),
        fee_per_unit=fee_per_unit,
    )

    # Max notional from equity curve open peaks — approximate via audit max_open * typical
    max_notional = 0.0
    # Walk open lots on each bar cheaply using flat_units entry/exit
    by_entry = sorted(flat_units, key=lambda u: (u.entry_ts, u.unit_id))
    by_exit = sorted(flat_units, key=lambda u: (u.exit_ts, u.unit_id))
    active: List[Unit] = []
    ei = xi = 0
    for bar in bars:
        while ei < len(by_entry) and by_entry[ei].entry_ts <= bar.ts:
            active.append(by_entry[ei])
            ei += 1
        while xi < len(by_exit) and by_exit[xi].exit_ts < bar.ts:
            u = by_exit[xi]
            try:
                active.remove(u)
            except ValueError:
                pass
            xi += 1
        max_notional = max(max_notional, sum(abs(u.entry_price) * pv for u in active))

    stress = float(audit.intrabar_mtm_dd_usd)
    ns = (forced_flat / abs(stress)) if stress else 0.0
    rankable = variant in RANKABLE_VARIANTS

    return LotBookResult(
        market=market,
        instrument=instrument,
        variant=variant,
        strategy_id=strategy_id,
        rankable=rankable,
        closed_units=len(closed_only),
        open_lots_terminal=len(open_marked),
        trade_matched_realized_usd=round(realized, 2),
        continuous_terminal_equity_usd=round(continuous, 2),
        forced_flat_equity_usd=round(forced_flat, 2),
        forced_flat_friction_usd=round(friction, 2),
        reachable_stress_dd_usd=round(stress, 2),
        raw_intrabar_stress_dd_usd=round(float(raw_audit.intrabar_mtm_dd_usd), 2),
        close_mtm_dd_usd=round(float(audit.close_mtm_dd_usd), 2),
        ns_forced_flat_reachable=round(ns, 3),
        max_open_units=int(audit.max_open_units),
        max_gross_notional=round(max_notional, 2),
        terminal_ts=terminal_ts,
        terminal_px=terminal_px,
        notes=(
            "NOT RANKABLE vs 3R/10R"
            if variant == INDEF_VARIANT
            else "lot-correct reconciliation"
        ),
    )


_FX_STOP_PTS = {
    "us30": 50.0,
    "nas100": 50.0,
    "spx500": 50.0,
    "xauusd": 50.0,
    "xagusd": 50.0,
    "eurusd": 0.0050,
    "gbpusd": 0.0050,
    "usdjpy": 0.50,
    "audjpy": 0.50,
}


def _hub_specs() -> List[Dict[str, object]]:
    specs: List[Dict[str, object]] = []
    us30 = REPO / "live" / "state" / "us30_st_pmc_runner_variants"
    for variant in (INDEF_VARIANT,) + RANKABLE_VARIANTS:
        sid = "us30_hourly_st_pmc_%s" % variant
        specs.append(
            {
                "hub": us30,
                "hub_name": "us30_st_pmc_runner_variants",
                "market": "us30",
                "instrument": "US30",
                "variant": variant,
                "strategy_id": sid,
                "fills": us30 / "states" / sid / "fills.csv",
                "bars_from": "us30",
                "stop_pts": 50.0,
            }
        )
    fut = REPO / "live" / "state" / "futures_st_pmc_runner_variants"
    for market, instrument in (("ym", "YM"), ("mym", "MYM"), ("mnq", "MNQ"), ("nq", "NQ")):
        for variant in (INDEF_VARIANT,) + RANKABLE_VARIANTS:
            sid = "%s_hourly_st_pmc_%s" % (market, variant)
            specs.append(
                {
                    "hub": fut,
                    "hub_name": "futures_st_pmc_runner_variants",
                    "market": market,
                    "instrument": instrument,
                    "variant": variant,
                    "strategy_id": sid,
                    "fills": fut / market / "states" / sid / "fills.csv",
                    "bars_from": market,
                    "stop_pts": 50.0,
                }
            )
    fx = REPO / "live" / "state" / "fx_index_metals_st_pmc_runner_variants"
    for market, instrument in (
        ("nas100", "NAS100"),
        ("eurusd", "EURUSD"),
        ("gbpusd", "GBPUSD"),
        ("usdjpy", "USDJPY"),
        ("audjpy", "AUDJPY"),
        ("xauusd", "XAUUSD"),
        ("xagusd", "XAGUSD"),
        ("spx500", "SPX500"),
    ):
        for variant in (INDEF_VARIANT,) + RANKABLE_VARIANTS:
            sid = "%s_hourly_st_pmc_%s" % (market, variant)
            specs.append(
                {
                    "hub": fx,
                    "hub_name": "fx_index_metals_st_pmc_runner_variants",
                    "market": market,
                    "instrument": instrument,
                    "variant": variant,
                    "strategy_id": sid,
                    "fills": fx / market / "states" / sid / "fills.csv",
                    "bars_from": market,
                    "stop_pts": float(_FX_STOP_PTS.get(market, 50.0)),
                }
            )
    return specs


def _load_fx_hourly(market_key: str, instrument: str) -> List[Bar]:
    from .fx_data import load_fx_1m_by_ny_date
    from .ym_hourly_st_pmc_retest_replay import concat_all_1m, resample_hourly

    path = REPO / "fx" / ("%s_1m.csv" % market_key)
    gby = load_fx_1m_by_ny_date(path, instrument)
    m1 = concat_all_1m(gby)
    hourly = resample_hourly(m1)
    out: List[Bar] = []
    for ts, row in hourly.iterrows():
        out.append(
            Bar(
                ts=ts.isoformat(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
            )
        )
    return out


def _load_bars(market_key: str, instrument: str = "") -> List[Bar]:
    if market_key in _FX_STOP_PTS or market_key in {
        "us30",
        "nas100",
        "eurusd",
        "gbpusd",
        "usdjpy",
        "audjpy",
        "xauusd",
        "xagusd",
        "spx500",
    }:
        inst = instrument or {
            "us30": "US30",
            "nas100": "NAS100",
            "spx500": "SPX500",
            "eurusd": "EURUSD",
            "gbpusd": "GBPUSD",
            "usdjpy": "USDJPY",
            "audjpy": "AUDJPY",
            "xauusd": "XAUUSD",
            "xagusd": "XAGUSD",
        }.get(market_key, market_key.upper())
        return _load_fx_hourly(market_key, inst)
    cfg = MARKET_CONFIGS[market_key]
    engine_bars = load_hourly_bars(Path(cfg["dbn"]), str(cfg["instrument"]))
    return _engine_bars_to_audit(engine_bars)


def write_reports(hub: Path, hub_name: str, rows: Sequence[LotBookResult]) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    csv_path = hub / "LOT_CORRECT_ACCOUNTING.csv"
    fields = list(asdict(rows[0]).keys()) if rows else []
    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(asdict(r))

    lines = [
        "# Lot-correct accounting — %s" % hub_name,
        "",
        "Replaces cross-trade FIFO nets for multi-lot books.",
        "",
        "## Rankability",
        "",
        "| Class | Status |",
        "|---|---|",
        "| Fair 3R / max 1 | **Rankable** (lot match still applied) |",
        "| 2R→10R / max 3 | **Rankable** after reconciliation |",
        "| Indefinite / large inventory | **Not rankable** on N/S until forced-flat + reachable stress reviewed as a separate sleeve |",
        "",
        "## Definitions",
        "",
        "- **Trade-matched realized** — closed lots paired within `trade_id`.",
        "- **Continuous terminal equity** — realized + mark of still-open lots at final sample close.",
        "- **Forced-flat equity** — continuous minus fee + 1-tick slip on liquidating open lots.",
        "- **Reachable stress DD** — intrabar adverse clipped to live stop (BE after TP1 / hard SL); gap-open uses bar open.",
        "- **Raw intrabar stress** — diagnostic unclipped mark (legacy contamination source for indef).",
        "",
        "## Results",
        "",
        "| market | variant | rankable | realized | continuous | forced-flat | friction | reachable stress | raw stress | N/S flat | open lots | max open |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in rows:
        lines.append(
            "| `%s` | `%s` | %s | $%.0f | $%.0f | $%.0f | $%.0f | $%.0f | $%.0f | %.2f | %d | %d |"
            % (
                r.market,
                r.variant,
                "yes" if r.rankable else "**no**",
                r.trade_matched_realized_usd,
                r.continuous_terminal_equity_usd,
                r.forced_flat_equity_usd,
                r.forced_flat_friction_usd,
                r.reachable_stress_dd_usd,
                r.raw_intrabar_stress_dd_usd,
                r.ns_forced_flat_reachable,
                r.open_lots_terminal,
                r.max_open_units,
            )
        )

    indef = [r for r in rows if r.variant == INDEF_VARIANT]
    if indef:
        lines.extend(
            [
                "",
                "## Indefinite sleeve (research only)",
                "",
                "Do **not** compare indefinite N/S to 3R/10R until product decision.",
                "Campaign economics remain TP1≈+150 vs losers≈−50; BE runners realize ~0 on stop,",
                "while gross notional / margin / correlated inventory are the real burdens.",
                "",
            ]
        )

    lines.extend(["", "## Artifacts", "", "- `%s`" % csv_path.name, "- `audits_lot_correct/` per strategy", ""])
    md = hub / "LOT_CORRECT_ACCOUNTING.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote %s" % csv_path, flush=True)
    print("Wrote %s" % md, flush=True)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--hubs",
        nargs="*",
        default=["us30", "futures", "fx"],
        choices=["us30", "futures", "fx"],
    )
    ap.add_argument("--markets", nargs="*", default=None)
    ap.add_argument("--only-indef", action="store_true", help="Only indefinite variants")
    ap.add_argument(
        "--skip-rankable",
        action="store_true",
        help="Skip 3R/10R reconciliation (indef only — same as --only-indef)",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)

    want_hubs = set(args.hubs)
    want_markets = set(args.markets) if args.markets else None
    bar_cache: Dict[str, List[Bar]] = {}
    by_hub: Dict[str, List[LotBookResult]] = {}
    only_indef = bool(args.only_indef or args.skip_rankable)

    def _hub_short(name: str) -> str:
        if name.startswith("us30"):
            return "us30"
        if name.startswith("futures"):
            return "futures"
        return "fx"

    for spec in _hub_specs():
        hub_name = str(spec["hub_name"])
        short = _hub_short(hub_name)
        if short not in want_hubs:
            continue
        market = str(spec["market"])
        variant = str(spec["variant"])
        if want_markets and market not in want_markets:
            continue
        if only_indef and variant != INDEF_VARIANT:
            continue
        fills = Path(spec["fills"])
        if not fills.exists():
            print("SKIP missing fills %s/%s" % (market, variant), flush=True)
            continue
        bars_key = str(spec["bars_from"])
        if bars_key not in bar_cache:
            print("Loading hourly bars for %s…" % bars_key, flush=True)
            bar_cache[bars_key] = _load_bars(bars_key, str(spec["instrument"]))
            print("  %d bars" % len(bar_cache[bars_key]), flush=True)
        print("LOT-AUDIT %s/%s" % (market, variant), flush=True)
        hub = Path(spec["hub"])
        out = hub / "audits_lot_correct" / str(spec["strategy_id"])
        res = reaudit_book(
            market=market,
            instrument=str(spec["instrument"]),
            variant=variant,
            fills_path=fills,
            strategy_id=str(spec["strategy_id"]),
            bars=bar_cache[bars_key],
            stop_pts=float(spec.get("stop_pts") or DEFAULT_STOP_PTS),
            runner_be_after_tp1=True,
            output_root=out,
        )
        by_hub.setdefault(hub_name, []).append(res)
        print(
            "  realized=$%.0f continuous=$%.0f forced_flat=$%.0f reachable_stress=$%.0f "
            "raw_stress=$%.0f open=%d N/S=%.2f rankable=%s"
            % (
                res.trade_matched_realized_usd,
                res.continuous_terminal_equity_usd,
                res.forced_flat_equity_usd,
                res.reachable_stress_dd_usd,
                res.raw_intrabar_stress_dd_usd,
                res.open_lots_terminal,
                res.ns_forced_flat_reachable,
                res.rankable,
            ),
            flush=True,
        )

    for hub_name, rows in by_hub.items():
        write_reports(REPO / "live" / "state" / hub_name, hub_name, rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
