"""Chart structure_only resting broker campaigns on 1m with OR + ST + structure.

Usage:
  python -m live.structure_program_st_chart_struct_resting --n 200
"""

from __future__ import annotations

import argparse
import random
from datetime import date, time, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .build_ym_1m_atr_supertrend_sample import compute_supertrend
from .structure_program_st_study import (
    ATR_LEN,
    ATR_MULT,
    StructureProgramEngine,
    rth_slice,
    to_15m,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE = (
    REPO
    / "live"
    / "state"
    / "structure_program_st_broker_struct_v2"
    / "states"
    / "nq_scale_run_r8_struct_resting"
)
DEFAULT_OUT = (
    REPO / "live" / "state" / "structure_program_st_broker_struct_v2" / "trade_charts"
)
RISK_PTS = 8.0
OR_END = time(9, 45)  # exclusive: 09:30–09:44
NY = "America/New_York"
POINT_VALUE = 20.0


def _to_ny(ts) -> pd.Timestamp:
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        return t.tz_localize(NY)
    return t.tz_convert(NY)


def load_campaigns(state: Path) -> pd.DataFrame:
    u = pd.read_csv(state / "unit_trades.csv")
    u["entry_ts"] = pd.to_datetime(u["entry_ts"], utc=True)
    u["exit_ts"] = pd.to_datetime(u["exit_ts"], utc=True)
    last = u.sort_values("exit_ts").groupby("trade_id", as_index=False).tail(1)
    camp = u.groupby("trade_id", as_index=False).agg(
        pnl_usd=("net_usd", "sum"),
        direction=("direction", "first"),
        entry_ts=("entry_ts", "min"),
        fill_px=("entry_price", "first"),
        units=("unit_id", "count"),
    )
    camp = camp.merge(
        last[["trade_id", "exit_ts", "exit_price", "exit_reason"]], on="trade_id"
    )
    reasons = (
        u.groupby("trade_id")["exit_reason"]
        .apply(lambda s: "+".join(sorted(set(s.astype(str)))))
        .rename("exit_reasons")
        .reset_index()
    )
    camp = camp.merge(reasons, on="trade_id")

    # filled entry order → original structure limit
    lim_map: Dict[str, float] = {}
    for ch in pd.read_csv(state / "orders.csv", chunksize=100000):
        e = ch[(ch["bracket_role"] == "entry") & (ch["status"] == "filled")]
        for tid, lim in zip(e["trade_id"], e["limit_price"]):
            if tid not in lim_map and pd.notna(lim):
                lim_map[str(tid)] = float(lim)
    camp["structure_key"] = camp["trade_id"].map(lambda t: lim_map.get(str(t)))
    camp["structure_key"] = camp["structure_key"].fillna(camp["fill_px"])
    camp["side"] = camp["direction"].str.lower()
    camp["program"] = camp["side"].map({"long": "buy", "short": "sell"})
    camp["exit"] = camp["exit_price"]
    camp["entry"] = camp["fill_px"]
    camp["stop"] = [
        float(e) - RISK_PTS if s == "long" else float(e) + RISK_PTS
        for e, s in zip(camp["structure_key"], camp["side"])
    ]
    camp["pnl_pts"] = camp["pnl_usd"] / (POINT_VALUE * 15.0)  # approx campaign pts on 15ct
    camp["result"] = np.where(camp["pnl_usd"] > 0, "win", "loss")
    camp["session_date"] = camp["entry_ts"].map(lambda t: _to_ny(t).date())
    return camp.sort_values("entry_ts").reset_index(drop=True)


def sample_campaigns(camp: pd.DataFrame, n: int, seed: int) -> pd.DataFrame:
    rng = random.Random(seed)
    wins = camp[camp["pnl_usd"] > 0]
    losses = camp[camp["pnl_usd"] <= 0]
    # Prefer balanced folders; take all winners if fewer than half.
    n_w = min(len(wins), n // 2)
    n_l = min(len(losses), n - n_w)
    # If winners short, fill with more losers (and vice versa).
    if n_w + n_l < n:
        n_l = min(len(losses), n - n_w)
    if n_w + n_l < n:
        n_w = min(len(wins), n - n_l)
    wi = wins.index.tolist()
    li = losses.index.tolist()
    # time-stratified: sort then stride, then top-up random
    def pick(idxs: List[int], k: int) -> List[int]:
        if k <= 0 or not idxs:
            return []
        if k >= len(idxs):
            return list(idxs)
        step = max(1, len(idxs) // k)
        chosen = idxs[::step][:k]
        if len(chosen) < k:
            rest = [i for i in idxs if i not in set(chosen)]
            chosen.extend(rng.sample(rest, k - len(chosen)))
        return chosen[:k]

    sel = pick(wi, n_w) + pick(li, n_l)
    out = camp.loc[sel].copy().sort_values("entry_ts").reset_index(drop=True)
    out["chart_id"] = np.arange(1, len(out) + 1)
    return out


def session_or(rth: pd.DataFrame) -> Tuple[Optional[float], Optional[float]]:
    if rth is None or rth.empty:
        return None, None
    orb = rth[rth.index.time < OR_END]
    if orb.empty:
        return None, None
    return float(orb["high"].max()), float(orb["low"].min())


def build_day_structure(
    gby: Dict[date, pd.DataFrame], through: date
) -> Dict[date, dict]:
    """Walk structure engine; snapshot keys at end of each day ≤ through."""
    engine = StructureProgramEngine()
    out: Dict[date, dict] = {}
    days = sorted(d for d in gby if d <= through)
    for d in days:
        rth = rth_slice(gby.get(d))
        if rth.empty:
            continue
        engine.ingest_day_15m(to_15m(rth))
        if not engine.ready:
            continue
        bull_keys = [float(s.key) for s in engine.bull][-5:]
        bear_keys = [float(s.key) for s in engine.bear][-5:]
        out[d] = {
            "program": engine.program,
            "bull_key": engine.latest_key("bull"),
            "bear_key": engine.latest_key("bear"),
            "bull_keys": bull_keys,
            "bear_keys": bear_keys,
        }
    return out


def plot_trade(
    gby: Dict[date, pd.DataFrame],
    t: pd.Series,
    struct_by_day: Dict[date, dict],
    out_path: Path,
) -> bool:
    entry_ts = _to_ny(t.entry_ts)
    exit_ts = _to_ny(t.exit_ts)
    d0 = entry_ts.date()
    all_days = sorted(gby)
    if d0 not in gby:
        near = [d for d in all_days if abs((d - d0).days) < 5]
        if not near:
            return False
        d0 = min(near, key=lambda d: abs((d - d0).days))

    # window: prior RTH day (ST warm) + entry→exit span + pad
    di = all_days.index(d0) if d0 in all_days else 0
    warm_day = all_days[di - 1] if di > 0 else d0
    end_day = exit_ts.date()
    if end_day not in gby:
        end_day = d0
    days = [d for d in all_days if warm_day <= d <= end_day]
    frames = []
    for d in days:
        rth = rth_slice(gby[d])
        if not rth.empty:
            frames.append(rth)
    if not frames:
        return False
    full = pd.concat(frames).sort_index()
    # chart display: from entry session open (or 90m pre) through exit+45m
    pad_pre = timedelta(minutes=30)
    pad_post = timedelta(minutes=45)
    view_start = max(full.index[0], entry_ts.normalize() + pd.Timedelta(hours=9, minutes=30) - pad_pre)
    # keep some pre-entry context inside RTH
    view_start = min(view_start, entry_ts - timedelta(minutes=60))
    view_end = min(full.index[-1], exit_ts + pad_post)
    # if hold is tiny, show at least ~90 minutes of session
    if (view_end - view_start) < timedelta(minutes=90):
        view_end = min(full.index[-1], view_start + timedelta(minutes=120))
    plot = full[(full.index >= view_start) & (full.index <= view_end)].copy()
    if len(plot) < 5:
        return False

    # ST on warm+view (use full concat for continuity, then slice)
    warm_rth = rth_slice(gby.get(warm_day))
    if warm_rth is not None and not warm_rth.empty:
        st_src = full[(full.index >= warm_rth.index[0]) & (full.index <= view_end)].copy()
    else:
        st_src = plot.copy()
    if len(st_src) < ATR_LEN + 5:
        st_src = plot
    st = compute_supertrend(st_src, atr_len=ATR_LEN, multiplier=ATR_MULT)
    st = st.reindex(plot.index)

    fig, ax = plt.subplots(figsize=(18, 9))
    x = np.arange(len(plot))
    up = plot["close"].to_numpy() >= plot["open"].to_numpy()
    ax.vlines(x, plot["low"], plot["high"], color="#888", lw=0.55, zorder=1)
    ax.vlines(x[up], plot["open"][up], plot["close"][up], color="#1a9850", lw=1.6, zorder=2)
    ax.vlines(x[~up], plot["close"][~up], plot["open"][~up], color="#d73027", lw=1.6, zorder=2)

    bull = st["supertrend"].where(st["supertrend_trend"] == 1)
    bear = st["supertrend"].where(st["supertrend_trend"] == -1)
    ax.plot(x, bull.to_numpy(), color="#009c5b", lw=1.6, label="1m ST trail (bull)", zorder=5)
    ax.plot(x, bear.to_numpy(), color="#d62728", lw=1.6, label="1m ST trail (bear)", zorder=5)

    # OR for entry session
    rth0 = rth_slice(gby[d0])
    oh, ol = session_or(rth0)
    if oh is not None:
        ax.axhline(oh, color="#5d4037", ls="--", lw=1.2, alpha=0.9, label="OR high %.1f" % oh)
        ax.axhline(ol, color="#5d4037", ls="--", lw=1.2, alpha=0.9, label="OR low %.1f" % ol)
        ax.axhline(0.5 * (oh + ol), color="#8d6e63", ls=":", lw=0.9, alpha=0.7, label="OR mid")

    snap = struct_by_day.get(d0) or struct_by_day.get(warm_day) or {}
    for i, bk in enumerate(snap.get("bull_keys") or []):
        ax.axhline(
            bk,
            color="#1565c0",
            ls=":",
            lw=0.7 if i < len(snap.get("bull_keys", [])) - 1 else 1.2,
            alpha=0.35 if i < len(snap.get("bull_keys", [])) - 1 else 0.75,
            label="Bull LL keys" if i == 0 else None,
        )
    for i, bk in enumerate(snap.get("bear_keys") or []):
        ax.axhline(
            bk,
            color="#6a1b9a",
            ls=":",
            lw=0.7 if i < len(snap.get("bear_keys", [])) - 1 else 1.2,
            alpha=0.35 if i < len(snap.get("bear_keys", [])) - 1 else 0.75,
            label="Bear HH keys" if i == 0 else None,
        )

    sk = float(t.structure_key)
    fill = float(t.fill_px)
    ax.axhline(sk, color="#0d47a1", ls="-", lw=1.8, label="Entry level (structure) %.2f" % sk, zorder=6)
    if abs(fill - sk) > 0.01:
        ax.axhline(fill, color="#0277bd", ls="--", lw=1.2, label="Fill %.2f" % fill, zorder=6)
    ax.axhline(float(t.stop), color="#ef6c00", ls=":", lw=1.3, label="Risk stop ±%.0f → %.2f" % (RISK_PTS, float(t.stop)))

    sign = 1.0 if t.side == "long" else -1.0
    e = sk
    ax.axhline(e + sign * 22.0, color="#2e7d32", ls="--", lw=0.9, alpha=0.7, label="Scale +22")
    ax.axhline(e + sign * 50.0, color="#00695c", ls="--", lw=0.9, alpha=0.65, label="Scale +50")
    ax.axhline(e + sign * 200.0, color="#004d40", ls="--", lw=0.8, alpha=0.55, label="Runner +200")

    def _xi(ts) -> Optional[int]:
        ts = _to_ny(ts)
        # bar label = minute start
        idx = plot.index
        for i, bt in enumerate(idx):
            if bt <= ts < bt + pd.Timedelta(minutes=1):
                return i
        deltas = [(abs((bt - ts).total_seconds()), i) for i, bt in enumerate(idx)]
        return min(deltas)[1] if deltas else None

    ei = _xi(entry_ts)
    xi = _xi(exit_ts)
    color = "#1a9850" if float(t.pnl_usd) > 0 else "#d73027"
    if ei is not None:
        ax.scatter(
            [ei],
            [fill],
            marker="^" if t.side == "long" else "v",
            s=170,
            color=color,
            edgecolors="white",
            zorder=8,
            label="Entry fill",
        )
    if xi is not None:
        ax.scatter(
            [xi],
            [float(t.exit)],
            marker="X",
            s=150,
            color=color,
            edgecolors="white",
            zorder=8,
            label="Exit (%s)" % t.exit_reason,
        )
    if ei is not None and xi is not None and xi >= ei:
        ax.axvspan(ei, max(xi, ei + 1), color=color, alpha=0.10, zorder=0)

    # session separators
    for d in days[1:]:
        for i, bt in enumerate(plot.index):
            if bt.date() == d:
                ax.axvline(i, color="#bbb", lw=0.8, ls="--", zorder=0)
                break

    prog = snap.get("program") or t.program
    ax.set_title(
        "NQ 1m | structure_only resting #%d %s %s | $%+.0f | %s → %s | %s | program=%s"
        % (
            int(t.chart_id),
            str(t.side).upper(),
            str(t.result).upper(),
            float(t.pnl_usd),
            entry_ts.strftime("%Y-%m-%d %H:%M"),
            exit_ts.strftime("%H:%M"),
            t.exit_reasons,
            prog,
        ),
        fontsize=11,
    )
    ax.legend(loc="upper left", fontsize=7, ncol=2)
    ax.set_xlim(-1, len(plot))
    step = max(1, len(plot) // 14)
    ax.set_xticks(x[::step])
    ax.set_xticklabels(
        [plot.index[i].strftime("%m-%d %H:%M") for i in x[::step]],
        rotation=30,
        ha="right",
        fontsize=8,
    )
    ax.set_ylabel("NQ")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=110)
    plt.close(fig)
    return True


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    state = Path(args.state)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    win_dir = out / "winners"
    loss_dir = out / "losers"
    win_dir.mkdir(parents=True, exist_ok=True)
    loss_dir.mkdir(parents=True, exist_ok=True)
    for d in (win_dir, loss_dir):
        for old in d.glob("*.png"):
            old.unlink()

    print("Loading campaigns…", flush=True)
    camp = load_campaigns(state)
    sample = sample_campaigns(camp, args.n, args.seed)
    sample.to_csv(out / "charted_trades.csv", index=False)
    print(
        "Campaigns=%d | charting %d (%dW / %dL)"
        % (
            len(camp),
            len(sample),
            int((sample.pnl_usd > 0).sum()),
            int((sample.pnl_usd <= 0).sum()),
        ),
        flush=True,
    )

    print("Loading NQ 1m…", flush=True)
    gby = load_1m_by_ny_date_any(MARKETS["nq"].dbn_path.resolve(), "nq")
    through = max(sample["session_date"])
    print("Building structure snapshots through %s…" % through, flush=True)
    # Structure lists need ~20+20 structures: walk from 2020-01 for correctness
    start_full = date(2020, 1, 1)
    struct_by_day = build_day_structure(
        {d: gby[d] for d in gby if d >= start_full and d <= through}, through
    )
    print("Structure days ready: %d" % len(struct_by_day), flush=True)

    n_ok = 0
    win_names: List[str] = []
    loss_names: List[str] = []
    for _, t in sample.iterrows():
        folder = win_dir if float(t.pnl_usd) > 0 else loss_dir
        fname = "%03d_%s_%s_%s_pnl%+.0f.png" % (
            int(t.chart_id),
            _to_ny(t.entry_ts).strftime("%Y-%m-%d"),
            t.side,
            str(t.exit_reason).replace("|", "+")[:40],
            float(t.pnl_usd),
        )
        path = folder / fname
        ok = plot_trade(gby, t, struct_by_day, path)
        if ok:
            n_ok += 1
            (win_names if float(t.pnl_usd) > 0 else loss_names).append(fname)
            if n_ok % 20 == 0:
                print("  charted %d/%d" % (n_ok, len(sample)), flush=True)
        else:
            print("  skip %s" % t.trade_id, flush=True)

    for folder, names, label in (
        (win_dir, win_names, "Winners"),
        (loss_dir, loss_names, "Losers"),
    ):
        lines = [
            "# %s — structure_only resting (1m)" % label,
            "",
            "1-minute RTH candles, 1m SuperTrend 14×3 trail, OR (09:30–09:44), "
            "structure bull LL / bear HH keys, original resting entry level, fill, risk stop, scale ladder.",
            "",
        ]
        for n in names:
            lines.append("- [%s](%s)" % (n, n))
        (folder / "INDEX.md").write_text("\n".join(lines))

    summary = [
        "# Structure-only resting — trade charts",
        "",
        "Sampled **%d** of %d campaigns (seed=%d): **%d** winners · **%d** losers."
        % (n_ok, len(camp), args.seed, len(win_names), len(loss_names)),
        "",
        "- [`winners/`](winners/) — %d charts" % len(win_names),
        "- [`losers/`](losers/) — %d charts" % len(loss_names),
        "- [`charted_trades.csv`](charted_trades.csv)",
        "",
        "Each chart: **1m candles**, **OR high/low/mid**, **1m ST trailing stop**, "
        "**structure bull LL / bear HH** (latest + recent), **original entry level** "
        "(filled limit = structure key), fill if slipped, risk stop ±8, scale +22/+50/+200.",
        "",
    ]
    (out / "README.md").write_text("\n".join(summary))
    print("→ %s (%d charts)" % (out, n_ok), flush=True)


if __name__ == "__main__":
    main()
