#!/usr/bin/env bash
# Wait for London overnight chain, then build FX 5m bias charts + email.
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
export PATH="$HOME/.local/bin:$PATH"
unset OPENSSL_CONF SSL_CERT_FILE SSL_CERT_DIR NODE_EXTRA_CA_CERTS NODE_OPTIONS AGENT_CLI_CREDENTIAL_STORE

CHAIN_PID="${1:-}"
LOG="live/state/fx_v2b_london_charts_watch.log"
mkdir -p live/state
exec > >(tee -a "$LOG") 2>&1

echo "[$(date -Iseconds)] chart watcher start chain_pid=${CHAIN_PID:-none}"

if [[ -n "${CHAIN_PID}" ]]; then
  echo "[$(date -Iseconds)] waiting for overnight chain pid ${CHAIN_PID}..."
  while kill -0 "${CHAIN_PID}" 2>/dev/null; do
    sleep 60
  done
  echo "[$(date -Iseconds)] chain pid ${CHAIN_PID} finished"
  sleep 5
fi

# Also require prior_aligned EMAIL (last gate) so we don't chart a partial hub.
for i in $(seq 1 180); do
  if [[ -f live/state/fx_v2b_london_prior_aligned/EMAIL.txt ]] \
     && [[ -f live/state/fx_v2b_london_prior_opposed/EMAIL.txt ]] \
     && [[ -f live/state/fx_v2b_london_ungated/EMAIL.txt ]]; then
    echo "[$(date -Iseconds)] all hub EMAIL.txt present"
    break
  fi
  echo "[$(date -Iseconds)] waiting for hub EMAIL artifacts (try ${i})..."
  sleep 60
done

python -m live.fx_v2b_london_5m_bias_charts \
  --hubs ungated,prior_opposed,prior_aligned \
  --markets EURUSD,GBPUSD,USDJPY,AUDJPY \
  --book S_1_1_3 \
  --max-charts 40 \
  --force \
  --email \
  --output-root live/state/fx_v2b_london_charts

rc=$?
echo "[$(date -Iseconds)] chart job exit=${rc}"
if [[ $rc -ne 0 ]]; then
  python - <<'PY' || true
from live.notify_email import send_email
send_email(
    subject="potions: FX London 5m bias charts FAILED",
    body="Chart job failed. See live/state/fx_v2b_london_charts_watch.log",
)
PY
fi
exit $rc
