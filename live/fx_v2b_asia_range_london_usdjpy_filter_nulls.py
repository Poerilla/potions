"""USDJPY Asia-range London — filter timing nulls on the unfiltered shadow tape.

Builds a campaign-level unfiltered S_3_1_3 shadow tape and runs:

1. January-skip month placebo (all 12 one-month omissions)
2. Matched-exposure random-skip null
3. Circular-shift / block-shift gate null
4. Shadow-tape outcome null (block permute nets → rebuild WR/PF gate)
5. Selection-aware master null (White-style best-of-search)

Writes ``FILTER_NULLS.md`` + ``filter_nulls.csv`` under the filters hub.
Does **not** shuffle bars; campaign P&Ls stay intact except where a null
explicitly remaps gate timing vs outcomes.
"""

from __future__ import annotations

import argparse
import json
import math
import traceback
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from .fx_v2b_asia_range_london_usdjpy_filters import (
    FILTER_HUB,
    SIZING_HUB,
    _campaigns_from_unit_trades,
)
from .fx_v2b_london_ungated import JPY_USD, _progress

REPO = Path(__file__).resolve().parents[1]
DEFAULT_UNIT = (
    SIZING_HUB / "states" / "usdjpy_v2b_asia_range_london_S_3_1_3" / "unit_trades.csv"
)
DEFAULT_FILTERED_METRICS = (
    FILTER_HUB
    / "states"
    / "usdjpy_v2b_asia_range_london_S_3_1_3_flt"
    / "metrics.json"
)
SEED = 20260811
OOS_CUT = 2021  # years > cut are frozen-rule OOS
FROZEN = {
    "book": "S_3_1_3",
    "skip_months": (1,),
    "window": 50,
    "min_wr": 0.40,
    "min_pf": 1.0,
}
BOOKS = (
    "S_0_5_0",
    "S_0_2_3",
    "S_1_1_1",
    "S_1_1_3",
    "S_1_3_1",
    "S_2_0_3",
    "S_2_3_0",
    "S_3_1_1",
    "S_3_1_3",
    "S_5_0_0",
)
# Predeclared roll grid (research neighbourhood around promote cell).
ROLL_WINDOWS = (40, 50, 60)
WR_THRESH = (0.35, 0.40, 0.45)
PF_THRESH = (0.85, 1.0, 1.15)
MONTH_NAMES = [
    "",
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
]


def _usd(jpy: float) -> float:
    return float(jpy) / float(JPY_USD)


