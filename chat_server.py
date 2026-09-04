import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import sqlite3
import time
from collections import deque
from contextlib import closing

import websockets


HOST = "0.0.0.0"
PORT = 8765
DB_FILE = "/path/to/relaxweb/users.db"
MAX_CHAT_LENGTH = 200
MAX_AVATAR_LENGTH = 200_000
AVATAR_PATTERN = re.compile(
    r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$"
)
AUTH_COOLDOWN = 1.5
CHAT_COOLDOWN = 1.0
SESSION_TTL = 30 * 24 * 60 * 60

clients = {}
history = deque(maxlen=50)
logger = logging.getLogger("live-chat")


def database():
    return closing(sqlite3.connect(DB_FILE, timeout=10))


def init_db():
    with database() as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS auth_sessions (
                token_hash TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                expires_at INTEGER NOT NULL
            )
            """
        )
        columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
        if "nickname" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN nickname TEXT NOT NULL DEFAULT ''"
            )
        if "avatar" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN avatar TEXT NOT NULL DEFAULT ''"
            )


def hash_password(password, salt=None):
    salt_bytes = os.urandom(16) if salt is None else base64.b64decode(salt)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, 310_000
    )
    return base64.b64encode(digest).decode(), base64.b64encode(salt_bytes).decode()


def valid_username(username):
    return bool(re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9_-]{2,20}", username))


def register_user(username, password):
    username = username.strip()
    if not valid_username(username):
        return False, "用户名需为2-20位中文、英文、数字、_ 或 -"
    if len(password) < 6:
        return False, "密码至少需要6位"
    if len(password) > 128:
        return False, "密码过长"

    password_hash, salt = hash_password(password)
    try:
        with database() as conn, conn:
            conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, role, created_at)
                VALUES (?, ?, ?, 'user', ?)
                """,
                (username, password_hash, salt, int(time.time())),
            )
    except sqlite3.IntegrityError:
        return False, "这个用户名已经被注册"
    return True, "注册成功"


