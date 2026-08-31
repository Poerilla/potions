"""Broker-like Engine+PaperBroker: daily quarterly range honest breakout.

Close outside prior-quarter range → market 8 (next open). SL fixed at range
mid (halfway). Scale 2 lots every 0.2× prior width (0.2/0.4/0.6/0.8). No BE.
Multiple breakouts per quarter while flat; flatten at quarter end.

Default hub: ``live/state/nq_quarterly_range_breakout_broker/``
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine, bars_from_csv
from .models import StrategyInstance, as_row
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .store import FlatFileStore

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "nq_quarterly_range_breakout_broker"
DEFAULT_DAILY = REPO / "nq" / "nq_daily.csv"

FEE = 1.50
ENTRY_QTY = 8
SCALE_QTY = 2
SCALE_STEP = 0.2

# Fallback specs when not already registered.
_SPEC = {
    "NQ": {"pv": 20.0, "tick": 0.25},
    "MNQ": {"pv": 2.0, "tick": 0.25},
    "ES": {"pv": 50.0, "tick": 0.25},
    "MES": {"pv": 5.0, "tick": 0.25},
    "YM": {"pv": 5.0, "tick": 1.0},
    "MYM": {"pv": 0.5, "tick": 1.0},
}


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def run(
    *,
    output_root: Path,
    daily_path: Path,
    instrument: str = "NQ",
    force: bool = True,
    slippage_ticks: float = 1.0,
    email: bool = False,
    allowed_sides: Optional[Sequence[str]] = None,
    entry_qty: int = ENTRY_QTY,
    scale_qty: int = SCALE_QTY,
    sidecar_scale_qty: Optional[int] = None,
    require_mor_dirs: Optional[Sequence[str]] = None,
    require_yor_dirs: Optional[Sequence[str]] = None,
    require_w_atr_aligns: Optional[Sequence[str]] = None,
    enable_mid_sidecar: bool = False,
    sidecar_min_width_quantile: float = 0.75,
    sidecar_min_hist: int = 8,
    sidecar_min_prior_width: float = 0.0,
    sidecar_eoq: str = "be_carry",
    sidecar_r_targets: Optional[Sequence[float]] = None,
) -> int:
    instrument = str(instrument).upper()
    sides: List[str]
    if allowed_sides:
        sides = [str(s).strip().lower() for s in allowed_sides if str(s).strip()]
    else:
        sides = ["long", "short"]
    if not sides:
        sides = ["long", "short"]
    mor_dirs: List[str] = []
    if require_mor_dirs:
        for raw in require_mor_dirs:
            key = str(raw).strip().lower()
            if not key:
                continue
            if not key.startswith("mor_"):
                key = "mor_%s" % key
            mor_dirs.append(key)
    yor_dirs: List[str] = []
    if require_yor_dirs:
        for raw in require_yor_dirs:
            key = str(raw).strip().lower()
            if not key:
                continue
            if not key.startswith("yor_"):
                key = "yor_%s" % key
            yor_dirs.append(key)
    w_atr_aligns: List[str] = []
    if require_w_atr_aligns:
        for raw in require_w_atr_aligns:
            key = str(raw).strip().lower()
            if not key:
                continue
            if not key.startswith("w_atr_"):
                key = "w_atr_%s" % key
            w_atr_aligns.append(key)

    spec = _SPEC.get(instrument, {"pv": POINT_VALUES.get(instrument, 20.0), "tick": 0.25})
    tick = float(DEFAULT_TICK_SIZE.get(instrument, spec["tick"]))
    pv = float(POINT_VALUES.get(instrument, spec["pv"]))

    if force and output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)

    strategy_id = "%s_quarterly_range_breakout" % instrument.lower()
    if sides == ["long"]:
        strategy_id = "%s_quarterly_range_breakout_long_only" % instrument.lower()
    gate_bits = mor_dirs + yor_dirs + w_atr_aligns
    if gate_bits:
        strategy_id = "%s_%s" % (strategy_id, "_".join(gate_bits))
    main_id = strategy_id
    sidecar_id = "%s_sidecar" % strategy_id if enable_mid_sidecar else ""
    state_root = output_root / "states" / ("book" if enable_mid_sidecar else strategy_id)
    audits_root = output_root / "audits"
    state_root.mkdir(parents=True, exist_ok=True)
    eoq_mode = str(sidecar_eoq or "be_carry").strip().lower() or "be_carry"
    if eoq_mode not in {"be_carry", "flatten"}:
        eoq_mode = "be_carry"
    r_targets = [float(x) for x in (sidecar_r_targets or [1.0, 2.0, 3.0, 4.0])]
    if not r_targets:
        r_targets = [1.0, 2.0, 3.0, 4.0]
    main_scale = int(scale_qty) if int(scale_qty) > 0 else SCALE_QTY
    sc_scale = (
        int(sidecar_scale_qty)
        if sidecar_scale_qty is not None and int(sidecar_scale_qty) > 0
        else main_scale
    )

    write_run_manifest(
        output_root,
        data_inputs=[daily_path],
        strategy_config={
            "strategy_type": "quarterly_range_breakout",
            "version": "v2_sidecar_be_carry" if enable_mid_sidecar else "v2_honest",
            "instrument": instrument,
            "entry_qty": int(entry_qty),
            "scale_qty": main_scale,
            "sidecar_scale_qty": sc_scale,
            "scale_step_width_mult": SCALE_STEP,
            "stop": "prior_range_mid",
            "be": False,
            "allowed_sides": sides,
            "require_mor_dirs": mor_dirs,
            "require_yor_dirs": yor_dirs,
            "require_w_atr_aligns": w_atr_aligns,
            "enable_mid_sidecar": bool(enable_mid_sidecar),
            "sidecar_min_width_quantile": float(sidecar_min_width_quantile),
            "sidecar_min_hist": int(sidecar_min_hist),
            "sidecar_min_prior_width": float(sidecar_min_prior_width),
            "sidecar_r_targets": r_targets,
            "sidecar_eoq": eoq_mode,
        },
        broker_realism_config={"slippage_ticks": slippage_ticks, "fee_per_unit": FEE},
        extra={
            "notes": (
                "%s daily honest quarterly range breakout (mid SL, 2@0.2W ladder, "
                "sides=%s, mor=%s, yor=%s, w_atr=%s, sidecar=%s)"
                % (
                    instrument,
                    ",".join(sides),
                    ",".join(mor_dirs) or "none",
                    ",".join(yor_dirs) or "none",
                    ",".join(w_atr_aligns) or "none",
                    (
                        "separate_%s_%sR"
                        % (eoq_mode, "-".join(str(int(x)) if float(x).is_integer() else str(x) for x in r_targets))
                        if enable_mid_sidecar
                        else "off"
                    ),
                )
            )
        },
    )

    POINT_VALUES[instrument] = pv
    DEFAULT_TICK_SIZE[instrument] = tick

    try:
        bars = bars_from_csv(daily_path, instrument, "D", source=str(daily_path))
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        main_payload = {
            "tick_size": tick,
            "entry_qty": int(entry_qty),
            "scale_qty": main_scale,
            "scale_step_width_mult": SCALE_STEP,
            "timeframe": "D",
            "suppress_alerts": True,
            "allowed_sides": sides,
            "require_mor_dirs": mor_dirs,
            "require_yor_dirs": yor_dirs,
            "require_w_atr_aligns": w_atr_aligns,
            "mode": "main",
            "enable_mid_sidecar": bool(enable_mid_sidecar),
            "sidecar_min_width_quantile": float(sidecar_min_width_quantile),
            "sidecar_min_hist": int(sidecar_min_hist),
            "sidecar_min_prior_width": float(sidecar_min_prior_width),
        }
        instances = [
            as_row(
                StrategyInstance(
                    strategy_id=main_id,
                    strategy_type="quarterly_range_breakout",
                    version="v2_sidecar_be_carry" if enable_mid_sidecar else "v2",
                    instrument=instrument,
                    broker_instrument=instrument,
                    account_mode="paper",
                    enabled=True,
                    timeframes="D",
                    max_contracts=int(entry_qty),
                    max_open_orders=32,
                    config_json=json.dumps(main_payload, sort_keys=True),
                )
            )
        ]
        if enable_mid_sidecar:
            sc_payload = {
                "tick_size": tick,
                "entry_qty": int(entry_qty),
                "scale_qty": sc_scale,
                "timeframe": "D",
                "suppress_alerts": True,
                "mode": "sidecar_only",
                "main_strategy_id": main_id,
                "enable_mid_sidecar": True,
                "sidecar_r_targets": r_targets,
                "sidecar_eoq": eoq_mode,
            }
            instances.append(
                as_row(
                    StrategyInstance(
                        strategy_id=sidecar_id,
                        strategy_type="quarterly_range_breakout",
                        version="v2_sidecar_be_carry",
                        instrument=instrument,
                        broker_instrument=instrument,
                        account_mode="paper",
                        enabled=True,
                        timeframes="D",
                        max_contracts=int(entry_qty),
                        max_open_orders=32,
                        config_json=json.dumps(sc_payload, sort_keys=True),
                    )
                )
            )
        store.write_table("strategy_instances", instances)
        engine = Engine(
            store=store,
            slippage_ticks=slippage_ticks,
            persist_health=False,
            tick_size={instrument: tick},
        )
        _progress(
            output_root,
            "RUN %s bars=%d instrument=%s sides=%s sidecar=%s"
            % (
                main_id,
                len(bars),
                instrument,
                ",".join(sides),
                sidecar_id or "off",
            ),
        )
        engine.replay_bars(bars)
        store.flush_tables()
        if bars:
            generate_market_close_report(store, bars[-1].ts[:10])

        bar_path = state_root / "bars" / ("%s_D.csv" % instrument)
        replay_bars = read_bars(bar_path, "ts")
        end_ts = replay_bars[-1].ts if replay_bars else ""
        end_px = replay_bars[-1].close if replay_bars else None

        def _audit_one(sid: str, name: str):
            units = units_from_live_fills(
                state_root / "fills.csv",
                sid,
                end_ts,
                end_px,
            )
            return audit_units(
                name=name,
                slug=sid,
                source=state_root / "fills.csv",
                bar_source=bar_path,
                bars=replay_bars,
                units=units,
                instrument=instrument,
                notes="sidecar book" if "sidecar" in sid else "main book",
                output_root=audits_root,
                fee_per_unit=FEE,
            )

        audit_main = _audit_one(main_id, "%s quarterly main" % instrument)
        audit_sc = (
            _audit_one(sidecar_id, "%s quarterly sidecar" % instrument)
            if enable_mid_sidecar
            else None
        )
        net = float(audit_main.net_usd) + (float(audit_sc.net_usd) if audit_sc else 0.0)
        stress = min(
            float(audit_main.intrabar_mtm_dd_usd),
            float(audit_sc.intrabar_mtm_dd_usd) if audit_sc else 0.0,
        )
        # Prefer combined equity stress from summing is hard; use worse of the two.
        if audit_sc is not None:
            # Approximate combined stress as sum of stresses (conservative if correlated).
            stress = float(audit_main.intrabar_mtm_dd_usd) + float(audit_sc.intrabar_mtm_dd_usd)
        closed = float(audit_main.close_mtm_dd_usd) + (
            float(audit_sc.close_mtm_dd_usd) if audit_sc else 0.0
        )
        trades = int(audit_main.trades) + (int(audit_sc.trades) if audit_sc else 0)
        units_n = int(audit_main.units) + (int(audit_sc.units) if audit_sc else 0)
        ns = float(net) / abs(float(stress)) if abs(float(stress)) > 1e-9 else 0.0
        row: Dict[str, object] = {
            "slug": main_id,
            "instrument": instrument,
            "allowed_sides": ",".join(sides),
            "enable_mid_sidecar": bool(enable_mid_sidecar),
            "bars": len(replay_bars),
            "units": units_n,
            "trades": trades,
            "net_usd": net,
            "main_net_usd": audit_main.net_usd,
            "sidecar_net_usd": audit_sc.net_usd if audit_sc else 0.0,
            "closed_dd": closed,
            "stress_dd": stress,
            "win_units": int(audit_main.win_units)
            + (int(audit_sc.win_units) if audit_sc else 0),
            "loss_units": int(audit_main.loss_units)
            + (int(audit_sc.loss_units) if audit_sc else 0),
            "ns": ns,
        }
        with (output_root / "summary.csv").open("w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerow(row)

        exit_mix = ""
        fills_path = state_root / "fills.csv"
        if fills_path.exists():
            import pandas as pd

            fdf = pd.read_csv(fills_path)
            if "reason" in fdf.columns:
                vc = fdf["reason"].value_counts()
                exit_mix = "\n".join("- `%s`: **%d**" % (k, int(v)) for k, v in vc.items())

        r_label = "–".join(
            ("%g" % float(x) for x in r_targets)
        )
        eoq_label = (
            "**BE carry** (no flatten)"
            if eoq_mode == "be_carry"
            else "**flatten at EOQ**"
        )
        sidecar_line = (
            "- **Mid-stop sidecar (separate position):** large prior width (causal p%.0f); "
            "same risk magnitude; targets **%sR**; EOQ → %s; "
            "runs independently of main (no blocking / no yield)."
            % (100 * float(sidecar_min_width_quantile), r_label, eoq_label)
            if enable_mid_sidecar
            else "- **Mid-stop sidecar:** off"
        )
        lines = [
            "# %s quarterly range honest breakout (broker-like)" % instrument,
            "",
            "Engine + PaperBroker on **%s daily**." % instrument,
            "",
            "## Rules",
            "",
            "- Breakout = daily **close** outside prior-quarter H/L → market **%d**."
            % int(entry_qty),
            "- **Allowed sides:** %s" % (", ".join(sides)),
            sidecar_line,
            "- Main **SL** = prior mid; scale **2** @ 0.2W; EOQ flatten main.",
            "",
            f"- Slippage: **{slippage_ticks:g}** tick · fee **${FEE:.2f}**/unit · "
            f"{instrument} ${pv:g}/pt",
            "",
            "## Results",
            "",
            f"- Combined net: **${net:,.2f}** (main ${float(audit_main.net_usd):,.2f}"
            + (
                " + sidecar $%s" % ("{:,.2f}".format(float(audit_sc.net_usd)))
                if audit_sc
                else ""
            )
            + ")",
            f"- Trades: **{trades}** (main {audit_main.trades}"
            + (f" + sidecar {audit_sc.trades}" if audit_sc else "")
            + ")",
            f"- Stress DD (sum): **${stress:,.2f}**",
            f"- Net/|stress|: **{ns:.2f}**",
            "",
            "## Fill reasons",
            "",
            exit_mix or "_n/a_",
            "",
        ]
        (output_root / "SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")
        email_body = "\n".join(
            [
                "%s quarterly breakout + sidecar BE-carry complete." % instrument,
                "",
                "Hub: %s" % output_root,
                "Sidecar: separate position, same-magnitude SL, %sR, EOQ→%s."
                % (r_label, eoq_mode),
                "Combined net: $%.2f | main $%.2f | sidecar $%.2f"
                % (
                    net,
                    float(audit_main.net_usd),
                    float(audit_sc.net_usd) if audit_sc else 0.0,
                ),
                "Trades: %d | Stress DD: $%.2f | N/S: %.2f" % (trades, stress, ns),
                "",
                "Stance: research.",
                "SUMMARY: %s" % (output_root / "SUMMARY.md"),
            ]
        )
        (output_root / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")
        _progress(
            output_root,
            "DONE net=$%.2f trades=%d N/S=%.2f" % (net, trades, ns),
        )
        try:
            from .run_ledger import log_run

            eq_cands = sorted((audits_root).rglob("equity_curve.csv")) if audits_root.exists() else []
            log_run(
                run_class="sidecar" if enable_mid_sidecar else "broker_like",
                variant_slug=str(output_root.name),
                instrument=instrument,
                hub_path=output_root,
                engine="paper_broker",
                net_usd=net,
                stress_dd_usd=stress,
                close_mtm_dd_usd=closed,
                ns=ns,
                trades=trades,
                units=units_n,
                replay_start=str(audit_main.start_ts or ""),
                replay_end=str(audit_main.end_ts or ""),
                equity_curve_path=eq_cands[0] if eq_cands else None,
                meta={
                    "main_id": main_id,
                    "sidecar_id": sidecar_id,
                    "enable_mid_sidecar": bool(enable_mid_sidecar),
                    "sidecar_eoq": eoq_mode,
                    "sidecar_r_targets": list(r_targets),
                    "allowed_sides": list(sides),
                    "main_net_usd": float(audit_main.net_usd),
                    "sidecar_net_usd": float(audit_sc.net_usd) if audit_sc else 0.0,
                },
                notes="quarterly_range_breakout_broker",
            )
        except Exception as exc:
            _progress(output_root, "run_ledger skip: %s" % exc)
        if email:
            send_email(
                subject="potions: %s quarterly + sidecar BE (net $%.0f)" % (instrument, net),
                body=email_body,
            )
        return 0
    except Exception as exc:
        _progress(output_root, "FAILED: %s" % exc)
        tb = traceback.format_exc()
        (output_root / "FAILED.txt").write_text(tb, encoding="utf-8")
        if email:
            try:
                send_email(
                    subject="potions: %s quarterly range breakout FAILED" % instrument,
                    body="Hub: %s\n\n%s\n" % (output_root, tb[-4000:]),
                )
            except Exception:
                pass
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", type=Path, default=DEFAULT_DAILY)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--instrument", type=str, default="NQ")
    p.add_argument("--slippage-ticks", type=float, default=1.0)
    p.add_argument("--entry-qty", type=int, default=ENTRY_QTY)
    p.add_argument("--scale-qty", type=int, default=SCALE_QTY, help="Main ladder scale qty.")
    p.add_argument(
        "--sidecar-scale-qty",
        type=int,
        default=0,
        help="Sidecar scale qty (0 → use --scale-qty). Use 4 with 1,2R targets.",
    )
    p.add_argument(
        "--allowed-sides",
        type=str,
        default="long,short",
        help="Comma list: long,short or long (no shorts).",
    )
    p.add_argument(
        "--require-mor-dirs",
        type=str,
        default="",
        help="Comma list of causal Monthly OR dirs to allow (e.g. mor_up or up).",
    )
    p.add_argument(
        "--require-yor-dirs",
        type=str,
        default="",
        help="Comma list of causal Yearly ORB dirs to allow (e.g. yor_up or up).",
    )
    p.add_argument(
        "--require-w-atr-aligns",
        type=str,
        default="",
        help="Comma list of weekly ATR align tags (e.g. w_atr_aligned or aligned).",
    )
    p.add_argument(
        "--enable-mid-sidecar",
        action="store_true",
        help="On large-width primary mid-stop, re-enter same dir at mid with far-extreme SL.",
    )
    p.add_argument("--sidecar-min-width-quantile", type=float, default=0.75)
    p.add_argument("--sidecar-min-hist", type=int, default=8)
    p.add_argument(
        "--sidecar-min-prior-width",
        type=float,
        default=0.0,
        help="Optional absolute prior-width floor (pts) to treat as large.",
    )
    p.add_argument(
        "--sidecar-eoq",
        type=str,
        default="be_carry",
        help="Sidecar end-of-quarter mode: be_carry | flatten.",
    )
    p.add_argument(
        "--sidecar-r-targets",
        type=str,
        default="1,2,3,4",
        help="Comma list of sidecar R multiples (e.g. 1,2,3,4 or 1,2).",
    )
    p.add_argument("--force", action="store_true", default=True)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    sides = [s.strip() for s in str(args.allowed_sides).split(",") if s.strip()]
    mor = [s.strip() for s in str(args.require_mor_dirs).split(",") if s.strip()]
    yor = [s.strip() for s in str(args.require_yor_dirs).split(",") if s.strip()]
    w_atr = [s.strip() for s in str(args.require_w_atr_aligns).split(",") if s.strip()]
    r_tgts = [
        float(x.strip())
        for x in str(args.sidecar_r_targets).split(",")
        if x.strip()
    ]
    return run(
        output_root=args.output_root,
        daily_path=args.daily,
        instrument=str(args.instrument),
        force=bool(args.force),
        slippage_ticks=float(args.slippage_ticks),
        email=bool(args.email),
        allowed_sides=sides,
        entry_qty=int(args.entry_qty),
        scale_qty=int(args.scale_qty),
        sidecar_scale_qty=(int(args.sidecar_scale_qty) or None),
        require_mor_dirs=mor,
        require_yor_dirs=yor,
        require_w_atr_aligns=w_atr,
        enable_mid_sidecar=bool(args.enable_mid_sidecar),
        sidecar_min_width_quantile=float(args.sidecar_min_width_quantile),
        sidecar_min_hist=int(args.sidecar_min_hist),
        sidecar_min_prior_width=float(args.sidecar_min_prior_width),
        sidecar_eoq=str(args.sidecar_eoq),
        sidecar_r_targets=r_tgts,
    )


if __name__ == "__main__":
    raise SystemExit(main())
