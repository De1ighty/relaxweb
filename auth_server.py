"""拉流鉴权服务：供 MediaMTX authExternalUrl 调用（仅监听本机）。"""
import hashlib
import json
import logging
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

HOST = "127.0.0.1"
PORT = 8001
DB_FILE = "/path/to/relaxweb/users.db"
STREAM_USER = "xiaopang"
STREAM_PASS = "changeme"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("live-auth")


def database():
    return sqlite3.connect(DB_FILE, timeout=10)


def session_valid(username, token):
    if not username or not token:
        return False
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with database() as conn:
        row = conn.execute(
            "SELECT 1 FROM auth_sessions s JOIN users u ON u.id = s.user_id "
            "WHERE s.token_hash = ? AND s.expires_at > ? AND u.username = ?",
            (token_hash, int(time.time()), username),
        ).fetchone()
    return bool(row)


def decide(action, user, password, query, ip):
    if action in ("publish", "playback"):
        return user == STREAM_USER and password == STREAM_PASS
    if action == "read":
        if user == STREAM_USER and password == STREAM_PASS:
            return True
        if session_valid(user, password):
            return True
        params = parse_qs(query or "")
        return session_valid(
            params.get("user", [""])[0], params.get("token", [""])[0]
        )
    if action in ("api", "metrics", "pprof"):
        return ip in ("127.0.0.1", "::1")
    return False


class AuthHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw)
        except ValueError:
            data = {}
        action = str(data.get("action") or "")
        user = str(data.get("user") or "")
        password = str(data.get("password") or "")
        query = str(data.get("query") or "")
        ip = str(data.get("ip") or "")
        ok = decide(action, user, password, query, ip)
        logger.info(
            "%s action=%s user=%s ip=%s", "ALLOW" if ok else "DENY", action, user or "-", ip
        )
        self.send_response(200 if ok else 403)
        self.end_headers()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    logger.info("auth server listening on http://%s:%d", HOST, PORT)
    ThreadingHTTPServer((HOST, PORT), AuthHandler).serve_forever()
