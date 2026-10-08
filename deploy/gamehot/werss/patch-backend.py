"""Add an ASGI root path for generated documentation URLs behind the subpath proxy."""
from pathlib import Path
import re
path = Path("/app/web.py")
source = path.read_text()
needle = 'app = FastAPI('
assert source.count(needle) == 1, "Pinned WeRSS source changed"
path.write_text(source.replace(needle, 'app = FastAPI(\n    root_path="/werss",', 1))
# Uvicorn must include root_path in the ASGI path so mounted StaticFiles strip it correctly.
main = Path("/app/main.py")
source = main.read_text()
needle = 'uvicorn.run("web:app", host='
assert source.count(needle) == 1, "Pinned WeRSS launcher changed"
source = source.replace(needle, 'uvicorn.run("web:app", root_path="/werss", host=', 1)
env_dump = '    print("环境变量:")\n    for k,v in os.environ.items():\n        print(f"{k}={v}")\n'
assert env_dump in source, "Pinned WeRSS environment dump changed"
main.write_text(source.replace(env_dump, ""))
# Native reader templates and breadcrumb links also use absolute root paths.
for folder, pattern in [(Path("/app/public/templates"), "*.html"), (Path("/app/views"), "*.py")]:
    for file in folder.rglob(pattern):
        text = file.read_text()
        file.write_text(re.sub(r'''(["'])/(static|assets|files|views|feed|proxy|rss|api)(?=[/?])''', r"\1/werss/\2", text))
