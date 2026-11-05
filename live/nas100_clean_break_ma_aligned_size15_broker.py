"""Broker-like Engine validation: NAS100 clean-break ma_aligned HP size-up.

Takes the frozen OANDA / Index Momentum trail06_m4_e2_out_be **Engine+PaperBroker
1m-fill** unit tape and applies HP size-up on campaigns where 5m MA vs trade
is ``ma_aligned``.

**Default contract (causal / no qty refresh):** size from MA **arm-asof**
(``live_after_ts`` of the resting entry stop). Fill-asof (campaign tape) is
optional via ``--fill-asof`` for research contrast only.

Default multiplier ×1.5; ``--scales`` also runs 2× / 4× / 6× on the same
arm-asof HP set to measure whether MTM (intrabar) DD scales with size.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nas100_clean_break_ma_aligned_size15_broker --email
  python -m live.nas100_clean_break_ma_aligned_size15_broker --email --scales 1.5,2,4,6
  python -m live.nas100_clean_break_ma_aligned_size15_broker --email --smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import traceback
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .fx_v2b_london_ungated import REPO
from .intraday_condition_profile import build_feature_frames
from .nas100_clean_break_best_1mfill_quote_validation import load_nas100_1m
from .notify_email import send_email
from .replay_audit import POINT_VALUES, Unit
from .replay_manifest import write_run_manifest
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_clean_break_pyramid_trail_sizing_v1 import FEE_PER_UNIT
from .v2b_strategy_replay import AuditBar, money, units_from_v2b_fills

HUB = REPO / "live" / "state" / "nas100_clean_break_ma_aligned_size15_broker"
SOURCE_HUB = (
    REPO
    / "live"
    / "state"
    / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation"
)
SOURCE_STATE = (
    SOURCE_HUB / "states" / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill"
)
SOURCE_FILLS = SOURCE_STATE / "fills.csv"
SOURCE_ORDERS = SOURCE_STATE / "orders.csv"
CAMPAIGNS = (
    REPO
    / "live"
    / "state"
    / "nas100_clean_break_ha_conditions"
    / "profile"
    / "all_campaigns.csv"
)
STRATEGY_ID = "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill"
INSTRUMENT = "NAS100"
POINT_VALUE = 1.0
HP_MULT = 1.5
DEFAULT_SCALES = (1.5, 2.0, 4.0, 6.0)
DSR = "TRL-2026-00201"
PARENT_DSR = "TRL-2026-00199"
NY = "America/New_York"


def _progress(msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _write_csv(path: Path, rows: Iterable[Dict[str, object]]) -> None:
    rows = list(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _norm_ts(ts: object) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    else:
        t = t.tz_convert(NY)
    return t.isoformat()


def load_hp_trade_ids(campaigns_path: Path) -> Tuple[Set[str], pd.DataFrame]:
    """Fill-asof HP from stored campaign ``ma5_align`` (research contrast)."""
    df = pd.read_csv(campaigns_path)
    df["entry_ts"] = pd.to_datetime(df["entry_ts"], utc=True)
    hp = df[df["ma5_align"].astype(str) == "ma_aligned"].copy()
    return set(hp["trade_id"].astype(str)), df


def _ma_label(side: str, ma_state: object) -> str:
    if ma_state is None or (isinstance(ma_state, float) and np.isnan(ma_state)) or pd.isna(ma_state):
        return "ma_na"
    ms = str(ma_state)
    if (side == "long" and ms == "ma_bull") or (side == "short" and ms == "ma_bear"):
        return "ma_aligned"
    if (side == "long" and ms == "ma_bear") or (side == "short" and ms == "ma_bull"):
        return "ma_opposed"
    return "ma_flat"


def _asof_ma_state(ts: pd.Series, m5: pd.DataFrame) -> np.ndarray:
    left = pd.DataFrame(
        {
            "t": pd.to_datetime(ts, utc=True).dt.tz_convert(NY),
            "i": np.arange(len(ts)),
        }
    )
    merged = pd.merge_asof(
        left.sort_values("t"),
        m5.sort_values("ts"),
        left_on="t",
        right_on="ts",
        direction="backward",
    ).sort_values("i")
    return merged["ma_state"].to_numpy()


def load_arm_asof_hp_trade_ids(
    campaigns_path: Path = CAMPAIGNS,
    orders_path: Path = SOURCE_ORDERS,
) -> Tuple[Set[str], pd.DataFrame, Dict[str, int]]:
    """HP = ma_aligned at resting-entry arm time (no qty refresh until fill)."""
    camps = pd.read_csv(campaigns_path)
    camps["entry_ts"] = pd.to_datetime(camps["entry_ts"], utc=True).dt.tz_convert(NY)
    orders = pd.read_csv(orders_path)
    eo = orders[
        (orders["bracket_role"].astype(str) == "entry")
        & (orders["order_type"].astype(str).str.lower() == "stop")
    ].copy()
    eo["live_after_ts"] = pd.to_datetime(eo["live_after_ts"], utc=True).dt.tz_convert(NY)
    eo = eo.sort_values("live_after_ts").groupby("trade_id", as_index=False).first()
    m = camps.merge(eo[["trade_id", "live_after_ts"]], on="trade_id", how="left")
    if int(m["live_after_ts"].isna().sum()) != 0:
        raise RuntimeError("Missing entry-stop live_after_ts for some campaigns")

    _progress("Building NAS100 5m MA feature frame for arm-asof HP...")
    feats = build_feature_frames("NAS100")
    m5 = feats["m5"][["ts", "ma_state"]].sort_values("ts").copy()
    arm_ma = _asof_ma_state(m["live_after_ts"], m5)
    arm_lab = np.array([_ma_label(s, x) for s, x in zip(m["side"].astype(str), arm_ma)])
    fill_lab = m["ma5_align"].astype(str).to_numpy()
    m = m.copy()
    m["ma5_align_arm"] = arm_lab
    arm_hp = set(m.loc[arm_lab == "ma_aligned", "trade_id"].astype(str))
    meta = {
        "campaigns": int(len(m)),
        "hp_arm": int((arm_lab == "ma_aligned").sum()),
        "hp_fill_stored": int((fill_lab == "ma_aligned").sum()),
        "arm_vs_fill_flips": int((arm_lab != fill_lab).sum()),
        "hp_only_arm": int(((arm_lab == "ma_aligned") & (fill_lab != "ma_aligned")).sum()),
        "hp_only_fill": int(((fill_lab == "ma_aligned") & (arm_lab != "ma_aligned")).sum()),
    }
    return arm_hp, m, meta


def _append_dsr() -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    lines = path.read_text().splitlines()
    if any(ln.startswith(DSR + ",") for ln in lines):
        return
    header = next(ln for ln in lines if ln.startswith("trial_id,"))
    fields = header.split(",")
    row = {k: "" for k in fields}
    row.update(
        {
            "trial_id": DSR,
            "entry_date": date.today().isoformat(),
            "analyst": "cursor",
            "trial_class": "EXECUTION_VARIANT",
            "trial_subclass": "nas100_clean_break_ma_aligned_arm_asof_scales",
            "is_independent": "TRUE",
            "market": "NAS100",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "parent_dsr": PARENT_DSR,
                    "hp_contract": "arm_asof_no_qty_refresh",
                    "default_mult": HP_MULT,
                    "scales": list(DEFAULT_SCALES),
                    "hub": str(HUB.relative_to(REPO)),
                }
            ),
            "fixed_parameters_ref": "live/nas100_clean_break_ma_aligned_size15_broker.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "Arm-asof ma_aligned HP default + 2/4/6x MTM DD sensitivity",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def _mult_slug(mult: float) -> str:
    if abs(mult - round(mult)) < 1e-12:
        return str(int(round(mult)))
    return ("%.2f" % mult).replace(".", "_").rstrip("0").rstrip("_")


def _intrabar_usd(unit: Unit, bar: AuditBar, point_value: float) -> float:
    if unit.sign > 0:
        return (bar.low - unit.entry_price) * point_value
    return (unit.entry_price - bar.high) * point_value


def weighted_intraday_audit(
    *,
    strategy_id: str,
    state_root: Path,
    bars: List[AuditBar],
    units: List[Unit],
    hp_trade_ids: Set[str],
    hp_mult: float,
    instrument: str,
    fee_per_unit: float,
) -> Dict[str, float]:
    """Engine-fill unit audit with per-trade size weight (HP → hp_mult)."""
    point_value = POINT_VALUES[instrument]
    weights = {
        u.unit_id + "|" + u.trade_id: (hp_mult if u.trade_id in hp_trade_ids else 1.0)
        for u in units
    }

    def w(u: Unit) -> float:
        return float(weights.get(u.unit_id + "|" + u.trade_id, 1.0))

    units = sorted(units, key=lambda u: (u.entry_ts, u.exit_ts, u.unit_id))
    entries = sorted(units, key=lambda u: u.entry_ts)
    exits = sorted(units, key=lambda u: u.exit_ts)
    entry_i = 0
    exit_i = 0
    active: List[Unit] = []
    realized_usd = 0.0
    peak_close = 0.0
    close_dd = 0.0
    intrabar_dd = 0.0
    max_open = 0.0
    equity_rows: List[Dict[str, str]] = []

    for bar in bars:
        while exit_i < len(exits) and exits[exit_i].exit_ts < bar.ts:
            unit = exits[exit_i]
            realized_usd += (unit.points * point_value - fee_per_unit) * w(unit)
            exit_i += 1
        while entry_i < len(entries) and entries[entry_i].entry_ts <= bar.ts:
            active.append(entries[entry_i])
            entry_i += 1
        active = [unit for unit in active if unit.exit_ts >= bar.ts]
        close_equity = realized_usd + sum(
            (bar.close - u.entry_price) * u.sign * point_value * w(u) for u in active
        )
        intrabar_equity = realized_usd + sum(
            _intrabar_usd(u, bar, point_value) * w(u) for u in active
        )
        open_w = float(sum(w(u) for u in active))
        max_open = max(max_open, open_w)
        close_dd = min(close_dd, close_equity - peak_close)
        intrabar_dd = min(intrabar_dd, intrabar_equity - peak_close)
        peak_close = max(peak_close, close_equity)
        equity_rows.append(
            {
                "ts": bar.ts,
                "realized_usd": "%.2f" % realized_usd,
                "open_units_weighted": "%.2f" % open_w,
                "close_equity_usd": "%.2f" % close_equity,
                "intrabar_stress_equity_usd": "%.2f" % intrabar_equity,
                "close_dd_usd": "%.2f" % close_dd,
                "intrabar_stress_dd_usd": "%.2f" % intrabar_dd,
            }
        )

    unit_rows: List[Dict[str, object]] = []
    unit_nets: List[float] = []
    hp_unit_n = 0
    for unit in units:
        mult = w(unit)
        if mult > 1.0 + 1e-12:
            hp_unit_n += 1
        net = (unit.points * point_value - fee_per_unit) * mult
        unit_nets.append(net)
        unit_rows.append(
            {
                "candidate": strategy_id,
                "trade_id": unit.trade_id,
                "unit_id": unit.unit_id,
                "direction": unit.direction,
                "entry_ts": unit.entry_ts,
                "entry_price": "%.2f" % unit.entry_price,
                "exit_ts": unit.exit_ts,
                "exit_price": "%.2f" % unit.exit_price,
                "exit_reason": unit.exit_reason,
                "size_mult": "%.2f" % mult,
                "hp": int(mult > 1.0 + 1e-12),
                "net_usd": "%.2f" % net,
            }
        )
    state_root.mkdir(parents=True, exist_ok=True)
    _write_csv(state_root / "unit_trades.csv", unit_rows)
    _write_csv(state_root / "equity_curve.csv", equity_rows)

    arr = np.array(unit_nets, dtype=float)
    wins = float(arr[arr > 0].sum()) if len(arr) else 0.0
    losses = abs(float(arr[arr < 0].sum())) if len(arr) else 0.0
    pf = wins / losses if losses > 1e-9 else (math.inf if wins > 0 else 0.0)
    win_rate = 100.0 * float((arr > 0).mean()) if len(arr) else 0.0
    return {
        "net_usd": float(arr.sum()) if len(arr) else 0.0,
        "closed_dd_usd": float(close_dd),
        "intrabar_stress_dd_usd": float(intrabar_dd),
        "max_open_units": float(max_open),
        "win_rate": win_rate,
        "profit_factor": pf,
        "units": len(units),
        "hp_units": hp_unit_n,
        "ns": (
            float(arr.sum()) / abs(float(intrabar_dd))
            if abs(float(intrabar_dd)) > 1e-9
            else 0.0
        ),
    }


def campaign_overlay_score(
    campaigns: pd.DataFrame, hp_trade_ids: Set[str], hp_mult: float
) -> Dict[str, float]:
    """Campaign-tape score matching HA overlay apply_policy(size_1.5)."""
    nets = campaigns["net_usd"].to_numpy(dtype=float).copy()
    mask = campaigns["trade_id"].astype(str).isin(hp_trade_ids).to_numpy()
    sized = nets.copy()
    sized[mask] = sized[mask] * float(hp_mult)
    base_net = float(nets.sum())
    sized_net = float(sized.sum())

    def _stress(x: np.ndarray) -> float:
        eq = np.cumsum(x)
        peak = np.maximum.accumulate(eq)
        dd = eq - peak
        return float(abs(dd.min())) if len(dd) else 0.0

    base_stress = _stress(nets)
    sized_stress = _stress(sized)
    return {
        "base_net": base_net,
        "base_stress": base_stress,
        "base_ns": base_net / base_stress if base_stress > 1e-9 else 0.0,
        "sized_net": sized_net,
        "sized_stress": sized_stress,
        "sized_ns": sized_net / sized_stress if sized_stress > 1e-9 else 0.0,
        "delta_net": sized_net - base_net,
        "delta_ns": (sized_net / sized_stress if sized_stress > 1e-9 else 0.0)
        - (base_net / base_stress if base_stress > 1e-9 else 0.0),
        "hp_n": int(mask.sum()),
        "hp_frac": float(mask.mean()) if len(mask) else 0.0,
        "n": int(len(nets)),
    }


def load_audit_bars(max_sessions: Optional[int]) -> List[AuditBar]:
    df = load_nas100_1m(max_sessions=max_sessions)
    bars: List[AuditBar] = []
    for row in df.itertuples(index=False):
        bars.append(
            AuditBar(
                _norm_ts(row.ts),
                float(row.open),
                float(row.high),
                float(row.low),
                float(row.close),
            )
        )
    return bars


def run(
    *,
    email: bool = False,
    smoke: bool = False,
    fill_asof: bool = False,
    scales: Optional[Sequence[float]] = None,
) -> Dict[str, object]:
    HUB.mkdir(parents=True, exist_ok=True)
    state_root = HUB / "states" / STRATEGY_ID
    state_root.mkdir(parents=True, exist_ok=True)
    POINT_VALUES[INSTRUMENT] = POINT_VALUE
    DEFAULT_TICK_SIZE[INSTRUMENT] = 0.1
    _append_dsr()

    if not SOURCE_FILLS.exists():
        raise FileNotFoundError("Missing Engine fills: %s" % SOURCE_FILLS)
    if not CAMPAIGNS.exists():
        raise FileNotFoundError("Missing HA campaigns: %s" % CAMPAIGNS)
    if not SOURCE_ORDERS.exists():
        raise FileNotFoundError("Missing Engine orders: %s" % SOURCE_ORDERS)

    scale_list = list(scales) if scales is not None else list(DEFAULT_SCALES)
    if HP_MULT not in scale_list:
        scale_list = [HP_MULT] + scale_list
    # Unique preserve order
    seen = set()
    scales_u: List[float] = []
    for s in scale_list:
        sf = float(s)
        if sf not in seen:
            seen.add(sf)
            scales_u.append(sf)

    hp_contract = "fill_asof" if fill_asof else "arm_asof_no_qty_refresh"
    arm_meta: Dict[str, int] = {}
    if fill_asof:
        hp_ids, campaigns = load_hp_trade_ids(CAMPAIGNS)
        arm_meta = {
            "campaigns": int(len(campaigns)),
            "hp_arm": -1,
            "hp_fill_stored": int(len(hp_ids)),
            "arm_vs_fill_flips": -1,
            "hp_only_arm": -1,
            "hp_only_fill": -1,
        }
        _progress(
            "HP fill-asof ma_aligned: %d / %d (%.0f%%)"
            % (len(hp_ids), len(campaigns), 100.0 * len(hp_ids) / max(len(campaigns), 1))
        )
    else:
        hp_ids, campaigns, arm_meta = load_arm_asof_hp_trade_ids()
        _progress(
            "HP arm-asof ma_aligned (no qty refresh): %d / %d (%.0f%%) | fill-stored=%d flips=%d"
            % (
                len(hp_ids),
                arm_meta["campaigns"],
                100.0 * len(hp_ids) / max(arm_meta["campaigns"], 1),
                arm_meta["hp_fill_stored"],
                arm_meta["arm_vs_fill_flips"],
            )
        )
        camps_out = HUB / "arm_asof_campaigns.csv"
        campaigns.to_csv(camps_out, index=False)
        _progress("Wrote %s" % camps_out.relative_to(REPO))

    overlay_default = campaign_overlay_score(campaigns, hp_ids, HP_MULT)
    _progress(
        "Campaign overlay @ ×%.2f (%s): net=$%.0f N/S=%.2f Δnet=$%+.0f ΔN/S=%+.2f"
        % (
            HP_MULT,
            hp_contract,
            overlay_default["sized_net"],
            overlay_default["sized_ns"],
            overlay_default["delta_net"],
            overlay_default["delta_ns"],
        )
    )

    units = units_from_v2b_fills(SOURCE_FILLS, STRATEGY_ID)
    unit_trade_ids = {u.trade_id for u in units}
    missing = sorted(hp_ids - unit_trade_ids)
    if missing:
        _progress("WARN: %d HP trade_ids not in Engine fills (first=%s)" % (len(missing), missing[0]))
    hp_units = sum(1 for u in units if u.trade_id in hp_ids)
    _progress(
        "Engine units: %d  HP-sized units: %d  scales=%s"
        % (len(units), hp_units, ",".join("%.2g" % s for s in scales_u))
    )

    max_sessions = 80 if smoke else None
    _progress("Loading NAS100 1m bars for weighted Engine stress audit...")
    bars = load_audit_bars(max_sessions=max_sessions)
    if smoke:
        if bars:
            end_ts = bars[-1].ts
            units = [u for u in units if u.entry_ts <= end_ts]
            keep = {u.trade_id for u in units}
            hp_ids = {t for t in hp_ids if t in keep}
        _progress("SMOKE: bars=%d units=%d hp=%d" % (len(bars), len(units), len(hp_ids)))

    _progress("Running weighted intrabar audit (baseline 1.0×)...")
    baseline = weighted_intraday_audit(
        strategy_id=STRATEGY_ID,
        state_root=state_root / "baseline",
        bars=bars,
        units=units,
        hp_trade_ids=set(),
        hp_mult=1.0,
        instrument=INSTRUMENT,
        fee_per_unit=FEE_PER_UNIT,
    )
    _progress(
        "Engine baseline: net=$%.2f stress=$%.2f closed_dd=$%.2f N/S=%.2f"
        % (
            baseline["net_usd"],
            baseline["intrabar_stress_dd_usd"],
            baseline["closed_dd_usd"],
            baseline["ns"],
        )
    )

    base_stress_abs = abs(float(baseline["intrabar_stress_dd_usd"]))
    base_close_abs = abs(float(baseline["closed_dd_usd"]))
    summary_rows: List[Dict[str, object]] = [
        {
            "book": "baseline_unit",
            "hp_contract": hp_contract,
            "policy": "baseline",
            "hp_mult": 1.0,
            "net_usd": "%.2f" % baseline["net_usd"],
            "closed_dd_usd": "%.2f" % baseline["closed_dd_usd"],
            "intrabar_stress_dd_usd": "%.2f" % baseline["intrabar_stress_dd_usd"],
            "ns": "%.6f" % baseline["ns"],
            "trades": len({u.trade_id for u in units}),
            "units": baseline["units"],
            "hp_units": 0,
            "max_open_units": "%.2f" % baseline["max_open_units"],
            "win_rate_units": "%.4f" % baseline["win_rate"],
            "profit_factor": "%.6f" % baseline["profit_factor"]
            if math.isfinite(baseline["profit_factor"])
            else "inf",
            "mtm_dd_vs_baseline": "1.000",
            "closed_dd_vs_baseline": "1.000",
            "net_vs_baseline": "1.000",
            "linear_mtm_expect": "1.000",
        }
    ]

    scale_results: Dict[str, Dict[str, float]] = {}
    default_key = "x%s" % _mult_slug(HP_MULT)
    for mult in scales_u:
        slug = _mult_slug(mult)
        book_dir = "size_%s_ma_aligned_arm" % slug if not fill_asof else "size_%s_ma_aligned_fill" % slug
        _progress("Running weighted audit HP @ ×%.2f (%s)..." % (mult, hp_contract))
        sized = weighted_intraday_audit(
            strategy_id=STRATEGY_ID,
            state_root=state_root / book_dir,
            bars=bars,
            units=units,
            hp_trade_ids=hp_ids,
            hp_mult=float(mult),
            instrument=INSTRUMENT,
            fee_per_unit=FEE_PER_UNIT,
        )
        overlay = campaign_overlay_score(campaigns, hp_ids, float(mult))
        delta_net = sized["net_usd"] - baseline["net_usd"]
        delta_ns = sized["ns"] - baseline["ns"]
        stress_abs = abs(float(sized["intrabar_stress_dd_usd"]))
        close_abs = abs(float(sized["closed_dd_usd"]))
        mtm_ratio = stress_abs / base_stress_abs if base_stress_abs > 1e-9 else float("nan")
        close_ratio = close_abs / base_close_abs if base_close_abs > 1e-9 else float("nan")
        net_ratio = (
            float(sized["net_usd"]) / float(baseline["net_usd"])
            if abs(float(baseline["net_usd"])) > 1e-9
            else float("nan")
        )
        # Linear in size would scale only the HP slice; report DD ratio vs baseline
        # and vs the ×1.5 book for super/sub-linearity diagnosis.
        scale_results["x%s" % slug] = {
            "hp_mult": float(mult),
            "net_usd": float(sized["net_usd"]),
            "closed_dd_usd": float(sized["closed_dd_usd"]),
            "intrabar_stress_dd_usd": float(sized["intrabar_stress_dd_usd"]),
            "ns": float(sized["ns"]),
            "delta_net": float(delta_net),
            "delta_ns": float(delta_ns),
            "hp_units": float(sized["hp_units"]),
            "max_open_units": float(sized["max_open_units"]),
            "mtm_dd_vs_baseline": float(mtm_ratio),
            "closed_dd_vs_baseline": float(close_ratio),
            "net_vs_baseline": float(net_ratio),
            "overlay_delta_net": float(overlay["delta_net"]),
            "overlay_delta_ns": float(overlay["delta_ns"]),
        }
        _progress(
            "Engine ×%.2f: net=$%.2f stress=$%.2f (×%.3f vs base) closed_dd=$%.2f N/S=%.2f Δnet=$%+.2f"
            % (
                mult,
                sized["net_usd"],
                sized["intrabar_stress_dd_usd"],
                mtm_ratio,
                sized["closed_dd_usd"],
                sized["ns"],
                delta_net,
            )
        )
        summary_rows.append(
            {
                "book": "ma_aligned_%s_x%s" % (hp_contract, slug),
                "hp_contract": hp_contract,
                "policy": "size_%s" % slug,
                "hp_mult": float(mult),
                "net_usd": "%.2f" % sized["net_usd"],
                "closed_dd_usd": "%.2f" % sized["closed_dd_usd"],
                "intrabar_stress_dd_usd": "%.2f" % sized["intrabar_stress_dd_usd"],
                "ns": "%.6f" % sized["ns"],
                "trades": len({u.trade_id for u in units}),
                "units": sized["units"],
                "hp_units": sized["hp_units"],
                "max_open_units": "%.2f" % sized["max_open_units"],
                "win_rate_units": "%.4f" % sized["win_rate"],
                "profit_factor": "%.6f" % sized["profit_factor"]
                if math.isfinite(sized["profit_factor"])
                else "inf",
                "delta_net": "%.2f" % delta_net,
                "delta_ns": "%.6f" % delta_ns,
                "overlay_delta_net": "%.2f" % overlay["delta_net"],
                "overlay_delta_ns": "%.6f" % overlay["delta_ns"],
                "overlay_sized_net": "%.2f" % overlay["sized_net"],
                "overlay_sized_ns": "%.6f" % overlay["sized_ns"],
                "hp_campaigns": overlay["hp_n"],
                "hp_frac": "%.6f" % overlay["hp_frac"],
                "mtm_dd_vs_baseline": "%.4f" % mtm_ratio,
                "closed_dd_vs_baseline": "%.4f" % close_ratio,
                "net_vs_baseline": "%.4f" % net_ratio,
            }
        )

    default = scale_results[default_key]
    # Relative to default ×1.5: does MTM DD grow ~linearly with (mult-1) or with mult?
    for key, row in scale_results.items():
        mult = row["hp_mult"]
        d15 = abs(default["intrabar_stress_dd_usd"])
        row["mtm_dd_vs_x1_5"] = (
            abs(row["intrabar_stress_dd_usd"]) / d15 if d15 > 1e-9 else float("nan")
        )
        # If only HP units scale and HP share of stress is constant, expect
        # stress ≈ base + (mult-1)/(1.5-1) * (stress_1.5 - base)
        expected = base_stress_abs + (mult - 1.0) / (HP_MULT - 1.0) * (
            abs(default["intrabar_stress_dd_usd"]) - base_stress_abs
        )
        actual = abs(row["intrabar_stress_dd_usd"])
        row["mtm_dd_linear_from_x1_5_expect"] = float(expected)
        row["mtm_dd_vs_linear_expect"] = (
            actual / expected if expected > 1e-9 else float("nan")
        )

    # Patch summary rows with vs x1.5 ratios
    for r in summary_rows:
        if float(r["hp_mult"]) <= 1.0 + 1e-12:
            r["mtm_dd_vs_x1_5"] = ""
            r["mtm_dd_vs_linear_expect"] = ""
            continue
        key = "x%s" % _mult_slug(float(r["hp_mult"]))
        sr = scale_results[key]
        r["mtm_dd_vs_x1_5"] = "%.4f" % sr["mtm_dd_vs_x1_5"]
        r["mtm_dd_linear_from_x1_5_expect"] = "%.2f" % sr["mtm_dd_linear_from_x1_5_expect"]
        r["mtm_dd_vs_linear_expect"] = "%.4f" % sr["mtm_dd_vs_linear_expect"]

    _write_csv(HUB / "summary.csv", summary_rows)
    _write_csv(
        HUB / "scale_sensitivity.csv",
        [
            {
                "hp_mult": "%.2f" % v["hp_mult"],
                "net_usd": "%.2f" % v["net_usd"],
                "closed_dd_usd": "%.2f" % v["closed_dd_usd"],
                "intrabar_stress_dd_usd": "%.2f" % v["intrabar_stress_dd_usd"],
                "ns": "%.6f" % v["ns"],
                "delta_net": "%.2f" % v["delta_net"],
                "delta_ns": "%.6f" % v["delta_ns"],
                "mtm_dd_vs_baseline": "%.4f" % v["mtm_dd_vs_baseline"],
                "mtm_dd_vs_x1_5": "%.4f" % v["mtm_dd_vs_x1_5"],
                "mtm_dd_linear_from_x1_5_expect": "%.2f" % v["mtm_dd_linear_from_x1_5_expect"],
                "mtm_dd_vs_linear_expect": "%.4f" % v["mtm_dd_vs_linear_expect"],
                "closed_dd_vs_baseline": "%.4f" % v["closed_dd_vs_baseline"],
                "net_vs_baseline": "%.4f" % v["net_vs_baseline"],
                "max_open_units": "%.2f" % v["max_open_units"],
                "hp_units": int(v["hp_units"]),
            }
            for v in scale_results.values()
        ],
    )

    # MTM DD affected? Compare ratios at 2/4/6 vs linear interpolation from ×1.5
    extreme = [scale_results[k] for k in scale_results if scale_results[k]["hp_mult"] > HP_MULT + 1e-12]
    if extreme:
        max_dev = max(abs(v["mtm_dd_vs_linear_expect"] - 1.0) for v in extreme)
        if max_dev < 0.02:
            dd_stance = (
                "MTM DD scales ~linearly with HP size increment (within 2%% of "
                "interpolation from ×1.5) — no material non-linear DD surprise at 2/4/6×."
            )
        elif max_dev < 0.10:
            dd_stance = (
                "MTM DD mostly linear in HP size; mild deviation (%.0f%%) from ×1.5 "
                "interpolation at extremes — report ratios, not a hard fail."
                % (100.0 * max_dev)
            )
        else:
            dd_stance = (
                "MTM DD shows material non-linearity vs ×1.5 interpolation "
                "(max |ratio-1|=%.0f%%) — size extremes change path DD, not just scale."
                % (100.0 * max_dev)
            )
    else:
        dd_stance = "No scales above ×1.5 requested."
        max_dev = 0.0

    stance = "RESEARCH — arm-asof Engine confirms size-up lift @ ×1.5"
    if default["delta_ns"] <= 0 or default["delta_net"] <= 0:
        stance = "REJECT / no Engine lift under arm-asof @ ×1.5"
    elif default["ns"] < baseline["ns"] * 1.05 and default["delta_net"] > 0:
        stance = "RESEARCH — arm-asof net up, N/S weak @ ×1.5"

    def _row_line(label: str, net: float, close_dd: float, stress: float, ns: float, max_open: float, hp_u: object) -> str:
        hp_s = "—" if hp_u is None else str(int(hp_u))
        return "| %s | $%s | $%s | $%s | %.2f | %.1f | %s |" % (
            label,
            money(net),
            money(close_dd),
            money(stress),
            ns,
            max_open,
            hp_s,
        )

    lines = [
        "# NAS100 clean-break — ma_aligned HP size-up (arm-asof default)",
        "",
        "STATUS: Engine+PaperBroker 1m-fill unit tape with **weighted** HP size-up.",
        "**Default contract:** arm-asof `ma_aligned` at resting-entry `live_after_ts`",
        "(no qty refresh until fill). Default mult ×1.5; also swept 2× / 4× / 6× for MTM DD.",
        "",
        "Source fills: `%s`" % SOURCE_FILLS.relative_to(REPO),
        "HA campaigns: `%s`" % CAMPAIGNS.relative_to(REPO),
        "Frozen variant: `trail06_m4_e2_out_be` (OANDA practice / Index Momentum).",
        "HP contract: `%s`" % hp_contract,
        "DSR: `%s` (parent `%s`)" % (DSR, PARENT_DSR),
        "",
        "## Arm-asof HP set",
        "",
        "| Metric | Value |",
        "|---|---:|",
        "| Campaigns | %d |" % arm_meta["campaigns"],
        "| HP arm-asof | %d |" % (arm_meta["hp_arm"] if arm_meta["hp_arm"] >= 0 else len(hp_ids)),
        "| HP fill-stored | %d |" % arm_meta["hp_fill_stored"],
        "| Arm↔fill label flips | %d |" % arm_meta["arm_vs_fill_flips"],
        "",
        "## Result (intrabar Engine stress)",
        "",
        "| Book | Net | Closed DD | Intrabar MTM stress | N/S | Max open (wtd) | HP units |",
        "|---|---:|---:|---:|---:|---:|---:|",
        _row_line(
            "Baseline 1.0×",
            baseline["net_usd"],
            baseline["closed_dd_usd"],
            baseline["intrabar_stress_dd_usd"],
            baseline["ns"],
            baseline["max_open_units"],
            None,
        ),
    ]
    for mult in scales_u:
        key = "x%s" % _mult_slug(mult)
        r = scale_results[key]
        label = "Arm-asof HP ×%s" % ("%.2g" % mult if not fill_asof else "%.2g fill" % mult)
        if fill_asof:
            label = "Fill-asof HP ×%.2g" % mult
        else:
            label = "Arm-asof HP ×%.2g" % mult
        lines.append(
            _row_line(
                label,
                r["net_usd"],
                r["closed_dd_usd"],
                r["intrabar_stress_dd_usd"],
                r["ns"],
                r["max_open_units"],
                r["hp_units"],
            )
        )
    lines.extend(
        [
            "",
            "Default ×1.5: Δnet=$%+.2f  ΔN/S=%+.2f" % (default["delta_net"], default["delta_ns"]),
            "",
            "## MTM DD scale sensitivity",
            "",
            "| Mult | MTM DD | vs baseline | vs ×1.5 | vs linear-from-×1.5 | Net | N/S |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for mult in scales_u:
        r = scale_results["x%s" % _mult_slug(mult)]
        lines.append(
            "| ×%.2g | $%s | %.3f× | %.3f× | %.3f× | $%s | %.2f |"
            % (
                mult,
                money(r["intrabar_stress_dd_usd"]),
                r["mtm_dd_vs_baseline"],
                r["mtm_dd_vs_x1_5"],
                r["mtm_dd_vs_linear_expect"],
                money(r["net_usd"]),
                r["ns"],
            )
        )
    lines.extend(
        [
            "",
            "Linear-from-×1.5 expect = baseline_MTM + (mult−1)/(1.5−1) × (MTM_1.5 − baseline_MTM).",
            "Only the HP slice is upsized; non-HP units stay ×1, so whole-book MTM is **not**",
            "expected to scale as mult×baseline.",
            "",
            "**MTM DD read:** %s" % dd_stance,
            "",
            "## Campaign overlay cross-check @ ×1.5",
            "",
            "| | Net | Stress | N/S |",
            "|---|---:|---:|---:|",
            "| Overlay baseline | $%.0f | $%.0f | %.2f |"
            % (
                overlay_default["base_net"],
                overlay_default["base_stress"],
                overlay_default["base_ns"],
            ),
            "| Overlay sized | $%.0f | $%.0f | %.2f |"
            % (
                overlay_default["sized_net"],
                overlay_default["sized_stress"],
                overlay_default["sized_ns"],
            ),
            "",
            "Overlay Δnet=$%+.0f ΔN/S=%+.2f (hp=%.0f%% n=%d)"
            % (
                overlay_default["delta_net"],
                overlay_default["delta_ns"],
                100.0 * overlay_default["hp_frac"],
                overlay_default["hp_n"],
            ),
            "",
            "## Stance",
            "",
            stance,
            "",
            "Live demo plugin unchanged (no ma_aligned size-up wired yet).",
            "",
            "Hub: `%s`" % HUB,
            "",
        ]
    )
    (HUB / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")

    email_lines = [
        "potions: NAS100 clean-break ma_aligned arm-asof HP size-up complete",
        "",
        "Hub: %s" % HUB,
        "Contract: %s (default ×1.5)" % hp_contract,
        "Scales: %s" % ", ".join("×%.2g" % s for s in scales_u),
        "DSR: %s (parent %s)" % (DSR, PARENT_DSR),
        "",
        "HP campaigns: %d / %d" % (len(hp_ids), arm_meta["campaigns"]),
        "Engine baseline: net=$%.0f MTM DD=$%.0f N/S=%.2f"
        % (baseline["net_usd"], abs(baseline["intrabar_stress_dd_usd"]), baseline["ns"]),
        "",
        "Scale board (MTM DD):",
    ]
    for mult in scales_u:
        r = scale_results["x%s" % _mult_slug(mult)]
        email_lines.append(
            "  ×%.2g  net=$%.0f  MTM=$%.0f (%.3f× base, %.3f× vs linear)  N/S=%.2f"
            % (
                mult,
                r["net_usd"],
                abs(r["intrabar_stress_dd_usd"]),
                r["mtm_dd_vs_baseline"],
                r["mtm_dd_vs_linear_expect"],
                r["ns"],
            )
        )
    email_lines.extend(
        [
            "",
            "Default ×1.5 Δnet=$%+.0f ΔN/S=%+.2f" % (default["delta_net"], default["delta_ns"]),
            "",
            "MTM DD: %s" % dd_stance,
            "Stance: %s" % stance,
            "",
        ]
    )
    email_body = "\n".join(email_lines)
    (HUB / "EMAIL.txt").write_text(email_body, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(
        json.dumps(
            {
                "hp_contract": hp_contract,
                "arm_meta": arm_meta,
                "baseline": baseline,
                "scales": {k: v for k, v in scale_results.items()},
                "default_mult": HP_MULT,
                "default": default,
                "overlay_default": overlay_default,
                "dd_stance": dd_stance,
                "max_linear_dev": max_dev,
                "stance": stance,
                "smoke": smoke,
                "dsr": DSR,
                "parent_dsr": PARENT_DSR,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    out_paths = [
        HUB / "SUMMARY.md",
        HUB / "summary.csv",
        HUB / "scale_sensitivity.csv",
        HUB / "EMAIL.txt",
        state_root / "baseline" / "equity_curve.csv",
    ]
    for mult in scales_u:
        slug = _mult_slug(mult)
        book_dir = "size_%s_ma_aligned_arm" % slug if not fill_asof else "size_%s_ma_aligned_fill" % slug
        out_paths.append(state_root / book_dir / "equity_curve.csv")

    write_run_manifest(
        HUB,
        data_inputs=[SOURCE_FILLS, SOURCE_ORDERS, CAMPAIGNS, REPO / "fx" / "nas100_1m.csv"],
        output_paths=out_paths,
        strategy_config={
            "variant": "trail06_m4_e2_out_be",
            "hp_condition": "5m MA vs trade",
            "hp_bucket": "ma_aligned",
            "hp_contract": hp_contract,
            "hp_size_mult_default": HP_MULT,
            "scales": scales_u,
            "fill_tape": "engine_1m_proxy_existing",
        },
        broker_realism_config={
            "fill_tape": "1m",
            "signal_timeframe": "5m",
            "fee_per_unit": FEE_PER_UNIT,
            "point_value": POINT_VALUE,
            "size_model": "weighted_unit_audit_on_engine_fills",
        },
        causality_mode="arm_asof_no_qty_refresh",
        repo_root=REPO,
        extra={
            "study_id": HUB.name,
            "dsr_trial_id": DSR,
            "parent_dsr": PARENT_DSR,
            "source_hub": str(SOURCE_HUB.relative_to(REPO)),
        },
    )

    _mark_dsr("COMPLETE")
    if email:
        send_email(
            subject="potions: NAS100 clean-break arm-asof ma_aligned HP scales complete",
            body=email_body,
        )
        _progress("email sent")

    return {
        "baseline_net": baseline["net_usd"],
        "baseline_ns": baseline["ns"],
        "baseline_stress": baseline["intrabar_stress_dd_usd"],
        "sized_net": default["net_usd"],
        "sized_ns": default["ns"],
        "sized_stress": default["intrabar_stress_dd_usd"],
        "delta_net": default["delta_net"],
        "delta_ns": default["delta_ns"],
        "hp_contract": hp_contract,
        "scales": scale_results,
        "dd_stance": dd_stance,
        "stance": stance,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument(
        "--fill-asof",
        action="store_true",
        help="Use fill-asof campaign ma5_align HP (research contrast). Default is arm-asof.",
    )
    ap.add_argument(
        "--scales",
        default="1.5,2,4,6",
        help="Comma-separated HP multipliers (default 1.5,2,4,6). Always includes 1.5.",
    )
    args = ap.parse_args()
    scales = [float(x.strip()) for x in str(args.scales).split(",") if x.strip()]
    rid = begin_run(
        run_class="broker_like",
        variant_slug="nas100_clean_break_ma_aligned_arm_asof_scales",
        instrument=INSTRUMENT,
        hub_path=str(HUB.relative_to(REPO)),
        engine="engine_1mfill_weighted_hp_size",
        dsr_trial_id=DSR,
        meta={
            "condition": "5m MA vs trade=ma_aligned",
            "hp_contract": "fill_asof" if args.fill_asof else "arm_asof_no_qty_refresh",
            "policy": "size_scales",
            "scales": scales,
            "source": "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation",
            "smoke": bool(args.smoke),
        },
        notes="Arm-asof ma_aligned HP default ×1.5 + 2/4/6× MTM DD sensitivity on OANDA NAS100 clean-break.",
    )
    try:
        result = run(
            email=bool(args.email),
            smoke=bool(args.smoke),
            fill_asof=bool(args.fill_asof),
            scales=scales,
        )
        complete_run(
            rid,
            net_usd=result["sized_net"],
            stress_dd_usd=result["sized_stress"],
            ns=result["sized_ns"],
            meta={
                "baseline_net": result["baseline_net"],
                "baseline_ns": result["baseline_ns"],
                "delta_net": result["delta_net"],
                "delta_ns": result["delta_ns"],
                "hp_contract": result["hp_contract"],
                "dd_stance": result["dd_stance"],
                "stance": result["stance"],
            },
        )
        payload = json.loads((HUB / "RUN_COMPLETE.json").read_text(encoding="utf-8"))
        payload["ledger_run_id"] = rid
        (HUB / "RUN_COMPLETE.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception as exc:
        fail_run(rid, error=str(exc))
        _mark_dsr("FAILED")
        err = (
            "potions: NAS100 clean-break arm-asof ma_aligned HP scales FAILED\n\n%s\n\n%s\n"
            % (HUB, traceback.format_exc()[-2500:])
        )
        (HUB / "EMAIL.txt").write_text(err, encoding="utf-8")
        if args.email:
            send_email(
                subject="potions: NAS100 clean-break arm-asof ma_aligned HP scales FAILED",
                body=err,
            )
        raise


if __name__ == "__main__":
    main()
