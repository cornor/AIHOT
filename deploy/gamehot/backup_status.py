"""Record completed host backups independently of Docker and PostgreSQL."""
import json
import sys
import time
from pathlib import Path


def record(root, status, snapshot, now=None):
    now = time.time() if now is None else now
    path = root / 'private/backup-status.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    data.update(status=status, checked_at=now, snapshot=snapshot)
    if status == 'success':
        data['last_success'] = now
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data))
    temp.chmod(0o600)
    temp.replace(path)


if __name__ == '__main__':
    record(Path('/opt/gamehot'), sys.argv[1], sys.argv[2])