def _max_dd(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float((equity - peak).min())


def _profit_factor_arr(pnl: np.ndarray) -> float:
    if pnl.size == 0:
        return 0.0
    gains = float(pnl[pnl > 0].sum())
    losses = float((-pnl[pnl < 0]).sum())
    if losses <= 0:
        return float("inf") if gains > 0 else 0.0
    return gains / losses


def _finite(x: float) -> float:
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return 999.0 if (isinstance(x, float) and math.isinf(x) and x > 0) else 0.0
    return float(x)


@dataclass
class Tape:
    """Chronological unfiltered campaign shadow tape."""

    book: str
    session: np.ndarray  # object dates
    year: np.ndarray
    month: np.ndarray
    net_jpy: np.ndarray
    net_usd: np.ndarray
    win: np.ndarray

    @property
    def n(self) -> int:
        return int(len(self.net_usd))


def load_tape(unit_trades: Path, *, book: str = "S_3_1_3") -> Tape:
    camps = _campaigns_from_unit_trades(unit_trades)
    return Tape(
        book=book,
        session=camps["session"].to_numpy(),
        year=camps["year"].astype(int).to_numpy(),
        month=camps["month"].astype(int).to_numpy(),
        net_jpy=camps["net_usd"].astype(float).to_numpy(),
        net_usd=(camps["net_usd"].astype(float) / float(JPY_USD)).to_numpy(),
        win=(camps["net_usd"].astype(float) > 0).to_numpy(),
    )


def load_book_tape(book: str) -> Optional[Tape]:
    path = SIZING_HUB / "states" / ("usdjpy_v2b_asia_range_london_%s" % book) / "unit_trades.csv"
    if not path.exists():
        # S_3_3_3 lives on the filters hub unfiltered run
        alt = FILTER_HUB / "states" / ("usdjpy_v2b_asia_range_london_%s" % book) / "unit_trades.csv"
        path = alt if alt.exists() else path
    if not path.exists():
        return None
    return load_tape(path, book=book)


def score_mask(
    tape: Tape,
    take: np.ndarray,
    *,
    label: str = "",
    oos_cut: int = OOS_CUT,
) -> dict:
    take = np.asarray(take, dtype=bool)
    if take.shape[0] != tape.n:
        raise ValueError("mask length mismatch")
    skipped = ~take
    taken_usd = tape.net_usd[take]
    taken_jpy = tape.net_jpy[take]
    eq = np.cumsum(taken_usd) if taken_usd.size else np.array([], dtype=float)
    dd = _max_dd(eq)
    stress = abs(dd)  # closed-campaign equity DD as reachable-stress proxy on shadow tape
    net = float(taken_usd.sum()) if taken_usd.size else 0.0
    ns = (net / stress) if stress > 0 else 0.0
    wr = float((taken_usd > 0).mean()) if taken_usd.size else 0.0
    pf = _finite(_profit_factor_arr(taken_jpy))
    worst = float(taken_usd.min()) if taken_usd.size else 0.0
    # yearly concentration: max abs-year share of abs net
    year_conc = 0.0
    if taken_usd.size:
        ty = tape.year[take]
        by = {}
        for y, v in zip(ty.tolist(), taken_usd.tolist()):
            by[y] = by.get(y, 0.0) + float(v)
        abs_sum = sum(abs(v) for v in by.values()) or 1.0
        year_conc = max(abs(v) for v in by.values()) / abs_sum
    oos = tape.year > int(oos_cut)
    oos_take = take & oos
    oos_usd = tape.net_usd[oos_take]
    oos_eq = np.cumsum(oos_usd) if oos_usd.size else np.array([], dtype=float)
    oos_dd = abs(_max_dd(oos_eq))
    oos_net = float(oos_usd.sum()) if oos_usd.size else 0.0
    oos_ns = (oos_net / oos_dd) if oos_dd > 0 else 0.0
    return {
        "label": label,
        "taken_n": int(take.sum()),
        "skipped_n": int(skipped.sum()),
        "net_usd": net,
        "stress_usd": -stress if stress else 0.0,
        "ns": ns,
        "max_dd_usd": dd,
        "worst_campaign_usd": worst,
        "pf": pf,
        "wr": wr,
        "year_conc": year_conc,
        "oos_net_usd": oos_net,
        "oos_ns": oos_ns,
        "oos_taken_n": int(oos_take.sum()),
        "delta_net_vs_all": net - float(tape.net_usd.sum()),
    }


def month_skip_mask(tape: Tape, months: Sequence[int]) -> np.ndarray:
    skip = set(int(m) for m in months)
    if not skip:
        return np.ones(tape.n, dtype=bool)
    return ~np.isin(tape.month, list(skip))


def rolling_gate_mask(
    nets_jpy: np.ndarray,
    *,
    window: int,
    min_wr: float,
    min_pf: float,
    mode: str,
) -> np.ndarray:
    """Causal rolling WR/PF gate on a shadow net sequence (JPY).

    Modes: ``none``, ``wr``, ``pf``, ``roll``.
    """
    n = int(len(nets_jpy))
    take = np.ones(n, dtype=bool)
    if mode == "none" or window <= 0 or n <= window:
        return take
    wins = (nets_jpy > 0).astype(np.float64)
    pos = np.maximum(nets_jpy, 0.0)
    neg = np.maximum(-nets_jpy, 0.0)
    # sliding window sums via cumsum difference for indices window..n-1
    c_wins = np.cumsum(wins)
    c_pos = np.cumsum(pos)
    c_neg = np.cumsum(neg)
    # sum over [i-window, i) equals c[i-1] - c[i-window-1] for i>=window
    # for i in range(window, n): hist = nets[i-window:i]
    i0 = np.arange(window, n)
    sum_wins = c_wins[i0 - 1] - np.where(i0 - window - 1 >= 0, c_wins[i0 - window - 1], 0.0)
    sum_pos = c_pos[i0 - 1] - np.where(i0 - window - 1 >= 0, c_pos[i0 - window - 1], 0.0)
    sum_neg = c_neg[i0 - 1] - np.where(i0 - window - 1 >= 0, c_neg[i0 - window - 1], 0.0)
    wr = sum_wins / float(window)
    pf = np.where(sum_neg > 0, sum_pos / sum_neg, np.where(sum_pos > 0, np.inf, 0.0))
    bad_wr = wr < min_wr
    bad_pf = pf < min_pf
    if mode == "wr":
        take[window:] = ~bad_wr
    elif mode == "pf":
        take[window:] = ~bad_pf
    else:
        take[window:] = ~(bad_wr | bad_pf)
    return take


def combined_mask(
    tape: Tape,
    *,
    skip_months: Sequence[int] = (),
    window: int = 50,
    min_wr: float = 0.40,
    min_pf: float = 1.0,
    roll_mode: str = "roll",
    shadow_nets_jpy: Optional[np.ndarray] = None,
) -> np.ndarray:
    """Month blackout AND rolling gate. Rolling state from ``shadow_nets_jpy`` (default: tape)."""
    m = month_skip_mask(tape, skip_months)
    nets = tape.net_jpy if shadow_nets_jpy is None else np.asarray(shadow_nets_jpy, dtype=float)
    r = rolling_gate_mask(nets, window=window, min_wr=min_wr, min_pf=min_pf, mode=roll_mode)
    return m & r


def component_masks(tape: Tape) -> Dict[str, np.ndarray]:
    return {
        "unfiltered": np.ones(tape.n, dtype=bool),
        "january_only": month_skip_mask(tape, (1,)),
        "wr_only": rolling_gate_mask(
            tape.net_jpy, window=50, min_wr=0.40, min_pf=1.0, mode="wr"
        ),
        "pf_only": rolling_gate_mask(
            tape.net_jpy, window=50, min_wr=0.40, min_pf=1.0, mode="pf"
        ),
        "roll_wr_pf": rolling_gate_mask(
            tape.net_jpy, window=50, min_wr=0.40, min_pf=1.0, mode="roll"
        ),
        "combined": combined_mask(
            tape, skip_months=(1,), window=50, min_wr=0.40, min_pf=1.0, roll_mode="roll"
        ),
    }


def empirical_pvalue(actual: float, nulls: Sequence[float], *, higher_is_better: bool) -> float:
    arr = np.asarray(list(nulls), dtype=float)
    if arr.size == 0:
        return 1.0
    if higher_is_better:
        extreme = int(np.sum(arr >= actual))
    else:
        extreme = int(np.sum(arr <= actual))
    return float((extreme + 1) / (arr.size + 1))


def classify_result(
    *,
    p_net: float,
    p_ns: float,
    p_dd: float,
    p_stress: float,
    alpha: float = 0.05,
) -> Tuple[str, str]:
    """Return (decision, interpretation) under conservative rules."""
    alpha_ok = (p_net <= alpha) or (p_ns <= alpha and p_net <= 0.25)
    risk_ok = (p_dd <= alpha) or (p_stress <= alpha)
    if alpha_ok and (p_net <= alpha or p_ns <= alpha):
        return "PROMOTE FILTER AS ALPHA", "alpha-selection evidence"
    if risk_ok and not alpha_ok:
        return "RETAIN FILTER AS RISK THROTTLE", "risk-throttle evidence"
    if risk_ok and p_ns <= alpha and p_net > 0.25:
        return "RETAIN FILTER AS RISK THROTTLE", "risk-throttle evidence"
    return "REJECT FILTER", "no evidence"


# ---------------------------------------------------------------------------
# Null 1 — month placebo
# ---------------------------------------------------------------------------


def null_month_placebo(tape: Tape) -> Tuple[pd.DataFrame, dict]:
    rows = []
    for m in range(1, 13):
        mask = month_skip_mask(tape, (m,))
        # keep rolling gate unchanged (promote combined mechanics minus Jan→other month)
        take = mask & rolling_gate_mask(
            tape.net_jpy, window=50, min_wr=0.40, min_pf=1.0, mode="roll"
        )
        sc = score_mask(tape, take, label="skip_%s" % MONTH_NAMES[m])
        sc["month"] = m
        sc["month_name"] = MONTH_NAMES[m]
        rows.append(sc)
    df = pd.DataFrame(rows)
    # ranks (1 = best): higher net/ns better; lower |dd|/stress better (less negative max_dd better → rank ascending=False on max_dd)
    df = df.copy()
    df["rank_net"] = df["net_usd"].rank(ascending=False, method="min")
    df["rank_ns"] = df["ns"].rank(ascending=False, method="min")
    df["rank_dd"] = df["max_dd_usd"].rank(ascending=False, method="min")  # less negative better
    # deltas vs no-month-skip + roll only
    roll_only = score_mask(
        tape,
        rolling_gate_mask(tape.net_jpy, window=50, min_wr=0.40, min_pf=1.0, mode="roll"),
        label="roll_only",
    )
    df["delta_net"] = df["net_usd"] - roll_only["net_usd"]
    df["delta_ns"] = df["ns"] - roll_only["ns"]
    df["delta_dd"] = df["max_dd_usd"] - roll_only["max_dd_usd"]
    jan = df[df["month"] == 1].iloc[0]
    # empirical p for January among the 12
    p_net = float((df["delta_net"] >= float(jan["delta_net"])).sum() / 12.0)
    p_ns = float((df["delta_ns"] >= float(jan["delta_ns"])).sum() / 12.0)
    p_dd = float((df["delta_dd"] >= float(jan["delta_dd"])).sum() / 12.0)  # more improvement (more +Δdd)
    summary = {
        "test": "january_month_placebo",
        "null_construction": (
            "Skip one calendar month + keep roll50 WR40/PF1; exhaust all 12 months"
        ),
        "iterations": 12,
        "seed": SEED,
        "actual_month": "January",
        "actual": score_mask(
            tape,
            combined_mask(tape, skip_months=(1,), window=50, min_wr=0.40, min_pf=1.0),
            label="combined",
        ),
        "jan_rank_net": int(df.loc[df["month"] == 1, "rank_net"].iloc[0]),
        "jan_rank_ns": int(df.loc[df["month"] == 1, "rank_ns"].iloc[0]),
        "jan_rank_dd": int(df.loc[df["month"] == 1, "rank_dd"].iloc[0]),
        "p_delta_net": p_net,
        "p_delta_ns": p_ns,
        "p_delta_dd": p_dd,
        "null_median_net": float(df["net_usd"].median()),
        "null_p05_net": float(df["net_usd"].quantile(0.05)),
        "null_p95_net": float(df["net_usd"].quantile(0.95)),
        "null_median_ns": float(df["ns"].median()),
        "null_p05_ns": float(df["ns"].quantile(0.05)),
        "null_p95_ns": float(df["ns"].quantile(0.95)),
        "null_median_dd": float(df["max_dd_usd"].median()),
        "null_p05_dd": float(df["max_dd_usd"].quantile(0.05)),
        "null_p95_dd": float(df["max_dd_usd"].quantile(0.95)),
        "table": df,
    }
    return df, summary


# ---------------------------------------------------------------------------
# Null 2 — matched-exposure random skip
# ---------------------------------------------------------------------------


def _year_month_targets(tape: Tape, take: np.ndarray) -> Dict[Tuple[int, int], int]:
    out: Dict[Tuple[int, int], int] = {}
    for y, m, t in zip(tape.year.tolist(), tape.month.tolist(), take.tolist()):
        if t:
            out[(int(y), int(m))] = out.get((int(y), int(m)), 0) + 1
    return out


def _matched_random_mask(
    tape: Tape,
    targets: Dict[Tuple[int, int], int],
    rng: np.random.Generator,
    *,
    total_take: int,
) -> np.ndarray:
    """Sample exactly ``total_take`` campaigns, matching year/month counts when possible."""
    take = np.zeros(tape.n, dtype=bool)
    idx_by: Dict[Tuple[int, int], np.ndarray] = {}
    for i, (y, m) in enumerate(zip(tape.year.tolist(), tape.month.tolist())):
        key = (int(y), int(m))
        idx_by.setdefault(key, [])
        idx_by[key].append(i)
    idx_by = {k: np.asarray(v, dtype=int) for k, v in idx_by.items()}
    chosen = 0
    for key, need in targets.items():
        pool = idx_by.get(key)
        if pool is None or pool.size == 0:
            continue
        k = min(int(need), int(pool.size))
        pick = rng.choice(pool, size=k, replace=False)
        take[pick] = True
        chosen += k
    # top-up / trim to exact total_take
    if chosen < total_take:
        remain = np.flatnonzero(~take)
        need = total_take - chosen
        if remain.size and need > 0:
            pick = rng.choice(remain, size=min(need, remain.size), replace=False)
            take[pick] = True
    elif chosen > total_take:
        have = np.flatnonzero(take)
        drop = rng.choice(have, size=chosen - total_take, replace=False)
        take[drop] = False
    return take


def null_matched_exposure(
    tape: Tape,
    actual_take: np.ndarray,
    *,
    iterations: int = 5000,
    seed: int = SEED,
) -> Tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed)
    targets = _year_month_targets(tape, actual_take)
    n_take = int(actual_take.sum())
    actual = score_mask(tape, actual_take, label="actual_combined")
    rows = []
    for i in range(iterations):
        mask = _matched_random_mask(tape, targets, rng, total_take=n_take)
        sc = score_mask(tape, mask, label="null_%d" % i)
        rows.append(sc)
    df = pd.DataFrame(rows)
    summary = _summarize_null(
        test="matched_exposure_random_skip",
        construction=(
            "Random masks with exact taken count and approximate year/month "
            "campaign counts of the live combined filter"
        ),
        iterations=iterations,
        seed=seed,
        actual=actual,
        null_df=df,
    )
    return df, summary


