"""CHOP20 boundary60 causal entry — NAS100 / US30 / FX / metals.

Same contract as NQ/MNQ causal variants:

  daily CHOP20 + close breakout = signal only
  available_at = last 1m of NY calendar day (matches fx/*_daily.csv close)
  close_to_globex   — first 1m with ts > available_at
  close_to_next_rth — NAS100/US30/SPX500: next US cash 09:30; FX/metals: first bar of next NY day
  fill = entry open ±1 tick adverse; stop-first 1m; age≤60; 0.5R/1R/4R

Default run is **baseline only**. Post-run ``DATE_WINDOW.md`` scores year
blocks + start-date trims (filter before re-running). HP gates come from the
HA mill on promising baselines, then re-sim here.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.chop20_dynamic_range_causal_entry_fx_metals --email
  python -m live.chop20_dynamic_range_causal_entry_fx_metals --email --smoke
  python -m live.chop20_dynamic_range_causal_entry_fx_metals --email --markets nas100,xauusd
  python -m live.chop20_dynamic_range_causal_entry_fx_metals --email --hp-from-hub
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import traceback
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .fx_data import load_fx_1m_by_ny_date
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"
sys.path[:0] = [str(SCRIPTS)]

from chop_range_breakout_charts import DetectorParams, add_range_metrics, load_bars  # noqa: E402

from . import chop20_dynamic_range_causal_entry_variants as core

HUB = REPO / "live" / "state" / "chop20_dynamic_range_causal_entry_fx_metals"
DSR = "TRL-2026-00182"
SESSION_MODE = "ny_day"
ENTRY_MODES = ("close_to_globex", "close_to_next_rth")
DEFAULT_MARKETS = ("nas100", "us30", "usdjpy", "gbpusd", "xauusd", "xagusd")

YEAR_BLOCKS: Tuple[Tuple[int, int], ...] = (
    (2003, 2010),
    (2011, 2015),
    (2016, 2019),
    (2020, 2022),
    (2023, 2026),
)


@dataclass(frozen=True)
class FxMarket:
    key: str
    symbol: str
    family: str  # cfd | fx | metal
    daily: Path
    one_m: Path
    point_value: float
    tick_size: float
    fee: float
    pnl_ccy: str  # USD | JPY


MARKETS: Dict[str, FxMarket] = {
    "nas100": FxMarket(
        "nas100", "NAS100", "cfd", REPO / "fx" / "nas100_daily.csv", REPO / "fx" / "nas100_1m.csv", 1.0, 0.1, 1.50, "USD"
    ),
    "us30": FxMarket(
        "us30", "US30", "cfd", REPO / "fx" / "us30_daily.csv", REPO / "fx" / "us30_1m.csv", 1.0, 0.1, 1.50, "USD"
    ),
    "usdjpy": FxMarket(
        "usdjpy",
        "USDJPY",
        "fx",
        REPO / "fx" / "usdjpy_daily.csv",
        REPO / "fx" / "usdjpy_1m.csv",
        100_000.0,
        0.001,
        1.50,
        "JPY",
    ),
    "gbpusd": FxMarket(
        "gbpusd",
        "GBPUSD",
        "fx",
        REPO / "fx" / "gbpusd_daily.csv",
        REPO / "fx" / "gbpusd_1m.csv",
        100_000.0,
        0.00001,
        7.0,
        "USD",
    ),
    "xauusd": FxMarket(
        "xauusd",
        "XAUUSD",
        "metal",
        REPO / "fx" / "xauusd_daily.csv",
        REPO / "fx" / "xauusd_1m.csv",
        100.0,
        0.01,
        1.50,
        "USD",
    ),
    "xagusd": FxMarket(
        "xagusd",
        "XAGUSD",
        "metal",
        REPO / "fx" / "xagusd_daily.csv",
        REPO / "fx" / "xagusd_1m.csv",
        1000.0,
        0.001,
        1.50,
        "USD",
    ),
    "spx500": FxMarket(
        "spx500",
        "SPX500",
        "cfd",
        REPO / "fx" / "spx500_daily.csv",
        REPO / "fx" / "spx500_1m.csv",
        1.0,
        0.1,
        1.50,
        "USD",
    ),
}


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    hub.mkdir(parents=True, exist_ok=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")


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
            "trial_class": "FILTER_EXPLORATION",
            "trial_subclass": "chop20_causal_entry_fx_metals",
            "is_independent": "TRUE",
            "market": "NAS100,US30,USDJPY,GBPUSD,XAUUSD,XAGUSD",
            "replay_type": "FULL_HISTORY",
            "is_oos": "FALSE",
            "parameters_json": json.dumps(
                {
                    "variant": core.VARIANT.name,
                    "entry_modes": list(ENTRY_MODES),
                    "session_mode": SESSION_MODE,
                    "targets_r": [0.5, 1.0, 4.0],
                    "fill_tape": "1m",
                    "same_bar": "stop_first",
                    "markets": list(DEFAULT_MARKETS),
                }
            ),
            "fixed_parameters_ref": "live/chop20_dynamic_range_causal_entry_fx_metals.py",
            "num_params_varied": "1",
            "counts_toward_dsr": "TRUE",
            "counts_toward_permutation_test": "FALSE",
            "dsr_weight": "1.00",
            "status": "PENDING",
            "notes": "CHOP20 causal entry baseline (+ optional HP) on FX/metals/index CFD",
            "disclosure_review": "FALSE",
        }
    )
    with path.open("a", newline="") as fh:
        csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore").writerow(row)


def _mark_dsr(status: str = "COMPLETE") -> None:
    path = REPO / "data" / "validation" / "dsr_trial_ledger.csv"
    out = []
    for ln in path.read_text().splitlines():
        if ln.startswith(DSR + ",") and ",PENDING," in ln:
            ln = ln.replace(",PENDING,", ",%s," % status, 1)
        out.append(ln)
    path.write_text("\n".join(out) + "\n")


def build_daily(m: FxMarket) -> pd.DataFrame:
    bars = load_bars(m.daily, "D")
    return add_range_metrics(bars, DetectorParams())


def _load_hourly(m: FxMarket) -> Optional[pd.DataFrame]:
    try:
        from .chop20_dynamic_range_ha_conditions import _seed_daily_cache
        from .intraday_condition_profile import build_feature_frames
    except Exception:
        return None
    try:
        # Extend HA daily map for FX symbols if needed.
        from . import chop20_dynamic_range_ha_conditions as ha

        if m.symbol not in ha.DAILY_CSV:
            ha.DAILY_CSV[m.symbol] = m.daily
        _seed_daily_cache(m.symbol)
        feats = build_feature_frames(m.symbol)
        return feats["h1"][["ts", "rsi14", "rsi_bucket"]].sort_values("ts")
    except Exception as exc:
        print("  hourly feat load failed for %s: %s" % (m.symbol, exc), flush=True)
        return None


def _hp_specs(
    market: str,
    extra: Sequence[Tuple[str, Optional[Tuple[str, object]], str]],
) -> List[Tuple[str, Optional[Tuple[str, object]], str]]:
    out: List[Tuple[str, Optional[Tuple[str, object]], str]] = [
        ("baseline", None, "no HP gate"),
    ]
    for label, gate, note in extra:
        if label == "baseline":
            continue
        out.append((label, gate, note))
    return out


def run_market(
    market: str,
    hub: Path,
    *,
    smoke: bool,
    hp_extra: Sequence[Tuple[str, Optional[Tuple[str, object]], str]] = (),
    entry_modes: Sequence[str] = ENTRY_MODES,
    atr_edges: Optional[Sequence[float]] = None,
    include_baseline: bool = True,
    skip_existing: bool = True,
) -> List[dict]:
    mkey = market.lower()
    cfg = MARKETS[mkey]
    summaries: List[dict] = []
    _progress(hub, "Loading %s daily + CHOP20 …" % cfg.symbol)
    daily = build_daily(cfg)
    if smoke:
        daily = daily.tail(350).reset_index(drop=True)
    _progress(
        hub,
        "  %s daily bars=%d (%s → %s)"
        % (
            cfg.symbol,
            len(daily),
            core._date_s(daily.iloc[0]["date"]),
            core._date_s(daily.iloc[-1]["date"]),
        ),
    )
    _progress(hub, "Loading %s 1m …" % cfg.symbol)
    gby = load_fx_1m_by_ny_date(cfg.one_m, cfg.symbol)
    if smoke:
        keep = set(pd.to_datetime(daily["date"]).dt.date.tolist())
        last = max(keep)
        for i in range(1, 8):
            keep.add(last + timedelta(days=i))
        gby = {d: v for d, v in gby.items() if d in keep or any(abs((d - x).days) <= 5 for x in keep)}
    _progress(hub, "  %s 1m sessions=%d" % (cfg.symbol, len(gby)))
    hp_feats = _load_hp_feats(cfg) if any(x[0] != "baseline" for x in hp_extra) else None
    h1 = None
    if hp_feats is not None:
        h1 = hp_feats.get("h1")
    elif any(x[0] != "baseline" for x in hp_extra):
        h1 = _load_hourly(cfg)
    # atr_edges passed in from hub HA campaigns (static quartile edges)
    if h1 is None and any(x[0] != "baseline" for x in hp_extra):
        h1 = _load_hourly(cfg)

    for entry_mode in entry_modes:
        specs = _hp_specs(mkey, hp_extra)
        if include_baseline and not any(s[0] == "baseline" for s in specs):
            specs = [("baseline", None, "no HP gate")] + list(specs)
        if not include_baseline:
            specs = [s for s in specs if s[0] != "baseline"]
        for hp_label, hp_gate, _note in specs:
            slug = "%s__%s__%s" % (mkey, entry_mode, hp_label)
            out = hub / slug
            if skip_existing and (out / "summary.csv").exists() and (out / "trades.csv").exists():
                _progress(hub, "SKIP existing %s" % slug)
                try:
                    summaries.append(pd.read_csv(out / "summary.csv").iloc[0].to_dict())
                except Exception:
                    pass
                continue
            out.mkdir(parents=True, exist_ok=True)
            rid = begin_run(
                run_class="pandas",
                variant_slug=slug,
                instrument=cfg.symbol,
                hub_path=str(out.relative_to(REPO)),
                dsr_trial_id=DSR,
                meta={
                    "entry_mode": entry_mode,
                    "hp_label": hp_label,
                    "session_mode": SESSION_MODE,
                    "family": cfg.family,
                    "pnl_ccy": cfg.pnl_ccy,
                    "fill_tape": "1m",
                    "same_bar": "stop_first",
                },
            )
            try:
                need_h1 = hp_gate is not None
                feats = h1 if need_h1 else h1
                if need_h1 and feats is None:
                    feats = _load_hourly(cfg)
                    h1 = feats
                trades, exits, equity = core.simulate_1m(
                    daily,
                    gby,
                    hub=hub,
                    market=mkey,
                    entry_mode=entry_mode,
                    hp_label=hp_label,
                    hp_gate=hp_gate,
                    h1=feats,
                    point_value=cfg.point_value,
                    tick_size=cfg.tick_size,
                    fee_per_unit=cfg.fee,
                    session_mode=SESSION_MODE,
                                    hp_feats=hp_feats,
                    atr_edges=atr_edges,
                )
                summary = core._summarize(mkey, entry_mode, hp_label, trades, exits, equity)
                summary["family"] = cfg.family
                summary["pnl_ccy"] = cfg.pnl_ccy
                summary["session_mode"] = SESSION_MODE
                trades.to_csv(out / "trades.csv", index=False)
                exits.to_csv(out / "unit_exits.csv", index=False)
                equity.to_csv(out / "equity_curve.csv", index=False)
                pd.DataFrame([summary]).to_csv(out / "summary.csv", index=False)
                complete_run(
                    rid,
                    net_usd=summary["net_usd"],
                    stress_dd_usd=summary["mtm_drawdown"],
                    close_mtm_dd_usd=summary["closed_drawdown"],
                    ns=summary["net_stress"],
                    trades=summary["trades"],
                    units=summary["units"],
                    equity_curve_path=out / "equity_curve.csv",
                    notes="fx/metals causal entry 1m path",
                    meta=summary,
                )
                summaries.append(summary)
                _progress(
                    hub,
                    "DONE %s net=%+.0f %s N/S=%.2f trades=%d causal=%d/%d"
                    % (
                        slug,
                        summary["net_usd"],
                        cfg.pnl_ccy,
                        summary["net_stress"],
                        summary["trades"],
                        summary["causal_available_before_entry"],
                        summary["trades"],
                    ),
                )
            except Exception:
                err = traceback.format_exc()
                fail_run(rid, notes=err[-1500:])
                raise
    return summaries


def analyze_date_windows(hub: Path, rows: List[dict]) -> str:
    """Post-run year-block + start-date trim filter (no re-sim yet)."""
    lines = [
        "# CHOP20 causal FX/metals — date-window post filter",
        "",
        "Generated: %s" % datetime.now().isoformat(timespec="seconds"),
        "",
        "Method: subset the finished baseline `trades.csv` by entry year.",
        "This is a **post-run filter** — recommended windows need a fresh re-sim",
        "before promotion (do not cherry-pick mid-stream).",
        "",
    ]
    recs: List[dict] = []
    for r in rows:
        if r.get("hp_label") != "baseline":
            continue
        if r.get("entry_mode") != "close_to_globex":
            continue
        m = str(r["market"]).lower()
        slug = "%s__close_to_globex__baseline" % m
        tpath = hub / slug / "trades.csv"
        if not tpath.exists():
            continue
        t = pd.read_csv(tpath)
        if t.empty:
            lines += ["## %s — empty tape" % r["market"], ""]
            continue
        t["entry_ts"] = pd.to_datetime(t["entry_ts"], utc=True)
        t["year"] = t["entry_ts"].dt.year
        full_net = float(t["net_usd"].sum())
        full_n = len(t)
        # Approximate stress from equity if present
        eq_path = hub / slug / "equity_curve.csv"
        full_ns = float(r.get("net_stress") or 0.0)
        lines += [
            "## %s / close_to_globex baseline" % r["market"],
            "",
            "Full: n=%d net=%+.0f %s N/S=%.2f"
            % (full_n, full_net, r.get("pnl_ccy", "USD"), full_ns),
            "",
            "### Year blocks",
            "",
            "| block | n | net | WR | share_net |",
            "|---|---:|---:|---:|---:|",
        ]
        for y0, y1 in YEAR_BLOCKS:
            sub = t[(t["year"] >= y0) & (t["year"] <= y1)]
            if sub.empty:
                lines.append("| %d–%d | 0 | — | — | — |" % (y0, y1))
                continue
            net = float(sub["net_usd"].sum())
            wr = 100.0 * float((sub["net_usd"] > 0).mean())
            share = net / full_net if full_net else 0.0
            lines.append(
                "| %d–%d | %d | %+.0f | %.0f%% | %.0f%% |"
                % (y0, y1, len(sub), net, wr, 100.0 * share)
            )
        lines += ["", "### Start-date trims (keep entry_ts ≥ year-start)", "", "| start | n | net | vs full |", "|---|---:|---:|---:|"]
        best_start = None
        best_score = None
        years = sorted(t["year"].unique())
        for y in years:
            sub = t[t["year"] >= y]
            if len(sub) < max(8, full_n // 5):
                continue
            net = float(sub["net_usd"].sum())
            # Prefer higher net with enough N; flag if early years drag
            score = net
            if best_score is None or score > best_score:
                best_score = score
                best_start = int(y)
            delta = net - full_net
            lines.append("| %d | %d | %+.0f | %+.0f |" % (y, len(sub), net, delta))
        stance = "keep full history"
        if best_start is not None and best_start > int(years[0]) and best_score is not None:
            lift = best_score - full_net
            # Only recommend move if early trim lifts net materially and keeps ≥40% trades
            sub = t[t["year"] >= best_start]
            if lift > 0.15 * abs(full_net) and len(sub) >= max(12, int(0.4 * full_n)):
                stance = "research re-sim from %d-01-01 (post-filter lift %+0.f)" % (best_start, lift)
            elif full_ns < 1.0 and lift > 0:
                stance = "weak full-sample — optional research window from %d" % best_start
        lines += ["", "**Window stance:** %s" % stance, ""]
        recs.append(
            {
                "market": r["market"],
                "full_n": full_n,
                "full_net": full_net,
                "full_ns": full_ns,
                "recommended_start": best_start,
                "stance": stance,
            }
        )
    if recs:
        pd.DataFrame(recs).to_csv(hub / "date_window_recs.csv", index=False)
    lines += ["Hub: `%s`" % hub, ""]
    text = "\n".join(lines)
    (hub / "DATE_WINDOW.md").write_text(text)
    return text


def _write_summary(hub: Path, rows: List[dict], *, smoke: bool) -> str:
    board = pd.DataFrame(rows)
    board.to_csv(hub / "summary_board.csv", index=False)
    lines = [
        "# CHOP20 boundary60 — Causal entry FX / metals / index CFD",
        "",
        "Generated: %s" % datetime.now().isoformat(timespec="seconds"),
        "Smoke: %s" % smoke,
        "DSR: %s" % DSR,
        "",
        "## Contract",
        "",
        "- Daily CHOP20 + close breakout = **signal only**.",
        "- `available_at` = last NY-calendar 1m (matches `fx/*_daily.csv`).",
        "- **close_to_globex**: first 1m with `ts > available_at`.",
        "- **close_to_next_rth**: NAS100/US30/SPX500 → next US cash 09:30; FX/metals → first bar next NY day.",
        "- Fill = entry-bar open ±1 tick adverse; stop-first; age≤60; 0.5R/1R/4R.",
        "- USDJPY net is **JPY** (PV=100k); use N/S for cross-market compare.",
        "",
        "## Board",
        "",
        "| market | family | mode | hp | trades | net | ccy | MTM DD | N/S | WR | causal |",
        "|---|---|---|---|---:|---:|---|---:|---:|---:|---:|",
    ]
    for _, r in board.sort_values(["market", "entry_mode", "hp_label"]).iterrows():
        lines.append(
            "| %s | %s | %s | %s | %d | %+.0f | %s | %+.0f | %.2f | %.0f%% | %d/%d |"
            % (
                r["market"],
                r.get("family", ""),
                r["entry_mode"],
                r["hp_label"],
                int(r["trades"]),
                float(r["net_usd"]),
                r.get("pnl_ccy", "USD"),
                float(r["mtm_drawdown"]),
                float(r["net_stress"]),
                float(r["win_rate"]),
                int(r["causal_available_before_entry"]),
                int(r["trades"]),
            )
        )
    base = board[(board["hp_label"] == "baseline") & (board["entry_mode"] == "close_to_globex")]
    lines += ["", "## Stance", ""]
    promising = []
    for _, r in base.iterrows():
        ok = int(r["causal_available_before_entry"]) == int(r["trades"]) and int(r["trades"]) > 0
        ns = float(r["net_stress"])
        flag = "research" if ns >= 1.5 and int(r["trades"]) >= 20 and float(r["net_usd"]) > 0 else "weak/reject"
        if flag == "research":
            promising.append(str(r["market"]))
        lines.append(
            "- **%s baseline globex**: net=%+.0f %s N/S=%.2f n=%d — %s; timing %s"
            % (
                r["market"],
                float(r["net_usd"]),
                r.get("pnl_ccy", "USD"),
                ns,
                int(r["trades"]),
                flag,
                "PASS" if ok else "FAIL",
            )
        )
    lines += [
        "",
        "- Promising for HA mill / HP re-sim: %s" % (", ".join(promising) if promising else "(none)"),
        "- Date-window post filter: see `DATE_WINDOW.md` before re-running trimmed starts.",
        "- StrategyPlugin port: only after one market clears causal baseline + window stance.",
        "",
        "Hub: `%s`" % hub,
        "",
    ]
    text = "\n".join(lines)
    (hub / "SUMMARY.md").write_text(text)
    (hub / "EMAIL.txt").write_text(text)
    return text


def _condition_to_gate(condition: str, bucket) -> Optional[Tuple[str, object]]:
    """Map HA profile/overlay condition title + bucket → (_hp_at key, value)."""
    cond = str(condition).strip()
    b = bucket
    mapping = {
        "Hourly RSI bucket": "rsi_bucket",
        "Hourly RSI vs trade": "rsi_align",
        "Week of month": "week_of_month",
        "Day of week": "dow",
        "Entry hour (NY)": "hour_ny",
        "Hourly OBV vs trade": "obv_align",
        "5m MA vs trade": "ma5_align",
        "5m MA cross vs trade": "ma5_cross_align",
        "ATR14 quartile": "atr_q",
        "Prior-week range half": "week_half_align",
        "Prior-day range half": "day_half_align",
    }
    key = mapping.get(cond)
    if key is None:
        return None
    if key in ("week_of_month", "hour_ny"):
        try:
            val: object = int(b)
        except Exception:
            val = b
    else:
        val = str(b)
    return (key, val)


def _market_from_book_or_symbol(book: str = "", symbol: str = "") -> str:
    sym = str(symbol or "").strip().lower()
    if sym in MARKETS:
        return sym
    # NAS100 / USDJPY / XAUUSD style
    for k, cfg in MARKETS.items():
        if cfg.symbol.lower() == sym:
            return k
    b = str(book or "").strip().lower()
    if b:
        head = b.split("_")[0]
        if head in MARKETS:
            return head
    return ""


def _parse_hp_from_hub(path: Path) -> Dict[str, List[Tuple[str, Optional[Tuple[str, object]], str]]]:
    """Promising HA filters → per-market HP gate list for 1m re-sim.

    Prefer overlay ranked_full.csv rows with policy=filter and delta_ns>0.
    Also include profile notables for other promising books (dual-lift).
    """
    out: Dict[str, List[Tuple[str, Optional[Tuple[str, object]], str]]] = {}
    seen: Dict[str, set] = {}

    def add(market: str, gate: Tuple[str, object], note: str) -> None:
        if not market or market not in MARKETS:
            return
        label = ("hp_%s_%s" % (gate[0], gate[1])).replace(" ", "_").replace("-", "_")[:48]
        sk = seen.setdefault(market, set())
        sig = (gate[0], str(gate[1]))
        if sig in sk:
            return
        sk.add(sig)
        out.setdefault(market, []).append((label, gate, note))

    ranked = path / "overlay" / "ranked_full.csv"
    if ranked.exists():
        df = pd.read_csv(ranked)
        if "policy" in df.columns:
            f = df[(df["policy"].astype(str) == "filter") & (df["delta_ns"].astype(float) > 0)].copy()
            f = f.sort_values("delta_ns", ascending=False)
            for _, row in f.iterrows():
                gate = _condition_to_gate(row.get("condition", ""), row.get("bucket"))
                if gate is None:
                    continue
                mkt = _market_from_book_or_symbol(str(row.get("book", "")), str(row.get("symbol", "")))
                add(mkt, gate, "overlay filter ΔN/S=%+.2f" % float(row["delta_ns"]))

    markets_with_overlay = set(out.keys())
    notables = path / "profile" / "notables.csv"
    if not notables.exists():
        notables = path / "notables.csv"
    if notables.exists():
        df = pd.read_csv(notables)
        for _, row in df.iterrows():
            gate = _condition_to_gate(row.get("condition", ""), row.get("bucket"))
            if gate is None:
                continue
            mkt = _market_from_book_or_symbol(str(row.get("book", "")), str(row.get("symbol", "")))
            # Overlay filter ΔN/S>0 already defines promising gates for that book.
            if mkt in markets_with_overlay:
                continue
            wr = row["wr_lift_pp"] if "wr_lift_pp" in df.columns else row.get("wr_lift_pp", 0.0)
            avg = row["avg_lift"] if "avg_lift" in df.columns else row.get("avg_lift", 0.0)
            try:
                note = "profile notable WR%+.1f avg%+.0f" % (float(wr or 0.0), float(avg or 0.0))
            except Exception:
                note = "profile notable"
            add(mkt, gate, note)

    return out


def _atr_edges_from_hub(path: Path, market: str) -> Optional[List[float]]:
    """Static ATR quartile edges from HA campaign tape (matches overlay atr_q)."""
    cfg = MARKETS[market]
    prof = path / "profile"
    cand = []
    if prof.exists():
        cand.extend(sorted(prof.glob("%s*_campaigns.csv" % market)))
        cand.extend(sorted(prof.glob("*_campaigns.csv")))
        if (prof / "all_campaigns.csv").exists():
            cand.append(prof / "all_campaigns.csv")
    for c in cand:
        df = pd.read_csv(c)
        if "symbol" in df.columns:
            df = df[df["symbol"].astype(str).str.upper() == cfg.symbol.upper()]
        if "book" in df.columns and market not in str(df["book"].astype(str).head(1).tolist()):
            # keep rows for this market book when present
            df2 = df[df["book"].astype(str).str.startswith(market)]
            if not df2.empty:
                df = df2
        if "atr14" not in df.columns or df["atr14"].notna().sum() < 20:
            continue
        qs = df["atr14"].quantile([0.0, 0.25, 0.5, 0.75, 1.0]).tolist()
        qs[0] = float(qs[0]) - 1e-9
        qs[-1] = float(qs[-1]) + 1e-9
        return [float(x) for x in qs]
    return None


def _load_hp_feats(m: FxMarket) -> Optional[Dict[str, pd.DataFrame]]:
    try:
        from .chop20_dynamic_range_ha_conditions import _seed_daily_cache
        from .intraday_condition_profile import build_feature_frames
        from . import chop20_dynamic_range_ha_conditions as ha
    except Exception:
        return None
    try:
        if m.symbol not in ha.DAILY_CSV:
            ha.DAILY_CSV[m.symbol] = m.daily
        _seed_daily_cache(m.symbol)
        feats = build_feature_frames(m.symbol)
        return {
            "h1": feats["h1"].sort_values("ts"),
            "d1": feats["d1"].sort_values("ts"),
            "m5": feats["m5"].sort_values("ts"),
        }
    except Exception as exc:
        print("  hp feat load failed for %s: %s" % (m.symbol, exc), flush=True)
        return None


        head = b.split("_")[0]
        if head in MARKETS:
            return head
    return ""


def run(
    *,
    markets: Sequence[str],
    email: bool,
    smoke: bool,
    hp_from_hub: Optional[Path] = None,
    entry_modes: Sequence[str] = ENTRY_MODES,
) -> pd.DataFrame:
    HUB.mkdir(parents=True, exist_ok=True)
    _append_dsr()
    rid = begin_run(
        run_class="pandas",
        variant_slug="chop20_causal_entry_fx_metals",
        instrument="MULTI",
        hub_path=str(HUB.relative_to(REPO)),
        dsr_trial_id=DSR,
        notes="fx/metals causal entry running",
    )
    hp_map: Dict[str, List[Tuple[str, Optional[Tuple[str, object]], str]]] = {}
    if hp_from_hub is not None:
        hp_map = _parse_hp_from_hub(hp_from_hub)
        _progress(HUB, "HP gates from hub: %s" % (
            {k: [x[0] for x in v] for k, v in hp_map.items()},
        ))
    try:
        board_path = HUB / "summary_board.csv"
        prev_board = pd.read_csv(board_path) if board_path.exists() else None
        rows: List[dict] = []
        for m in markets:
            extra = hp_map.get(m.lower(), [])
            if hp_from_hub is not None and not extra:
                _progress(HUB, "No HP gates for %s — skip" % m)
                continue
            edges = _atr_edges_from_hub(hp_from_hub, m.lower()) if hp_from_hub is not None else None
            rows.extend(
                run_market(
                    m,
                    HUB,
                    smoke=smoke,
                    hp_extra=extra,
                    entry_modes=entry_modes,
                    atr_edges=edges,
                    include_baseline=False if (hp_from_hub is not None and extra) else True,
                    skip_existing=True,
                )
            )
        # Preserve prior markets when this invocation is a subset (e.g. SPX500 add-on).
        if prev_board is not None and not prev_board.empty and rows:
            cur = pd.DataFrame(rows)
            touched = set(cur["market"].astype(str).str.upper())
            keep = prev_board[~prev_board["market"].astype(str).str.upper().isin(touched)]
            rows = pd.concat([keep, cur], ignore_index=True).to_dict("records")
        text = _write_summary(HUB, rows, smoke=smoke)
        dw = analyze_date_windows(HUB, rows)
        text = text + "\n\n---\n\n" + dw
        (HUB / "EMAIL.txt").write_text(text)
        board = pd.DataFrame(rows)
        complete_run(
            rid,
            net_usd=float(board["net_usd"].sum()) if not board.empty else 0.0,
            trades=int(board["trades"].sum()) if not board.empty else 0,
            notes="fx/metals causal entry complete",
            meta={"smoke": smoke, "markets": list(markets)},
        )
        _mark_dsr("COMPLETE")
        if email:
            send_email(
                subject="potions: CHOP20 causal FX/metals %s" % ("smoke" if smoke else "complete"),
                body=text[:12000],
            )
        return board
    except Exception:
        err = traceback.format_exc()
        fail_run(rid, notes=err[-1500:])
        _mark_dsr("FAILED")
        if email:
            send_email(subject="potions: CHOP20 causal FX/metals FAILED", body=err[-4000:])
        raise


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--email", action="store_true")
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--markets", default=",".join(DEFAULT_MARKETS))
    p.add_argument(
        "--entry-modes",
        default=",".join(ENTRY_MODES),
        help="comma list; default both locked modes",
    )
    p.add_argument(
        "--hp-from-hub",
        default="",
        help="optional HA mill hub with notables.csv to re-sim HP gates",
    )
    args = p.parse_args(argv)
    markets = [m.strip().lower() for m in args.markets.split(",") if m.strip()]
    modes = [m.strip() for m in args.entry_modes.split(",") if m.strip()]
    hp_hub = Path(args.hp_from_hub) if args.hp_from_hub else None
    run(markets=markets, email=bool(args.email), smoke=bool(args.smoke), hp_from_hub=hp_hub, entry_modes=modes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
