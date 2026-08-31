"""Path-sim risk sweep: 2c half+open at $1k / $2k / $3k, pre/post COVID.

Uses the same 1h path engine as ``liq_run_fade_2c_half_open_r1000`` (not 1m
Engine). COVID split: months with (year, month) < 2020-03 vs >= 2020-03.
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .monthly_atr4_helpers import load_1h, month_windows
from .monthly_open_atr_extension_band_lookback_hp_charts import (
    FEATURES_CSV,
    _ny_ts,
    select_months,
)
from .monthly_open_liq_run_fade_2c_half_open_r1000 import (
    FEE,
    PV,
    QTY,
    _progress,
    _score,
    run_universe,
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
    / "liq_run_fade_2c_half_open_risk_sweep"
)
NY = "America/New_York"
RISKS = (1000.0, 2000.0, 3000.0)
COVID_CUT = (2020, 3)  # months >= Mar 2020 = post
DSR = "TRL-2026-00147"


def _split(trades, *, post: bool):
    out = []
    for t in trades:
        key = (int(t.year), int(t.month))
        is_post = key >= COVID_CUT
        if is_post == post:
            out.append(t)
    return out


def run(*, output_root: Path, email: bool = False, risks: Sequence[float] = RISKS) -> int:
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

    table_rows = []
    metrics: Dict[str, dict] = {}

    for risk in risks:
        stop_pts = float(risk) / (QTY * PV)
        _progress(output_root, "RISK $%.0f stop_pts=%.2f" % (risk, stop_pts))
        trades_all = run_universe(
            bars_ny=bars_ny,
            win_by=win_by,
            month_opens=month_opens,
            keys=all_keys,
            universe="all",
            stop_pts=stop_pts,
        )
        trades_hp = run_universe(
            bars_ny=bars_ny,
            win_by=win_by,
            month_opens=month_opens,
            keys=hp_keys,
            universe="hp",
            stop_pts=stop_pts,
        )
        slug = "r%.0f" % risk
        pd.DataFrame([asdict(t) for t in trades_all]).to_csv(
            output_root / ("trades_all_%s.csv" % slug), index=False
        )
        pd.DataFrame([asdict(t) for t in trades_hp]).to_csv(
            output_root / ("trades_hp_%s.csv" % slug), index=False
        )

        for uni_name, trades in (("all", trades_all), ("hp", trades_hp)):
            for era_name, era_trades in (
                ("full", trades),
                ("pre_covid", _split(trades, post=False)),
                ("post_covid", _split(trades, post=True)),
            ):
                s = _score(era_trades)
                key = "%s_%s_%s" % (slug, uni_name, era_name)
                metrics[key] = {
                    **s,
                    "risk_usd": float(risk),
                    "stop_pts": stop_pts,
                    "universe": uni_name,
                    "era": era_name,
                }
                table_rows.append(
                    {
                        "risk_usd": risk,
                        "stop_pts": stop_pts,
                        "universe": uni_name,
                        "era": era_name,
                        "fills": int(s["n_fills"]),
                        "half": int(s.get("n_half") or 0),
                        "open": int(s.get("n_open") or 0),
                        "stop": int(s.get("n_stop") or 0),
                        "wr": float(s["wr"]),
                        "net_usd": float(s["net_usd"]),
                        "stress": float(s["stress"]),
                        "ns": float(s["ns"]),
                        "sharpe": float(s["sharpe"]),
                        "avg_usd": float(s["avg_usd"]),
                    }
                )

    df = pd.DataFrame(table_rows)
    df.to_csv(output_root / "risk_era_table.csv", index=False)
    (output_root / "metrics.json").write_text(
        json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    lines = [
        "# NQ 2c half+open — risk sweep $1k / $2k / $3k (1h path)",
        "",
        "- Same structure as `liq_run_fade_2c_half_open_r1000` (not 1m broker)",
        "- SL risk $R → stop_pts = R / (2 × $20)",
        "- COVID cut: **pre** = months before 2020-03; **post** = 2020-03 onward",
        "",
        "## HP lookback OR",
        "",
        "| Risk $ | Era | Fills | Half | Open | Stop | WR | Net $ | Stress $ | N/S | Avg $ |",
        "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    hp = df[df["universe"] == "hp"].sort_values(["risk_usd", "era"])
    for r in hp.itertuples(index=False):
        lines.append(
            "| %.0f | %s | %d | %d | %d | %d | %.0f%% | %+.0f | %.0f | %.2f | %+.0f |"
            % (
                r.risk_usd,
                r.era,
                r.fills,
                r.half,
                r.open,
                r.stop,
                100 * r.wr,
                r.net_usd,
                r.stress,
                r.ns,
                r.avg_usd,
            )
        )
    lines.extend(
        [
            "",
            "## All months",
            "",
            "| Risk $ | Era | Fills | Half | Open | Stop | WR | Net $ | Stress $ | N/S | Avg $ |",
            "|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    am = df[df["universe"] == "all"].sort_values(["risk_usd", "era"])
    for r in am.itertuples(index=False):
        lines.append(
            "| %.0f | %s | %d | %d | %d | %d | %.0f%% | %+.0f | %.0f | %.2f | %+.0f |"
            % (
                r.risk_usd,
                r.era,
                r.fills,
                r.half,
                r.open,
                r.stop,
                100 * r.wr,
                r.net_usd,
                r.stress,
                r.ns,
                r.avg_usd,
            )
        )

    # quick stance from HP post-covid N/S by risk
    post_hp = df[(df["universe"] == "hp") & (df["era"] == "post_covid")].sort_values("ns", ascending=False)
    best = post_hp.iloc[0] if len(post_hp) else None
    stance = "path diagnostic only — no 1m broker yet for this book."
    if best is not None:
        stance = (
            "HP post-COVID best N/S among {1,2,3}k: **$%.0f** (N/S %.2f, net %+.0f). "
            % (best.risk_usd, best.ns, best.net_usd)
            + stance
        )
    lines.extend(["", "Hub: `%s`" % output_root, "", "Stance: %s" % stance, ""])
    summary = "\n".join(lines)
    (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
    (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
    (output_root / "RUN_COMPLETE.json").write_text(
        json.dumps({"ok": True, "n_rows": len(df)}, indent=2) + "\n", encoding="utf-8"
    )
    _progress(output_root, "DONE rows=%d" % len(df))

    for r in df[(df["universe"] == "hp") & (df["era"] == "full")].itertuples(index=False):
        log_run(
            run_class="pandas",
            variant_slug="nq_liq_2c_half_open_r%.0f_hp" % r.risk_usd,
            instrument="NQ",
            hub_path=str(output_root.relative_to(REPO)),
            net_usd=float(r.net_usd),
            stress_dd_usd=-float(r.stress),
            ns=float(r.ns),
            trades=int(r.fills),
            dsr_trial_id=DSR,
            meta={"risk_usd": float(r.risk_usd), "era": "full", "universe": "hp"},
            notes="2c half+open risk sweep path sim",
        )
    if email:
        send_email(subject="potions: NQ 2c half+open risk sweep $1/2/3k", body=summary)
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
            send_email(subject="potions: 2c risk sweep FAILED", body=tb[-4000:])
        raise


if __name__ == "__main__":
    raise SystemExit(main())
