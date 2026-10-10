"""Add a private authenticated endpoint and serialize QR/manual credential writes."""
import ast
from pathlib import Path

api = Path('/app/apis/weread.py')
s = api.read_text()
needle = 'def _save_weread_data(data: dict):'
assert s.count(needle) == 1
s = s.replace(needle, 'from core.gamehot_weread_auth import AUTH_LOCK, auth_locked, ensure_authorization\n\n\n@auth_locked\n' + needle)
# Manual edits must read and write under the same lock as QR saves and renewal commits.
for name in ['save_weread_cookie', 'save_weread_config']:
    node = next(n for n in ast.parse(s).body if isinstance(n, ast.AsyncFunctionDef) and n.name == name)
    lines = s.splitlines(keepends=True)
    start, end = node.body[0].lineno - 1, node.end_lineno
    lines[start:end] = ['    with AUTH_LOCK:\n'] + ['    ' + line for line in lines[start:end]]
    s = ''.join(lines)
s += '''

class EnsureAuthRequest(BaseModel):
    book_id: str
    allow_renew: bool = True


@router.post("/ensure-auth", summary="采集前验证并尝试续期微信读书授权")
def ensure_weread_auth(req: EnsureAuthRequest, current_user=Depends(get_current_user_or_ak)):
    if os.environ.get("GAMEHOT_WEREAD_RENEW_ENABLED") != "true":
        return success_response({"status": "unknown", "renewed": False, "attempted": False, "reason": "collection_disabled"})
    return success_response(ensure_authorization(req.book_id, req.allow_renew))
'''
api.write_text(s)
qr = Path('/app/driver/weread_qr.py')
s = qr.read_text()
needle = '    def _save_cookies_to_lic(self, result: Dict[str, Any]):'
assert s.count(needle) == 1
s = s.replace(needle, '    @auth_locked\n' + needle)
# Keep the module docstring intact.
needle = 'import json'
assert needle in s
s = s.replace(needle, 'from core.gamehot_weread_auth import auth_locked\nimport json', 1)
qr.write_text(s)
