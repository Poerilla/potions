"""Cluster Monday-OR breakout losers vs 1h MA50/150 and OBV vs OBV-SMA.

Joins each primary trade's entry to the last completed 1h bar and reports:
- price vs MA50 / MA150 regime and MA50×MA150 cross state
- OBV vs OBV SMA (default 20) bull/bear alignment with trade side
- how flat@50% (failed breaks) cluster under those filters
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional, Sequence

import numpy as np
import pandas as pd
import pytz

from .eurusd_monday_or_breakout_15m import DEFAULT_OUT, resample_15m
from .fx_data import ensure_eurusd_platform_files, load_fx_1m_by_ny_date
from .ym_hourly_st_pmc_retest_replay import concat_all_1m


REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
INSTRUMENT = "EURUSD"


def resample_1h(df_1m: pd.DataFrame) -> pd.DataFrame:
    return (
        df_1m.resample("1h", label="left", closed="left")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .dropna(subset=["open"])
    )


def add_htf_features(h1: pd.DataFrame, *, obv_ma: int = 20) -> pd.DataFrame:
    out = h1.copy()
    out["ma50"] = out["close"].rolling(50, min_periods=50).mean()
    out["ma150"] = out["close"].rolling(150, min_periods=150).mean()
    out["ma_bull"] = out["ma50"] > out["ma150"]
    # cross on this bar
    prev_bull = out["ma_bull"].shift(1)
    out["ma_bull_cross"] = out["ma_bull"] & ~prev_bull.fillna(False)
    out["ma_bear_cross"] = (~out["ma_bull"]) & prev_bull.fillna(False)

    direction = np.sign(out["close"].diff()).fillna(0.0)
    vol = out["volume"].fillna(0.0).clip(lower=0.0)
    # If volume is sparse/zero, fall back to range proxy so OBV still moves
    proxy = (out["high"] - out["low"]).clip(lower=1e-8)
    use_vol = vol.where(vol > 0, proxy)
    out["obv"] = (direction * use_vol).cumsum()
    out["obv_ma"] = out["obv"].rolling(obv_ma, min_periods=obv_ma).mean()
    out["obv_bull"] = out["obv"] > out["obv_ma"]
    prev_obv = out["obv_bull"].shift(1)
    out["obv_bull_cross"] = out["obv_bull"] & ~prev_obv.fillna(False)
    out["obv_bear_cross"] = (~out["obv_bull"]) & prev_obv.fillna(False)
    return out


def align_label(side: str, bull: bool) -> str:
    if side == "long":
        return "aligned" if bull else "opposed"
    return "aligned" if (not bull) else "opposed"


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trades",
        type=Path,
        default=DEFAULT_OUT / "trades.csv",
        help="Primary breakout trades.csv (filters to is_reverse_fade!=1 if present)",
    )
    parser.add_argument("--obv-ma", type=int, default=20)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUT / "HTF_LOSER_CLUSTERS.md",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    trades = pd.read_csv(args.trades)
    if "is_reverse_fade" in trades.columns:
        trades = trades[trades["is_reverse_fade"].fillna(0).astype(int) == 0].copy()
    trades["entry_ts"] = pd.to_datetime(trades["entry_ts"], utc=True).dt.tz_convert(NY)

    one_m_path, _ = ensure_eurusd_platform_files(REPO)
    print("Loading 1m → 1h features...", flush=True)
    bars_by_day = load_fx_1m_by_ny_date(one_m_path, INSTRUMENT)
    m1 = concat_all_1m(bars_by_day)
    if m1.index.tz is None:
        m1.index = m1.index.tz_localize(NY)
    else:
        m1.index = m1.index.tz_convert(NY)
    h1 = add_htf_features(resample_1h(m1), obv_ma=args.obv_ma)
    # asof join: last completed 1h bar at/before entry
    feat = h1.reset_index().rename(columns={"index": "bar_ts"})
    if "bar_ts" not in feat.columns:
        feat = h1.copy()
        feat["bar_ts"] = feat.index
        feat = feat.reset_index(drop=True)
    feat = feat.sort_values("bar_ts")
    t = trades.sort_values("entry_ts")
    merged = pd.merge_asof(
        t,
        feat[
            [
                "bar_ts",
                "close",
                "ma50",
                "ma150",
                "ma_bull",
                "ma_bull_cross",
                "ma_bear_cross",
                "obv_bull",
                "obv_bull_cross",
                "obv_bear_cross",
            ]
        ],
        left_on="entry_ts",
        right_on="bar_ts",
        direction="backward",
    )
    merged = merged.dropna(subset=["ma50", "ma150", "obv_bull"])
    merged["ma_align"] = [
        align_label(s, bool(b)) for s, b in zip(merged["side"], merged["ma_bull"])
    ]
    merged["obv_align"] = [
        align_label(s, bool(b)) for s, b in zip(merged["side"], merged["obv_bull"])
    ]
    merged["is_flat50"] = merged["exit_reason"].astype(str).str.endswith("flat_at_50")
    merged["is_loss"] = merged["result"].astype(str) == "loss"
    merged["is_win"] = merged["result"].astype(str) == "win"

    def block(title: str, key: str) -> list:
        lines = [f"### {title}", "", "| Bucket | n | Wins | Losses | Flat@50 | WR | Net |", "|---|---:|---:|---:|---:|---:|---:|"]
        for name, g in merged.groupby(key):
            n = len(g)
            w = int(g["is_win"].sum())
            l = int(g["is_loss"].sum())
            f50 = int(g["is_flat50"].sum())
            wr = 100.0 * w / n if n else 0.0
            net = float(g["pnl_usd"].sum())
            lines.append(f"| {name} | {n} | {w} | {l} | {f50} | {wr:.1f}% | ${net:,.0f} |")
        lines.append("")
        return lines

    # Cross: MA opposed + OBV opposed among flat50
    flat = merged[merged["is_flat50"]]
    both_opp = flat[(flat["ma_align"] == "opposed") & (flat["obv_align"] == "opposed")]
    both_aln = flat[(flat["ma_align"] == "aligned") & (flat["obv_align"] == "aligned")]
    ma_opp = flat[flat["ma_align"] == "opposed"]
    obv_opp = flat[flat["obv_align"] == "opposed"]

    # Fresh cross on entry hour
    merged["fresh_ma_opp_cross"] = (
        ((merged["side"] == "long") & merged["ma_bear_cross"])
        | ((merged["side"] == "short") & merged["ma_bull_cross"])
    )
    merged["fresh_obv_opp_cross"] = (
        ((merged["side"] == "long") & merged["obv_bear_cross"])
        | ((merged["side"] == "short") & merged["obv_bull_cross"])
    )

    lines = [
        "# Monday OR breakout — 1h HTF loser clusters",
        "",
        f"Primary trades joined to last completed 1h bar at entry. OBV SMA = {args.obv_ma}.",
        f"Sample: **{len(merged)}** trades with valid MA/OBV (of {len(trades)} primary).",
        "",
        "## Summary",
        "",
        f"- Flat@50% (failed breaks): **{int(merged['is_flat50'].sum())}**",
        f"- Of flat@50%: MA **opposed** {len(ma_opp)} ({100*len(ma_opp)/max(len(flat),1):.0f}%), "
        f"OBV **opposed** {len(obv_opp)} ({100*len(obv_opp)/max(len(flat),1):.0f}%)",
        f"- Flat@50% with **both** MA+OBV opposed: **{len(both_opp)}** "
        f"({100*len(both_opp)/max(len(flat),1):.0f}%) net ${both_opp['pnl_usd'].sum():,.0f}",
        f"- Flat@50% with **both** aligned: **{len(both_aln)}** "
        f"({100*len(both_aln)/max(len(flat),1):.0f}%) net ${both_aln['pnl_usd'].sum():,.0f}",
        "",
    ]
    lines.extend(block("MA50 vs MA150 regime (aligned = trade with MA50>MA150 for longs)", "ma_align"))
    lines.extend(block(f"OBV vs OBV-SMA{args.obv_ma} regime", "obv_align"))

    # Combo table
    lines.extend(
        [
            "### MA × OBV combo",
            "",
            "| MA | OBV | n | Flat@50 | WR | Net |",
            "|---|---|---:|---:|---:|---:|",
        ]
    )
    for (ma, obv), g in merged.groupby(["ma_align", "obv_align"]):
        n = len(g)
        f50 = int(g["is_flat50"].sum())
        wr = 100.0 * g["is_win"].mean()
        lines.append(f"| {ma} | {obv} | {n} | {f50} | {wr:.1f}% | ${g['pnl_usd'].sum():,.0f} |")
    lines.append("")

    # Fresh cross
    for label, col in [
        ("Fresh 1h MA50/150 cross opposed to trade", "fresh_ma_opp_cross"),
        (f"Fresh 1h OBV×SMA{args.obv_ma} cross opposed to trade", "fresh_obv_opp_cross"),
    ]:
        g = merged[merged[col]]
        o = merged[~merged[col]]
        lines.extend(
            [
                f"### {label}",
                "",
                f"- Yes: n={len(g)} flat50={int(g['is_flat50'].sum())} WR={100*g['is_win'].mean():.1f}% net=${g['pnl_usd'].sum():,.0f}",
                f"- No:  n={len(o)} flat50={int(o['is_flat50'].sum())} WR={100*o['is_win'].mean():.1f}% net=${o['pnl_usd'].sum():,.0f}",
                "",
            ]
        )

    # If we skipped opposed-MA entries, hypothetical
    keep = merged[merged["ma_align"] == "aligned"]
    skip = merged[merged["ma_align"] == "opposed"]
    lines.extend(
        [
            "## Hypothetical filter: skip MA-opposed entries",
            "",
            f"- Keep aligned: n={len(keep)} net=${keep['pnl_usd'].sum():,.0f} WR={100*keep['is_win'].mean():.1f}% flat50={int(keep['is_flat50'].sum())}",
            f"- Skip opposed: n={len(skip)} net=${skip['pnl_usd'].sum():,.0f} WR={100*skip['is_win'].mean():.1f}% flat50={int(skip['is_flat50'].sum())}",
            "",
            "## Hypothetical filter: skip OBV-opposed entries",
            "",
        ]
    )
    keep_o = merged[merged["obv_align"] == "aligned"]
    skip_o = merged[merged["obv_align"] == "opposed"]
    lines.extend(
        [
            f"- Keep aligned: n={len(keep_o)} net=${keep_o['pnl_usd'].sum():,.0f} WR={100*keep_o['is_win'].mean():.1f}% flat50={int(keep_o['is_flat50'].sum())}",
            f"- Skip opposed: n={len(skip_o)} net=${skip_o['pnl_usd'].sum():,.0f} WR={100*skip_o['is_win'].mean():.1f}% flat50={int(skip_o['is_flat50'].sum())}",
            "",
            "## Hypothetical: skip when BOTH MA and OBV opposed",
            "",
        ]
    )
    both_opp_all = merged[(merged["ma_align"] == "opposed") & (merged["obv_align"] == "opposed")]
    keep_b = merged[~((merged["ma_align"] == "opposed") & (merged["obv_align"] == "opposed"))]
    lines.extend(
        [
            f"- Skip both-opposed: n={len(both_opp_all)} net=${both_opp_all['pnl_usd'].sum():,.0f} flat50={int(both_opp_all['is_flat50'].sum())}",
            f"- Keep rest: n={len(keep_b)} net=${keep_b['pnl_usd'].sum():,.0f} WR={100*keep_b['is_win'].mean():.1f}% flat50={int(keep_b['is_flat50'].sum())}",
            "",
        ]
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(lines), encoding="utf-8")
    # also dump joined csv for digging
    merged.to_csv(args.output.with_suffix(".csv"), index=False)
    print("Wrote %s" % args.output, flush=True)
    print(
        "flat50=%d | both-opposed flat50=%d | MA-aligned net=$%.0f | MA-opposed net=$%.0f"
        % (
            int(merged["is_flat50"].sum()),
            len(both_opp),
            keep["pnl_usd"].sum(),
            skip["pnl_usd"].sum(),
        ),
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
