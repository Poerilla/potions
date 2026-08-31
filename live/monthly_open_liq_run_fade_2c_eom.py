"""Liquidity-run fade: 2 contracts — 1 @ month open, runner to EOM; SL stays 1R.

Base structure (after first 2 NY trading days, largest |ext| from month open):

- Limit 2 at ``p_liq``
- SL = full liq-run beyond swing for the life of the trade (no BE / half trail)
- Contract 1 target = month open (1R)
- Contract 2 = runner flat at month end (no 2R target)

Hub: ``live/state/monthly_open_atr_extension_band/liq_run_fade_2c_eom/``
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    FEATURES_CSV,
    LiquidityRun,
    _ny_ts,
    detect_liquidity_run,
    select_months,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS
from .run_ledger import log_run

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "monthly_open_atr_extension_band" / "liq_run_fade_2c_eom"
NY = "America/New_York"
FEE = 1.50
QTY_TP1 = 1
QTY_RUNNER = 1
QTY = QTY_TP1 + QTY_RUNNER
SLIP_TICKS = 1.0
TICK = 0.25
PV = 20.0
DSR = "TRL-2026-00139"


@dataclass
class FadeTrade:
    year: int
    month: int
    side: str
    liq_side: str
    month_open: float
    entry: float
    stop_init: float
    target_1r: float
    ext_pts: float
    t_arm: str
    entry_ts: str
    exit_ts: str
    exit_reason: str
    pnl_usd: float
    pnl_pts_avg: float
    tp1_hit: int
    runner_eom: int
    universe: str
    legs: str = ""


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _slip(side: str, px: float, *, is_entry: bool) -> float:
    tick = TICK * SLIP_TICKS
    if side == "long":
        return px + tick if is_entry else px - tick
    return px - tick if is_entry else px + tick


def _leg_pnl(side: str, entry: float, exit_px: float, qty: int) -> float:
    pts = (entry - exit_px) if side == "short" else (exit_px - entry)
    return pts * PV * qty - FEE * qty


def simulate_fade(
    *,
    bars: pd.DataFrame,
    liq: LiquidityRun,
    t1: pd.Timestamp,
    universe: str,
) -> FadeTrade:
    month_open = float(liq.month_open)
    p_liq = float(liq.p_liq)
    ext = float(liq.ext_pts)
    if liq.side == "up":
        side = "short"
        entry_lvl = p_liq
        target_1r = month_open
        stop_init = p_liq + ext
    else:
        side = "long"
        entry_lvl = p_liq
        target_1r = month_open
        stop_init = p_liq - ext

    after = bars[(bars.index > pd.Timestamp(liq.t_liq)) & (bars.index < t1)]
    base = FadeTrade(
        year=liq.year,
        month=liq.month,
        side=side,
        liq_side=liq.side,
        month_open=month_open,
        entry=entry_lvl,
        stop_init=stop_init,
        target_1r=target_1r,
        ext_pts=ext,
        t_arm=str(liq.t_liq),
        entry_ts="",
        exit_ts="",
        exit_reason="no_fill",
        pnl_usd=0.0,
        pnl_pts_avg=0.0,
        tp1_hit=0,
        runner_eom=0,
        universe=universe,
    )
    if after.empty or ext <= 0:
        return base

    filled = False
    fill_px = entry_lvl
    fill_ts = None
    stop = stop_init
    rem = QTY
    tp1_done = False
    pnl = 0.0
    legs: List[str] = []

    def hit_stop(hi: float, lo: float) -> bool:
        return (hi >= stop) if side == "short" else (lo <= stop)

    def hit_tp1(hi: float, lo: float) -> bool:
        return (lo <= target_1r) if side == "short" else (hi >= target_1r)

    def pack(*, ts, reason: str, exit_px: float, runner_eom: int = 0) -> FadeTrade:
        return FadeTrade(
            year=liq.year,
            month=liq.month,
            side=side,
            liq_side=liq.side,
            month_open=month_open,
            entry=fill_px,
            stop_init=stop_init,
            target_1r=target_1r,
            ext_pts=ext,
            t_arm=str(liq.t_liq),
            entry_ts=str(fill_ts),
            exit_ts=str(ts),
            exit_reason=reason,
            pnl_usd=pnl,
            pnl_pts_avg=((fill_px - exit_px) if side == "short" else (exit_px - fill_px)),
            tp1_hit=int(tp1_done),
            runner_eom=runner_eom,
            universe=universe,
            legs=";".join(legs),
        )

    for ts, row in after.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])

        if not filled:
            if side == "short" and hi >= entry_lvl:
                filled = True
                fill_px = _slip(side, entry_lvl, is_entry=True)
                fill_ts = ts
                pnl -= FEE * QTY
            elif side == "long" and lo <= entry_lvl:
                filled = True
                fill_px = _slip(side, entry_lvl, is_entry=True)
                fill_ts = ts
                pnl -= FEE * QTY
            else:
                continue

        assert filled
        # Conservative same-bar: stop before TP1; SL stays full liq-run

        if hit_stop(hi, lo):
            exit_px = _slip(side, stop, is_entry=False)
            pnl += _leg_pnl(side, fill_px, exit_px, rem)
            legs.append("stop_x%d@%.2f" % (rem, exit_px))
            reason = "stop_after_tp1" if tp1_done else "stop_full"
            return pack(ts=ts, reason=reason, exit_px=exit_px)

        if not tp1_done and hit_tp1(hi, lo):
            exit_px = _slip(side, target_1r, is_entry=False)
            pnl += _leg_pnl(side, fill_px, exit_px, QTY_TP1)
            legs.append("tp1_x%d@%.2f" % (QTY_TP1, exit_px))
            rem -= QTY_TP1
            tp1_done = True
            if rem <= 0:
                return pack(ts=ts, reason="tp1_only", exit_px=exit_px)
            # same bar: full SL still live for runner
            if hit_stop(hi, lo):
                exit_px2 = _slip(side, stop, is_entry=False)
                pnl += _leg_pnl(side, fill_px, exit_px2, rem)
                legs.append("stop_x%d@%.2f" % (rem, exit_px2))
                return pack(ts=ts, reason="tp1_stop", exit_px=exit_px2)
            continue

        # runner: no 2R — hold to EOM unless stopped

    if not filled:
        return base

    last = after.iloc[-1]
    exit_px = _slip(side, float(last["close"]), is_entry=False)
    pnl += _leg_pnl(side, fill_px, exit_px, rem)
    legs.append("eom_x%d@%.2f" % (rem, exit_px))
    if tp1_done:
        reason = "tp1_eom"
        runner_eom = 1
    else:
        reason = "eom_flat"
        runner_eom = 0
    return pack(ts=after.index[-1], reason=reason, exit_px=exit_px, runner_eom=runner_eom)


def _score(trades: Sequence[FadeTrade]) -> Dict[str, float]:
    filled = [t for t in trades if t.exit_reason != "no_fill"]
    n = len(filled)
    if n == 0:
        return {
            "n_armed": float(len(trades)),
            "n_fills": 0.0,
            "n_tp1": 0.0,
            "n_runner_eom": 0.0,
            "n_stop_full": 0.0,
            "n_stop_after_tp1": 0.0,
            "n_eom": 0.0,
            "wr": 0.0,
            "net_usd": 0.0,
            "avg_usd": 0.0,
            "stress": 0.0,
            "ns": 0.0,
            "sharpe": 0.0,
        }
    nets = np.array([t.pnl_usd for t in filled], dtype=float)
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    dd = float((eq - peak).min())
    stress = abs(dd)
    net = float(nets.sum())
    wins = int((nets > 0).sum())
    sd = float(nets.std(ddof=1)) if n > 1 else 0.0
    sharpe = (float(nets.mean()) / sd * np.sqrt(12.0)) if sd > 1e-9 else 0.0
    return {
        "n_armed": float(len(trades)),
        "n_fills": float(n),
        "n_tp1": float(sum(t.tp1_hit for t in filled)),
        "n_runner_eom": float(sum(t.runner_eom for t in filled)),
        "n_stop_full": float(sum(1 for t in filled if t.exit_reason == "stop_full")),
        "n_stop_after_tp1": float(
            sum(1 for t in filled if t.exit_reason in {"stop_after_tp1", "tp1_stop"})
        ),
        "n_eom": float(sum(1 for t in filled if "eom" in t.exit_reason)),
        "wr": wins / n,
        "net_usd": net,
        "avg_usd": float(nets.mean()),
        "stress": stress,
        "ns": (net / stress) if stress > 1e-9 else (99.0 if net > 0 else 0.0),
        "sharpe": float(sharpe),
    }


def run_universe(
    *,
    bars_ny: pd.DataFrame,
    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]],
    month_opens: Dict[Tuple[int, int], float],
    keys: Sequence[Tuple[int, int]],
    universe: str,
) -> List[FadeTrade]:
    out: List[FadeTrade] = []
    for year, month in keys:
        if (year, month) not in win_by:
            continue
        t0, t1 = win_by[(year, month)]
        t0n, t1n = _ny_ts(t0), _ny_ts(t1)
        mo = month_opens.get((year, month))
        if mo is None:
            seg = bars_ny[(bars_ny.index >= t0n) & (bars_ny.index < t1n)]
            if seg.empty:
                continue
            mo = float(seg["open"].iloc[0])
        liq = detect_liquidity_run(
            bars_1h=bars_ny,
            year=year,
            month=month,
            month_open=float(mo),
            t0=t0n,
            t1=t1n,
        )
        if liq is None:
            continue
        out.append(simulate_fade(bars=bars_ny, liq=liq, t1=t1n, universe=universe))
    return out


def _summary_md(scores: Dict[str, Dict[str, float]], hub: Path) -> str:
    lines = [
        "# NQ liq-run fade — 2 contracts (TP1@open, runner EOM, SL=full 1R)",
        "",
        "After first **2 NY trading days**, fade largest |extension| from month open:",
        "",
        "- Enter **2** at limit `p_liq`",
        "- SL = **full liq-run** beyond swing (never trailed to BE/half)",
        "- **1** off at month open",
        "- Runner **1** held to **EOM** (no 2R target)",
        "- Path-aware 1h; 1-tick slip; fee $1.50/unit/side; stop before TP1 same-bar",
        "",
        "## Results",
        "",
        "| Universe | Armed | Fills | TP1 | Runner EOM | Full stop | Stop after TP1 | WR | Net $ | Stress $ | N/S | Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in scores.items():
        lines.append(
            "| %s | %d | %d | %d | %d | %d | %d | %.1f%% | %+.0f | %.0f | %.2f | %.2f |"
            % (
                name,
                int(s["n_armed"]),
                int(s["n_fills"]),
                int(s.get("n_tp1") or 0),
                int(s.get("n_runner_eom") or 0),
                int(s.get("n_stop_full") or 0),
                int(s.get("n_stop_after_tp1") or 0),
                100.0 * float(s["wr"]),
                float(s["net_usd"]),
                float(s["stress"]),
                float(s["ns"]),
                float(s["sharpe"]),
            )
        )
    lines.extend(
        [
            "",
            "Vs 2c BE+2R (`liq_run_fade_2c_be_2r`): all-months +$120k / N/S 1.19.",
            "",
            "Hub: `%s`" % hub,
            "",
            "Stance: diagnostic path sim (full-SL + EOM runner).",
        ]
    )
    return "\n".join(lines) + "\n"


def run(*, output_root: Path, email: bool = False) -> int:
    if output_root.exists():
        import shutil

        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    spec = MARKETS["NQ"]
    bars = load_1h(spec)
    if bars.index.tz is None:
        bars.index = bars.index.tz_localize("UTC")
    bars_ny = bars.tz_convert(NY)

    win_by: Dict[Tuple[int, int], Tuple[pd.Timestamp, pd.Timestamp]] = {}
    month_opens: Dict[Tuple[int, int], float] = {}
    all_keys: List[Tuple[int, int]] = []
    for year, month, m0, m1 in month_windows(bars, None, None):
        key = (int(year), int(month))
        win_by[key] = (m0, m1)
        all_keys.append(key)
        seg = bars_ny[(bars_ny.index >= _ny_ts(m0)) & (bars_ny.index < _ny_ts(m1))]
        if not seg.empty:
            month_opens[key] = float(seg["open"].iloc[0])

    hp_keys: List[Tuple[int, int]] = []
    if FEATURES_CSV.exists():
        feats = pd.read_csv(FEATURES_CSV)
        feats = feats[feats["market"].astype(str).str.upper() == "NQ"]
        sel = select_months(feats)
        hp_keys = [(int(r.year), int(r.month)) for r in sel.itertuples(index=False)]
        for r in sel.itertuples(index=False):
            month_opens[(int(r.year), int(r.month))] = float(r.month_open)

    _progress(
        output_root,
        "RUN qty=%d tp1=%d runner=%d sl=full_1r target=eom all=%d hp=%d"
        % (QTY, QTY_TP1, QTY_RUNNER, len(all_keys), len(hp_keys)),
    )

    trades_all = run_universe(
        bars_ny=bars_ny, win_by=win_by, month_opens=month_opens, keys=all_keys, universe="all"
    )
    trades_hp = run_universe(
        bars_ny=bars_ny, win_by=win_by, month_opens=month_opens, keys=hp_keys, universe="hp"
    )
    pd.DataFrame([asdict(t) for t in trades_all]).to_csv(output_root / "trades_all.csv", index=False)
    pd.DataFrame([asdict(t) for t in trades_hp]).to_csv(output_root / "trades_hp.csv", index=False)

    scores = {"all_months": _score(trades_all), "hp_lookback_or": _score(trades_hp)}
    (output_root / "metrics.json").write_text(json.dumps(scores, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = _summary_md(scores, output_root)
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "scores": scores}, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    _progress(output_root, "DONE %s" % json.dumps(scores))

    for uni, key in (("all", "all_months"), ("hp", "hp_lookback_or")):
        s = scores[key]
        log_run(
            run_class="pandas",
            variant_slug="nq_liq_run_fade_2c_eom_%s" % uni,
            instrument="NQ",
            hub_path=str(output_root.relative_to(REPO)),
            net_usd=float(s["net_usd"]),
            stress_dd_usd=-float(s["stress"]),
            ns=float(s["ns"]),
            trades=int(s["n_fills"]),
            dsr_trial_id=DSR,
            meta={"qty": QTY, "tp1": QTY_TP1, "runner_eom": QTY_RUNNER, "sl": "full_1r", "universe": uni},
            notes="2c fade: TP1@open, runner EOM, SL=full liq-run",
        )
    if email:
        send_email(subject="potions: NQ liq-run fade 2c EOM runner", body=summary)
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        return run(output_root=args.output_root, email=args.email)
    except Exception:
        tb = traceback.format_exc()
        _progress(args.output_root, "FAILED\n" + tb)
        if args.email:
            send_email(subject="potions: liq-run fade 2c EOM FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
