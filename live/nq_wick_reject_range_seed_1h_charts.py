"""1h / 2-week visual audit charts for frozen primary_limit_retest fills.

Population: only FILLED campaigns from
`live/state/nq_wick_reject_range_seed_retest/trades_primary.csv` (67 fills:
53 development + 14 holdout). Overlays come from frozen campaign/event rows —
not reconstructed from chart inspection.

Window: entry fill_ts −7d / +7d calendar on NQ 1h candles.
Subsets: ALL fills, holdout, balanced-review (stratified W/L × L/S from filled).

Hub: live/state/nq_wick_reject_range_seed_1h_charts/

Usage:
  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.nq_wick_reject_range_seed_1h_charts --email
  python -m live.nq_wick_reject_range_seed_1h_charts --smoke --email
"""

from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .gbpusd_quarterly_4h_charts import shade_weeks
from .notify_email import send_email
from .run_ledger import begin_run, complete_run, fail_run

REPO = Path(__file__).resolve().parents[1]
STUDY_HUB = REPO / "live" / "state" / "nq_wick_reject_range_seed_retest"
HUB = REPO / "live" / "state" / "nq_wick_reject_range_seed_1h_charts"
BARS_1H = REPO / "live" / "state" / "_cache" / "bars" / "nq_1h.parquet"
NY = "America/New_York"
PRE_DAYS = 7
POST_DAYS = 7
PNG_BATCH_BYTES = 35 * 1024 * 1024
PNG_MAX_PER_EMAIL = 200
BALANCED_PER_CELL = 3  # wins×losses × long×short → up to 12 balanced-review charts


def _localize(ts: pd.Timestamp) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def _progress(hub: Path, msg: str) -> None:
    line = "[%s] %s" % (datetime.now().strftime("%H:%M:%S"), msg)
    print(line, flush=True)
    with (hub / "PROGRESS.log").open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_1h() -> pd.DataFrame:
    df = pd.read_parquet(BARS_1H)
    ts = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    if ts.isna().any():
        ts = pd.to_datetime(df["ts"], errors="coerce")
        if getattr(ts.dt, "tz", None) is None:
            ts = ts.dt.tz_localize(NY, ambiguous="infer", nonexistent="shift_forward")
        else:
            ts = ts.dt.tz_convert(NY)
    else:
        ts = ts.dt.tz_convert(NY)
    out = df.assign(ts=ts).dropna(subset=["ts"]).set_index("ts").sort_index()
    return out[["open", "high", "low", "close"] + (["volume"] if "volume" in out.columns else [])]


def _plot_candles_1h(ax, df: pd.DataFrame) -> None:
    if df.empty:
        return
    width_days = (1.0 / 24.0) * 0.62
    x = mdates.date2num(df.index.to_pydatetime())
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    colors = np.where(closes >= opens, "#168a5a", "#c43d3d")
    price_span = float(np.nanmax(highs) - np.nanmin(lows)) if len(highs) else 0.0
    min_body = max(price_span * 0.001, 1e-6)
    ax.vlines(x, lows, highs, color=colors, linewidth=0.65, alpha=0.9, zorder=3)
    for xi, o, c, color in zip(x, opens, closes, colors):
        bottom = min(o, c)
        height = max(abs(c - o), min_body)
        ax.add_patch(
            plt.Rectangle(
                (xi - width_days / 2.0, bottom),
                width_days,
                height,
                facecolor=color,
                edgecolor=color,
                linewidth=0.2,
                alpha=0.88,
                zorder=4,
            )
        )


def _xi_time(bars: pd.DataFrame, ts: pd.Timestamp) -> Optional[pd.Timestamp]:
    if bars is None or bars.empty or pd.isna(ts):
        return None
    ts = _localize(ts)
    pos = bars.index.searchsorted(ts, side="left")
    if pos >= len(bars):
        pos = len(bars) - 1
    best = bars.index[pos]
    best_dt = abs((best - ts).total_seconds())
    if pos > 0:
        t0 = bars.index[pos - 1]
        dt0 = abs((t0 - ts).total_seconds())
        if dt0 < best_dt:
            best, best_dt = t0, dt0
    if best_dt > 3 * 3600:
        return None
    return best


