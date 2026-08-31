"""Weekly open-day breakout — 4h signals, 1m fill tape.

StrategyPlugin ``weekly_open_day_breakout`` on weekly chart levels (open-day H/L
+ mid ±4×ATR). Limit at breakout candle close; SL at far side of open-day range;
scale **2/1/1** (candle-R / open-day-R / Friday NY runner), BE after OD-R.

Default hub: ``live/state/weekly_open_day_breakout_1m_broker``
Default market: GBPUSD (top-3 weekly chart book); optional US30.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from datetime import date, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .engine import Engine
from .fx_data import load_fx_1m_by_ny_date
from .gbpusd_quarterly_4h_charts import load_4h
from .hourly_st_pmc_strategyplugin_variants import _broker_needs_1m
from .models import Bar, StrategyInstance, as_row
from .notifications import NullNotificationSink
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS, MarketSpec, _spread
from .replay_audit import POINT_VALUES
from .replay_manifest import write_run_manifest
from .replay_realism import hardened_replay_engine_kwargs
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore
from .v2b_strategy_replay import AuditBar, fast_intraday_audit, units_from_v2b_fills
from .verification import QuietPaperVerificationProvider
from .ym_hourly_st_pmc_retest_replay import concat_all_1m

REPO = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO / "live" / "state" / "weekly_open_day_breakout_1m_broker"
NY = "America/New_York"
SIGNAL_OFFSET_MIN = 240
DSR = "TRL-2026-00161"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _utc_z(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY)
    return t.tz_convert("UTC").isoformat().replace("+00:00", "Z")


def _1m_csv(market: MarketSpec) -> Path:
    return REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())


def _append_dsr(hub: Path, markets: Sequence[str], start: date, end: date) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    if DSR in text:
        return
    with path.open("r", encoding="utf-8") as rh:
        reader = csv.DictReader(rh)
        fieldnames = list(reader.fieldnames or [])
    row = {k: "" for k in fieldnames}
    updates = {
        "trial_id": DSR,
        "date": date.today().isoformat(),
        "agent": "cursor",
        "family": "WEEKLY_LEVEL",
        "variant": "weekly_open_day_breakout_1m",
        "is_primary": "True",
        "instrument": ",".join(markets),
        "sample_start": start.isoformat(),
        "sample_end": end.isoformat(),
        "sample_scope": "RECENT_WINDOW",
        "peeked": "False",
        "params_json": json.dumps(
            {
                "entry": "limit_at_breakout_close",
                "stop": "od_range_far_side",
                "scale": "2_1_1_candleR_odR_friday",
                "be_after": "tp2",
                "max_trades_per_week": 2,
                "friday_flatten_ny": "17:00",
                "feed_tf": "1m",
                "signal_tf": "4h",
            },
            sort_keys=True,
        ),
        "artifact_path": str(hub.relative_to(REPO)),
        "n_markets": str(len(markets)),
        "status": "RUNNING",
        "notes": "Weekly OD breakout v3: SL=far OD range; 2/1/1; Fri NY flatten; max 2/wk.",
    }
    for k, v in updates.items():
        if k in row:
            row[k] = v
    with path.open("a", encoding="utf-8", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore").writerow(row)


def _signal_bars(df: pd.DataFrame, market: MarketSpec) -> Tuple[List[Bar], List[AuditBar]]:
    out: List[Bar] = []
    audit: List[AuditBar] = []
    for ts, row in df.iterrows():
        if pd.isna(row.get("close")):
            continue
        ts_s = pd.Timestamp(ts).tz_convert("UTC").isoformat().replace("+00:00", "Z")
        o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
        out.append(
            Bar(
                instrument=market.symbol,
                timeframe="4h",
                ts=ts_s,
                open=o,
                high=h,
                low=l,
                close=c,
                volume=float(row.get("volume", 0.0) or 0.0),
                complete=True,
                source=str(market.csv),
            )
        )
        audit.append(AuditBar(ts_s, o, h, l, c))
    return out, audit


def _replay_4h_with_1m(
    engine: Engine,
    *,
    signal_bars: Sequence[Bar],
    one_m: pd.DataFrame,
    market: MarketSpec,
    label: str,
    output_root: Path,
) -> int:
    offset = pd.Timedelta(minutes=SIGNAL_OFFSET_MIN)
    idx = one_m.index
    seen = 0
    n = len(signal_bars)
    cursor: Optional[pd.Timestamp] = None
    source = str(_1m_csv(market))

    def replay_1m_until(start: Optional[pd.Timestamp], end: pd.Timestamp) -> int:
        nonlocal seen
        if not _broker_needs_1m(engine):
            return 0
        lo = 0 if start is None else idx.searchsorted(start, side="left")
        hi = idx.searchsorted(end, side="left")
        if lo >= hi:
            return 0
        sl = one_m.iloc[lo:hi]
        vol = sl["volume"] if "volume" in sl.columns else None
        for j, (ts, o, h, l, c) in enumerate(
            zip(sl.index, sl["open"], sl["high"], sl["low"], sl["close"])
        ):
            if min(float(o), float(h), float(l), float(c)) <= 0:
                continue
            engine.process_bar(
                Bar(
                    instrument=market.symbol,
                    timeframe="1m",
                    ts=_utc_z(ts),
                    open=float(o),
                    high=float(h),
                    low=float(l),
                    close=float(c),
                    volume=float(vol.iloc[j]) if vol is not None else 0.0,
                    complete=True,
                    source=source,
                )
            )
            seen += 1
        return len(sl)

    for i, sbar in enumerate(signal_bars):
        signal_ts = pd.Timestamp(sbar.ts)
        if signal_ts.tzinfo is None:
            signal_ts = signal_ts.tz_localize("UTC")
        else:
            signal_ts = signal_ts.tz_convert("UTC")
        signal_ts = signal_ts + offset

        replay_1m_until(cursor, signal_ts)
        shifted = Bar(
            instrument=sbar.instrument,
            timeframe=sbar.timeframe,
            ts=_utc_z(signal_ts),
            open=sbar.open,
            high=sbar.high,
            low=sbar.low,
            close=sbar.close,
            volume=sbar.volume,
            complete=sbar.complete,
            source=sbar.source,
        )
        engine.process_bar(shifted, broker_fills=False)
        cursor = signal_ts
        if (i + 1) % 2000 == 0 or (i + 1) == n:
            _progress(output_root, "  %s signal %d/%d (1m=%d)" % (label, i + 1, n, seen))

    if len(idx) > 0 and cursor is not None:
        replay_1m_until(cursor, idx[-1] + pd.Timedelta(minutes=1))
    _progress(output_root, "  %s done 1m=%d" % (label, seen))
    return seen


def run_one(
    *,
    output_root: Path,
    market: MarketSpec,
    force: bool,
    start: Optional[date],
    end: Optional[date],
) -> dict:
    strategy_id = "%s_weekly_open_day_breakout" % market.symbol.lower()
    state_root = output_root / "states" / strategy_id
    metrics_path = state_root / "metrics.json"
    if (not force) and metrics_path.exists():
        _progress(output_root, "CACHE %s" % strategy_id)
        return json.loads(metrics_path.read_text(encoding="utf-8"))

    one_m_path = _1m_csv(market)
    if not one_m_path.exists():
        raise FileNotFoundError("Missing 1m tape for %s: %s" % (market.symbol, one_m_path))

    POINT_VALUES[market.symbol] = market.point_value
    DEFAULT_TICK_SIZE[market.symbol] = market.tick

    df = load_4h(market.csv, market.symbol)
    if start is not None:
        # Warm ATR: keep ~60 days of 4h before window.
        warm = pd.Timestamp(start, tz=NY) - pd.Timedelta(days=60)
        df = df[df.index >= warm]
    if end is not None:
        df = df[df.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]

    _progress(output_root, "Loading %s 1m from %s ..." % (market.symbol, one_m_path))
    gby = load_fx_1m_by_ny_date(one_m_path, market.symbol)
    one_m = concat_all_1m(gby)
    if start is not None:
        one_m = one_m[one_m.index >= pd.Timestamp(start, tz=NY)]
    if end is not None:
        one_m = one_m[one_m.index < pd.Timestamp(end, tz=NY) + pd.Timedelta(days=1)]
    if one_m.empty:
        raise RuntimeError("empty 1m tape for %s" % market.symbol)
    _progress(output_root, "  %s 4h=%d 1m=%d" % (market.symbol, len(df), len(one_m)))

    # Signal bars only inside [start, end]; ATR warm bars before start still feed plugin
    # if we include them — include all df bars for ATR, but only arm after start via
    # live_after. Simpler: pass all df bars (warm+window) as signals.
    signal_bars, audit_bars = _signal_bars(df, market)
    # Audit only in-window bars.
    if start is not None:
        start_utc = pd.Timestamp(start, tz=NY).tz_convert("UTC")
        audit_bars = [b for b in audit_bars if pd.Timestamp(b.ts) >= start_utc]

    if force and state_root.exists():
        shutil.rmtree(state_root)
    store = FlatFileStore(state_root, defer_table_writes=True)
    store.ensure()
    payload = {
        "tick_size": market.tick,
        "entry_qty": 4,
        "tp1_qty": 2,
        "tp2_qty": 1,
        "atr_len": 14,
        "atr_mult": 4.0,
        "timeframe": "4h",
        "max_trades_per_week": 2,
        "be_after": "tp2",
        "record_levels": False,
        "suppress_alerts": True,
    }
    store.write_table(
        "strategy_instances",
        [
            as_row(
                StrategyInstance(
                    strategy_id=strategy_id,
                    strategy_type="weekly_open_day_breakout",
                    version="v1",
                    instrument=market.symbol,
                    broker_instrument=market.symbol,
                    account_mode="paper",
                    enabled=True,
                    timeframes="4h",
                    max_contracts=4,
                    max_open_orders=64,
                    config_json=json.dumps(payload, sort_keys=True),
                )
            )
        ],
    )
    engine = Engine(
        store=store,
        persist_bars=False,
        persist_health=False,
        tick_size={market.symbol: market.tick},
        notification_sink=NullNotificationSink(),
        verification_provider=QuietPaperVerificationProvider(),
        emit_order_alerts=False,
        broker_log_events=False,
        broker_persist_modifications=False,
        **hardened_replay_engine_kwargs(
            slippage_ticks=1.0,
            spread_model=_spread(market.tick, market.family),
        ),
    )
    _progress(output_root, "START %s weekly_open_day_breakout (4h signal / 1m fills)" % market.symbol)
    _replay_4h_with_1m(
        engine,
        signal_bars=signal_bars,
        one_m=one_m,
        market=market,
        label=strategy_id,
        output_root=output_root,
    )
    store.flush_tables()

    units = units_from_v2b_fills(state_root / "fills.csv", strategy_id)
    audit = fast_intraday_audit(
        strategy_id=strategy_id,
        state_root=state_root,
        bars=audit_bars,
        units=units,
        instrument=market.symbol,
        fee_per_unit=market.fee_per_unit,
    )
    net = float(audit.get("net_usd") or 0.0)
    stress = float(audit.get("intrabar_stress_dd_usd") or 0.0)
    ns = (net / abs(stress)) if stress else 0.0
    trades = int(audit.get("trades") or len({u.trade_id for u in units}))
    if ns >= 2.0 and trades >= 20:
        stance = "research — interesting N/S"
    elif net > 0 and trades >= 10:
        stance = "weak — needs tune"
    else:
        stance = "reject / thin"

    metrics = {
        "strategy_id": strategy_id,
        "market": market.symbol,
        "feed_tf": "1m",
        "signal_tf": "4h",
        "bars_4h": len(signal_bars),
        "bars_1m": len(one_m),
        "units": int(audit.get("units") or len(units)),
        "trades": trades,
        "net_usd": net,
        "closed_dd_usd": float(audit.get("closed_dd_usd") or 0.0),
        "intrabar_stress_dd_usd": stress,
        "win_rate": float(audit.get("win_rate") or 0.0) / 100.0,
        "profit_factor": float(audit.get("profit_factor") or 0.0),
        "net_over_stress": ns,
        "max_open_units": int(audit.get("max_open_units") or 0),
        "stance": stance,
        "dsr_trial": DSR,
    }
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    _progress(
        output_root,
        "DONE %s net=%+.0f N/S=%.2f trades=%d WR=%.1f%%"
        % (market.symbol, net, ns, trades, 100.0 * metrics["win_rate"]),
    )
    return metrics


def write_summary(output_root: Path, rows: Sequence[dict], start: date, end: date) -> None:
    lines = [
        "# Weekly open-day breakout (1m fills) v3",
        "",
        "4h decisions on open-day H/L; limit at breakout candle close; SL at **far OD range**.",
        "Scale **2/1/1** (entry 4): 2 @ candle-R, 1 @ open-day-R, runner to **Friday 17:00 NY** flatten.",
        "BE after OD-R. Max **2** campaigns/week. No candle-size skip filters.",
        "",
        "Window: %s → %s · DSR %s" % (start.isoformat(), end.isoformat(), DSR),
        "",
        "| Market | 4h bars | 1m bars | Trades | Net | Stress DD | N/S | WR | PF | Stance |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for m in rows:
        lines.append(
            "| %s | %d | %d | %d | $%+.0f | $%+.0f | %.2f | %.1f%% | %.2f | %s |"
            % (
                m["market"],
                int(m.get("bars_4h") or 0),
                int(m.get("bars_1m") or 0),
                int(m.get("trades") or 0),
                float(m.get("net_usd") or 0.0),
                float(m.get("intrabar_stress_dd_usd") or 0.0),
                float(m.get("net_over_stress") or 0.0),
                100.0 * float(m.get("win_rate") or 0.0),
                float(m.get("profit_factor") or 0.0),
                m.get("stance") or "",
            )
        )
    lines.extend(["", "Hub: `%s`" % output_root, ""])
    (output_root / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    pd.DataFrame(list(rows)).to_csv(output_root / "summary.csv", index=False)


def run(
    *,
    output_root: Path,
    markets: Sequence[str],
    years: float,
    force: bool,
    email: bool,
) -> int:
    output_root.mkdir(parents=True, exist_ok=True)
    # Anchor end to last available 4h bar (research tape), not wall clock.
    probe = MARKETS[markets[0].upper()]
    df_probe = load_4h(probe.csv, probe.symbol)
    end = df_probe.index.max().tz_convert(NY).date() if len(df_probe) else date.today()
    start = end - timedelta(days=int(round(365.25 * years)))
    start = start - timedelta(days=start.weekday())  # Monday
    _append_dsr(output_root, markets, start, end)
    rid = begin_run(
        run_class="broker_like",
        variant_slug="weekly_open_day_breakout_1m",
        instrument=",".join(m.upper() for m in markets),
        hub_path=str(output_root.relative_to(REPO)),
        dsr_trial_id=DSR,
        meta={"years": years, "start": start.isoformat(), "end": end.isoformat()},
    )
    try:
        rows: List[dict] = []
        for sym in markets:
            market = MARKETS[sym.upper()]
            rows.append(
                run_one(
                    output_root=output_root,
                    market=market,
                    force=force,
                    start=start,
                    end=end,
                )
            )
        write_summary(output_root, rows, start, end)
        (output_root / "RUN_COMPLETE.json").write_text('{"ok": true}\n', encoding="utf-8")
        write_run_manifest(
            output_root,
            data_inputs=[MARKETS[m.upper()].csv for m in markets],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            strategy_config={"strategy_type": "weekly_open_day_breakout", "entry_qty": 4, "scale": "2/1/1"},
            extra={"dsr_trial_id": DSR, "markets": list(markets), "years": years},
        )
        body_lines = [
            "Weekly open-day breakout (1m fills)",
            "",
            "Hub: %s" % output_root,
            "DSR: %s" % DSR,
            "Window: %s → %s (~%.1fy)" % (start.isoformat(), end.isoformat(), years),
            "",
        ]
        for m in rows:
            body_lines.append(
                "%s: trades=%d net=$%+.0f stress=$%+.0f N/S=%.2f WR=%.1f%% — %s"
                % (
                    m["market"],
                    int(m["trades"]),
                    float(m["net_usd"]),
                    float(m["intrabar_stress_dd_usd"]),
                    float(m["net_over_stress"]),
                    100.0 * float(m["win_rate"]),
                    m["stance"],
                )
            )
        body = "\n".join(body_lines) + "\n"
        (output_root / "EMAIL.txt").write_text(body, encoding="utf-8")
        if email:
            send_email(subject="potions: weekly open-day breakout 1m broker", body=body)
        complete_run(
            rid,
            net_usd=sum(float(r["net_usd"]) for r in rows),
            stress_dd_usd=min((float(r["intrabar_stress_dd_usd"]) for r in rows), default=0.0),
            trades=sum(int(r["trades"]) for r in rows),
            ns=float(rows[0]["net_over_stress"]) if len(rows) == 1 else None,
            meta={"rows": rows},
            notes=rows[0]["stance"] if rows else "",
        )
        return 0
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        _progress(output_root, "CRASH %s\n%s" % (exc, traceback.format_exc()))
        if email:
            send_email(
                subject="potions: weekly open-day breakout FAILED",
                body="Hub: %s\n\n%s\n%s" % (output_root, exc, traceback.format_exc()[-2000:]),
            )
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    p.add_argument("--market", action="append", default=[], help="Repeatable; default GBPUSD")
    p.add_argument("--years", type=float, default=3.0)
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    markets = args.market or ["GBPUSD"]
    return run(
        output_root=args.output_root,
        markets=markets,
        years=float(args.years),
        force=bool(args.force),
        email=bool(args.email),
    )


if __name__ == "__main__":
    raise SystemExit(main())
