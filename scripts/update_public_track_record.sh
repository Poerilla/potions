#!/usr/bin/env bash
# Refresh sanitized public track-record JSON and push GitHub Pages.
#
# Usage:
#   scripts/update_public_track_record.sh           # export + push if changed
#   scripts/update_public_track_record.sh --dry-run # export only, no git push
#   scripts/update_public_track_record.sh --email   # also email success summary
#   scripts/update_public_track_record.sh --install-cron
#
# Env:
#   PUBLIC_TRACK_REPO   default: /home/tester/fx-momentum-track
#   PUBLIC_TRACK_EMAIL  if 1, email on success (failures always email)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="/home/tester/hsm:${ROOT}/v20-python/src${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HOME}/.local/bin:${HOME}/.pyenv/shims:${PATH}"

PUBLIC_REPO="${PUBLIC_TRACK_REPO:-/home/tester/fx-momentum-track}"
LOG_DIR="${ROOT}/live/state/public_fx_momentum_pages"
LOG_FILE="${LOG_DIR}/cron.log"
LOCK_FILE="${LOG_DIR}/update.lock"
EMAIL_FLAG=0
DRY_RUN=0
INSTALL_CRON=0

for arg in "$@"; do
  case "$arg" in
    --email) EMAIL_FLAG=1 ;;
    --dry-run) DRY_RUN=1 ;;
    --install-cron) INSTALL_CRON=1 ;;
    -h|--help)
      sed -n '2,14p' "$0"
      exit 0
      ;;
  esac
done

mkdir -p "$LOG_DIR"

if [[ "$INSTALL_CRON" -eq 1 ]]; then
  # Daily 06:15 America/New_York. Idempotent: strip any prior lines first.
  LINE="15 6 * * * TZ=America/New_York cd ${ROOT} && ./scripts/update_public_track_record.sh --email >>${LOG_FILE} 2>&1"
  TMP="$(mktemp)"
  { crontab -l 2>/dev/null || true; } | grep -v 'update_public_track_record.sh' | grep -v '^[[:space:]]*$' >"$TMP" || true
  echo "$LINE" >>"$TMP"
  crontab "$TMP"
  rm -f "$TMP"
  echo "installed cron:"
  crontab -l | grep update_public_track_record || true
  exit 0
fi

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) skip: another update is running"
  exit 0
fi

ts() { date -u +%Y-%m-%dT%H:%M:%SZ; }
echo "$(ts) start public track-record update"

send_mail() {
  local subject="$1"
  local body="$2"
  local body_file
  body_file="$(mktemp)"
  printf '%s\n' "$body" >"$body_file"
  (
    cd "$ROOT"
    export PYTHONPATH="/home/tester/hsm:${ROOT}/v20-python/src${PYTHONPATH:+:$PYTHONPATH}"
    python3 -m live.notify_email --subject "$subject" --body-file "$body_file"
  ) && echo "email sent: $subject" \
    || echo "email failed: $subject" >&2
  rm -f "$body_file"
}

on_fail() {
  local rc=$?
  local tip
  tip="$(tail -n 40 "$LOG_FILE" 2>/dev/null || echo "(no log)")"
  send_mail "potions: public track-record update FAILED" \
"Public track-record daily update failed (rc=${rc}).

Log: ${LOG_FILE}
Hub: live/state/public_fx_momentum_pages/
Pages: https://poerilla.github.io/fx-momentum-track/

Last log lines:
${tip}
" || true
  exit "$rc"
}
trap on_fail ERR

# 1) Export sanitized JSON into private hub + public docs/data
OUT_PRIVATE="${LOG_DIR}/data"
OUT_PUBLIC="${PUBLIC_REPO}/docs/data"
mkdir -p "$OUT_PRIVATE" "$OUT_PUBLIC"

python3 -m live.public_track_record.export_all --out-dir "$OUT_PRIVATE"
python3 -m live.public_track_record.export_all --out-dir "$OUT_PUBLIC"

# 2) Leak scan (belt + suspenders; exporter also checks)
python3 - <<PY
from pathlib import Path
banned = (
    "usdjpy", "usd_jpy", "nas100", "asia-range", "asia_range",
    "monday or", "monday_or", "s_3_1_3", "m2_s3_r1", "trail06",
    "oanda", "101-002", "potions", "breakout", "pyramid",
    "clean-break", "clean_break",
    "size-normalized", "size normalized", "live size", "multi-lot",
    "micro-size", "micro fills", "lot-cash", "size-up", "size up",
    "scale-out", "point value", "spy", "n/s", "net/stress", "net-stress",
)
root = Path(${OUT_PUBLIC@Q})
hits = []
for p in root.rglob("*"):
    if not p.is_file():
        continue
    text = p.read_text(errors="ignore").lower()
    bad = [b for b in banned if b in text]
    if bad:
        hits.append(f"{p}: {bad}")
if hits:
    raise SystemExit("LEAK in public data:\\n" + "\\n".join(hits))
print("leak scan ok")
PY

SUMMARY="$(python3 - <<PY
import json
from pathlib import Path
root = Path(${OUT_PUBLIC@Q})
cat = json.loads((root / "catalog.json").read_text())
lines = ["as_of=" + str(cat.get("as_of")), "tabs=" + ",".join(t["name"] for t in cat["tabs"])]
for t in cat["tabs"]:
    rel = t["data"].split("/", 1)[-1]
    d = json.loads((root / rel).read_text())
    pk = d.get("practice_kpis") or {}
    lines.append(
        f"{t['name']}: practice_n={pk.get('n_campaigns')} practice_net={d.get('practice_net_check_usd')} "
        f"bt_end={ (d.get('kpis') or {}).get('end_equity') }"
    )
print("\\n".join(lines))
PY
)"

echo "$SUMMARY"

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "$(ts) dry-run: skip git push"
  trap - ERR
  exit 0
fi

# 3) Commit + push public repo only if data/html changed
cd "$PUBLIC_REPO"
git add docs/data docs/index.html README.md 2>/dev/null || git add docs/data
if git diff --cached --quiet; then
  echo "$(ts) no public changes to push"
  CHANGED=0
else
  git -c user.email="poerilla@users.noreply.github.com" -c user.name="Poerilla" commit -m "$(cat <<'EOF'
Daily refresh of sanitized track-record JSON.

Practice sleeve fills + research backtests; no account NAV.
EOF
)"
  # Prefer HTTPS + gh creds (SSH to github.com:443 often flaky here).
  if git remote get-url origin | grep -q '^git@'; then
    git remote set-url origin "https://github.com/Poerilla/fx-momentum-track.git"
  fi
  gh auth setup-git >/dev/null 2>&1 || true
  git push origin HEAD
  CHANGED=1
  echo "$(ts) pushed public pages"
fi

trap - ERR

BODY="Public track-record daily update OK.

Pages: https://poerilla.github.io/fx-momentum-track/
Repo: https://github.com/Poerilla/fx-momentum-track
Changed/pushed: ${CHANGED}
Log: ${LOG_FILE}

${SUMMARY}

Rules: sleeve fills only (never account NAV); no instruments in public JSON.
"

if [[ "$EMAIL_FLAG" -eq 1 || "${PUBLIC_TRACK_EMAIL:-0}" == "1" || "$CHANGED" -eq 1 ]]; then
  send_mail "potions: public track-record updated" "$BODY"
fi

echo "$(ts) done changed=${CHANGED}"
