#!/usr/bin/env python3
"""Morning digest for risk-guard shadow + MAE hubs."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
import sys
sys.path.insert(0, "/home/tester/hsm")
sys.path.insert(0, "/home/tester/hsm/potions/v20-python/src")
from live.notify_email import send_email

REPO = Path("/home/tester/hsm/potions")
RG = REPO / "live/state/risk_guard_shadow"
MAE = REPO / "live/state/oanda_winner_mae_carry"

def main() -> int:
    pid_path = RG / "pidfile"
    pid = pid_path.read_text().strip() if pid_path.exists() else "?"
    alive = False
    try:
        os.kill(int(pid), 0)
        alive = True
    except Exception:
        pass
    status = json.loads((RG / "STATUS.json").read_text()) if (RG / "STATUS.json").exists() else {}
    prog = (RG / "PROGRESS.log").read_text().strip().splitlines() if (RG / "PROGRESS.log").exists() else []
    last = prog[-1] if prog else "(none)"
    polls = 0
    breaches = 0
    if (RG / "poll_status.csv").exists():
        import csv
        with (RG / "poll_status.csv").open() as fh:
            for r in csv.DictReader(fh):
                polls += 1
                if str(r.get("breach", "")).lower() in ("1", "true", "True"):
                    breaches += 1
    actions_n = 0
    if (RG / "actions.csv").exists():
        with (RG / "actions.csv").open() as fh:
            actions_n = max(0, sum(1 for _ in fh) - 1)
    mae_txt = (MAE / "EMAIL.txt").read_text() if (MAE / "EMAIL.txt").exists() else "MAE hub missing"
    body = "\n".join([
        "potions morning: risk-guard SHADOW digest",
        f"sent_at={datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"daemon pid={pid} alive={alive}",
        f"shadow_until={status.get('shadow_until')}",
        f"threshold_basis={status.get('threshold_basis')}",
        f"poll_rows={polls} breach_rows={breaches} actions.csv_rows={actions_n}",
        f"last_progress={last}",
        "",
        "=== MAE snapshot ===",
        mae_txt,
        "",
        "hubs:",
        "  live/state/risk_guard_shadow/",
        "  live/state/oanda_winner_mae_carry/",
    ])
    open_rows = status.get("open_rows") or []
    rows_html = []
    for r in open_rows[:40]:
        rows_html.append(
            "<tr><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td><td>%s</td></tr>"
            % (r.get("demo"), r.get("instrument"), r.get("open_qty"), r.get("adverse_pts"),
               r.get("threshold_pts"), r.get("breach"), r.get("would_action"))
        )
    mae_html = (MAE / "EMAIL.html").read_text() if (MAE / "EMAIL.html").exists() else ""
    html = f"""<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;line-height:1.4;color:#222">
<h2>Morning: risk-guard SHADOW digest</h2>
<p>Daemon pid=<code>{pid}</code> alive=<b>{alive}</b> · until <b>{status.get('shadow_until')}</b></p>
<p>threshold: <code>{status.get('threshold_basis')}</code></p>
<p>poll_rows={polls} · breach_rows={breaches} · actions.csv={actions_n}</p>
<p>last: <code>{last}</code></p>
<table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;font-size:13px">
<thead><tr><th>demo</th><th>inst</th><th>qty</th><th>adverse</th><th>thr</th><th>breach</th><th>would</th></tr></thead>
<tbody>
{''.join(rows_html) if rows_html else '<tr><td colspan=7>flat / heartbeat</td></tr>'}
</tbody></table>
<hr/>
{mae_html}
</body></html>"""
    (RG / "EMAIL_MORNING.txt").write_text(body)
    (RG / "EMAIL_MORNING.html").write_text(html)
    send_email(
        subject="potions morning: risk-guard SHADOW + MAE digest",
        body=body,
        html=html,
    )
    print("morning_email_sent", flush=True)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
