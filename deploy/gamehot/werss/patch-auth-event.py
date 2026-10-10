"""Notify the collector only after QR authorization is verified and saved."""
from pathlib import Path

path = Path('/app/driver/weread_qr.py')
source = path.read_text()
needle = '            cfg.reload()\n            print_success(f"Weread QR: Cookie 已保存'
assert source.count(needle) == 1, 'Pinned WeRSS QR save path changed'
replacement = '''            cfg.reload()
            try:
                from core.gamehot_auth_event import authorization_saved
                authorization_saved()
            except Exception:
                print_warning("Gamehot: 无法通知采集器授权已保存")
            print_success(f"Weread QR: Cookie 已保存'''
path.write_text(source.replace(needle, replacement, 1))
