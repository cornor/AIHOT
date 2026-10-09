#!/usr/bin/env python3
"""Host-side, read-only checks with grouped and rate-limited Feishu alerts."""
import fcntl
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from notifications import send

ROOT = Path('/opt/gamehot')
DEBOUNCE = 20 * 60
SEND_INTERVAL = 6 * 3600
REPEAT_INTERVAL = 24 * 3600


def command(args):
    return subprocess.run(args, capture_output=True, text=True, timeout=25, check=True).stdout.strip()


def save(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, ensure_ascii=False))
    temp.chmod(0o600)
    temp.replace(path)


class Monitor:
    def __init__(self, path):
        self.path = Path(path)
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'checks': {}}

    def update(self, observations, now):
        for row in self.state['checks'].values():
            row['known'] = False
        for key, (bad, text) in observations.items():
            if bad is None:
                continue  # An unreachable probe is not evidence of recovery.
            row = self.state['checks'].setdefault(key, {'notified': False})
            row['known'] = True
            row['text'] = text
            if bad:
                row.pop('healthy_since', None)
                row.setdefault('bad_since', now)
                if now - row['bad_since'] >= DEBOUNCE:
                    row['active'] = True
            else:
                row.pop('bad_since', None)
                row.setdefault('healthy_since', now)
                if now - row['healthy_since'] >= DEBOUNCE:
                    row['active'] = False
        self.state['checked_at'] = now
        save(self.path, self.state)

    def deliver(self, now, sender=send):
        if now - self.state.get('last_attempt', -SEND_INTERVAL) < SEND_INTERVAL:
            return False
        events = []
        for key, row in self.state['checks'].items():
            if not row.get('known'):
                continue
            if row.get('active') and 'bad_since' in row and now - row.get('last_alarm', -REPEAT_INTERVAL) >= REPEAT_INTERVAL:
                events.append((key, 'alarm', row['text']))
            elif row.get('notified') and row.get('active') is False and 'healthy_since' in row:
                events.append((key, 'recovery', row['text']))
        if not events:
            return False
        # Persist the attempt before sending: crashes/timeouts must not cause rapid retries.
        self.state['last_attempt'] = now
        self.state['notice_id'] = self.state.get('notice_id') or uuid.uuid4().hex[:12]
        save(self.path, self.state)
        lines = ['【游戏研发情报】运行状态通知']
        lines += [('异常：' if kind == 'alarm' else '恢复：') + text for _, kind, text in events]
        lines += ['异常请转给维护人员排查；恢复仅表示对应检查已恢复正常。',
                  '同一问题每天最多提醒一次；运维通知间隔至少 6 小时。',
                  '后台：https://gamehot.paoyou.com/admin', '通知编号：' + self.state['notice_id']]
        try:
            delivered = sender('\n'.join(lines))
        except Exception as exc:
            print('Operations notification failed: ' + type(exc).__name__, flush=True)
            return False
        if not delivered:
            return False
        for key, kind, _ in events:
            row = self.state['checks'][key]
            row['notified'] = kind == 'alarm'
            if kind == 'alarm': row['last_alarm'] = now
        self.state.pop('notice_id', None)
        save(self.path, self.state)
        print('Operations notification delivered.', flush=True)
        return True


SQL = """SELECT json_build_object(
 'worker_age', (SELECT extract(epoch from now()-updated_at) FROM settings WHERE key='heartbeat.worker'),
 'model_failed', (SELECT count(*) FROM receipt_attempts WHERE origin='live' AND service IN ('llm','deepseek') AND status='failed'
   AND started_at > (SELECT coalesce(max(started_at),'epoch'::timestamptz) FROM receipt_attempts WHERE origin='live' AND service IN ('llm','deepseek') AND status='received')),
 'model_last_failed', (SELECT extract(epoch from max(started_at)) FROM receipt_attempts WHERE origin='live' AND service IN ('llm','deepseek') AND status='failed'),
 'model_last_ok', (SELECT extract(epoch from max(started_at)) FROM receipt_attempts WHERE origin='live' AND service IN ('llm','deepseek') AND status='received'),
 'waiting', (SELECT count(*) FROM articles WHERE processing_state='new' AND discovered_at<now()-interval '2 hours'),
 'failed', (SELECT count(*) FROM articles WHERE processing_state='failed'),
 'collection_sources', (SELECT count(*) FROM sources WHERE enabled AND id LIKE 'werss-%'),
 'collection_sync_age', (SELECT extract(epoch from now()-max(last_ok_at)) FROM sources WHERE enabled AND id LIKE 'werss-%')
);"""