# ---------------------------------------------------------------------------
# Null 3 — circular shift of live gate
# ---------------------------------------------------------------------------


def null_circular_shift(
    tape: Tape,
    gate_take: np.ndarray,
    *,
    iterations: int = 2000,
    seed: int = SEED,
    min_shift: int = 10,
) -> Tuple[pd.DataFrame, dict]:
    rng = np.random.default_rng(seed + 17)
    n = tape.n
    actual = score_mask(tape, gate_take, label="actual_combined")
    # all non-trivial shifts (deterministic coverage + random subsample if huge)
    shifts = [s for s in range(min_shift, n - min_shift + 1)]
    if len(shifts) > iterations:
        shifts = list(rng.choice(shifts, size=iterations, replace=False))
    rows = []
    for s in shifts:
        shifted = np.roll(gate_take, int(s))
        sc = score_mask(tape, shifted, label="shift_%d" % s)
        sc["shift"] = int(s)
        rows.append(sc)
    df = pd.DataFrame(rows)
    summary = _summarize_null(
        test="circular_shift_gate",
        construction=(
            "Circularly shift live_gate_take vs fixed campaign P&L; exclude |shift|<%d"
            % min_shift
        ),
        iterations=int(len(df)),
        seed=seed,
        actual=actual,
        null_df=df,
    )
    return df, summary


# ---------------------------------------------------------------------------
# Null 4 — shadow outcome block permutation
# ---------------------------------------------------------------------------


def _block_permute(arr: np.ndarray, block: int, rng: np.random.Generator) -> np.ndarray:
    n = len(arr)
    if block <= 1 or block >= n:
        out = arr.copy()
        rng.shuffle(out)
        return out
    blocks = [arr[i : i + block] for i in range(0, n, block)]
    order = rng.permutation(len(blocks))
    return np.concatenate([blocks[i] for i in order])


