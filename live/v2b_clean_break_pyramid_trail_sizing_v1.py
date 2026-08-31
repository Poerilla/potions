"""Broker-like sweep: v2b clean-break pyramid + trail@60%-to-2R + sizing cadence.

Extends the pyramid-outside OR book with:
  - Trail stop to BE (entry) once bar high reaches 60% of the path to 2R.
  - Optional resting 2R target once trailed.
  - Max size 4 / 8 / 12.
  - Add cadence: every 1 outside candle, every 2, or opposing (bearish) outside candles.
  - Soft exit on close <= OR high still applies; EOD 15:55 flattens.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.v2b_clean_break_pyramid_trail_sizing_v1 --email
  python -m live.v2b_clean_break_pyramid_trail_sizing_v1 --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .first_hour_follow_cross_market import MarketSpec, load_market_5m
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_clean_break_replays import (
    DEFAULT_SLIPPAGE_TICKS,
    FEE_PER_UNIT,
    MARKETS as FUTURES_MARKETS,
    MarketConfig,
    ReplayResult,
    load_5m_bars,
)
from .v2b_strategy_replay import money

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live" / "state" / "v2b_clean_break_pyramid_trail_sizing_v1"
STUDY_ID = "v2b_clean_break_pyramid_trail_sizing_v1"
DSR = "TRL-2026-00194"

# Index CFDs (OANDA-style): $1/pt, tick 0.1 — same economics as cfd_wick / first-hour books.
CFD_SPECS: Dict[str, MarketSpec] = {
    "nas100": MarketSpec("NAS100", "cfd", 0.1, 1.0, "USD", "fx_1m", REPO / "fx" / "nas100_1m.csv"),
    "us30": MarketSpec("US30", "cfd", 0.1, 1.0, "USD", "fx_1m", REPO / "fx" / "us30_1m.csv"),
    "spx500": MarketSpec("SPX500", "cfd", 0.1, 1.0, "USD", "fx_1m", REPO / "fx" / "spx500_1m.csv"),
}
MARKETS: Dict[str, MarketConfig] = dict(FUTURES_MARKETS)
for _k, _spec in CFD_SPECS.items():
    MARKETS[_k] = MarketConfig(_k, _spec.symbol, _spec.path)
TICK_BY_INSTRUMENT: Dict[str, float] = {
    "NQ": 0.25,
    "MNQ": 0.25,
    "MES": 0.25,
    "MYM": 1.0,
    "NAS100": 0.1,
    "US30": 0.1,
    "SPX500": 0.1,
}
MARKET_CHOICES = sorted(MARKETS.keys())


@dataclass(frozen=True)
class PyramidVariant:
    name: str
    label: str
    max_qty: int
    add_every_n: int
    add_mode: str  # outside | opposing
    trail_at_frac: float
    trail_to: str = "entry"

    def config(self) -> Dict[str, Any]:
        return {
            "variant": self.name,
            "entry_qty": 1,
            "required_break_num": 0,
            "stop_mode": "opposite",
            "size_model": "pyramid_outside",
            "max_pyramid_qty": self.max_qty,
            "pyramid_add_every_n": self.add_every_n,
            "pyramid_add_mode": self.add_mode,
            "trail_at_frac": self.trail_at_frac,
            "trail_to": self.trail_to,
            "pyramid_place_2r_target": self.trail_at_frac > 0,
            "entry_offset_ticks": 2,
        }


# Focused grid: isolate trail vs baseline cadence/size, then cadence + opposing.
VARIANTS: List[PyramidVariant] = [
    # Control: same as v1 max8 every-1 outside, no trail.
    PyramidVariant(
        "ctrl_m8_e1_out_notrail",
        "Control max8 every-1 outside, no trail",
        max_qty=8,
        add_every_n=1,
        add_mode="outside",
        trail_at_frac=0.0,
    ),
    # Trail @ 60% → BE, size sweep, every-1 outside.
    PyramidVariant(
        "trail06_m4_e1_out_be",
        "Trail@60%→BE max4 every-1 outside",
        max_qty=4,
        add_every_n=1,
        add_mode="outside",
        trail_at_frac=0.6,
    ),
    PyramidVariant(
        "trail06_m8_e1_out_be",
        "Trail@60%→BE max8 every-1 outside",
        max_qty=8,
        add_every_n=1,
        add_mode="outside",
        trail_at_frac=0.6,
    ),
    PyramidVariant(
        "trail06_m12_e1_out_be",
        "Trail@60%→BE max12 every-1 outside",
        max_qty=12,
        add_every_n=1,
        add_mode="outside",
        trail_at_frac=0.6,
    ),
    # Cadence: every 2 outside candles.
    PyramidVariant(
        "trail06_m8_e2_out_be",
        "Trail@60%→BE max8 every-2 outside",
        max_qty=8,
        add_every_n=2,
        add_mode="outside",
        trail_at_frac=0.6,
    ),
    PyramidVariant(
        "trail06_m4_e2_out_be",
        "Trail@60%→BE max4 every-2 outside",
        max_qty=4,
        add_every_n=2,
        add_mode="outside",
        trail_at_frac=0.6,
    ),
    PyramidVariant(
        "trail06_m12_e2_out_be",
        "Trail@60%→BE max12 every-2 outside",
        max_qty=12,
        add_every_n=2,
        add_mode="outside",
        trail_at_frac=0.6,
    ),
    # Opposing (bearish pullback) adds while still outside OR.
    PyramidVariant(
        "trail06_m8_e1_opp_be",
        "Trail@60%→BE max8 every-1 opposing",
        max_qty=8,
        add_every_n=1,
        add_mode="opposing",
        trail_at_frac=0.6,
    ),
    PyramidVariant(
        "trail06_m4_e1_opp_be",
        "Trail@60%→BE max4 every-1 opposing",
        max_qty=4,
        add_every_n=1,
        add_mode="opposing",
        trail_at_frac=0.6,
    ),
    PyramidVariant(
        "trail06_m12_e1_opp_be",
        "Trail@60%→BE max12 every-1 opposing",
        max_qty=12,
        add_every_n=1,
        add_mode="opposing",
        trail_at_frac=0.6,
    ),
]


def _progress(msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def _append_dsr(markets: Sequence[str]) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    is_cfd = any(m in CFD_SPECS for m in markets)
    is_confirm = "top3" in STUDY_ID or "confirm" in STUDY_ID or is_cfd
    market_label = ",".join(MARKETS[m].instrument for m in markets)
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "EXECUTION_VARIANT",
            "trial_subclass": STUDY_ID,
            "is_independent": "FALSE" if is_confirm else "TRUE",
            "market": market_label,
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "base": "pyramid_outside clean break",
                    "trail_at_frac": 0.6,
                    "trail_to": "entry",
                    "parent_dsr": "TRL-2026-00194",
                    "confirm": is_confirm,
                    "cfd_portability": is_cfd,
                    "study_id": STUDY_ID,
                    "markets": list(markets),
                }
            ),
            "fixed_parameters_ref": "live/v2b_clean_break_pyramid_trail_sizing_v1.py",
            "num_params_varied": "0" if is_confirm else "4",
            "counts_toward_dsr": "FALSE" if is_confirm else "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "0.00" if is_confirm else "1.00",
            "status": "PENDING",
            "notes": (
                "CFD portability of trail top-3 (parent TRL-2026-00194/195)"
                if is_cfd
                else (
                    "Top-3 broker-like confirm of trail sizing sweep winners (parent TRL-2026-00194)"
                    if is_confirm
                    else "Pyramid trail@60%to2R + max size + add cadence/opposing sweep"
                )
            ),
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _load_bars(market: MarketConfig) -> pd.DataFrame:
    """Futures RTH CSV or CFD 1m→5m RTH (cached parquet via first-hour helper)."""
    key = market.market.lower()
    if key in CFD_SPECS:
        spec = CFD_SPECS[key]
        POINT_VALUES[spec.symbol] = spec.point_value
        DEFAULT_TICK_SIZE[spec.symbol] = spec.tick
        df = load_market_5m(spec, HUB)
        df = df.copy()
        df["session_day"] = pd.to_datetime(df["ts"]).dt.date.astype(str)
        return df
    return load_5m_bars(market.bars_path, market.instrument)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ","):
            for old in ("PENDING", "RUNNING", "COMPLETE", "FAILED"):
                tok = ",%s," % old
                if tok in ln:
                    ln = ln.replace(tok, ",%s," % status, 1)
                    break
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def run_one(
    *,
    output_root: Path,
    market: MarketConfig,
    bars,
    variant: PyramidVariant,
    extra_config: Optional[Dict[str, Any]] = None,
    slippage_ticks: Optional[float] = None,
    state_suffix: str = "",
) -> ReplayResult:
    from .engine import Engine
    from .models import Bar, StrategyInstance, as_row
    from .store import FlatFileStore
    from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills

    strategy_id = "%s_v2b_clean_break_%s%s" % (market.market, variant.name, state_suffix)
    state_root = output_root / "states" / strategy_id
    if state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()

    config = dict(variant.config())
    tick = float(TICK_BY_INSTRUMENT.get(market.instrument, 0.25))
    config.update(
        {
            "market": market.market,
            "record_levels": False,
            "tick_size": tick,
        }
    )
    if extra_config:
        config.update(extra_config)
    DEFAULT_TICK_SIZE[market.instrument] = tick
    max_qty = int(config.get("max_pyramid_qty") or 8)
    slip = DEFAULT_SLIPPAGE_TICKS if slippage_ticks is None else float(slippage_ticks)
    instance = StrategyInstance(
        strategy_id=strategy_id,
        strategy_type="v2b_clean_break",
        version="v1",
        instrument=market.instrument,
        broker_instrument=market.instrument,
        account_mode="paper",
        enabled=True,
        timeframes="5m",
        max_contracts=max_qty,
        max_open_orders=24,
        config_json=json.dumps(config, sort_keys=True),
    )
    store.write_table("strategy_instances", [as_row(instance)])
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        slippage_ticks=slip,
        tick_size={market.instrument: tick},
    )

    audit_bars: List[AuditBar] = []
    _progress("replay %s / %s%s slip=%.1f" % (market.instrument, variant.name, state_suffix, slip))
    sessions = 0
    for _session_day, session_bars in bars.groupby("session_day", sort=True):
        sessions += 1
        for _, row in session_bars.iterrows():
            ts_s = pd.Timestamp(row["ts"]).isoformat()
            bar = Bar(
                instrument=market.instrument,
                timeframe="5m",
                ts=ts_s,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                complete=True,
                source=str(market.bars_path),
            )
            engine.process_bar(bar)
            audit_bars.append(AuditBar(ts_s, bar.open, bar.high, bar.low, bar.close))
        if sessions % 500 == 0:
            _progress("%s/%s: %d sessions" % (market.instrument, variant.name, sessions))

    store.flush_tables()
    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.instrument,
        fee_per_unit=FEE_PER_UNIT,
    )
    return ReplayResult(
        market=market.market,
        instrument=market.instrument,
        variant=variant.name,
        label=variant.label,
        strategy_id=strategy_id,
        state_root=state_root,
        sessions=sessions,
        units=len(units),
        trades=len({u.trade_id for u in units}),
        net_usd=audit["net_usd"],
        closed_dd_usd=audit["closed_dd_usd"],
        intrabar_stress_dd_usd=audit["intrabar_stress_dd_usd"],
        max_open_units=audit["max_open_units"],
        win_rate=audit["win_rate"],
        profit_factor=audit["profit_factor"],
    )


def _rank_variants(summary: pd.DataFrame) -> pd.DataFrame:
    """Per-variant combined net / worst-market stress."""
    rows = []
    for name, g in summary.groupby("variant"):
        total_net = float(g["net_usd"].sum())
        worst_stress = float(g["intrabar_stress_dd_usd"].min()) if len(g) else 0.0
        ns = total_net / abs(worst_stress) if worst_stress else 0.0
        rows.append(
            {
                "variant": name,
                "label": str(g["label"].iloc[0]),
                "combined_net": total_net,
                "worst_stress": worst_stress,
                "combined_ns": ns,
                "trades": int(g["trades"].sum()),
                "units": int(g["units"].sum()),
                "max_open_units": int(g["max_open_units"].max()),
            }
        )
    board = pd.DataFrame(rows).sort_values(["combined_ns", "combined_net"], ascending=False)
    return board.reset_index(drop=True)


def run(
    *,
    email: bool,
    smoke: bool,
    markets: Sequence[str],
    max_sessions: Optional[int],
    variant_names: Optional[Sequence[str]],
    hub: Optional[Path] = None,
    study_id: Optional[str] = None,
    dsr: Optional[str] = None,
) -> None:
    global HUB, STUDY_ID, DSR
    if hub is not None:
        HUB = Path(hub)
        if not HUB.is_absolute():
            HUB = REPO / HUB
    if study_id:
        STUDY_ID = study_id
    if dsr:
        DSR = dsr
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr(markets)
    variants = list(VARIANTS)
    if variant_names:
        want = set(variant_names)
        variants = [v for v in variants if v.name in want]
        if not variants:
            raise SystemExit("No variants matched --variant filter")

    market_label = ",".join(MARKETS[m].instrument for m in markets)
    is_cfd = any(m in CFD_SPECS for m in markets)
    rid = begin_run(
        run_class="broker_like" if len(variants) <= 3 else "sweep",
        variant_slug=STUDY_ID,
        instrument=market_label,
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={
            "n_variants": len(variants),
            "trail_at_frac": 0.6,
            "smoke": smoke,
            "variants": [v.name for v in variants],
            "parent_sweep": "v2b_clean_break_pyramid_trail_sizing_v1",
            "cfd_portability": is_cfd,
        },
    )
    try:
        results: List[ReplayResult] = []
        for name in markets:
            market = MARKETS[name]
            bars = _load_bars(market)
            if max_sessions is not None:
                keep = sorted(bars["session_day"].unique())[:max_sessions]
                bars = bars[bars["session_day"].isin(keep)].copy()
            _progress("%s sessions=%d variants=%d" % (market.instrument, bars["session_day"].nunique(), len(variants)))
            for variant in variants:
                results.append(run_one(output_root=HUB, market=market, bars=bars, variant=variant))

        rows = []
        for r in results:
            rows.append(
                {
                    "market": r.market,
                    "instrument": r.instrument,
                    "variant": r.variant,
                    "label": r.label,
                    "sessions": r.sessions,
                    "trades": r.trades,
                    "units": r.units,
                    "net_usd": r.net_usd,
                    "closed_dd_usd": r.closed_dd_usd,
                    "intrabar_stress_dd_usd": r.intrabar_stress_dd_usd,
                    "max_open_units": r.max_open_units,
                    "win_rate": r.win_rate,
                    "profit_factor": r.profit_factor,
                    "ns": r.net_over_stress,
                }
            )
        summary = pd.DataFrame(rows)
        summary.to_csv(HUB / "summary.csv", index=False)
        board = _rank_variants(summary)
        board.to_csv(HUB / "variant_board.csv", index=False)

        best = board.iloc[0] if len(board) else None
        total_net_best = float(best["combined_net"]) if best is not None else 0.0
        ns_best = float(best["combined_ns"]) if best is not None else 0.0
        best_name = str(best["variant"]) if best is not None else ""

        # Stance vs futures trail top-3 / pyramid v1.
        stance = "research"
        if best is not None and total_net_best > 0 and ns_best >= 1.0:
            stance = (
                "research — best=%s combined N/S=%.2f net=$%+.0f on %s; "
                "compare to NQ+MNQ trail top-3 (best 8.48 N/S) and pyramid v1 (~4.90)"
                % (best_name, ns_best, total_net_best, market_label)
            )
        elif best is not None and total_net_best <= 0:
            stance = "reject / weak on this trail+sizing grid (%s)" % market_label

        focused = variant_names is not None and len(variants) <= 3
        if is_cfd and focused:
            title = "# V2B Clean-Break Pyramid Trail Top-3 CFD Portability"
            status = "STATUS: CFD PORTABILITY (Engine + PaperBroker, 5m RTH index CFDs)"
        elif focused:
            title = "# V2B Clean-Break Pyramid Trail Top-3 Broker-Like Confirm"
            status = "STATUS: TOP-3 CONFIRM (Engine + PaperBroker, 5m RTH)"
        else:
            title = "# V2B Clean-Break Pyramid Trail@60% + Sizing Sweep"
            status = "STATUS: RESEARCH SWEEP (Engine + PaperBroker, 5m RTH)"
        board_hdr = "## Variant board (combined %s, ranked by N/S)" % market_label
        lines = [
            title,
            "",
            status,
            "",
            "## Rules",
            "- Base: bullish v2b clean break (OR 09:30–09:45, stop @ OR high + 2 ticks, clean close).",
            "- Pyramid: +1 on eligible outside 5m candles (low > OR high), max qty per variant.",
            "- Cadence: every 1 / every 2 eligible bars; or **opposing** (bearish close < open) outside bars.",
            "- Trail: when bar high ≥ entry + 0.6×(2R−entry), park stop at **entry (BE)** + rest 2R target.",
            "- Soft exit: 5m close ≤ OR high still flattens; EOD 15:55.",
            "- Control variant: max8 every-1 outside, no trail (pyramid v1 twin).",
        ]
        if is_cfd:
            lines.append("- CFD economics: tick 0.1, $1/pt, fee $1.50/unit (NAS100/US30/SPX500).")
        lines += [
            "",
            board_hdr,
            "",
            "| Rank | Variant | Net | Worst stress | N/S | Trades | Units | MaxU |",
            "|---:|---|---:|---:|---:|---:|---:|---:|",
        ]
        for i, row in board.iterrows():
            lines.append(
                "| %d | %s | $%s | $%s | %.2f | %d | %d | %d |"
                % (
                    i + 1,
                    row["variant"],
                    money(row["combined_net"]),
                    money(row["worst_stress"]),
                    row["combined_ns"],
                    int(row["trades"]),
                    int(row["units"]),
                    int(row["max_open_units"]),
                )
            )

        lines += [
            "",
            "## Per-market detail",
            "",
            "| Market | Variant | Sessions | Trades | Units | Net | Stress DD | MaxU | N/S | Win% | PF |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for r in results:
            pf = "%.2f" % r.profit_factor if math.isfinite(r.profit_factor) else "inf"
            lines.append(
                "| %s | %s | %d | %d | %d | $%s | $%s | %d | %.2f | %.1f%% | %s |"
                % (
                    r.instrument,
                    r.variant,
                    r.sessions,
                    r.trades,
                    r.units,
                    money(r.net_usd),
                    money(r.intrabar_stress_dd_usd),
                    r.max_open_units,
                    r.net_over_stress,
                    r.win_rate,
                    pf,
                )
            )

        lines += [
            "",
            "**Best:** `%s` combined N/S=%.2f net=$%+.0f" % (best_name, ns_best, total_net_best),
            "",
            "**Stance:** %s" % stance,
            "",
            "Hub: `%s`" % HUB,
            "DSR: `%s`" % DSR,
            "smoke=%s" % smoke,
            "",
            "Refs: NQ+MNQ trail top-3 hub `v2b_clean_break_pyramid_trail_top3_v1`; "
            "pyramid v1 `v2b_clean_break_pyramid_outside_v1`; parent sweep `v2b_clean_break_pyramid_trail_sizing_v1`.",
            "",
        ]
        body = "\n".join(lines)
        (HUB / "SUMMARY.md").write_text(body, encoding="utf-8")
        (HUB / "EMAIL.txt").write_text("potions: %s\n\n%s\n" % (STUDY_ID, body), encoding="utf-8")
        (HUB / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study_id": STUDY_ID,
                    "best_variant": best_name,
                    "best_combined_net": total_net_best,
                    "best_combined_ns": ns_best,
                    "stance": stance,
                    "smoke": smoke,
                    "board": board.to_dict(orient="records"),
                    "markets": rows,
                },
                indent=2,
            )
            + "\n"
        )

        complete_run(
            rid,
            net_usd=total_net_best,
            stress_dd_usd=float(best["worst_stress"]) if best is not None else 0.0,
            close_mtm_dd_usd=float(best["worst_stress"]) if best is not None else 0.0,
            ns=ns_best,
            trades=int(summary["trades"].sum()),
            notes=stance,
            meta={"best": best_name, "n_variants": len(variants)},
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(subject="potions: %s complete" % STUDY_ID, body=(HUB / "EMAIL.txt").read_text())
        _progress("DONE best=%s net=$%+.0f N/S=%.2f stance=%s" % (best_name, total_net_best, ns_best, stance))
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-2000:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: %s FAILED" % STUDY_ID, body=err[-4000:])
        raise


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--max-sessions", type=int, default=None)
    ap.add_argument("--market", action="append", choices=MARKET_CHOICES, default=None)
    ap.add_argument("--variant", action="append", default=None, help="Filter to named variant(s)")
    ap.add_argument("--hub", type=Path, default=None, help="Override output hub under live/state/")
    ap.add_argument("--study-id", default=None, help="Override study_id / ledger slug")
    ap.add_argument("--dsr", default=None, help="Override DSR trial id")
    args = ap.parse_args()
    max_sessions = args.max_sessions
    if args.smoke and max_sessions is None:
        max_sessions = 40
    markets = args.market or ["nq", "mnq"]
    run(
        email=bool(args.email),
        smoke=bool(args.smoke),
        markets=markets,
        max_sessions=max_sessions,
        variant_names=args.variant,
        hub=args.hub,
        study_id=args.study_id,
        dsr=args.dsr,
    )


if __name__ == "__main__":
    main()
