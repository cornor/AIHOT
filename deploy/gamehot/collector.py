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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from notifications import Notices

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8001/api/v1/wx"
TIMEZONE = ZoneInfo('Asia/Shanghai')
SCHEDULE_VERSION = 'daily-09-shanghai-v1'
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


def check_authorization(notices, token=None, book_id=None, allow_renew=True, renewal_state=None):
    try:
        if book_id is None:
            feeds = json.loads(Path(os.environ.get('WERSS_FEEDS_FILE', ROOT / 'deploy/gamehot/feeds.json')).read_text())
            book_id = feeds[0]['feedId']
        data = request('/weread/ensure-auth', {'book_id': book_id, 'allow_renew': allow_renew},
                       token=token or login(), timeout=110)
        if renewal_state is not None and data.get('attempted') is True:
            renewal_state['attempted'] = True
        status = data.get('status', 'unknown')
        if status not in ('valid', 'expired', 'missing', 'unknown'):
            status = 'unknown'
        if os.environ.get('FEISHU_COLLECTOR_ENABLED') == 'true':
            notices.authorization(status, os.environ.get('COLLECT_ENABLED') == 'true')
        print('WeRead authorization check: ' + status + '; renewed=' + str(data.get('renewed') is True), flush=True)
        return status
    except Exception as exc:
        print('Authorization check failed: ' + type(exc).__name__, flush=True)
        return 'unknown'


def cycle(notices):
    if os.environ.get("COLLECT_ENABLED") != "true":
        print("Collection disabled.", flush=True)
        return
    feeds = json.loads(Path(os.environ.get("WERSS_FEEDS_FILE", ROOT / "deploy/gamehot/feeds.json")).read_text())
    token = login()
    if not feeds:
        return True
    renewal_state = {}
    status = check_authorization(notices, token, feeds[0]['feedId'], renewal_state=renewal_state)
    if status in ('expired', 'missing'):
        return False
    if status != 'valid':
        if os.environ.get('FEISHU_COLLECTOR_ENABLED') == 'true':
            notices.authorization_problem()
        return False
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
                 f'本轮耗时：{round(time.monotonic() - started)} 秒；定时采集：每天北京时间 09:00。']
        if failures: lines.append('采集失败：' + '、'.join(failures))
        if import_failed: lines.append('导入失败：' + '、'.join(import_failed))
        if os.environ.get('WERSS_LATEST_ONLY') == 'true':
            lines.append('临时模式：每个公众号每轮只取最新一篇并去重；两轮之间的其他文章可能漏采，不代表完整同步。')
        lines.append('站点：https://gamehot.paoyou.com')
        notices.enqueue('采集结束（有异常）' if failures or incomplete else '采集完成', lines)
        if failures and os.environ.get('FEISHU_COLLECTOR_ENABLED') == 'true':
            if check_authorization(notices, token, feeds[0]['feedId'],
                                   allow_renew=not renewal_state.get('attempted'), renewal_state=renewal_state) != 'valid':
                return False
        return True


def daily_slot(now):
    return datetime.fromtimestamp(now, TIMEZONE).replace(hour=9, minute=0, second=0, microsecond=0)


def next_daily(now):
    slot = daily_slot(now)
    if slot.timestamp() <= now:
        slot += timedelta(days=1)
    return slot.timestamp()


class Schedule:
    """Run at 09:00 Beijing time, plus once for each newly saved QR authorization."""
    def __init__(self, path=None):
        self.path = Path(path or Path(os.environ.get('AIHOT_DATA_DIR', '.data')) / 'collector-schedule.json')
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state))
        temp.chmod(0o600)
        temp.replace(self.path)

    def run_due(self, notices):
        if os.environ.get('COLLECT_ENABLED') != 'true':
            return False
        now = time.time()
        event = self.state.get('auth_event')
        event_path = os.environ.get('WERSS_AUTH_EVENT_FILE')
        if event_path:
            try:
                value = json.loads(Path(event_path).read_text()).get('id')
                if isinstance(value, str) and value:
                    event = value
            except (OSError, ValueError, AttributeError):
                pass
        # A fresh installation remembers the existing event without replaying an old scan.
        changed = bool(self.state) and event != self.state.get('auth_event')
        if self.state.get('version') != SCHEDULE_VERSION:
            slot = daily_slot(now).timestamp()
            self.state = {'version': SCHEDULE_VERSION,
                          'due_at': slot if now < slot + 60 else next_daily(now),
                          'auth_event': self.state.get('auth_event', event)}
            self.save()
        due = self.state['due_at']
        scheduled = due <= now < due + 60
        # A missed 09:00 slot is skipped; restarting later does not cause an extra run.
        if now >= due:
            self.state['due_at'] = next_daily(now)
            self.save()
        if not scheduled and not changed:
            return False
        # Consume both triggers before collection so a restart cannot replay the attempt.
        self.state['auth_event'] = event
        self.state['last_attempt_at'] = now
        self.save()
        print('Collection trigger: ' + ('daily+scan' if scheduled and changed else 'daily' if scheduled else 'scan'), flush=True)
        try:
            cycle(notices)
        except Exception as exc:
            print('Collection failed: ' + type(exc).__name__, flush=True)
            if not stop.is_set():
                notices.enqueue('采集未完成', ['本轮任务异常中断，请检查采集器和 WeRSS 服务。',
                    '错误类型：' + type(exc).__name__,
                    '下一次定时采集为北京时间 09:00；重新扫码成功也会额外采集一次。'])
        return True


if __name__ == "__main__":
    notices = Notices()
    if '--notify-test' in sys.argv:
        notices.enqueue('飞书通知接通测试', [
            '已启用：每轮采集概况、微信读书授权过期及恢复提醒。',
            '采集周期：每天北京时间 09:00；扫码成功后额外采集一次，仅在采集时检查授权。',
            '当前采集开关：' + ('开启' if os.environ.get('COLLECT_ENABLED') == 'true' else '关闭'),
            '这是接通测试，不代表本轮采集已完成，也不是授权过期告警。'])
        notices.flush()
        raise SystemExit(1 if notices.state['pending'] else 0)
    schedule = Schedule()
    next_flush = 0
    while not stop.is_set():
        attempted = schedule.run_due(notices)
        if attempted or time.monotonic() >= next_flush:
            notices.flush()
            next_flush = time.monotonic() + 15 * 60
        if '--watch' not in sys.argv:
            break
        stop.wait(5)
