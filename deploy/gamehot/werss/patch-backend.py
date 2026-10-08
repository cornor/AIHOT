"""Add an ASGI root path for generated documentation URLs behind the subpath proxy."""
from pathlib import Path
path = Path("/app/web.py")
source = path.read_text()
needle = 'app = FastAPI('
assert source.count(needle) == 1, "Pinned WeRSS source changed"
path.write_text(source.replace(needle, 'app = FastAPI(\n    root_path="/werss",', 1))
