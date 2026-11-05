#!/usr/bin/env bash
# Incremental Drive backup of every non-git file (untracked + ignored) to gdrive:potions-local.
# Skips credentials (.env*, token json), symlinks, virtualenvs, .certs, __pycache__, and singleton lock/pid files.
# Emails the outcome via live.notify_email when --email is passed.
#
#   setsid nohup scripts/drive_backup_nongit.sh --email >/dev/null 2>&1 &
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$(dirname "$ROOT"):${ROOT}/v20-python/src${PYTHONPATH:+:$PYTHONPATH}"
EMAIL=0
[ "${1:-}" = "--email" ] && EMAIL=1

STAMP="$(date +%Y%m%d_%H%M%S)"
LOG_DIR="${ROOT}/data/backup_logs"
mkdir -p "$LOG_DIR"
LOG="${LOG_DIR}/drive_backup_${STAMP}.log"
LIST="/tmp/potions_nongit_${STAMP}.txt"

git ls-files -z --others --ignored --exclude-standard >"${LIST}.raw"
git ls-files -z --others --exclude-standard >>"${LIST}.raw"
python3 - "${LIST}.raw" "$LIST" <<'PY'
import os, re, sys
from pathlib import Path
skip = re.compile(r'(^|/)(\.env[^/]*|\.gmail_token[^/]*|[^/]*token[^/]*\.json|__pycache__/.*|\.locks/.*|daemon\.lock|pidfile)$'
                  r'|^(\.venv[^/]*|venv|\.certs)/')
seen, paths, total = set(), [], 0
for raw in Path(sys.argv[1]).read_bytes().split(b'\0'):
    s = raw.decode('utf-8', 'surrogateescape')
    if not s or '\n' in s or s in seen or skip.search(s) or os.path.islink(s):
        continue
    seen.add(s)
    paths.append(s)
    try:
        total += os.path.getsize(s)
    except OSError:
        pass
Path(sys.argv[2]).write_text('\n'.join(paths) + '\n')
print('%d files, %.1f GB' % (len(paths), total / 1e9))
PY
SUMMARY_LIST="$(wc -l <"$LIST") files listed"
START=$(date +%s)

rclone copy "$ROOT" gdrive:potions-local \
  --files-from "$LIST" --no-traverse \
  --transfers 4 --checkers 8 --retries 5 --drive-chunk-size 64M \
  --stats 10m --stats-one-line --log-level NOTICE --log-file "$LOG"
RC=$?
MINS=$(( ($(date +%s) - START) / 60 ))
rm -f "${LIST}.raw"

if [ "$EMAIL" = 1 ]; then
  python3 - "$RC" "$MINS" "$LOG" "$SUMMARY_LIST" <<'PY'
import sys
from pathlib import Path
from potions.live.notify_email import send_email
rc, mins, log, listed = sys.argv[1], sys.argv[2], Path(sys.argv[3]), sys.argv[4]
lines = log.read_text(errors='replace').splitlines() if log.exists() else []
errors = [l for l in lines if 'ERROR' in l]
tail = '\n'.join(lines[-8:])
status = 'OK' if rc == '0' else 'FINISHED WITH ERRORS (rc=%s)' % rc
body = ("Drive backup %s\nremote: gdrive:potions-local (appDataFolder)\n%s; %s min\n"
        "errors: %d (live-growing daemon files can fail; re-run picks them up)\n\nlog: %s\n\n%s\n"
        % (status, listed, mins, len(errors), log, tail))
if errors:
    body += "\nfirst errors:\n" + '\n'.join(errors[:10])
send_email(subject="potions Drive backup %s" % status.split(' (')[0], body=body)
PY
fi
exit $RC
