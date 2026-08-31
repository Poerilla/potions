from __future__ import annotations

"""Yearly ORB scaleout3 sizing sweep.

Grid sweep of per-unit sizing for the ``yearly_orb_scaleout3`` plugin. Each
row is one ``(tp25_qty, tp_qty, runner_qty)`` combination, replayed through
the same broker-like ``Engine`` + ``PaperBroker`` path used by
``broker_like_replays.py`` so the rows are directly comparable to the live
production leaderboard.

Supports futures (MNQ/NQ/ES/MES/YM/MYM) and FX/metals (AUDJPY/XAUUSD/XAGUSD).

Knobs swept:

- ``tp25_qty``: contracts that exit at 25% of the way to the full TP
- ``tp_qty``: contracts that exit at the full TP (range == OR width)
- ``runner_qty``: contracts that ride to the runner stop / breakeven runner

The Yearly ORB strategy was extended in 2026-05-21 to honour these per-bucket
quantities for both the default ``limit_retest`` entry mode and the
``oco_stop`` entry mode used by the 20% range-close variant. ``batch_qty=1``
is the legacy "1/1/1 scaleout3" baseline.

Realism baseline is inherited from ``broker_like_replays.py`` (1-tick
slippage, stop gap-through, stop-first same-bar ordering, OCO-collapsed risk
projection). FX/metals fees: metals $1.50/unit; AUDJPY ¥7/unit (FX pack).
"""

import argparse
import csv
import json
import shutil
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Set

from .broker_like_replays import DEFAULT_FEE_PER_UNIT, DEFAULT_SLIPPAGE_TICKS
from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore

REPO = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SweepMarket:
    market: str
    instrument: str
    daily_path: Path
    tick: Optional[float] = None
    fee_per_unit: float = DEFAULT_FEE_PER_UNIT
    pnl_ccy: str = "USD"
    usd_fx_approx: Optional[float] = None  # divide native PnL by this for ~USD


FUTURES_MARKETS: List[SweepMarket] = [
    SweepMarket("mnq", "MNQ", REPO / "mnq" / "mnq_daily.csv"),
    SweepMarket("nq", "NQ", REPO / "nq" / "nq_daily.csv"),
    SweepMarket("es", "ES", REPO / "es" / "es_daily.csv"),
    SweepMarket("mes", "MES", REPO / "mes" / "mes_daily.csv"),
    SweepMarket("ym", "YM", REPO / "ym" / "ym_daily.csv"),
    SweepMarket("mym", "MYM", REPO / "mym" / "mym_daily.csv"),
]

# Same banked FX/metals yearly ORB sleeves as fx_metals_top4 / demo yearly_orb_common.
# NAS100 is the OANDA CFD proxy for NQ yearly ORB research (not a banked sleeve yet).
FX_METALS_MARKETS: List[SweepMarket] = [
    SweepMarket(
        "audjpy",
        "AUDJPY",
        REPO / "fx" / "audjpy_daily.csv",
        tick=0.001,
        fee_per_unit=7.0,
        pnl_ccy="JPY",
        usd_fx_approx=110.0,
    ),
    SweepMarket(
        "xauusd",
        "XAUUSD",
        REPO / "fx" / "xauusd_daily.csv",
        tick=0.01,
        fee_per_unit=1.50,
    ),
    SweepMarket(
        "xagusd",
        "XAGUSD",
        REPO / "fx" / "xagusd_daily.csv",
        tick=0.001,
        fee_per_unit=1.50,
    ),
    SweepMarket(
        "nas100",
        "NAS100",
        REPO / "fx" / "nas100_daily.csv",
        tick=0.1,
        fee_per_unit=1.50,
    ),
]

ALL_MARKETS: List[SweepMarket] = FUTURES_MARKETS + FX_METALS_MARKETS


@dataclass(frozen=True)
class YearlyOrbSizingScenario:
    slug: str
    label: str
    tp25_qty: int
    tp_qty: int
    runner_qty: int
    entry_mode: str = "limit_retest"  # "limit_retest" | "oco_stop"
    range_close_inside_frac: Optional[float] = None
    exit_mode: str = "range_close"  # range_close | mid_close | inside_swing_take
    allow_weeks_of_month: tuple = ()
    notes: str = ""

    @property
    def total_qty(self) -> int:
        return int(self.tp25_qty) + int(self.tp_qty) + int(self.runner_qty)

    def to_config(self) -> Dict[str, object]:
        cfg: Dict[str, object] = {
            "or_start_month": 1,
            "or_end_month": 3,
            "trade_start_month": 4,
            "trade_end_month": 12,
            "batch_qty": 1,
            "tp25_qty": int(self.tp25_qty),
            "tp_qty": int(self.tp_qty),
            "runner_qty": int(self.runner_qty),
            "tp25_frac": 0.25,
            "tp_full_mult": 1.0,
            "require_fresh_break": True,
            "entry_mode": self.entry_mode,
            "exit_mode": self.exit_mode,
        }
        if self.range_close_inside_frac is not None:
            cfg["range_close_inside_frac"] = float(self.range_close_inside_frac)
        if self.exit_mode == "mid_close" and self.range_close_inside_frac is None:
            cfg["range_close_inside_frac"] = 0.5
        if self.allow_weeks_of_month:
            cfg["allow_weeks_of_month"] = [int(w) for w in self.allow_weeks_of_month]
        return cfg


