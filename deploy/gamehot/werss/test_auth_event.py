import ast
import json
import os
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from auth_event import authorization_saved


class AuthEventTest(unittest.TestCase):
    def test_marker_is_atomic_credential_free_and_unique_per_save(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'event.json'
            with patch.dict(os.environ, {'GAMEHOT_AUTH_EVENT_FILE': str(path)}):
                authorization_saved()
                first = json.loads(path.read_text())
                authorization_saved()
                second = json.loads(path.read_text())
            self.assertEqual(set(first), {'id'})
            self.assertNotEqual(first, second)
            self.assertFalse(path.with_suffix('.tmp').exists())
            self.assertEqual(path.stat().st_mode & 0o777, 0o644)

    def test_verified_qr_save_emits_event_only_after_persisting_credentials(self):
        # Use the real patched upstream method, without importing its network/browser dependencies.
        source = Path('/app/driver/weread_qr.py').read_text()
        cls = next(n for n in ast.parse(source).body if isinstance(n, ast.ClassDef) and n.name == 'WereadQRLogin')
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '_save_cookies_to_lic')
        calls = []
        config = Mock()
        config.get.return_value = {}
        config.save_config.side_effect = lambda: calls.append('save')
        config.reload.side_effect = lambda: calls.append('reload')
        event = Mock(side_effect=lambda: calls.append('event'))
        config_module = types.ModuleType('core.config'); config_module.Config = Mock(return_value=config)
        event_module = types.ModuleType('core.gamehot_auth_event'); event_module.authorization_saved = event
        namespace = {'auth_locked': lambda fn: fn, 'Dict': dict, 'Any': object, 'os': os, 'json': json,
                     'print_error': Mock(), 'print_success': Mock(), 'print_warning': Mock()}
        exec(compile(ast.Module(body=[method], type_ignores=[]), '<qr-save>', 'exec'), namespace)
        obj = Mock()
        obj._build_cookie_dict.return_value = {'wr_skey': 'synthetic'}
        with patch.dict(sys.modules, {'core.config': config_module, 'core.gamehot_auth_event': event_module}), \
             patch.object(os.path, 'exists', return_value=True), patch.object(os, 'makedirs'):
            obj._verify_cookies.return_value = False
            namespace['_save_cookies_to_lic'](obj, {'vid': 'test'})
            self.assertEqual(calls, [])
            obj._verify_cookies.return_value = True
            namespace['_save_cookies_to_lic'](obj, {'vid': 'test'})
            self.assertEqual(calls, ['save', 'reload', 'event'])
            calls.clear()
            config.save_config.side_effect = RuntimeError('disk failure')
            namespace['_save_cookies_to_lic'](obj, {'vid': 'test'})
            self.assertEqual(calls, [])
