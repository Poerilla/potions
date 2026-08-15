#!/usr/bin/env bash
# Wait for ungated London v2b, then prior-opposed S_1_1_3, then prior-aligned.
# Emails after each gated batch (ungated already has --email).
set -u
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"
export PYTHONPATH="/home/tester/hsm:/home/tester/hsm/potions/v20-python/src"
export PATH="$HOME/.local/bin:$PATH"
unset OPENSSL_CONF SSL_CERT_FILE SSL_CERT_DIR NODE_EXTRA_CA_CERTS NODE_OPTIONS AGENT_CLI_CREDENTIAL_STORE

WAIT_PID="${1:-}"
MARKETS="EURUSD,GBPUSD,USDJPY,AUDJPY,XAUUSD,XAGUSD,US30,NAS100"
LOG="live/state/fx_v2b_london_overnight_chain.log"
mkdir -p live/state
exec > >(tee -a "$LOG") 2>&1

echo "[$(date -Iseconds)] overnight chain start wait_pid=${WAIT_PID:-none}"

if [[ -n "${WAIT_PID}" ]]; then
  echo "[$(date -Iseconds)] waiting for ungated pid ${WAIT_PID}..."
  while kill -0 "${WAIT_PID}" 2>/dev/null; do
    sleep 60
  done
  echo "[$(date -Iseconds)] ungated pid ${WAIT_PID} finished"
  # Give ungated a moment to flush EMAIL if still writing
  sleep 5
fi

run_gate() {
  local gate="$1"
  local out="live/state/fx_v2b_london_${gate}"
  echo "[$(date -Iseconds)] START gate=${gate} -> ${out}"
  if python -m live.fx_v2b_london_gated \
      --gate "${gate}" \
      --book S_1_1_3 \
      --markets "${MARKETS}" \
      --email \
      --output-root "${out}"; then
    echo "[$(date -Iseconds)] OK gate=${gate}"
  else
    local rc=$?
    echo "[$(date -Iseconds)] FAIL gate=${gate} rc=${rc}"
    python - <<PY || true
from live.notify_email import send_email
send_email(
    subject="potions: fx_v2b_london_${gate} FAILED",
    body="Gate ${gate} failed with rc=${rc}. See ${REPO}/live/state/fx_v2b_london_overnight_chain.log and ${out}/PROGRESS.log",
)
PY
    return $rc
  fi
}

run_gate prior_opposed
run_gate prior_aligned

echo "[$(date -Iseconds)] overnight chain complete"
python - <<'PY' || true
from live.notify_email import send_email
from pathlib import Path
parts = ["potions: fx_v2b_london overnight chain complete", ""]
for gate in ("ungated", "prior_opposed", "prior_aligned"):
    hub = Path(f"live/state/fx_v2b_london_{gate}" if gate != "ungated" else "live/state/fx_v2b_london_ungated")
    email = hub / "EMAIL.txt"
    parts.append(f"=== {gate} ({hub}) ===")
    if email.exists():
        parts.append(email.read_text(encoding="utf-8", errors="replace")[:2500])
    else:
        parts.append("(no EMAIL.txt yet)")
    parts.append("")
send_email(subject="potions: fx_v2b_london overnight chain complete", body="\n".join(parts))
print("chain summary email sent")
PY
