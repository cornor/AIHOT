"""Publish a credential-free local event after verified QR credentials are saved."""
import json
import os
import uuid
from pathlib import Path


def authorization_saved():
    filename = os.environ.get('GAMEHOT_AUTH_EVENT_FILE')
    if not filename:
        return
    path = Path(filename)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps({'id': uuid.uuid4().hex}))
    temp.chmod(0o644)
    temp.replace(path)