def _with_exit(
    base: YearlyOrbSizingScenario,
    *,
    exit_mode: str,
    slug_suffix: str,
    label_suffix: str,
    notes: str,
    range_close_inside_frac: Optional[float] = None,
) -> YearlyOrbSizingScenario:
    return YearlyOrbSizingScenario(
        slug="%s_%s" % (base.slug, slug_suffix),
        label="%s + %s" % (base.label, label_suffix),
        tp25_qty=base.tp25_qty,
        tp_qty=base.tp_qty,
        runner_qty=base.runner_qty,
        entry_mode=base.entry_mode,
        range_close_inside_frac=range_close_inside_frac,
        exit_mode=exit_mode,
        allow_weeks_of_month=base.allow_weeks_of_month,
        notes=notes,
    )


# Core limit_retest sizings used for exit-variant sweeps (skip OCO/rc20 clones).
_SIZING_CORE_SLUGS = {
    "L_1_1_1",
    "L_2_1_1",
    "L_2_2_2",
    "L_3_2_1",
    "L_3_3_3",
    "L_4_1_1",
    "L_4_2_1",
    "L_4_2_2",
    "L_5_2_1",
    "L_1_1_3",
    "L_1_2_4",
    "L_2_2_4",
    "L_2_4_1",
    "L_1_3_3",
    "L_3_1_3",
}