def _vline(ax, bars: pd.DataFrame, ts, color: str, label: str, ls: str = "--") -> None:
    if ts is None or (isinstance(ts, float) and np.isnan(ts)) or str(ts) == "" or pd.isna(ts):
        return
    x = _xi_time(bars, _localize(pd.Timestamp(ts)))
    if x is None:
        return
    ax.axvline(mdates.date2num(x.to_pydatetime()), color=color, lw=1.1, ls=ls, alpha=0.85, label=label)


def causal_ok(row: pd.Series) -> Tuple[int, str]:
    """Assert seed(available_at) < break < limit_live <= fill from frozen timestamps."""
    try:
        seed = _localize(pd.Timestamp(row["available_at"]))
        brk = _localize(pd.Timestamp(row["break_confirm_ts"]))
        live = _localize(pd.Timestamp(row["order_live_at"]))
        fill = _localize(pd.Timestamp(row["fill_ts"]))
    except Exception:  # noqa: BLE001
        return 0, "parse_fail"
    if not (seed < brk < live <= fill):
        return 0, "seed < break < limit_live <= fill FAILED (%s < %s < %s <= %s)" % (
            seed,
            brk,
            live,
            fill,
        )
    return 1, "seed < break < limit_live <= fill OK"


def chart_one(row: pd.Series, bars: pd.DataFrame, out_path: Path) -> Tuple[bool, int, int, str]:
    fill_ts = _localize(pd.Timestamp(row["fill_ts"]))
    confirm_open = _localize(pd.Timestamp(row["confirm_bar_open_ts"]))
    confirm_close = _localize(pd.Timestamp(row["confirm_bar_close_ts"]))
    t0 = fill_ts - pd.Timedelta(days=PRE_DAYS)
    t1 = fill_ts + pd.Timedelta(days=POST_DAYS)
    plot = bars[(bars.index >= t0) & (bars.index <= t1)]
    if len(plot) < 12:
        plot = bars[
            (bars.index >= fill_ts - pd.Timedelta(days=PRE_DAYS + 2))
            & (bars.index <= fill_ts + pd.Timedelta(days=POST_DAYS + 2))
        ]
    if len(plot) < 12:
        return False, 0, 0, "too_few_bars"

    rh = float(row["range_high"])
    rl = float(row["range_low"])
    mid = 0.5 * (rh + rl)
    side = str(row.get("side") or "")
    outcome = str(row.get("outcome") or "")
    net = float(row["net_usd"]) if pd.notna(row.get("net_usd")) else 0.0
    r_mult = float(row["r_multiple"]) if pd.notna(row.get("r_multiple")) else 0.0
    cok, cmsg = causal_ok(row)

    fig, ax = plt.subplots(figsize=(14, 7))
    shade_weeks(ax, plot.index[0], plot.index[-1] + pd.Timedelta(hours=1))
    _plot_candles_1h(ax, plot)

    ax.axhline(rh, color="#1565c0", lw=1.5, ls="--", label="seed high %.2f" % rh)
    ax.axhline(rl, color="#1565c0", lw=1.5, ls=":", label="seed low %.2f" % rl)
    ax.axhline(mid, color="#90caf9", lw=1.0, ls="-.", label="seed mid %.2f" % mid)

    xo = _xi_time(plot, confirm_open)
    xc = _xi_time(plot, confirm_close)
    if xo is not None and xc is not None:
        left = mdates.date2num(xo.to_pydatetime()) - (0.5 / 24.0)
        right = mdates.date2num(xc.to_pydatetime()) + (0.5 / 24.0)
        ax.axvspan(left, right, color="#fff59d", alpha=0.4, label="confirm 4h", zorder=1)

    _vline(ax, plot, row.get("available_at"), "#455a64", "seed available", ls=":")
    _vline(ax, plot, row.get("break_confirm_ts"), "#6a1b9a", "1h break", ls="-")
    _vline(ax, plot, row.get("order_live_at"), "#5e35b1", "limit live", ls=":")
    _vline(ax, plot, row.get("fill_ts"), "#00838f", "fill", ls="--")
    _vline(ax, plot, row.get("exit_ts"), "#b71c1c", "exit", ls="--")

    if outcome == "FILLED" and pd.notna(row.get("entry")):
        entry = float(row["entry"])
        ax.axhline(entry, color="#6a1b9a", lw=1.2, ls="-.", label="limit entry %.2f" % entry)
        if pd.notna(row.get("stop")):
            ax.axhline(float(row["stop"]), color="#ef6c00", lw=1.1, ls="-.", label="stop %.2f" % float(row["stop"]))
        for k, col in (("tp1", "#2e7d32"), ("tp2", "#43a047"), ("tp3", "#66bb6a")):
            if pd.notna(row.get(k)):
                ax.axhline(float(row[k]), color=col, lw=0.9, ls=":", alpha=0.85, label="%s %.2f" % (k, float(row[k])))

    trade_note = " | %s %s R=%.2f net=$%.0f | causal=%s | %s" % (
        side or "—",
        outcome,
        r_mult,
        net,
        "OK" if cok else "FAIL",
        str(row.get("terminal_reason") or row.get("exit_reason") or "")[:40],
    )
    title = (
        "NQ 1h | limit-retest FILL | %s | slice=%s | entry %s\n"
        "window entry−%dd/+%dd %s → %s (%d bars)%s"
        % (
            row["event_id"],
            row.get("slice", ""),
            fill_ts.strftime("%Y-%m-%d %H:%M"),
            PRE_DAYS,
            POST_DAYS,
            plot.index[0].strftime("%Y-%m-%d %H:%M"),
            plot.index[-1].strftime("%Y-%m-%d %H:%M"),
            len(plot),
            trade_note,
        )
    )
    ax.set_title(title, fontsize=9)
    ax.legend(loc="best", fontsize=7, ncol=2)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M", tz=plot.index.tz))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=6, maxticks=12))
    fig.autofmt_xdate(rotation=30, ha="right")
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True, len(plot), cok, cmsg