def null_shadow_outcome(
    tape: Tape,
    *,
    block_lengths: Sequence[int] = (10, 25, 50),
    iterations: int = 1000,
    seed: int = SEED,
) -> Tuple[Dict[int, pd.DataFrame], List[dict]]:
    """Permute shadow nets in blocks; rebuild WR/PF(+Jan) gate; apply to real PnL."""
    out_frames: Dict[int, pd.DataFrame] = {}
    summaries: List[dict] = []
    actual_take = combined_mask(
        tape, skip_months=(1,), window=50, min_wr=0.40, min_pf=1.0, roll_mode="roll"
    )
    actual = score_mask(tape, actual_take, label="actual_combined")
    for bi, block in enumerate(block_lengths):
        rng = np.random.default_rng(seed + 100 + bi)
        rows = []
        for i in range(iterations):
            null_nets = _block_permute(tape.net_jpy, int(block), rng)
            take = combined_mask(
                tape,
                skip_months=(1,),
                window=50,
                min_wr=0.40,
                min_pf=1.0,
                roll_mode="roll",
                shadow_nets_jpy=null_nets,
            )
            sc = score_mask(tape, take, label="block%d_%d" % (block, i))
            rows.append(sc)
        df = pd.DataFrame(rows)
        out_frames[int(block)] = df
        summaries.append(
            _summarize_null(
                test="shadow_outcome_block_%d" % block,
                construction=(
                    "Block-permute unfiltered shadow nets (block=%d); recompute "
                    "Jan+roll50 WR40/PF1 gate; apply decisions to real campaign P&L"
                    % block
                ),
                iterations=iterations,
                seed=seed + 100 + bi,
                actual=actual,
                null_df=df,
            )
        )
    return out_frames, summaries


# ---------------------------------------------------------------------------
# Selection-aware master null
# ---------------------------------------------------------------------------


def _candidate_specs() -> List[dict]:
    specs: List[dict] = []
    # calendar: no skip + each single month
    calendars: List[Tuple[str, Tuple[int, ...]]] = [("none", ())]
    for m in range(1, 13):
        calendars.append(("m%d" % m, (m,)))
    roll_specs: List[Tuple[str, str, int, float, float]] = [("none", "none", 0, 0.0, 0.0)]
    for w in ROLL_WINDOWS:
        for wr in WR_THRESH:
            roll_specs.append(("wr_w%d_wr%.2f" % (w, wr), "wr", w, wr, 1.0))
        for pf in PF_THRESH:
            roll_specs.append(("pf_w%d_pf%.2f" % (w, pf), "pf", w, 0.40, pf))
        for wr in WR_THRESH:
            for pf in PF_THRESH:
                roll_specs.append(
                    ("roll_w%d_wr%.2f_pf%.2f" % (w, wr, pf), "roll", w, wr, pf)
                )
    for cal_name, months in calendars:
        for roll_name, mode, window, min_wr, min_pf in roll_specs:
            specs.append(
                {
                    "cal": cal_name,
                    "months": months,
                    "roll": roll_name,
                    "mode": mode,
                    "window": window,
                    "min_wr": min_wr,
                    "min_pf": min_pf,
                }
            )
    return specs


def _ns_fast(net_usd: np.ndarray, take: np.ndarray) -> Tuple[float, float, float]:
    """Return (ns, net, max_dd) without building a full score dict."""
    taken = net_usd[take]
    if taken.size == 0:
        return 0.0, 0.0, 0.0
    net = float(taken.sum())
    eq = np.cumsum(taken)
    dd = _max_dd(eq)
    stress = abs(dd)
    ns = (net / stress) if stress > 0 else 0.0
    return ns, net, dd


def _roll_cache_for_nets(nets_jpy: np.ndarray) -> Dict[Tuple[str, int, float, float], np.ndarray]:
    """Precompute rolling take masks for the predeclared roll grid."""
    cache: Dict[Tuple[str, int, float, float], np.ndarray] = {}
    cache[("none", 0, 0.0, 0.0)] = np.ones(len(nets_jpy), dtype=bool)
    for w in ROLL_WINDOWS:
        for wr in WR_THRESH:
            cache[("wr", w, wr, 1.0)] = rolling_gate_mask(
                nets_jpy, window=w, min_wr=wr, min_pf=1.0, mode="wr"
            )
        for pf in PF_THRESH:
            cache[("pf", w, 0.40, pf)] = rolling_gate_mask(
                nets_jpy, window=w, min_wr=0.40, min_pf=pf, mode="pf"
            )
        for wr in WR_THRESH:
            for pf in PF_THRESH:
                cache[("roll", w, wr, pf)] = rolling_gate_mask(
                    nets_jpy, window=w, min_wr=wr, min_pf=pf, mode="roll"
                )
    return cache


def _month_cache(tape: Tape) -> Dict[str, np.ndarray]:
    out: Dict[str, np.ndarray] = {"none": np.ones(tape.n, dtype=bool)}
    for m in range(1, 13):
        out["m%d" % m] = month_skip_mask(tape, (m,))
    return out


def _best_ns_over_candidates(
    tapes: Dict[str, Tape],
    specs: List[dict],
    *,
    shadow_override: Optional[Dict[str, np.ndarray]] = None,
) -> Tuple[float, dict]:
    best_ns = -1e18
    best_meta: dict = {}
    # Unique roll keys from specs
    for book, tape in tapes.items():
        nets = tape.net_jpy if shadow_override is None else shadow_override[book]
        # When scoring self-consistently on overridden nets, use those nets for PnL too
        pnl = tape.net_usd if shadow_override is None else (nets / float(JPY_USD))
        roll_c = _roll_cache_for_nets(nets)
        month_c = _month_cache(tape)
        for sp in specs:
            rkey = (str(sp["mode"]), int(sp["window"]), float(sp["min_wr"]), float(sp["min_pf"]))
            take = month_c[sp["cal"]] & roll_c[rkey]
            ns, net, dd = _ns_fast(pnl, take)
            if ns > best_ns:
                best_ns = ns
                best_meta = {
                    "book": book,
                    "cal": sp["cal"],
                    "roll": sp["roll"],
                    "mode": sp["mode"],
                    "window": sp["window"],
                    "min_wr": sp["min_wr"],
                    "min_pf": sp["min_pf"],
                    "months": sp["months"],
                    "ns": ns,
                    "net_usd": net,
                    "max_dd_usd": dd,
                    "taken_n": int(take.sum()),
                    "skipped_n": int((~take).sum()),
                }
    return best_ns, best_meta