# A grid of per-unit sizings (tp25 / tp / runner). Total = sum of three.
# Naming convention: "L_4_2_1" = limit_retest, 4 scale-out / 2 TP / 1 runner.
# Range-close 20% variants are flagged with "_rc20".
DEFAULT_SCENARIOS: List[YearlyOrbSizingScenario] = [
    # --- Baselines: 1/1/1 limit_retest matches the current production row ---
    YearlyOrbSizingScenario(
        slug="L_1_1_1",
        label="limit_retest 1/1/1 (baseline)",
        tp25_qty=1,
        tp_qty=1,
        runner_qty=1,
        notes="Existing production yearly ORB scaleout3 row.",
    ),
    YearlyOrbSizingScenario(
        slug="L_1_1_1_rc20",
        label="limit_retest 1/1/1 + 20% range-close",
        tp25_qty=1,
        tp_qty=1,
        runner_qty=1,
        range_close_inside_frac=0.20,
        notes="Baseline plus the 20% range-close exit.",
    ),
    YearlyOrbSizingScenario(
        slug="O_1_1_1_rc20",
        label="oco_stop 1/1/1 + 20% range-close",
        tp25_qty=1,
        tp_qty=1,
        runner_qty=1,
        entry_mode="oco_stop",
        range_close_inside_frac=0.20,
        notes="Current OCO+20% production row.",
    ),
    # --- User's requested 4/2/1 family ---
    YearlyOrbSizingScenario(
        slug="L_4_2_1",
        label="limit_retest 4/2/1",
        tp25_qty=4,
        tp_qty=2,
        runner_qty=1,
        notes="User's pick: front-load 4 scale-out, 2 at TP, 1 runner.",
    ),
    YearlyOrbSizingScenario(
        slug="L_4_2_1_rc20",
        label="limit_retest 4/2/1 + 20% range-close",
        tp25_qty=4,
        tp_qty=2,
        runner_qty=1,
        range_close_inside_frac=0.20,
        notes="User's pick with 20% range-close.",
    ),
    YearlyOrbSizingScenario(
        slug="O_4_2_1_rc20",
        label="oco_stop 4/2/1 + 20% range-close",
        tp25_qty=4,
        tp_qty=2,
        runner_qty=1,
        entry_mode="oco_stop",
        range_close_inside_frac=0.20,
        notes="User's pick as OCO stop entry.",
    ),
    # --- Symmetric scales ---
    YearlyOrbSizingScenario(
        slug="L_2_2_2",
        label="limit_retest 2/2/2",
        tp25_qty=2,
        tp_qty=2,
        runner_qty=2,
        notes="Doubled baseline; 6 total contracts.",
    ),
    YearlyOrbSizingScenario(
        slug="L_3_3_3",
        label="limit_retest 3/3/3",
        tp25_qty=3,
        tp_qty=3,
        runner_qty=3,
        notes="Tripled baseline; 9 total contracts.",
    ),
    # --- Front-loaded variants (heavier scale-out) ---
    YearlyOrbSizingScenario(
        slug="L_2_1_1",
        label="limit_retest 2/1/1",
        tp25_qty=2,
        tp_qty=1,
        runner_qty=1,
        notes="Mildly front-loaded.",
    ),
    YearlyOrbSizingScenario(
        slug="L_3_2_1",
        label="limit_retest 3/2/1",
        tp25_qty=3,
        tp_qty=2,
        runner_qty=1,
        notes="Steeper front-load than user's pick.",
    ),
    YearlyOrbSizingScenario(
        slug="L_5_2_1",
        label="limit_retest 5/2/1",
        tp25_qty=5,
        tp_qty=2,
        runner_qty=1,
        notes="Extreme front-loading.",
    ),
    YearlyOrbSizingScenario(
        slug="L_4_1_1",
        label="limit_retest 4/1/1",
        tp25_qty=4,
        tp_qty=1,
        runner_qty=1,
        notes="Heavy quick exit, light TP and runner.",
    ),
    # --- Back-loaded (bigger runner) ---
    YearlyOrbSizingScenario(
        slug="L_1_1_3",
        label="limit_retest 1/1/3",
        tp25_qty=1,
        tp_qty=1,
        runner_qty=3,
        notes="Modest scaleouts, larger runner for trend.",
    ),
    YearlyOrbSizingScenario(
        slug="L_1_2_4",
        label="limit_retest 1/2/4",
        tp25_qty=1,
        tp_qty=2,
        runner_qty=4,
        notes="Back-loaded; big runner.",
    ),
    YearlyOrbSizingScenario(
        slug="L_2_2_4",
        label="limit_retest 2/2/4",
        tp25_qty=2,
        tp_qty=2,
        runner_qty=4,
        notes="Balanced with extra runner weight.",
    ),
    # --- TP-heavy ---
    YearlyOrbSizingScenario(
        slug="L_2_4_1",
        label="limit_retest 2/4/1",
        tp25_qty=2,
        tp_qty=4,
        runner_qty=1,
        notes="Heavy on full-TP exit.",
    ),
    YearlyOrbSizingScenario(
        slug="L_1_3_3",
        label="limit_retest 1/3/3",
        tp25_qty=1,
        tp_qty=3,
        runner_qty=3,
        notes="TP-heavy with sizable runner.",
    ),
    # --- Asymmetric front + runner ---
    YearlyOrbSizingScenario(
        slug="L_4_2_2",
        label="limit_retest 4/2/2",
        tp25_qty=4,
        tp_qty=2,
        runner_qty=2,
        notes="User's pick with bigger runner.",
    ),
    YearlyOrbSizingScenario(
        slug="L_3_1_3",
        label="limit_retest 3/1/3",
        tp25_qty=3,
        tp_qty=1,
        runner_qty=3,
        notes="Front and runner heavy; thin middle.",
    ),
]


L411_WOM2_SCENARIOS: List[YearlyOrbSizingScenario] = [
    YearlyOrbSizingScenario(
        slug="L_4_1_1",
        label="limit_retest 4/1/1",
        tp25_qty=4,
        tp_qty=1,
        runner_qty=1,
        notes="Baseline L_4_1_1 (all weeks).",
    ),
    YearlyOrbSizingScenario(
        slug="L_4_1_1_wom2",
        label="limit_retest 4/1/1 WoM2",
        tp25_qty=4,
        tp_qty=1,
        runner_qty=1,
        allow_weeks_of_month=(2,),
        notes="Plugin gate allow_weeks_of_month=[2]; cancels resting entries outside week 2.",
    ),
]


def _core_sizing_scenarios() -> List[YearlyOrbSizingScenario]:
    return [s for s in DEFAULT_SCENARIOS if s.slug in _SIZING_CORE_SLUGS and s.entry_mode == "limit_retest"]


# Baseline compare: default range-close vs mid-close vs inside-swing-take at 1/1/1 and 4/2/1.
EXIT_VARIANT_BASELINE_SCENARIOS: List[YearlyOrbSizingScenario] = []
for _base_slug in ("L_1_1_1", "L_4_2_1"):
    _base = next(s for s in DEFAULT_SCENARIOS if s.slug == _base_slug)
    EXIT_VARIANT_BASELINE_SCENARIOS.append(_base)
    EXIT_VARIANT_BASELINE_SCENARIOS.append(
        _with_exit(
            _base,
            exit_mode="mid_close",
            slug_suffix="mid",
            label_suffix="mid-close",
            notes="Close exit only when close crosses YOR midpoint (long ≤ mid / short ≥ mid).",
            range_close_inside_frac=0.5,
        )
    )
    EXIT_VARIANT_BASELINE_SCENARIOS.append(
        _with_exit(
            _base,
            exit_mode="inside_swing_take",
            slug_suffix="swing",
            label_suffix="inside-swing-take",
            notes="No range/mid market flatten; SL trails to latest inside-range swing; exit when swing taken.",
        )
    )

