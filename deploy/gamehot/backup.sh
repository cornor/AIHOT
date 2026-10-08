#!/usr/bin/env bash
set -euo pipefail
cd /opt/gamehot
backup_dir=private/backups/$(date +%Y%m%d-%H%M%S)
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
# Keep the newest seven completed snapshots.
find private/backups -mindepth 1 -maxdepth 1 -type d | sort -r | tail -n +8 | while read -r old; do rm -rf -- "$old"; done
