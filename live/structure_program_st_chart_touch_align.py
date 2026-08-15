"""Chart touch_st_align broker campaigns: 1m + OR + ST + structure levels.

Usage:
  python -m live.structure_program_st_chart_touch_align --n-wins 100 --n-losses 100
"""

from __future__ import annotations

import argparse
from pathlib import Path

# Reuse the structure_only charting machinery with different defaults / sampling.
from .structure_program_st_chart_struct_resting import (
    RISK_PTS,
    build_day_structure,
    load_campaigns,
    plot_trade,
    sample_campaigns,
)
from .v2b_strategy_cross_market_replay import MARKETS, load_1m_by_ny_date_any
from datetime import date, timedelta
import pandas as pd
import numpy as np
import random

REPO = Path(__file__).resolve().parents[1]
DEFAULT_STATE = (
    REPO
    / "live"
    / "state"
    / "structure_program_st_broker_touch_align"
    / "states"
    / "nq_touch_st_align_r8"
)
DEFAULT_OUT = (
    REPO / "live" / "state" / "structure_program_st_broker_touch_align" / "trade_charts"
)


def sample_fixed(
    camp: pd.DataFrame, n_wins: int, n_losses: int, seed: int
) -> pd.DataFrame:
    rng = random.Random(seed)
    wins = camp[camp["pnl_usd"] > 0]
    losses = camp[camp["pnl_usd"] <= 0]
    wi = wins.index.tolist()
    li = losses.index.tolist()

    def pick(idxs, k):
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

    sel = pick(wi, min(n_wins, len(wi))) + pick(li, min(n_losses, len(li)))
    out = camp.loc[sel].copy().sort_values("entry_ts").reset_index(drop=True)
    out["chart_id"] = np.arange(1, len(out) + 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default=str(DEFAULT_STATE))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    ap.add_argument("--n-wins", type=int, default=100)
    ap.add_argument("--n-losses", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()
    state = Path(args.state)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    win_dir = out / "winners"
    loss_dir = out / "losers"
    for d in (win_dir, loss_dir):
        d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("*.png"):
            old.unlink()

    print("Loading campaigns…", flush=True)
    camp = load_campaigns(state)
    # stop for touch_align: prefer structure_key ± risk only as fallback; actual
    # initial SL was ST trail — chart still shows structure entry level.
    sample = sample_fixed(camp, args.n_wins, args.n_losses, args.seed)
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
    struct_by_day = build_day_structure(
        {d: gby[d] for d in gby if d >= date(2020, 1, 1) and d <= through}, through
    )
    print("Structure days ready: %d" % len(struct_by_day), flush=True)

    n_ok = 0
    win_names = []
    loss_names = []
    for _, t in sample.iterrows():
        folder = win_dir if float(t.pnl_usd) > 0 else loss_dir
        from .structure_program_st_chart_struct_resting import _to_ny

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

    for folder, names, label in (
        (win_dir, win_names, "Winners"),
        (loss_dir, loss_names, "Losers"),
    ):
        lines = [
            "# %s — touch_st_align (1m)" % label,
            "",
            "1m candles, OR, 1m ST trail, structure keys, entry/structure level, "
            "risk/tight stops, scale ladder (+25/+50/+200).",
            "",
        ]
        for n in names:
            lines.append("- [%s](%s)" % (n, n))
        (folder / "INDEX.md").write_text("\n".join(lines))

    (out / "README.md").write_text(
        "\n".join(
            [
                "# touch_st_align — trade charts",
                "",
                "Sampled **%d** campaigns: **%d** winners · **%d** losers."
                % (n_ok, len(win_names), len(loss_names)),
                "",
                "- [`winners/`](winners/)",
                "- [`losers/`](losers/)",
                "- [`charted_trades.csv`](charted_trades.csv)",
                "",
            ]
        )
    )
    print("→ %s (%d charts)" % (out, n_ok), flush=True)


if __name__ == "__main__":
    main()
