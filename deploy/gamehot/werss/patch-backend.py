"""Add an ASGI root path for generated documentation URLs behind the subpath proxy."""
from pathlib import Path
import re
path = Path("/app/web.py")
source = path.read_text()
needle = 'app = FastAPI('
assert source.count(needle) == 1, "Pinned WeRSS source changed"
path.write_text(source.replace(needle, 'app = FastAPI(\n    root_path="/werss",', 1))
# Native reader templates and breadcrumb links also use absolute root paths.
for folder, pattern in [(Path("/app/public/templates"), "*.html"), (Path("/app/views"), "*.py")]:
    for file in folder.rglob(pattern):
        text = file.read_text()
        file.write_text(re.sub(r'''(["'])/(static|assets|files|views|feed|proxy|rss|api)(?=[/?])''', r"\1/werss/\2", text))
