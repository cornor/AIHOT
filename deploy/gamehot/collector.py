#!/usr/bin/env python3
"""Collect configured WeRead feeds and import their RSS through the normal article pipeline."""
import json
import os
import signal
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8001/api/v1/wx"
stop = threading.Event()
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda *_: stop.set())


def request(route, payload, token=None, form=False):
    data = urllib.parse.urlencode(payload).encode() if form else json.dumps(payload).encode()
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urllib.request.urlopen(urllib.request.Request(BASE + route, data=data, headers=headers), timeout=600) as response:
        result = json.load(response)
    if result.get("code") != 0:
        raise RuntimeError("WeRSS response code: " + str(result.get("code")))
    return result.get("data", {})


def cycle():
    if os.environ.get("COLLECT_ENABLED") != "true":
        print("Collection disabled.", flush=True)
        return
    feeds = json.loads(Path(os.environ.get("WERSS_FEEDS_FILE", ROOT / "deploy/gamehot/feeds.json")).read_text())
    auth = request("/auth/login", {"username": os.environ["USERNAME"], "password": os.environ["PASSWORD"]}, form=True)
    for feed in feeds:
        if stop.is_set():
            return
        try:
            result = request("/weread/collect", {
                "mp_id": feed["feedId"], "faker_id": feed["feedId"], "mp_name": feed["name"],
                "gather_content": True, "max_page": 1,
            }, auth["access_token"])
            print(json.dumps({"source": feed["name"], "collected": result.get("collected")}, ensure_ascii=False), flush=True)
        except Exception as exc:
            print(json.dumps({"source": feed["name"], "error": type(exc).__name__ + ": " + str(exc)[:250]}, ensure_ascii=False), flush=True)
    if not stop.is_set():
        subprocess.run(["node", "scripts/sync-werss.ts"], cwd=ROOT, check=True)


if __name__ == "__main__":
    while not stop.is_set():
        try:
            cycle()
        except Exception as exc:
            print("Collection failed: " + type(exc).__name__ + ": " + str(exc)[:250], flush=True)
            if "--watch" not in sys.argv:
                raise SystemExit(1)
        if "--watch" not in sys.argv:
            break
        stop.wait(4 * 60 * 60)
