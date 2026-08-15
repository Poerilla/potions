"""London-session 5m charts for FX v2b runs with structure/ST overlays.

For each FX pair trade day sample:

- **5m candles** clipped to the London clock (03:00–12:00 America/New_York)
- **Prior NY range** = previous trading day's NY cash session high/low (09:30–16:00)
- **4h SuperTrend** ATR(14)×3 trail (forward-filled onto the 5m grid)
- **4h structure bias** label for the day (StructureProgramEngine on 4h FX bars,
  snapshot at London open)

Trade markers (v2b entry/exits) are drawn when fills are available.

Usage::

  python -m live.fx_v2b_london_5m_bias_charts \\
    --hubs ungated,prior_opposed,prior_aligned \\
    --markets EURUSD,GBPUSD,USDJPY,AUDJPY \\
    --max-charts 40 --email
"""

from __future__ import annotations

import argparse
import shutil
from datetime import date, datetime, time
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .bars import RTH_CLOSE, RTH_OPEN
from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .fx_data import load_fx_1m_by_ny_date
from .fx_or_markets import CLOCKS, session_bars
from .fx_v2b_london_ungated import MARKETS, MarketSpec, _usd_norm
from .nq_v2b_prior_opposed_15m_charts import (
    FillTrade,
    _draw_v2b_trade,
    _load_v2b_fill_groups,
    _load_v2b_trades,
    _plot_candles,
)
from .structure_program_st_chart_bias_4h import _ingest_4h_day, to_4h
from .structure_program_st_study import ATR_LEN, ATR_MULT, StructureProgramEngine

REPO = Path(__file__).resolve().parents[1]
NY = "America/New_York"
LONDON = CLOCKS["london_open"]
DEFAULT_OUT = REPO / "live" / "state" / "fx_v2b_london_charts"
DEFAULT_BOOK = "S_1_1_3"
FX_PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDJPY")
LOOKBACK_DAYS = 40

HUB_SPECS = {
    "ungated": {
        "root": REPO / "live" / "state" / "fx_v2b_london_ungated",
        "strategy_id": lambda sym, book: "%s_v2b_london_%s" % (sym.lower(), book),
    },
    "prior_opposed": {
        "root": REPO / "live" / "state" / "fx_v2b_london_prior_opposed",
        "strategy_id": lambda sym, book: "%s_v2b_london_prior_opposed_%s" % (sym.lower(), book),
    },
    "prior_aligned": {
        "root": REPO / "live" / "state" / "fx_v2b_london_prior_aligned",
        "strategy_id": lambda sym, book: "%s_v2b_london_prior_aligned_%s" % (sym.lower(), book),
    },
}

BUY_SHADE = "#bbdefb"
SELL_SHADE = "#f8bbd0"
NY_RANGE_COLOR = "#6a1b9a"
ST_BULL = "#009c5b"
ST_BEAR = "#d62728"
OR_COLOR = "#1565c0"


def _resample_5m(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    return (
        frame.resample("5min", label="right", closed="right")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum") if "volume" in frame.columns else ("close", "count"),
        )
        .dropna(subset=["open", "high", "low", "close"])
    )


def _sample_even(trades: List[FillTrade], max_n: int) -> List[FillTrade]:
    if max_n is None or max_n < 0 or len(trades) <= max_n:
        return list(trades)
    if max_n == 0:
        return []
    idx = np.linspace(0, len(trades) - 1, num=max_n, dtype=int)
    seen = set()
    out: List[FillTrade] = []
    for i in idx:
        i = int(i)
        if i in seen:
            continue
        seen.add(i)
        out.append(trades[i])
    return out


