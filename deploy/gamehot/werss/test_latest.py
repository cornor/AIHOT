"""Run inside the pinned WeRSS image with --network none; credentials and database are stubbed."""
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


class Parent:
    def FillBack(self, CallBack, data, Ext_Data):
        if CallBack(data):
            self.articles.append(data)

    def Over(self, CallBack=None):
        pass


def module(name, **values):
    item = types.ModuleType(name)
    item.__dict__.update(values)
    return item


stubs = {
    'core.log': module('core.log', logger=Mock()),
    'core.models.feed': module('core.models.feed', Feed=lambda **kw: kw),
    'core.print': module('core.print', print_info=Mock(), print_warning=Mock()),
    'core.wx.model.weread': module('core.wx.model.weread', MpsWeread=Parent),
}
spec = importlib.util.spec_from_file_location('latest_subject', Path(__file__).with_name('weread_mp.py'))
subject = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, stubs):
    spec.loader.exec_module(subject)

STAMP = 1791514680
BOOK = 'MP_WXS_2399768513'
REVIEW = BOOK + '_test~token'
HTML = '<script>var ct=et(r,G);</script><script>var ct = "1791514680";</script><div id="js_content"><p>Actual article</p><script>unsafe()</script></div>'


class LatestTest(unittest.TestCase):
    def make(self, html=HTML):
        obj = subject.MpsWereadMP()
        obj.articles = []
        obj._get_mp_cover = Mock(return_value={'title': 'Latest', 'reviewId': REVIEW})
        obj._is_article_gathered = Mock(side_effect=[False, True])
        obj._get_feed_update_time = Mock(return_value=STAMP - 100)
        obj._get_content_interval = Mock(return_value=0)
        obj._get_mp_document = Mock(return_value=html)
        return obj

    def collect(self, obj, save=None):
        return obj._collect_latest_via_cover(BOOK, BOOK, 'Feed', True, CallBack=save or Mock(return_value=True))

    def test_real_metadata_is_preserved_and_scripts_removed(self):
        obj = self.make()
        self.assertEqual(self.collect(obj), STAMP)
        item = obj.articles[0]
        self.assertEqual(item['create_time'], STAMP)
        self.assertEqual(item['update_time'], STAMP)
        self.assertEqual(item['link'], 'https://mp.weixin.qq.com/s/test_token')
        self.assertIn('Actual article', item['content'])
        self.assertNotIn('unsafe', item['content'])

    def test_duplicate_does_not_fetch_body_or_write_again(self):
        obj = self.make()
        obj._is_article_gathered = Mock(return_value=True)
        save = Mock(return_value=True)
        self.assertEqual(self.collect(obj, save), STAMP - 100)
        obj._get_mp_document.assert_not_called()
        save.assert_not_called()

    def test_missing_conflicting_future_or_body_only_dates_fail_without_write(self):
        values = [
            '<div id="js_content">body</div>',
            HTML + '<script>var ct = "1791514681";</script>',
            HTML.replace(str(STAMP), '9999999999'),
            '<div id="js_content"><script>var ct = "1791514680";</script>body</div>',
            '<p>var ct = "1791514680";</p><div id="js_content">body</div>',
        ]
        for html in values:
            with self.subTest(html=html):
                obj = self.make(html)
                save = Mock()
                with self.assertRaises(subject.WereadMPAPIError):
                    self.collect(obj, save)
                save.assert_not_called()

    def test_challenge_and_empty_body_are_not_saved(self):
        for html in ['<p>verification required</p>', '<script>var ct = "1791514680";</script><div id="js_content"></div>']:
            obj = self.make(html)
            with self.assertRaises(subject.WereadMPAPIError):
                self.collect(obj)
            self.assertEqual(obj.articles, [])

    def test_wrong_feed_identity_is_rejected(self):
        obj = self.make()
        obj._get_mp_cover.return_value['reviewId'] = 'MP_WXS_other_token'
        with self.assertRaises(subject.WereadMPAPIError):
            self.collect(obj)
        obj._get_mp_document.assert_not_called()

    def test_database_save_failure_is_not_reported_as_success(self):
        obj = self.make()
        obj._is_article_gathered = Mock(return_value=False)
        with self.assertRaisesRegex(subject.WereadMPAPIError, 'save_failed'):
            self.collect(obj)

    def test_latest_mode_never_calls_broken_list_and_only_commits_sync_after_success(self):
        obj = self.make()
        obj.get_token = Mock()
        obj._load_weread_auth = Mock()
        obj._weread_cookies = 'synthetic'
        obj.ensure_mp_on_shelf = Mock(return_value=(True, 'ok'))
        obj.Gather_Content = True
        obj._collect_via_article_list = Mock(side_effect=AssertionError('list must not be called'))
        obj.update_mps = Mock()
        with patch.dict(os.environ, {'WERSS_LATEST_ONLY': 'true'}):
            obj.get_Articles(Mps_id=BOOK, CallBack=Mock(return_value=True))
        obj._collect_via_article_list.assert_not_called()
        self.assertEqual(obj.update_mps.call_args.args[1]['update_time'], STAMP)
        obj.update_mps.reset_mock()
        obj._is_article_gathered = Mock(return_value=False)
        obj._get_mp_document.return_value = '<p>missing body and date</p>'
        with patch.dict(os.environ, {'WERSS_LATEST_ONLY': 'true'}), self.assertRaises(subject.WereadMPAPIError):
            obj.get_Articles(Mps_id=BOOK, CallBack=Mock(return_value=True))
        obj.update_mps.assert_not_called()

    def test_normal_list_mode_does_not_silently_switch_to_partial_coverage(self):
        obj = self.make()
        obj.get_token = Mock()
        obj._load_weread_auth = Mock()
        obj._weread_cookies = 'synthetic'
        obj.ensure_mp_on_shelf = Mock(return_value=(True, 'ok'))
        obj.Gather_Content = True
        obj._collect_via_article_list = Mock(side_effect=subject.WereadMPAPIError(-2041, 'test'))
        obj.update_mps = Mock()
        with patch.dict(os.environ, {'WERSS_LATEST_ONLY': 'false'}), self.assertRaises(subject.WereadMPAPIError):
            obj.get_Articles(Mps_id=BOOK)
        obj._get_mp_cover.assert_not_called()
        obj.update_mps.assert_not_called()


if __name__ == '__main__':
    unittest.main()
