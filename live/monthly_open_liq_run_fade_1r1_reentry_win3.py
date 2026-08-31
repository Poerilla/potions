"""Base 1:1 liq-run fade: re-entry only after a win, max 3 re-entries.

Same geometry as ``monthly_open_liq_run_fade_1r1``:

- Limit at ``p_liq``, target = month open, SL = full liq-run size (1R)
- Re-arm only after a **target (win)** exit, when price leaves open then
  **re-touches month open** (max **3** re-entries → ≤4 fills/month)
- No re-arm after stop or EOM
- First entry armed immediately after the liq extreme

Hub: ``live/state/monthly_open_atr_extension_band/liq_run_fade_1r1_reentry_win3/``
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
DEFAULT_OUT = (
    REPO
    / "live"
    / "state"
    / "monthly_open_atr_extension_band"
    / "liq_run_fade_1r1_reentry_win3"
)
NY = "America/New_York"
FEE = 1.50
QTY = 10
SLIP_TICKS = 1.0
TICK = 0.25
PV = 20.0
MAX_REENTRIES = 3  # attempts 2..4
DSR = "TRL-2026-00141"


@dataclass
class FadeTrade:
    year: int
    month: int
    attempt: int
    side: str
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
    exit_reason: str
    pnl_pts: float
    pnl_usd: float
    universe: str
    reentry: int


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


def _touches(level: float, hi: float, lo: float) -> bool:
    return lo <= level <= hi


def _left_open(side: str, month_open: float, hi: float, lo: float) -> bool:
    if side == "short":
        return lo > month_open
    return hi < month_open


def simulate_fade_month(
    *,
    bars: pd.DataFrame,
    liq: LiquidityRun,
    t1: pd.Timestamp,
    universe: str,
) -> List[FadeTrade]:
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

    after = bars[(bars.index > pd.Timestamp(liq.t_liq)) & (bars.index < t1)]
    empty = FadeTrade(
        year=liq.year,
        month=liq.month,
        attempt=0,
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
        reentry=0,
    )
    if after.empty or ext <= 0:
        return [empty]

    trades: List[FadeTrade] = []
    limit_armed = True
    wait_open_touch = False
    must_leave_open = False
    left_open = False
    n_reentries = 0  # completed re-entry fills; also gate before arming next

    in_trade = False
    fill_px = 0.0
    fill_ts = None
    attempt = 0

    def close_trade(ts, exit_px: float, reason: str) -> None:
        nonlocal in_trade, limit_armed, wait_open_touch, must_leave_open, left_open, n_reentries
        pts = (fill_px - exit_px) if side == "short" else (exit_px - fill_px)
        usd = pts * PV * QTY - 2.0 * FEE * QTY
        is_re = int(attempt > 1)
        if is_re:
            n_reentries += 1
        trades.append(
            FadeTrade(
                year=liq.year,
                month=liq.month,
                attempt=attempt,
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
                exit_reason=reason,
                pnl_pts=pts,
                pnl_usd=usd,
                universe=universe,
                reentry=is_re,
            )
        )
        in_trade = False
        limit_armed = False
        # Re-arm only after a win, and only if under max re-entries
        if reason == "target" and n_reentries < MAX_REENTRIES:
            wait_open_touch = True
            must_leave_open = True
            left_open = False
        else:
            wait_open_touch = False
            must_leave_open = False
            left_open = False

    for ts, row in after.iterrows():
        hi = float(row["high"])
        lo = float(row["low"])

        if not in_trade:
            if wait_open_touch and n_reentries < MAX_REENTRIES:
                if must_leave_open and not left_open:
                    if _left_open(side, month_open, hi, lo):
                        left_open = True
                if (left_open or not must_leave_open) and _touches(month_open, hi, lo):
                    wait_open_touch = False
                    must_leave_open = False
                    left_open = False
                    limit_armed = True

            if limit_armed:
                tagged = (side == "short" and hi >= entry_lvl) or (
                    side == "long" and lo <= entry_lvl
                )
                if tagged:
                    # Cap: attempt 1 + MAX_REENTRIES
                    if attempt >= 1 + MAX_REENTRIES:
                        limit_armed = False
                        continue
                    attempt += 1
                    in_trade = True
                    limit_armed = False
                    fill_px = _slip(side, entry_lvl, is_entry=True)
                    fill_ts = ts
                    if side == "short":
                        if hi >= stop:
                            close_trade(ts, _slip(side, stop, is_entry=False), "stop")
                            continue
                        if lo <= target:
                            close_trade(ts, _slip(side, target, is_entry=False), "target")
                            continue
                    else:
                        if lo <= stop:
                            close_trade(ts, _slip(side, stop, is_entry=False), "stop")
                            continue
                        if hi >= target:
                            close_trade(ts, _slip(side, target, is_entry=False), "target")
                            continue
            continue

        if side == "short":
            if hi >= stop:
                close_trade(ts, _slip(side, stop, is_entry=False), "stop")
                continue
            if lo <= target:
                close_trade(ts, _slip(side, target, is_entry=False), "target")
                continue
        else:
            if lo <= stop:
                close_trade(ts, _slip(side, stop, is_entry=False), "stop")
                continue
            if hi >= target:
                close_trade(ts, _slip(side, target, is_entry=False), "target")
                continue

    if in_trade:
        last = after.iloc[-1]
        close_trade(after.index[-1], _slip(side, float(last["close"]), is_entry=False), "eom")

    if not trades:
        return [empty]
    return trades


def _score(trades: Sequence[FadeTrade], *, n_months: int) -> Dict[str, float]:
    filled = [t for t in trades if t.exit_reason != "no_fill"]
    n = len(filled)
    if n == 0:
        return {
            "n_months": float(n_months),
            "n_fills": 0.0,
            "n_reentry_fills": 0.0,
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
    sd = float(nets.std(ddof=1)) if n > 1 else 0.0
    sharpe = (float(nets.mean()) / sd * np.sqrt(12.0)) if sd > 1e-9 else 0.0
    return {
        "n_months": float(n_months),
        "n_fills": float(n),
        "n_reentry_fills": float(sum(t.reentry for t in filled)),
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
        out.extend(simulate_fade_month(bars=bars_ny, liq=liq, t1=t1n, universe=universe))
    return out


def _summary_md(scores: Dict[str, Dict[str, float]], hub: Path) -> str:
    lines = [
        "# NQ liq-run fade — base 1:1 + win-only re-entry (max %d)" % MAX_REENTRIES,
        "",
        "After first **2 NY trading days**, fade largest |extension| from month open:",
        "",
        "- **Limit** at `p_liq` (qty **%d**); **target** = month open; **SL** = full 1R" % QTY,
        "- Re-arm **only after a win (target)**, on leave-open then **re-touch open**",
        "- **Max %d re-entries** (≤%d fills/month); no re-arm after stop/EOM" % (MAX_REENTRIES, 1 + MAX_REENTRIES),
        "- Path-aware 1h; 1-tick slip; fee $1.50/side; stop before target same-bar",
        "",
        "## Results",
        "",
        "| Universe | Months | Fills | Re-entries | Target | Stop | EOM | WR | Net $ | Stress $ | N/S | Sharpe |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, s in scores.items():
        lines.append(
            "| %s | %d | %d | %d | %d | %d | %d | %.1f%% | %+.0f | %.0f | %.2f | %.2f |"
            % (
                name,
                int(s["n_months"]),
                int(s["n_fills"]),
                int(s.get("n_reentry_fills") or 0),
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
            "Vs unlimited open-touch re-entry (`liq_run_fade_1r1_reentry`): all +$711k / N/S 1.78; HP +$618k / N/S 2.24.",
            "",
            "Hub: `%s`" % hub,
            "",
            "Stance: diagnostic path sim (win-only re-entry cap).",
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
        "RUN reentry=win_only max_re=%d all=%d hp=%d qty=%d"
        % (MAX_REENTRIES, len(all_keys), len(hp_keys), QTY),
    )

    trades_all = run_universe(
        bars_ny=bars_ny, win_by=win_by, month_opens=month_opens, keys=all_keys, universe="all"
    )
    trades_hp = run_universe(
        bars_ny=bars_ny, win_by=win_by, month_opens=month_opens, keys=hp_keys, universe="hp"
    )
    pd.DataFrame([asdict(t) for t in trades_all]).to_csv(output_root / "trades_all.csv", index=False)
    pd.DataFrame([asdict(t) for t in trades_hp]).to_csv(output_root / "trades_hp.csv", index=False)

    def n_months(ts: Sequence[FadeTrade]) -> int:
        return len({(t.year, t.month) for t in ts})

    scores = {
        "all_months": _score(trades_all, n_months=n_months(trades_all)),
        "hp_lookback_or": _score(trades_hp, n_months=n_months(trades_hp)),
    }
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
            variant_slug="nq_liq_run_fade_1r1_reentry_win3_%s" % uni,
            instrument="NQ",
            hub_path=str(output_root.relative_to(REPO)),
            net_usd=float(s["net_usd"]),
            stress_dd_usd=-float(s["stress"]),
            ns=float(s["ns"]),
            trades=int(s["n_fills"]),
            dsr_trial_id=DSR,
            meta={
                "universe": uni,
                "qty": QTY,
                "reentry": "win_only",
                "max_reentries": MAX_REENTRIES,
                "sl": "full_1r",
            },
            notes="1r1 base; re-arm after win only; max 3 re-entries",
        )
    if email:
        send_email(subject="potions: NQ liq-run fade 1:1 win-only reentry max3", body=summary)
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
            send_email(subject="potions: liq-run fade win3 reentry FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