def _select_trades(
    trades: List[FillTrade],
    max_charts: int,
    *,
    max_wins: Optional[int] = None,
    max_losses: Optional[int] = None,
) -> List[FillTrade]:
    """Evenly sample trades. Optional win/loss caps take precedence over max_charts."""
    ordered = sorted(trades, key=lambda t: t.entry_ts)
    if max_wins is not None or max_losses is not None:
        wins = [t for t in ordered if t.net_usd > 0]
        losses = [t for t in ordered if t.net_usd <= 0]
        out: List[FillTrade] = []
        if max_wins is not None:
            out.extend(_sample_even(wins, max_wins))
        if max_losses is not None:
            out.extend(_sample_even(losses, max_losses))
        return sorted(out, key=lambda t: t.entry_ts)
    return _sample_even(ordered, max_charts)


def _prior_ny_range(
    gby: Dict[date, pd.DataFrame],
    session: date,
) -> Optional[Tuple[float, float, date]]:
    """Prior trading day's NY cash-session high/low (09:30–16:00)."""
    priors = sorted(d for d in gby if d < session)
    for prior in reversed(priors):
        raw = gby.get(prior)
        if raw is None or raw.empty:
            continue
        day = raw.copy()
        if day.index.tz is None:
            day.index = day.index.tz_localize(NY)
        else:
            day.index = day.index.tz_convert(NY)
        rth = day[(day.index.time >= RTH_OPEN) & (day.index.time < RTH_CLOSE)]
        if rth.empty or len(rth) < 30:
            continue
        return float(rth["high"].max()), float(rth["low"].min()), prior
    return None


def _london_or(london_1m: pd.DataFrame) -> Optional[Tuple[float, float]]:
    opening = london_1m[
        (london_1m.index.time >= LONDON.or_start) & (london_1m.index.time < LONDON.or_end)
    ]
    if opening.empty:
        return None
    return float(opening["high"].max()), float(opening["low"].min())


def _walk_4h_bias_and_st(
    gby: Dict[date, pd.DataFrame],
) -> Tuple[Dict[date, Optional[str]], pd.DataFrame]:
    """Causal 4h structure bias at London open + continuous 4h SuperTrend."""
    eng = StructureProgramEngine()
    buf: List[pd.DataFrame] = []
    bars4h_frames: List[pd.DataFrame] = []
    bias_at_london: Dict[date, Optional[str]] = {}
    days = sorted(gby)

    for di, d in enumerate(days, 1):
        raw = gby.get(d)
        if raw is None or raw.empty:
            continue
        day = raw.copy()
        if day.index.tz is None:
            day.index = day.index.tz_localize(NY)
        else:
            day.index = day.index.tz_convert(NY)
        day = day[~day.index.duplicated(keep="last")].sort_index()
        if day.empty:
            continue

        london_open = pd.Timestamp(datetime.combine(d, LONDON.or_start), tz=NY)
        pre = day[day.index < london_open]
        post = day[day.index >= london_open]

        # Ingest pre-London bars first so the day label is causal at open.
        if not pre.empty:
            b4_pre = to_4h(pre)
            if not b4_pre.empty:
                _ingest_4h_day(eng, b4_pre, buf[-LOOKBACK_DAYS:])
                buf.append(b4_pre)
                buf = buf[-LOOKBACK_DAYS:]
                bars4h_frames.append(b4_pre)

        bias_at_london[d] = eng.program if eng.ready else None

        if not post.empty:
            b4_post = to_4h(post)
            if not b4_post.empty:
                _ingest_4h_day(eng, b4_post, buf[-LOOKBACK_DAYS:])
                buf.append(b4_post)
                buf = buf[-LOOKBACK_DAYS:]
                bars4h_frames.append(b4_post)

        if di % 500 == 0:
            print(
                "  4h walk %d/%d bias=%s ready=%s"
                % (di, len(days), eng.program, eng.ready),
                flush=True,
            )

    if not bars4h_frames:
        return bias_at_london, pd.DataFrame()
    full = pd.concat(bars4h_frames).sort_index()
    full = full[~full.index.duplicated(keep="last")]
    st = compute_supertrend(full, atr_len=ATR_LEN, multiplier=ATR_MULT)
    return bias_at_london, st


