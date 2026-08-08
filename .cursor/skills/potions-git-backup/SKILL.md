---
name: potions-git-backup
description: >-
  Handles potions git check-in, curated large-file archives, and Google Drive
  backups via rclone. Use when committing, pushing, packing/unpacking large
  files, updating gdrive:potions-local, or when the user mentions large files,
  strip list, Drive, or rclone.
---

# Potions git + large-file + Drive backup

## Git check-in (code only)

1. Commit **only when the user asks**.
2. Never commit: `live/demo/.env`, credentials, multi-GB raw/sweep dumps, `feature_snapshots.csv`, chart packs.
3. Prefer small code/docs commits; keep archives out of git (already gitignored).
4. Push in batches if history is heavy: [`scripts/push_in_batches.sh`](../../../scripts/push_in_batches.sh).
5. Do **not** run `strip_large_files.sh` / `git filter-repo` unless the user explicitly requests destructive history rewrite.

Follow the user’s normal git commit protocol (status/diff/log → stage → HEREDOC message → status).

## Curated large-file archive

Policy: [`scripts/LARGE_FILES_MANIFEST.md`](../../../scripts/LARGE_FILES_MANIFEST.md)  
Path list: [`scripts/large_files_to_strip.txt`](../../../scripts/large_files_to_strip.txt)

```bash
# Pack (does NOT delete local files)
./scripts/pack_large_files.sh --strict
# → data/potions_large_files.tar.zst + data/potions_large_files.manifest

# Restore later
./scripts/unpack_large_files.sh data/potions_large_files.tar.zst
```

Refresh `large_files_to_strip.txt` before packing if the curated set changed (raw OHLC + winner equities; skip full sweeps / feature dumps).

## Incremental Drive backup (non-git files)

Prefer **`rclone copy`** (incremental), not system `rsync`. Destination remote: `gdrive:potions-local`.

Full recipe: [reference.md](reference.md).

**Important:** the current `gdrive` remote uses `scope = drive.appfolder` / `root_folder_id = appDataFolder`. Files **count against Drive quota** but **do not appear** in the My Drive web UI. Listing works via rclone/`~/gdrive`. Do not promise browser visibility unless reconfigured to full `drive` scope.

## Related skills

- `potions-repo-router` — when to pack vs commit
- `potions-tracker-docs` — after research, docs go to git; large artifacts to Drive