# Full sizing grids for each new exit mode (core L_* cells).
MID_CLOSE_SIZING_SCENARIOS: List[YearlyOrbSizingScenario] = [
    _with_exit(
        s,
        exit_mode="mid_close",
        slug_suffix="mid",
        label_suffix="mid-close",
        notes="Sizing sweep with YOR midpoint close exit.",
        range_close_inside_frac=0.5,
    )
    for s in _core_sizing_scenarios()
]

SWING_EXIT_SIZING_SCENARIOS: List[YearlyOrbSizingScenario] = [
    _with_exit(
        s,
        exit_mode="inside_swing_take",
        slug_suffix="swing",
        label_suffix="inside-swing-take",
        notes="Sizing sweep with inside-swing-take stop trail exit.",
    )
    for s in _core_sizing_scenarios()
]

# Combined research pack: baselines + both sizing grids (dedupe by slug).
EXIT_VARIANT_PACK_SCENARIOS: List[YearlyOrbSizingScenario] = []
_seen_slugs: Set[str] = set()
for _s in EXIT_VARIANT_BASELINE_SCENARIOS + MID_CLOSE_SIZING_SCENARIOS + SWING_EXIT_SIZING_SCENARIOS:
    if _s.slug in _seen_slugs:
        continue
    _seen_slugs.add(_s.slug)
    EXIT_VARIANT_PACK_SCENARIOS.append(_s)


def _mid(tp25: int, tp: int, runner: int, *, notes: str = "") -> YearlyOrbSizingScenario:
    slug = "L_%d_%d_%d_mid" % (tp25, tp, runner)
    return YearlyOrbSizingScenario(
        slug=slug,
        label="limit_retest %d/%d/%d + mid-close" % (tp25, tp, runner),
        tp25_qty=tp25,
        tp_qty=tp,
        runner_qty=runner,
        exit_mode="mid_close",
        range_close_inside_frac=0.5,
        notes=notes or "XAU mid attribution: favor TP/runner weight.",
    )


def _range(tp25: int, tp: int, runner: int, *, notes: str = "") -> YearlyOrbSizingScenario:
    slug = "L_%d_%d_%d" % (tp25, tp, runner)
    return YearlyOrbSizingScenario(
        slug=slug,
        label="limit_retest %d/%d/%d" % (tp25, tp, runner),
        tp25_qty=tp25,
        tp_qty=tp,
        runner_qty=runner,
        exit_mode="range_close",
        notes=notes or "XAG range attribution: refine front-load around 4/2/1.",
    )


# Attribution-shaped: XAUUSD mid_close — TP/runner heavy + light front-load controls.
XAU_MID_TPRUNNER_SCENARIOS: List[YearlyOrbSizingScenario] = [
    _mid(1, 1, 1, notes="Baseline mid 1/1/1."),
    _mid(1, 1, 3),
    _mid(1, 2, 4),
    _mid(1, 3, 3),
    _mid(1, 4, 4),
    _mid(1, 3, 5),
    _mid(2, 2, 4),
    _mid(2, 3, 3),
    _mid(2, 4, 4),
    _mid(1, 5, 3),
    _mid(0, 3, 3, notes="No tp25; pure TP+runner mid."),
    _mid(0, 2, 4, notes="No tp25; TP/runner mid."),
    _mid(1, 1, 5),
    _mid(2, 1, 1, notes="Front-load control (expect weaker N/S)."),
    _mid(4, 2, 1, notes="Front-load control vs prior pack."),
    _mid(3, 3, 3, notes="Symmetric scale control."),
]

# Attribution-shaped: XAGUSD range_close — front-load refine around 4/2/1.
XAG_RANGE_FRONTLOAD_SCENARIOS: List[YearlyOrbSizingScenario] = [
    _range(1, 1, 1, notes="Baseline range 1/1/1."),
    _range(2, 1, 1),
    _range(3, 1, 1),
    _range(3, 2, 1),
    _range(4, 1, 1),
    _range(4, 2, 1, notes="Prior pack XAG N/S leader."),
    _range(4, 2, 2),
    _range(4, 3, 1),
    _range(5, 1, 1),
    _range(5, 2, 1),
    _range(5, 2, 2),
    _range(6, 2, 1),
    _range(6, 1, 1),
    _range(3, 3, 1),
    _range(2, 2, 1),
    _range(1, 2, 4, notes="Back-load control (expect weaker N/S on silver range)."),
    _range(1, 3, 3, notes="TP/runner control."),
]

