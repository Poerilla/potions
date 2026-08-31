"""Base structure: fade 2-day liquidity-run swing → month open (1:1).

After the first two full NY trading days, take the largest |extension| from
month open as the liquidity run. Fade that swing:

- Limit at ``p_liq`` (liq swing)
- Target = month open
- Stop = liq-run size beyond the swing (1R = extension distance)

Hub: ``live/state/monthly_open_atr_extension_band/liq_run_fade_1r1/``

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.monthly_open_liq_run_fade_1r1 --email
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
DEFAULT_OUT = REPO / "live" / "state" / "monthly_open_atr_extension_band" / "liq_run_fade_1r1"
NY = "America/New_York"
FEE = 1.50
QTY = 10
SLIP_TICKS = 1.0
TICK = 0.25
PV = 20.0  # NQ $/pt
DSR = "TRL-2026-00136"


@dataclass
class FadeTrade:
    year: int
    month: int
    side: str  # long|short
    liq_side: str
    month_open: float
    entry: float
    stop: float
    target: float
    ext_pts: float
    t_arm: str
    entry_ts: str
    exit_ts: str
    exit_px: float
    exit_reason: str  # target|stop|eom|no_fill
    pnl_pts: float
    pnl_usd: float
    universe: str


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _slip(side: str, px: float, *, is_entry: bool) -> float:
    """1-tick adverse slip."""
    tick = TICK * SLIP_TICKS
    if side == "long":
        return px + tick if is_entry else px - tick
    return px - tick if is_entry else px + tick


def simulate_fade(
    *,
    bars: pd.DataFrame,
    liq: LiquidityRun,
    t1: pd.Timestamp,
    universe: str,
) -> FadeTrade:
    """Path-aware 1h sim after liq extreme: limit at p_liq, 1:1 to month open."""
    month_open = float(liq.month_open)
    p_liq = float(liq.p_liq)
    ext = float(liq.ext_pts)
    if liq.side == "up":
        side = "short"
        entry_lvl = p_liq
        target = month_open
        stop = p_liq + ext
    else:
        side = "long"
        entry_lvl = p_liq
        target = month_open
        stop = p_liq - ext

    # Arm after the bar that printed the extreme (no same-bar fill).
    after = bars[(bars.index > pd.Timestamp(liq.t_liq)) & (bars.index < t1)]
    base = FadeTrade(
        year=liq.year,
        month=liq.month,
        side=side,
        liq_side=liq.side,
        month_open=month_open,
        entry=entry_lvl,
        stop=stop,
        target=target,
        ext_pts=ext,
        t_arm=str(liq.t_liq),
        entry_ts="",
        exit_ts="",
        exit_px=0.0,
        exit_reason="no_fill",
        pnl_pts=0.0,
        pnl_usd=0.0,
        universe=universe,
    )
    if after.empty or ext <= 0:
        return base

    filled = False
    fill_px = entry_lvl
    fill_ts = None
    for ts, row in after.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])
        if not filled:
            if side == "short" and hi >= entry_lvl:
                filled = True
                fill_px = _slip(side, entry_lvl, is_entry=True)
                fill_ts = ts
                # same-bar exit after fill: stop before target (conservative)
                if hi >= stop:
                    exit_px = _slip(side, stop, is_entry=False)
                    pts = fill_px - exit_px
                    usd = pts * PV * QTY - 2.0 * FEE * QTY
                    return FadeTrade(
                        year=liq.year,
                        month=liq.month,
                        side=side,
                        liq_side=liq.side,
                        month_open=month_open,
                        entry=fill_px,
                        stop=stop,
                        target=target,
                        ext_pts=ext,
                        t_arm=str(liq.t_liq),
                        entry_ts=str(ts),
                        exit_ts=str(ts),
                        exit_px=exit_px,
                        exit_reason="stop",
                        pnl_pts=pts,
                        pnl_usd=usd,
                        universe=universe,
                    )
                if lo <= target:
                    exit_px = _slip(side, target, is_entry=False)
                    pts = fill_px - exit_px
                    usd = pts * PV * QTY - 2.0 * FEE * QTY
                    return FadeTrade(
                        year=liq.year,
                        month=liq.month,
                        side=side,
                        liq_side=liq.side,
                        month_open=month_open,
                        entry=fill_px,
                        stop=stop,
                        target=target,
                        ext_pts=ext,
                        t_arm=str(liq.t_liq),
                        entry_ts=str(ts),
                        exit_ts=str(ts),
                        exit_px=exit_px,
                        exit_reason="target",
                        pnl_pts=pts,
                        pnl_usd=usd,
                        universe=universe,
                    )
                continue
            if side == "long" and lo <= entry_lvl:
                filled = True
                fill_px = _slip(side, entry_lvl, is_entry=True)
                fill_ts = ts
                if lo <= stop:
                    exit_px = _slip(side, stop, is_entry=False)
                    pts = exit_px - fill_px
                    usd = pts * PV * QTY - 2.0 * FEE * QTY
                    return FadeTrade(
                        year=liq.year,
                        month=liq.month,
                        side=side,
                        liq_side=liq.side,
                        month_open=month_open,
                        entry=fill_px,
                        stop=stop,
                        target=target,
                        ext_pts=ext,
                        t_arm=str(liq.t_liq),
                        entry_ts=str(ts),
                        exit_ts=str(ts),
                        exit_px=exit_px,
                        exit_reason="stop",
                        pnl_pts=pts,
                        pnl_usd=usd,
                        universe=universe,
                    )
                if hi >= target:
                    exit_px = _slip(side, target, is_entry=False)
                    pts = exit_px - fill_px
                    usd = pts * PV * QTY - 2.0 * FEE * QTY
                    return FadeTrade(
                        year=liq.year,
                        month=liq.month,
                        side=side,
                        liq_side=liq.side,
                        month_open=month_open,
                        entry=fill_px,
                        stop=stop,
                        target=target,
                        ext_pts=ext,
                        t_arm=str(liq.t_liq),
                        entry_ts=str(ts),
                        exit_ts=str(ts),
                        exit_px=exit_px,
                        exit_reason="target",
                        pnl_pts=pts,
                        pnl_usd=usd,
                        universe=universe,
                    )
                continue
            continue

        # In trade
        if side == "short":
            if hi >= stop:
                exit_px = _slip(side, stop, is_entry=False)
                pts = fill_px - exit_px
                usd = pts * PV * QTY - 2.0 * FEE * QTY
                return FadeTrade(
                    year=liq.year,
                    month=liq.month,
                    side=side,
                    liq_side=liq.side,
                    month_open=month_open,
                    entry=fill_px,
                    stop=stop,
                    target=target,
                    ext_pts=ext,
                    t_arm=str(liq.t_liq),
                    entry_ts=str(fill_ts),
                    exit_ts=str(ts),
                    exit_px=exit_px,
                    exit_reason="stop",
                    pnl_pts=pts,
                    pnl_usd=usd,
                    universe=universe,
                )
            if lo <= target:
                exit_px = _slip(side, target, is_entry=False)
                pts = fill_px - exit_px
                usd = pts * PV * QTY - 2.0 * FEE * QTY
                return FadeTrade(
                    year=liq.year,
                    month=liq.month,
                    side=side,
                    liq_side=liq.side,
                    month_open=month_open,
                    entry=fill_px,
                    stop=stop,
                    target=target,
                    ext_pts=ext,
                    t_arm=str(liq.t_liq),
                    entry_ts=str(fill_ts),
                    exit_ts=str(ts),
                    exit_px=exit_px,
                    exit_reason="target",
                    pnl_pts=pts,
                    pnl_usd=usd,
                    universe=universe,
                )
        else:
            if lo <= stop:
                exit_px = _slip(side, stop, is_entry=False)
                pts = exit_px - fill_px
                usd = pts * PV * QTY - 2.0 * FEE * QTY
                return FadeTrade(
                    year=liq.year,
                    month=liq.month,
                    side=side,
                    liq_side=liq.side,
                    month_open=month_open,
                    entry=fill_px,
                    stop=stop,
                    target=target,
                    ext_pts=ext,
                    t_arm=str(liq.t_liq),
                    entry_ts=str(fill_ts),
                    exit_ts=str(ts),
                    exit_px=exit_px,
                    exit_reason="stop",
                    pnl_pts=pts,
                    pnl_usd=usd,
                    universe=universe,
                )
            if hi >= target:
                exit_px = _slip(side, target, is_entry=False)
                pts = exit_px - fill_px
                usd = pts * PV * QTY - 2.0 * FEE * QTY
                return FadeTrade(
                    year=liq.year,
                    month=liq.month,
                    side=side,
                    liq_side=liq.side,
                    month_open=month_open,
                    entry=fill_px,
                    stop=stop,
                    target=target,
                    ext_pts=ext,
                    t_arm=str(liq.t_liq),
                    entry_ts=str(fill_ts),
                    exit_ts=str(ts),
                    exit_px=exit_px,
                    exit_reason="target",
                    pnl_pts=pts,
                    pnl_usd=usd,
                    universe=universe,
                )

    if not filled:
        return base

    # EOM flatten at last close
    last = after.iloc[-1]
    exit_px = _slip(side, float(last["close"]), is_entry=False)
    pts = (fill_px - exit_px) if side == "short" else (exit_px - fill_px)
    usd = pts * PV * QTY - 2.0 * FEE * QTY
    return FadeTrade(
        year=liq.year,
        month=liq.month,
        side=side,
        liq_side=liq.side,
        month_open=month_open,
        entry=fill_px,
        stop=stop,
        target=target,
        ext_pts=ext,
        t_arm=str(liq.t_liq),
        entry_ts=str(fill_ts),
        exit_ts=str(after.index[-1]),
        exit_px=exit_px,
        exit_reason="eom",
        pnl_pts=pts,
        pnl_usd=usd,
        universe=universe,
    )


def _score(trades: Sequence[FadeTrade]) -> Dict[str, float]:
    filled = [t for t in trades if t.exit_reason != "no_fill"]
    n = len(filled)
    if n == 0:
        return {
            "n_armed": float(len(trades)),
            "n_fills": 0.0,
            "n_target": 0.0,
            "n_stop": 0.0,
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
    # crude monthly sharpe
    sd = float(nets.std(ddof=1)) if n > 1 else 0.0
    sharpe = (float(nets.mean()) / sd * np.sqrt(12.0)) if sd > 1e-9 else 0.0
    return {
        "n_armed": float(len(trades)),
        "n_fills": float(n),
        "n_target": float(sum(1 for t in filled if t.exit_reason == "target")),
        "n_stop": float(sum(1 for t in filled if t.exit_reason == "stop")),
        "n_eom": float(sum(1 for t in filled if t.exit_reason == "eom")),
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
            # fallback: first bar open
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
        "# NQ liquidity-run fade — base structure (1:1)",
        "",
        "After first **2 NY trading days**, fade the largest |extension| from month open:",
        "",
        "- **Limit** at liq swing `p_liq`",
        "- **Target** = month open",
        "- **Stop** = one liq-run beyond the swing (1R = extension)",
        "- Path-aware **1h** OHLC; 1-tick adverse slip; fee $1.50/side; qty **%d**" % QTY,
        "- Same-bar: stop before target",
        "",
        "## Results",
        "",
        "| Universe | Armed | Fills | Target | Stop | EOM | WR | Net $ | Stress $ | N/S | Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in scores.items():
        lines.append(
            "| %s | %d | %d | %d | %d | %d | %.1f%% | %+.0f | %.0f | %.2f | %.2f |"
            % (
                name,
                int(s["n_armed"]),
                int(s["n_fills"]),
                int(s["n_target"]),
                int(s["n_stop"]),
                int(s["n_eom"]),
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
            "Hub: `%s`" % hub,
            "",
            "Stance: **base structure** — diagnostic path sim (not Engine+PaperBroker promote gate).",
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

    # HP universe from lookback features
    hp_keys: List[Tuple[int, int]] = []
    if FEATURES_CSV.exists():
        feats = pd.read_csv(FEATURES_CSV)
        feats = feats[feats["market"].astype(str).str.upper() == "NQ"]
        sel = select_months(feats)
        hp_keys = [(int(r.year), int(r.month)) for r in sel.itertuples(index=False)]
        # prefer month_open from features when present
        for r in sel.itertuples(index=False):
            month_opens[(int(r.year), int(r.month))] = float(r.month_open)

    _progress(output_root, "RUN all_months=%d hp_months=%d" % (len(all_keys), len(hp_keys)))

    trades_all = run_universe(
        bars_ny=bars_ny, win_by=win_by, month_opens=month_opens, keys=all_keys, universe="all"
    )
    trades_hp = run_universe(
        bars_ny=bars_ny, win_by=win_by, month_opens=month_opens, keys=hp_keys, universe="hp"
    )

    pd.DataFrame([asdict(t) for t in trades_all]).to_csv(output_root / "trades_all.csv", index=False)
    pd.DataFrame([asdict(t) for t in trades_hp]).to_csv(output_root / "trades_hp.csv", index=False)

    scores = {
        "all_months": _score(trades_all),
        "hp_lookback_or": _score(trades_hp),
    }
    (output_root / "metrics.json").write_text(json.dumps(scores, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    summary = _summary_md(scores, output_root)
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "scores": scores}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _progress(output_root, "DONE %s" % json.dumps(scores))

    for uni, trades in (("all", trades_all), ("hp", trades_hp)):
        s = scores["all_months" if uni == "all" else "hp_lookback_or"]
        log_run(
            run_class="pandas",
            variant_slug="nq_liq_run_fade_1r1_%s" % uni,
            instrument="NQ",
            hub_path=str(output_root.relative_to(REPO)),
            net_usd=float(s["net_usd"]),
            stress_dd_usd=-float(s["stress"]),
            ns=float(s["ns"]),
            trades=int(s["n_fills"]),
            dsr_trial_id=DSR,
            meta={"universe": uni, "qty": QTY, "structure": "fade_liq_swing_1r1"},
            notes="1h path sim base structure; limit@liq → open; SL=1R",
        )

    if email:
        send_email(subject="potions: NQ liq-run fade 1:1 base structure", body=summary)
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
            send_email(subject="potions: liq-run fade 1:1 FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
