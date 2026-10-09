#!/usr/bin/env python3
"""Collect configured WeRead feeds and import their RSS through the normal article pipeline."""
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from notifications import Notices, auth_status

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8001/api/v1/wx"
stop = threading.Event()
for sig in (signal.SIGINT, signal.SIGTERM):
    signal.signal(sig, lambda *_: stop.set())


class WeRSSError(Exception):
    def __init__(self, result):
        self.code = (result.get('data') or {}).get('code', result.get('code'))
        super().__init__('WeRSS response code: ' + str(self.code))


def request(route, payload=None, token=None, form=False, timeout=30):
    data = None if payload is None else (urllib.parse.urlencode(payload).encode() if form else json.dumps(payload).encode())
    headers = {"Content-Type": "application/x-www-form-urlencoded" if form else "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        with urllib.request.urlopen(urllib.request.Request(BASE + route, data=data, headers=headers), timeout=timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        try:
            result = json.load(exc)
            if isinstance(result, dict):
                result = result.get('detail', result)
            if not isinstance(result, dict):
                raise ValueError('Unexpected error response')
        except (ValueError, TypeError):
            raise RuntimeError('WeRSS HTTP ' + str(exc.code)) from None
    if result.get("code") != 0:
        raise WeRSSError(result)
    return result.get("data", {})


def login():
    return request('/auth/login', {'username': os.environ['USERNAME'], 'password': os.environ['PASSWORD']}, form=True)['access_token']


def check_authorization(notices, token=None):
    try:
        status = auth_status(request('/weread', token=token or login()))
        notices.authorization(status, os.environ.get('COLLECT_ENABLED') == 'true')
        print('WeRead authorization check: ' + status, flush=True)
        return status
    except Exception as exc:
        print('Authorization check failed: ' + type(exc).__name__, flush=True)


def cycle(notices):
    if os.environ.get("COLLECT_ENABLED") != "true":
        print("Collection disabled.", flush=True)
        return
    feeds = json.loads(Path(os.environ.get("WERSS_FEEDS_FILE", ROOT / "deploy/gamehot/feeds.json")).read_text())
    token = login()
    if os.environ.get('FEISHU_COLLECTOR_ENABLED') == 'true':
        if check_authorization(notices, token) in ('expired', 'missing'):
            return
    started = time.monotonic()
    gathered = 0
    succeeded = 0
    failures = []
    for feed in feeds:
        if stop.is_set():
            return
        try:
            result = request("/weread/collect", {
                "mp_id": feed["feedId"], "faker_id": feed["feedId"], "mp_name": feed["name"],
                "gather_content": True, "max_page": 1,
            }, token, timeout=600)
            gathered += int(result.get("collected", 0))
            succeeded += 1
            print(json.dumps({"source": feed["name"], "collected": result.get("collected")}, ensure_ascii=False), flush=True)
        except Exception as exc:
            code = getattr(exc, 'code', type(exc).__name__)
            failures.append(feed['name'] + '（' + str(code) + '）')
            print(json.dumps({'source': feed['name'], 'error_code': code}, ensure_ascii=False), flush=True)
    if not stop.is_set():
        imported = subprocess.run(['node', 'scripts/sync-werss.ts'], cwd=ROOT, capture_output=True, text=True, timeout=900)
        created = revised = import_ok = 0
        import_failed = []
        for line in imported.stdout.splitlines() + imported.stderr.splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            if not isinstance(row, dict) or not row.get('source'):
                continue
            if 'error' in row:
                import_failed.append(row['source'])
            elif 'created' in row and 'revised' in row:
                created += row['created']; revised += row['revised']; import_ok += 1
        incomplete = imported.returncode != 0 or import_ok != len(feeds) or bool(import_failed)
        lines = [f'公众号：成功 {succeeded}/{len(feeds)}，失败 {len(failures)}。',
                 f'WeRSS 本轮抓取：{gathered} 篇（失败信源可能已有部分写入，未计入）。',
                 f'站点入库：新增 {created} 篇，更新 {revised} 篇。',
                 'RSS 导入：' + ('存在失败或结果不完整。' if incomplete else '完成。'),
                 '摘要由后台异步生成；此通知不代表 DeepSeek 摘要已完成。',
                 f'本轮耗时：{round(time.monotonic() - started)} 秒；下一轮约 4 小时后。']
        if failures: lines.append('采集失败：' + '、'.join(failures))
        if import_failed: lines.append('导入失败：' + '、'.join(import_failed))
        lines.append('站点：http://gamehot.paoyou.com')
        notices.enqueue('采集结束（有异常）' if failures or incomplete else '采集完成', lines)
        if failures and os.environ.get('FEISHU_COLLECTOR_ENABLED') == 'true':
            check_authorization(notices)


if __name__ == "__main__":
    notices = Notices()
    if '--notify-test' in sys.argv:
        notices.enqueue('飞书通知接通测试', [
            '已启用：每轮采集概况、微信读书授权过期及恢复提醒。',
            '采集周期：每轮结束后等待 4 小时；仅在采集时检查授权。',
            '当前采集开关：' + ('开启' if os.environ.get('COLLECT_ENABLED') == 'true' else '关闭'),
            '这是接通测试，不代表本轮采集已完成，也不是授权过期告警。'])
        notices.flush()
        raise SystemExit(1 if notices.state['pending'] else 0)
    next_cycle = 0
    while not stop.is_set():
        if time.monotonic() >= next_cycle:
            try:
                cycle(notices)
            except Exception as exc:
                print('Collection failed: ' + type(exc).__name__, flush=True)
                if not stop.is_set():
                    notices.enqueue('采集未完成', ['本轮任务异常中断，请检查采集器和 WeRSS 服务。',
                        '错误类型：' + type(exc).__name__, '下一轮约 4 小时后重试。'])
            next_cycle = time.monotonic() + 4 * 60 * 60
        notices.flush()
        if '--watch' not in sys.argv:
            break
        stop.wait(min(15 * 60, max(1, next_cycle - time.monotonic())))
