"""Shared catalog, campaign tapes, and causal features for futures HP size-up."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_london_ungated import REPO
from .replay_audit import POINT_VALUES

NY = "America/New_York"
CACHE = REPO / "live" / "state" / "_cache" / "bars"
STUDY = "futures_intraday_hp_sizeup_v1"
PROFILE_HUB = REPO / "live" / "state" / "futures_intraday_condition_profile"
NULLS_HUB = REPO / "live" / "state" / "futures_intraday_hp_sizeup_nulls"
NULLS_HUB_2X = REPO / "live" / "state" / "futures_intraday_hp_sizeup_nulls_2x"
LIVE_HUB = REPO / "live" / "state" / "futures_intraday_hp_live_plan"
SEED = 20260812

# Predeclared 2× null suite (Tier A/B @ 1.25×). Separate hub; no 1.25× LIVE_PLAN overwrite.
PREDECLARED_2X: List[Tuple[str, str, str]] = [
    ("es_prior_opposed_legacy", "ST-event age", "st_age_gt180m"),
    ("ym_prior_opposed_rl", "Overnight range third", "on_middle"),
    ("nq_prior_opposed_rl", "Opening 15m range vs ATR", "or_norm"),
]

# Phase-3 ΔN/S objective shortlist @ 1.25× (exact pairs; not shortlist head)
PHASE3_1_25: List[Tuple[str, str, str]] = [
    ("nq_prior_opposed_rl", "Opening 15m range vs ATR", "or_norm"),
    ("es_prior_opposed_legacy", "ST-event age", "st_age_gt180m"),
    ("ym_prior_opposed_rl", "Overnight range third", "on_middle"),
]
FEE_PER_UNIT = 1.5

# Index sleeve for portfolio stacking rules (full contract preferred over micro).
SLEEVE = {
    "NQ": "nasdaq",
    "MNQ": "nasdaq",
    "YM": "dow",
    "MYM": "dow",
    "ES": "spx",
    "MES": "spx",
}
MICRO = {"MNQ", "MYM", "MES"}

# Proven FX buckets carried over (exclude generic 5m MA-cross alignment).
CARRY_CONDITION_COLS: List[Tuple[str, str]] = [
    ("dow", "Day of week"),
    ("week_of_month", "Week of month"),
    ("hour_ny", "Entry hour (NY)"),
    ("month", "Month"),
    ("ma5_align", "5m MA vs trade"),  # opposition only is of interest; keep both buckets
    ("rsi_bucket", "Hourly RSI bucket"),
    ("rsi_align", "Hourly RSI vs trade"),
    ("atr_q", "ATR14 quartile"),
    ("atr_pct_bucket", "ATR causal rolling percentile"),
    ("day_half_align", "Prior-day range half"),
    ("week_half_align", "Prior-week range half"),
]

FUTURES_CONDITION_COLS: List[Tuple[str, str]] = [
    ("on_third", "Overnight range third"),
    ("on_vwap_side", "Overnight VWAP side"),
    ("gap_dir", "Gap direction"),
    ("on_range_pct", "Overnight compression"),
    ("prior_rth_loc", "Prior RTH close location"),
    ("prior_rth_range_pct", "Prior RTH range percentile"),
    ("or15_width_pct", "Opening 15m range vs ATR"),
    ("or15_dir_align", "Opening 15m direction vs trade"),
    ("rth_vwap_side", "RTH VWAP side"),
    ("on_vol_open_pct", "Opening 15m volume percentile"),
    ("idx_agree", "Cross-index direction agreement"),
    ("nq_es_disp", "NQ-ES dispersion"),
    ("st_age_bucket", "ST-event age"),
    ("st_dir_align", "ST-event direction vs trade"),
    ("post_holiday", "Post-holiday session"),
    ("roll_week", "Contract-roll week"),
]

CONDITION_COLS = CARRY_CONDITION_COLS + FUTURES_CONDITION_COLS

COND_COL: Dict[str, str] = {title: col for col, title in CONDITION_COLS}

CAUSAL_LIVE_READY = {
    "Day of week",
    "Week of month",
    "Entry hour (NY)",
    "Month",
    "5m MA vs trade",
    "Hourly RSI bucket",
    "Hourly RSI vs trade",
    "Prior-day range half",
    "Prior-week range half",
    "Overnight range third",
    "Overnight VWAP side",
    "Gap direction",
    "Overnight compression",
    "Prior RTH close location",
    "Prior RTH range percentile",
    "Opening 15m range vs ATR",
    "Opening 15m direction vs trade",
    "RTH VWAP side",
    "Opening 15m volume percentile",
    "Cross-index direction agreement",
    "NQ-ES dispersion",
    "ST-event age",
    "ST-event direction vs trade",
    "Post-holiday session",
    "Contract-roll week",
}
NEEDS_LIVE_PROXY = {
    "ATR14 quartile",  # static within-book cut in research; live needs rolling
    "ATR causal rolling percentile",  # computed here with rolling; keep proxy tag for audit
}


@dataclass(frozen=True)
class FuturesBook:
    key: str
    label: str
    symbol: str
    family: str
    fills: Path
    tracker_ns: float
    tracker_net: float
    tracker_stress: float
    campaigns_est: int
    status: str  # research-promoted | paper | strongest-candidate
    inventory: str = "flat"  # flat | approved | rejected
    notes: str = ""
    fee_per_unit: float = FEE_PER_UNIT
    strategy_id_filter: Optional[str] = None  # when fills live in a combined_state

    @property
    def sleeve(self) -> str:
        return SLEEVE.get(self.symbol.upper(), self.symbol.lower())

    @property
    def is_micro(self) -> bool:
        return self.symbol.upper() in MICRO


# Tracker + frozen research artifacts (StrategyPlugin / broker-like fills only).
# Metrics are the current banked Net/Stress figures from STRATEGY_TRACKER / hubs.
BOOK_UNIVERSE: Tuple[FuturesBook, ...] = (
    FuturesBook(
        "nq_prior_opposed_rl",
        "NQ prior-opposed v2b resting-limit S_1_1_3",
        "NQ",
        "prior_opposed",
        REPO
        / "live/state/nq_v2b_prior_opposed_causal_proxies/resting_limit/states/nq_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        19.40,
        1_330_920.0,
        68_610.0,
        432,
        "research-promoted",
        notes="hour-complete resting-limit; SOLID lookahead review",
    ),
    FuturesBook(
        "mnq_prior_opposed_rl",
        "MNQ prior-opposed v2b resting-limit S_1_1_3",
        "MNQ",
        "prior_opposed",
        REPO
        / "live/state/mnq_v2b_prior_opposed_stpmc_resting_limit/states/mnq_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        18.44,
        128_360.0,
        6_960.0,
        428,
        "research-promoted",
        notes="micro mirror of NQ prior-opposed",
    ),
    FuturesBook(
        "ym_prior_opposed_rl",
        "YM prior-opposed v2b resting-limit S_1_1_3",
        "YM",
        "prior_opposed",
        REPO
        / "live/state/ym_v2b_prior_opposed_stpmc_resting_limit/states/ym_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        8.53,
        289_225.0,
        33_894.0,
        436,
        "research-promoted",
    ),
    FuturesBook(
        "mym_prior_opposed_rl",
        "MYM prior-opposed v2b resting-limit S_1_1_3",
        "MYM",
        "prior_opposed",
        REPO
        / "live/state/mym_v2b_prior_opposed_stpmc_resting_limit/states/mym_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        6.47,
        22_101.0,
        3_417.0,
        423,
        "research-promoted",
        notes="micro Dow",
    ),
    FuturesBook(
        "es_prior_opposed_legacy",
        "ES prior-opposed v2b gate (legacy hourly fill)",
        "ES",
        "prior_opposed",
        REPO
        / "live/state/es_v2b_prior_opposed_stpmc_broker_like/states/es_v2b_prior_opposed_stpmc_only_S_1_1_3/fills.csv",
        10.51,
        348_688.0,
        33_177.0,
        400,
        "strongest-candidate",
        notes="resting-limit blocked (ES 1m DBN missing); legacy fill-stamp",
    ),
    FuturesBook(
        "nq_st_pmc_3r",
        "NQ hourly ST+PMC 50/150 fair 3R 1mfill",
        "NQ",
        "st_pmc",
        REPO
        / "live/state/futures_st_pmc_runner_variants/nq/states/nq_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        20.51,
        349_517.0,
        17_038.0,
        679,
        "research-promoted",
        inventory="flat",
    ),
    FuturesBook(
        "mnq_st_pmc_3r",
        "MNQ hourly ST+PMC 50/150 fair 3R 1mfill",
        "MNQ",
        "st_pmc",
        REPO
        / "live/state/futures_st_pmc_runner_variants/mnq/states/mnq_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        19.38,
        23_171.0,
        1_195.0,
        342,
        "research-promoted",
        notes="micro Nasdaq ST+PMC",
    ),
    FuturesBook(
        "ym_st_pmc_3r",
        "YM hourly ST+PMC 50/150 fair 3R 1mfill",
        "YM",
        "st_pmc",
        REPO
        / "live/state/futures_st_pmc_runner_variants/ym/states/ym_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        17.66,
        106_425.0,
        6_026.0,
        985,
        "research-promoted",
        inventory="flat",
    ),
    FuturesBook(
        "mym_st_pmc_3r",
        "MYM hourly ST+PMC 50/150 fair 3R 1mfill",
        "MYM",
        "st_pmc",
        REPO
        / "live/state/futures_st_pmc_runner_variants/mym/states/mym_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv",
        4.77,
        6_516.0,
        1_366.0,
        496,
        "research-promoted",
        notes="micro Dow ST+PMC",
    ),
    FuturesBook(
        "nq_st_pmc_25_75",
        "NQ hourly ST+PMC 25/75 3R",
        "NQ",
        "st_pmc",
        REPO
        / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/nq/states/nq_hourly_st_pmc_sl25_tp75_3r/fills.csv",
        5.87,
        144_520.0,
        24_635.0,
        1_683,
        "strongest-candidate",
        notes="older SL/TP expression; dominated by 50/150 3R on N/S",
    ),
    FuturesBook(
        "es_st_pmc_ma_bull",
        "ES hourly ST+PMC MA-bull prior",
        "ES",
        "st_pmc",
        REPO
        / "live/state/hourly_st_pmc_strategyplugin_variants_cross_market/es/combined_state/fills.csv",
        2.13,
        96_230.0,
        45_174.0,
        223,
        "strongest-candidate",
        notes="best viable ES ST expression; fair 3R N/S <1; filtered from combined_state",
        strategy_id_filter="es_hourly_st_pmc_ma_bull_prior_only",
    ),
    FuturesBook(
        "nq_v2b_s113",
        "NQ all-day v2b S_1_1_3 opening-range",
        "NQ",
        "opening_range",
        REPO / "live/state/v2b_sizing_sweep/states/nq_v2b_sizing_S_1_1_3/fills.csv",
        7.34,
        867_355.0,
        118_094.0,
        1_386,
        "research-promoted",
        notes="best plain all-days OR breakout expression",
    ),
    FuturesBook(
        "nq_or_complement_skipflat",
        "NQ v2b complement satellite + flat-gap skip",
        "NQ",
        "session_range",
        REPO / "live/state/nq_v2b_combined_book_causal/states/nq_a_comp_skipflat/fills.csv",
        22.51,  # combined book N/S; satellite alone lower — still distinct OR sleeve
        590_282.0,  # approx complement contribution (combined - core)
        16_731.0,
        800,
        "research-promoted",
        notes="distinct from gated prior-opposed core; session OR complement",
    ),
)


def _score(book: FuturesBook) -> float:
    """Rank score: prefer higher N/S, campaign count, and promotion status."""
    status_w = {
        "research-promoted": 1.15,
        "paper": 1.10,
        "strongest-candidate": 1.0,
    }.get(book.status, 0.9)
    ns = max(float(book.tracker_ns), 0.0)
    n = max(int(book.campaigns_est), 1)
    inv = 0.0 if book.inventory == "rejected" else 1.0
    return status_w * inv * ns * (1.0 + 0.15 * np.log10(n))


def select_top_futures_books(
    *,
    n: int = 8,
    min_ns: float = 1.0,
    min_campaigns: int = 100,
    universe: Sequence[FuturesBook] = BOOK_UNIVERSE,
) -> Tuple[List[FuturesBook], pd.DataFrame]:
    """Select top-N viable non-duplicate futures intraday books from the catalog."""
    rows = []
    viable: List[FuturesBook] = []
    for b in universe:
        ok_fills = b.fills.exists()
        ok_econ = b.tracker_ns >= min_ns and b.tracker_net > 0
        ok_n = b.campaigns_est >= min_campaigns
        ok_inv = b.inventory in {"flat", "approved"}
        ok_status = b.status in {"research-promoted", "paper", "strongest-candidate"}
        keep = ok_fills and ok_econ and ok_n and ok_inv and ok_status
        rows.append(
            {
                "key": b.key,
                "symbol": b.symbol,
                "sleeve": b.sleeve,
                "family": b.family,
                "tracker_ns": b.tracker_ns,
                "tracker_net": b.tracker_net,
                "campaigns_est": b.campaigns_est,
                "status": b.status,
                "inventory": b.inventory,
                "is_micro": b.is_micro,
                "fills_ok": ok_fills,
                "viable": keep,
                "score": _score(b) if keep else -1.0,
                "fills": str(b.fills),
                "notes": b.notes,
                "selected": False,
                "reject_reason": ""
                if keep
                else ";".join(
                    [
                        x
                        for x, flag in [
                            ("missing_fills", not ok_fills),
                            ("weak_ns_or_net", not ok_econ),
                            ("low_campaigns", not ok_n),
                            ("inventory", not ok_inv),
                            ("status", not ok_status),
                        ]
                        if flag
                    ]
                ),
            }
        )
        if keep:
            viable.append(b)

    # Dedup: within each (sleeve, family) keep the best non-micro (else best micro).
    by_group: Dict[Tuple[str, str], List[FuturesBook]] = {}
    for b in viable:
        by_group.setdefault((b.sleeve, b.family), []).append(b)

    deduped: List[FuturesBook] = []
    dropped_dup: Dict[str, str] = {}
    for (_sleeve, _fam), group in by_group.items():
        full = [g for g in group if not g.is_micro]
        pool = full if full else group
        best = max(pool, key=_score)
        deduped.append(best)
        for g in group:
            if g.key != best.key:
                dropped_dup[g.key] = "duplicate_sleeve_family_of_%s" % best.key

    # Soft family diversity: take highest scores but prefer covering distinct families.
    ranked = sorted(deduped, key=_score, reverse=True)
    selected: List[FuturesBook] = []
    families_seen = set()
    # First pass: one per family from top ranks
    for b in ranked:
        if b.family in families_seen:
            continue
        selected.append(b)
        families_seen.add(b.family)
        if len(selected) >= n:
            break
    # Fill remaining by score
    for b in ranked:
        if b in selected:
            continue
        selected.append(b)
        if len(selected) >= n:
            break

    selected = selected[:n]
    sel_keys = {b.key for b in selected}
    for r in rows:
        if r["key"] in sel_keys:
            r["selected"] = True
        elif r["key"] in dropped_dup:
            r["viable"] = False
            r["reject_reason"] = dropped_dup[r["key"]]
            r["score"] = -1.0
        elif r["viable"] and r["key"] not in sel_keys:
            r["reject_reason"] = "below_top_%d" % n

    ledger = pd.DataFrame(rows).sort_values(
        ["selected", "score"], ascending=[False, False]
    ).reset_index(drop=True)
    return selected, ledger


def load_campaigns(book: FuturesBook) -> pd.DataFrame:
    """Every baseline-taken campaign from StrategyPlugin fills."""
    sym = book.symbol.upper()
    pv = float(POINT_VALUES[sym])
    fee = float(book.fee_per_unit)
    fills = pd.read_csv(book.fills)
    if book.strategy_id_filter and "strategy_id" in fills.columns:
        fills = fills[fills["strategy_id"].astype(str) == book.strategy_id_filter].copy()
    fills["ts"] = pd.to_datetime(fills["ts"], utc=True).dt.tz_convert(NY)
    fills["price"] = pd.to_numeric(fills["price"], errors="coerce")
    fills["quantity"] = pd.to_numeric(fills["quantity"], errors="coerce").fillna(1).astype(int)
    rows = []
    for trade_id, group in fills.sort_values("ts").groupby("trade_id"):
        entries = group[group["reason"].astype(str) == "entry"]
        exits = group[group["reason"].astype(str) != "entry"]
        if entries.empty or exits.empty:
            continue
        entry = entries.iloc[0]
        side = "long" if str(entry["side"]).lower() == "buy" else "short"
        entry_px = float(entry["price"])
        net = 0.0
        exit_reasons = []
        for _, exit_row in exits.iterrows():
            qty = int(exit_row["quantity"])
            px = float(exit_row["price"])
            pts = px - entry_px if side == "long" else entry_px - px
            net += pts * pv * qty - fee * qty
            exit_reasons.append(str(exit_row["reason"]))
        entry_ts = pd.Timestamp(entry["ts"])
        rows.append(
            {
                "book": book.key,
                "family": book.family,
                "symbol": sym,
                "sleeve": book.sleeve,
                "strategy_label": book.label,
                "campaign_id": str(trade_id),
                "trade_id": str(trade_id),
                "contract": str(entry.get("instrument", sym)),
                "side": side,
                "direction": 1 if side == "long" else -1,
                "entry_ts": entry_ts,
                "exit_ts": pd.Timestamp(exits["ts"].max()),
                "entry_price": entry_px,
                "net_usd": float(net),
                "base_fill_path": "|".join(exit_reasons[:8]),
                "entry_qty": int(entries["quantity"].sum()),
            }
        )
    out = pd.DataFrame(rows).sort_values("entry_ts").reset_index(drop=True)
    if out.empty:
        return out
    out["win"] = out["net_usd"] > 0
    out["dow"] = out["entry_ts"].dt.day_name()
    out["hour_ny"] = out["entry_ts"].dt.hour
    out["month"] = out["entry_ts"].dt.month
    out["year"] = out["entry_ts"].dt.year
    out["week_of_month"] = ((out["entry_ts"].dt.day - 1) // 7 + 1).astype(int)
    out["session_date"] = out["entry_ts"].dt.strftime("%Y-%m-%d")
    return out


def _read_ohlcv_csv(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts_col = "ts_event" if "ts_event" in df.columns else ("date" if "date" in df.columns else ("ts" if "ts" in df.columns else None))
    if ts_col is None:
        raise ValueError("no ts column in %s" % path)
    if ts_col == "date":
        ts = pd.to_datetime(df["date"])
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY)
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = pd.to_datetime(df[ts_col], utc=True).dt.tz_convert(NY)
    out = pd.DataFrame(
        {
            "ts": ts,
            "open": pd.to_numeric(df["open"], errors="coerce"),
            "high": pd.to_numeric(df["high"], errors="coerce"),
            "low": pd.to_numeric(df["low"], errors="coerce"),
            "close": pd.to_numeric(df["close"], errors="coerce"),
            "volume": pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
            if "volume" in df.columns
            else 0.0,
        }
    ).dropna(subset=["ts", "close"])
    return out.sort_values("ts").drop_duplicates("ts", keep="last").reset_index(drop=True)


def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    g = df.set_index("ts").sort_index()
    ohlc = g.resample(rule, label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
    )
    return ohlc.dropna(subset=["close"]).reset_index()


DBN_1M = {
    "NQ": REPO / "nq/raw/glbx-mdp3-20100606-20260616.ohlcv-1m.dbn.zst",
    "YM": REPO / "ym/raw/glbx-mdp3-20100606-20260506.ohlcv-1m.dbn.zst",
    "MNQ": REPO / "mnq/raw/glbx-mdp3-20210304-20260303.ohlcv-1m.csv",
    "MYM": REPO / "mym/raw/glbx-mdp3-20100606-20260308.ohlcv-1m (mym).dbn.zst",
    # ES 1m DBN missing locally — daily only
}

DAILY_CSV = {
    "NQ": REPO / "nq/nq_daily.csv",
    "YM": REPO / "ym/ym_daily.csv",
    "ES": REPO / "es/es_daily.csv",
    "MNQ": REPO / "nq/nq_daily.csv",  # proxy scale not needed for features that use ratios
    "MYM": REPO / "ym/ym_daily.csv",
}


def _load_dbn_1m_frame(symbol: str) -> Optional[pd.DataFrame]:
    path = DBN_1M.get(symbol.upper())
    if path is None or not path.exists():
        return None
    from .v2b_strategy_cross_market_replay import load_1m_by_ny_date_any
    from .ym_hourly_st_pmc_retest_replay import concat_all_1m

    print("  loading 1m DBN/CSV for %s ..." % symbol, flush=True)
    by_day = load_1m_by_ny_date_any(path.resolve(), symbol.lower())
    bars = concat_all_1m(by_day)
    if bars is None or bars.empty:
        return None
    out = bars.reset_index().rename(columns={"ts_event": "ts", "index": "ts"})
    if "ts" not in out.columns:
        out = bars.copy()
        out["ts"] = out.index
        out = out.reset_index(drop=True)
    out["ts"] = pd.to_datetime(out["ts"], utc=True).dt.tz_convert(NY)
    for c in ("open", "high", "low", "close", "volume"):
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" not in out.columns:
        out["volume"] = 0.0
    return out[["ts", "open", "high", "low", "close", "volume"]].dropna(subset=["ts", "close"])


def ensure_tf_bars(symbol: str, tf: str) -> Optional[pd.DataFrame]:
    """Return NY-tz OHLCV for tf in {5m,1h,1d}, or None if unavailable."""
    sym = symbol.upper()
    CACHE.mkdir(parents=True, exist_ok=True)
    cache_path = CACHE / ("%s_%s.parquet" % (sym.lower(), tf))
    if cache_path.exists():
        df = pd.read_parquet(cache_path)
        df["ts"] = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(NY)
        if len(df) >= 100:
            return df

    if tf == "1d":
        daily = DAILY_CSV.get(sym)
        if daily is not None and daily.exists():
            df = _read_ohlcv_csv(daily)
            df.to_parquet(cache_path, index=False)
            return df

    # Prefer full-session 1m→tf from DBN (includes overnight / Globex).
    one = _load_dbn_1m_frame(sym)
    if one is not None:
        rule = {"5m": "5min", "1h": "1h", "1d": "1D"}[tf]
        df = _resample(one, rule)
        df.to_parquet(cache_path, index=False)
        print("  cached %s rows=%s" % (cache_path.name, f"{len(df):,}"), flush=True)
        if tf != "5m":
            c5 = CACHE / ("%s_5m.parquet" % sym.lower())
            if not c5.exists():
                _resample(one, "5min").to_parquet(c5, index=False)
        if tf != "1h":
            c1 = CACHE / ("%s_1h.parquet" % sym.lower())
            if not c1.exists():
                _resample(one, "1h").to_parquet(c1, index=False)
        return df

    # Fallbacks (RTH-only — overnight features will be NA)
    if sym == "NQ" and tf == "5m":
        p = REPO / "nq/nq_5min_rth.csv"
        if p.exists():
            df = _read_ohlcv_csv(p)
            df.to_parquet(cache_path, index=False)
            return df

    if sym == "NQ" and tf == "1h":
        p = REPO / "live/state/trend_momentum_sweep/states/nq_1h/bars/NQ_1h.csv"
        if p.exists():
            df = _read_ohlcv_csv(p)
            df.to_parquet(cache_path, index=False)
            return df

    return None

def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    up = delta.clip(lower=0.0)
    down = -delta.clip(upper=0.0)
    ma_up = up.ewm(alpha=1 / period, adjust=False).mean()
    ma_down = down.ewm(alpha=1 / period, adjust=False).mean()
    rs = ma_up / ma_down.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def _asof_merge(left: pd.DataFrame, right: pd.DataFrame, cols: Sequence[str]) -> pd.DataFrame:
    l = left.sort_values("entry_ts").copy()
    r = right.sort_values("ts").copy()
    merged = pd.merge_asof(l, r, left_on="entry_ts", right_on="ts", direction="backward")
    out = left.copy()
    for c in cols:
        if c in merged.columns:
            out[c] = merged[c].values
    # availability = right ts used (already shifted to known-at)
    if "ts" in merged.columns:
        out["_feat_ts"] = merged["ts"].values
    return out


def _us_holidays() -> set:
    # Minimal fixed + observed NYSE-ish holidays for session flags (causal calendar).
    try:
        import pandas.tseries.holiday as hol

        cal = hol.USFederalHolidayCalendar()
        days = cal.holidays(start="2010-01-01", end="2027-12-31")
        return {pd.Timestamp(d).date() for d in days}
    except Exception:
        return set()


def build_cross_index_daily() -> pd.DataFrame:
    """Prior-day NQ/ES/YM closes for agreement / dispersion (known at next session open)."""
    frames = {}
    for sym in ("NQ", "ES", "YM"):
        d = ensure_tf_bars(sym, "1d")
        if d is None:
            continue
        frames[sym] = d[["ts", "close"]].rename(columns={"close": sym})
    if len(frames) < 2:
        return pd.DataFrame(columns=["ts", "idx_agree", "nq_es_disp"])
    out = None
    for sym, fr in frames.items():
        out = fr if out is None else out.merge(fr, on="ts", how="outer")
    out = out.sort_values("ts").reset_index(drop=True)
    for sym in frames:
        out["%s_ret" % sym] = out[sym].pct_change()
    # Agreement of prior-day returns (known next day)
    ret_cols = [c for c in out.columns if c.endswith("_ret")]
    signs = out[ret_cols].apply(np.sign)
    agree_n = signs.sum(axis=1).abs()
    out["idx_agree"] = np.where(
        agree_n >= len(ret_cols),
        "all_agree",
        np.where(agree_n >= max(len(ret_cols) - 1, 1), "majority_agree", "mixed"),
    )
    if "NQ_ret" in out.columns and "ES_ret" in out.columns:
        disp = (out["NQ_ret"] - out["ES_ret"]).abs()
        try:
            out["nq_es_disp"] = pd.qcut(disp, 3, labels=["disp_low", "disp_mid", "disp_high"], duplicates="drop").astype(str)
        except ValueError:
            out["nq_es_disp"] = "disp_na"
    else:
        out["nq_es_disp"] = "disp_na"
    # Valid from next day open
    out["ts"] = out["ts"].dt.normalize() + pd.Timedelta(days=1)
    return out[["ts", "idx_agree", "nq_es_disp"]].dropna(subset=["ts"])


def annotate_campaigns(campaigns: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Attach causal entry-asof features + availability timestamps."""
    df = campaigns.copy()
    sym = symbol.upper()
    h1 = ensure_tf_bars(sym, "1h")
    d1 = ensure_tf_bars(sym, "1d")
    m5 = ensure_tf_bars(sym, "5m")
    holidays = _us_holidays()

    # --- hourly RSI ---
    if h1 is not None and len(h1) >= 50:
        h = h1.copy()
        h["rsi14"] = rsi(h["close"], 14)
        h["rsi_bucket"] = pd.cut(
            h["rsi14"],
            bins=[-0.1, 30, 45, 55, 70, 100.1],
            labels=["rsi_le30", "rsi_30_45", "rsi_45_55", "rsi_55_70", "rsi_gt70"],
        ).astype(str)
        h_feat = h[["ts", "rsi14", "rsi_bucket", "close"]].copy()
        h_feat["ts"] = h_feat["ts"] + pd.Timedelta(hours=1)
        h_feat["rsi_available_ts"] = h_feat["ts"]
        df = _asof_merge(df, h_feat.rename(columns={"rsi_available_ts": "feat_avail_rsi"}), ["rsi14", "rsi_bucket", "feat_avail_rsi"])
    else:
        df["rsi14"] = np.nan
        df["rsi_bucket"] = "rsi_na"
        df["feat_avail_rsi"] = pd.NaT

    # --- daily structure / ATR ---
    if d1 is not None and len(d1) >= 30:
        d = d1.copy()
        prev = d[["high", "low", "close"]].shift(1)
        d["prev_day_high"] = prev["high"]
        d["prev_day_low"] = prev["low"]
        d["prev_day_mid"] = (prev["high"] + prev["low"]) / 2.0
        d["prev_close"] = prev["close"]
        tr = pd.concat(
            [
                (d["high"] - d["low"]),
                (d["high"] - d["close"].shift(1)).abs(),
                (d["low"] - d["close"].shift(1)).abs(),
            ],
            axis=1,
        ).max(axis=1)
        d["atr14"] = tr.rolling(14).mean().shift(1)
        d["atr_pct"] = d["atr14"].rolling(252, min_periods=60).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) else np.nan,
            raw=False,
        ).shift(0)
        d["week"] = d["ts"].dt.to_period("W-SUN")
        week_hl = d.groupby("week", sort=False).agg(w_high=("high", "max"), w_low=("low", "min"))
        d = d.join(week_hl.shift(1), on="week")
        d["prev_week_mid"] = (d["w_high"] + d["w_low"]) / 2.0
        # Prior RTH location of close in prior day's range
        rng = (d["prev_day_high"] - d["prev_day_low"]).replace(0, np.nan)
        loc = (d["prev_close"] - d["prev_day_low"]) / rng
        d["prior_rth_loc"] = np.where(
            loc.isna(),
            "prior_loc_na",
            np.where(loc < 1 / 3, "prior_close_low_third", np.where(loc > 2 / 3, "prior_close_high_third", "prior_close_mid_third")),
        )
        pr = (d["prev_day_high"] - d["prev_day_low"])
        d["prior_rth_range_pct"] = pr.rolling(252, min_periods=60).apply(
            lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) else np.nan,
            raw=False,
        )
        d["prior_rth_range_pct_bucket"] = pd.cut(
            d["prior_rth_range_pct"],
            bins=[-0.01, 0.33, 0.66, 1.01],
            labels=["prior_range_comp", "prior_range_norm", "prior_range_exp"],
        ).astype(str)
        d_feat = d[
            [
                "ts",
                "prev_day_high",
                "prev_day_low",
                "prev_day_mid",
                "prev_close",
                "prev_week_mid",
                "w_high",
                "w_low",
                "atr14",
                "atr_pct",
                "prior_rth_loc",
                "prior_rth_range_pct_bucket",
            ]
        ].copy()
        d_feat["ts"] = d_feat["ts"].dt.normalize() + pd.Timedelta(days=1)
        d_feat = d_feat.rename(columns={"prior_rth_range_pct_bucket": "prior_rth_range_pct"})
        df = _asof_merge(
            df,
            d_feat,
            [
                "prev_day_high",
                "prev_day_low",
                "prev_day_mid",
                "prev_close",
                "prev_week_mid",
                "w_high",
                "w_low",
                "atr14",
                "atr_pct",
                "prior_rth_loc",
                "prior_rth_range_pct",
            ],
        )
        df["feat_avail_daily"] = df["entry_ts"].dt.normalize()  # known by session open
    else:
        for c in (
            "prev_day_high",
            "prev_day_low",
            "prev_day_mid",
            "prev_close",
            "prev_week_mid",
            "atr14",
            "atr_pct",
            "prior_rth_loc",
            "prior_rth_range_pct",
        ):
            df[c] = np.nan if c not in ("prior_rth_loc", "prior_rth_range_pct") else "na"
        df["feat_avail_daily"] = pd.NaT

    # --- 5m MA (opposition; no cross stacking) ---
    if m5 is not None and len(m5) >= 50:
        m = m5.copy()
        m["sma9"] = m["close"].rolling(9).mean()
        m["sma21"] = m["close"].rolling(21).mean()
        m["ma_state"] = np.where(
            m["sma9"] > m["sma21"],
            "ma_bull",
            np.where(m["sma9"] < m["sma21"], "ma_bear", "ma_flat"),
        )
        m_feat = m[["ts", "ma_state", "close", "volume"]].copy()
        m_feat["ts"] = m_feat["ts"] + pd.Timedelta(minutes=5)
        df = _asof_merge(df, m_feat, ["ma_state"])
        df["feat_avail_m5"] = df["entry_ts"]  # conservative: bar close before entry via asof
    else:
        df["ma_state"] = "ma_na"
        df["feat_avail_m5"] = pd.NaT

    # ATR buckets
    if df["atr14"].notna().sum() >= 20:
        try:
            df["atr_q"] = pd.qcut(
                df["atr14"], 4, labels=["atr_q1", "atr_q2", "atr_q3", "atr_q4"], duplicates="drop"
            ).astype(str)
        except ValueError:
            df["atr_q"] = "atr_na"
    else:
        df["atr_q"] = "atr_na"
    if "atr_pct" in df.columns and df["atr_pct"].notna().sum() >= 20:
        df["atr_pct_bucket"] = pd.cut(
            df["atr_pct"],
            bins=[-0.01, 0.25, 0.50, 0.75, 1.01],
            labels=["atr_p0_25", "atr_p25_50", "atr_p50_75", "atr_p75_100"],
        ).astype(str)
    else:
        df["atr_pct_bucket"] = "atr_pct_na"

    def half(px: pd.Series, mid: pd.Series) -> pd.Series:
        return np.where(
            px.isna() | mid.isna(),
            "range_na",
            np.where(px < mid, "lower_half", "upper_half"),
        )

    df["day_half"] = half(df["entry_price"], df["prev_day_mid"])
    df["week_half"] = half(df["entry_price"], df["prev_week_mid"])

    def align(side: pd.Series, half_col: pd.Series, name: str) -> pd.Series:
        good = ((side == "long") & (half_col == "lower_half")) | (
            (side == "short") & (half_col == "upper_half")
        )
        bad = ((side == "long") & (half_col == "upper_half")) | (
            (side == "short") & (half_col == "lower_half")
        )
        return np.where(
            half_col == "range_na",
            "%s_na" % name,
            np.where(good, "%s_aligned" % name, np.where(bad, "%s_opposed" % name, "%s_na" % name)),
        )

    df["day_half_align"] = align(df["side"], df["day_half"], "day")
    df["week_half_align"] = align(df["side"], df["week_half"], "week")

    df["ma5_align"] = np.where(
        df["ma_state"].isna() | (df["ma_state"] == "ma_na"),
        "ma_na",
        np.where(
            ((df["side"] == "long") & (df["ma_state"] == "ma_bull"))
            | ((df["side"] == "short") & (df["ma_state"] == "ma_bear")),
            "ma_aligned",
            np.where(
                ((df["side"] == "long") & (df["ma_state"] == "ma_bear"))
                | ((df["side"] == "short") & (df["ma_state"] == "ma_bull")),
                "ma_opposed",
                "ma_flat",
            ),
        ),
    )
    df["rsi_align"] = np.where(
        df["rsi14"].isna(),
        "rsi_na",
        np.where(
            ((df["side"] == "long") & (df["rsi14"] >= 55))
            | ((df["side"] == "short") & (df["rsi14"] <= 45)),
            "rsi_with_side",
            np.where(
                ((df["side"] == "long") & (df["rsi14"] <= 45))
                | ((df["side"] == "short") & (df["rsi14"] >= 55)),
                "rsi_against_side",
                "rsi_neutral",
            ),
        ),
    )

    # --- Overnight / opening structure from 5m or 1h when available ---
    # Overnight = 18:00 prior → 09:29; OR15 = 09:30–09:44. Features shifted to be known at end of window.
    src = m5 if m5 is not None else h1
    if src is not None and len(src) >= 100:
        s = src.copy().sort_values("ts")
        s["sess"] = s["ts"].dt.normalize()
        # Map bars after 16:00 to next session overnight
        s["on_sess"] = np.where(
            s["ts"].dt.time >= pd.Timestamp("16:00").time(),
            s["sess"] + pd.Timedelta(days=1),
            s["sess"],
        )
        # Overnight bars: 18:00–09:29 relative to on_sess
        t = s["ts"].dt.time
        on_mask = (t >= pd.Timestamp("18:00").time()) | (t < pd.Timestamp("09:30").time())
        overnight = s.loc[on_mask].copy()
        if not overnight.empty:
            g = overnight.groupby("on_sess", sort=False).agg(
                on_high=("high", "max"),
                on_low=("low", "min"),
                on_open=("open", "first"),
                on_close=("close", "last"),
                on_vol=("volume", "sum"),
                on_end=("ts", "max"),
            )
            # VWAP proxy: typical price * vol / vol (vectorized; pandas 2.0-safe)
            overnight["tp"] = (overnight["high"] + overnight["low"] + overnight["close"]) / 3.0
            overnight["_vol_clip"] = overnight["volume"].clip(lower=1.0)
            overnight["tpv"] = overnight["tp"] * overnight["_vol_clip"]
            _tpv_sum = overnight.groupby("on_sess", sort=False)["tpv"].sum()
            _vol_sum = overnight.groupby("on_sess", sort=False)["_vol_clip"].sum().clip(lower=1.0)
            g["on_vwap"] = _tpv_sum / _vol_sum
            g["on_range"] = g["on_high"] - g["on_low"]
            g = g.reset_index().rename(columns={"on_sess": "session_day"})
            g["on_range_pct_raw"] = g["on_range"].rolling(60, min_periods=20).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
            )
            g["on_range_pct"] = pd.cut(
                g["on_range_pct_raw"],
                bins=[-0.01, 0.33, 0.66, 1.01],
                labels=["on_comp", "on_norm", "on_exp"],
            ).astype(str)
            # Availability = max overnight bar ts (≤ 09:29)
            g["feat_avail_on"] = pd.to_datetime(g["on_end"], utc=True).dt.tz_convert(NY)
            g["ts"] = g["feat_avail_on"]
            df["_sess_day"] = df["entry_ts"].dt.normalize()
            on_map = g.set_index("session_day")
            for col in ("on_high", "on_low", "on_vwap", "on_range_pct", "feat_avail_on", "on_close", "on_open"):
                df[col] = df["_sess_day"].map(on_map[col] if col in on_map.columns else {})
            on_rng = (df["on_high"] - df["on_low"]).replace(0, np.nan)
            on_loc = (df["entry_price"] - df["on_low"]) / on_rng
            df["on_third"] = np.where(
                on_loc.isna(),
                "on_third_na",
                np.where(on_loc < 1 / 3, "on_lower", np.where(on_loc > 2 / 3, "on_upper", "on_middle")),
            )
            df["on_vwap_side"] = np.where(
                df["on_vwap"].isna(),
                "on_vwap_na",
                np.where(df["entry_price"] >= df["on_vwap"], "above_on_vwap", "below_on_vwap"),
            )
            # Gap vs prior close
            df["gap_dir"] = np.where(
                df["prev_close"].isna() | df["on_open"].isna(),
                "gap_na",
                np.where(
                    df["on_open"] > df["prev_close"],
                    "gap_up",
                    np.where(df["on_open"] < df["prev_close"], "gap_down", "gap_flat"),
                ),
            )
        else:
            for c in ("on_third", "on_vwap_side", "gap_dir", "on_range_pct"):
                df[c] = "%s_na" % c.split("_")[0]
            df["feat_avail_on"] = pd.NaT

        # Opening 15m range
        or_mask = (t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("09:45").time())
        opening = s.loc[or_mask].copy()
        if not opening.empty:
            og = opening.groupby(opening["ts"].dt.normalize(), sort=False).agg(
                or_high=("high", "max"),
                or_low=("low", "min"),
                or_open=("open", "first"),
                or_close=("close", "last"),
                or_vol=("volume", "sum"),
                or_end=("ts", "max"),
            )
            og = og.reset_index().rename(columns={"ts": "session_day"})
            og["or_width"] = og["or_high"] - og["or_low"]
            og["or15_width_pct_raw"] = og["or_width"].rolling(60, min_periods=20).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
            )
            og["or15_width_pct"] = pd.cut(
                og["or15_width_pct_raw"],
                bins=[-0.01, 0.33, 0.66, 1.01],
                labels=["or_narrow", "or_norm", "or_wide"],
            ).astype(str)
            og["or_dir"] = np.where(og["or_close"] >= og["or_open"], "or_up", "or_down")
            # volume percentile same clock
            og["on_vol_open_pct_raw"] = og["or_vol"].rolling(60, min_periods=20).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1], raw=False
            )
            og["on_vol_open_pct"] = pd.cut(
                og["on_vol_open_pct_raw"],
                bins=[-0.01, 0.33, 0.66, 1.01],
                labels=["vol_low", "vol_mid", "vol_high"],
            ).astype(str)
            og["feat_avail_or15"] = pd.to_datetime(og["or_end"], utc=True).dt.tz_convert(NY)
            omap = og.set_index("session_day")
            if "_sess_day" not in df.columns:
                df["_sess_day"] = df["entry_ts"].dt.normalize()
            for col in ("or15_width_pct", "or_dir", "on_vol_open_pct", "feat_avail_or15", "or_high", "or_low"):
                df[col] = df["_sess_day"].map(omap[col] if col in omap.columns else {})
            df["or15_dir_align"] = np.where(
                df["or_dir"].isna(),
                "or_dir_na",
                np.where(
                    ((df["side"] == "long") & (df["or_dir"] == "or_up"))
                    | ((df["side"] == "short") & (df["or_dir"] == "or_down")),
                    "or_aligned",
                    "or_opposed",
                ),
            )
        else:
            df["or15_width_pct"] = "or_na"
            df["or15_dir_align"] = "or_dir_na"
            df["on_vol_open_pct"] = "vol_na"
            df["feat_avail_or15"] = pd.NaT

        # RTH VWAP from 09:30 to entry (causal running) — approximate with completed 5m bars asof
        rth = s[(t >= pd.Timestamp("09:30").time()) & (t < pd.Timestamp("16:00").time())].copy()
        if not rth.empty:
            rth["tp"] = (rth["high"] + rth["low"] + rth["close"]) / 3.0
            rth["tpv"] = rth["tp"] * rth["volume"].clip(lower=1.0)
            rth["sess"] = rth["ts"].dt.normalize()
            rth["cum_tpv"] = rth.groupby("sess")["tpv"].cumsum()
            rth["cum_vol"] = rth.groupby("sess")["volume"].cumsum().clip(lower=1.0)
            rth["rth_vwap"] = rth["cum_tpv"] / rth["cum_vol"]
            rth_feat = rth[["ts", "rth_vwap"]].copy()
            rth_feat["ts"] = rth_feat["ts"] + pd.Timedelta(minutes=5)
            df = _asof_merge(df, rth_feat, ["rth_vwap"])
            df["rth_vwap_side"] = np.where(
                df["rth_vwap"].isna(),
                "rth_vwap_na",
                np.where(df["entry_price"] >= df["rth_vwap"], "above_rth_vwap", "below_rth_vwap"),
            )
            df["feat_avail_rth_vwap"] = df["entry_ts"]
        else:
            df["rth_vwap_side"] = "rth_vwap_na"
            df["feat_avail_rth_vwap"] = pd.NaT
    else:
        for c in (
            "on_third",
            "on_vwap_side",
            "gap_dir",
            "on_range_pct",
            "or15_width_pct",
            "or15_dir_align",
            "on_vol_open_pct",
            "rth_vwap_side",
        ):
            df[c] = "na"
        for c in ("feat_avail_on", "feat_avail_or15", "feat_avail_rth_vwap"):
            df[c] = pd.NaT

    # Cross-index
    xidx = build_cross_index_daily()
    if not xidx.empty:
        df = _asof_merge(df, xidx, ["idx_agree", "nq_es_disp"])
        df["feat_avail_xidx"] = df["entry_ts"].dt.normalize()
    else:
        df["idx_agree"] = "idx_na"
        df["nq_es_disp"] = "disp_na"
        df["feat_avail_xidx"] = pd.NaT

    # ST-event age/direction: for prior-opposed books, ST gate is known before arm;
    # approximate with hours since 09:30 as age proxy + side vs prior opposed not available —
    # use entry hour buckets relative to RTH open for ST-age research proxy on ST books.
    rth_open = df["entry_ts"].dt.normalize() + pd.Timedelta(hours=9, minutes=30)
    age_h = (df["entry_ts"] - rth_open).dt.total_seconds() / 3600.0
    df["st_age_bucket"] = pd.cut(
        age_h,
        bins=[-1e9, 0.5, 1.5, 3.0, 1e9],
        labels=["st_age_lt30m", "st_age_30_90m", "st_age_90_180m", "st_age_gt180m"],
    ).astype(str)
    # Without gate tape, direction align is unknown → mark na except family st_pmc/prior_opposed use trade-side RSI proxy already
    df["st_dir_align"] = np.where(
        df["family"].isin(["st_pmc", "prior_opposed"]),
        df["rsi_align"].map(
            {
                "rsi_against_side": "st_opposed_proxy",
                "rsi_with_side": "st_aligned_proxy",
                "rsi_neutral": "st_neutral_proxy",
            }
        ).fillna("st_dir_na"),
        "st_dir_na",
    )
    df["feat_avail_st"] = df["entry_ts"]

    # Calendar futures flags
    prev_day = (df["entry_ts"] - pd.Timedelta(days=1)).dt.date
    df["post_holiday"] = np.where(
        prev_day.map(lambda d: d in holidays),
        "post_holiday",
        "not_post_holiday",
    )
    # Roll week heuristic: week containing 3rd Friday of quarter months
    def _roll_week(ts: pd.Timestamp) -> str:
        if ts.month not in (3, 6, 9, 12):
            return "not_roll_week"
        # third Friday
        d0 = pd.Timestamp(year=ts.year, month=ts.month, day=1, tz=NY)
        # find first Friday
        days_ahead = (4 - d0.weekday()) % 7
        first_fri = d0 + pd.Timedelta(days=days_ahead)
        third_fri = first_fri + pd.Timedelta(days=14)
        week_start = third_fri - pd.Timedelta(days=third_fri.weekday())
        week_end = week_start + pd.Timedelta(days=6)
        return "roll_week" if week_start.date() <= ts.date() <= week_end.date() else "not_roll_week"

    df["roll_week"] = df["entry_ts"].map(_roll_week)
    df["feat_avail_cal"] = df["entry_ts"].dt.normalize()

    # Causal pass: feature availability strictly before entry
    def _causal_ok(avail: pd.Series) -> pd.Series:
        a = pd.to_datetime(avail, utc=True, errors="coerce")
        if getattr(a.dt, "tz", None) is None:
            a = a.dt.tz_localize(NY)
        else:
            a = a.dt.tz_convert(NY)
        return a.notna() & (a <= df["entry_ts"])

    df["causal_pass_rsi"] = _causal_ok(df.get("feat_avail_rsi", pd.Series(pd.NaT, index=df.index)))
    df["causal_pass_daily"] = _causal_ok(df.get("feat_avail_daily", pd.Series(pd.NaT, index=df.index)))
    df["causal_pass_on"] = _causal_ok(df.get("feat_avail_on", pd.Series(pd.NaT, index=df.index)))
    df["causal_pass_or15"] = _causal_ok(df.get("feat_avail_or15", pd.Series(pd.NaT, index=df.index)))
    # For OR15 features: only valid if entry is after 09:45
    after_or = df["entry_ts"].dt.time >= pd.Timestamp("09:45").time()
    df.loc[~after_or, "causal_pass_or15"] = False
    df.loc[~after_or, "or15_width_pct"] = "or_pre_open"
    df.loc[~after_or, "or15_dir_align"] = "or_pre_open"
    df.loc[~after_or, "on_vol_open_pct"] = "or_pre_open"

    # MAE/stress proxy from campaign net path (linear); full stress from book equity later
    df["base_stress_proxy"] = df["net_usd"].clip(upper=0).abs()
    df["base_mae_proxy"] = df["base_stress_proxy"]

    # Drop helpers
    drop_cols = [c for c in df.columns if c.startswith("_")]
    return df.drop(columns=drop_cols, errors="ignore")


