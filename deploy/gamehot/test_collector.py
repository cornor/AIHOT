import json
import io
import os
import subprocess
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

import collector
import notifications


class NotificationsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'state.json'
        self.notices = notifications.Notices(self.path)
        collector.stop.clear()

    def test_expiry_dedup_survives_restart_and_recovers_once(self):
        self.notices.authorization('expired', False, now=100000)
        self.assertEqual(len(self.notices.state['pending']), 1)
        reloaded = notifications.Notices(self.path)
        reloaded.authorization('expired', False, now=100100)
        reloaded.authorization('unknown', False, now=100200)
        self.assertEqual(len(reloaded.state['pending']), 1)
        reloaded.authorization('valid', False, now=100300)
        reloaded.authorization('valid', False, now=100400)
        self.assertEqual(len(reloaded.state['pending']), 2)
        self.assertIn('开关仍关闭', reloaded.state['pending'][1]['text'])

    def test_expiry_repeat_is_at_most_daily(self):
        self.notices.authorization('expired', True, now=100000)
        self.notices.authorization('expired', True, now=186399)
        self.assertEqual(len(self.notices.state['pending']), 1)
        self.notices.authorization('expired', True, now=186400)
        self.assertEqual(len(self.notices.state['pending']), 2)

    def test_healthy_start_does_not_send_recovery(self):
        self.notices.authorization('valid', True)
        self.assertEqual(self.notices.state['pending'], [])

    def test_failed_delivery_is_persisted_and_retries_same_id(self):
        self.notices.enqueue('测试', ['正文'])
        notice = self.notices.state['pending'][0]
        with patch.object(notifications, 'send', side_effect=TimeoutError('secret-url')):
            self.notices.flush()
        reloaded = notifications.Notices(self.path)
        self.assertEqual(reloaded.state['pending'][0], notice)
        with patch.object(notifications, 'send', return_value=True) as sender:
            reloaded.flush()
            sender.assert_called_once_with(notice['text'])
        self.assertEqual(notifications.Notices(self.path).state['pending'], [])

    def test_disabled_notifications_never_contact_network_or_discard_pending(self):
        self.notices.enqueue('测试', ['正文'])
        with patch.dict(os.environ, {'FEISHU_COLLECTOR_ENABLED': 'false'}), patch.object(notifications, 'read_json') as network:
            self.notices.flush()
            network.assert_not_called()
        self.assertEqual(len(self.notices.state['pending']), 1)

    def test_feishu_business_error_not_treated_as_delivery(self):
        env = {'FEISHU_COLLECTOR_ENABLED': 'true', 'FEISHU_COLLECTOR_WEBHOOK_URL': 'https://open.feishu.cn/open-apis/bot/v2/hook/test-only'}
        with patch.dict(os.environ, env), patch.object(notifications, 'read_json', return_value={'code': 19024}):
            with self.assertRaises(RuntimeError): notifications.send('test')
        with patch.dict(os.environ, env), patch.object(notifications, 'read_json', return_value={}):
            with self.assertRaises(RuntimeError): notifications.send('test')

    def test_only_explicit_auth_errors_prompt_scan(self):
        for payload, expected in [({'errCode': -2041}, 'unknown'), ({'errCode': -2012}, 'expired'),
                                  ({'errCode': -2010}, 'expired'), ({'books': []}, 'valid'), ({}, 'unknown')]:
            with self.subTest(payload=payload), patch.object(notifications, 'read_json', return_value=payload):
                self.assertEqual(notifications.auth_status({'cookie': 'test-only'}), expected)
        self.assertEqual(notifications.auth_status({}), 'missing')

    def test_expiry_in_http_error_is_recognized(self):
        error = urllib.error.HTTPError('https://weread.qq.com', 401, 'Unauthorized', {}, io.BytesIO(b'{"errCode":-2012}'))
        with patch.object(notifications, 'read_json', side_effect=error):
            self.assertEqual(notifications.auth_status({'cookie': 'test-only'}), 'expired')

    def test_renewal_outcomes_notify_only_after_final_result(self):
        with patch.dict(os.environ, {'FEISHU_COLLECTOR_ENABLED': 'true', 'COLLECT_ENABLED': 'true'}), \
             patch.object(collector, 'request', return_value={'status': 'valid', 'attempted': True, 'renewed': True}) as req:
            state = {}
            self.assertEqual(collector.check_authorization(self.notices, 'test', 'MP_WXS_123', renewal_state=state), 'valid')
            self.assertTrue(state['attempted'])
            req.assert_called_once_with('/weread/ensure-auth', {'book_id': 'MP_WXS_123', 'allow_renew': True}, token='test', timeout=110)
            self.assertEqual(self.notices.state['pending'], [])
            req.return_value = {'status': 'expired', 'attempted': True, 'renewed': False}
            collector.check_authorization(self.notices, 'test', 'MP_WXS_123')
            self.assertEqual(len(self.notices.state['pending']), 1)
            collector.check_authorization(self.notices, 'test', 'MP_WXS_123')
            self.assertEqual(len(self.notices.state['pending']), 1)

    def test_unknown_notice_is_daily_across_restart(self):
        self.notices.authorization_problem(now=100000)
        reloaded = notifications.Notices(self.path)
        reloaded.authorization_problem(now=100001)
        self.assertEqual(len(reloaded.state['pending']), 1)
        self.assertNotIn('授权已过期', reloaded.state['pending'][0]['text'])
        reloaded.authorization_problem(now=186400)
        self.assertEqual(len(reloaded.state['pending']), 2)

    def test_verification_runs_even_with_feishu_off(self):
        path = Path(self.temp.name) / 'feeds.json'
        path.write_text('[{"name":"测试","feedId":"MP_WXS_123"}]')
        with patch.dict(os.environ, {'COLLECT_ENABLED': 'true', 'FEISHU_COLLECTOR_ENABLED': 'false', 'WERSS_FEEDS_FILE': str(path)}), \
             patch.object(collector, 'login', return_value='test'), \
             patch.object(collector, 'request', return_value={'status': 'unknown', 'attempted': True}) as req, \
             patch.object(collector.subprocess, 'run') as imports:
            self.assertFalse(collector.cycle(self.notices))
            self.assertEqual(req.call_count, 1)
            self.assertEqual(req.call_args.args[0], '/weread/ensure-auth')
            imports.assert_not_called()
        self.assertEqual(self.notices.state['pending'], [])

    def test_mid_cycle_check_reuses_renewal_budget(self):
        with patch.object(collector, 'check_authorization') as check:
            def verified(*args, **kwargs):
                kwargs['renewal_state']['attempted'] = True
                return 'valid'
            check.side_effect = verified
            self.run_cycle(subprocess.CompletedProcess([], 1, '', ''), failed=True, monitor=True)
            self.assertFalse(check.call_args.kwargs['allow_renew'])

    def test_werss_nested_error_preserves_code_without_credentials(self):
        error = urllib.error.HTTPError('http://127.0.0.1', 400, 'Bad request', {},
            io.BytesIO(b'{"detail":{"code":400,"message":"secret","data":{"code":-2041}}}'))
        with patch.object(collector.urllib.request, 'urlopen', side_effect=error):
            with self.assertRaises(collector.WeRSSError) as caught:
                collector.request('/weread/collect', {})
        self.assertEqual(caught.exception.code, -2041)
        self.assertNotIn('secret', str(caught.exception))

    def test_timeout_does_not_clear_expired_state(self):
        self.notices.authorization('expired', False)
        with patch.object(collector, 'login', side_effect=TimeoutError):
            collector.check_authorization(self.notices)
        self.assertEqual(self.notices.state['auth_status'], 'expired')
        self.assertEqual(len(self.notices.state['pending']), 1)

    def run_cycle(self, import_result, failed=False, monitor=False):
        feeds = [{'name': '测试甲', 'feedId': 'a'}, {'name': '测试乙', 'feedId': 'b'}]
        path = Path(self.temp.name) / 'feeds.json'
        path.write_text(json.dumps(feeds))
        responses = [{'collected': 2}, collector.WeRSSError({'data': {'code': -2041}}) if failed else {'collected': 0}]
        def respond(route, *args, **kwargs):
            if route == '/weread/ensure-auth':
                return {'status': 'valid', 'attempted': False}
            result = responses.pop(0)
            if isinstance(result, Exception):
                raise result
            return result
        with patch.dict(os.environ, {'COLLECT_ENABLED': 'true', 'WERSS_FEEDS_FILE': str(path),
                                    'FEISHU_COLLECTOR_ENABLED': 'true' if monitor else 'false'}), \
             patch.object(collector, 'login', return_value='test'), patch.object(collector, 'request', side_effect=respond), \
             patch.object(collector.subprocess, 'run', return_value=import_result):
            collector.cycle(self.notices)
        return self.notices.state['pending'][0]['text']

    def test_partial_collection_counts_and_async_model_wording(self):
        result = subprocess.CompletedProcess([], 0, '\n'.join(json.dumps(row) for row in [
            {'source': '测试甲', 'created': 2, 'revised': 0}, {'source': '测试乙', 'created': 0, 'revised': 1}]), '')
        text = self.run_cycle(result, failed=True)
        self.assertIn('成功 1/2，失败 1', text)
        self.assertIn('新增 2 篇，更新 1 篇', text)
        self.assertIn('测试乙（-2041）', text)
        self.assertNotIn('授权已过期', text)
        self.assertIn('不代表 DeepSeek 摘要已完成', text)

    def test_import_crash_does_not_claim_success(self):
        text = self.run_cycle(subprocess.CompletedProcess([], 1, '', 'secret-url'))
        self.assertIn('有异常', text)
        self.assertIn('结果不完整', text)
        self.assertNotIn('secret-url', text)

    def test_latest_only_summary_discloses_incomplete_coverage(self):
        with patch.dict(os.environ, {'WERSS_LATEST_ONLY': 'true'}):
            text = self.run_cycle(subprocess.CompletedProcess([], 0, '\n'.join([
                json.dumps({'source': name, 'created': 0, 'revised': 0}) for name in ['测试甲', '测试乙']]), ''))
        self.assertIn('每个公众号每轮只取最新一篇', text)
        self.assertIn('其他文章可能漏采', text)

    def test_collection_disabled_sends_no_fake_summary(self):
        with patch.dict(os.environ, {'COLLECT_ENABLED': 'false', 'FEISHU_COLLECTOR_ENABLED': 'true'}), \
             patch.object(collector, 'login') as login, patch.object(collector, 'check_authorization') as auth:
            collector.cycle(self.notices)
            login.assert_not_called()
            auth.assert_not_called()
        self.assertEqual(self.notices.state['pending'], [])

    def test_failed_collection_rechecks_auth_without_periodic_polling(self):
        with patch.object(collector, 'check_authorization', return_value='valid') as check:
            self.run_cycle(subprocess.CompletedProcess([], 1, '', ''), failed=True, monitor=True)
        self.assertEqual(check.call_count, 2)

    def test_expired_authorization_skips_article_requests(self):
        path = Path(self.temp.name) / 'feeds.json'
        path.write_text('[{"name":"测试","feedId":"test"}]')
        with patch.dict(os.environ, {'COLLECT_ENABLED': 'true', 'FEISHU_COLLECTOR_ENABLED': 'true',
                                    'WERSS_FEEDS_FILE': str(path)}), \
             patch.object(collector, 'login', return_value='test'), \
             patch.object(collector, 'check_authorization', return_value='expired'), \
             patch.object(collector, 'request') as articles, patch.object(collector.subprocess, 'run') as imports:
            collector.cycle(self.notices)
            articles.assert_not_called()
            imports.assert_not_called()
        # No completion summary: the auth checker owns the scan reminder.
        self.assertEqual(self.notices.state['pending'], [])


if __name__ == '__main__':
    unittest.main()