def authenticate_user(username, password):
    with database() as conn:
        row = conn.execute(
            """
            SELECT username, password_hash, salt, role, nickname, avatar
            FROM users WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()
    if not row:
        return None
    real_username, saved_hash, salt, role, nickname, avatar = row
    calculated_hash, _ = hash_password(password, salt)
    if not hmac.compare_digest(calculated_hash, saved_hash):
        return None
    return {
        "username": real_username,
        "role": role,
        "nickname": nickname or "",
        "avatar": avatar or "",
    }


def get_profile(username):
    with database() as conn:
        row = conn.execute(
            "SELECT nickname, avatar FROM users WHERE username = ?", (username,)
        ).fetchone()
    if not row:
        return {"username": username, "nickname": "", "avatar": ""}
    return {"username": username, "nickname": row[0] or "", "avatar": row[1] or ""}


def create_session(username):
    token = secrets.token_urlsafe(32)
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    expires_at = int(time.time()) + SESSION_TTL
    with database() as conn, conn:
        user_id = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()[0]
        conn.execute("DELETE FROM auth_sessions WHERE expires_at <= ?", (int(time.time()),))
        conn.execute(
            "INSERT INTO auth_sessions (token_hash, user_id, expires_at) VALUES (?, ?, ?)",
            (token_hash, user_id, expires_at),
        )
    return token


def resume_user(token):
    if not token:
        return None
    token_hash = hashlib.sha256(str(token).encode()).hexdigest()
    with database() as conn:
        row = conn.execute(
            """
            SELECT users.username, users.role, users.nickname, users.avatar
            FROM auth_sessions
            JOIN users ON users.id = auth_sessions.user_id
            WHERE auth_sessions.token_hash = ? AND auth_sessions.expires_at > ?
            """,
            (token_hash, int(time.time())),
        ).fetchone()
    return {
        "username": row[0],
        "role": row[1],
        "nickname": row[2] or "",
        "avatar": row[3] or "",
    } if row else None


async def send_json(websocket, data):
    await websocket.send(json.dumps(data, ensure_ascii=False, separators=(",", ":")))


async def broadcast(data):
    if not clients:
        return
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    sockets = tuple(clients)
    results = await asyncio.gather(
        *(socket.send(payload) for socket in sockets), return_exceptions=True
    )
    for socket, result in zip(sockets, results):
        if isinstance(result, Exception):
            clients.pop(socket, None)


async def broadcast_online_count():
    await broadcast({"type": "online", "count": len(clients)})


def rate_limited(state, key, cooldown):
    now = time.monotonic()
    if now - state[key] < cooldown:
        return True
    state[key] = now
    return False


async def handle_register(websocket, state, data):
    if rate_limited(state, "last_auth_attempt", AUTH_COOLDOWN):
        await send_json(websocket, {"type": "auth_error", "message": "操作太频繁，请稍后再试"})
        return
    success, message = register_user(
        str(data.get("username", "")).strip(), str(data.get("password", ""))
    )
    await send_json(
        websocket,
        {"type": "register_success" if success else "auth_error", "message": message},
    )


async def handle_login(websocket, state, data):
    if rate_limited(state, "last_auth_attempt", AUTH_COOLDOWN):
        await send_json(websocket, {"type": "auth_error", "message": "操作太频繁，请稍后再试"})
        return
    user = authenticate_user(
        str(data.get("username", "")).strip(), str(data.get("password", ""))
    )
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "用户名或密码错误"})
        return
    state["user"] = user
    token = create_session(user["username"])
    logger.info("user login: %s", user["username"])
    profile = get_profile(user["username"])
    await send_json(
        websocket,
        {
            "type": "login_success",
            "username": user["username"],
            "role": user["role"],
            "token": token,
            "nickname": profile["nickname"],
            "avatar": profile["avatar"],
        },
    )


async def handle_resume(websocket, state, data):
    user = resume_user(data.get("token"))
    if not user:
        await send_json(websocket, {"type": "auth_expired"})
        return
    state["user"] = user
    await send_json(
        websocket,
        {
            "type": "resume_success",
            "username": user["username"],
            "role": user["role"],
            "nickname": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
        },
    )


async def handle_logout(websocket, state, data):
    if rate_limited(state, "last_auth_attempt", AUTH_COOLDOWN):
        await send_json(websocket, {"type": "auth_error", "message": "操作太频繁，请稍后再试"})
        return
    token = data.get("token")
    if token:
        token_hash = hashlib.sha256(str(token).encode()).hexdigest()
        with database() as conn, conn:
            conn.execute(
                "DELETE FROM auth_sessions WHERE token_hash = ?", (token_hash,)
            )
    state["user"] = None
    logger.info("user logout")
    await send_json(websocket, {"type": "logout_success"})


async def handle_update_profile(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_profile_update", 1.0):
        await send_json(websocket, {"type": "profile_error", "message": "操作太频繁，请稍后再试"})
        return
    updates, params = [], []
    if "nickname" in data:
        nickname = str(data.get("nickname") or "").strip()
        if nickname and not valid_username(nickname):
            await send_json(
                websocket,
                {"type": "profile_error", "message": "昵称需为2-20位中文、英文、数字、_ 或 -"},
            )
            return
        updates.append("nickname = ?")
        params.append(nickname)
    if "avatar" in data:
        avatar = str(data.get("avatar") or "")
        if avatar and (
            len(avatar) > MAX_AVATAR_LENGTH or not AVATAR_PATTERN.match(avatar)
        ):
            await send_json(
                websocket,
                {"type": "profile_error", "message": "头像格式不支持或过大"},
            )
            return
        updates.append("avatar = ?")
        params.append(avatar)
    if updates:
        params.append(user["username"])
        with database() as conn, conn:
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE username = ?", params
            )
    profile = get_profile(user["username"])
    state["user"]["nickname"] = profile["nickname"]
    state["user"]["avatar"] = profile["avatar"]
    logger.info("profile updated: %s", user["username"])
    await send_json(websocket, {"type": "profile_updated", **profile})
    await broadcast({"type": "profile", **profile})


async def handle_get_profile(websocket, state, data):
    await send_json(
        websocket,
        {"type": "profile", **get_profile(str(data.get("username", "")))},
    )


async def handle_delete_account(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_auth_attempt", AUTH_COOLDOWN):
        await send_json(websocket, {"type": "account_error", "message": "操作太频繁，请稍后再试"})
        return
    if not authenticate_user(user["username"], str(data.get("password", ""))):
        await send_json(websocket, {"type": "account_error", "message": "密码错误"})
        return
    with database() as conn, conn:
        conn.execute(
            "DELETE FROM auth_sessions WHERE user_id IN "
            "(SELECT id FROM users WHERE username = ?)",
            (user["username"],),
        )
        conn.execute("DELETE FROM users WHERE username = ?", (user["username"],))
    state["user"] = None
    logger.info("account deleted: %s", user["username"])
    await send_json(websocket, {"type": "account_deleted"})


async def handle_get_online(websocket, state, data):
    users = {}
    for client_state in list(clients.values()):
        user = client_state.get("user")
        if not user:
            continue
        users[user["username"]] = {
            "username": user["username"],
            "nickname": user.get("nickname") or "",
            "avatar": user.get("avatar") or "",
            "role": user.get("role") or "user",
        }
    await send_json(websocket, {"type": "online_users", "users": list(users.values())})


async def handle_chat(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    text = str(data.get("text", "")).strip()[:MAX_CHAT_LENGTH]
    if not text:
        return
    if rate_limited(state, "last_message", CHAT_COOLDOWN):
        await send_json(websocket, {"type": "error", "message": "发送太快了"})
        return
    message = {
        "type": "chat",
        "username": user["username"],
        "nickname": user.get("nickname") or "",
        "role": user["role"],
        "text": text,
        "time": time.strftime("%H:%M"),
    }
    history.append(message)
    logger.info("chat message from %s (%d chars)", user["username"], len(text))
    await broadcast(message)


handlers = {
    "register": handle_register,
    "login": handle_login,
    "resume": handle_resume,
    "logout": handle_logout,
    "update_profile": handle_update_profile,
    "get_profile": handle_get_profile,
    "delete_account": handle_delete_account,
    "get_online": handle_get_online,
    "chat": handle_chat,
}


async def handler(websocket):
    state = {
        "user": None,
        "last_message": 0.0,
        "last_auth_attempt": 0.0,
        "last_profile_update": 0.0,
    }
    clients[websocket] = state
    logger.info("connection opened; online=%d", len(clients))
    await send_json(websocket, {"type": "history", "messages": list(history)})
    await broadcast_online_count()
    try:
        async for raw_message in websocket:
            try:
                data = json.loads(raw_message)
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(data, dict):
                continue
            action = handlers.get(data.get("type"))
            if action:
                await action(websocket, state, data)
    except websockets.ConnectionClosed:
        pass
    finally:
        clients.pop(websocket, None)
        logger.info("connection closed; online=%d", len(clients))
        await broadcast_online_count()


async def main():
    init_db()
    logger.info("chat server listening on ws://%s:%d", HOST, PORT)
    async with websockets.serve(
        handler,
        HOST,
        PORT,
        max_size=300_000,
        max_queue=32,
        ping_interval=20,
        ping_timeout=20,
        close_timeout=5,
    ):
        await asyncio.Future()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main())
