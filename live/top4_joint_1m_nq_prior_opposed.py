"""TOP3 basket plus NQ prior-opposed OR-norm 2× (best futures HP variant).

Fourth sleeve is ``nq_prior_opposed_rl`` S_1_1_3 resting-limit, sized at the
high-probability rule that won the ΔN/S study: **2.00×** when the opening
15-minute range is ``or_norm``, otherwise 1.00×. That is the highest-conviction
row in ``futures_intraday_hp_live_plan`` (whole-book N/S 24.06 → 36.26).

The walk reuses the TOP3 joint 1-minute Engine-fill MTM. Comparison is on the
common window of all four sleeves (NQ history starts in 2021, so the original
2016–2025 TOP3 window is recomputed on that overlap).

Hub::

  live/state/top3_active_demo_portfolio/joint_1m_cb10x_plus_nq_po_or_norm_2x/

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.top4_joint_1m_nq_prior_opposed --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import date, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from . import top3_joint_1m_broker_portfolio as t3
from .futures_intraday_hp_sizeup_lib import DBN_1M, FEE_PER_UNIT, book_by_key
from .notify_email import send_email
from .replay_audit import POINT_VALUES
from .run_ledger import begin_run, complete_run, fail_run
from .v2b_strategy_replay import AuditBar, units_from_v2b_fills

REPO = t3.REPO
HUB = REPO / "live" / "state" / "top3_active_demo_portfolio" / "joint_1m_cb10x_plus_nq_po_or_norm_2x"
CACHE_1M = REPO / "live" / "state" / "_cache" / "bars" / "nq_1m_rth_front_2021_2025.parquet"
CAMPAIGNS = (
    REPO / "live" / "state" / "futures_intraday_condition_profile" / "nq_prior_opposed_rl_campaigns.csv"
)
NY = t3.NY
HP_MULT = 2.0
HP_BUCKET = "or_norm"
SLEEVE = "nq_prior_opposed"
RTH_LO = time(9, 30)
RTH_HI = time(16, 0)


def _progress(msg: str) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg.rstrip() + "\n")
    try:
        print(msg, flush=True)
    except BrokenPipeError:
        pass


def or_norm_size_by_trade() -> Dict[str, float]:
    df = pd.read_csv(CAMPAIGNS, usecols=["trade_id", "or15_width_pct"])
    out: Dict[str, float] = {}
    for trade_id, bucket in zip(df["trade_id"].astype(str), df["or15_width_pct"].astype(str)):
        out[trade_id] = HP_MULT if bucket == HP_BUCKET else 1.0
    return out


def load_nq_units() -> Tuple[List[t3.SleeveUnit], Dict[str, int]]:
    book = book_by_key("nq_prior_opposed_rl")
    sizes = or_norm_size_by_trade()
    units = units_from_v2b_fills(book.fills, book.key)
    pv = float(POINT_VALUES["NQ"])
    fee = float(FEE_PER_UNIT)
    out: List[t3.SleeveUnit] = []
    n_hp = n_base = missing = 0
    seen_hp = set()
    seen_base = set()
    seen_missing = set()
    for u in units:
        mult = sizes.get(str(u.trade_id))
        if mult is None:
            mult = 1.0
            missing += 1
            seen_missing.add(str(u.trade_id))
        elif mult > 1.0:
            n_hp += 1
            seen_hp.add(str(u.trade_id))
        else:
            n_base += 1
            seen_base.add(str(u.trade_id))
        out.append(
            t3.SleeveUnit(
                sleeve=SLEEVE,
                instrument="NQ",
                unit=u,
                point_value=pv,
                fee=fee,
                usd_div=1.0,
                size_mult=float(mult),
            )
        )
    stats = {
        "units": len(out),
        "hp_units": n_hp,
        "base_units": n_base,
        "unmatched_units": missing,
        "hp_trades": len(seen_hp),
        "base_trades": len(seen_base),
        "unmatched_trades": len(seen_missing),
    }
    return out, stats


def _symbol_intervals(mappings: dict) -> Dict[int, List[Tuple[date, date, str]]]:
    out: Dict[int, List[Tuple[date, date, str]]] = {}
    for sym, intervals in mappings.items():
        raw = str(sym)
        if "-" in raw or not raw.startswith("NQ"):
            continue
        for iv in intervals:
            iid = int(iv["symbol"])
            start = iv["start_date"]
            end = iv["end_date"]
            if not isinstance(start, date):
                start = date.fromisoformat(str(start)[:10])
            if not isinstance(end, date):
                end = date.fromisoformat(str(end)[:10])
            out.setdefault(iid, []).append((start, end, raw))
    return out


def _resolve_symbol(intervals: Dict[int, List[Tuple[date, date, str]]], iid: int, day: date) -> Optional[str]:
    for start, end, sym in intervals.get(iid, ()):
        if start <= day < end:
            return sym
    return None


def _build_nq_rth_cache(lo: pd.Timestamp, hi: pd.Timestamp) -> pd.DataFrame:
    import databento as db

    path = DBN_1M["NQ"]
    _progress("Streaming NQ 1m DBN %s ..." % path.name)
    store = db.DBNStore.from_file(str(path))
    intervals = _symbol_intervals(store.metadata.mappings)
    outright_ids = set(intervals)
    cut_lo = int((lo - pd.Timedelta(days=5)).tz_convert("UTC").value)
    cut_hi = int((hi + pd.Timedelta(days=3)).tz_convert("UTC").value)
    rows_ns: List[int] = []
    rows_o: List[float] = []
    rows_h: List[float] = []
    rows_l: List[float] = []
    rows_c: List[float] = []
    rows_v: List[int] = []
    rows_id: List[int] = []
    n_seen = 0
    n_kept = 0
    for rec in store:
        n_seen += 1
        ts_ns = int(rec.hd.ts_event)
        if ts_ns < cut_lo or ts_ns >= cut_hi:
            if n_seen % 5_000_000 == 0:
                _progress("  scanned %s records kept %s" % (f"{n_seen:,}", f"{n_kept:,}"))
            continue
        iid = int(rec.hd.instrument_id)
        if iid not in outright_ids:
            continue
        rows_ns.append(ts_ns)
        rows_o.append(float(rec.open))
        rows_h.append(float(rec.high))
        rows_l.append(float(rec.low))
        rows_c.append(float(rec.close))
        rows_v.append(int(rec.volume))
        rows_id.append(iid)
        n_kept += 1
        if n_kept % 1_000_000 == 0:
            _progress("  scanned %s records kept %s" % (f"{n_seen:,}", f"{n_kept:,}"))
    _progress("  scan done records=%s kept=%s" % (f"{n_seen:,}", f"{n_kept:,}"))
    if not rows_ns:
        raise RuntimeError("NQ 1m scan kept zero outright bars")
    df = pd.DataFrame(
        {
            "ts_ns": rows_ns,
            "open": rows_o,
            "high": rows_h,
            "low": rows_l,
            "close": rows_c,
            "volume": rows_v,
            "instrument_id": rows_id,
        }
    )
    med_px = float(np.median(df["close"].to_numpy()))
    if med_px > 1_000_000:
        df[["open", "high", "low", "close"]] = df[["open", "high", "low", "close"]] / 1e9
        _progress("  scaled DBN fixed-point prices (median was %.3e)" % med_px)
    df["ts"] = pd.to_datetime(df["ts_ns"], unit="ns", utc=True).dt.tz_convert(NY)
    df["session"] = df["ts"].dt.date
    # Resolve instrument_id on the NY session date (mapping intervals are [start, end)).
    sym_map: Dict[Tuple[int, date], str] = {}
    for iid, day in df.groupby(["instrument_id", "session"], sort=False).size().index:
        sym = _resolve_symbol(intervals, int(iid), day)
        if sym is not None:
            sym_map[(int(iid), day)] = sym
    df["symbol"] = [
        sym_map.get((int(iid), day))
        for iid, day in zip(df["instrument_id"].to_numpy(), df["session"].to_numpy())
    ]
    df = df[df["symbol"].notna()].copy()
    front = (
        df.groupby(["session", "symbol"], sort=False)["volume"]
        .sum()
        .groupby(level="session")
        .idxmax()
        .apply(lambda item: item[1])
        .to_dict()
    )
    df = df[df["symbol"].eq(df["session"].map(front))].copy()
    local = df["ts"].dt.time
    df = df[(df["ts"].dt.weekday < 5) & (local >= RTH_LO) & (local < RTH_HI)].copy()
    df = df.sort_values("ts").drop_duplicates("ts", keep="last")
    CACHE_1M.parent.mkdir(parents=True, exist_ok=True)
    df[["ts", "open", "high", "low", "close", "volume", "symbol"]].to_parquet(CACHE_1M, index=False)
    _progress("  cached %s rows=%s" % (CACHE_1M.name, f"{len(df):,}"))
    return df


def load_nq_1m(lo: pd.Timestamp, hi: pd.Timestamp) -> List[Tuple[int, AuditBar]]:
    if CACHE_1M.exists():
        _progress("Loading cached NQ RTH 1m %s" % CACHE_1M.name)
        df = pd.read_parquet(CACHE_1M)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
    else:
        df = _build_nq_rth_cache(lo, hi)
    df = df[(df["ts"] >= lo) & (df["ts"] <= hi + pd.Timedelta(days=1))].copy()
    df = df.sort_values("ts")
    out: List[Tuple[int, AuditBar]] = []
    for r in df.itertuples(index=False):
        t = pd.Timestamp(r.ts)
        out.append((int(t.value), AuditBar(t3._iso(t), float(r.open), float(r.high), float(r.low), float(r.close))))
    _progress("  NQ 1m bars=%d %s → %s" % (len(out), lo.date(), hi.date()))
    if out:
        # Sanity: a 2021-03-04 entry near 12765 should see a bar in that neighborhood.
        sample = df[(df["ts"] >= pd.Timestamp("2021-03-04 11:00", tz=NY)) & (df["ts"] <= pd.Timestamp("2021-03-04 11:05", tz=NY))]
        if not sample.empty:
            px = float(sample.iloc[0]["close"])
            _progress("  sanity 2021-03-04 11:0x close=%.2f (entry was 12765.625)" % px)
            if abs(px - 12765.625) > 400:
                raise RuntimeError("NQ front-month 1m close %.2f is far from the 2021-03-04 fill" % px)
    return out


def _pack(name: str, result: dict) -> dict:
    return {
        "name": name,
        "net_usd": float(result["net_usd"]),
        "closed_dd_usd": float(result["closed_dd_usd"]),
        "intrabar_stress_dd_usd": float(result["intrabar_stress_dd_usd"]),
        "net_over_stress": float(result["net_over_stress"]),
        "max_open_units": int(result["max_open_units"]),
        "events": int(result["events"]),
        "sleeve": result["sleeve"],
    }


def _daily_pnl(rows: Sequence[dict]) -> pd.Series:
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows)
    eq = df["close_equity_usd"].astype(float)
    pnl = eq.diff()
    pnl.iloc[0] = eq.iloc[0]
    return pd.Series(pnl.to_numpy(), index=df["date"].astype(str))


def _money(x: float) -> str:
    return t3._money(x)


def write_outputs(
    *,
    lo: pd.Timestamp,
    hi: pd.Timestamp,
    top3: dict,
    top4: dict,
    nq_only: dict,
    nq_stats: Dict[str, int],
    published_top3_ns: float,
) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(top4["equity_rows"]).to_csv(HUB / "equity_curve_1m_sample.csv", index=False)
    pd.DataFrame(top4["daily_rows"]).to_csv(HUB / "equity_curve_daily.csv", index=False)
    pd.DataFrame(top3["daily_rows"]).to_csv(HUB / "top3_equity_curve_daily.csv", index=False)
    pd.DataFrame(nq_only["daily_rows"]).to_csv(HUB / "nq_equity_curve_daily.csv", index=False)

    a = _daily_pnl(top3["daily_rows"])
    b = _daily_pnl(nq_only["daily_rows"])
    both = pd.concat([a.rename("top3"), b.rename("nq")], axis=1).dropna()
    corr = float(both["top3"].corr(both["nq"])) if len(both) > 5 else float("nan")

    t3p = _pack("top3_overlap", top3)
    t4p = _pack("top4", top4)
    nqp = _pack("nq_or_norm_2x", nq_only)
    delta_ns = t4p["net_over_stress"] - t3p["net_over_stress"]
    improves = bool(delta_ns > 0)
    nq_net = float(top4["sleeve"][SLEEVE]["net_usd"])
    share = (nq_net / t4p["net_usd"]) if t4p["net_usd"] else 0.0

    metrics = {
        "hub": str(HUB),
        "variant": "nq_prior_opposed_rl or_norm @ 2.00x else 1.00x",
        "hp_source": "futures_intraday_hp_live_plan highest-conviction controlled paper",
        "common_window_start": lo.isoformat(),
        "common_window_end": hi.isoformat(),
        "published_top3_full_window_ns": published_top3_ns,
        "top3_overlap": t3p,
        "top4": t4p,
        "nq_only": nqp,
        "delta_ns_top4_minus_top3": delta_ns,
        "basket_ns_improves": improves,
        "nq_net_share_of_top4": share,
        "daily_close_pnl_corr_top3_vs_nq": corr,
        "nq_size_stats_full_history": nq_stats,
        "method": "joint_1m_mtm_on_engine_fills",
    }
    (HUB / "metrics.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")

    def sleeve_table(result: dict) -> List[str]:
        lines = [
            "| Sleeve | Units | Trades | Net |",
            "|---|---:|---:|---:|",
        ]
        labels = {
            "asia_range": "Asia Range",
            "monday_or": "Monday OR",
            "clean_break": "Clean Break ×10",
            SLEEVE: "NQ prior-opposed OR-norm 2×",
        }
        for name, s in result["sleeve"].items():
            lines.append(
                "| %s | %d | %d | %s |"
                % (labels.get(name, name), int(s["units"]), int(s["trades"]), _money(float(s["net_usd"])))
            )
        return lines

    stance = (
        "Adding NQ prior-opposed OR-norm 2× **raises** basket N/S on the overlap window."
        if improves
        else "Adding NQ prior-opposed OR-norm 2× **does not raise** basket N/S on the overlap window."
    )
    lines = [
        "# TOP4 joint 1-minute portfolio — TOP3 + NQ prior-opposed OR-norm 2×",
        "",
        "Fourth sleeve is the best futures high-probability variant: NQ prior-opposed",
        "resting-limit `S_1_1_3`, sized **2×** when the opening 15m range is `or_norm`",
        "and **1×** otherwise (ΔN/S +12.20, provisional / highest-conviction controlled paper).",
        "",
        stance,
        "",
        "## Overlap window",
        "",
        "NQ fills begin in 2021, so this is **not** the published 2016–2025 TOP3 window",
        "(that book is N/S **%.2f**). Both columns below use the same four-sleeve overlap."
        % published_top3_ns,
        "",
        "| | TOP3 on overlap | TOP4 (TOP3 + NQ) | NQ OR-norm 2× alone |",
        "|---|---:|---:|---:|",
        "| Net | %s | %s | %s |"
        % (_money(t3p["net_usd"]), _money(t4p["net_usd"]), _money(nqp["net_usd"])),
        "| Close MTM DD | %s | %s | %s |"
        % (_money(t3p["closed_dd_usd"]), _money(t4p["closed_dd_usd"]), _money(nqp["closed_dd_usd"])),
        "| **Intrabar stress DD** | **%s** | **%s** | **%s** |"
        % (
            _money(t3p["intrabar_stress_dd_usd"]),
            _money(t4p["intrabar_stress_dd_usd"]),
            _money(nqp["intrabar_stress_dd_usd"]),
        ),
        "| **N/S** | **%.2f** | **%.2f** | **%.2f** |"
        % (t3p["net_over_stress"], t4p["net_over_stress"], nqp["net_over_stress"]),
        "| Δ N/S vs TOP3 |  | **%+.2f** |  |" % delta_ns,
        "",
        "Window %s → %s. NQ is %s of TOP4 net. Daily close-P&L correlation vs TOP3: **%.2f**."
        % (lo.date(), hi.date(), "%.0f%%" % (100.0 * share), corr),
        "",
        "NQ size on the full fill tape: %d trades at 2× (`or_norm`), %d trades at 1×, %d unmatched (kept at 1×)."
        % (nq_stats["hp_trades"], nq_stats["base_trades"], nq_stats["unmatched_trades"]),
        "",
        "## TOP4 sleeve nets (overlap entries)",
        "",
        *sleeve_table(top4),
        "",
        "## Method",
        "",
        "- Asia / Monday OR / Clean Break ×10: same Engine fills as `joint_1m_cb10x`",
        "- NQ: `nq_v2b_prior_opposed_stpmc_only_S_1_1_3` fills, point value $20, fee $1.50/contract",
        "- HP map: `or15_width_pct == or_norm` → size ×2 on every unit of that trade",
        "- Mark NQ on front-month RTH 1m; USDJPY and NAS100 tapes unchanged",
        "- Lots stay sleeve-scoped (no cross-sleeve fill interference)",
        "",
        "Stance: research basket add-on. NQ OR-norm @2× remains provisional controlled paper, not a funded promote.",
        "",
    ]
    (HUB / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    email = "\n".join(
        [
            "TOP4 joint 1m: TOP3 + NQ prior-opposed OR-norm 2×",
            "Hub: %s" % HUB,
            "Overlap window: %s → %s" % (lo.date(), hi.date()),
            "TOP3 overlap net %s stress %s N/S %.2f"
            % (_money(t3p["net_usd"]), _money(t3p["intrabar_stress_dd_usd"]), t3p["net_over_stress"]),
            "TOP4 net %s stress %s N/S %.2f (Δ N/S %+.2f)"
            % (
                _money(t4p["net_usd"]),
                _money(t4p["intrabar_stress_dd_usd"]),
                t4p["net_over_stress"],
                delta_ns,
            ),
            "NQ alone net %s stress %s N/S %.2f"
            % (_money(nqp["net_usd"]), _money(nqp["intrabar_stress_dd_usd"]), nqp["net_over_stress"]),
            "NQ share of TOP4 net %.0f%% · daily P&L corr vs TOP3 %.2f" % (100.0 * share, corr),
            stance.replace("**", ""),
            "Published TOP3 window (2016–2025) N/S was %.2f; this compare uses the 2021 overlap."
            % published_top3_ns,
            "Stance: research add-on only. NQ OR-norm @2× stays provisional controlled paper.",
        ]
    )
    (HUB / "EMAIL.txt").write_text(email + "\n", encoding="utf-8")


def run(*, email: bool = False) -> Dict[str, object]:
    HUB.mkdir(parents=True, exist_ok=True)
    (HUB / "PROGRESS.log").write_text("", encoding="utf-8")
    rid = begin_run(
        run_class="broker_like",
        variant_slug="top4_joint_1m_cb10x_nq_po_or_norm_2x",
        instrument="PORTFOLIO",
        hub_path=str(HUB),
        meta={
            "sleeves": ["asia_range", "monday_or", "clean_break", "nq_prior_opposed"],
            "nq_rule": "or_norm_2x",
            "cb_scale": t3.CB_SCALE,
        },
    )
    prev_hub = t3._PROGRESS_HUB
    t3._PROGRESS_HUB = HUB
    try:
        _progress("Loading TOP3 Engine fills + NQ prior-opposed OR-norm 2× ...")
        top3_units = t3.load_sleeve_units()
        nq_units, nq_stats = load_nq_units()
        _progress(
            "  NQ units=%d hp_trades=%d base_trades=%d unmatched=%d"
            % (nq_stats["units"], nq_stats["hp_trades"], nq_stats["base_trades"], nq_stats["unmatched_trades"])
        )
        if nq_stats["hp_trades"] < 30:
            raise RuntimeError("or_norm trade count %d is too small to be the HP variant" % nq_stats["hp_trades"])
        all_units = list(top3_units) + list(nq_units)
        lo, hi = t3._common_window(all_units)
        _progress("Overlap window %s → %s" % (lo, hi))
        top3_w = t3._filter_units_common(top3_units, lo, hi)
        nq_w = t3._filter_units_common(nq_units, lo, hi)
        top4_w = list(top3_w) + list(nq_w)
        _progress(
            "Overlap units top3=%d nq=%d top4=%d" % (len(top3_w), len(nq_w), len(top4_w))
        )

        jpy = t3.load_usdjpy_1m(lo, hi)
        nas = t3.load_nas100_1m(lo, hi)
        nq = load_nq_1m(lo, hi)

        _progress("Walking TOP3 on overlap (%d events)..." % (len(jpy) + len(nas)))
        top3_res = t3.joint_1m_mtm(top3_w, jpy, nas)
        _progress(
            "  TOP3 net=%s stress=%s N/S=%.2f"
            % (_money(float(top3_res["net_usd"])), _money(float(top3_res["intrabar_stress_dd_usd"])), float(top3_res["net_over_stress"]))
        )
        _progress("Walking NQ OR-norm 2× alone (%d events)..." % len(nq))
        nq_res = t3.joint_1m_mtm(nq_w, [], [], nq)
        _progress(
            "  NQ net=%s stress=%s N/S=%.2f"
            % (_money(float(nq_res["net_usd"])), _money(float(nq_res["intrabar_stress_dd_usd"])), float(nq_res["net_over_stress"]))
        )
        _progress("Walking TOP4 (%d events)..." % (len(jpy) + len(nas) + len(nq)))
        top4_res = t3.joint_1m_mtm(top4_w, jpy, nas, nq)
        _progress(
            "  TOP4 net=%s stress=%s N/S=%.2f"
            % (_money(float(top4_res["net_usd"])), _money(float(top4_res["intrabar_stress_dd_usd"])), float(top4_res["net_over_stress"]))
        )

        published = 10.607987988582144
        write_outputs(
            lo=lo,
            hi=hi,
            top3=top3_res,
            top4=top4_res,
            nq_only=nq_res,
            nq_stats=nq_stats,
            published_top3_ns=published,
        )
        delta = float(top4_res["net_over_stress"]) - float(top3_res["net_over_stress"])
        _progress("DONE ΔN/S %+.2f basket_improves=%s" % (delta, delta > 0))
        complete_run(
            rid,
            net_usd=float(top4_res["net_usd"]),
            stress_dd_usd=float(top4_res["intrabar_stress_dd_usd"]),
            close_mtm_dd_usd=float(top4_res["closed_dd_usd"]),
            ns=float(top4_res["net_over_stress"]),
            trades=int(sum(int(s["trades"]) for s in top4_res["sleeve"].values())),
            units=len(top4_w),
            equity_curve_path=HUB / "equity_curve_daily.csv",
            replay_start=str(lo.date()),
            replay_end=str(hi.date()),
            notes="delta_ns_vs_top3_overlap=%+.4f" % delta,
            meta={
                "top3_overlap_ns": float(top3_res["net_over_stress"]),
                "top4_ns": float(top4_res["net_over_stress"]),
                "nq_only_ns": float(nq_res["net_over_stress"]),
                "delta_ns": delta,
                "basket_ns_improves": bool(delta > 0),
                "nq_hp_trades": nq_stats["hp_trades"],
            },
        )
        if email:
            send_email(
                subject="potions: TOP4 + NQ prior-opposed OR-norm 2× complete",
                body=(HUB / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        return {"top3": top3_res, "top4": top4_res, "nq": nq_res, "delta_ns": delta}
    except Exception:
        tb = traceback.format_exc()
        fail_run(rid, notes=tb[-2000:])
        (HUB / "FAIL.txt").write_text(tb, encoding="utf-8")
        if email:
            send_email(
                subject="potions: TOP4 + NQ prior-opposed FAILED",
                body="Hub: %s\n\n%s" % (HUB, tb[-3000:]),
            )
        raise
    finally:
        t3._PROGRESS_HUB = prev_hub


def main() -> None:
    ap = argparse.ArgumentParser(description="TOP3 + NQ prior-opposed OR-norm 2× joint 1m MTM")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args()
    run(email=bool(args.email))


if __name__ == "__main__":
    main()