SCENARIO_SETS: Dict[str, List[YearlyOrbSizingScenario]] = {
    "default": DEFAULT_SCENARIOS,
    "exit_baseline": EXIT_VARIANT_BASELINE_SCENARIOS,
    "mid_close": MID_CLOSE_SIZING_SCENARIOS,
    "swing_exit": SWING_EXIT_SIZING_SCENARIOS,
    "exit_pack": EXIT_VARIANT_PACK_SCENARIOS,
    "xau_mid_tprunner": XAU_MID_TPRUNNER_SCENARIOS,
    "xag_range_frontload": XAG_RANGE_FRONTLOAD_SCENARIOS,
    "l411_wom2": L411_WOM2_SCENARIOS,
}


@dataclass(frozen=True)
class SweepResult:
    market: str
    instrument: str
    scenario: YearlyOrbSizingScenario
    units: int
    trades: int
    net_native: float
    closed_dd_native: float
    intrabar_stress_dd_native: float
    max_open_units: int
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


def _progress(output_root: Path, msg: str) -> None:
    print(msg, flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg + "\n")


def run_sweep(
    *,
    output_root: Path,
    market_names: Sequence[str],
    scenarios: Sequence[YearlyOrbSizingScenario] = DEFAULT_SCENARIOS,
    slippage_ticks: float = DEFAULT_SLIPPAGE_TICKS,
    fee_per_unit: Optional[float] = None,
    force: bool = True,
) -> List[SweepResult]:
    output_root.mkdir(parents=True, exist_ok=True)
    states_root = output_root / "states"
    audits_root = output_root / "audits"
    states_root.mkdir(parents=True, exist_ok=True)
    audits_root.mkdir(parents=True, exist_ok=True)

    wanted = {x.lower() for x in market_names}
    selected = [m for m in ALL_MARKETS if m.market in wanted]
    if not selected:
        raise ValueError(f"No matching markets in ALL_MARKETS for: {market_names!r}")

    results: List[SweepResult] = []
    for market in selected:
        if not market.daily_path.exists() or market.instrument not in POINT_VALUES:
            _progress(
                output_root,
                f"Skipping {market.instrument}, missing daily bars: {market.daily_path}",
            )
            continue
        fee = float(fee_per_unit) if fee_per_unit is not None else float(market.fee_per_unit)
        bars = bars_from_csv(market.daily_path, market.instrument, "D", source=str(market.daily_path))
        if not bars:
            continue
        tick_kw = {"tick_size": {market.instrument: market.tick}} if market.tick is not None else {}
        for scenario in scenarios:
            slug = f"{market.market}_yorb_sizing_{scenario.slug}"
            state_root = states_root / slug
            if force and state_root.exists():
                shutil.rmtree(state_root)
            state = FlatFileStore(state_root, defer_table_writes=True)
            state.ensure()
            instance = StrategyInstance(
                strategy_id=slug,
                strategy_type="yearly_orb_scaleout3",
                version="v1",
                instrument=market.instrument,
                broker_instrument=market.instrument,
                account_mode="paper",
                enabled=True,
                timeframes="D",
                # Max contracts must accommodate the full ladder. Risk projection
                # is collapsed-by-OCO-group, so a 4/2/1 = 7 ladder needs at least 7.
                max_contracts=max(scenario.total_qty, 1),
                max_open_orders=64,
                config_json=json.dumps(scenario.to_config(), sort_keys=True),
            )
            state.upsert_row("strategy_instances", "strategy_id", as_row(instance))
            Engine(store=state, slippage_ticks=slippage_ticks, **tick_kw).replay_bars(bars)
            state.flush_tables()
            generate_market_close_report(state, bars[-1].ts[:10])
            replay_bars = read_bars(state_root / "bars" / f"{market.instrument}_D.csv", "ts")
            units = units_from_live_fills(
                state_root / "fills.csv",
                slug,
                replay_bars[-1].ts,
                replay_bars[-1].close,
            )
            note = (
                f"{scenario.notes} "
                f"Realism: slippage={slippage_ticks:g} tick, fee={fee:.2f}/{market.pnl_ccy}/unit. "
                f"Per-unit sizing tp25/tp/runner = {scenario.tp25_qty}/{scenario.tp_qty}/{scenario.runner_qty}."
            ).strip()
            audit = audit_units(
                name=f"{market.instrument} Yearly ORB {scenario.label}",
                slug=slug,
                source=state_root / "fills.csv",
                bar_source=state_root / "bars" / f"{market.instrument}_D.csv",
                bars=replay_bars,
                units=units,
                instrument=market.instrument,
                notes=note,
                output_root=audits_root,
                fee_per_unit=fee,
            )
            res = SweepResult(
                market=market.market,
                instrument=market.instrument,
                scenario=scenario,
                units=audit.units,
                trades=audit.trades,
                net_native=audit.net_usd,
                closed_dd_native=audit.close_mtm_dd_usd,
                intrabar_stress_dd_native=audit.intrabar_mtm_dd_usd,
                max_open_units=audit.max_open_units,
                pnl_ccy=market.pnl_ccy,
                usd_fx_approx=market.usd_fx_approx,
            )
            results.append(res)
            ccy = market.pnl_ccy
            usd_note = ""
            if market.pnl_ccy != "USD" and market.usd_fx_approx:
                usd_note = f" (~${res.net_usd_approx:,.0f} / ${res.stress_usd_approx:,.0f} @{market.usd_fx_approx:g})"
            _progress(
                output_root,
                f"{market.instrument:>6} {scenario.slug:<22} "
                f"({scenario.tp25_qty}/{scenario.tp_qty}/{scenario.runner_qty} tot={scenario.total_qty}, "
                f"{scenario.entry_mode:<12} exit={scenario.exit_mode:<18} "
                f"rc={scenario.range_close_inside_frac}) "
                f"net={ccy} {res.net_native:>12,.2f} stress={res.intrabar_stress_dd_native:>11,.2f} "
                f"ratio={res.net_over_stress:.2f}{usd_note}",
            )

    _write_summary(output_root, results, slippage_ticks)
    return results


