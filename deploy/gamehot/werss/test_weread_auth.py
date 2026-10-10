import io
import json
import sys
import tempfile
import types
import unittest
import urllib.request
from email.message import Message
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.response import addinfourl

from weread_auth import FileStore, WeReadClient, NoRedirect, ensure_authorization

BOOK = 'MP_WXS_1234'
OLD = 'wr_vid=123; wr_skey=old; wr_rt=web%40old; wr_fp=fingerprint'
NEW = 'wr_vid=123; wr_skey=new; wr_rt=web%40new; wr_fp=fingerprint'


class RenewalTest(unittest.TestCase):
    def setUp(self):
        self.store = Mock()
        self.store.read.return_value = {'cookie': OLD, 'managed': False}
        self.store.save.return_value = True
        self.client = Mock()
        self.client.verify.side_effect = ['expired', 'valid']
        self.client.renew.return_value = 'ok'
        self.client.cookie.return_value = NEW
        self.client.verify_article.return_value = 'valid'
        self.factory = Mock(return_value=self.client)

    def run_auth(self, **kwargs):
        return ensure_authorization(BOOK, store=self.store, client_factory=self.factory, **kwargs)

    def test_healthy_session_does_not_renew_or_rewrite(self):
        self.client.verify.side_effect = ['valid']
        result = self.run_auth()
        self.assertEqual(result['status'], 'valid')
        self.assertFalse(result['attempted'])
        self.client.renew.assert_not_called()
        self.store.save.assert_not_called()

    def test_missing_credentials_need_scan_without_network(self):
        self.store.read.return_value['cookie'] = ''
        self.assertEqual(self.run_auth()['status'], 'missing')
        self.factory.assert_not_called()

    def test_expired_session_rotates_both_tokens_after_live_verification(self):
        result = self.run_auth()
        self.assertEqual(result, {'status': 'valid', 'attempted': True, 'renewed': True, 'reason': 'renewed'})
        self.client.renew.assert_called_once()
        self.assertEqual(self.client.verify.call_count, 2)
        self.client.verify_article.assert_called_once_with(BOOK)
        self.store.save.assert_called_once_with({'cookie': OLD, 'managed': False}, NEW)
        self.assertNotIn('web%40', json.dumps(result))

    def test_expired_refresh_token_prompts_scan_and_keeps_old_file(self):
        self.client.renew.return_value = 'expired'
        self.assertEqual(self.run_auth()['status'], 'expired')
        self.store.save.assert_not_called()

    def test_network_unknown_or_risk_control_never_prompts_scan(self):
        self.client.verify.side_effect = ['unknown']
        self.assertEqual(self.run_auth()['status'], 'unknown')
        self.client.renew.assert_not_called()
        self.client.verify.side_effect = ['expired']
        self.client.renew.side_effect = TimeoutError('sensitive-cookie')
        result = self.run_auth()
        self.assertEqual(result['status'], 'unknown')
        self.assertNotIn('sensitive', json.dumps(result))
        self.store.save.assert_not_called()

    def test_no_refresh_cookie_or_read_only_config(self):
        self.store.read.return_value['cookie'] = 'wr_vid=123; wr_skey=old'
        self.assertEqual(self.run_auth()['status'], 'expired')
        self.client.renew.assert_not_called()
        self.client.verify.side_effect = ['expired']
        self.store.read.return_value = {'cookie': OLD, 'managed': True}
        self.assertEqual(self.run_auth()['reason'], 'config_managed')
        self.client.renew.assert_not_called()

    def test_second_check_cannot_make_second_renewal(self):
        self.assertEqual(self.run_auth(allow_renew=False)['status'], 'expired')
        self.client.renew.assert_not_called()

    def test_unverified_or_wrong_account_never_saved(self):
        self.client.cookie.return_value = NEW.replace('wr_vid=123', 'wr_vid=456')
        self.assertEqual(self.run_auth()['status'], 'unknown')
        self.store.save.assert_not_called()
        self.client.verify.side_effect = ['expired', 'valid']
        self.client.cookie.return_value = NEW
        self.client.verify_article.return_value = 'unknown'
        self.assertEqual(self.run_auth()['status'], 'unknown')
        self.store.save.assert_not_called()

    def test_noop_renewal_is_rejected_by_shelf_check(self):
        self.client.cookie.return_value = OLD
        self.client.verify.side_effect = ['expired', 'expired']
        self.assertEqual(self.run_auth()['status'], 'expired')
        self.store.save.assert_not_called()

    def test_new_qr_login_wins_over_inflight_renewal(self):
        def renew():
            self.store.read.return_value = {'cookie': 'wr_vid=999; wr_skey=scan', 'managed': False}
            return 'ok'
        self.client.renew.side_effect = renew
        self.assertEqual(self.run_auth()['reason'], 'credentials_changed')
        self.store.save.assert_not_called()

    def test_commit_conflict_and_disk_failure_never_claim_recovery(self):
        self.store.save.return_value = False
        self.assertEqual(self.run_auth()['reason'], 'credentials_changed')
        self.client.verify.side_effect = ['expired', 'valid']
        self.store.save.side_effect = OSError('secret-path')
        self.assertEqual(self.run_auth()['status'], 'unknown')

    def test_invalid_feed_never_contacts_any_service(self):
        result = ensure_authorization('https://attacker.test', store=self.store, client_factory=self.factory)
        self.assertEqual(result['status'], 'unknown')
        self.factory.assert_not_called()