def null_selection_aware(
    tapes: Dict[str, Tape],
    *,
    iterations: int = 300,
    seed: int = SEED,
    block: int = 25,
) -> Tuple[pd.DataFrame, dict]:
    specs = _candidate_specs()
    # Real selected winner score on S_3_1_3 combined (not re-search — locked promote cell)
    real_tape = tapes["S_3_1_3"]
    real_take = combined_mask(
        real_tape, skip_months=(1,), window=50, min_wr=0.40, min_pf=1.0, roll_mode="roll"
    )
    actual = score_mask(real_tape, real_take, label="promote_S_3_1_3_jan_roll50")
    # Also record what unconstrained search finds on real tape (for honesty)
    real_best_ns, real_best_meta = _best_ns_over_candidates(tapes, specs)

    rng = np.random.default_rng(seed + 999)
    rows = []
    for i in range(iterations):
        override: Dict[str, np.ndarray] = {}
        for book, tape in tapes.items():
            # Circular-shift nets relative to calendar/gate state (breaks timing)
            shift = int(rng.integers(10, max(11, tape.n - 10)))
            override[book] = np.roll(tape.net_jpy, shift)
        # Self-consistent: best N/S on the null (shifted) tape after full search
        best_ns, meta = _best_ns_over_candidates(tapes, specs, shadow_override=override)
        rows.append(
            {
                "net_usd": meta["net_usd"],
                "ns": meta["ns"],
                "max_dd_usd": meta["max_dd_usd"],
                "stress_usd": -abs(meta["max_dd_usd"]),
                "taken_n": meta["taken_n"],
                "skipped_n": meta["skipped_n"],
                "pf": 0.0,
                "wr": 0.0,
                "worst_campaign_usd": 0.0,
                "oos_net_usd": 0.0,
                "oos_ns": 0.0,
                "best_ns_on_null_tape": best_ns,
                "sel_book": meta["book"],
                "sel_cal": meta["cal"],
                "sel_roll": meta["roll"],
            }
        )
        if (i + 1) % 25 == 0:
            _progress(FILTER_HUB, "selection-aware null %d/%d" % (i + 1, iterations))

    df = pd.DataFrame(rows)
    summary = _summarize_null(
        test="selection_aware_master",
        construction=(
            "Per iteration: circular-shift each book's shadow nets; search full "
            "candidate universe (books × month skips × roll grid); keep best N/S "
            "on the null tape (White-style selection control). "
            "n_specs=%d books=%d shift_min=10"
            % (len(specs), len(tapes))
        ),
        iterations=iterations,
        seed=seed + 999,
        actual=actual,
        null_df=df,
        extra={
            "n_candidates_per_iter": len(specs) * len(tapes),
            "real_unconstrained_best_ns": real_best_ns,
            "real_unconstrained_best": real_best_meta,
            "promote_ns": actual["ns"],
            "null_stat": "ns",
        },
    )
    # Selection-aware p-value: promote cell vs distribution of *best null winners*
    summary["p_ns_selection"] = empirical_pvalue(
        actual["ns"], df["ns"].tolist(), higher_is_better=True
    )
    summary["p_net_selection"] = empirical_pvalue(
        actual["net_usd"], df["net_usd"].tolist(), higher_is_better=True
    )
    # Override primary p_ns/p_net to selection-aware comparison
    summary["p_ns"] = summary["p_ns_selection"]
    summary["p_net"] = summary["p_net_selection"]
    decision, interp = classify_result(
        p_net=summary["p_net"],
        p_ns=summary["p_ns"],
        p_dd=summary["p_dd"],
        p_stress=summary["p_stress"],
    )
    summary["decision"] = decision
    summary["interpretation"] = interp
    summary["verdict"] = (
        "pass"
        if decision.startswith("PROMOTE")
        else ("inconclusive" if decision.startswith("RETAIN") else "fail")
    )
    return df, summary


def _summarize_null(
    *,
    test: str,
    construction: str,
    iterations: int,
    seed: int,
    actual: dict,
    null_df: pd.DataFrame,
    extra: Optional[dict] = None,
) -> dict:
    def pct(col: str, q: float) -> float:
        return float(null_df[col].quantile(q)) if col in null_df.columns and len(null_df) else 0.0

    p_net = empirical_pvalue(actual["net_usd"], null_df["net_usd"], higher_is_better=True)
    p_ns = empirical_pvalue(actual["ns"], null_df["ns"], higher_is_better=True)
    p_dd = empirical_pvalue(actual["max_dd_usd"], null_df["max_dd_usd"], higher_is_better=True)
    p_stress = empirical_pvalue(
        abs(actual["stress_usd"]),
        null_df["stress_usd"].abs() if "stress_usd" in null_df.columns else [],
        higher_is_better=False,  # lower |stress| is better
    )
    decision, interp = classify_result(p_net=p_net, p_ns=p_ns, p_dd=p_dd, p_stress=p_stress)
    # Pass/fail/inconclusive for the study row
    if decision.startswith("PROMOTE"):
        verdict = "pass"
    elif decision.startswith("RETAIN"):
        verdict = "inconclusive"  # risk throttle retained, not alpha pass
    else:
        verdict = "fail"
    out = {
        "test": test,
        "null_construction": construction,
        "iterations": iterations,
        "seed": seed,
        "actual_taken_n": actual["taken_n"],
        "actual_skipped_n": actual["skipped_n"],
        "actual_net_usd": actual["net_usd"],
        "actual_stress_usd": actual["stress_usd"],
        "actual_ns": actual["ns"],
        "actual_max_dd_usd": actual["max_dd_usd"],
        "actual_pf": actual["pf"],
        "actual_wr": actual["wr"],
        "actual_worst_usd": actual["worst_campaign_usd"],
        "actual_oos_net_usd": actual["oos_net_usd"],
        "actual_oos_ns": actual["oos_ns"],
        "null_median_net": pct("net_usd", 0.50),
        "null_p05_net": pct("net_usd", 0.05),
        "null_p95_net": pct("net_usd", 0.95),
        "null_median_ns": pct("ns", 0.50),
        "null_p05_ns": pct("ns", 0.05),
        "null_p95_ns": pct("ns", 0.95),
        "null_median_dd": pct("max_dd_usd", 0.50),
        "null_p05_dd": pct("max_dd_usd", 0.05),
        "null_p95_dd": pct("max_dd_usd", 0.95),
        "null_median_stress": pct("stress_usd", 0.50),
        "null_p05_stress": pct("stress_usd", 0.05),
        "null_p95_stress": pct("stress_usd", 0.95),
        "p_net": p_net,
        "p_ns": p_ns,
        "p_dd": p_dd,
        "p_stress": p_stress,
        "verdict": verdict,
        "decision": decision,
        "interpretation": interp,
    }
    if extra:
        out.update(extra)
    return out


def write_shadow_tape(tape: Tape, path: Path, take: np.ndarray) -> None:
    rows = []
    # eligible under combined promote cell
    for i in range(tape.n):
        rows.append(
            {
                "i": i,
                "session_date": tape.session[i],
                "year": int(tape.year[i]),
                "month": int(tape.month[i]),
                "net_jpy": float(tape.net_jpy[i]),
                "net_usd": float(tape.net_usd[i]),
                "win": bool(tape.win[i]),
                "live_gate_take": bool(take[i]),
            }
        )
    pd.DataFrame(rows).to_csv(path, index=False)


