"""USDJPY FBO 1/1/3 atr80 — HA RSI 55–70 entry filter (broker-like).

Same Engine+PaperBroker book as banked ``fbo_1_1_3_atr80_usdjpy``, with
``entry_filter_csv`` = atr80 AND causal hourly RSI14 in [55, 70].

Fill tape (``--tf``):
  - ``1m`` (default): 1-minute PaperBroker fills; daily OR decisions synthesized
  - ``4h``: 4-hour fill tape (≤4h ceiling)
  - ``D``: legacy daily OHLC fill tape

MTM audit uses 4h bars when fill tape is 1m (finer than daily, bounded size).
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import traceback
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

from .broker import DEFAULT_TICK_SIZE
from .broker_like_replays import BrokerReplaySpec, _month_end_dates
from .engine import Engine, bars_from_csv
from .fx_data import load_fx_1m_by_ny_date
from .intraday_condition_profile import build_feature_frames
from .models import Bar, StrategyInstance, as_row
from .notify_email import send_email
from .replay_audit import POINT_VALUES, audit_units, units_from_live_fills
from .replay_manifest import write_run_manifest
from .reporting import generate_market_close_report
from .run_ledger import begin_run, complete_run, fail_run
from .store import FlatFileStore

REPO = Path(__file__).resolve().parents[1]
OUT_D = REPO / "live" / "state" / "usdjpy_fbo_113_atr80_rsi55_70_broker"
OUT_1M = REPO / "live" / "state" / "usdjpy_fbo_113_atr80_rsi55_70_1m_broker"
OUT_4H = REPO / "live" / "state" / "usdjpy_fbo_113_atr80_rsi55_70_4h_broker"
OUT_ARM_1M = REPO / "live" / "state" / "usdjpy_fbo_113_atr80_rsi55_70_arm_skip_1m_broker"
OUT_ARM_RSI_SIDE_1M = REPO / "live" / "state" / "usdjpy_fbo_113_atr80_rsi_with_side_arm_skip_1m_broker"
INSTRUMENT = "USDJPY"
TICK = 0.001
FEE = 7.0
JPY_USD = 110.0
NY = "America/New_York"
VARIANT = "fbo_1_1_3_atr80_rsi55_70_usdjpy"


def _normalize_arm_rsi_buckets(raw: Optional[Iterable[str]]) -> List[str]:
    if raw is None:
        return ["rsi_55_70"]
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    else:
        parts = [str(p).strip() for p in raw if str(p).strip()]
    return parts or ["rsi_55_70"]


def _arm_rsi_tag(buckets: List[str]) -> str:
    if "rsi_with_side" in buckets:
        return "rsi_with_side"
    return "rsi55_70"


def _hub_for(tf: str, arm_policy: str, arm_rsi_buckets: Optional[List[str]] = None) -> Path:
    buckets = _normalize_arm_rsi_buckets(arm_rsi_buckets)
    if arm_policy and arm_policy != "legacy_date":
        if tf == "1m" and arm_policy == "skip_candidate" and buckets == ["rsi_55_70"]:
            return OUT_ARM_1M
        if tf == "1m" and arm_policy == "skip_candidate" and buckets == ["rsi_with_side"]:
            return OUT_ARM_RSI_SIDE_1M
        rsi_tag = _arm_rsi_tag(buckets)
        return REPO / "live" / "state" / ("usdjpy_fbo_113_atr80_%s_arm_%s_%s_broker" % (rsi_tag, arm_policy, tf.lower()))
    if tf == "1m":
        return OUT_1M
    if tf == "4H":
        return OUT_4H
    return OUT_D


def _dsr_for(tf: str, arm_policy: str, arm_rsi_buckets: Optional[List[str]] = None) -> str:
    buckets = _normalize_arm_rsi_buckets(arm_rsi_buckets)
    if arm_policy == "skip_candidate" and tf == "1m" and buckets == ["rsi_with_side"]:
        return "TRL-2026-00157"
    if arm_policy == "skip_candidate" and tf == "1m":
        return "TRL-2026-00155"
    if arm_policy == "skip_month" and tf == "1m":
        return "TRL-2026-00156"
    if tf == "1m":
        return "TRL-2026-00153"
    if tf == "4H":
        return "TRL-2026-00154"
    return "TRL-2026-00152"


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _append_dsr(tf: str, arm_policy: str, arm_rsi_buckets: Optional[List[str]] = None) -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    if not path.exists():
        return
    buckets = _normalize_arm_rsi_buckets(arm_rsi_buckets)
    trial = _dsr_for(tf, arm_policy, buckets)
    text = path.read_text(encoding="utf-8")
    if trial in text:
        return
    with path.open("r", encoding="utf-8") as fh:
        lines = fh.readlines()
    header_line = next(l for l in lines if l.startswith("trial_id"))
    cols = header_line.strip().split(",")
    row = {c: "" for c in cols}
    rsi_note = "RSI55-70" if buckets == ["rsi_55_70"] else ",".join(buckets)
    row.update(
        {
            "trial_id": trial,
            "entry_date": "2026-08-26",
            "analyst": "cursor",
            "trial_class": "FILTER_OVERLAY",
            "trial_subclass": "%s_%s_%s" % (VARIANT, tf.lower(), arm_policy),
            "parent_trial_id": "TRL-2026-00153",
            "is_independent": "False",
            "market": INSTRUMENT,
            "replay_window_start": "2003-05-06",
            "replay_window_end": "2026-03-31",
            "replay_type": "FULL_SAMPLE",
            "is_oos": "False",
            "parameters_json": json.dumps(
                {
                    "base": "fbo_1_1_3_atr80",
                    "arm_rsi_buckets": buckets,
                    "arm_filter_on_reject": arm_policy,
                    "entry_filter_rearm": False,
                    "feed_tf": tf,
                }
            ),
            "fixed_parameters_ref": str(_hub_for(tf, arm_policy, buckets).relative_to(REPO) / "summary.csv"),
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "False",
            "dsr_weight": "1.00",
            "status": "RUNNING",
            "notes": "Arm-time %s + %s; fill tape=%s (executable HA-near)." % (rsi_note, arm_policy, tf),
            "disclosure_review": "False",
        }
    )
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writerow({c: row.get(c, "") for c in cols})


def build_atr80_filter(output_root: Path) -> Path:
    """atr80-only date CSV (arm-time / optional rearm); RSI is separate."""
    path = output_root / "filters" / "usdjpy_atr80.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    atr = _atr80_ok_by_date()
    rows = [dict(date=d, long_ok=ok, short_ok=ok) for d, ok in sorted(atr.items())]
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def build_arm_rsi_csv(output_root: Path) -> Path:
    """Causal hourly RSI bucket series (same +1h shift as HA profile)."""
    path = output_root / "filters" / "usdjpy_hourly_rsi_causal.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    feats = build_feature_frames(INSTRUMENT)
    h = feats["h1"][["ts", "rsi14", "rsi_bucket"]].dropna(subset=["rsi14"]).copy()
    h = h.sort_values("ts")
    # Write UTC Z timestamps for stable plugin asof.
    out_rows = []
    for _, r in h.iterrows():
        ts = pd.Timestamp(r["ts"])
        if ts.tzinfo is None:
            ts = ts.tz_localize(NY)
        ts_utc = ts.tz_convert("UTC")
        out_rows.append(
            dict(
                ts=ts_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                rsi14=float(r["rsi14"]),
                rsi_bucket=str(r["rsi_bucket"]),
            )
        )
    pd.DataFrame(out_rows).to_csv(path, index=False)
    print("Arm RSI CSV %s rows=%d" % (path, len(out_rows)), flush=True)
    return path


def build_combined_filter(output_root: Path) -> Path:
    """Legacy: atr80 AND RSI day-gate (inflates campaigns under retry). Prefer arm-time."""
    path = output_root / "filters" / "usdjpy_atr80_rsi55_70.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    atr = _atr80_ok_by_date()
    feats = build_feature_frames(INSTRUMENT)
    h = feats["h1"][["ts", "rsi14", "rsi_bucket"]].dropna(subset=["rsi14"]).copy()
    h = h.sort_values("ts")

    daily = pd.read_csv(REPO / "fx" / "usdjpy_daily.csv")
    date_col = "date" if "date" in daily.columns else daily.columns[0]
    dates = [str(x)[:10] for x in daily[date_col].tolist()]
    entry_ts = pd.to_datetime(dates, utc=True).tz_convert(NY)
    left = pd.DataFrame({"date": dates, "entry_ts": entry_ts}).sort_values("entry_ts")
    merged = pd.merge_asof(
        left,
        h.rename(columns={"ts": "feat_ts"}),
        left_on="entry_ts",
        right_on="feat_ts",
        direction="backward",
    )
    rows = []
    n_rsi = 0
    for _, r in merged.iterrows():
        d = str(r["date"])[:10]
        atr_ok = bool(atr.get(d, True))
        rsi_ok = str(r.get("rsi_bucket")) == "rsi_55_70"
        if rsi_ok:
            n_rsi += 1
        ok = atr_ok and rsi_ok
        rows.append(dict(date=d, long_ok=ok, short_ok=ok, atr_ok=atr_ok, rsi_ok=rsi_ok, rsi14=r.get("rsi14")))
    out = pd.DataFrame(rows)
    out[["date", "long_ok", "short_ok"]].to_csv(path, index=False)
    out.to_csv(path.with_name("usdjpy_atr80_rsi55_70_detail.csv"), index=False)
    print(
        "Filter %s: days=%d atr80&rsi55_70=%d rsi_bucket_days=%d"
        % (path, len(out), int(out["long_ok"].sum()), n_rsi),
        flush=True,
    )
    return path


def _atr80_ok_by_date() -> dict:
    prior = (
        REPO
        / "live"
        / "state"
        / "fx_cross_pair_tracker_leaders"
        / "filters"
        / "usdjpy_atr80.csv"
    )
    if prior.exists():
        df = pd.read_csv(prior)
        return {
            str(r["date"])[:10]: str(r["long_ok"]).strip().lower() in {"1", "true", "yes"}
            for _, r in df.iterrows()
        }
    d = pd.read_csv(REPO / "fx" / "usdjpy_daily.csv", parse_dates=["date"])
    d = d.sort_values("date").reset_index(drop=True)
    tr = np.maximum(
        d.high - d.low,
        np.maximum((d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()),
    )
    d["atr14"] = tr.rolling(14).mean()
    d["pctl"] = d.atr14.rolling(500, min_periods=100).rank(pct=True)
    out = {}
    for _, r in d.iterrows():
        ok = True if r.pctl != r.pctl else bool(r.pctl <= 0.80)
        out[r.date.date().isoformat()] = ok
    return out


def _utc_z(ts) -> str:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize(NY).tz_convert("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.isoformat().replace("+00:00", "Z")


def _iter_1m_bars() -> Tuple[Iterable[Bar], List[str], int]:
    path = REPO / "fx" / "usdjpy_1m.csv"
    print("Loading USDJPY 1m by NY date from %s ..." % path, flush=True)
    gby = load_fx_1m_by_ny_date(path, INSTRUMENT)
    ny_days = [d.isoformat() for d in sorted(gby)]

    def _gen():
        for d in sorted(gby):
            frame = gby[d]
            for ts, row in frame.iterrows():
                o = float(row["open"])
                h = float(row["high"])
                l = float(row["low"])
                c = float(row["close"])
                if min(o, h, l, c) <= 0:
                    continue
                yield Bar(
                    instrument=INSTRUMENT,
                    timeframe="1m",
                    ts=_utc_z(ts),
                    open=o,
                    high=h,
                    low=l,
                    close=c,
                    volume=float(row.get("volume", 0.0) or 0.0),
                    complete=True,
                    source=str(path),
                )

    n_bars = int(sum(len(gby[d]) for d in gby))
    print("1m approx bars=%d NY days=%d" % (n_bars, len(ny_days)), flush=True)
    return _gen(), ny_days, n_bars


def _load_4h_bars() -> Tuple[List[Bar], List[str]]:
    path = REPO / "fx" / "usdjpy_4h.csv"
    raw = bars_from_csv(path, INSTRUMENT, "4H", source=str(path))
    out: List[Bar] = []
    days = set()
    for b in raw:
        ts = pd.Timestamp(str(b.ts).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        day = ts.tz_convert(NY).date().isoformat()
        days.add(day)
        out.append(
            Bar(
                instrument=b.instrument,
                timeframe="4H",
                ts=_utc_z(ts),
                open=b.open,
                high=b.high,
                low=b.low,
                close=b.close,
                volume=b.volume,
                complete=True,
                source=str(path),
            )
        )
    return out, sorted(days)


def _month_end_from_ny_days(ny_days: List[str]) -> List[str]:
    last_by_month: Dict[str, str] = {}
    for day in ny_days:
        last_by_month[day[:7]] = day
    return [last_by_month[k] for k in sorted(last_by_month)]


def _spec(
    filt: Path,
    feed_tf: str,
    *,
    arm_policy: str = "legacy_date",
    arm_rsi_csv: Optional[Path] = None,
    arm_rsi_buckets: Optional[List[str]] = None,
) -> BrokerReplaySpec:
    buckets = _normalize_arm_rsi_buckets(arm_rsi_buckets)
    cfg = {
        "allow_shorts": True,
        "or_sessions": 3,
        "max_trades_per_month": 2,
        "entry_qty": 5,
        "tp1_qty": 1,
        "tp2_qty": 1,
        "tp1_r": 0.25,
        "tp2_r": 1.0,
        "runner_r": 2.0,
        "be_after": "tp1",
        "entry_mode": "first_break_opposite",
        "stop_mode": "close",
        "flip_after_stop": False,
        "eod_stop_to_or_mid": False,
        "record_levels": False,
        "entry_filter_csv": str(filt),
        "feed_timeframe": feed_tf,
        "flatten_month_end": True,
    }
    if arm_policy != "legacy_date":
        cfg["entry_filter_rearm"] = False
        cfg["arm_rsi_buckets"] = buckets
        cfg["arm_rsi_csv"] = str(arm_rsi_csv) if arm_rsi_csv else None
        cfg["arm_filter_on_reject"] = arm_policy
        rsi_label = "RSI-with-side" if buckets == ["rsi_with_side"] else "RSI55-70"
        slug = "%s_arm_%s_%s" % (VARIANT, arm_policy, feed_tf.lower())
        if buckets == ["rsi_with_side"]:
            slug = "fbo_1_1_3_atr80_rsi_with_side_usdjpy_arm_%s_%s" % (arm_policy, feed_tf.lower())
        name = "USDJPY FBO atr80 arm-%s %s (%s)" % (rsi_label, arm_policy, feed_tf)
        notes = (
            "Executable HA-near: atr80 CSV at arm only (no rearm); "
            "causal hourly %s at arm; on reject=%s; feed=%s."
            % (rsi_label, arm_policy, feed_tf)
        )
    else:
        slug = VARIANT if feed_tf == "D" else "%s_%s" % (VARIANT, feed_tf.lower())
        name = "USDJPY FBO 1/1/3 atr80 RSI55-70 (%s)" % feed_tf
        notes = "Legacy date AND RSI day-gate; feed=%s." % feed_tf
    return BrokerReplaySpec(
        name=name,
        slug=slug,
        strategy_type="monthly_orb_v2b_oco",
        max_contracts=5,
        config=cfg,
        notes=notes,
    )


def _campaign_wr(fills: pd.DataFrame, pv: float, fee: float):
    fills = fills.copy()
    fills["ts"] = pd.to_datetime(fills["ts"])
    pnls = []
    for _, g in fills.groupby("trade_id"):
        g = g.sort_values("ts")
        e = g[g.reason == "entry"]
        if e.empty:
            continue
        e = e.iloc[0]
        pnl = -fee * float(e.quantity)
        for _, r in g[g.reason != "entry"].iterrows():
            pts = (r.price - e.price) * r.quantity if e.side == "buy" else (e.price - r.price) * r.quantity
            pnl += pts * pv - fee * float(r.quantity)
        pnls.append(pnl)
    a = np.array(pnls, float)
    return len(a), (100.0 * (a > 0).mean() if len(a) else 0.0)


def _flush_intraday(engine: Engine, plugin) -> None:
    if plugin is None or not hasattr(plugin, "flush_intraday_day"):
        return
    context = engine.manager._context(plugin.instance)
    actions = plugin.flush_intraday_day(context)
    engine.manager._apply_actions(plugin.instance, actions)


def run(
    output_root: Path,
    *,
    feed_tf: str = "1m",
    arm_policy: str = "skip_candidate",
    arm_rsi_buckets: Optional[List[str]] = None,
    force: bool = False,
    do_email: bool = False,
) -> Path:
    feed_tf = feed_tf.strip()
    if feed_tf.lower() in {"1m", "1min"}:
        feed_tf = "1m"
    elif feed_tf.lower() in {"4h", "4hour"}:
        feed_tf = "4H"
    elif feed_tf.lower() in {"d", "1d", "daily"}:
        feed_tf = "D"
    else:
        raise SystemExit("unsupported --tf %s (use 1m|4h|D)" % feed_tf)

    arm_policy = str(arm_policy or "skip_candidate").strip().lower()
    buckets = _normalize_arm_rsi_buckets(arm_rsi_buckets)
    if arm_policy in {"legacy", "legacy_date", "date"}:
        arm_policy = "legacy_date"
    elif arm_policy not in {"skip_candidate", "skip_month", "retry"}:
        raise SystemExit("unsupported --arm-policy %s" % arm_policy)

    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / "PROGRESS.log").write_text("", encoding="utf-8")
    dsr = _dsr_for(feed_tf, arm_policy, buckets)
    _append_dsr(feed_tf, arm_policy, buckets)
    POINT_VALUES[INSTRUMENT] = 100000.0
    DEFAULT_TICK_SIZE[INSTRUMENT] = TICK

    if arm_policy == "legacy_date":
        filt = build_combined_filter(output_root)
        arm_rsi = None
    else:
        filt = build_atr80_filter(output_root)
        arm_rsi = build_arm_rsi_csv(output_root)
    spec = _spec(filt, feed_tf, arm_policy=arm_policy, arm_rsi_csv=arm_rsi, arm_rsi_buckets=buckets)
    sid = spec.slug
    state_root = output_root / "states" / sid

    rid = begin_run(
        run_class="broker_like",
        variant_slug=sid,
        instrument=INSTRUMENT,
        hub_path=str(output_root),
        dsr_trial_id=dsr,
        notes="FBO atr80 arm-%s %s; feed=%s" % (_arm_rsi_tag(buckets), arm_policy, feed_tf),
        meta={
            "filter": "arm_%s" % _arm_rsi_tag(buckets),
            "arm_rsi_buckets": buckets,
            "arm_policy": arm_policy,
            "feed_tf": feed_tf,
            "structure": "1/1/3",
        },
    )
    try:
        if force and state_root.exists():
            shutil.rmtree(state_root)

        if feed_tf == "1m":
            bar_iter, ny_days, n_bars = _iter_1m_bars()
            month_ends = _month_end_from_ny_days(ny_days)
            audit_bars = bars_from_csv(REPO / "fx" / "usdjpy_4h.csv", INSTRUMENT, "4H")
            audit_src = REPO / "fx" / "usdjpy_4h.csv"
            persist_bars = False
            instance_tf = "1m"
            first_ts = last_ts = ""
        elif feed_tf == "4H":
            bars, ny_days = _load_4h_bars()
            bar_iter = bars
            n_bars = len(bars)
            month_ends = _month_end_from_ny_days(ny_days)
            audit_bars = bars
            audit_src = REPO / "fx" / "usdjpy_4h.csv"
            persist_bars = False
            instance_tf = "4H"
            first_ts = bars[0].ts if bars else ""
            last_ts = bars[-1].ts if bars else ""
        else:
            daily_path = REPO / "fx" / "usdjpy_daily.csv"
            bars = bars_from_csv(daily_path, INSTRUMENT, "D", source=str(daily_path))
            bar_iter = bars
            n_bars = len(bars)
            month_ends = _month_end_dates(bars)
            audit_bars = bars
            audit_src = daily_path
            persist_bars = True
            instance_tf = "D"
            ny_days = [str(b.ts)[:10] for b in bars]
            first_ts = bars[0].ts
            last_ts = bars[-1].ts

        cfg = dict(spec.config)
        cfg["month_end_dates"] = month_ends
        cfg["feed_timeframe"] = feed_tf

        _progress(output_root, "START feed=%s bars≈%d month_ends=%d" % (feed_tf, n_bars, len(month_ends)))
        store = FlatFileStore(state_root, defer_table_writes=True)
        store.ensure()
        inst = StrategyInstance(
            strategy_id=sid,
            strategy_type=spec.strategy_type,
            version="v1",
            instrument=INSTRUMENT,
            broker_instrument=INSTRUMENT,
            account_mode="paper",
            enabled=True,
            timeframes=instance_tf,
            max_contracts=5,
            max_open_orders=64,
            config_json=json.dumps(cfg, sort_keys=True),
        )
        store.upsert_row("strategy_instances", "strategy_id", as_row(inst))
        engine = Engine(
            store=store,
            slippage_ticks=1.0,
            tick_size={INSTRUMENT: TICK},
            persist_bars=persist_bars,
            persist_health=False,
        )
        step = max(1, n_bars // 20)
        i = 0
        for bar in bar_iter:
            if i == 0:
                first_ts = bar.ts
            last_ts = bar.ts
            engine.process_bar(bar)
            i += 1
            if i % step == 0:
                _progress(
                    output_root,
                    "  bar %d/%d (%.0f%%) ts=%s" % (i, n_bars, 100.0 * i / max(n_bars, 1), bar.ts),
                )
        plugin = engine.manager.plugins.get(sid)
        _flush_intraday(engine, plugin)
        store.flush_tables()
        last_day = ny_days[-1] if ny_days else str(last_ts)[:10]
        generate_market_close_report(store, last_day)

        fills_path = state_root / "fills.csv"
        if not fills_path.exists() or fills_path.stat().st_size < 10:
            raise RuntimeError("no fills written")
        last_audit = audit_bars[-1]
        units = units_from_live_fills(fills_path, sid, last_audit.ts, last_audit.close)
        # Align 4H audit bar timeframe tag if needed
        if feed_tf == "1m":
            audit_bars = [
                Bar(
                    instrument=b.instrument,
                    timeframe="4H",
                    ts=b.ts,
                    open=b.open,
                    high=b.high,
                    low=b.low,
                    close=b.close,
                    volume=b.volume,
                    complete=True,
                    source=str(audit_src),
                )
                for b in audit_bars
            ]
        audit = audit_units(
            name=spec.name,
            slug=sid,
            source=fills_path,
            bar_source=audit_src,
            bars=audit_bars,
            units=units,
            instrument=INSTRUMENT,
            notes=spec.notes + " audit_tf=%s" % ("4H" if feed_tf == "1m" else feed_tf),
            output_root=output_root / "audits",
            fee_per_unit=FEE,
        )
        n, wr = _campaign_wr(pd.read_csv(fills_path), 100000.0, FEE)
        ns = audit.net_usd / abs(audit.intrabar_mtm_dd_usd) if audit.intrabar_mtm_dd_usd else 0.0
        net_usd = audit.net_usd / JPY_USD
        stress_usd = audit.intrabar_mtm_dd_usd / JPY_USD
        close_usd = audit.close_mtm_dd_usd / JPY_USD

        base_ns, base_net = 4.25, 108000.0
        base = REPO / "live" / "state" / "fx_cross_pair_tracker_leaders" / "summary.csv"
        if base.exists():
            df = pd.read_csv(base)
            hit = df[(df.pair == "USDJPY") & (df.variant == "1_1_3_atr80")]
            if len(hit):
                base_ns = float(hit.iloc[0]["ns"])
                base_net = float(hit.iloc[0]["net_usd_approx"])

        if ns >= base_ns and net_usd > 0 and n >= 20:
            stance = "promote-candidate vs atr80 baseline"
        elif ns >= 1.5 and net_usd > 0:
            stance = "retain/research — HA filter broker check"
        elif net_usd > 0:
            stance = "weak — prefer unfiltered atr80"
        else:
            stance = "reject"

        ha_paper_n = 95 if buckets == ["rsi_with_side"] else 38
        rsi_label = "rsi_with_side (long RSI≥55 / short RSI≤45)" if buckets == ["rsi_with_side"] else "RSI 55–70"
        variant_slug = "1_1_3_atr80_rsi_with_side" if buckets == ["rsi_with_side"] else "1_1_3_atr80_rsi55_70"
        row = {
            "variant": variant_slug,
            "arm_rsi_buckets": ",".join(buckets),
            "arm_policy": arm_policy,
            "feed_tf": feed_tf,
            "audit_tf": "4H" if feed_tf == "1m" else feed_tf,
            "instrument": INSTRUMENT,
            "campaigns": n,
            "wr": round(wr, 1),
            "trades": audit.trades,
            "units": audit.units,
            "net_jpy": round(audit.net_usd, 2),
            "stress_jpy": round(audit.intrabar_mtm_dd_usd, 2),
            "ns": round(ns, 2),
            "net_usd_approx": round(net_usd, 2),
            "stress_usd_approx": round(stress_usd, 2),
            "baseline_atr80_net_usd": base_net,
            "baseline_atr80_ns": base_ns,
            "ha_paper_n": ha_paper_n,
            "stance": stance,
        }
        with (output_root / "summary.csv").open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(row.keys()))
            w.writeheader()
            w.writerow(row)

        lines = [
            "# USDJPY FBO atr80 × %s — arm-time %s (feed=%s)" % (rsi_label, arm_policy, feed_tf),
            "",
            "Executable HA-near path: **arm-time** causal hourly %s + atr80. "
            "On reject: **%s**. PaperBroker fills on **%s**; MTM audit on **%s**. "
            "Paper HA sleeve was post-hoc n=%d — not a target to reproduce exactly."
            % (rsi_label, arm_policy, feed_tf, row["audit_tf"], ha_paper_n),
            "",
            "| Variant | Campaigns | WR | Net≈USD | Stress≈USD | N/S | Stance |",
            "|---|---:|---:|---:|---:|---:|---|",
            "| **arm %s (%s)** | %d | %.1f%% | **$%.0f** | $%.0f | **%.2f** | %s |"
            % (arm_policy, feed_tf, n, wr, net_usd, stress_usd, ns, stance),
            "| legacy date-gate 1m | 102 | 49.0%% | $58554 | $-43666 | 1.34 | weak |",
            "| baseline atr80 daily | 156 | 50.6%% | $%.0f | — | %.2f | banked |"
            % (base_net, base_ns),
            "| HA paper filter (post-hoc) | %d | — | — | — | — | diagnostic |" % ha_paper_n,
            "",
            "Hub: `%s`" % output_root,
            "Filter atr80: `%s`" % filt,
            "Arm RSI CSV: `%s`" % (arm_rsi or "—"),
            "DSR: %s" % dsr,
            "",
        ]
        summary = "\n".join(lines)
        (output_root / "SUMMARY.md").write_text(summary, encoding="utf-8")
        (output_root / "EMAIL.txt").write_text(summary, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "row": row}, indent=2) + "\n", encoding="utf-8"
        )
        write_run_manifest(
            output_root,
            data_inputs=[filt, REPO / "fx" / "usdjpy_1m.csv" if feed_tf == "1m" else REPO / "fx" / "usdjpy_4h.csv"],
            output_paths=[output_root / "summary.csv", output_root / "SUMMARY.md"],
            broker_realism_config={"slippage_ticks": 1.0, "fee_per_unit": FEE, "tick_size": TICK, "feed_tf": feed_tf},
            causality_mode="audit",
            extra={"driver": "usdjpy_fbo_113_atr80_rsi55_70_broker", "dsr": dsr, "feed_tf": feed_tf},
        )
        complete_run(
            rid,
            net_usd=net_usd,
            stress_dd_usd=stress_usd,
            close_mtm_dd_usd=close_usd,
            ns=ns,
            trades=n,
            units=audit.units,
            replay_start=ny_days[0] if ny_days else str(first_ts)[:10],
            replay_end=ny_days[-1] if ny_days else str(last_ts)[:10],
            meta={"stance": stance, "wr": wr, "feed_tf": feed_tf, "arm_policy": arm_policy, "arm_rsi_buckets": buckets},
        )
        _progress(output_root, "DONE n=%d WR=%.1f net≈$%.0f N/S=%.2f" % (n, wr, net_usd, ns))
        print(summary, flush=True)
        if do_email:
            send_email(
                subject="potions: USDJPY FBO arm-%s %s %s complete" % (_arm_rsi_tag(buckets), arm_policy, feed_tf),
                body=summary,
            )
        return output_root / "SUMMARY.md"
    except Exception as exc:
        fail_run(rid, notes=str(exc))
        tb = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % tb)
        if do_email:
            send_email(
                subject="potions: USDJPY FBO arm-%s %s %s FAILED" % (_arm_rsi_tag(buckets), arm_policy, feed_tf),
                body=tb[-4000:],
            )
        raise


def main(argv: Optional[list] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tf", default="1m", help="Fill tape: 1m (default) | 4h | D")
    p.add_argument(
        "--arm-policy",
        default="skip_candidate",
        help="skip_candidate (default) | skip_month | retry | legacy_date",
    )
    p.add_argument(
        "--arm-rsi-buckets",
        default="rsi_55_70",
        help="Arm-time RSI allow-list: rsi_55_70 (default) | rsi_with_side",
    )
    p.add_argument("--output-root", type=Path, default=None)
    p.add_argument("--force", action="store_true")
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    tf = args.tf
    tf_norm = "1m" if tf.lower() in {"1m", "1min"} else ("4H" if tf.lower().startswith("4") else "D")
    policy = args.arm_policy
    buckets = _normalize_arm_rsi_buckets(args.arm_rsi_buckets)
    out = args.output_root or _hub_for(tf_norm, policy, buckets)
    try:
        run(out, feed_tf=tf, arm_policy=policy, arm_rsi_buckets=buckets, force=args.force, do_email=args.email)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())