#!/usr/bin/env bash
set -euo pipefail
cd /opt/gamehot
exec 9>private/backup.lock
flock -n 9 || exit 0
backup_dir=private/backups/$(date +%Y%m%d-%H%M%S)
record_failure() {
  backup_exit=$?
  if [ "$backup_exit" -ne 0 ]; then
    python3 deploy/gamehot/backup_status.py failed "$backup_dir" || true
  fi
}
trap record_failure EXIT
mkdir -p "$backup_dir"
chmod 700 "$backup_dir"
compose=(docker compose --env-file .env -f deploy/gamehot/compose.yaml)
"${compose[@]}" exec -T db pg_dump -U gamehot -d gamehot -Fc > "$backup_dir/postgres.dump"
"${compose[@]}" exec -T werss python3 -c 'import sqlite3; a=sqlite3.connect("file:/app/data/db.db?mode=ro",uri=True); b=sqlite3.connect("/app/data/backup.sqlite"); a.backup(b); b.close(); a.close()'
cp private/werss-data/backup.sqlite "$backup_dir/werss.sqlite"
tar --exclude=db.db --exclude=db.db-wal --exclude=db.db-shm --exclude=backup.sqlite -czf "$backup_dir/files.tar.gz" private/app-data private/werss-data
cp .env private/werss.env "$backup_dir/"
git rev-parse HEAD > "$backup_dir/commit.txt"
chmod -R go-rwx "$backup_dir"
docker compose --env-file .env -f deploy/gamehot/compose.yaml exec -T db pg_restore --list < "$backup_dir/postgres.dump" > /dev/null
python3 - "$backup_dir" <<'PY'
from pathlib import Path
import sqlite3
import sys
import tarfile
snapshot = Path(sys.argv[1])
with sqlite3.connect(f"file:{snapshot / 'werss.sqlite'}?mode=ro", uri=True) as db:
    assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
with tarfile.open(snapshot / 'files.tar.gz', 'r:gz') as archive:
    assert archive.getmembers()
(snapshot / 'completed').touch(mode=0o600)
PY
# Keep the newest seven completed snapshots.
python3 - <<'PY'
from pathlib import Path
import re
import shutil
root = Path("private/backups").resolve()
snapshots = sorted((p for p in root.iterdir() if p.is_dir() and not p.is_symlink()
                    and re.fullmatch(r"\d{8}-\d{6}", p.name) and (p / 'completed').is_file()), reverse=True)
for old in snapshots[7:]:
    shutil.rmtree(old)
PY
python3 deploy/gamehot/backup_status.py success "$backup_dir"
