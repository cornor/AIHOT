"""Private collector notifications; persistent retries, no credentials in logs."""
import json
import os
import re
import time
import uuid
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


def read_json(request, timeout=20):
    with urllib.request.build_opener(NoRedirect).open(request, timeout=timeout) as response:
        return json.loads(response.read(2 * 1024 * 1024))


def send(text):
    if os.environ.get('FEISHU_COLLECTOR_ENABLED') != 'true':
        return False
    url = os.environ.get('FEISHU_COLLECTOR_WEBHOOK_URL', '')
    if not re.fullmatch(r'https://open\.feishu\.cn/open-apis/bot/v2/hook/[A-Za-z0-9-]+', url):
        raise ValueError('Invalid collector webhook configuration')
    payload = {'msg_type': 'text', 'content': {'text': text}}
    result = read_json(urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={'Content-Type': 'application/json'}))
    # An HTTP 200 can still contain a rejected bot message.
    if result.get('code', result.get('StatusCode')) != 0:
        raise RuntimeError('Feishu rejected message: ' + str(result.get('code', result.get('StatusCode'))))
    return True


class Notices:
    def __init__(self, path=None):
        self.path = Path(path or Path(os.environ.get('AIHOT_DATA_DIR', '.data')) / 'collector-notices.json')
        self.state = json.loads(self.path.read_text()) if self.path.exists() else {'pending': []}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(self.state, ensure_ascii=False))
        temp.chmod(0o600)
        temp.replace(self.path)

    def enqueue(self, title, lines):
        stamp = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')
        notice_id = uuid.uuid4().hex[:12]
        self.state['pending'].append({'id': notice_id, 'text': '\n'.join([
            '【游戏研发情报】' + title, *lines, '时间：' + stamp + '（北京时间）', '通知编号：' + notice_id])})
        self.save()

    def flush(self):
        while self.state['pending']:
            try:
                if not send(self.state['pending'][0]['text']):
                    return
            except Exception as exc:
                # Exception strings can contain a webhook or request credentials.
                print('Notification delivery failed: ' + type(exc).__name__, flush=True)
                return
            print('Notification delivered: ' + self.state['pending'][0]['id'], flush=True)
            self.state['pending'].pop(0)
            self.save()

    def authorization_problem(self, now=None):
        now = time.time() if now is None else now
        if now - self.state.get('auth_problem_notice_at', 0) < 86400:
            return
        self.state['auth_problem_notice_at'] = now
        self.enqueue('采集暂缓：授权验证或续期异常', [
            '本次未能确认可用登录态，未继续抓取；不代表必须重新扫码。',
            '可能是网络、接口或凭据保存异常，约 4 小时后重试；同类异常每天最多提醒一次。'])

    def authorization(self, status, collecting, now=None):
        now = time.time() if now is None else now
        previous = self.state.get('auth_status')
        # Network errors and -2041 are not evidence of expiry or recovery.
        if status not in ('valid', 'expired', 'missing'):
            return
        self.state['auth_status'] = status
        if status in ('expired', 'missing') and (previous != status or now - self.state.get('auth_notice_at', 0) >= 86400):
            self.state['auth_notice_at'] = now
            self.enqueue('微信读书授权已过期' if status == 'expired' else '微信读书尚未授权', [
                '无法正常采集新文章，请打开下面的页面重新扫码并在手机上确认。',
                'https://gamehot.paoyou.com/werss/weread',
                '先登录站点，再登录 WeRSS，点击“扫码授权”。',
                '同一问题每天最多提醒一次。'])
        elif status == 'valid' and previous in ('expired', 'missing'):
            self.enqueue('微信读书授权已恢复', [
                '登录凭据已通过验证；各公众号是否采集成功仍以本轮采集结果为准。',
                '自动采集已启用。' if collecting else '自动采集开关仍关闭，尚未开始采集。'])
        self.save()


def auth_status(data):
    cookie = data.get('cookie', '')
    if not cookie:
        return 'missing'
    request = urllib.request.Request('https://weread.qq.com/web/shelf/sync?userVid=&synckey=0',
        headers={'Cookie': cookie, 'Accept': 'application/json', 'Referer': 'https://weread.qq.com/',
                 'User-Agent': 'Mozilla/5.0'})
    try:
        payload = read_json(request)
    except urllib.error.HTTPError as exc:
        # Only an explicit authentication code proves expiry; an HTTP error alone does not.
        payload = json.load(exc)
    code = payload.get('errCode', payload.get('errcode', 0))
    if code in (-2012, -2010):
        return 'expired'
    if code == 0 and isinstance(payload.get('books'), list):
        return 'valid'
    return 'unknown'