def _pack_batches(paths: Sequence[Path]) -> List[List[Path]]:
    batches: List[List[Path]] = []
    cur: List[Path] = []
    cur_bytes = 0
    for p in paths:
        if not p.exists():
            continue
        sz = p.stat().st_size
        if cur and (len(cur) >= PNG_MAX_PER_EMAIL or cur_bytes + sz > PNG_BATCH_BYTES):
            batches.append(cur)
            cur, cur_bytes = [], 0
        cur.append(p)
        cur_bytes += sz
    if cur:
        batches.append(cur)
    return batches


def select_balanced(book: pd.DataFrame, per_cell: int = BALANCED_PER_CELL) -> pd.DataFrame:
    """Stratified sample: win/loss × long/short from filled (prefer holdout then early/late mix)."""
    picks = []
    for side in ("LONG", "SHORT"):
        for win in (True, False):
            sub = book[(book["side"] == side) & ((book["net_usd"] > 0) == win)].copy()
            if sub.empty:
                continue
            # preference: holdout first, then by |R| extremity for audit interest
            sub["_hold"] = (sub["slice"] == "holdout").astype(int)
            sub["_absR"] = sub["r_multiple"].astype(float).abs()
            sub = sub.sort_values(["_hold", "_absR"], ascending=[False, False])
            picks.append(sub.head(per_cell))
    if not picks:
        return book.head(0)
    out = pd.concat(picks, ignore_index=True).drop_duplicates(subset=["event_id"])
    return out.sort_values("fill_ts").reset_index(drop=True)


