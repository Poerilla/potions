"""US30 ST+PMC 3R prior-day range percentile structure study (locked bands).

Frozen broker-realistic experiment on the canonical 1mfill 3R book. All variants
use the same StrategyPlugin fill tape; filters are entry-time causal sit-outs
(or 1.25× overlay diagnostic) — not a separate idealized simulator.

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.us30_st_pmc_3r_prior_range_structure --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_metals_cfd_intraday_condition_profile_lib import (
    DEFAULT_BOOKS,
    _rolling_pct_rank,
    _width_tercile,
    load_campaigns,
)
from .fx_v2b_london_ungated import REPO
from .intraday_condition_overlay import score_nets
from .notify_email import send_email
from .oanda_winner_mae_carry import path_mae_mfe
from .replay_audit import Bar, Unit, audit_units, read_bars

NY = "America/New_York"
STUDY = "us30_st_pmc_3r_prior_range_structure"
HUB = REPO / "live" / "state" / STUDY
BOOK = "us30_st_pmc_3r"
START_EQUITY = 100_000.0
SL_PTS = 50.0

FILLS = REPO / "live/state/us30_st_pmc_runner_variants/states/us30_hourly_st_pmc_sl50_tp150_3r_1mfill/fills.csv"
UNIT_FILLS = (
    REPO
    / "live/state/us30_st_pmc_runner_variants/audits_lot_correct"
    / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"
    / "us30_hourly_st_pmc_sl50_tp150_3r_1mfill_lot_correct"
    / "unit_fills.csv"
)
BARS_1M = REPO / "fx" / "us30_1m.csv"
CANDIDATE = "us30_hourly_st_pmc_sl50_tp150_3r_1mfill"

# Locked before re-run (do not tune after seeing results).
LOCKED_VARIANTS: Tuple[Tuple[str, str, Optional[float], Optional[float], float], ...] = (
    ("baseline_all", "primary", None, None, 1.00),
    ("broad_central_filter", "primary", 0.25, 0.75, 1.00),
    ("original_tercile_filter", "primary", 0.33, 0.66, 1.00),
    ("narrow_central_diagnostic", "diagnostic", 0.40, 0.60, 1.00),
    ("original_overlay", "diagnostic", 0.33, 0.66, 1.25),
)


@dataclass
class VariantMetrics:
    variant: str
    status: str
    policy: str
    band_lo: Optional[float]
    band_hi: Optional[float]
    multiplier: float
    campaigns: int
    units: int
    net_usd: float
    gross_profit: float
    gross_loss: float
    profit_factor: float
    win_rate: float
    avg_campaign: float
    median_campaign: float
    closed_dd_usd: float
    intrabar_stress_usd: float
    net_over_stress: float
    cagr: float
    ann_return: float
    worst_month_net: float
    worst_month: str
    worst_year_net: float
    worst_year: int
    max_consec_losses: int
    mae_median_r: float
    mae_p75_r: float
    mfe_median_r: float
    mfe_p75_r: float
    long_n: int
    long_net: float
    long_wr: float
    short_n: int
    short_net: float
    short_wr: float


def _progress(msg: str) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(msg.rstrip() + "\n")
    print(msg, flush=True)


def _max_consecutive_losses(nets: np.ndarray) -> int:
    best = cur = 0
    for x in nets:
        if float(x) <= 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _gross_split(nets: np.ndarray) -> Tuple[float, float, float]:
    gains = float(nets[nets > 0].sum()) if nets.size else 0.0
    losses = float((-nets[nets < 0]).sum()) if nets.size else 0.0
    pf = gains / losses if losses > 0 else (99.0 if gains > 0 else 0.0)
    return gains, losses, pf


def _attach_prior_range_raw(campaigns: pd.DataFrame) -> pd.DataFrame:
    df = campaigns.copy()
    daily = pd.read_csv(REPO / "fx" / "us30_daily.csv", parse_dates=["date"]).sort_values("date")
    daily["ts"] = pd.to_datetime(daily["date"]).dt.tz_localize(NY)
    prev_rng = (daily["high"].shift(1) - daily["low"].shift(1))
    daily["prior_day_range_pct_raw"] = _rolling_pct_rank(prev_rng)
    daily["prior_day_range_pct"] = _width_tercile(daily["prior_day_range_pct_raw"], prefix="prior_range")
    feat = daily[["ts", "prior_day_range_pct_raw", "prior_day_range_pct"]].copy()
    feat["ts"] = feat["ts"].dt.normalize() + pd.Timedelta(days=1)
    feat = feat.sort_values("ts")
    df = df.sort_values("entry_ts")
    df["entry_day"] = df["entry_ts"].dt.normalize()
    merged = pd.merge_asof(
        df,
        feat,
        left_on="entry_day",
        right_on="ts",
        direction="backward",
        allow_exact_matches=True,
    )
    return merged.drop(columns=["entry_day", "ts"], errors="ignore")


def _band_mask(pct: pd.Series, lo: Optional[float], hi: Optional[float]) -> pd.Series:
    if lo is None and hi is None:
        return pd.Series(True, index=pct.index)
    ok = pct.notna()
    if lo is not None:
        ok &= pct >= lo
    if hi is not None:
        ok &= pct <= hi
    return ok


def _variant_nets(df: pd.DataFrame, lo: Optional[float], hi: Optional[float], mult: float) -> np.ndarray:
    base = df["net_usd"].to_numpy(float)
    if mult == 1.25 and lo is not None:
        mask = _band_mask(df["prior_day_range_pct_raw"], lo, hi).to_numpy()
        out = base.copy()
        out[mask] *= 1.25
        return out
    if lo is None and hi is None:
        return base
    mask = _band_mask(df["prior_day_range_pct_raw"], lo, hi).to_numpy()
    return base[mask]


def _variant_rows(df: pd.DataFrame, lo: Optional[float], hi: Optional[float], mult: float) -> pd.DataFrame:
    if mult == 1.25 and lo is not None:
        return df.copy()
    if lo is None and hi is None:
        return df.copy()
    mask = _band_mask(df["prior_day_range_pct_raw"], lo, hi)
    return df.loc[mask].copy()


def _load_units() -> List[Unit]:
    rows = pd.read_csv(UNIT_FILLS)
    units: List[Unit] = []
    for _, r in rows.iterrows():
        hs = r.get("hard_stop_price")
        hard = None
        if pd.notna(hs) and str(hs).strip():
            hard = float(hs)
        units.append(
            Unit(
                candidate=str(r["candidate"]),
                trade_id=str(r["trade_id"]),
                unit_id=str(r["unit_id"]),
                direction=str(r["direction"]),
                entry_ts=str(r["entry_ts"]),
                entry_price=float(r["entry_price"]),
                exit_ts=str(r["exit_ts"]),
                exit_price=float(r["exit_price"]),
                exit_reason=str(r["exit_reason"]),
                entry_reason=str(r.get("entry_reason") or "entry"),
                hard_stop_price=hard,
                be_after_ts=str(r.get("be_after_ts") or ""),
            )
        )
    return units


def _filter_units(units: List[Unit], trade_ids: set) -> List[Unit]:
    return [u for u in units if u.trade_id in trade_ids]


def _load_1m_index() -> pd.DataFrame:
    raw = pd.read_csv(BARS_1M)
    ts_col = "ts_event" if "ts_event" in raw.columns else "ts"
    ts = pd.to_datetime(raw[ts_col], utc=True).dt.tz_convert(NY)
    out = pd.DataFrame(
        {
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
        }
    )
    out["ts"] = ts
    return out.drop_duplicates("ts", keep="last").set_index("ts").sort_index()


def _mae_mfe_stats(rows: pd.DataFrame, bars: pd.DataFrame) -> Dict[str, float]:
    maes: List[float] = []
    mfes: List[float] = []
    for row in rows.itertuples(index=False):
        entry_ts = pd.Timestamp(row.entry_ts)
        exit_ts = pd.Timestamp(row.exit_ts)
        if entry_ts.tzinfo is None:
            entry_ts = entry_ts.tz_localize(NY)
        else:
            entry_ts = entry_ts.tz_convert(NY)
        if exit_ts.tzinfo is None:
            exit_ts = exit_ts.tz_localize(NY)
        else:
            exit_ts = exit_ts.tz_convert(NY)
        mae, mfe, n = path_mae_mfe(
            bars,
            entry_ts=entry_ts,
            exit_ts=exit_ts,
            entry_price=float(row.entry_price),
            is_long=str(row.side).lower() == "long",
        )
        if n <= 0 or np.isnan(mae):
            continue
        maes.append(mae / SL_PTS)
        mfes.append(mfe / SL_PTS)
    if not maes:
        return {"mae_median_r": 0.0, "mae_p75_r": 0.0, "mfe_median_r": 0.0, "mfe_p75_r": 0.0}
    arr_mae = np.asarray(maes, float)
    arr_mfe = np.asarray(mfes, float)
    return {
        "mae_median_r": float(np.median(arr_mae)),
        "mae_p75_r": float(np.quantile(arr_mae, 0.75)),
        "mfe_median_r": float(np.median(arr_mfe)),
        "mfe_p75_r": float(np.quantile(arr_mfe, 0.75)),
    }


def _calendar_returns(rows: pd.DataFrame, nets: np.ndarray) -> Tuple[float, float, str, float, int, float]:
    if rows.empty:
        return 0.0, 0.0, "", 0.0, 0, 0.0
    tmp = rows[["entry_ts"]].copy()
    tmp["net"] = nets
    tmp["year"] = tmp["entry_ts"].dt.year
    tmp["month"] = tmp["entry_ts"].dt.to_period("M").astype(str)
    y = tmp.groupby("year")["net"].sum()
    m = tmp.groupby("month")["net"].sum()
    worst_year = int(y.idxmin())
    worst_year_net = float(y.min())
    worst_month = str(m.idxmin())
    worst_month_net = float(m.min())
    span_years = max(
        (tmp["entry_ts"].max() - tmp["entry_ts"].min()).days / 365.25,
        1 / 365.25,
    )
    net = float(nets.sum())
    cagr = (1 + net / START_EQUITY) ** (1 / span_years) - 1 if START_EQUITY else 0.0
    ann = net / span_years / START_EQUITY if START_EQUITY else 0.0
    return cagr, ann, worst_month, worst_month_net, worst_year, worst_year_net


def _side_split(rows: pd.DataFrame, nets: np.ndarray) -> Dict[str, float]:
    out = {
        "long_n": 0,
        "long_net": 0.0,
        "long_wr": 0.0,
        "short_n": 0,
        "short_net": 0.0,
        "short_wr": 0.0,
    }
    if rows.empty:
        return out
    tmp = rows[["side"]].copy()
    tmp["net"] = nets
    for side, prefix in (("long", "long"), ("short", "short")):
        sub = tmp[tmp["side"].str.lower() == side]
        out["%s_n" % prefix] = int(len(sub))
        out["%s_net" % prefix] = float(sub["net"].sum()) if len(sub) else 0.0
        out["%s_wr" % prefix] = float((sub["net"] > 0).mean()) if len(sub) else 0.0
    return out


def _yearly_table(rows: pd.DataFrame, nets: np.ndarray) -> pd.DataFrame:
    tmp = rows[["entry_ts", "side"]].copy()
    tmp["net"] = nets
    tmp["year"] = tmp["entry_ts"].dt.year
    g = tmp.groupby("year").agg(
        n=("net", "count"),
        net=("net", "sum"),
        wr=("net", lambda s: float((s > 0).mean())),
        avg=("net", "mean"),
    )
    eq = np.cumsum(nets)
    peak = np.maximum.accumulate(eq)
    dd = eq - peak
    tmp["dd"] = dd
    stress = tmp.groupby("year")["dd"].min().abs()
    g["stress"] = stress
    g["ns"] = g["net"] / g["stress"].replace(0, np.nan)
    return g.reset_index()


def _three_year_blocks(rows: pd.DataFrame, nets: np.ndarray) -> pd.DataFrame:
    tmp = rows[["entry_ts"]].copy()
    tmp["net"] = nets
    tmp["year"] = tmp["entry_ts"].dt.year
    tmp["block"] = ((tmp["year"] - tmp["year"].min()) // 3).astype(int)
    g = tmp.groupby("block").agg(
        start_year=("year", "min"),
        end_year=("year", "max"),
        n=("net", "count"),
        net=("net", "sum"),
        wr=("net", lambda s: float((s > 0).mean())),
    )
    return g.reset_index()


def _bucket_opportunity(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    total_net = float(df["net_usd"].sum())
    sc_base = score_nets(df["net_usd"].to_numpy(float))
    total_stress = float(sc_base["stress"])
    for bucket, lo, hi in (
        ("compressed", None, 0.33),
        ("normal", 0.33, 0.66),
        ("expanded", 0.66, None),
    ):
        if lo is None:
            mask = df["prior_day_range_pct_raw"] < hi
        elif hi is None:
            mask = df["prior_day_range_pct_raw"] > lo
        else:
            mask = (df["prior_day_range_pct_raw"] >= lo) & (df["prior_day_range_pct_raw"] <= hi)
        sub = df.loc[mask & df["prior_day_range_pct_raw"].notna()]
        sc = score_nets(sub["net_usd"].to_numpy(float))
        rows.append(
            {
                "bucket": bucket,
                "n": int(sc["n"]),
                "net": float(sc["net"]),
                "stress": float(sc["stress"]),
                "ns": float(sc["ns"]),
                "wr": float(sc["wr"]),
                "share_net": float(sc["net"] / total_net) if total_net else 0.0,
                "share_stress": float(sc["stress"] / total_stress) if total_stress else 0.0,
            }
        )
    return pd.DataFrame(rows)


def evaluate_variant(
    df: pd.DataFrame,
    *,
    name: str,
    status: str,
    lo: Optional[float],
    hi: Optional[float],
    mult: float,
    units_all: List[Unit],
    bars: List[Bar],
    bars_idx: pd.DataFrame,
    skip_mtm: bool,
) -> Tuple[VariantMetrics, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = _variant_rows(df, lo, hi, mult)
    nets = _variant_nets(df, lo, hi, mult)
    if mult == 1.25 and lo is not None:
        policy = "overlay 1.00 + 0.25 on %.0f–%.0f%%" % (100 * lo, 100 * hi)
        row_idx = df.index
    elif lo is None:
        policy = "all signals @ %.2f×" % mult
        row_idx = rows.index
    else:
        policy = "filter %.0f–%.0f%% @ %.2f×" % (100 * lo, 100 * hi, mult)
        row_idx = rows.index

    sc = score_nets(nets)
    gains, losses, pf = _gross_split(nets)
    cal = _calendar_returns(rows if mult != 1.25 else df, nets)
    cagr, ann, worst_month, worst_month_net, worst_year, worst_year_net = cal
    side = _side_split(rows if mult != 1.25 else df.assign(net_usd=nets), nets if mult != 1.25 else nets)
    mae = _mae_mfe_stats(rows if mult != 1.25 else df, bars_idx)

    trade_ids = set(rows["trade_id"].astype(str))
    if mult == 1.25 and lo is not None:
        trade_ids = set(df["trade_id"].astype(str))
    units = _filter_units(units_all, trade_ids)

    intrabar = float(sc["stress"])
    closed = float(abs(sc["max_dd"]))
    if not skip_mtm and units:
        audit = audit_units(
            name=name,
            slug=name,
            source=UNIT_FILLS,
            bar_source=BARS_1M,
            bars=bars,
            units=units,
            instrument="US30",
            notes=policy,
            output_root=HUB / "audits",
            fee_per_unit=1.5,
        )
        intrabar = abs(float(audit.intrabar_mtm_dd_usd))
        closed = abs(float(audit.close_mtm_dd_usd))

    yearly = _yearly_table(rows if mult != 1.25 else df, nets)
    blocks = _three_year_blocks(rows if mult != 1.25 else df, nets)

    metrics = VariantMetrics(
        variant=name,
        status=status,
        policy=policy,
        band_lo=lo,
        band_hi=hi,
        multiplier=mult,
        campaigns=int(sc["n"]),
        units=len(units),
        net_usd=float(sc["net"]),
        gross_profit=gains,
        gross_loss=losses,
        profit_factor=pf,
        win_rate=float(sc["wr"]),
        avg_campaign=float(sc["avg"]),
        median_campaign=float(np.median(nets)) if nets.size else 0.0,
        closed_dd_usd=closed,
        intrabar_stress_usd=intrabar,
        net_over_stress=float(sc["net"] / intrabar) if intrabar else 0.0,
        cagr=cagr,
        ann_return=ann,
        worst_month_net=worst_month_net,
        worst_month=worst_month,
        worst_year_net=worst_year_net,
        worst_year=worst_year,
        max_consec_losses=_max_consecutive_losses(nets),
        mae_median_r=mae["mae_median_r"],
        mae_p75_r=mae["mae_p75_r"],
        mfe_median_r=mae["mfe_median_r"],
        mfe_p75_r=mae["mfe_p75_r"],
        long_n=int(side["long_n"]),
        long_net=float(side["long_net"]),
        long_wr=float(side["long_wr"]),
        short_n=int(side["short_n"]),
        short_net=float(side["short_net"]),
        short_wr=float(side["short_wr"]),
    )
    return metrics, yearly, blocks, rows if mult != 1.25 else df


def render_summary(
    metrics: Sequence[VariantMetrics],
    bucket_df: pd.DataFrame,
    baseline: VariantMetrics,
) -> str:
    lines = [
        "# US30 ST+PMC 3R — prior-day range structure (locked bands)",
        "",
        "Study: `%s`" % STUDY,
        "",
        "Engine: broker-realistic `us30_hourly_st_pmc_sl50_tp150_3r_1mfill` (1m fill tape,",
        "stop-first / gap-through, lot-correct MTM). Filters are causal sit-outs on the",
        "same campaign tape — not a separate idealized simulator.",
        "",
        "Locked bands (pre-specified): 25–75%, 33–66%, 40–60%; overlay diagnostic 1.25× on 33–66%.",
        "",
        "## Baseline (all signals @ 1.00×)",
        "",
        "| metric | value |",
        "|---|---:|",
        "| campaigns | %d |" % baseline.campaigns,
        "| net P&L | $%+.0f |" % baseline.net_usd,
        "| gross profit / loss | $%+.0f / $%.0f |" % (baseline.gross_profit, baseline.gross_loss),
        "| profit factor | %.2f |" % baseline.profit_factor,
        "| win rate | %.1f%% |" % (100 * baseline.win_rate),
        "| avg / median campaign | $%+.0f / $%+.0f |" % (baseline.avg_campaign, baseline.median_campaign),
        "| closed DD | $%.0f |" % baseline.closed_dd_usd,
        "| intrabar MTM stress | $%.0f |" % baseline.intrabar_stress_usd,
        "| Net / Stress | %.2f |" % baseline.net_over_stress,
        "| CAGR ( $100k start ) | %.1f%% |" % (100 * baseline.cagr),
        "| worst month / year | %s ($%+.0f) / %d ($%+.0f) |"
        % (baseline.worst_month, baseline.worst_month_net, baseline.worst_year, baseline.worst_year_net),
        "| max consecutive losses | %d |" % baseline.max_consec_losses,
        "| long / short | n=%d $%+.0f WR=%.0f%% · n=%d $%+.0f WR=%.0f%% |"
        % (
            baseline.long_n,
            baseline.long_net,
            100 * baseline.long_wr,
            baseline.short_n,
            baseline.short_net,
            100 * baseline.short_wr,
        ),
        "",
        "## Variant matrix",
        "",
        "| variant | status | n | net | PF | WR | avg | closed DD | intrabar stress | N/S | CAGR |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for m in metrics:
        lines.append(
            "| %s | %s | %d | $%+.0f | %.2f | %.0f%% | $%+.0f | $%.0f | $%.0f | %.2f | %.1f%% |"
            % (
                m.variant,
                m.status,
                m.campaigns,
                m.net_usd,
                m.profit_factor,
                100 * m.win_rate,
                m.avg_campaign,
                m.closed_dd_usd,
                m.intrabar_stress_usd,
                m.net_over_stress,
                100 * m.cagr,
            )
        )
    lines.extend(
        [
            "",
            "## Opportunity-cost buckets (baseline tape)",
            "",
            "Tercile buckets on 252d rolling prior-day range percentile (same feature as HP profile).",
            "",
            bucket_df.to_markdown(index=False, floatfmt=".2f"),
            "",
            "## Decision read",
            "",
        ]
    )
    broad = next((m for m in metrics if m.variant == "broad_central_filter"), None)
    terc = next((m for m in metrics if m.variant == "original_tercile_filter"), None)
    narrow = next((m for m in metrics if m.variant == "narrow_central_diagnostic"), None)
    if baseline and broad and terc:
        if broad.net_over_stress > baseline.net_over_stress and terc.net_over_stress <= baseline.net_over_stress:
            lines.append(
                "- **Broad 25–75% filter beats baseline on N/S; original 33–66% tercile does not** — "
                "supports shadow risk-throttle hypothesis on the wide band, not the discovered tercile alone."
            )
        elif terc.net_over_stress > baseline.net_over_stress and broad.net_over_stress <= baseline.net_over_stress:
            lines.append(
                "- **Only the narrow 33–66% tercile wins** — maintain NOT VALIDATED; band-dependent, not robust."
            )
        elif baseline.net_over_stress >= max(m.net_over_stress for m in metrics if m.status == "primary"):
            lines.append(
                "- **Baseline wins on N/S among primary variants** — archive prior-range as descriptive discovery only."
            )
        else:
            lines.append("- Mixed primary-variant ranking — see yearly / 3-year block CSVs per variant.")
    if narrow and narrow.net_over_stress < (terc.net_over_stress if terc else 0):
        lines.append(
            "- **40–60% diagnostic collapses vs 33–66%** — reinforces narrow-band fragility."
        )
    lines.extend(["", "## Artifacts", "", "- `variants/<slug>/RESULT.json`, `yearly.csv`, `blocks_3y.csv`", "- `opportunity_buckets.csv`", "- `SUMMARY.md` / `EMAIL.txt`"])
    return "\n".join(lines) + "\n"


def run(*, email: bool = False, skip_mtm: bool = False) -> int:
    HUB.mkdir(parents=True, exist_ok=True)
    _progress("loading campaigns from broker fills …")
    book = next(b for b in DEFAULT_BOOKS if b.key == BOOK)
    camp = load_campaigns(book)
    df = _attach_prior_range_raw(camp)
    df = df[df["prior_day_range_pct_raw"].notna()].sort_values("entry_ts").reset_index(drop=True)
    _progress("campaigns with feature: %d" % len(df))

    units_all = _load_units()
    _progress("loading 1m bars …")
    bars = read_bars(BARS_1M, ts_field="ts_event")
    bars_idx = _load_1m_index()

    all_metrics: List[VariantMetrics] = []
    for name, status, lo, hi, mult in LOCKED_VARIANTS:
        _progress("variant %s …" % name)
        vdir = HUB / "variants" / name
        vdir.mkdir(parents=True, exist_ok=True)
        m, yearly, blocks, vrows = evaluate_variant(
            df,
            name=name,
            status=status,
            lo=lo,
            hi=hi,
            mult=mult,
            units_all=units_all,
            bars=bars,
            bars_idx=bars_idx,
            skip_mtm=skip_mtm,
        )
        all_metrics.append(m)
        yearly.to_csv(vdir / "yearly.csv", index=False)
        blocks.to_csv(vdir / "blocks_3y.csv", index=False)
        vrows.to_csv(vdir / "campaigns.csv", index=False)
        (vdir / "RESULT.json").write_text(json.dumps(asdict(m), indent=2), encoding="utf-8")

    bucket_df = _bucket_opportunity(df)
    bucket_df.to_csv(HUB / "opportunity_buckets.csv", index=False)
    pd.DataFrame([asdict(m) for m in all_metrics]).to_csv(HUB / "variant_matrix.csv", index=False)

    baseline = all_metrics[0]
    summary = render_summary(all_metrics, bucket_df, baseline)
    (HUB / "SUMMARY.md").write_text(summary, encoding="utf-8")

    body = [
        "US30 ST+PMC 3R prior-range structure study complete.",
        "Hub: %s" % HUB,
        "",
        "Baseline: n=%d net=$%+.0f N/S=%.2f WR=%.0f%%" % (
            baseline.campaigns,
            baseline.net_usd,
            baseline.net_over_stress,
            100 * baseline.win_rate,
        ),
        "",
    ]
    for m in all_metrics[1:]:
        body.append(
            "%s [%s]: n=%d net=$%+.0f N/S=%.2f (Δnet %+.0f vs baseline)"
            % (m.variant, m.status, m.campaigns, m.net_usd, m.net_over_stress, m.net_usd - baseline.net_usd)
        )
    body.append("")
    body.append("See SUMMARY.md for opportunity-cost buckets and decision read.")
    email_txt = "\n".join(body)
    (HUB / "EMAIL.txt").write_text(email_txt, encoding="utf-8")
    (HUB / "RUN_COMPLETE.json").write_text(
        json.dumps({"study": STUDY, "hub": str(HUB), "variants": [m.variant for m in all_metrics]}, indent=2),
        encoding="utf-8",
    )
    if email:
        send_email(subject="potions: US30 ST+PMC 3R prior-range structure complete", body=email_txt)
        _progress("email_sent")
    return 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--email", action="store_true")
    ap.add_argument("--skip-mtm", action="store_true", help="Skip intrabar MTM re-audit (faster; closed DD only)")
    args = ap.parse_args(argv)
    try:
        return run(email=args.email, skip_mtm=args.skip_mtm)
    except Exception:
        tb = traceback.format_exc()
        _progress("FATAL\n%s" % tb)
        if args.email:
            send_email(subject="potions: US30 ST+PMC 3R prior-range structure FAILED", body=tb[-4000:])
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