def _fmt_money(value: float, ccy: str) -> str:
    if ccy == "JPY":
        return f"¥{value:,.0f}"
    return f"${value:,.2f}"


def _write_summary(
    output_root: Path,
    results: List[SweepResult],
    slippage_ticks: float,
) -> None:
    rows = []
    ranked = sorted(results, key=lambda r: r.net_over_stress, reverse=True)
    for rank, r in enumerate(ranked, start=1):
        s = r.scenario
        rows.append(
            {
                "rank": str(rank),
                "market": r.market,
                "instrument": r.instrument,
                "slug": s.slug,
                "label": s.label,
                "entry_mode": s.entry_mode,
                "exit_mode": s.exit_mode,
                "range_close_inside_frac": ""
                if s.range_close_inside_frac is None
                else f"{s.range_close_inside_frac:.2f}",
                "tp25_qty": str(s.tp25_qty),
                "tp_qty": str(s.tp_qty),
                "runner_qty": str(s.runner_qty),
                "total_qty": str(s.total_qty),
                "units": str(r.units),
                "trades": str(r.trades),
                "pnl_ccy": r.pnl_ccy,
                "net_native": "%.2f" % r.net_native,
                "closed_dd_native": "%.2f" % r.closed_dd_native,
                "intrabar_stress_dd_native": "%.2f" % r.intrabar_stress_dd_native,
                "net_usd_approx": "%.2f" % r.net_usd_approx,
                "stress_usd_approx": "%.2f" % r.stress_usd_approx,
                # Compat with prior futures CSV column names.
                "net_usd": "%.2f" % r.net_usd_approx,
                "closed_dd_usd": "%.2f"
                % (
                    r.closed_dd_native
                    if r.pnl_ccy == "USD" or not r.usd_fx_approx
                    else r.closed_dd_native / float(r.usd_fx_approx)
                ),
                "intrabar_stress_dd_usd": "%.2f" % r.stress_usd_approx,
                "max_open_units": str(r.max_open_units),
                "net_over_stress_dd": "%.2f" % r.net_over_stress,
                "notes": s.notes,
            }
        )
    _write_csv(output_root / "summary.csv", rows)

    lines = [
        "# Yearly ORB Scaleout3 Sizing Sweep",
        "",
        "Each row is one per-unit sizing combination (`tp25_qty / tp_qty / runner_qty`) for ",
        "`yearly_orb_scaleout3` driven through the same broker-like `Engine` + `PaperBroker` ",
        "path used by `broker_like_replays.py`.",
        "",
        f"Realism baseline: `slippage_ticks={slippage_ticks:g}`, per-market fees ",
        "(futures/metals $1.50; AUDJPY ¥7), stop gap-through ON, stop-first same-bar, ",
        "OCO-collapsed risk projection.",
        "",
        "Causal market exits: range-close / mid-close / year-change flatten with ",
        "`live_after_ts=decision_bar.ts` so fills occur on the **next daily open**, ",
        "not the same completed bar's open (lookahead fix). ",
        "`inside_swing_take` disables range/mid market flatten and trails the ",
        "protective stop to the latest confirmed inside-range swing.",
        "",
        "Ranking is by `Net / Stress DD` (currency-invariant). AUDJPY ~USD uses ÷110.",
        "",
        "| Rank | Market | Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Units | Trades | Net | Stress DD | Net / Stress |",
        "|---:|---|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for rank, r in enumerate(ranked, start=1):
        s = r.scenario
        rc = "—" if s.range_close_inside_frac is None else f"{int(s.range_close_inside_frac * 100)}%"
        if r.pnl_ccy == "JPY":
            net_s = f"¥{r.net_native:,.0f} (~${r.net_usd_approx:,.0f})"
            st_s = f"¥{r.intrabar_stress_dd_native:,.0f} (~${r.stress_usd_approx:,.0f})"
        else:
            net_s = f"${r.net_native:,.2f}"
            st_s = f"${r.intrabar_stress_dd_native:,.2f}"
        lines.append(
            f"| {rank} | {r.instrument} | {s.label} | {s.tp25_qty} | {s.tp_qty} | {s.runner_qty} | "
            f"{s.total_qty} | {s.entry_mode} | {s.exit_mode} | {rc} | {r.units} | {r.trades} | "
            f"{net_s} | {st_s} | {r.net_over_stress:.2f} |"
        )

    lines.append("")
    lines.append("## Per-Market Ranking")
    by_market: Dict[str, List[SweepResult]] = {}
    for r in results:
        by_market.setdefault(r.instrument, []).append(r)
    for inst in sorted(by_market):
        rows_m = sorted(by_market[inst], key=lambda r: r.net_over_stress, reverse=True)
        lines.append("")
        lines.append(f"### {inst}")
        lines.append("")
        lines.append("| Sizing | TP25 | TP | Runner | Total | Entry | Exit | RC | Net | Stress DD | Net / Stress |")
        lines.append("|---|---:|---:|---:|---:|---|---|---|---:|---:|---:|")
        for r in rows_m:
            s = r.scenario
            rc = "—" if s.range_close_inside_frac is None else f"{int(s.range_close_inside_frac * 100)}%"
            lines.append(
                f"| {s.label} | {s.tp25_qty} | {s.tp_qty} | {s.runner_qty} | {s.total_qty} | "
                f"{s.entry_mode} | {s.exit_mode} | {rc} | {_fmt_money(r.net_native, r.pnl_ccy)} | "
                f"{_fmt_money(r.intrabar_stress_dd_native, r.pnl_ccy)} | "
                f"{r.net_over_stress:.2f} |"
            )

    lines.append("")
    lines.append("## Best sizing per market")
    lines.append("")
    lines.append("| Market | Best | TP25/TP/R | Net | Stress | N/S | vs baseline 1/1/1 |")
    lines.append("|---|---|---:|---:|---:|---:|---|")
    for inst in sorted(by_market):
        rows_m = sorted(by_market[inst], key=lambda r: r.net_over_stress, reverse=True)
        best = rows_m[0]
        base = next((x for x in rows_m if x.scenario.slug == "L_1_1_1"), None)
        delta = ""
        if base is not None:
            delta = f"{best.net_over_stress - base.net_over_stress:+.2f} N/S"
        s = best.scenario
        lines.append(
            f"| {inst} | {s.label} | {s.tp25_qty}/{s.tp_qty}/{s.runner_qty} | "
            f"{_fmt_money(best.net_native, best.pnl_ccy)} | "
            f"{_fmt_money(best.intrabar_stress_dd_native, best.pnl_ccy)} | "
            f"{best.net_over_stress:.2f} | {delta} |"
        )

    lines.append("")
    lines.append("## Files")
    lines.append("")
    lines.append("- [`summary.csv`](summary.csv) — same data, CSV.")
    lines.append("- `audits/<slug>/MTM_AUDIT.md` — per-row audit and equity curve.")
    lines.append("- `states/<slug>/` — broker state, fills, orders, and report for each row.")

    (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _write_email(output_root: Path, results: List[SweepResult], *, scenario_set: str) -> Path:
    by_market: Dict[str, List[SweepResult]] = {}
    for r in results:
        by_market.setdefault(r.instrument, []).append(r)
    lines = [
        "potions: FX metals yearly ORB exit-variant sizing sweep complete",
        "",
        f"Hub: {output_root.relative_to(REPO) if output_root.is_absolute() else output_root}",
        f"Scenario set: {scenario_set} ({len(results)} result rows across "
        f"{', '.join(sorted(by_market))})",
        "Exit modes:",
        "- range_close: flatten when close back inside YOR (causal next-bar open)",
        "- mid_close: long flatten when close ≤ YOR mid; short when close ≥ mid",
        "- inside_swing_take: no range/mid flatten; SL trails to latest inside-range swing",
        "Rank by Net/Stress. AUDJPY ~USD @110.",
        "",
        "Best per market:",
        "",
    ]
    for inst in sorted(by_market):
        rows_m = sorted(by_market[inst], key=lambda r: r.net_over_stress, reverse=True)
        best = rows_m[0]
        base = next(
            (x for x in rows_m if x.scenario.slug in {"L_1_1_1", "L_1_1_1_mid", "L_1_1_1_swing"}),
            None,
        )
        # Prefer plain causal L_1_1_1 when present for delta.
        plain = next((x for x in rows_m if x.scenario.slug == "L_1_1_1"), base)
        s = best.scenario
        lines.append(
            f"{inst}: {s.label} ({s.tp25_qty}/{s.tp_qty}/{s.runner_qty} exit={s.exit_mode}) "
            f"N/S={best.net_over_stress:.2f} "
            f"net={_fmt_money(best.net_native, best.pnl_ccy)} "
            f"stress={_fmt_money(best.intrabar_stress_dd_native, best.pnl_ccy)}"
        )
        if plain is not None and plain.scenario.slug != s.slug:
            lines.append(
                f"  vs {plain.scenario.slug} N/S={plain.net_over_stress:.2f} "
                f"(Δ {best.net_over_stress - plain.net_over_stress:+.2f})"
            )
        # Baseline exit compare at 1/1/1 when all three present.
        trio = {
            x.scenario.exit_mode: x
            for x in rows_m
            if x.scenario.slug.startswith("L_1_1_1") and x.scenario.tp25_qty == 1
        }
        if len(trio) >= 2:
            bits = [
                f"{mode}={trio[mode].net_over_stress:.2f}"
                for mode in ("range_close", "mid_close", "inside_swing_take")
                if mode in trio
            ]
            if bits:
                lines.append("  L_1_1_1 exit compare N/S: " + ", ".join(bits))
    lines.append("")
    lines.append(
        "Stance: research / not promotion-safe until PnL attribution + causal audits "
        "on leaders. Prefer N/S over max-net; check swing vs mid vs range close sources."
    )
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run a Yearly ORB scaleout3 sizing sweep.")
    parser.add_argument(
        "--output-root",
        type=Path,
        default=REPO / "live" / "state" / "yearly_orb_sizing_sweep",
    )
    parser.add_argument(
        "--markets",
        type=str,
        default="mnq,nq",
        help="Comma-separated markets (mnq,nq,es,mes,ym,mym,audjpy,xauusd,xagusd,nas100).",
    )
    parser.add_argument(
        "--slippage-ticks",
        type=float,
        default=DEFAULT_SLIPPAGE_TICKS,
    )
    parser.add_argument(
        "--fee-per-unit",
        type=float,
        default=None,
        help="Override per-market fee (default: $1.50 futures/metals, ¥7 AUDJPY).",
    )
    parser.add_argument("--no-force", action="store_true")
    parser.add_argument(
        "--scenario-set",
        type=str,
        default="default",
        choices=sorted(SCENARIO_SETS.keys()),
        help="Scenario pack: default | exit_baseline | mid_close | swing_exit | exit_pack | "
        "xau_mid_tprunner | xag_range_frontload | l411_wom2",
    )
    parser.add_argument("--email", action="store_true", help="Send Resend summary on complete/fail.")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    output_root = args.output_root
    if not output_root.is_absolute():
        output_root = (Path.cwd() / output_root).resolve()
    scenarios = SCENARIO_SETS[str(args.scenario_set)]
    try:
        _progress(
            output_root,
            f"START markets={markets} scenario_set={args.scenario_set} cells={len(scenarios)}",
        )
        results = run_sweep(
            output_root=output_root,
            market_names=markets,
            scenarios=scenarios,
            slippage_ticks=args.slippage_ticks,
            fee_per_unit=args.fee_per_unit,
            force=not args.no_force,
        )
        write_run_manifest(
            output_root,
            data_inputs=[m.daily_path for m in ALL_MARKETS if m.market in set(markets)],
            extra={
                "job": "yearly_orb_sizing_sweep",
                "markets": markets,
                "scenario_set": args.scenario_set,
                "n_results": len(results),
                "n_cells": len(scenarios),
            },
        )
        email_path = _write_email(output_root, results, scenario_set=str(args.scenario_set))
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "n": len(results),
                    "scenario_set": args.scenario_set,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _progress(output_root, f"Wrote {output_root}/SUMMARY.md with {len(results)} rows")
        if args.email:
            send_email(
                subject="potions: yearly ORB sizing sweep (%s) complete — %s"
                % (args.scenario_set, ",".join(markets)),
                body=email_path.read_text(encoding="utf-8"),
            )
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(output_root, "FAILED\n" + tb)
        if args.email:
            send_email(
                subject="potions: yearly ORB sizing sweep FAILED",
                body=f"Hub: {output_root}\nscenario_set={args.scenario_set}\n\n{tb}",
            )
        raise


if __name__ == "__main__":
    raise SystemExit(main())
