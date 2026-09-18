"""静态文件服务：白名单只提供公开前端文件，所有响应带 no-cache。

允许的路径：
  /                    -> index.html
  /game                -> game.html
  /assets/<路径>       -> assets 目录下的静态资源（可含子目录，如 assets/js/games/uno.js）
其余任何路径一律 404，防止源码、数据库、备份文件被下载。
"""
import http.server
import os
from urllib.parse import unquote

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
DEAD_END = os.path.join(ROOT, "__forbidden__")

# 只放行这几类静态资源：源码（.py）、数据库、备份文件都在白名单之外
ALLOWED_EXT = {".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico", ".webp",
               ".woff", ".woff2", ".json"}


def asset_path(rel):
    """把 assets 下的相对路径解析成真实文件；越界或后缀不在白名单都返回 None。"""
    target = os.path.normpath(os.path.join(ASSETS, rel))
    if target != ASSETS and not target.startswith(ASSETS + os.sep):
        return None
    if os.path.isdir(target):
        return None                     # 不给目录列表
    if os.path.splitext(target)[1].lower() not in ALLOWED_EXT:
        return None
    return target


class Handler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=ROOT, **kwargs)

    def translate_path(self, path):
        clean = os.path.normpath(
            unquote(path.split("?", 1)[0].split("#", 1)[0])
        )
        if clean in ("", "/", ".", os.sep, "/index.html"):
            return os.path.join(ROOT, "index.html")
        if clean in ("/game", "/game.html"):
            return os.path.join(ROOT, "game.html")
        if clean.startswith("/assets/"):
            # normpath 已消掉 ../，仍然再校验一次解析结果是否落在 assets 内
            return asset_path(clean[len("/assets/"):]) or DEAD_END
        return DEAD_END

    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer(("0.0.0.0", 8000), Handler)
    server.serve_forever()
