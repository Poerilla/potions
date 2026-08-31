"""Central ledger for every potions research / broker-like / deep-check run.

Append-only CSV: ``data/validation/broker_run_ledger.csv``

Use from drivers, pandas studies, and skills::

    from live.run_ledger import begin_run, complete_run, log_run

    run_id = begin_run(
        run_class="broker_like",
        variant_slug="nq_quarterly_range_breakout",
        instrument="NQ",
        hub_path="live/state/nq_quarterly_range_breakout_v2_honest_chk",
    )
    # ... replay ...
    complete_run(run_id, net_usd=..., stress_dd_usd=..., ns=..., ...)

Or one-shot after artifacts exist::

    log_run(
        run_class="broker_like",
        variant_slug="...",
        instrument="NQ",
        hub_path=hub,
        net_usd=...,
        stress_dd_usd=...,
        ns=...,
        equity_curve_path=hub / "audits" / "..." / "equity_curve.csv",
        yearly_csv_path=hub / "deep_check" / "..." / "yearly_breakdown.csv",
    )

``parmar`` is stored as Calmar-like (terminal / |max DD|); same number as ``calmar``
when computed from an equity curve.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Union

from .models import new_id, utc_now_iso
from .replay_manifest import git_state

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = REPO_ROOT / "data" / "validation" / "broker_run_ledger.csv"

COLUMNS: Sequence[str] = (
    "run_id",
    "ts_start",
    "ts_end",
    "status",
    "run_class",
    "variant_slug",
    "instrument",
    "hub_path",
    "engine",
    "replay_start",
    "replay_end",
    "net_usd",
    "stress_dd_usd",
    "close_mtm_dd_usd",
    "ns",
    "sharpe",
    "sortino",
    "calmar",
    "parmar",
    "trades",
    "units",
    "avg_yearly_net",
    "avg_yearly_stress",
    "avg_yearly_ns",
    "n_years",
    "parent_run_id",
    "dsr_trial_id",
    "git_commit",
    "command",
    "meta_json",
    "notes",
)

RUN_CLASSES = (
    "broker_like",
    "pandas",
    "deep_check",
    "walk_forward",
    "sweep",
    "audit",
    "sidecar",
    "ha",  # high-probability condition mill (profile / overlay / nulls)
    "other",
)

Number = Union[int, float]


def ledger_path(path: Optional[Path] = None) -> Path:
    env = os.environ.get("POTIONS_RUN_LEDGER", "").strip()
    if path is not None:
        return Path(path)
    if env:
        return Path(env)
    return DEFAULT_LEDGER


def _ensure_ledger(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        with path.open("w", encoding="utf-8", newline="") as fh:
            fh.write("# potions broker/research run ledger; schema_version=1.0\n")
            w = csv.DictWriter(fh, fieldnames=list(COLUMNS))
            w.writeheader()


def _fmt(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        s = "%.10g" % value
        return s
    return str(value)


def _empty_row() -> Dict[str, str]:
    return {c: "" for c in COLUMNS}


def _read_all(path: Path) -> list:
    if not path.exists():
        return []
    rows = []
    with path.open(encoding="utf-8", newline="") as fh:
        lines = [ln for ln in fh if not ln.startswith("#")]
    if not lines:
        return []
    from io import StringIO

    reader = csv.DictReader(StringIO("".join(lines)))
    for raw in reader:
        row = _empty_row()
        for k, v in (raw or {}).items():
            if k in row:
                row[k] = "" if v is None else str(v)
        if row.get("run_id"):
            rows.append(row)
    return rows


def _write_all(path: Path, rows: Iterable) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write("# potions broker/research run ledger; schema_version=1.0\n")
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), extrasaction="ignore")
        w.writeheader()
        for raw in rows:
            out = _empty_row()
            for c in COLUMNS:
                out[c] = _fmt(raw.get(c, ""))
            w.writerow(out)


def _append_row(path: Path, row: Mapping) -> None:
    _ensure_ledger(path)
    with path.open("a", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(COLUMNS), extrasaction="ignore")
        out = _empty_row()
        for c in COLUMNS:
            out[c] = _fmt(row.get(c, ""))
        w.writerow(out)


def _update_row(path: Path, run_id: str, updates: Mapping) -> bool:
    rows = _read_all(path)
    found = False
    out_rows = []
    for row in rows:
        if row.get("run_id") == run_id:
            found = True
            merged = dict(row)
            for k, v in updates.items():
                if k in merged and v is not None:
                    merged[k] = _fmt(v)
            out_rows.append(merged)
        else:
            out_rows.append(row)
    if found:
        _write_all(path, out_rows)
    return found


def _rel_hub(hub_path) -> str:
    if hub_path is None or hub_path == "":
        return ""
    p = Path(hub_path)
    try:
        return str(p.resolve().relative_to(REPO_ROOT.resolve()))
    except Exception:
        return str(hub_path)


def _git_commit() -> str:
    try:
        return str(git_state(REPO_ROOT).get("commit") or "")
    except Exception:
        return ""


def begin_run(
    *,
    run_class: str,
    variant_slug: str,
    instrument: str = "",
    hub_path=None,
    engine: str = "",
    parent_run_id: str = "",
    dsr_trial_id: str = "",
    notes: str = "",
    meta=None,
    command=None,
    run_id=None,
    ledger=None,
) -> str:
    """Register a RUNNING row; returns run_id. Call complete_run / fail_run later."""
    rid = run_id or new_id("brl")
    rc = str(run_class or "other").strip().lower() or "other"
    if rc not in RUN_CLASSES:
        rc = "other"
    row = _empty_row()
    row.update(
        {
            "run_id": rid,
            "ts_start": utc_now_iso(),
            "status": "RUNNING",
            "run_class": rc,
            "variant_slug": str(variant_slug or ""),
            "instrument": str(instrument or "").upper(),
            "hub_path": _rel_hub(hub_path),
            "engine": str(engine or ("paper_broker" if rc == "broker_like" else rc)),
            "parent_run_id": str(parent_run_id or ""),
            "dsr_trial_id": str(dsr_trial_id or ""),
            "git_commit": _git_commit(),
            "command": " ".join(command) if command is not None else " ".join(sys.argv),
            "meta_json": json.dumps(dict(meta or {}), sort_keys=True, default=str),
            "notes": str(notes or ""),
        }
    )
    _append_row(ledger_path(ledger), row)
    return rid


def complete_run(
    run_id: str,
    *,
    net_usd=None,
    stress_dd_usd=None,
    close_mtm_dd_usd=None,
    ns=None,
    sharpe=None,
    sortino=None,
    calmar=None,
    parmar=None,
    trades=None,
    units=None,
    avg_yearly_net=None,
    avg_yearly_stress=None,
    avg_yearly_ns=None,
    n_years=None,
    replay_start: str = "",
    replay_end: str = "",
    hub_path=None,
    notes: str = "",
    meta=None,
    equity_curve_path=None,
    yearly_csv_path=None,
    status: str = "COMPLETE",
    ledger=None,
) -> bool:
    """Fill metrics on an existing RUNNING row."""
    path = ledger_path(ledger)
    derived = {}
    if equity_curve_path:
        derived.update(metrics_from_equity_curve(Path(equity_curve_path)))
    if yearly_csv_path:
        derived.update(metrics_from_yearly_csv(Path(yearly_csv_path)))

    def pick(name, explicit):
        if explicit is not None and explicit != "":
            return explicit
        return derived.get(name)

    ns_val = pick("ns", ns)
    if ns_val in (None, "") and net_usd is not None and stress_dd_usd not in (None, ""):
        try:
            s = float(stress_dd_usd)
            n = float(net_usd)
            ns_val = (n / abs(s)) if abs(s) > 1e-12 else 0.0
        except (TypeError, ValueError):
            pass

    cal = pick("calmar", calmar)
    par = pick("parmar", parmar)
    if par in (None, "") and cal not in (None, ""):
        par = cal
    if cal in (None, "") and par not in (None, ""):
        cal = par

    updates = {
        "ts_end": utc_now_iso(),
        "status": status,
        "net_usd": pick("net_usd", net_usd),
        "stress_dd_usd": pick("stress_dd_usd", stress_dd_usd),
        "close_mtm_dd_usd": pick("close_mtm_dd_usd", close_mtm_dd_usd),
        "ns": ns_val,
        "sharpe": pick("sharpe", sharpe),
        "sortino": pick("sortino", sortino),
        "calmar": cal,
        "parmar": par,
        "trades": pick("trades", trades),
        "units": pick("units", units),
        "avg_yearly_net": pick("avg_yearly_net", avg_yearly_net),
        "avg_yearly_stress": pick("avg_yearly_stress", avg_yearly_stress),
        "avg_yearly_ns": pick("avg_yearly_ns", avg_yearly_ns),
        "n_years": pick("n_years", n_years),
        "replay_start": replay_start or derived.get("replay_start", ""),
        "replay_end": replay_end or derived.get("replay_end", ""),
    }
    if hub_path:
        updates["hub_path"] = _rel_hub(hub_path)
    if notes:
        updates["notes"] = notes
    if meta:
        updates["meta_json"] = json.dumps(dict(meta), sort_keys=True, default=str)

    if not _update_row(path, run_id, updates):
        row = _empty_row()
        row.update(
            {
                "run_id": run_id,
                "ts_start": updates["ts_end"],
                "run_class": "other",
                "variant_slug": "",
                "git_commit": _git_commit(),
                "command": " ".join(sys.argv),
            }
        )
        row.update({k: _fmt(v) for k, v in updates.items()})
        _append_row(path, row)
        return False
    return True


def fail_run(run_id: str, *, notes: str = "", meta=None, ledger=None) -> bool:
    return complete_run(run_id, status="FAILED", notes=notes, meta=meta, ledger=ledger)


_METRIC_KEYS = {
    "net_usd", "stress_dd_usd", "close_mtm_dd_usd", "ns", "sharpe", "sortino",
    "calmar", "parmar", "trades", "units", "avg_yearly_net", "avg_yearly_stress",
    "avg_yearly_ns", "n_years", "replay_start", "replay_end",
}


def log_run(
    *,
    run_class: str,
    variant_slug: str,
    instrument: str = "",
    hub_path=None,
    engine: str = "",
    parent_run_id: str = "",
    dsr_trial_id: str = "",
    notes: str = "",
    meta=None,
    command=None,
    equity_curve_path=None,
    yearly_csv_path=None,
    ledger=None,
    **metrics
) -> str:
    """One-shot: begin + complete. Returns run_id."""
    rid = begin_run(
        run_class=run_class,
        variant_slug=variant_slug,
        instrument=instrument,
        hub_path=hub_path,
        engine=engine,
        parent_run_id=parent_run_id,
        dsr_trial_id=dsr_trial_id,
        notes=notes,
        meta=meta,
        command=command,
        ledger=ledger,
    )
    complete_run(
        rid,
        hub_path=hub_path,
        notes=notes,
        meta=meta,
        equity_curve_path=equity_curve_path,
        yearly_csv_path=yearly_csv_path,
        ledger=ledger,
        **{k: v for k, v in metrics.items() if k in _METRIC_KEYS},
    )
    return rid


def metrics_from_audit(audit) -> Dict[str, Any]:
    net = float(getattr(audit, "net_usd", 0.0) or 0.0)
    stress = float(getattr(audit, "intrabar_mtm_dd_usd", 0.0) or 0.0)
    closed = float(getattr(audit, "close_mtm_dd_usd", 0.0) or 0.0)
    ns = (net / abs(stress)) if abs(stress) > 1e-12 else 0.0
    return {
        "net_usd": net,
        "stress_dd_usd": stress,
        "close_mtm_dd_usd": closed,
        "ns": ns,
        "trades": int(getattr(audit, "trades", 0) or 0),
        "units": int(getattr(audit, "units", 0) or 0),
        "replay_start": str(getattr(audit, "start_ts", "") or ""),
        "replay_end": str(getattr(audit, "end_ts", "") or ""),
        "instrument": str(getattr(audit, "instrument", "") or "").upper(),
        "variant_slug": str(getattr(audit, "slug", "") or ""),
    }


def metrics_from_summary_csv(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        return {}
    r = rows[0]
    out = {}
    for src, dst in (
        ("net_usd", "net_usd"),
        ("stress_dd", "stress_dd_usd"),
        ("stress_dd_usd", "stress_dd_usd"),
        ("closed_dd", "close_mtm_dd_usd"),
        ("close_mtm_dd_usd", "close_mtm_dd_usd"),
        ("ns", "ns"),
        ("trades", "trades"),
        ("units", "units"),
        ("slug", "variant_slug"),
        ("instrument", "instrument"),
    ):
        if src in r and r[src] not in (None, ""):
            out[dst] = r[src]
    try:
        if "ns" not in out and "net_usd" in out and "stress_dd_usd" in out:
            n = float(out["net_usd"])
            s = float(out["stress_dd_usd"])
            out["ns"] = n / abs(s) if abs(s) > 1e-12 else 0.0
    except (TypeError, ValueError):
        pass
    return out


def metrics_from_yearly_csv(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import pandas as pd
    except ImportError:
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    out = {"n_years": int(len(df))}
    if "net_usd" in df.columns:
        out["avg_yearly_net"] = float(pd.to_numeric(df["net_usd"], errors="coerce").mean())
    if "stress_dd_usd" in df.columns:
        out["avg_yearly_stress"] = float(pd.to_numeric(df["stress_dd_usd"], errors="coerce").mean())
    if "net_over_stress" in df.columns:
        out["avg_yearly_ns"] = float(pd.to_numeric(df["net_over_stress"], errors="coerce").mean())
    elif "net_usd" in df.columns and "stress_dd_usd" in df.columns:
        nets = pd.to_numeric(df["net_usd"], errors="coerce")
        stresses = pd.to_numeric(df["stress_dd_usd"], errors="coerce").abs().replace(0, float("nan"))
        out["avg_yearly_ns"] = float((nets / stresses).mean())
    return out


def metrics_from_equity_curve(path: Path) -> Dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {}
    try:
        import pandas as pd
    except ImportError:
        return {}
    df = pd.read_csv(path)
    if df.empty:
        return {}
    col = None
    for c in (
        "close_equity_usd",
        "equity_usd",
        "intrabar_stress_equity_usd",
        "close_mtm_usd",
        "close_equity_points",
        "intrabar_stress_points",
    ):
        if c in df.columns:
            col = c
            break
    if col is None:
        return {}
    eq = pd.to_numeric(df[col], errors="coerce").dropna()
    if len(eq) < 3:
        return {}
    rets = eq.diff().dropna()
    mu = float(rets.mean())
    sigma = float(rets.std(ddof=1)) if len(rets) > 1 else 0.0
    downside = rets[rets < 0]
    dsigma = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    ann = math.sqrt(252.0)
    sharpe = (mu / sigma) * ann if sigma > 1e-12 else 0.0
    sortino = (mu / dsigma) * ann if dsigma > 1e-12 else 0.0
    peak = eq.cummax()
    dd = eq - peak
    max_dd = float(dd.min())
    terminal = float(eq.iloc[-1] - eq.iloc[0])
    calmar = (terminal / abs(max_dd)) if abs(max_dd) > 1e-12 else 0.0
    out = {
        "sharpe": sharpe,
        "sortino": sortino,
        "calmar": calmar,
        "parmar": calmar,
    }
    if "ts" in df.columns:
        ts = df["ts"].astype(str)
        out["replay_start"] = str(ts.iloc[0])
        out["replay_end"] = str(ts.iloc[-1])
    return out


def log_from_hub(
    hub_path: Path,
    *,
    run_class: str = "broker_like",
    variant_slug: str = "",
    instrument: str = "",
    notes: str = "",
    meta=None,
    dsr_trial_id: str = "",
    parent_run_id: str = "",
    ledger=None,
) -> str:
    hub = Path(hub_path)
    summary = hub / "summary.csv"
    metrics = {}
    if summary.exists():
        metrics.update(metrics_from_summary_csv(summary))
    slug = variant_slug or str(metrics.get("variant_slug") or hub.name)
    inst = instrument or str(metrics.get("instrument") or "")
    eq = None
    audits = hub / "audits"
    if audits.exists():
        cands = sorted(audits.rglob("equity_curve.csv"))
        if cands:
            eq = cands[0]
    yearly = None
    if (hub / "yearly_breakdown.csv").exists():
        yearly = hub / "yearly_breakdown.csv"
    else:
        deep = hub / "deep_check"
        if deep.exists():
            yc = sorted(deep.rglob("yearly_breakdown.csv"))
            if yc:
                yearly = yc[0]
    # Deep-check hubs: derive net/trades from campaigns if no summary.csv
    camps = hub / "campaigns_robustness.csv"
    if "net_usd" not in metrics and camps.exists():
        try:
            import pandas as pd
            cdf = pd.read_csv(camps)
            if "net_usd" in cdf.columns:
                metrics["net_usd"] = float(pd.to_numeric(cdf["net_usd"], errors="coerce").sum())
                metrics["trades"] = int(len(cdf))
            if "closed_dd_usd" in cdf.columns:
                metrics["close_mtm_dd_usd"] = -float(
                    pd.to_numeric(cdf["closed_dd_usd"], errors="coerce").abs().max()
                )
        except Exception:
            pass
    if yearly is not None and "stress_dd_usd" not in metrics:
        try:
            import pandas as pd
            ydf = pd.read_csv(yearly)
            if "stress_dd_usd" in ydf.columns:
                metrics["stress_dd_usd"] = -float(
                    pd.to_numeric(ydf["stress_dd_usd"], errors="coerce").abs().sum()
                )
            if "net_usd" in metrics and "stress_dd_usd" in metrics:
                n = float(metrics["net_usd"])
                s = float(metrics["stress_dd_usd"])
                metrics["ns"] = n / abs(s) if abs(s) > 1e-12 else 0.0
        except Exception:
            pass
    return log_run(
        run_class=run_class,
        variant_slug=slug,
        instrument=inst,
        hub_path=hub,
        notes=notes,
        meta=meta,
        dsr_trial_id=dsr_trial_id,
        parent_run_id=parent_run_id,
        equity_curve_path=eq,
        yearly_csv_path=yearly,
        ledger=ledger,
        **{k: v for k, v in metrics.items() if k in _METRIC_KEYS},
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p_log = sub.add_parser("log-hub", help="Harvest a finished hub into the ledger")
    p_log.add_argument("--hub", type=Path, required=True)
    p_log.add_argument("--run-class", default="broker_like")
    p_log.add_argument("--variant-slug", default="")
    p_log.add_argument("--instrument", default="")
    p_log.add_argument("--notes", default="")
    p_log.add_argument("--dsr-trial-id", default="")
    p_log.add_argument("--ledger", type=Path, default=None)

    p_show = sub.add_parser("tail", help="Show last N ledger rows")
    p_show.add_argument("-n", type=int, default=10)
    p_show.add_argument("--ledger", type=Path, default=None)

    args = ap.parse_args(list(argv) if argv is not None else None)
    if args.cmd == "log-hub":
        rid = log_from_hub(
            args.hub,
            run_class=args.run_class,
            variant_slug=args.variant_slug,
            instrument=args.instrument,
            notes=args.notes,
            dsr_trial_id=args.dsr_trial_id,
            ledger=args.ledger,
        )
        print(rid)
        return 0
    if args.cmd == "tail":
        rows = _read_all(ledger_path(args.ledger))[-int(args.n) :]
        w = csv.DictWriter(sys.stdout, fieldnames=list(COLUMNS), extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