def write_index(hub: Path, meta: pd.DataFrame, title: str, fname: str) -> None:
    lines = [
        "# %s" % title,
        "",
        "Source: frozen `trades_primary.csv` FILLED rows only (not chart reconstruction).",
        "Each chart: NQ **1h** candles entry −%dd / +%dd (~2 weeks),"
        % (PRE_DAYS, POST_DAYS),
        "seed high/low/mid, confirm 4h, break / limit-live / fill / exit, stop + TPs.",
        "Causal assert: `seed_available < break < limit_live <= fill`.",
        "",
        "Charts: **%d** (ok=%d) causal_ok=%d"
        % (len(meta), int(meta["ok"].sum()) if len(meta) else 0, int(meta["causal_ok"].sum()) if len(meta) else 0),
        "",
        "| # | file | event_id | slice | subset | side | net $ | R | bars | causal |",
        "|---:|---|---|---|---|---|---:|---:|---:|---|",
    ]
    for i, r in meta.iterrows():
        lines.append(
            "| %d | `%s` | `%s` | %s | %s | %s | %s | %s | %s | %s |"
            % (
                i + 1,
                r.get("chart_file", ""),
                r.get("event_id", ""),
                r.get("slice", ""),
                r.get("subset", ""),
                r.get("side", ""),
                r.get("net_usd", ""),
                r.get("r_multiple", ""),
                r.get("n_bars", ""),
                r.get("causal_ok", ""),
            )
        )
    (hub / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_chart_spec(hub: Path, n_all: int, n_ho: int, n_bal: int) -> None:
    text = """# CHART_SPEC — NQ limit-retest 1h / 2-week visual audit pack

**study_source:** `live/state/nq_wick_reject_range_seed_retest/`
**population:** all **67** `primary_limit_retest` **FILLED** campaigns (frozen tape)
- development fills: 53
- holdout fills: 14

## Geometry
- timeframe: **1-hour** RTH candles
- window: **7 calendar days before → 7 calendar days after** each **entry fill_ts**
- overlays from frozen campaign/event records only:
  - seeded 4h WICK_REJECT range **high / low / midpoint**
  - yellow confirm 4h span
  - seed `available_at`
  - 1h break confirmation
  - retest-limit activation (`order_live_at`) and actual fill
  - opposite-range stop
  - TP1/TP2/runner (0.5W / 1W / 2W) and exit annotation

## Causal timestamp assertions
Required ordering on every chart / manifest row:
`seed_available_at < break_confirm_ts < order_live_at <= fill_ts`

## Subsets
| subset | n | path prefix |
|---|---:|---|
| all_filled | %d | `charts/all/` |
| holdout | %d | `charts/holdout/` |
| balanced_review | %d | `charts/balanced_review/` |

Balanced-review = stratified sample up to %d per (side × win/loss) cell, holdout preferred then extreme |R|.

## Artifacts
- `CHART_SPEC.md` (this file)
- `INDEX.md` / `INDEX_holdout.md` / `INDEX_balanced_review.md`
- `chart_manifest.csv`
""" % (
        n_all,
        n_ho,
        n_bal,
        BALANCED_PER_CELL,
    )
    (hub / "CHART_SPEC.md").write_text(text, encoding="utf-8")


def load_book(smoke: bool = False) -> pd.DataFrame:
    census = pd.read_csv(STUDY_HUB / "phase0_census.csv")
    trades = pd.read_csv(STUDY_HUB / "trades_primary.csv")
    filled = trades[trades["outcome"] == "FILLED"].copy()
    elig = census[census["eligible"] == 1][
        ["event_id", "confirm_bar_open_ts", "confirm_bar_close_ts", "atr20_4h"]
    ]
    merged = filled.merge(elig, on="event_id", how="left")
    merged = merged.sort_values("fill_ts").reset_index(drop=True)
    if smoke:
        merged = merged.head(8)
    return merged


def _chart_batch(
    hub: Path,
    book: pd.DataFrame,
    bars: pd.DataFrame,
    charts_dir: Path,
    subset: str,
    start_i: int = 1,
) -> pd.DataFrame:
    rows = []
    for i, (_, row) in enumerate(book.iterrows(), start=start_i):
        eid = str(row["event_id"])
        fname = "%03d_%s_limit_retest_1h_%s.png" % (i, subset[:3], eid[:48])
        ok, n_bars, cok, cmsg = chart_one(row, bars, charts_dir / fname)
        rows.append(
            {
                "chart_file": fname if ok else "",
                "ok": int(ok),
                "event_id": eid,
                "slice": row.get("slice", ""),
                "subset": subset,
                "side": row.get("side", ""),
                "outcome": row.get("outcome", ""),
                "net_usd": ("%.0f" % float(row["net_usd"])) if pd.notna(row.get("net_usd")) else "",
                "r_multiple": ("%.2f" % float(row["r_multiple"])) if pd.notna(row.get("r_multiple")) else "",
                "n_bars": n_bars,
                "causal_ok": cok,
                "causal_msg": cmsg,
                "fill_ts": row["fill_ts"],
                "confirm_bar_close_ts": row.get("confirm_bar_close_ts", ""),
            }
        )
        if i % 10 == 0 or i == start_i + len(book) - 1:
            _progress(hub, "chart %s %d/%d ok=%s causal=%s" % (subset, i - start_i + 1, len(book), ok, cok))
    return pd.DataFrame(rows)


def run(*, smoke: bool = False, email: bool = False) -> Path:
    hub = HUB
    hub.mkdir(parents=True, exist_ok=True)
    for sub in ("all", "holdout", "balanced_review"):
        d = hub / "charts" / sub
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.png"):
            old.unlink()
    # clear legacy flat charts/
    legacy = hub / "charts"
    for old in legacy.glob("*.png"):
        old.unlink()
    (hub / "PROGRESS.log").write_text("", encoding="utf-8")

    rid = begin_run(
        run_class="other",
        variant_slug="nq_wick_reject_range_seed_1h_charts",
        instrument="NQ",
        hub_path=str(hub.relative_to(REPO)),
        meta={"pre_days": PRE_DAYS, "post_days": POST_DAYS, "smoke": smoke, "fills_only": True},
    )
    try:
        if email:
            start = (
                "potions: NQ limit-retest 1h charts (67 fills) STARTED\n\n"
                "Hub: %s\nSource: %s FILLED only\nWindow: entry −%dd / +%dd 1h.\n"
                % (hub, STUDY_HUB, PRE_DAYS, POST_DAYS)
            )
            (hub / "EMAIL_START.txt").write_text(start, encoding="utf-8")
            try:
                send_email(subject="potions: NQ limit-retest 1h charts STARTED", body=start)
            except Exception as exc:  # noqa: BLE001
                _progress(hub, "start email failed: %s" % exc)

        _progress(hub, "load FILLED book + 1h bars")
        book = load_book(smoke=smoke)
        bars = load_1h()
        _progress(hub, "fills=%d 1h_bars=%d" % (len(book), len(bars)))

        meta_all = _chart_batch(hub, book, bars, hub / "charts" / "all", "all_filled")
        hold = book[book["slice"] == "holdout"].copy()
        meta_ho = _chart_batch(hub, hold, bars, hub / "charts" / "holdout", "holdout", start_i=1)
        bal = select_balanced(book)
        meta_bal = _chart_batch(
            hub, bal, bars, hub / "charts" / "balanced_review", "balanced_review", start_i=1
        )

        meta = pd.concat([meta_all, meta_ho, meta_bal], ignore_index=True)
        meta.to_csv(hub / "chart_manifest.csv", index=False)
        write_index(hub, meta_all, "NQ 1h limit-retest charts — ALL fills", "INDEX.md")
        write_index(hub, meta_ho, "NQ 1h limit-retest charts — holdout fills", "INDEX_holdout.md")
        write_index(
            hub, meta_bal, "NQ 1h limit-retest charts — balanced review", "INDEX_balanced_review.md"
        )
        write_chart_spec(hub, len(meta_all), len(meta_ho), len(meta_bal))

        pngs = sorted((hub / "charts").rglob("*.png"))
        total_bytes = sum(p.stat().st_size for p in pngs)
        n_causal_fail = int((meta_all["causal_ok"] == 0).sum()) if len(meta_all) else 0
        body_lines = [
            "potions: NQ limit-retest 1h charts COMPLETE (fills-only pack)",
            "",
            "Hub: %s" % hub,
            "Source: %s FILLED primary_limit_retest" % STUDY_HUB,
            "ALL fills: %d (ok=%d) causal_fail=%d" % (len(meta_all), int(meta_all["ok"].sum()), n_causal_fail),
            "Holdout: %d | Balanced-review: %d" % (len(meta_ho), len(meta_bal)),
            "PNG total: %d (%.1f MB)" % (len(pngs), total_bytes / (1024 * 1024)),
            "Window: entry −%dd / +%dd 1h candles." % (PRE_DAYS, POST_DAYS),
            "",
            "See CHART_SPEC.md + INDEX*.md + chart_manifest.csv.",
        ]
        body = "\n".join(body_lines) + "\n"
        (hub / "EMAIL.txt").write_text(body, encoding="utf-8")
        (hub / "STATUS.md").write_text(
            "# Status — NQ limit-retest 1h charts\n\n"
            "Fills: %d | Holdout: %d | Balanced: %d | PNGs: %d\n"
            % (len(meta_all), len(meta_ho), len(meta_bal), len(pngs)),
            encoding="utf-8",
        )
        (hub / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "ok": True,
                    "n_all": len(meta_all),
                    "n_holdout": len(meta_ho),
                    "n_balanced": len(meta_bal),
                    "n_ok": int(meta["ok"].sum()),
                    "n_png": len(pngs),
                    "causal_fail_all": n_causal_fail,
                    "finished_at": datetime.now().isoformat(timespec="seconds"),
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        if email and pngs:
            # Prefer emailing all_filled + holdout; balanced is subset of all
            prefer = sorted((hub / "charts" / "all").glob("*.png")) + sorted(
                (hub / "charts" / "holdout").glob("*.png")
            )
            # de-dupe by name stem preference already separate dirs
            batches = _pack_batches(prefer)
            for bi, batch in enumerate(batches, start=1):
                batch_mb = sum(p.stat().st_size for p in batch) / (1024 * 1024)
                subj = "potions: NQ limit-retest 1h charts 2w fills (%d/%d, batch %d/%d)" % (
                    len(batch),
                    len(prefer),
                    bi,
                    len(batches),
                )
                b = body + "\nAttached %d PNGs (%.1f MB) batch %d/%d:\n" % (
                    len(batch),
                    batch_mb,
                    bi,
                    len(batches),
                )
                b += "\n".join("  %s" % p.name for p in batch)
                b += "\n\nFull hub: %s\n" % hub
                (hub / ("EMAIL_BATCH_%02d.txt" % bi)).write_text(b, encoding="utf-8")
                send_email(subject=subj, body=b, attachments=batch)
                _progress(hub, "emailed batch %d/%d n=%d" % (bi, len(batches), len(batch)))
        elif email:
            send_email(subject="potions: NQ limit-retest 1h charts COMPLETE (no png)", body=body)

        complete_run(rid, trades=int(meta_all["ok"].sum()), meta={"n_png": len(pngs), "fills_only": True})
        return hub
    except Exception as exc:  # noqa: BLE001
        fail_run(rid, error=str(exc))
        err = "potions: NQ limit-retest 1h charts FAILED\n\n%s\n\n%s\n" % (
            hub,
            traceback.format_exc()[-2500:],
        )
        (hub / "FAILED.txt").write_text(err, encoding="utf-8")
        if email:
            try:
                send_email(subject="potions: NQ limit-retest 1h charts FAILED", body=err)
            except Exception:  # noqa: BLE001
                pass
        raise


def main(argv: Optional[Sequence[str]] = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--email", action="store_true")
    args = ap.parse_args(list(argv) if argv is not None else None)
    run(smoke=bool(args.smoke), email=bool(args.email))


if __name__ == "__main__":
    main()
