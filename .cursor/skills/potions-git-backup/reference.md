# Git / Drive backup reference

## Incremental rclone copy (Option 1 — all non-git files)

```bash
cd /home/tester/hsm/potions

git ls-files -z --others --ignored --exclude-standard > /tmp/potions_nongit.txt
git ls-files -z --others --exclude-standard >> /tmp/potions_nongit.txt

python3 - <<'PY'
from pathlib import Path
raw = Path('/tmp/potions_nongit.txt').read_bytes().split(b'\0')
paths, seen = [], set()
for p in raw:
    if not p:
        continue
    s = p.decode('utf-8', 'surrogateescape')
    if '\n' in s or s in seen:
        continue
    seen.add(s)
    paths.append(s)
Path('/tmp/potions_nongit_nl.txt').write_text('\n'.join(paths) + '\n')
print(len(paths), 'files')
PY

rclone copy /home/tester/hsm/potions gdrive:potions-local \
  --files-from /tmp/potions_nongit_nl.txt \
  --no-traverse \
  --progress \
  --transfers 4 \
  --checkers 8 \
  --retries 5
```

Resume-safe: re-run skips unchanged files. Live-growing logs may fail a few copies; retry later.

## Lean archive-only upload

```bash
rclone copy data/potions_large_files.tar.zst gdrive:potions-local/data/ --progress
rclone copy data/potions_large_files.manifest gdrive:potions-local/data/ --progress
```

## Inspect remote (no browser)

```bash
rclone about gdrive:
rclone lsd gdrive:potions-local
rclone size gdrive:potions-local
ls ~/gdrive/potions-local   # if mount is up
```

Mount (optional browse on this host):

```bash
mkdir -p ~/gdrive
rclone mount gdrive: ~/gdrive --vfs-cache-mode writes --daemon
```

## appDataFolder note

If `rclone config show gdrive` shows `scope = drive.appfolder` and `root_folder_id = appDataFolder`:

- Backup is valid and quota-consuming.
- drive.google.com My Drive will **not** list `potions-local`.
- `rclone link` needs broader scopes (`DrivePermissions.Create`) — not required for personal backup.
- To make files visible in the browser: reconnect with full `drive` scope (blank root) and `rclone copy` into My Drive. Only do this when the user asks.

## Destructive ops (explicit user request only)

| Script | Effect |
|--------|--------|
| `scripts/strip_large_files.sh` | `git filter-repo` history strip |
| `rclone sync` (vs `copy`) | Can delete remote files missing locally |
| `rclone purge` | Deletes remote tree |
