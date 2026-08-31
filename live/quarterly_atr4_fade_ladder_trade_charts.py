"""Quarterly 4h charts with ATR4-fade ladder fills + planned exit levels.

For each path in ``top3_paths.csv`` (or ``--path``), chart every quarter that
has a broker ladder trade: candles / open-week / ±ATR bands, plus entry /
stop / TP ladder lines and fill markers.
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import (
    ATR_LEN,
    NY,
    draw_atr_bands,
    draw_month_closes,
    draw_opening_week_range,
    load_4h,
    opening_week_slice,
    plot_candles,
    price_fmt,
    quarter_windows,
    shade_weeks,
    slug,
    wilder_atr,
)
from .notify_email import send_email
from .quarterly_atr4_fade_broker import MARKETS

REPO = Path(__file__).resolve().parents[1]
DEFAULT_TOP3 = REPO / "live" / "state" / "quarterly_atr4_top3_paths" / "top3_paths.csv"
DEFAULT_OUT = REPO / "live" / "state" / "quarterly_atr4_top3_trade_charts"
BEST_PATH_HUB = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_best_path"
FAMILY_HUB = REPO / "live" / "state" / "quarterly_atr4_fade_ladder"
SECOND_HUB = REPO / "live" / "state" / "quarterly_atr4_fade_ladder_us30_second_after_upper"
HA_HUB = REPO / "live" / "state" / "quarterly_atr4_ha_conditions"

# HA winners competitive vs top3 WR paths (WR≈58–73%): live_ready HP subsets
# with WR≥56% and n≥6, plus material size/filter lift on the be8 ladder tape.
HA_WINNERS: Tuple[Dict[str, str], ...] = (
    {
        "slug": "gbpusd_monday",
        "book": "gbpusd_first_lower",
        "market": "GBPUSD",
        "path_id": "first_lower",
        "fills_hub": "best_path",
        "condition": "Day of week",
        "bucket": "Monday",
        "why": "HP WR 60% n=15; size 1.25× ΔN/S +0.93 — matches/beats top3 GBPUSD WR",
    },
    {
        "slug": "gbpusd_hour12",
        "book": "gbpusd_first_lower",
        "market": "GBPUSD",
        "path_id": "first_lower",
        "fills_hub": "best_path",
        "condition": "Entry hour (NY)",
        "bucket": "12",
        "why": "HP WR 56% n=9; size 1.25× ΔN/S +0.97 — strongest GBPUSD hour sleeve",
    },
    {
        "slug": "eurusd_monday",
        "book": "eurusd_second_after_upper",
        "market": "EURUSD",
        "path_id": "second_after_upper",
        "fills_hub": "best_path",
        "condition": "Day of week",
        "bucket": "Monday",
        "why": "HP WR 67% n=6 — clears top3 GBPUSD WR bar; filter ΔN/S +5.7",
    },
    {
        "slug": "eurusd_ma_aligned",
        "book": "eurusd_second_after_upper",
        "market": "EURUSD",
        "path_id": "second_after_upper",
        "fills_hub": "best_path",
        "condition": "5m MA vs trade",
        "bucket": "ma_aligned",
        "why": "HP WR 57% n=7; filter lifts net AND N/S (rare dual lift)",
    },
    {
        "slug": "xauusd_week2",
        "book": "xauusd_first_only",
        "market": "XAUUSD",
        "path_id": "first_only_lower",
        "fills_hub": "family",
        "condition": "Week of month",
        "bucket": "2",
        "why": "HP WR 62% n=13 — competitive with top3 WR; size 1.25× ΔN/S +0.71",
    },
)

ROLE_COLORS = {
    "entry": "#1565c0",
    "stop": "#c62828",
    "tp1": "#2e7d32",
    "tp2": "#00838f",
    "tp3": "#6a1b9a",
    "tp4": "#ef6c00",
    "flatten": "#6d4c41",
    "quarter_close": "#6d4c41",
}


def _progress(output_root: Path, msg: str) -> None:
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    output_root.mkdir(parents=True, exist_ok=True)
    with (output_root / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _parse_ts(raw: Any) -> pd.Timestamp:
    ts = pd.Timestamp(raw)
    if ts.tzinfo is None:
        return ts.tz_localize("UTC").tz_convert(NY)
    return ts.tz_convert(NY)


def _ladder_state_root(market: str, path_id: str, *, fills_hub: str = "best_path") -> Path:
    market_u = market.upper()
    if market_u == "US30" and path_id == "second_after_upper":
        return SECOND_HUB / "states" / "us30_quarterly_atr4_fade_ladder"
    if fills_hub == "family" or path_id in {"first_only_lower", "first_only"}:
        return FAMILY_HUB / "states" / ("%s_quarterly_atr4_fade_ladder" % market.lower())
    return BEST_PATH_HUB / "states" / ("%s_quarterly_atr4_fade_ladder" % market.lower())


def _trade_windows(fills: pd.DataFrame) -> List[dict]:
    """One row per trade_id with entry/exit span and planned ladder prices."""
    out: List[dict] = []
    if fills.empty:
        return out
    fills = fills.copy()
    fills["ts_ny"] = fills["ts"].map(_parse_ts)
    for trade_id, g in fills.groupby("trade_id", sort=True):
        g = g.sort_values("ts_ny")
        entry = g[g["reason"] == "entry"]
        if entry.empty:
            continue
        e = entry.iloc[0]
        exits = g[g["reason"] != "entry"]
        exit_ts = exits["ts_ny"].iloc[-1] if not exits.empty else e["ts_ny"]
        direction = "Long" if str(e["side"]).lower() == "buy" else "Short"
        out.append(
            {
                "trade_id": str(trade_id),
                "direction": direction,
                "entry_ts": e["ts_ny"],
                "entry_price": float(e["price"]),
                "exit_ts": exit_ts,
                "fills": g,
                "year": int(e["ts_ny"].year),
                "quarter": int((int(e["ts_ny"].month) - 1) // 3 + 1),
            }
        )
    return out


def _planned_levels(orders: pd.DataFrame, trade_id: str) -> Dict[str, float]:
    """First stop / tp limit prices armed after entry for this trade."""
    levels: Dict[str, float] = {}
    if orders.empty:
        return levels
    sub = orders[orders["trade_id"].astype(str) == str(trade_id)].copy()
    if sub.empty:
        return levels
    # Prefer earliest created stop / tp limits (initial ladder, not BE updates).
    if "created_at" in sub.columns:
        sub = sub.sort_values("created_at")
    for _, row in sub.iterrows():
        role = str(row.get("bracket_role") or "")
        if role == "stop" and "stop" not in levels:
            px = row.get("stop_price")
            if pd.notna(px):
                levels["stop"] = float(px)
        elif role.startswith("tp") and role not in levels:
            px = row.get("limit_price")
            if pd.notna(px):
                levels[role] = float(px)
    return levels


def plot_trade_quarter(
    *,
    bars: pd.DataFrame,
    atr_series: pd.Series,
    year: int,
    quarter: int,
    t0: pd.Timestamp,
    t1: pd.Timestamp,
    out_path: Path,
    symbol: str,
    path_id: str,
    trades: Sequence[dict],
    orders: pd.DataFrame,
) -> Dict[str, Any]:
    fmt = price_fmt(symbol)
    window = bars[(bars.index >= t0) & (bars.index < t1)].copy()
    ow = opening_week_slice(bars, t0)
    atr_val = None
    if not ow.empty and ow.index[-1] in atr_series.index:
        atr_val = float(atr_series.loc[ow.index[-1]])
        if not np.isfinite(atr_val):
            atr_val = None
    if atr_val is None and not ow.empty:
        prior = atr_series.loc[: ow.index[-1]].dropna()
        if not prior.empty:
            atr_val = float(prior.iloc[-1])

    fig, ax = plt.subplots(figsize=(18, 8.5))
    shade_weeks(ax, t0, t1)
    plot_candles(ax, window)
    hi, lo, mid = draw_opening_week_range(ax, ow, t0, t1, fmt=fmt)
    extras: List[float] = []
    if mid is not None and atr_val is not None and atr_val > 0:
        extras.extend(draw_atr_bands(ax, mid, atr_val, t0, t1, fmt=fmt))
    extras.extend(draw_month_closes(ax, window, t0, t1, fmt=fmt))
    if hi is not None:
        extras.extend([hi, lo])

    labeled_roles = set()
    for tr in trades:
        entry_ts = tr["entry_ts"]
        exit_ts = min(tr["exit_ts"], t1 - pd.Timedelta(minutes=1))
        entry_px = float(tr["entry_price"])
        levels = _planned_levels(orders, tr["trade_id"])
        # Span of open risk / ladder guides.
        span_left = max(entry_ts, t0)
        span_right = max(span_left, exit_ts)
        ax.hlines(
            entry_px,
            span_left,
            span_right,
            colors=ROLE_COLORS["entry"],
            linestyles="-",
            linewidth=1.6,
            alpha=0.95,
            zorder=7,
            label="entry" if "entry" not in labeled_roles else None,
        )
        labeled_roles.add("entry")
        extras.append(entry_px)
        for role, px in levels.items():
            color = ROLE_COLORS.get(role, "#455a64")
            style = ":" if role == "stop" else "-."
            ax.hlines(
                px,
                span_left,
                span_right,
                colors=color,
                linestyles=style,
                linewidth=1.35,
                alpha=0.95,
                zorder=7,
                label=role if role not in labeled_roles else None,
            )
            labeled_roles.add(role)
            extras.append(px)
            ax.text(
                span_right,
                px,
                (" %s " % role) + (fmt % px),
                color=color,
                fontsize=7.5,
                va="center",
                ha="left",
                zorder=8,
                bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.7, "pad": 0.8},
            )

        marker = "^" if tr["direction"] == "Long" else "v"
        ax.scatter(
            [entry_ts],
            [entry_px],
            marker=marker,
            s=140,
            color=ROLE_COLORS["entry"],
            edgecolors="white",
            linewidths=0.8,
            zorder=10,
        )
        for _, fill in tr["fills"].iterrows():
            reason = str(fill["reason"])
            if reason == "entry":
                continue
            color = ROLE_COLORS.get(reason, "#455a64")
            ax.scatter(
                [fill["ts_ny"]],
                [float(fill["price"])],
                marker="o" if reason.startswith("tp") else "x",
                s=90 if reason.startswith("tp") else 110,
                color=color,
                linewidths=1.6,
                zorder=11,
                label=reason if reason not in labeled_roles else None,
            )
            labeled_roles.add(reason)
            extras.append(float(fill["price"]))

    if not window.empty:
        y_lo = float(window["low"].min())
        y_hi = float(window["high"].max())
        for v in extras:
            if v is None or not np.isfinite(v):
                continue
            y_lo = min(y_lo, float(v))
            y_hi = max(y_hi, float(v))
        pad = max((y_hi - y_lo) * 0.04, 1e-4)
        ax.set_ylim(y_lo - pad, y_hi + pad)

    ax.set_xlim(t0, t1)
    atr_txt = (("ATR(14)=" + fmt) % atr_val) if atr_val is not None else "ATR n/a"
    trade_ids = ",".join(t["trade_id"].split("_")[-1] for t in trades)
    ax.set_title(
        "%s 4h · %d Q%d · path=%s · trades=%s · %s"
        % (symbol.upper(), year, quarter, path_id, trade_ids, atr_txt)
    )
    ax.set_ylabel(symbol.upper())
    ax.grid(True, color="#dedede", linewidth=0.55, alpha=0.75)
    ax.legend(loc="upper left", fontsize=8, ncol=3)
    ax.xaxis.set_major_locator(mdates.WeekdayLocator(byweekday=mdates.MO, tz=NY))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d", tz=NY))
    ax.set_xlabel("America/New_York")
    fig.autofmt_xdate()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=130, bbox_inches="tight")
    plt.close(fig)
    return {
        "year": year,
        "quarter": quarter,
        "trades": len(trades),
        "chart": out_path.name,
    }


def chart_path(
    *,
    market: str,
    path_id: str,
    output_root: Path,
    force: bool,
    fills_hub: str = "best_path",
    trade_id_allow: Optional[Sequence[str]] = None,
    folder_name: Optional[str] = None,
    title_tag: Optional[str] = None,
) -> List[dict]:
    market = market.upper()
    if market not in MARKETS:
        raise SystemExit("Unknown market %s" % market)
    spec = MARKETS[market]
    state_root = _ladder_state_root(market, path_id, fills_hub=fills_hub)
    fills_path = state_root / "fills.csv"
    orders_path = state_root / "orders.csv"
    if not fills_path.exists():
        raise FileNotFoundError(
            "Missing ladder fills for %s %s at %s — run ladder broker first" % (market, path_id, fills_path)
        )
    fills = pd.read_csv(fills_path)
    orders = pd.read_csv(orders_path) if orders_path.exists() else pd.DataFrame()
    trades = _trade_windows(fills)
    if trade_id_allow is not None:
        allow = {str(x) for x in trade_id_allow}
        trades = [t for t in trades if str(t["trade_id"]) in allow]
    if not trades:
        _progress(output_root, "  %s %s: no trades" % (market, path_id))
        return []

    path_root = output_root / (folder_name or ("%s_%s" % (slug(market), path_id)))
    charts_root = path_root / "charts"
    if force and path_root.exists():
        import shutil

        shutil.rmtree(path_root)
    charts_root.mkdir(parents=True, exist_ok=True)

    bars = load_4h(spec.csv, market)
    atr_series = wilder_atr(bars, ATR_LEN)
    windows = {(y, q): (t0, t1) for y, q, t0, t1 in quarter_windows(bars, None, None)}

    by_q: Dict[Tuple[int, int], List[dict]] = {}
    for tr in trades:
        by_q.setdefault((tr["year"], tr["quarter"]), []).append(tr)

    display_path = title_tag or path_id
    rows: List[dict] = []
    for (year, quarter), q_trades in sorted(by_q.items()):
        key = (year, quarter)
        if key not in windows:
            # Entry near quarter boundary — snap to containing window.
            ts = q_trades[0]["entry_ts"]
            hit = None
            for (y, q), (t0, t1) in windows.items():
                if t0 <= ts < t1:
                    hit = (y, q, t0, t1)
                    break
            if hit is None:
                continue
            year, quarter, t0, t1 = hit
        else:
            t0, t1 = windows[key]
        rel = Path("charts") / ("%s_4h_%d_Q%d_trades.png" % (slug(market), year, quarter))
        out_path = path_root / rel
        _progress(
            output_root,
            "  chart %s %s %d Q%d (%d trades)" % (market, display_path, year, quarter, len(q_trades)),
        )
        meta = plot_trade_quarter(
            bars=bars,
            atr_series=atr_series,
            year=year,
            quarter=quarter,
            t0=t0,
            t1=t1,
            out_path=out_path,
            symbol=market,
            path_id=display_path,
            trades=q_trades,
            orders=orders,
        )
        meta.update(
            {
                "market": market,
                "path_id": path_id,
                "chart": str(rel),
                "trade_ids": ";".join(t["trade_id"] for t in q_trades),
            }
        )
        rows.append(meta)

    pd.DataFrame(rows).to_csv(path_root / "chart_manifest.csv", index=False)
    lines = [
        "# %s · %s — trade ladder charts" % (market, display_path),
        "",
        "State: `%s`" % state_root,
        "Quarters with trades: **%d**" % len(rows),
        "",
        "| Year | Q | Trades | Chart |",
        "|---:|---:|---:|---|",
    ]
    for r in rows:
        lines.append(
            "| %d | %d | %d | [%s](%s) |"
            % (r["year"], r["quarter"], r["trades"], Path(str(r["chart"])).name, r["chart"])
        )
    (path_root / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return rows


def build_ha_winners(
    *,
    output_root: Path,
    force: bool,
    email: bool,
) -> List[dict]:
    """Chart HA HP subsets that look competitive vs top3 WR paths."""
    from .intraday_condition_overlay import hp_mask

    ha_root = output_root / "ha_winners"
    ha_root.mkdir(parents=True, exist_ok=True)
    camp_path = HA_HUB / "profile" / "all_campaigns.csv"
    if not camp_path.exists():
        raise SystemExit("Missing HA campaigns at %s — run quarterly_atr4_ha_conditions first" % camp_path)
    campaigns = pd.read_csv(camp_path)
    all_rows: List[dict] = []
    index_rows: List[dict] = []

    try:
        for win in HA_WINNERS:
            book = str(win["book"])
            cond = str(win["condition"])
            bucket = str(win["bucket"])
            sub = campaigns[campaigns["book"] == book].copy()
            mask = hp_mask(sub, cond, bucket)
            hp = sub.loc[mask]
            trade_ids = [str(x) for x in hp["trade_id"].tolist()]
            n = len(trade_ids)
            wr = float((hp["net_usd"] > 0).mean()) if n else 0.0
            net = float(hp["net_usd"].sum()) if n else 0.0
            _progress(
                output_root,
                "HA %s | %s=%s n=%d WR=%.0f%% net=$%.0f"
                % (win["slug"], cond, bucket, n, 100.0 * wr, net),
            )
            folder = str(win["slug"])
            rows = chart_path(
                market=str(win["market"]),
                path_id=str(win["path_id"]),
                output_root=ha_root,
                force=force,
                fills_hub=str(win.get("fills_hub") or "best_path"),
                trade_id_allow=trade_ids,
                folder_name=folder,
                title_tag="HA:%s=%s" % (cond, bucket),
            )
            # Per-winner INDEX preface
            pref = ha_root / folder / "WHY.md"
            pref.write_text(
                "# %s\n\n%s\n\n- book: `%s`\n- condition: **%s = %s**\n- HP trades: **%d**\n- HP WR: **%.1f%%**\n- HP net: **$%s**\n"
                % (
                    win["slug"],
                    win["why"],
                    book,
                    cond,
                    bucket,
                    n,
                    100.0 * wr,
                    f"{net:,.0f}",
                ),
                encoding="utf-8",
            )
            for r in rows:
                r["ha_slug"] = folder
                r["condition"] = cond
                r["bucket"] = bucket
            all_rows.extend(rows)
            index_rows.append(
                {
                    "slug": folder,
                    "market": win["market"],
                    "path_id": win["path_id"],
                    "condition": cond,
                    "bucket": bucket,
                    "n": n,
                    "wr": wr,
                    "net": net,
                    "charts": len(rows),
                    "why": win["why"],
                }
            )

        pd.DataFrame(index_rows).to_csv(ha_root / "summary.csv", index=False)
        lines = [
            "# HA winners — competitive vs top3 trade charts",
            "",
            "HP condition subsets from `quarterly_atr4_ha_conditions` that clear or approach",
            "the top3 WR bar (GBPUSD first_lower ~58.5%, US30 paths 60–73%) with n≥6,",
            "live_ready features, and material size/filter lift on the be8 ladder tape.",
            "",
            "Nulls did **not** validate 1.25× size-up — charts are for inspection only.",
            "",
            "| Slug | Market | Path | Condition | n | WR | HP net | Charts | Why |",
            "|---|---|---|---|---:|---:|---:|---:|---|",
        ]
        for r in index_rows:
            lines.append(
                "| [%s](%s/) | %s | %s | %s=%s | %d | %.0f%% | $%s | %d | %s |"
                % (
                    r["slug"],
                    r["slug"],
                    r["market"],
                    r["path_id"],
                    r["condition"],
                    r["bucket"],
                    int(r["n"]),
                    100.0 * float(r["wr"]),
                    f"{float(r['net']):,.0f}",
                    int(r["charts"]),
                    r["why"],
                )
            )
        lines.extend(["", "Parent: `%s`" % output_root, "HA hub: `%s`" % HA_HUB, ""])
        (ha_root / "INDEX.md").write_text("\n".join(lines), encoding="utf-8")

        # Patch parent INDEX.md with HA section if present
        parent_index = output_root / "INDEX.md"
        if parent_index.exists():
            text = parent_index.read_text(encoding="utf-8")
            marker = "## HA winners"
            block = (
                "## HA winners\n\n"
                "Competitive HP subsets vs top3 WR bar — see [%s](%s/).\n"
                % ("ha_winners/INDEX.md", "ha_winners")
            )
            if marker in text:
                # replace from marker to end-of-section or append overwrite
                pre = text.split(marker)[0].rstrip() + "\n\n"
                text = pre + block + "\n"
            else:
                text = text.rstrip() + "\n\n" + block + "\n"
            parent_index.write_text(text, encoding="utf-8")

        email_body = "\n".join(
            [
                "potions: quarterly ATR4 HA winners charts complete",
                "",
                "Hub: %s" % ha_root,
                "Winners: %d  Charts: %d" % (len(index_rows), len(all_rows)),
                "",
                (ha_root / "INDEX.md").read_text(encoding="utf-8"),
            ]
        )
        (ha_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        (ha_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "winners": len(index_rows), "charts": len(all_rows)}, indent=2)
            + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH HA winners\n%s" % err)
        (ha_root / "EMAIL.txt").write_text(
            "potions: HA winners charts FAILED\n\nHub: %s\n\n%s\n" % (ha_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: HA winners charts FAILED",
                body=(ha_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise
    if email:
        send_email(
            subject="potions: quarterly ATR4 HA winners charts complete",
            body=(ha_root / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress(output_root, "HA winners email sent")
    return all_rows


def build(
    *,
    paths_csv: Path,
    output_root: Path,
    force: bool,
    email: bool,
) -> List[dict]:
    output_root.mkdir(parents=True, exist_ok=True)
    df = pd.read_csv(paths_csv)
    all_rows: List[dict] = []
    try:
        for _, row in df.iterrows():
            market = str(row["market"]).upper()
            path_id = str(row["path_id"])
            _progress(
                output_root,
                "PATH %s %s WR=%.1f%% n=%s risk=%s×ATR"
                % (
                    market,
                    path_id,
                    100.0 * float(row.get("win_rate") or 0.0),
                    row.get("n"),
                    row.get("risk_atr_mult"),
                ),
            )
            all_rows.extend(
                chart_path(market=market, path_id=path_id, output_root=output_root, force=force)
            )
        summary = (
            df.assign(charts=0)
            if all_rows == []
            else df.merge(
                pd.DataFrame(all_rows)
                .groupby(["market", "path_id"], as_index=False)
                .size()
                .rename(columns={"size": "charts"}),
                on=["market", "path_id"],
                how="left",
            )
        )
        summary.to_csv(output_root / "summary.csv", index=False)
        index_lines = [
            "# Top-3 WR path trade charts",
            "",
            "Same quarterly 4h canvas as the ATR4 study, with **entry / stop / TP ladder** overlays and fill markers for every broker ladder trade.",
            "",
            "| Market | Path | WR | N | Risk | Charts | Hub |",
            "|---|---|---:|---:|---:|---:|---|",
        ]
        for _, row in summary.iterrows():
            hub = "%s_%s" % (slug(str(row["market"])), row["path_id"])
            index_lines.append(
                "| %s | %s | %.1f%% | %s | %s× | %s | [%s](%s/) |"
                % (
                    row["market"],
                    row["path_id"],
                    100.0 * float(row["win_rate"]),
                    row["n"],
                    row["risk_atr_mult"],
                    int(row.get("charts") or 0),
                    hub,
                    hub,
                )
            )
        index_lines.extend(["", "Hub: `%s`" % output_root])
        (output_root / "INDEX.md").write_text("\n".join(index_lines) + "\n", encoding="utf-8")
        email_body = "\n".join(
            [
                "potions: top-3 WR quarterly fade ladder trade charts complete",
                "",
                "Hub: %s" % output_root,
                "Charts: %d" % len(all_rows),
                "",
                (output_root / "INDEX.md").read_text(encoding="utf-8"),
            ]
        )
        (output_root / "EMAIL.txt").write_text(email_body, encoding="utf-8")
        (output_root / "RUN_COMPLETE.json").write_text(
            json.dumps({"ok": True, "charts": len(all_rows)}, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        err = traceback.format_exc()
        _progress(output_root, "CRASH\n%s" % err)
        (output_root / "EMAIL.txt").write_text(
            "potions: top-3 WR trade charts FAILED\n\nHub: %s\n\n%s\n" % (output_root, err),
            encoding="utf-8",
        )
        if email:
            send_email(
                subject="potions: top-3 WR trade charts FAILED",
                body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
            )
        raise
    if email:
        send_email(
            subject="potions: top-3 WR quarterly fade ladder trade charts complete",
            body=(output_root / "EMAIL.txt").read_text(encoding="utf-8"),
        )
        _progress(output_root, "email sent")
    return all_rows


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--paths-csv", type=Path, default=DEFAULT_TOP3)
    ap.add_argument("--output-root", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--email", action="store_true")
    ap.add_argument(
        "--ha-winners",
        action="store_true",
        help="Chart competitive HA HP subsets into <output-root>/ha_winners/",
    )
    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.ha_winners:
        rows = build_ha_winners(output_root=args.output_root, force=args.force, email=args.email)
        print("Wrote %d HA-winner charts -> %s/ha_winners" % (len(rows), args.output_root), flush=True)
        return 0
    rows = build(
        paths_csv=args.paths_csv,
        output_root=args.output_root,
        force=args.force,
        email=args.email,
    )
    print("Wrote %d charts -> %s" % (len(rows), args.output_root), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