def _overlay_4h_st(ax, candles: pd.DataFrame, st_4h: pd.DataFrame) -> None:
    if st_4h is None or st_4h.empty or candles.empty:
        return
    overlay = st_4h[["supertrend", "supertrend_trend"]].reindex(candles.index, method="ffill")
    bull = overlay["supertrend"].where(overlay["supertrend_trend"] == 1)
    bear = overlay["supertrend"].where(overlay["supertrend_trend"] == -1)
    ax.plot(
        candles.index,
        bull,
        color=ST_BULL,
        linewidth=1.6,
        label="4h ST ATR(%d)×%g bull" % (ATR_LEN, ATR_MULT),
        zorder=5,
    )
    ax.plot(
        candles.index,
        bear,
        color=ST_BEAR,
        linewidth=1.6,
        label="4h ST ATR(%d)×%g bear" % (ATR_LEN, ATR_MULT),
        zorder=5,
    )


def _draw_levels(
    ax,
    candles: pd.DataFrame,
    *,
    prior_ny: Optional[Tuple[float, float, date]],
    or_levels: Optional[Tuple[float, float]],
    bias: Optional[str],
) -> None:
    t0, t1 = candles.index[0], candles.index[-1]
    if bias == "buy":
        ax.axvspan(t0, t1, color=BUY_SHADE, alpha=0.18, zorder=0, label="4h bias BUY")
    elif bias == "sell":
        ax.axvspan(t0, t1, color=SELL_SHADE, alpha=0.18, zorder=0, label="4h bias SELL")

    if prior_ny is not None:
        ny_h, ny_l, prior_day = prior_ny
        ax.hlines(
            ny_h,
            t0,
            t1,
            colors=NY_RANGE_COLOR,
            linestyles="--",
            linewidth=1.35,
            alpha=0.95,
            label="Prior NY H/L (%s)" % prior_day.isoformat(),
        )
        ax.hlines(ny_l, t0, t1, colors=NY_RANGE_COLOR, linestyles="--", linewidth=1.35, alpha=0.95)
        ax.text(t0, ny_h, " Prior NY high", color=NY_RANGE_COLOR, fontsize=8, va="bottom")
        ax.text(t0, ny_l, " Prior NY low", color=NY_RANGE_COLOR, fontsize=8, va="top")

    if or_levels is not None:
        or_h, or_l = or_levels
        ax.axhspan(or_l, or_h, color=OR_COLOR, alpha=0.12, zorder=1, label="London OR 03:00-03:15")
        ax.hlines(or_h, t0, t1, colors=OR_COLOR, linestyles="-", linewidth=1.0, alpha=0.8)
        ax.hlines(or_l, t0, t1, colors=OR_COLOR, linestyles="-", linewidth=1.0, alpha=0.8)


def _load_trades_for_market(
    fills: Path,
    market: MarketSpec,
) -> List[FillTrade]:
    import live.nq_v2b_prior_opposed_15m_charts as base

    base.POINT_VALUE = market.point_value
    base.FEE_PER_UNIT = market.fee_per_unit
    trades = _load_v2b_trades(fills)
    if market.quote == "JPY":
        for i, t in enumerate(trades):
            trades[i] = FillTrade(
                trade_id=t.trade_id,
                side=t.side,
                entry_ts=t.entry_ts,
                entry_price=t.entry_price,
                exit_ts=t.exit_ts,
                exit_price=t.exit_price,
                net_usd=_usd_norm(t.net_usd, market.quote),
            )
    return trades