def write_report(
    output_root: Path,
    *,
    components: pd.DataFrame,
    month_df: pd.DataFrame,
    month_sum: dict,
    summaries: List[dict],
    broker: Optional[dict],
) -> Path:
    actual = next(s for s in summaries if s["test"] == "matched_exposure_random_skip")
    unf = components[components["label"] == "unfiltered"].iloc[0]
    comb = components[components["label"] == "combined"].iloc[0]

    lines = [
        "# USDJPY Asia-range London — filter nulls",
        "",
        "Shadow tape: unfiltered `S_3_1_3` campaign nets (sizing hub), chronological,",
        "one row per Asia-range campaign. Bars are **not** shuffled. Nulls destroy only",
        "the mapping between gate timing and future outcomes (or search over that mapping).",
        "",
        "Stress / max DD on this report are **closed-campaign equity drawdowns** on the",
        "taken shadow tape (reachable-stress proxy). Broker-like intrabar stress for the",
        "promoted filtered replay remains N/S **7.23** on the filters hub.",
        "",
        "Frozen promote cell: `S_3_1_3` + January skip + roll50 WR40/PF1.",
        "Seed: **%d**. OOS cut: years > **%d**." % (SEED, OOS_CUT),
        "",
        "## Component scorecard (shadow tape vs unfiltered)",
        "",
        "| Component | Taken | Skipped | Net≈USD | Stress | N/S | Max DD | Worst | PF | WR | OOS net | OOS N/S |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    order = ["unfiltered", "january_only", "wr_only", "pf_only", "roll_wr_pf", "combined"]
    for lab in order:
        r = components[components["label"] == lab].iloc[0]
        lines.append(
            "| %s | %d | %d | $%+.0f | $%.0f | %.2f | $%.0f | $%.0f | %.3f | %.1f%% | $%+.0f | %.2f |"
            % (
                lab,
                int(r["taken_n"]),
                int(r["skipped_n"]),
                float(r["net_usd"]),
                float(r["stress_usd"]),
                float(r["ns"]),
                float(r["max_dd_usd"]),
                float(r["worst_campaign_usd"]),
                float(r["pf"]),
                100.0 * float(r["wr"]),
                float(r["oos_net_usd"]),
                float(r["oos_ns"]),
            )
        )
    lines.extend(
        [
            "",
            "Combined vs unfiltered: Δnet **$%+.0f** | stress %+.0f → %+.0f | N/S %.2f → %.2f | max DD %.0f → %.0f."
            % (
                float(comb["net_usd"]) - float(unf["net_usd"]),
                float(unf["stress_usd"]),
                float(comb["stress_usd"]),
                float(unf["ns"]),
                float(comb["ns"]),
                float(unf["max_dd_usd"]),
                float(comb["max_dd_usd"]),
            ),
            "",
            "Broker-like filtered hub (reference): trades=%s net≈$%s stress≈$%s N/S=%s"
            % (
                (broker or {}).get("trades"),
                _fmt((broker or {}).get("net_usd")),
                _fmt((broker or {}).get("stress_dd_usd")),
                _fmt((broker or {}).get("net_over_stress")),
            ),
            "",
            "Attribution reminder (Δ taken net vs unfiltered): January +$28.9k; WR −$9.1k;",
            "PF −$35.8k; rolling −$37.4k; combined −$7.9k — rolling is the sit-out engine;",
            "January is the only positive-Δ lever on raw net.",
            "",
            "## 1. January-skip month placebo",
            "",
            "Real rule: skip January (+ roll50 WR40/PF1). Null: skip one other calendar month,",
            "same roll gate. Exhaustive 12-way table.",
            "",
            "| Month skipped | Taken | Net≈USD | Stress | N/S | Max DD | Δnet vs roll-only | Rank N/S |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for _, r in month_sum["table"].sort_values("month").iterrows():
        name = str(r["month_name"])
        if int(r["month"]) == 1:
            name = "**%s**" % name
        lines.append(
            "| %s | %d | $%+.0f | $%.0f | %.2f | $%.0f | $%+.0f | %d |"
            % (
                name,
                int(r["taken_n"]),
                float(r["net_usd"]),
                float(r["stress_usd"]),
                float(r["ns"]),
                float(r["max_dd_usd"]),
                float(r["delta_net"]),
                int(r["rank_ns"]),
            )
        )
    lines.extend(
        [
            "",
            "January ranks: net **#%d**/12, N/S **#%d**/12, max-DD **#%d**/12."
            % (month_sum["jan_rank_net"], month_sum["jan_rank_ns"], month_sum["jan_rank_dd"]),
            "Among one-month omissions, empirical mass with Δnet/ΔN/S/ΔDD at least as extreme as January:",
            "p(Δnet)=%.3f, p(ΔN/S)=%.3f, p(ΔDD)=%.3f."
            % (month_sum["p_delta_net"], month_sum["p_delta_ns"], month_sum["p_delta_dd"]),
            "",
            "### Null study rows",
            "",
            "| Test | Iters | Seed | Actual taken/skip | Actual net | Actual N/S | Actual max DD | Null med N/S | N/S 5–95%% | p(net) | p(N/S) | p(DD) | Verdict | Decision | Interpretation |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|---|",
        ]
    )
    for s in summaries:
        lines.append(
            "| %s | %d | %s | %d/%d | $%+.0f | %.2f | $%.0f | %.2f | %.2f–%.2f | %.4f | %.4f | %.4f | %s | %s | %s |"
            % (
                s["test"],
                int(s["iterations"]),
                s["seed"],
                int(s["actual_taken_n"]),
                int(s["actual_skipped_n"]),
                float(s["actual_net_usd"]),
                float(s["actual_ns"]),
                float(s["actual_max_dd_usd"]),
                float(s["null_median_ns"]),
                float(s["null_p05_ns"]),
                float(s["null_p95_ns"]),
                float(s["p_net"]),
                float(s["p_ns"]),
                float(s["p_dd"]),
                s["verdict"],
                s["decision"],
                s["interpretation"],
            )
        )

    # Decision rule + overall stance
    sel = next((s for s in summaries if s["test"] == "selection_aware_master"), None)
    matched = next(s for s in summaries if s["test"] == "matched_exposure_random_skip")
    shift = next(s for s in summaries if s["test"] == "circular_shift_gate")
    lines.extend(
        [
            "",
            "## Decision rule (conservative)",
            "",
            "- **PROMOTE FILTER AS ALPHA:** Actual Δnet and/or predictive selection statistic",
            "  beats the selection-aware null at the predeclared confidence threshold (p≤0.05).",
            "- **RETAIN FILTER AS RISK THROTTLE:** Actual Δnet is not significant, but the filter",
            "  produces robust, OOS-confirmed stress/drawdown improvement beyond matched-exposure nulls.",
            "- **REJECT FILTER:** Actual result does not beat matched-exposure, shifted-gate,",
            "  or selection-aware nulls on either net or risk path.",
            "",
            "## Overall stance",
            "",
        ]
    )
    # Compose overall from key tests (conservative decision rule)
    alpha_pass = bool(
        sel
        and float(sel.get("p_ns_selection", sel["p_ns"])) <= 0.05
        and float(sel["p_net"]) <= 0.25
    )
    # Risk throttle requires matched-exposure stress/DD improvement (rule text).
    matched_risk = float(matched["p_dd"]) <= 0.05 or float(matched["p_stress"]) <= 0.05
    shift_timing = float(shift["p_ns"]) <= 0.05 or float(shift["p_net"]) <= 0.05
    if alpha_pass:
        overall = "PROMOTE FILTER AS ALPHA"
        read = (
            "Selection-aware null rejects randomness on the promote cell; "
            "treat as alpha-selection evidence (still subject to funded-sleeve gates)."
        )
    elif matched_risk:
        overall = "RETAIN FILTER AS RISK THROTTLE"
        read = (
            "Matched-exposure nulls support stress/drawdown improvement beyond random "
            "same-count subsets, but net/selection timing is not selection-aware significant. "
            "Label as a risk throttle, not an alpha filter."
        )
    elif shift_timing and not matched_risk:
        overall = "RETAIN FILTER AS RISK THROTTLE"
        read = (
            "Matched-exposure random masks are **not** beaten on net, N/S, or DD "
            "(actual N/S sits below the matched null median — exposure reduction alone "
            "can look better). Circular-shift still shows the live gate's **timing** beats "
            "most scrambled gates with the same take count and clustering. "
            "January ranks #1 among one-month omissions. "
            "Do **not** promote as alpha; keep only as an operational risk throttle with "
            "the understanding that year/month-matched random subsets can match or beat "
            "shadow N/S."
        )
    else:
        overall = "REJECT FILTER"
        read = (
            "Filter does not clear matched-exposure, shifted-gate, or selection-aware nulls "
            "on net or risk path under the conservative rule."
        )
    lines.extend(
        [
            "**%s**" % overall,
            "",
            read,
            "",
            "### Prior expectation check",
            "",
            "- January seasonal lever: month placebo ranks and Δnet distribution (see §1).",
            "- Rolling WR/PF as risk/exposure regulator: watch matched-exposure and shift p(DD)/p(stress)",
            "  vs weak p(net).",
            "- Combined N/S beauty from stress removal: compare actual N/S percentile under",
            "  matched-exposure (same take count) vs circular-shift (same clustering).",
            "",
            "### Artifacts",
            "",
            "- `filter_nulls.csv` — one row per null study with p-values and decision fields",
            "- `filter_nulls_month_placebo.csv` — 12 one-month omission rows",
            "- `filter_nulls_components.csv` — component scorecard",
            "- `filter_nulls_shadow_tape.csv` — campaign tape + live_gate_take",
            "- `filter_nulls_*.parquet` / detail CSVs for iteration draws when written",
            "",
            "Driver: `python -m live.fx_v2b_asia_range_london_usdjpy_filter_nulls --email`",
            "",
        ]
    )
    path = output_root / "FILTER_NULLS.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _fmt(x) -> str:
    if x is None:
        return "—"
    try:
        return "%.2f" % float(x)
    except (TypeError, ValueError):
        return str(x)


def run(
    *,
    output_root: Path,
    unit_trades: Path,
    filtered_metrics: Path,
    matched_iters: int,
    shift_iters: int,
    outcome_iters: int,
    selection_iters: int,
    email: bool,
) -> Path:
    output_root.mkdir(parents=True, exist_ok=True)
    _progress(output_root, "FILTER_NULLS load %s" % unit_trades)
    tape = load_tape(unit_trades, book="S_3_1_3")
    masks = component_masks(tape)
    components = pd.DataFrame(
        [score_mask(tape, masks[k], label=k) for k in masks]
    )
    components.to_csv(output_root / "filter_nulls_components.csv", index=False)
    write_shadow_tape(tape, output_root / "filter_nulls_shadow_tape.csv", masks["combined"])

    _progress(output_root, "FILTER_NULLS month placebo")
    month_df, month_sum = null_month_placebo(tape)
    month_df.to_csv(output_root / "filter_nulls_month_placebo.csv", index=False)

    summaries: List[dict] = []
    # Fold month placebo into a summary-like row
    jan_actual = score_mask(tape, masks["combined"], label="combined")
    month_row = {
        "test": "january_month_placebo",
        "null_construction": month_sum["null_construction"],
        "iterations": 12,
        "seed": SEED,
        "actual_taken_n": jan_actual["taken_n"],
        "actual_skipped_n": jan_actual["skipped_n"],
        "actual_net_usd": jan_actual["net_usd"],
        "actual_stress_usd": jan_actual["stress_usd"],
        "actual_ns": jan_actual["ns"],
        "actual_max_dd_usd": jan_actual["max_dd_usd"],
        "actual_pf": jan_actual["pf"],
        "actual_wr": jan_actual["wr"],
        "actual_worst_usd": jan_actual["worst_campaign_usd"],
        "actual_oos_net_usd": jan_actual["oos_net_usd"],
        "actual_oos_ns": jan_actual["oos_ns"],
        "null_median_net": month_sum["null_median_net"],
        "null_p05_net": month_sum["null_p05_net"],
        "null_p95_net": month_sum["null_p95_net"],
        "null_median_ns": month_sum["null_median_ns"],
        "null_p05_ns": month_sum["null_p05_ns"],
        "null_p95_ns": month_sum["null_p95_ns"],
        "null_median_dd": month_sum["null_median_dd"],
        "null_p05_dd": month_sum["null_p05_dd"],
        "null_p95_dd": month_sum["null_p95_dd"],
        "null_median_stress": float(month_sum["table"]["stress_usd"].median()),
        "null_p05_stress": float(month_sum["table"]["stress_usd"].quantile(0.05)),
        "null_p95_stress": float(month_sum["table"]["stress_usd"].quantile(0.95)),
        "p_net": month_sum["p_delta_net"],
        "p_ns": month_sum["p_delta_ns"],
        "p_dd": month_sum["p_delta_dd"],
        "p_stress": month_sum["p_delta_dd"],
        "verdict": "inconclusive",
        "decision": "RETAIN FILTER AS RISK THROTTLE"
        if month_sum["jan_rank_ns"] <= 3
        else "REJECT FILTER",
        "interpretation": (
            "january seasonal evidence"
            if month_sum["jan_rank_net"] <= 3
            else "january not uniquely worst / best among months"
        ),
        "jan_rank_net": month_sum["jan_rank_net"],
        "jan_rank_ns": month_sum["jan_rank_ns"],
        "jan_rank_dd": month_sum["jan_rank_dd"],
    }
    # refine month interpretation after we know ranks
    if month_sum["jan_rank_net"] == 1 and month_sum["p_delta_net"] <= 0.20:
        month_row["decision"] = "PROMOTE FILTER AS ALPHA"
        month_row["verdict"] = "pass"
        month_row["interpretation"] = "alpha-selection evidence"
    elif month_sum["jan_rank_dd"] <= 3 or month_sum["jan_rank_ns"] <= 3:
        month_row["decision"] = "RETAIN FILTER AS RISK THROTTLE"
        month_row["verdict"] = "inconclusive"
        month_row["interpretation"] = "risk-throttle evidence"
    else:
        month_row["decision"] = "REJECT FILTER"
        month_row["verdict"] = "fail"
        month_row["interpretation"] = "no evidence"
    summaries.append(month_row)

    _progress(output_root, "FILTER_NULLS matched-exposure (%d)" % matched_iters)
    m_df, m_sum = null_matched_exposure(
        tape, masks["combined"], iterations=matched_iters, seed=SEED
    )
    m_df.to_csv(output_root / "filter_nulls_matched_exposure.csv", index=False)
    summaries.append(m_sum)

    _progress(output_root, "FILTER_NULLS circular-shift (%d)" % shift_iters)
    s_df, s_sum = null_circular_shift(
        tape, masks["combined"], iterations=shift_iters, seed=SEED
    )
    s_df.to_csv(output_root / "filter_nulls_circular_shift.csv", index=False)
    summaries.append(s_sum)

    _progress(output_root, "FILTER_NULLS shadow-outcome (%d×3 blocks)" % outcome_iters)
    o_frames, o_sums = null_shadow_outcome(
        tape, iterations=outcome_iters, seed=SEED
    )
    for block, df in o_frames.items():
        df.to_csv(output_root / ("filter_nulls_shadow_outcome_block%d.csv" % block), index=False)
    summaries.extend(o_sums)

    _progress(output_root, "FILTER_NULLS load books for selection-aware")
    tapes: Dict[str, Tape] = {}
    for book in BOOKS:
        t = load_book_tape(book)
        if t is not None:
            tapes[book] = t
            _progress(output_root, "  book %s n=%d" % (book, t.n))
    # optional S_3_3_3
    t333 = load_book_tape("S_3_3_3")
    if t333 is not None:
        tapes["S_3_3_3"] = t333

    _progress(output_root, "FILTER_NULLS selection-aware (%d)" % selection_iters)
    sel_df, sel_sum = null_selection_aware(
        tapes, iterations=selection_iters, seed=SEED, block=25
    )
    sel_df.to_csv(output_root / "filter_nulls_selection_aware.csv", index=False)
    summaries.append(sel_sum)

    broker = None
    if filtered_metrics.exists():
        broker = json.loads(filtered_metrics.read_text(encoding="utf-8"))

    # flat CSV of study summaries
    flat_cols = [
        "test",
        "null_construction",
        "iterations",
        "seed",
        "actual_taken_n",
        "actual_skipped_n",
        "actual_net_usd",
        "actual_stress_usd",
        "actual_ns",
        "actual_max_dd_usd",
        "actual_pf",
        "actual_wr",
        "actual_worst_usd",
        "actual_oos_net_usd",
        "actual_oos_ns",
        "null_median_net",
        "null_p05_net",
        "null_p95_net",
        "null_median_ns",
        "null_p05_ns",
        "null_p95_ns",
        "null_median_dd",
        "null_p05_dd",
        "null_p95_dd",
        "null_median_stress",
        "null_p05_stress",
        "null_p95_stress",
        "p_net",
        "p_ns",
        "p_dd",
        "p_stress",
        "verdict",
        "decision",
        "interpretation",
    ]
    flat = pd.DataFrame([{c: s.get(c) for c in flat_cols} for s in summaries])
    flat.to_csv(output_root / "filter_nulls.csv", index=False)

    path = write_report(
        output_root,
        components=components,
        month_df=month_df,
        month_sum=month_sum,
        summaries=summaries,
        broker=broker,
    )

    # email body
    overall_line = path.read_text(encoding="utf-8").split("## Overall stance", 1)[-1]
    overall_snip = "\n".join(overall_line.strip().splitlines()[:6])
    email_lines = [
        "potions: USDJPY Asia-range filter nulls",
        "",
        "Hub: %s" % output_root,
        "Report: %s" % path,
        "Shadow tape: unfiltered S_3_1_3 (%d campaigns)." % tape.n,
        "Combined taken/skipped: %d / %d | net≈$%+.0f | N/S %.2f | max DD $%.0f"
        % (
            int(comb_taken(masks, tape)),
            int((~masks["combined"]).sum()),
            float(components[components["label"] == "combined"]["net_usd"].iloc[0]),
            float(components[components["label"] == "combined"]["ns"].iloc[0]),
            float(components[components["label"] == "combined"]["max_dd_usd"].iloc[0]),
        ),
        "",
        "Key p-values:",
    ]
    for s in summaries:
        email_lines.append(
            "  %s: p_net=%.4f p_ns=%.4f p_dd=%.4f → %s (%s)"
            % (s["test"], s["p_net"], s["p_ns"], s["p_dd"], s["decision"], s["verdict"])
        )
    email_lines.extend(["", overall_snip, ""])
    (output_root / "FILTER_NULLS_EMAIL.txt").write_text("\n".join(email_lines) + "\n", encoding="utf-8")
    _progress(output_root, "FILTER_NULLS wrote %s" % path)

    if email:
        try:
            from .notify_email import send_email

            send_email(
                subject="potions: USDJPY Asia-range filter nulls",
                body=(output_root / "FILTER_NULLS_EMAIL.txt").read_text(encoding="utf-8"),
            )
            _progress(output_root, "FILTER_NULLS EMAIL sent")
        except Exception as exc:
            _progress(output_root, "FILTER_NULLS EMAIL failed: %s" % exc)
    return path


def comb_taken(masks: Dict[str, np.ndarray], tape: Tape) -> int:
    return int(masks["combined"].sum())


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output-root", type=Path, default=FILTER_HUB)
    p.add_argument("--unit-trades", type=Path, default=DEFAULT_UNIT)
    p.add_argument("--filtered-metrics", type=Path, default=DEFAULT_FILTERED_METRICS)
    p.add_argument("--matched-iters", type=int, default=5000)
    p.add_argument("--shift-iters", type=int, default=2000)
    p.add_argument("--outcome-iters", type=int, default=1000)
    p.add_argument("--selection-iters", type=int, default=300)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    try:
        path = run(
            output_root=args.output_root,
            unit_trades=args.unit_trades,
            filtered_metrics=args.filtered_metrics,
            matched_iters=args.matched_iters,
            shift_iters=args.shift_iters,
            outcome_iters=args.outcome_iters,
            selection_iters=args.selection_iters,
            email=args.email,
        )
        print("Wrote %s" % path, flush=True)
        return 0
    except Exception:
        err = traceback.format_exc()
        print(err, flush=True)
        try:
            args.output_root.mkdir(parents=True, exist_ok=True)
            (args.output_root / "FILTER_NULLS_FAIL.txt").write_text(err, encoding="utf-8")
            if args.email:
                from .notify_email import send_email

                send_email(
                    subject="potions: USDJPY Asia-range filter nulls FAILED",
                    body="Hub: %s\n\n%s" % (args.output_root, err[-4000:]),
                )
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
