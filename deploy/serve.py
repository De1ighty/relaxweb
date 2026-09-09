"""静态文件服务：白名单只提供公开前端文件，所有响应带 no-cache。

允许的路径：
  /                 -> index.html
  /assets/<文件名>  -> assets 目录下的单个文件（禁止路径穿越）
其余任何路径一律 404，防止源码、数据库、备份文件被下载。
"""
import http.server
import os
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
DEAD_END = os.path.join(ROOT, "__forbidden__")


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def translate_path(self, path):
        clean = os.path.normpath(
            unquote(path.split("?", 1)[0].split("#", 1)[0])
        )
        if clean in ("", "/", ".", os.sep, "/index.html"):
            return os.path.join(ROOT, "index.html")
        if clean.startswith("/assets/"):
            return os.path.join(ASSETS, os.path.basename(clean[len("/assets/"):]))
        return DEAD_END

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()
