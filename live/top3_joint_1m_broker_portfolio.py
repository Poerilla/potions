"""TOP3 active-demo portfolio — joint 1-minute Engine fill MTM (NAS100 ×10).

Walks Asia-range + Monday OR + NAS100 Clean Break on a shared minute clock using
each sleeve's existing Engine+PaperBroker fills (independent strategy_id lots,
same as separate demo accounts). NAS100 Clean Break size is scaled ×10 for this
run. USDJPY research PnL is USD-normalized at /JPY_USD (110).

Hub::

  live/state/top3_active_demo_portfolio/joint_1m_cb10x/

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.top3_joint_1m_broker_portfolio --email
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import JPY_USD, MARKETS, REPO
from .notify_email import send_email
from .replay_audit import POINT_VALUES, Unit, units_from_live_fills
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_clean_break_pyramid_trail_sizing_v1 import FEE_PER_UNIT as CB_FEE
from .v2b_strategy_replay import AuditBar, units_from_v2b_fills

HUB = REPO / "live" / "state" / "top3_active_demo_portfolio" / "joint_1m_cb10x"
CB_SCALE = 10.0
# Optional override so an add-on driver can log into its own hub.
_PROGRESS_HUB: Optional[Path] = None

ASIA_STATE = (
    REPO
    / "live/state/fx_v2b_asia_range_london_usdjpy_filters/states/usdjpy_v2b_asia_range_london_S_3_1_3_flt"
)
MONDAY_STATE = REPO / "live/state/monday_or_phase2/tuneup_broker/states/usdjpy_m2_s3_r1_skip_augsep"
CB_STATE = (
    REPO
    / "live/state/nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill_validation/states"
    / "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill"
)

ASIA_ID = "usdjpy_v2b_asia_range_london_S_3_1_3"
MONDAY_ID = "usdjpy_m2_s3_r1_skip_augsep"
CB_ID = "nas100_v2b_clean_break_trail06_m4_e2_out_be_1mfill"

NY = "America/New_York"


@dataclass(frozen=True)
class SleeveUnit:
    sleeve: str
    instrument: str
    unit: Unit
    point_value: float
    fee: float
    usd_div: float
    size_mult: float

    @property
    def sign(self) -> int:
        return -1 if str(self.unit.direction).lower().startswith("s") else 1

    @property
    def entry_ts(self) -> str:
        return self.unit.entry_ts

    @property
    def exit_ts(self) -> str:
        return self.unit.exit_ts

    def realized_usd(self) -> float:
        pts = (self.unit.exit_price - self.unit.entry_price) * self.sign
        raw = pts * self.point_value * self.size_mult - self.fee * self.size_mult
        return raw / self.usd_div

    def close_mtm_usd(self, px: float) -> float:
        pts = (px - self.unit.entry_price) * self.sign
        return (pts * self.point_value * self.size_mult) / self.usd_div

    def intrabar_mtm_usd(self, bar: AuditBar) -> float:
        if self.sign > 0:
            pts = bar.low - self.unit.entry_price
        else:
            pts = self.unit.entry_price - bar.high
        return (pts * self.point_value * self.size_mult) / self.usd_div


def _progress(msg: str) -> None:
    dest = _PROGRESS_HUB or HUB
    dest.mkdir(parents=True, exist_ok=True)
    with (dest / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg.rstrip() + "\n")
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        pass


def _parse_ts(ts: str) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def _iso(ts: pd.Timestamp) -> str:
    return ts.isoformat()


def load_sleeve_units() -> List[SleeveUnit]:
    asia_fee = float(MARKETS["USDJPY"].fee_per_unit)
    usdjpy_pv = float(POINT_VALUES["USDJPY"])
    nas_pv = float(POINT_VALUES["NAS100"])

    asia = units_from_v2b_fills(ASIA_STATE / "fills.csv", ASIA_ID)
    monday = units_from_live_fills(MONDAY_STATE / "fills.csv", MONDAY_ID)
    cb = units_from_v2b_fills(CB_STATE / "fills.csv", CB_ID)

    out: List[SleeveUnit] = []
    for u in asia:
        out.append(
            SleeveUnit(
                sleeve="asia_range",
                instrument="USDJPY",
                unit=u,
                point_value=usdjpy_pv,
                fee=asia_fee,
                usd_div=JPY_USD,
                size_mult=1.0,
            )
        )
    for u in monday:
        out.append(
            SleeveUnit(
                sleeve="monday_or",
                instrument="USDJPY",
                unit=u,
                point_value=usdjpy_pv,
                fee=1.5,
                usd_div=JPY_USD,
                size_mult=1.0,
            )
        )
    for u in cb:
        out.append(
            SleeveUnit(
                sleeve="clean_break",
                instrument="NAS100",
                unit=u,
                point_value=nas_pv,
                fee=float(CB_FEE),
                usd_div=1.0,
                size_mult=CB_SCALE,
            )
        )
    return out


def _common_window(units: Sequence[SleeveUnit]) -> Tuple[pd.Timestamp, pd.Timestamp]:
    by_sleeve: Dict[str, List[SleeveUnit]] = {}
    for u in units:
        by_sleeve.setdefault(u.sleeve, []).append(u)
    starts = []
    ends = []
    for sleeve, rows in by_sleeve.items():
        starts.append(min(_parse_ts(u.entry_ts) for u in rows))
        ends.append(max(_parse_ts(u.exit_ts) for u in rows))
        _progress("  sleeve %s units=%d %s → %s" % (sleeve, len(rows), starts[-1].date(), ends[-1].date()))
    lo = max(starts)
    hi = min(ends)
    return lo, hi


def _filter_units_common(units: Sequence[SleeveUnit], lo: pd.Timestamp, hi: pd.Timestamp) -> List[SleeveUnit]:
    """Keep units whose entry falls inside the common window (standard common-window N/S)."""
    out = []
    for u in units:
        et = _parse_ts(u.entry_ts)
        if lo <= et <= hi:
            out.append(u)
    return out


def load_usdjpy_1m(lo: pd.Timestamp, hi: pd.Timestamp) -> List[Tuple[int, AuditBar]]:
    path = REPO / "fx" / "usdjpy_1m.csv"
    _progress("Loading USDJPY 1m %s → %s ..." % (lo.date(), hi.date()))
    df = pd.read_csv(path, usecols=["ts_event", "open", "high", "low", "close"])
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    df = df[ts.notna()].copy()
    df["ts"] = ts[ts.notna()].dt.tz_convert(NY)
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[(df["ts"] >= lo) & (df["ts"] <= hi + pd.Timedelta(days=1))].copy()
    df = df.sort_values("ts")
    out: List[Tuple[int, AuditBar]] = []
    for r in df.itertuples(index=False):
        t = pd.Timestamp(r.ts)
        out.append((int(t.value), AuditBar(_iso(t), float(r.open), float(r.high), float(r.low), float(r.close))))
    _progress("  USDJPY 1m bars=%d" % len(out))
    return out


def load_nas100_1m(lo: pd.Timestamp, hi: pd.Timestamp) -> List[Tuple[int, AuditBar]]:
    path = REPO / "fx" / "nas100_1m.csv"
    _progress("Loading NAS100 1m %s → %s ..." % (lo.date(), hi.date()))
    df = pd.read_csv(path, usecols=["ts_event", "open", "high", "low", "close", "volume"])
    ts = pd.to_datetime(df["ts_event"], utc=True, errors="coerce")
    df = df[ts.notna()].copy()
    df["ts"] = ts[ts.notna()].dt.tz_convert(NY)
    for c in ("open", "high", "low", "close"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.dropna(subset=["open", "high", "low", "close"])
    df = df[df["ts"].dt.weekday < 5]
    local_time = df["ts"].dt.time
    df = df[(local_time >= pd.Timestamp("09:30").time()) & (local_time < pd.Timestamp("16:00").time())]
    df = df[(df["ts"] >= lo) & (df["ts"] <= hi + pd.Timedelta(days=1))].copy()
    df = df.sort_values("ts")
    out: List[Tuple[int, AuditBar]] = []
    for r in df.itertuples(index=False):
        t = pd.Timestamp(r.ts)
        out.append((int(t.value), AuditBar(_iso(t), float(r.open), float(r.high), float(r.low), float(r.close))))
    _progress("  NAS100 1m bars=%d" % len(out))
    return out


_SLEEVE_ORDER = (
    "asia_range",
    "monday_or",
    "clean_break",
    "nq_prior_opposed",
    "nas100_nq_lead",
)


def _sleeve_stats(units: Sequence[SleeveUnit]) -> Dict[str, dict]:
    present = {u.sleeve for u in units}
    names = [s for s in _SLEEVE_ORDER if s in present]
    for s in sorted(present):
        if s not in names:
            names.append(s)
    out: Dict[str, dict] = {}
    for sleeve in names:
        rows = [u for u in units if u.sleeve == sleeve]
        nets = np.array([u.realized_usd() for u in rows], dtype=float) if rows else np.array([])
        out[sleeve] = {
            "units": len(rows),
            "trades": len({u.unit.trade_id for u in rows}),
            "net_usd": float(nets.sum()) if len(nets) else 0.0,
            "win_rate": float((nets > 0).mean() * 100.0) if len(nets) else 0.0,
        }
    return out


def joint_1m_mtm(
    units: Sequence[SleeveUnit],
    jpy_bars: Sequence[Tuple[int, AuditBar]],
    nas_bars: Sequence[Tuple[int, AuditBar]],
    nq_bars: Optional[Sequence[Tuple[int, AuditBar]]] = None,
    keep_bar_sample: bool = True,
) -> Dict[str, object]:
    """Walk union of 1m bars; mark each sleeve on its instrument tape."""

    @dataclass
    class _Lot:
        sleeve: str
        instrument: str
        sign: int
        entry_px: float
        exit_ns: int
        point_value: float
        fee: float
        usd_div: float
        size_mult: float
        realized: float

    def _ns(ts: str) -> int:
        return int(_parse_ts(ts).value)

    lots_entry: List[Tuple[int, _Lot]] = []
    lots_exit: List[Tuple[int, _Lot]] = []
    for u in units:
        lot = _Lot(
            sleeve=u.sleeve,
            instrument=u.instrument,
            sign=u.sign,
            entry_px=float(u.unit.entry_price),
            exit_ns=_ns(u.exit_ts),
            point_value=u.point_value,
            fee=u.fee,
            usd_div=u.usd_div,
            size_mult=u.size_mult,
            realized=u.realized_usd(),
        )
        lots_entry.append((_ns(u.entry_ts), lot))
        lots_exit.append((_ns(u.exit_ts), lot))
    lots_entry.sort(key=lambda x: x[0])
    lots_exit.sort(key=lambda x: x[0])

    events: List[Tuple[int, int, AuditBar]] = []  # ns, inst_code 0=JPY 1=NAS 2=NQ, bar
    for ns, b in jpy_bars:
        events.append((ns, 0, b))
    for ns, b in nas_bars:
        events.append((ns, 1, b))
    if nq_bars:
        for ns, b in nq_bars:
            events.append((ns, 2, b))
    events.sort(key=lambda x: (x[0], x[1]))

    entry_i = 0
    exit_i = 0
    active: List[_Lot] = []
    last_jpy: Optional[AuditBar] = None
    last_nas: Optional[AuditBar] = None
    last_nq: Optional[AuditBar] = None
    realized = 0.0
    peak_close = 0.0
    close_dd = 0.0
    intrabar_dd = 0.0
    max_open = 0
    equity_rows: List[dict] = []
    daily_rows: List[dict] = []
    last_day: Optional[str] = None
    day_close = 0.0
    day_stress = 0.0

    n_events = len(events)
    for i, (ts_ns, inst_code, bar) in enumerate(events, start=1):
        if inst_code == 0:
            last_jpy = bar
        elif inst_code == 2:
            last_nq = bar
        else:
            last_nas = bar

        exited = False
        while exit_i < len(lots_exit) and lots_exit[exit_i][0] < ts_ns:
            realized += lots_exit[exit_i][1].realized
            exit_i += 1
            exited = True
        while entry_i < len(lots_entry) and lots_entry[entry_i][0] <= ts_ns:
            active.append(lots_entry[entry_i][1])
            entry_i += 1
        if exited and active:
            active = [u for u in active if u.exit_ns >= ts_ns]
        max_open = max(max_open, len(active))

        close_mtm = 0.0
        intrabar_mtm = 0.0
        open_asia = open_monday = open_cb = open_nq = open_lead = 0
        jpy_close = last_jpy.close if last_jpy is not None else None
        jpy_high = last_jpy.high if last_jpy is not None else None
        jpy_low = last_jpy.low if last_jpy is not None else None
        nas_close = last_nas.close if last_nas is not None else None
        nas_high = last_nas.high if last_nas is not None else None
        nas_low = last_nas.low if last_nas is not None else None
        nq_close = last_nq.close if last_nq is not None else None
        nq_high = last_nq.high if last_nq is not None else None
        nq_low = last_nq.low if last_nq is not None else None
        for u in active:
            if u.sleeve == "asia_range":
                open_asia += 1
            elif u.sleeve == "monday_or":
                open_monday += 1
            elif u.sleeve == "nq_prior_opposed":
                open_nq += 1
            elif u.sleeve == "nas100_nq_lead":
                open_lead += 1
            else:
                open_cb += 1
            scale = (u.point_value * u.size_mult) / u.usd_div
            if u.instrument == "USDJPY":
                mark_close, mark_high, mark_low = jpy_close, jpy_high, jpy_low
            elif u.instrument == "NQ":
                mark_close, mark_high, mark_low = nq_close, nq_high, nq_low
            else:
                mark_close, mark_high, mark_low = nas_close, nas_high, nas_low
            if mark_close is None or mark_high is None or mark_low is None:
                continue
            close_mtm += (mark_close - u.entry_px) * u.sign * scale
            px = mark_low if u.sign > 0 else mark_high
            intrabar_mtm += (px - u.entry_px) * u.sign * scale

        close_eq = realized + close_mtm
        stress_eq = realized + intrabar_mtm
        close_dd = min(close_dd, close_eq - peak_close)
        intrabar_dd = min(intrabar_dd, stress_eq - peak_close)
        peak_close = max(peak_close, close_eq)

        if keep_bar_sample and (i % 5 == 0 or i == n_events):
            equity_rows.append(
                {
                    "ts": bar.ts,
                    "realized_usd": round(realized, 4),
                    "open_units": len(active),
                    "open_asia": open_asia,
                    "open_monday": open_monday,
                    "open_cb": open_cb,
                    "open_nq": open_nq,
                    "open_nas_lead": open_lead,
                    "close_equity_usd": round(close_eq, 4),
                    "intrabar_stress_equity_usd": round(stress_eq, 4),
                    "close_dd_usd": round(close_dd, 4),
                    "intrabar_stress_dd_usd": round(intrabar_dd, 4),
                }
            )

        d = bar.ts[:10]  # NY-local ISO date prefix from AuditBar.ts
        if last_day is None:
            last_day = d
        if d != last_day:
            daily_rows.append(
                {
                    "date": last_day,
                    "close_equity_usd": round(day_close, 4),
                    "intrabar_stress_equity_usd": round(day_stress, 4),
                    "close_dd_usd": round(close_dd, 4),
                    "intrabar_stress_dd_usd": round(intrabar_dd, 4),
                }
            )
            last_day = d
        day_close = close_eq
        day_stress = stress_eq

        if i % 250000 == 0:
            _progress(
                "  joint walked %d/%d bars close_eq=%.0f stress_dd=%.0f"
                % (i, n_events, close_eq, intrabar_dd)
            )

    if last_day is not None:
        daily_rows.append(
            {
                "date": last_day,
                "close_equity_usd": round(day_close, 4),
                "intrabar_stress_equity_usd": round(day_stress, 4),
                "close_dd_usd": round(close_dd, 4),
                "intrabar_stress_dd_usd": round(intrabar_dd, 4),
            }
        )

    while exit_i < len(lots_exit):
        realized += lots_exit[exit_i][1].realized
        exit_i += 1

    sleeve = _sleeve_stats(units)
    net = float(sum(u.realized_usd() for u in units))
    ns = (net / abs(intrabar_dd)) if intrabar_dd else 0.0
    return {
        "net_usd": net,
        "closed_dd_usd": close_dd,
        "intrabar_stress_dd_usd": intrabar_dd,
        "net_over_stress": ns,
        "max_open_units": max_open,
        "events": n_events,
        "equity_rows": equity_rows,
        "daily_rows": daily_rows,
        "sleeve": sleeve,
        "final_realized_usd": realized,
    }


def _money(x: float) -> str:
    return "$%.2f" % x


def write_outputs(
    *,
    lo: pd.Timestamp,
    hi: pd.Timestamp,
    result: Dict[str, object],
    all_sleeve_stats: Dict[str, dict],
) -> Tuple[Path, Path]:
    HUB.mkdir(parents=True, exist_ok=True)
    eq = pd.DataFrame(result["equity_rows"])
    daily = pd.DataFrame(result["daily_rows"])
    eq_path = HUB / "equity_curve_1m_sample.csv"
    daily_path = HUB / "equity_curve_daily.csv"
    eq.to_csv(eq_path, index=False)
    daily.to_csv(daily_path, index=False)

    sleeve = result["sleeve"]  # type: ignore[assignment]
    net = float(result["net_usd"])
    stress = float(result["intrabar_stress_dd_usd"])
    closed = float(result["closed_dd_usd"])
    ns = float(result["net_over_stress"])

    metrics = {
        "hub": str(HUB),
        "cb_scale": CB_SCALE,
        "common_window_start": lo.isoformat(),
        "common_window_end": hi.isoformat(),
        "method": "joint_1m_mtm_on_engine_fills",
        "note": (
            "Independent Engine+PaperBroker fills per sleeve; shared 1m MTM clock; "
            "NAS100 Clean Break size ×%.0f; USDJPY /%.0f USD-norm."
            % (CB_SCALE, JPY_USD)
        ),
        "net_usd": net,
        "closed_dd_usd": closed,
        "intrabar_stress_dd_usd": stress,
        "net_over_stress": ns,
        "max_open_units": int(result["max_open_units"]),
        "events": int(result["events"]),
        "sleeves": sleeve,
        "published_full_history_sleeves": all_sleeve_stats,
    }
    (HUB / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    lines = [
        "# TOP3 joint 1-minute broker portfolio (Clean Break ×10)",
        "",
        "Shared minute clock over Engine+PaperBroker fills from the three active demos.",
        "Lots stay strategy-scoped (no cross-sleeve fill interference). NAS100 Clean Break **×10**.",
        "",
        "## Common window",
        "",
        "| | |",
        "|---|---|",
        "| Start | %s |" % lo.date(),
        "| End | %s |" % hi.date(),
        "| Joint net | %s |" % _money(net),
        "| Joint close MTM DD | %s |" % _money(closed),
        "| **Joint intrabar stress DD** | **%s** |" % _money(stress),
        "| **True common-window N/S** | **%.2f** |" % ns,
        "| Max open units | %d |" % int(result["max_open_units"]),
        "| 1m events walked | %s |" % f"{int(result['events']):,}",
        "",
        "## Sleeve nets on common-window entries (CB×10)",
        "",
        "| Sleeve | Units | Trades | Net |",
        "|---|---:|---:|---:|",
    ]
    for name, label in (
        ("asia_range", "Asia Range"),
        ("monday_or", "Monday OR"),
        ("clean_break", "Clean Break ×10"),
    ):
        s = sleeve[name]  # type: ignore[index]
        lines.append(
            "| %s | %d | %d | %s |"
            % (label, int(s["units"]), int(s["trades"]), _money(float(s["net_usd"])))
        )
    lines.extend(
        [
            "",
            "## Method",
            "",
            "- Asia: `v2b_scaleout` S_3_1_3_flt fills → mark on USDJPY 1m",
            "- Monday OR: `monday_or_breakout` M2_S3_R1 skip Aug/Sep fills → mark on USDJPY 1m",
            "- Clean Break: `v2b_clean_break` trail06_m4_e2_out_be 1m-fill tape → mark on NAS100 1m, size ×10",
            "- Joint close / intrabar equity = sum of sleeve MTMs each minute (JPY÷110)",
            "",
            "Artifacts: `equity_curve_1m_sample.csv` (every 5th minute), `equity_curve_daily.csv`, `metrics.json`.",
        ]
    )
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    email = "\n".join(
        [
            "TOP3 joint 1m broker portfolio (CB×10)",
            "Hub: %s" % HUB,
            "Common window: %s → %s" % (lo.date(), hi.date()),
            "Joint net %s · stress %s · N/S %.2f" % (_money(net), _money(stress), ns),
            "Sleeve nets: Asia %s · Monday OR %s · CB×10 %s"
            % (
                _money(float(sleeve["asia_range"]["net_usd"])),  # type: ignore[index]
                _money(float(sleeve["monday_or"]["net_usd"])),  # type: ignore[index]
                _money(float(sleeve["clean_break"]["net_usd"])),  # type: ignore[index]
            ),
            "Stance: true common-window joint MTM N/S from Engine fills on a shared 1m clock.",
        ]
    )
    (HUB / "EMAIL.txt").write_text(email + "\n", encoding="utf-8")
    return eq_path, daily_path


def run(*, email: bool = False) -> Dict[str, object]:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    rid = begin_run(
        run_class="broker_like",
        variant_slug="top3_joint_1m_cb10x",
        instrument="PORTFOLIO",
        hub_path=str(HUB),
        meta={"cb_scale": CB_SCALE, "sleeves": ["asia_range", "monday_or", "clean_break"]},
    )
    try:
        _progress("Loading Engine fill units (CB×%.0f)..." % CB_SCALE)
        units_all = load_sleeve_units()
        all_stats = _sleeve_stats(units_all)
        lo, hi = _common_window(units_all)
        _progress("Common window %s → %s" % (lo, hi))
        units = _filter_units_common(units_all, lo, hi)
        _progress("Common-window entry units=%d (of %d)" % (len(units), len(units_all)))

        jpy_bars = load_usdjpy_1m(lo, hi)
        nas_bars = load_nas100_1m(lo, hi)
        _progress("Walking joint 1m MTM (%d events)..." % (len(jpy_bars) + len(nas_bars)))
        result = joint_1m_mtm(units, jpy_bars, nas_bars)
        eq_path, daily_path = write_outputs(lo=lo, hi=hi, result=result, all_sleeve_stats=all_stats)
        _progress(
            "DONE net=%s stress=%s N/S=%.2f"
            % (
                _money(float(result["net_usd"])),
                _money(float(result["intrabar_stress_dd_usd"])),
                float(result["net_over_stress"]),
            )
        )
        complete_run(
            rid,
            net_usd=float(result["net_usd"]),
            stress_dd_usd=float(result["intrabar_stress_dd_usd"]),
            close_mtm_dd_usd=float(result["closed_dd_usd"]),
            ns=float(result["net_over_stress"]),
            trades=int(sum(int(s["trades"]) for s in result["sleeve"].values())),  # type: ignore[union-attr]
            equity_curve_path=daily_path,
            meta={
                "cb_scale": CB_SCALE,
                "common_window": "%s→%s" % (lo.date(), hi.date()),
                "events": int(result["events"]),
                "eq_sample": str(eq_path),
            },
        )
        if email:
            send_email(
                subject="potions: TOP3 joint 1m portfolio (CB×10) complete",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return result
    except Exception:
        fail_run(rid, notes=traceback.format_exc()[-2000:])
        (HUB / "FAIL.txt").write_text(traceback.format_exc(), encoding="utf-8")
        if email:
            send_email(
                subject="potions: TOP3 joint 1m portfolio FAILED",
                body="Hub: %s\n\n%s" % (HUB, traceback.format_exc()[-3000:]),
            )
        raise


def main() -> None:
    ap = argparse.ArgumentParser(description="TOP3 joint 1m Engine-fill portfolio MTM (CB×10)")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    run(email=bool(args.email))


if __name__ == "__main__":
    main()
