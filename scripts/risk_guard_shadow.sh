#!/usr/bin/env bash
# Shadow risk-guard daemon (avg-loss threshold, log-only) through ~2026-08-28.
#
# Usage:
#   scripts/risk_guard_shadow.sh --once --email
#   scripts/risk_guard_shadow.sh --daemon
#   scripts/risk_guard_shadow.sh --stop
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="/home/tester/hsm:${ROOT}/v20-python/src${PYTHONPATH:+:$PYTHONPATH}"

HUB="$ROOT/live/state/risk_guard_shadow"
PIDFILE="$HUB/pidfile"
LOGFILE="$HUB/daemon.log"
mkdir -p "$HUB"

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
  # shellcheck disable=SC2086
  nohup python -u -m live.risk_guard_shadow --loop --interval 120 --email "$@" >>"$LOGFILE" 2>&1 &
  echo $! >"$PIDFILE"
  echo "started pid=$! log=$LOGFILE hub=$HUB"
  exit 0
fi

exec python -u -m live.risk_guard_shadow "$@"
