"""ES quarterly breakout — causal Monthly OR **up** gated broker-like.

Plugin gate ``require_mor_dirs=["mor_up"]`` (first-3-session Monthly OR; ready
after 3rd daily close). Stricter than post-filtering the ungated tape by
``mor_dir``. Compares to the ungated baseline hub.

HP coupon (diagnostic, NOT VALIDATED @1.25×):
  Monthly OR up · n=26 · +12.9pp · +$10.9k · ΔN/S +1.34 · p_master 0.26

Usage::

  export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
  python -m live.es_quarterly_breakout_mor_up_broker --email
"""

from __future__ import annotations

import argparse
import csv
import json
import traceback
from pathlib import Path
from typing import Optional, Sequence

from live.notify_email import send_email
from live.quarterly_range_breakout_broker import run as run_broker

REPO = Path(__file__).resolve().parents[1]
HUB = REPO / "live/state/es_quarterly_breakout_mor_up_broker"
BASELINE_HUB = REPO / "live/state/es_quarterly_range_breakout_broker"
DAILY = REPO / "es/es_daily.csv"
HP_NOTE = (
    "HP coupon: Monthly OR up n=26 +12.9pp +$10.9k NOT VALIDATED "
    "(best ΔN/S +1.34, p_master 0.26)"
)


def _progress(msg: str) -> None:
    HUB.mkdir(parents=True, exist_ok=True)
    line = msg.rstrip() + "\n"
    print(line, end="", flush=True)
    with (HUB / "PROGRESS.log").open("a", encoding="utf-8") as fh:
        fh.write(line)


def _read_summary(hub: Path) -> dict:
    path = hub / "summary.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    return rows[0] if rows else {}


def main(argv: Optional[Sequence[str]] = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--daily", type=Path, default=DAILY)
    p.add_argument("--output-root", type=Path, default=HUB)
    p.add_argument("--email", action="store_true")
    args = p.parse_args(argv)
    out = Path(args.output_root)
    out.mkdir(parents=True, exist_ok=True)
    _progress("START ES QB causal broker-like require_mor_dirs=mor_up")
    try:
        rc = run_broker(
            output_root=out,
            daily_path=Path(args.daily),
            instrument="ES",
            force=True,
            slippage_ticks=1.0,
            email=False,
            allowed_sides=["long", "short"],
            entry_qty=8,
            require_mor_dirs=["mor_up"],
        )
        if rc != 0:
            raise RuntimeError("broker returned %s" % rc)
        gated = _read_summary(out)
        base = _read_summary(BASELINE_HUB)
        g_net = float(gated.get("net_usd") or 0)
        g_stress = float(gated.get("stress_dd") or 0)
        g_ns = float(gated.get("ns") or 0)
        g_tr = int(float(gated.get("trades") or 0))
        b_net = float(base.get("net_usd") or 0)
        b_stress = float(base.get("stress_dd") or 0)
        b_ns = float(base.get("ns") or 0)
        b_tr = int(float(base.get("trades") or 0))
        stance = (
            "research — plugin-gated mor_up book; HP size-up stays NOT VALIDATED"
        )
        compare = [
            "# ES quarterly breakout — Monthly OR **up** causal broker-like",
            "",
            HP_NOTE,
            "",
            "Plugin gate: `require_mor_dirs=[\"mor_up\"]` on `quarterly_range_breakout` "
            "(causal first-3 Monthly OR; next-open fills via `live_after_ts`).",
            "",
            "## Comparison",
            "",
            "| Book | Trades | Net | Stress DD | N/S |",
            "|---|---:|---:|---:|---:|",
            "| Baseline (ungated) | %d | $%s | $%s | %.2f |"
            % (b_tr, f"{b_net:,.2f}", f"{b_stress:,.2f}", b_ns),
            "| **mor_up gated** | **%d** | **$%s** | **$%s** | **%.2f** |"
            % (g_tr, f"{g_net:,.2f}", f"{g_stress:,.2f}", g_ns),
            "",
            "## Stance",
            "",
            stance,
            "",
            "## Hubs",
            "",
            "- Gated: `live/state/es_quarterly_breakout_mor_up_broker/`",
            "- Baseline: `live/state/es_quarterly_range_breakout_broker/`",
            "- HP nulls: `live/state/es_quarterly_breakout_hp_nulls/`",
            "",
        ]
        (out / "COMPARE.md").write_text("\n".join(compare), encoding="utf-8")
        # Prefer COMPARE as the human summary when gated.
        summary_path = out / "SUMMARY.md"
        if summary_path.exists():
            body = summary_path.read_text(encoding="utf-8")
            summary_path.write_text(
                "\n".join(compare) + "\n---\n\n" + body, encoding="utf-8"
            )
        else:
            summary_path.write_text("\n".join(compare), encoding="utf-8")
        email_body = "\n".join(
            [
                "ES quarterly breakout — Monthly OR up causal broker-like complete.",
                "",
                HP_NOTE,
                "",
                "Hub: %s" % out,
                "Gate: require_mor_dirs=mor_up (plugin, causal)",
                "",
                "Baseline: trades=%d net=$%.2f stress=$%.2f N/S=%.2f"
                % (b_tr, b_net, b_stress, b_ns),
                "mor_up gated: trades=%d net=$%.2f stress=$%.2f N/S=%.2f"
                % (g_tr, g_net, g_stress, g_ns),
                "",
                "Stance: %s" % stance,
                "",
                "COMPARE: %s" % (out / "COMPARE.md"),
            ]
        )
        (out / "EMAIL.txt").write_text(email_body + "\n", encoding="utf-8")
        (out / "RUN_COMPLETE.json").write_text(
            json.dumps(
                {
                    "study": "es_quarterly_breakout_mor_up_broker",
                    "gated": gated,
                    "baseline": base,
                    "stance": stance,
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        _progress(
            "DONE gated trades=%d net=$%.2f N/S=%.2f (baseline N/S=%.2f)"
            % (g_tr, g_net, g_ns, b_ns)
        )
        if args.email:
            send_email(
                subject="potions: ES QB mor_up broker-like (N/S %.2f, n=%d)"
                % (g_ns, g_tr),
                body=email_body,
            )
        return 0
    except Exception as exc:
        _progress("FAILED: %s" % exc)
        tb = traceback.format_exc()
        (out / "FAILED.txt").write_text(tb, encoding="utf-8")
        if args.email:
            try:
                send_email(
                    subject="potions: ES QB mor_up broker-like FAILED",
                    body="Hub: %s\n\n%s\n" % (out, tb[-4000:]),
                )
            except Exception:
                pass
        raise


if __name__ == "__main__":
    raise SystemExit(main())
