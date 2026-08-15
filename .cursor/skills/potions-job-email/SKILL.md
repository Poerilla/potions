---
name: potions-job-email
description: >-
  Always email the user when potions market replays, backtests, sweeps, audits,
  or long-running jobs finish (or crash). Use whenever starting or completing
  a research/replay/test job, or when the user asks for completion notifications.
---

# Potions job email (always notify)

**Rule:** Any market replay, broker-like backtest, sweep, causality audit, plugin
batch, or other multi-minute job **must** email a completion (or failure) summary
to the configured notify address. Do not wait for the user to ask.

## How to send

Prefer Resend (works under corp TLS):

```bash
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
python -m live.notify_email --subject "potions: <job> complete" --body-file <hub>/EMAIL.txt
# or
python - <<'PY'
from live.notify_email import send_email
send_email(subject="potions: <job> complete", body=open("EMAIL.txt").read())
PY
```

Drivers should accept `--email` and write `EMAIL.txt` + call `send_email` on finish.

## What to include

- Job name + hub path (`live/state/<slug>/`)
- Markets / book / gate
- Key metrics (net, stress, N/S, trades) or crash traceback tip
- Promote / reject stance when applicable

## Arming watchers

For background batches already running without `--email`:

```bash
scripts/arm_completion_watchers.sh   # if present for that hub family
# or
python -m live.notify_when_done --hub live/state/<slug> --pid <pid>
```

## Gmail → agent prompts

Inbound prompts use subject `potions-prompt` or `Re: potions-prompt`
(`live/gmail_prompt_agent.py`, daemon via `scripts/gmail_prompt_agent_poll.sh`).
Outbound job mail is separate (Resend / notify).

## Related

- `live/notify_email.py` — send path
- `strategy-completion-report` — richer completion reports
- `potions-demo-status` — live/demo heartbeats (different from research jobs)