class TransportTest(unittest.TestCase):
    def setUp(self):
        guard = patch('socket.socket.connect', side_effect=AssertionError('External network forbidden in tests'))
        guard.start()
        self.addCleanup(guard.stop)

    def test_real_cookiejar_rotates_refresh_and_session_cookies_without_duplicates(self):
        seen = []
        class StubHTTPS(urllib.request.HTTPSHandler):
            def https_open(self, req):
                seen.append(req)
                headers = Message()
                if len(seen) == 1:
                    headers.add_header('Set-Cookie', 'wr_skey=new; Domain=.weread.qq.com; Path=/; Secure; HttpOnly')
                    headers.add_header('Set-Cookie', 'wr_rt=web%40new; Domain=.weread.qq.com; Path=/; Secure; HttpOnly')
                    payload = {}
                elif len(seen) == 2:
                    payload = {'books': []}
                else:
                    payload = {'reviewId': 'article-id'}
                response = addinfourl(io.BytesIO(json.dumps(payload).encode()), headers, req.full_url, 200)
                response.msg = 'OK'
                return response
        client = WeReadClient(OLD)
        client.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(client.jar), StubHTTPS())
        self.assertEqual(client.renew(), 'ok')
        self.assertEqual(client.verify(), 'valid')
        self.assertEqual(client.verify_article(BOOK), 'valid')
        self.assertEqual(seen[0].full_url, 'https://weread.qq.com/web/login/renewal')
        self.assertEqual(json.loads(seen[0].data), {'rq': '%2Fweb%2Fbook%2Fread', 'ql': True})
        for request in seen[1:]:
            cookie = request.get_header('Cookie')
            self.assertIn('wr_rt=web%40new', cookie)
            self.assertIn('wr_fp=fingerprint', cookie)
            self.assertEqual(cookie.count('wr_skey='), 1)
            self.assertNotIn('wr_skey=old', cookie)
        self.assertNotIn('/web/mp/articles', str([r.full_url for r in seen]))

    def test_business_codes_and_http_errors(self):
        client = WeReadClient(OLD)
        for response, expected in [((200, {'errCode': -2041}), 'unknown'), ((403, {}), 'unknown'),
                                   ((401, {'errCode': -2012}), 'expired'), ((200, {'books': []}), 'valid')]:
            with self.subTest(response=response), patch.object(client, 'request', return_value=response):
                self.assertEqual(client.verify(), expected)
        with patch.object(client, 'request', return_value=(200, {'errCode': -2013})):
            self.assertEqual(client.renew(), 'expired')

    def test_redirects_cannot_leak_cookies(self):
        class StubHTTPS(urllib.request.HTTPSHandler):
            def https_open(self, req):
                headers = Message(); headers['Location'] = 'https://attacker.test/'
                response = addinfourl(io.BytesIO(b''), headers, req.full_url, 302)
                response.msg = 'Found'
                return response
        client = WeReadClient(OLD); client.opener = urllib.request.build_opener(NoRedirect(), urllib.request.HTTPCookieProcessor(client.jar), StubHTTPS())
        self.assertEqual(client.verify(), 'unknown')


class StorageTest(unittest.TestCase):
    def test_atomic_write_preserves_other_sections_and_rejects_stale_cookie(self):
        # JSON is a YAML subset; use a tiny parser substitute for local stdlib-only tests.
        yaml = types.SimpleNamespace(safe_load=json.loads,
            safe_dump=lambda doc, f, **kw: json.dump(doc, f))
        config = types.ModuleType('core.config'); config.cfg = Mock(); config.cfg.get.return_value = ''
        with tempfile.TemporaryDirectory() as folder, patch.dict(sys.modules, {'yaml': yaml, 'core.config': config}):
            path = Path(folder) / 'wx.lic'
            doc = {'token_data': {'unrelated': 'keep'}, 'weread_data': {'cookie': OLD, 'name': 'reader', 'ticket': 'keep'}}
            path.write_text(json.dumps(doc)); store = FileStore(path); expected = store.read()
            with patch('weread_auth.os.replace', side_effect=OSError('disk failure')):
                with self.assertRaises(OSError): store.save(expected, NEW)
            self.assertEqual(json.loads(path.read_text()), doc)
            self.assertEqual(len(list(Path(folder).iterdir())), 1)
            self.assertTrue(store.save(expected, NEW))
            saved = json.loads(path.read_text())
            self.assertEqual(saved['token_data'], doc['token_data'])
            self.assertEqual(saved['weread_data']['name'], 'reader')
            self.assertEqual(saved['weread_data']['ticket'], 'keep')
            self.assertEqual(saved['weread_data']['vid'], '123')
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertFalse(store.save(expected, OLD))
            self.assertEqual(json.loads(path.read_text()), saved)
