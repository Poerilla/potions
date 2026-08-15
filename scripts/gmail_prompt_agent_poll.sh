#!/usr/bin/env bash
# Poll Gmail for subject potions-prompt → Cursor CLI agent → email reply.
# Requires: .env.google + one-time `python -m live.gmail_prompt_agent auth`
#
# Usage:
#   scripts/gmail_prompt_agent_poll.sh              # foreground poll loop
#   scripts/gmail_prompt_agent_poll.sh --daemon     # background w/ pidfile+log
#   scripts/gmail_prompt_agent_poll.sh --once
#   scripts/gmail_prompt_agent_poll.sh --stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="/home/tester/hsm:${ROOT}/v20-python/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HOME}/.local/bin:${PATH}"
export PYTHONWARNINGS="${PYTHONWARNINGS:-ignore::FutureWarning}"

set -a
[[ -f .env.cursor ]] && . ./.env.cursor
[[ -f .env.google ]] && . ./.env.google
set +a

# Do not inherit incomplete CA bundles / OPENSSL_CONF from interactive shells —
# system trust (with Thales Root CA V3) is enough for cursor-agent.
unset OPENSSL_CONF SSL_CERT_FILE SSL_CERT_DIR NODE_EXTRA_CA_CERTS NODE_OPTIONS
unset AGENT_CLI_CREDENTIAL_STORE

PIDFILE="${GMAIL_AGENT_PIDFILE:-$ROOT/live/state/job_notify/gmail_prompt_agent.pid}"
LOGFILE="${GMAIL_AGENT_LOG:-$ROOT/live/state/job_notify/gmail_prompt_agent.log}"
mkdir -p "$(dirname "$PIDFILE")"

if [[ "${1:-}" == "--stop" ]]; then
  if [[ -f "$PIDFILE" ]]; then
    pid=$(cat "$PIDFILE" || true)
    if [[ -n "${pid:-}" ]] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" || true
      echo "stopped $pid"
    else
      echo "not running (stale pidfile)"
    fi
    rm -f "$PIDFILE"
  else
    echo "no pidfile"
  fi
  exit 0
fi

if [[ "${1:-}" == "--daemon" ]]; then
  shift || true
  if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
    echo "already running pid=$(cat "$PIDFILE") log=$LOGFILE"
    exit 0
  fi
  nohup env -u OPENSSL_CONF -u SSL_CERT_FILE -u SSL_CERT_DIR -u NODE_EXTRA_CA_CERTS -u NODE_OPTIONS -u AGENT_CLI_CREDENTIAL_STORE \
    python -u -W ignore -m live.gmail_prompt_agent poll "$@" >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  echo "started pid=$! log=$LOGFILE"
  exit 0
fi

exec env -u OPENSSL_CONF -u SSL_CERT_FILE -u SSL_CERT_DIR -u NODE_EXTRA_CA_CERTS -u NODE_OPTIONS -u AGENT_CLI_CREDENTIAL_STORE \
  python -u -W ignore -m live.gmail_prompt_agent poll "$@"
