"""Broker-like MNQ periodic DCA: 1 contract every month vs every quarter.

Buys on the open of the first daily bar of each month / calendar quarter
(Jan/Apr/Jul/Oct). Holds to end; net + MTM drawdowns via ``audit_units``.

Optional ``--require-st-bullish``: buy only when prior-close daily ATR Supertrend
(14×3) is bullish; otherwise skip that period.
"""

from __future__ import annotations

import argparse
import json
import shutil
import traceback
from pathlib import Path
from typing import List, Optional

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, read_bars, units_from_live_fills
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .spread_model import SpreadModel
from .store import FlatFileStore
from .verification import QuietPaperVerificationProvider

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "mnq_periodic_dca_broker"
DEFAULT_OUT_ST = REPO / "live" / "state" / "mnq_periodic_dca_st_bullish_broker"
BASELINE_HUB = DEFAULT_OUT
MNQ_DAILY = REPO / "mnq" / "mnq_daily.csv"
TICK = 0.25
POINT_VALUE = 2.0
FEE_PER_UNIT = 1.50
ATR_LEN = 14
ATR_MULT = 3.0


def _progress(hub: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    path = hub / "PROGRESS.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(line)


def _load_daily(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts = pd.to_datetime(df["date"], errors="coerce")
    df = df.assign(ts=ts).dropna(subset=["ts"]).sort_values("ts")
    return df.reset_index(drop=True)


def run_cadence(
    *,
    hub: Path,
    cadence: str,
    force: bool,
    qty: int = 1,
    require_st_bullish: bool = False,
) -> dict:
    gate_tag = "st_bullish" if require_st_bullish else "ungated"
    strategy_id = "mnq_periodic_dca_%s_%s" % (cadence, gate_tag)
    state_root = hub / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(hub, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    POINT_VALUES["MNQ"] = POINT_VALUE
    DEFAULT_TICK_SIZE["MNQ"] = TICK

    df = _load_daily(MNQ_DAILY)
    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "cadence": cadence,
        "qty": int(qty),
        "side": "buy",
        "suppress_alerts": True,
        "require_daily_supertrend_bullish": bool(require_st_bullish),
        "atr_len": ATR_LEN,
        "atr_mult": ATR_MULT,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="periodic_dca",
                    version="v1",
                    instrument="MNQ",
                    broker_instrument="MNQ",
                    account_mode="paper",
                    enabled=True,
                    timeframes="D",
                    max_contracts=500,
                    max_open_orders=32,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    spread = SpreadModel(
        rth_half_spread_ticks=0.5,
        eth_half_spread_ticks=1.0,
        open_widen_half_spread_ticks=1.0,
        low_volume_threshold=50.0,
        low_volume_multiplier=1.5,
        tick_size=TICK,
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={"MNQ": TICK},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(slippage_ticks=1.0, spread_model=spread),
    )

    _progress(hub, "RUN %s bars=%d" % (strategy_id, len(df)))
    last_ts = ""
    last_close = 0.0
    for _, row in df.iterrows():
        ts_s = pd.Timestamp(row["ts"]).strftime("%Y-%m-%d")
        bar = Bar(
            instrument="MNQ",
            timeframe="D",
            ts=ts_s,
            open=float(row["open"]),
            high=float(row["high"]),
            low=float(row["low"]),
            close=float(row["close"]),
            volume=float(row.get("volume", 0.0) or 0.0),
            complete=True,
            source=str(MNQ_DAILY),
        )
        engine.process_bar(bar)
        last_ts = ts_s
        last_close = float(row["close"])
    store.flush_tables()

    fills_path = state_root / "fills.csv"
    units = units_from_live_fills(
        fills_path,
        strategy_id,
        mark_open_ts=last_ts,
        mark_open_price=last_close,
        mark_exit_reason="open_mark",
    )
    bars = read_bars(MNQ_DAILY, ts_field="date")
    gate_note = (
        "ST gate: prior-close daily ATR Supertrend %dx%.1f bullish; else skip period."
        % (ATR_LEN, ATR_MULT)
        if require_st_bullish
        else "ungated period-open buys"
    )
    audit = audit_units(
        name="MNQ periodic DCA %s %s" % (cadence, gate_tag),
        slug=strategy_id,
        source=fills_path,
        bar_source=MNQ_DAILY,
        bars=bars,
        units=units,
        instrument="MNQ",
        notes="1 MNQ buy on period-open; hold to end; %s; fee=$%.2f/unit; slip=1 tick"
        % (gate_note, FEE_PER_UNIT),
        output_root=state_root / "audit",
        fee_per_unit=FEE_PER_UNIT,
    )
    n_buys = 0
    if fills_path.exists():
        for row in pd.read_csv(fills_path).to_dict("records"):
            reason = str(row.get("reason") or "")
            if reason in {"entry", "add"} or reason.startswith("runner_entry"):
                n_buys += int(float(row.get("quantity") or 0))

    skip_count = 0
    try:
        st = store.get_state(strategy_id)
        skip_count = int(st.get("skip_count") or 0)
    except Exception:
        skip_count = 0

    final_qty = int(audit.max_open_units)
    net = float(audit.net_usd)
    close_dd = float(audit.close_mtm_dd_usd)
    stress_dd = float(audit.intrabar_mtm_dd_usd)
    metrics = {
        "strategy_id": strategy_id,
        "cadence": cadence,
        "gate": gate_tag,
        "require_st_bullish": bool(require_st_bullish),
        "atr_len": ATR_LEN,
        "atr_mult": ATR_MULT,
        "instrument": "MNQ",
        "qty_per_buy": qty,
        "bars": len(df),
        "start_ts": str(df["ts"].iloc[0].date()) if len(df) else "",
        "end_ts": last_ts,
        "n_buys": n_buys,
        "n_skips": skip_count,
        "final_qty": final_qty,
        "units_marked": int(audit.units),
        "net_usd": net,
        "close_mtm_dd_usd": close_dd,
        "intrabar_stress_dd_usd": stress_dd,
        "net_over_stress": (net / abs(stress_dd)) if stress_dd else 0.0,
        "end_mark_price": last_close,
        "fee_per_unit": FEE_PER_UNIT,
        "slippage_ticks": 1.0,
        "point_value": POINT_VALUE,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        hub,
        "DONE %s gate=%s buys=%d skips=%d qty=%d net=$%+.0f close_dd=$%.0f stress_dd=$%.0f N/S=%.2f"
        % (
            cadence,
            gate_tag,
            n_buys,
            skip_count,
            final_qty,
            net,
            close_dd,
            stress_dd,
            metrics["net_over_stress"],
        ),
    )
    return metrics


def _load_baseline() -> dict:
    """Map cadence -> ungated metrics from prior hub if present."""
    out = {}
    for cadence in ("monthly", "quarterly"):
        # Prior hub used mnq_periodic_dca_{cadence} before gate tags.
        for slug in (
            "mnq_periodic_dca_%s" % cadence,
            "mnq_periodic_dca_%s_ungated" % cadence,
        ):
            path = BASELINE_HUB / "states" / slug / "metrics.json"
            if path.exists():
                out[cadence] = json.loads(path.read_text(encoding="utf-8"))
                break
    return out


def write_summary(hub: Path, results: List[dict], *, require_st_bullish: bool) -> Path:
    gate_line = (
        "Gate: **prior-close** daily ATR Supertrend %d×%.1f must be **bullish** on period-open; "
        "else skip that period (no mid-period catch-up)."
        % (ATR_LEN, ATR_MULT)
        if require_st_bullish
        else "Gate: none (buy every period open)."
    )
    lines = [
        "# MNQ periodic DCA (broker-like)%s"
        % (" — ST bullish gate" if require_st_bullish else ""),
        "",
        "Engine + PaperBroker + StrategyPlugin `periodic_dca`.",
        "Buy **1 MNQ** on the **open** of the first daily bar of each month or calendar quarter; hold to end.",
        gate_line,
        "Realism: slip 1 tick, spread model, fee $%.2f/unit (entry-side in audit), MNQ $2/pt." % FEE_PER_UNIT,
        "Bars: `%s`." % MNQ_DAILY.relative_to(REPO),
        "",
        "| Cadence | Buys | Skips | Final qty | Net | Close MTM DD | Intrabar stress DD | N/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in results:
        lines.append(
            "| {cadence} | {n_buys} | {n_skips} | {final_qty} | ${net_usd:,.0f} | ${close_mtm_dd_usd:,.0f} | "
            "${intrabar_stress_dd_usd:,.0f} | {net_over_stress:.2f} |".format(**r)
        )
    if require_st_bullish:
        baseline = _load_baseline()
        if baseline:
            lines.extend(
                [
                    "",
                    "## vs ungated (prior hub)",
                    "",
                    "| Cadence | Ungated net | ST-gated net | Δ net | Ungated stress | ST stress |",
                    "|---|---:|---:|---:|---:|---:|",
                ]
            )
            for r in results:
                b = baseline.get(r["cadence"])
                if not b:
                    continue
                lines.append(
                    "| {cadence} | ${u_net:,.0f} | ${g_net:,.0f} | ${delta:,.0f} | ${u_st:,.0f} | ${g_st:,.0f} |".format(
                        cadence=r["cadence"],
                        u_net=float(b["net_usd"]),
                        g_net=float(r["net_usd"]),
                        delta=float(r["net_usd"]) - float(b["net_usd"]),
                        u_st=float(b["intrabar_stress_dd_usd"]),
                        g_st=float(r["intrabar_stress_dd_usd"]),
                    )
                )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Quarterly buys fire on first session of Jan / Apr / Jul / Oct.",
            "- Net marks open inventory at last close; drawdowns are peak-to-trough on MTM equity.",
            "- Diagnostic only — not a promotion gate.",
            "",
        ]
    )
    path = hub / "SUMMARY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    pd.DataFrame(results).to_csv(hub / "summary.csv", index=False)
    return path


def write_email(hub: Path, results: List[dict], *, require_st_bullish: bool) -> Path:
    title = "MNQ periodic DCA ST-bullish gate" if require_st_bullish else "MNQ periodic DCA"
    body_lines = [
        "%s (broker-like) complete" % title,
        "Hub: %s" % hub,
        "",
    ]
    if require_st_bullish:
        body_lines.append(
            "Gate: prior-close daily ATR Supertrend %dx%.1f bullish on period-open."
            % (ATR_LEN, ATR_MULT)
        )
        body_lines.append("")
    for r in results:
        body_lines.append(
            "%s: buys=%d skips=%d final_qty=%d net=$%+.0f close_dd=$%.0f stress_dd=$%.0f N/S=%.2f"
            % (
                r["cadence"],
                r["n_buys"],
                r.get("n_skips", 0),
                r["final_qty"],
                r["net_usd"],
                r["close_mtm_dd_usd"],
                r["intrabar_stress_dd_usd"],
                r["net_over_stress"],
            )
        )
    if require_st_bullish:
        baseline = _load_baseline()
        if baseline:
            body_lines.append("")
            body_lines.append("vs ungated:")
            for r in results:
                b = baseline.get(r["cadence"])
                if not b:
                    continue
                body_lines.append(
                    "  %s: ungated net=$%+.0f → gated $%+.0f (Δ $%+.0f); stress $%.0f → $%.0f"
                    % (
                        r["cadence"],
                        float(b["net_usd"]),
                        float(r["net_usd"]),
                        float(r["net_usd"]) - float(b["net_usd"]),
                        float(b["intrabar_stress_dd_usd"]),
                        float(r["intrabar_stress_dd_usd"]),
                    )
                )
    body_lines.extend(["", "Stance: diagnostic only (buy-and-hold DCA benchmark).", ""])
    path = hub / "EMAIL.txt"
    path.write_text("\n".join(body_lines), encoding="utf-8")
    return path


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--qty", type=int, default=1)
    ap.add_argument(
        "--require-st-bullish",
        action="store_true",
        help="Only buy when prior-close daily ATR Supertrend is bullish",
    )
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(argv)

    hub = args.out or (DEFAULT_OUT_ST if args.require_st_bullish else DEFAULT_OUT)
    hub.mkdir(parents=True, exist_ok=True)
    if args.force and (hub / "PROGRESS.log").exists():
        (hub / "PROGRESS.log").unlink()

    results: List[dict] = []
    try:
        for cadence in ("monthly", "quarterly"):
            results.append(
                run_cadence(
                    hub=hub,
                    cadence=cadence,
                    force=args.force,
                    qty=args.qty,
                    require_st_bullish=bool(args.require_st_bullish),
                )
            )
        write_summary(hub, results, require_st_bullish=bool(args.require_st_bullish))
        email_path = write_email(hub, results, require_st_bullish=bool(args.require_st_bullish))
        write_run_manifest(
            hub,
            data_inputs=[MNQ_DAILY],
            strategy_config={
                "strategy_type": "periodic_dca",
                "qty": args.qty,
                "require_daily_supertrend_bullish": bool(args.require_st_bullish),
                "atr_len": ATR_LEN,
                "atr_mult": ATR_MULT,
            },
            broker_realism_config={
                "slippage_ticks": 1.0,
                "fee_per_unit": FEE_PER_UNIT,
                "tick": TICK,
            },
            extra={"results": results},
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "results": results}, indent=2) + "\n",
            encoding="utf-8",
        )
        if args.email:
            subj = (
                "potions: MNQ periodic DCA ST-bullish complete"
                if args.require_st_bullish
                else "potions: MNQ periodic DCA complete"
            )
            send_email(subject=subj, body=email_path.read_text(encoding="utf-8"))
        return 0
    except Exception:
        tb = traceback.format_exc()
        _progress(hub, "FAIL\n" + tb)
        fail_mail = hub / "EMAIL_FAIL.txt"
        fail_mail.write_text("MNQ periodic DCA FAILED\nHub: %s\n\n%s\n" % (hub, tb), encoding="utf-8")
        try:
            send_email(subject="potions: MNQ periodic DCA FAILED", body=fail_mail.read_text())
        except Exception:
            pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