def database_findings(data):
    fail = data['model_last_failed'] or 0
    ok = data['model_last_ok'] or 0
    model_bad = True if data['model_failed'] >= 3 and fail > ok else (False if ok >= fail else None)
    return {
        'worker.heartbeat': (data['worker_age'] is None or data['worker_age'] > 1200, '后台处理心跳检查（超过 20 分钟未更新视为异常）'),
        'model.calls': (model_bad, 'DeepSeek 调用累计至少 3 次失败，期间及之后尚无成功回执' if model_bad else 'DeepSeek 已有后续成功回执'),
        'model.backlog': (data['waiting'] >= 10 or data['failed'] >= 3,
                          f"文章处理队列：等待超过两小时 {data['waiting']} 篇，处理失败 {data['failed']} 篇"),
    }


def collection_findings(enabled, data):
    # Only inspect local configuration and RSS sync records, never WeRead authorization.
    paused = None if enabled is None else not enabled
    stale = None
    if enabled and data is not None and data.get('collection_sources', 0) > 0:
        age = data.get('collection_sync_age')
        stale = age is None or age > 8 * 3600
    return {
        'collector.paused': (paused, '自动采集已暂停，不会抓取新文章；需验证上游接口后恢复采集' if paused else '自动采集开关已开启；是否同步成功由同步记录检查确认'),
        'collector.sync': (stale, '自动采集已开启，但超过 8 小时没有成功 RSS 同步（或从未成功）；请检查采集器及上游接口' if stale else '最近 8 小时内有成功 RSS 同步'),
    }


def backup_finding(path, now):
    if not path.exists():
        return True, '尚无可验证的完整备份成功记录'
    value = json.loads(path.read_text())
    age = now - value.get('last_success', 0)
    if value.get('status') == 'failed':
        return True, '最近一次完整备份失败，请检查备份日志和可用空间'
    return age > 30 * 3600, '完整备份时效检查（超过 30 小时没有成功备份视为异常）'


def observations(root=ROOT, now=None):
    now = time.time() if now is None else now
    found = {}
    collect_enabled = None
    sync_data = None
    for service in ('docker', 'nginx', 'cron'):
        try: healthy = command(['systemctl', 'is-active', service]) == 'active'
        except Exception: healthy = False
        found['service.' + service] = (not healthy, service + ' 服务运行状态')
    if not found['service.docker'][0]:
        try:
            flag = command(['docker', 'exec', 'gamehot-collector-1', 'python3', '-c', "import os;print(os.getenv('COLLECT_ENABLED', ''))"])
            collect_enabled = {'true': True, 'false': False}.get(flag)
        except Exception:
            pass  # Container/Docker failures are reported separately; do not invent a mode.
        for name in ('db', 'api', 'web', 'worker', 'werss', 'collector'):
            try:
                value = json.loads(command(['docker', 'inspect', '--format', '{{json .State}}', 'gamehot-' + name + '-1']))
                healthy = value.get('Running') and value.get('Health', {}).get('Status', 'healthy') == 'healthy'
            except Exception: healthy = False
            found['container.' + name] = (not healthy, name + ' 容器运行和健康检查')
        try:
            data = json.loads(command(['docker', 'exec', 'gamehot-db-1', 'psql', '-U', 'gamehot', '-d', 'gamehot', '-Atc', SQL]))
            sync_data = data
            found.update(database_findings(data))
            found['database.probe'] = (False, '数据库查询检查')
        except Exception:
            found['database.probe'] = (True, '无法查询数据库，模型和后台任务状态暂不可确认')
    found.update(collection_findings(collect_enabled, sync_data))
    try:
        request = urllib.request.Request('https://gamehot.paoyou.com/api/health')
        try:
            with urllib.request.urlopen(request, timeout=10) as response: status = response.status
        except urllib.error.HTTPError as exc: status = exc.code
        # Internal site: the access guard normally replies 401 to anonymous health requests.
        found['site.http'] = (status not in (200, 401), '网站 HTTP 入口响应检查')
    except Exception: found['site.http'] = (True, '网站 HTTP 入口无法连接')
    try: found['backup'] = backup_finding(root / 'private/backup-status.json', now)
    except Exception: found['backup'] = (True, '备份状态记录无法读取')
    disk = os.statvfs(root)
    used = 1 - disk.f_bavail / disk.f_blocks
    found['disk'] = (used >= .90, f'服务器磁盘已使用 {used:.0%}（90% 起提醒）')
    return found


if __name__ == '__main__':
    if os.environ.get('FEISHU_OPS_ENABLED') != 'true':
        raise SystemExit('Operations monitoring disabled.')
    with (ROOT / 'private/ops-monitor.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        monitor = Monitor(ROOT / 'private/ops-monitor-state.json')
        now = time.time()
        found = observations(now=now)
        monitor.update(found, now)
        monitor.deliver(now)
        print(json.dumps({'checks': len(found), 'abnormal': [k for k, (bad, _) in found.items() if bad]}))