def chart_market_hub(
    *,
    hub_name: str,
    market: MarketSpec,
    book: str,
    output_root: Path,
    max_charts: int,
    force: bool,
    gby: Optional[Dict[date, pd.DataFrame]] = None,
    bias_by_day: Optional[Dict[date, Optional[str]]] = None,
    st_4h: Optional[pd.DataFrame] = None,
    max_wins: Optional[int] = None,
    max_losses: Optional[int] = None,
) -> int:
    hub = HUB_SPECS[hub_name]
    strategy_id = hub["strategy_id"](market.symbol, book)
    fills = hub["root"] / "states" / strategy_id / "fills.csv"
    if not fills.exists():
        print("  skip %s/%s: missing %s" % (hub_name, market.symbol, fills), flush=True)
        return 0

    out = output_root / hub_name / market.symbol.lower()
    if force and out.exists():
        shutil.rmtree(out)
    charts_dir = out / "charts"
    charts_dir.mkdir(parents=True, exist_ok=True)

    if gby is None:
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        print("Loading %s 1m (%s / %s)..." % (market.symbol, hub_name, strategy_id), flush=True)
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)

    trades = sorted(_load_trades_for_market(fills, market), key=lambda t: t.entry_ts)
    trades = _select_trades(trades, max_charts, max_wins=max_wins, max_losses=max_losses)
    groups = _load_v2b_fill_groups(fills)

    if bias_by_day is None or st_4h is None:
        print("  walking 4h structure bias + SuperTrend...", flush=True)
        bias_by_day, st_4h = _walk_4h_bias_and_st(gby)
    assert bias_by_day is not None and st_4h is not None

    rows = []
    for idx, trade in enumerate(trades, start=1):
        session = trade.entry_ts.date()
        london_1m = session_bars(gby.get(session), session, LONDON, dense=True)
        if london_1m.empty or london_1m["close"].isna().all():
            continue
        london_1m = london_1m.dropna(subset=["open", "high", "low", "close"])
        candles = _resample_5m(london_1m)
        if candles.empty:
            continue

        prior_ny = _prior_ny_range(gby, session)
        or_levels = _london_or(london_1m)
        bias = bias_by_day.get(session)
        bias_label = (bias or "none").upper()

        fig, ax = plt.subplots(figsize=(17, 8))
        _plot_candles(ax, candles, width_days=(5 / (24 * 60)) * 0.7)
        _draw_levels(ax, candles, prior_ny=prior_ny, or_levels=or_levels, bias=bias)
        _overlay_4h_st(ax, candles, st_4h)
        fills_df = groups.get(trade.trade_id)
        if fills_df is not None:
            _draw_v2b_trade(ax, trade, fills_df)

        ax.set_title(
            "%s %s %s | London 5m | 4h bias=%s | %s %s | net $%.0f"
            % (
                market.symbol,
                hub_name,
                book,
                bias_label,
                session.isoformat(),
                trade.side,
                trade.net_usd,
            )
        )
        ax.set_ylabel(market.symbol)
        ax.grid(True, color="#dedede", linewidth=0.6, alpha=0.75)
        ax.legend(loc="upper left", fontsize=8)
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=1, tz=candles.index.tz))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M", tz=candles.index.tz))
        ax.set_xlabel("Time (America/New_York) — London session only")
        fig.autofmt_xdate()

        rel = Path("charts") / (
            "%03d_%s_%s_%s.png"
            % (idx, session.isoformat(), trade.side, "win" if trade.net_usd > 0 else "loss")
        )
        fig.savefig(out / rel, dpi=130, bbox_inches="tight")
        plt.close(fig)
        rows.append(
            {
                "idx": idx,
                "hub": hub_name,
                "market": market.symbol,
                "session": session.isoformat(),
                "side": trade.side,
                "net_usd": trade.net_usd,
                "bias_4h": bias_label,
                "prior_ny_day": prior_ny[2].isoformat() if prior_ny else "",
                "prior_ny_high": prior_ny[0] if prior_ny else "",
                "prior_ny_low": prior_ny[1] if prior_ny else "",
                "trade_id": trade.trade_id,
                "chart": str(rel),
            }
        )
        if idx % 20 == 0:
            print("  charted %d/%d" % (idx, len(trades)), flush=True)

    pd.DataFrame(rows).to_csv(out / "chart_manifest.csv", index=False)
    lines = [
        "# %s — %s London 5m bias charts" % (market.symbol, hub_name),
        "",
        "London clock only (**03:00–12:00** America/New_York). Book `%s` / `%s`."
        % (book, strategy_id),
        "",
        "Overlays:",
        "- Prior NY cash range (prev day 09:30–16:00 H/L)",
        "- 4h SuperTrend ATR(%d)×%g" % (ATR_LEN, ATR_MULT),
        "- Day bias label from 4h StructureProgramEngine at London open",
        "- v2b entry/exit markers",
        "",
        "Charts: **%d**" % len(rows),
        "",
        "| # | Session | Side | Bias | Net | Chart |",
        "|---:|---|---|---|---:|---|",
    ]
    for item in rows:
        lines.append(
            "| {idx} | {session} | {side} | {bias_4h} | ${net_usd:,.0f} | [{chart}]({chart}) |".format(
                **item
            )
        )
    (out / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("  wrote %d charts -> %s" % (len(rows), out), flush=True)
    return len(rows)


def build_all(
    *,
    hubs: Sequence[str],
    markets: Sequence[str],
    book: str,
    output_root: Path,
    max_charts: int,
    force: bool,
    max_wins: Optional[int] = None,
    max_losses: Optional[int] = None,
) -> Dict[str, int]:
    output_root.mkdir(parents=True, exist_ok=True)
    counts: Dict[str, int] = {}
    for sym in markets:
        if sym not in MARKETS:
            raise SystemExit("unknown market %s" % sym)
        market = MARKETS[sym]
        active_hubs = [
            h
            for h in hubs
            if h in HUB_SPECS and HUB_SPECS[h]["root"].exists()
        ]
        if not active_hubs:
            continue
        # Load + 4h walk once per market, reuse across hubs.
        one_m = REPO / "fx" / ("%s_1m.csv" % market.symbol.lower())
        print("Loading %s 1m for hubs=%s..." % (market.symbol, ",".join(active_hubs)), flush=True)
        gby = load_fx_1m_by_ny_date(one_m, market.symbol)
        print("  walking 4h structure bias + SuperTrend...", flush=True)
        bias_by_day, st_4h = _walk_4h_bias_and_st(gby)
        for hub_name in active_hubs:
            key = "%s/%s" % (hub_name, sym)
            counts[key] = chart_market_hub(
                hub_name=hub_name,
                market=market,
                book=book,
                output_root=output_root,
                max_charts=max_charts,
                force=force,
                gby=gby,
                bias_by_day=bias_by_day,
                st_4h=st_4h,
                max_wins=max_wins,
                max_losses=max_losses,
            )
    _write_root_index(
        output_root,
        hubs,
        markets,
        book,
        counts,
        max_wins=max_wins,
        max_losses=max_losses,
    )
    return counts


def _write_root_index(
    output_root: Path,
    hubs: Sequence[str],
    markets: Sequence[str],
    book: str,
    counts: Dict[str, int],
    *,
    max_wins: Optional[int] = None,
    max_losses: Optional[int] = None,
) -> None:
    lines = [
        "# FX v2b London 5m bias charts",
        "",
        "Generated %s." % datetime.now().isoformat(timespec="seconds"),
        "",
        "- Book: `%s`" % book,
        "- Session window: London **03:00–12:00** America/New_York (5m candles)",
        "- Prior NY range + 4h SuperTrend ATR(%d)×%g + 4h structure bias label"
        % (ATR_LEN, ATR_MULT),
    ]
    if max_wins is not None or max_losses is not None:
        lines.append(
            "- Sample caps: wins=%s losses=%s"
            % (
                max_wins if max_wins is not None else "—",
                max_losses if max_losses is not None else "—",
            )
        )
    lines.extend(
        [
            "",
            "| Hub | Market | Charts | Index |",
            "|---|---|---:|---|",
        ]
    )
    total = 0
    for hub in hubs:
        for sym in markets:
            key = "%s/%s" % (hub, sym)
            n = int(counts.get(key, 0))
            total += n
            rel = "%s/%s/INDEX.md" % (hub, sym.lower())
            path = output_root / rel
            link = "[INDEX](%s)" % rel if path.exists() else "—"
            lines.append("| %s | %s | %d | %s |" % (hub, sym, n, link))
    lines.extend(["", "Total charts: **%d**" % total, ""])
    (output_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")
    email = [
        "potions: FX London 5m bias charts complete",
        "",
        "Hub: %s" % output_root,
        "Book: %s" % book,
        "Markets: %s" % ",".join(markets),
        "Gates/hubs: %s" % ",".join(hubs),
        "Total charts: %d" % total,
    ]
    if max_wins is not None or max_losses is not None:
        email.append(
            "Sample: max_wins=%s max_losses=%s"
            % (max_wins, max_losses)
        )
    email.extend(
        [
            "",
            "Each chart: London-only 5m candles, prior NY H/L, 4h ST ATR trail,",
            "4h structure bias label, v2b markers.",
            "",
            "See INDEX.md for per-market links.",
        ]
    )
    (output_root / "EMAIL.txt").write_text("\n".join(email) + "\n", encoding="utf-8")


def hubs_ready(hubs: Sequence[str], markets: Sequence[str], book: str) -> Tuple[bool, List[str]]:
    missing: List[str] = []
    for hub_name in hubs:
        spec = HUB_SPECS[hub_name]
        root = spec["root"]
        if not root.exists():
            missing.append("%s (hub root)" % hub_name)
            continue
        # Prefer RUN_COMPLETE / EMAIL as batch-done signals when present.
        if hub_name == "ungated":
            if not (root / "RUN_COMPLETE.json").exists() and not (root / "EMAIL.txt").exists():
                missing.append("%s RUN_COMPLETE/EMAIL" % hub_name)
        else:
            if not (root / "EMAIL.txt").exists() and not (root / "summary.csv").exists():
                missing.append("%s EMAIL/summary" % hub_name)
        for sym in markets:
            sid = spec["strategy_id"](sym, book)
            fills = root / "states" / sid / "fills.csv"
            metrics = root / "states" / sid / "metrics.json"
            if not fills.exists() and not metrics.exists():
                missing.append("%s/%s" % (hub_name, sid))
    return (not missing), missing


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--hubs", default="ungated,prior_opposed,prior_aligned")
    ap.add_argument("--markets", default=",".join(FX_PAIRS))
    ap.add_argument("--book", default=DEFAULT_BOOK)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-charts", type=int, default=40)
    ap.add_argument(
        "--max-wins",
        type=int,
        default=None,
        help="Evenly sample this many winning day trades (net>0). Overrides --max-charts when set with --max-losses.",
    )
    ap.add_argument(
        "--max-losses",
        type=int,
        default=None,
        help="Evenly sample this many losing day trades (net<=0). Overrides --max-charts when set with --max-wins.",
    )
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument(
        "--wait-ready",
        action="store_true",
        help="Exit 2 if any requested hub/market fills are not ready yet",
    )
    args = ap.parse_args(argv)

    hubs = [h.strip() for h in args.hubs.split(",") if h.strip()]
    markets = [m.strip().upper() for m in args.markets.split(",") if m.strip()]
    ready, missing = hubs_ready(hubs, markets, args.book)
    if args.wait_ready and not ready:
        print("not ready yet: %s" % ", ".join(missing[:12]), flush=True)
        return 2

    counts = build_all(
        hubs=hubs,
        markets=markets,
        book=args.book,
        output_root=args.output_root,
        max_charts=args.max_charts,
        force=args.force,
        max_wins=args.max_wins,
        max_losses=args.max_losses,
    )
    total = sum(counts.values())
    print("TOTAL charts=%d -> %s" % (total, args.output_root), flush=True)

    if args.email:
        from .notify_email import send_email

        body = (args.output_root / "EMAIL.txt").read_text(encoding="utf-8")
        subject = "potions: FX London 5m bias charts complete"
        if args.max_wins is not None or args.max_losses is not None:
            subject = "potions: FX London v2b %s win/loss charts complete" % args.book
        send_email(subject=subject, body=body)
        print("email sent", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