def feature_family(condition: str) -> str:
    """Map condition title → family for ≤1 shortlist per family."""
    mapping = {
        "Day of week": "calendar",
        "Week of month": "calendar",
        "Entry hour (NY)": "calendar",
        "Month": "calendar",
        "Post-holiday session": "futures_calendar",
        "Contract-roll week": "futures_calendar",
        "Hourly RSI bucket": "momentum_rsi",
        "Hourly RSI vs trade": "momentum_rsi",
        "5m MA vs trade": "ma_opposition",
        "ATR14 quartile": "atr",
        "ATR causal rolling percentile": "atr",
        "Prior-day range half": "prior_range",
        "Prior-week range half": "prior_range",
        "Overnight range third": "overnight_location",
        "Overnight VWAP side": "overnight_location",
        "Gap direction": "overnight_location",
        "Overnight compression": "overnight_compression",
        "Prior RTH close location": "prior_rth",
        "Prior RTH range percentile": "prior_rth",
        "Opening 15m range vs ATR": "opening_structure",
        "Opening 15m direction vs trade": "opening_structure",
        "Opening 15m volume percentile": "participation",
        "RTH VWAP side": "vwap",
        "Cross-index direction agreement": "cross_index",
        "NQ-ES dispersion": "cross_index",
        "ST-event age": "st_state",
        "ST-event direction vs trade": "st_state",
    }
    return mapping.get(condition, "other")


def write_selection_artifacts(books: Sequence[FuturesBook], ledger: pd.DataFrame, hub: Path) -> None:
    hub.mkdir(parents=True, exist_ok=True)
    ledger.to_csv(hub / "universe_selection.csv", index=False)
    payload = {
        "study": STUDY,
        "n_selected": len(books),
        "books": [
            {
                **asdict(b),
                "fills": str(b.fills),
                "sleeve": b.sleeve,
                "score": _score(b),
            }
            for b in books
        ],
    }
    (hub / "SELECTED_BOOKS.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
