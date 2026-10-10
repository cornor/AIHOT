"""Renew WeRead sessions at collection time; never return or log credentials."""
import functools
import http.cookiejar
from http.cookies import SimpleCookie
import json
import os
import re
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

AUTH_LOCK = threading.RLock()
RENEW_LOCK = threading.Lock()
BASE = 'https://weread.qq.com'
SHELF = '/web/shelf/sync?userVid=&synckey=0'


def auth_locked(fn):
    @functools.wraps(fn)
    def wrapped(*args, **kwargs):
        with AUTH_LOCK:
            return fn(*args, **kwargs)
    return wrapped


def cookies_of(raw):
    # Preserve URL-encoded refresh tokens exactly, and reject ambiguous duplicate keys.
    result = {}
    for part in raw.split(';'):
        if '=' not in part:
            continue
        key, value = part.strip().split('=', 1)
        if key in result and result[key] != value:
            raise ValueError('Ambiguous cookie')
        if '\r' in value or '\n' in value:
            raise ValueError('Invalid cookie')
        result[key] = value
    return result


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


class WeReadClient:
    def __init__(self, cookie):
        self.jar = http.cookiejar.CookieJar()
        for name, value in cookies_of(cookie).items():
            self.jar.set_cookie(http.cookiejar.Cookie(0, name, value, None, False,
                'weread.qq.com', True, False, '/', True, True, None, True, None, None, {}))
        self.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(self.jar))

    def request(self, path, body=None):
        headers = {'Accept': 'application/json, text/plain, */*', 'Origin': BASE,
                   'Referer': BASE + '/', 'User-Agent': 'Mozilla/5.0',
                   'Content-Type': 'application/json'}
        data = json.dumps(body, separators=(',', ':')).encode() if body is not None else None
        req = urllib.request.Request(BASE + path, data=data, headers=headers)
        try:
            response = self.opener.open(req, timeout=20)
        except urllib.error.HTTPError as exc:
            response = exc
        with response:
            # A rotated cookie may use .weread.qq.com while the stored seed was host-only.
            # Keep only the just-issued variant, so the next request never sends stale duplicates.
            for header in response.headers.get_all('Set-Cookie', []):
                changed = SimpleCookie()
                changed.load(header)
                for name, morsel in changed.items():
                    domain = (morsel['domain'] or 'weread.qq.com').lstrip('.')
                    path = morsel['path'] or '/'
                    if domain != 'weread.qq.com':
                        continue
                    for cookie in list(self.jar):
                        if cookie.name == name and (cookie.domain.lstrip('.') != domain or cookie.path != path or cookie.value != morsel.value):
                            self.jar.clear(cookie.domain, cookie.path, cookie.name)
            raw = response.read(2 * 1024 * 1024 + 1)
            if len(raw) > 2 * 1024 * 1024:
                return response.status, {}
            try:
                payload = json.loads(raw)
            except ValueError:
                payload = {}
            return response.status, payload if isinstance(payload, dict) else {}

    def cookie(self):
        return '; '.join(f'{c.name}={c.value}' for c in self.jar
                         if c.domain.lstrip('.') == 'weread.qq.com' and not c.is_expired())

    def verify(self):
        status, payload = self.request(SHELF)
        code = payload.get('errCode', payload.get('errcode', 0))
        if code in (-2012, -2010):
            return 'expired'
        if status == 200 and code == 0 and isinstance(payload.get('books'), list):
            return 'valid'
        return 'unknown'

    def renew(self):
        status, payload = self.request('/web/login/renewal', {'rq': '%2Fweb%2Fbook%2Fread', 'ql': True})
        code = payload.get('errCode', payload.get('errcode', 0))
        if code in (-2012, -2010, -2013):
            return 'expired'
        return 'ok' if status == 200 and code == 0 else 'unknown'

    def verify_article(self, book_id):
        status, payload = self.request('/api/mp/cover?' + urllib.parse.urlencode({'bookId': book_id}))
        code = payload.get('errCode', payload.get('errcode', 0))
        if code in (-2012, -2010):
            return 'expired'
        return 'valid' if status == 200 and code == 0 and isinstance(payload.get('reviewId'), str) and payload['reviewId'] else 'unknown'


class FileStore:
    def __init__(self, path='./data/wx.lic'):
        self.path = Path(path)

    def _document(self):
        import yaml
        doc = yaml.safe_load(self.path.read_text()) if self.path.exists() else {}
        if not isinstance(doc, dict):
            raise ValueError('Invalid credential document')
        data = doc.get('weread_data', {})
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise ValueError('Invalid credential section')
        return doc, data

    @auth_locked
    def read(self):
        from core.config import cfg
        _, data = self._document()
        override = cfg.get('weread.cookie', '')
        return {'cookie': override or data.get('cookie', ''), 'managed': bool(override)}

    @auth_locked
    def save(self, expected, cookie):
        import yaml
        if self.read() != expected:
            return False
        doc, data = self._document()
        data.update(cookie=cookie, vid=cookies_of(cookie)['wr_vid'], cookie_refresh_last_ts=time.time())
        doc['weread_data'] = data
        # A crash or full disk leaves the old complete document in place.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=self.path.parent, delete=False) as f:
                name = f.name
                os.fchmod(f.fileno(), 0o600)
                yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)
        return True


def ensure_authorization(book_id, allow_renew=True, store=None, client_factory=WeReadClient):
    if not re.fullmatch(r'MP_WXS_\d+', book_id):
        return {'status': 'unknown', 'renewed': False, 'reason': 'invalid_feed'}
    store = store or FileStore()
    attempted = False
    def result(status, reason, renewed=False):
        return {'status': status, 'renewed': renewed, 'attempted': attempted, 'reason': reason}
    # Serialize simultaneous collection/admin requests. QR saves use AUTH_LOCK, not this lock.
    with RENEW_LOCK:
        try:
            original = store.read()
            raw = original['cookie']
            if not raw:
                return result('missing', 'no_cookie')
            old = cookies_of(raw)
            client = client_factory(raw)
            status = client.verify()
            if store.read() != original:
                return result('unknown', 'credentials_changed')
            if status != 'expired':
                return result(status, 'session_check')
            if not allow_renew:
                return result('expired', 'session_expired')
            if original.get('managed'):
                return result('unknown', 'config_managed')
            if not old.get('wr_rt') or not old.get('wr_vid'):
                return result('expired', 'no_refresh_cookie')
            attempted = True
            status = client.renew()
            if status != 'ok':
                # A QR login performed during the request takes precedence over its old outcome.
                if store.read() != original:
                    return result('unknown', 'credentials_changed')
                return result(status, 'renewal_rejected' if status == 'expired' else 'renewal_unavailable')
            candidate = client.cookie()
            new = cookies_of(candidate)
            if new.get('wr_vid') != old['wr_vid'] or not new.get('wr_skey'):
                return result('unknown', 'invalid_renewal_identity')
            status = client.verify()
            if status == 'valid':
                status = client.verify_article(book_id)
            if store.read() != original:
                return result('unknown', 'credentials_changed')
            if status != 'valid':
                return result(status, 'renewal_verification_failed')
            if not store.save(original, candidate):
                return result('unknown', 'credentials_changed')
            return result('valid', 'renewed', True)
        except Exception:
            # Error strings and HTTP bodies may contain secrets. Return only a fixed reason.
            return result('unknown', 'request_or_storage_failed')
