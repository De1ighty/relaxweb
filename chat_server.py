import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
import os
import random
import re
import secrets
import sqlite3
import time
from collections import deque
from contextlib import closing
from itertools import combinations

import websockets


HOST = "0.0.0.0"
PORT = 8765
DB_FILE = os.environ.get("LIVE_DB_FILE", "/path/to/relaxweb/users.db")
MAX_CHAT_LENGTH = 200
MAX_AVATAR_LENGTH = 200_000
AVATAR_PATTERN = re.compile(
    r"^data:image/(png|jpe?g|gif|webp);base64,[A-Za-z0-9+/=]+$"
)
AUTH_COOLDOWN = 1.5
CHAT_COOLDOWN = 1.0
REGISTER_IP_LIMIT = 10
REGISTER_IP_WINDOW = 3600
INVITE_UNUSED_LIMIT = 5
SESSION_TTL = 30 * 24 * 60 * 60
NEW_USER_COINS = 100.0
BET_MIN_STAKE = 10.0
BET_MAX_OPTIONS = 6
BET_QUESTION_LIMIT = 60
BET_OPTION_LIMIT = 20
FINANCE_HISTORY_LIMIT = 60
TRANSFER_COOLDOWN = 2.0
GAME_TURN_TIMEOUT = 45
GAME_INTERMISSION = 8
GAME_MAX_PLAYERS = 9
GAME_BLIND_PRESETS = (1, 2, 5, 10)
GAME_DISCONNECT_GRACE = 30.0
GAME_TYPES = ("holdem",)

clients = {}
history = deque(maxlen=50)
register_ip_times = {}
active_bet = None
game_rooms = {}
room_seq = 0
room_leave_timers = {}
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
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invite_codes (
                code TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                used_by TEXT,
                used_at INTEGER,
                created_by TEXT NOT NULL DEFAULT ''
            )
            """
        )
        invite_columns = {
            row[1] for row in conn.execute("PRAGMA table_info(invite_codes)")
        }
        if "created_by" not in invite_columns:
            conn.execute(
                "ALTER TABLE invite_codes ADD COLUMN created_by TEXT NOT NULL DEFAULT ''"
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
        if "coins" not in columns:
            conn.execute(
                "ALTER TABLE users ADD COLUMN coins REAL NOT NULL DEFAULT 100"
            )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coin_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                amount REAL NOT NULL,
                balance REAL NOT NULL,
                kind TEXT NOT NULL,
                detail TEXT NOT NULL DEFAULT '',
                created_at INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_coin_tx_user "
            "ON coin_transactions(username, id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question TEXT NOT NULL,
                options TEXT NOT NULL,
                creator TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'open',
                correct_index INTEGER,
                created_at INTEGER NOT NULL,
                settled_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bet_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bet_id INTEGER NOT NULL REFERENCES bets(id) ON DELETE CASCADE,
                username TEXT NOT NULL,
                option_index INTEGER NOT NULL,
                amount REAL NOT NULL,
                created_at INTEGER NOT NULL,
                UNIQUE(bet_id, username)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS game_escrows (
                username TEXT NOT NULL,
                room_id INTEGER NOT NULL,
                amount REAL NOT NULL,
                PRIMARY KEY (username, room_id)
            )
            """
        )


def set_escrow(username, room_id, amount):
    with database() as conn, conn:
        if amount is None:
            conn.execute(
                "DELETE FROM game_escrows WHERE username = ? AND room_id = ?",
                (username, room_id),
            )
        else:
            conn.execute(
                "INSERT INTO game_escrows (username, room_id, amount) VALUES (?, ?, ?) "
                "ON CONFLICT(username, room_id) DO UPDATE SET amount = excluded.amount",
                (username, room_id, round(amount, 2)),
            )


def refund_game_escrows():
    """服务器重启后房间不再存在，把所有托管中的游戏筹码退还为金币。"""
    with database() as conn, conn:
        rows = conn.execute(
            "SELECT username, amount FROM game_escrows"
        ).fetchall()
        for username, amount in rows:
            try:
                adjust_coins(
                    conn, username, amount, "game_settle", "游戏厅退款（服务重启）"
                )
            except (KeyError, ValueError):
                continue
        conn.execute("DELETE FROM game_escrows")
    if rows:
        logger.info("refunded %d game escrows on startup", len(rows))


def record_coins(conn, username, amount, balance, kind, detail=""):
    conn.execute(
        "INSERT INTO coin_transactions (username, amount, balance, kind, detail, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            username,
            round(amount, 2),
            round(balance, 2),
            kind,
            str(detail or "")[:120],
            int(time.time()),
        ),
    )


def adjust_coins(conn, username, delta, kind, detail=""):
    """在已打开的事务中调整用户金币并记录明细，返回新余额。"""
    row = conn.execute(
        "SELECT coins FROM users WHERE username = ?", (username,)
    ).fetchone()
    if row is None:
        raise KeyError(username)
    balance = round((row[0] or 0.0) + delta, 2)
    if balance < 0:
        raise ValueError("金币不能低于 0")
    conn.execute(
        "UPDATE users SET coins = ? WHERE username = ?", (balance, username)
    )
    record_coins(conn, username, delta, balance, kind, detail)
    return balance


def hash_password(password, salt=None):
    salt_bytes = os.urandom(16) if salt is None else base64.b64decode(salt)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_bytes, 310_000
    )
    return base64.b64encode(digest).decode(), base64.b64encode(salt_bytes).decode()


def valid_username(username):
    return bool(re.fullmatch(r"[\u4e00-\u9fa5A-Za-z0-9_-]{2,20}", username))


def register_user(username, password, invite_code=""):
    username = username.strip()
    if not valid_username(username):
        return False, "用户名需为2-20位中文、英文、数字、_ 或 -"
    if len(password) < 6:
        return False, "密码至少需要6位"
    if len(password) > 128:
        return False, "密码过长"

    code = str(invite_code or "").strip()
    if not code:
        return False, "注册需要邀请码"

    password_hash, salt = hash_password(password)
    try:
        with database() as conn, conn:
            row = conn.execute(
                "SELECT code FROM invite_codes WHERE code = ? AND used_by IS NULL",
                (code,),
            ).fetchone()
            if not row:
                return False, "邀请码无效或已被使用"
            conn.execute(
                """
                INSERT INTO users (username, password_hash, salt, role, created_at, coins)
                VALUES (?, ?, ?, 'user', ?, 0)
                """,
                (username, password_hash, salt, int(time.time())),
            )
            adjust_coins(
                conn, username, NEW_USER_COINS, "register", "新用户注册奖励"
            )
            conn.execute(
                "UPDATE invite_codes SET used_by = ?, used_at = ? WHERE code = ?",
                (username, int(time.time()), code),
            )
    except sqlite3.IntegrityError:
        return False, "这个用户名已经被注册"
    return True, "注册成功"


def authenticate_user(username, password):
    with database() as conn:
        row = conn.execute(
            """
            SELECT username, password_hash, salt, role, nickname, avatar, coins
            FROM users WHERE username = ?
            """,
            (username.strip(),),
        ).fetchone()
    if not row:
        return None
    real_username, saved_hash, salt, role, nickname, avatar, coins = row
    calculated_hash, _ = hash_password(password, salt)
    if not hmac.compare_digest(calculated_hash, saved_hash):
        return None
    return {
        "username": real_username,
        "role": role,
        "nickname": nickname or "",
        "avatar": avatar or "",
        "coins": round(coins or 0.0, 2),
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
            SELECT users.username, users.role, users.nickname, users.avatar, users.coins
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
        "coins": round(row[4] or 0.0, 2),
    } if row else None


async def _ws_send(socket, payload):
    """带锁发送：两个广播并发打到同一连接会触发 ConcurrencyError，导致连接被静默剔除。"""
    state = clients.get(socket)
    if not state:
        return
    async with state["send_lock"]:
        try:
            await socket.send(payload)
        except Exception as error:
            clients.pop(socket, None)
            logger.warning("send failed (%s), dropped connection", error)


async def send_json(websocket, data):
    await _ws_send(
        websocket, json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    )


async def broadcast(data):
    if not clients:
        return
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    sockets = tuple(clients)
    await asyncio.gather(*(_ws_send(socket, payload) for socket in sockets))


async def broadcast_online_count():
    # 游戏厅独立页的连接不算直播间在线观众
    count = sum(
        1 for state in clients.values() if state.get("client") != "game"
    )
    await broadcast({"type": "online", "count": count})


def rate_limited(state, key, cooldown):
    now = time.monotonic()
    if now - state.get(key, 0.0) < cooldown:
        return True
    state[key] = now
    return False


async def handle_register(websocket, state, data):
    ip = (websocket.remote_address or ("?", 0))[0]
    now = time.monotonic()
    recent = [t for t in register_ip_times.get(ip, []) if now - t < REGISTER_IP_WINDOW]
    register_ip_times[ip] = recent
    if len(recent) >= REGISTER_IP_LIMIT:
        await send_json(websocket, {"type": "auth_error", "message": "注册太频繁，请稍后再试"})
        return
    if rate_limited(state, "last_auth_attempt", AUTH_COOLDOWN):
        await send_json(websocket, {"type": "auth_error", "message": "操作太频繁，请稍后再试"})
        return
    success, message = register_user(
        str(data.get("username", "")).strip(),
        str(data.get("password", "")),
        str(data.get("invite_code", "")),
    )
    if success:
        recent.append(now)
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
    on_user_authenticated(user["username"])
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
            "coins": user["coins"],
        },
    )


async def handle_resume(websocket, state, data):
    user = resume_user(data.get("token"))
    if not user:
        await send_json(websocket, {"type": "auth_expired"})
        return
    state["user"] = user
    on_user_authenticated(user["username"])
    await send_json(
        websocket,
        {
            "type": "resume_success",
            "username": user["username"],
            "role": user["role"],
            "nickname": user.get("nickname", ""),
            "avatar": user.get("avatar", ""),
            "coins": user.get("coins", 0),
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
    if active_bet and active_bet["creator"] == user["username"]:
        await cancel_active_bet("发起者已注销账号")
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


def display_name(username):
    profile = get_profile(username)
    return profile["nickname"] or username


def parse_amount(value):
    try:
        amount = round(float(value), 2)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None
    return amount


async def push_balance(username, coins):
    payload = json.dumps(
        {"type": "coins", "username": username, "coins": round(coins, 2)},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    for socket, client_state in list(clients.items()):
        user = client_state.get("user")
        if user and user["username"] == username:
            await _ws_send(socket, payload)


async def broadcast_system(text, danmaku=False):
    message = {"type": "system", "text": text, "time": time.strftime("%m/%d %H:%M")}
    if danmaku:
        message["danmaku"] = True
    history.append(message)
    logger.info("system message: %s", text)
    await broadcast(message)


async def handle_get_finance(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    with database() as conn:
        row = conn.execute(
            "SELECT coins FROM users WHERE username = ?", (user["username"],)
        ).fetchone()
        rows = conn.execute(
            "SELECT amount, balance, kind, detail, created_at FROM coin_transactions "
            "WHERE username = ? ORDER BY id DESC LIMIT ?",
            (user["username"], FINANCE_HISTORY_LIMIT),
        ).fetchall()
    coins = round(row[0] or 0.0, 2) if row else 0.0
    await send_json(
        websocket,
        {
            "type": "finance",
            "coins": coins,
            "transactions": [
                {
                    "amount": round(amount, 2),
                    "balance": round(balance, 2),
                    "kind": kind,
                    "detail": detail,
                    "created_at": created_at,
                }
                for amount, balance, kind, detail, created_at in rows
            ],
        },
    )


async def handle_transfer_coins(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_transfer", TRANSFER_COOLDOWN):
        await send_json(websocket, {"type": "coins_error", "message": "操作太频繁，请稍后再试"})
        return
    target = str(data.get("to", "")).strip()
    amount = parse_amount(data.get("amount"))
    if not target or target == user["username"]:
        await send_json(websocket, {"type": "coins_error", "message": "请输入正确的对方用户名"})
        return
    if amount is None:
        await send_json(websocket, {"type": "coins_error", "message": "转账金额无效"})
        return
    sender = user["username"]
    try:
        with database() as conn, conn:
            row = conn.execute(
                "SELECT username FROM users WHERE username = ?", (target,)
            ).fetchone()
            if not row:
                raise ValueError("用户不存在")
            balance_row = conn.execute(
                "SELECT coins FROM users WHERE username = ?", (sender,)
            ).fetchone()
            if (balance_row[0] or 0.0) < amount:
                raise ValueError("金币不足")
            sender_balance = adjust_coins(
                conn, sender, -amount, "transfer_out", f"转账给 {row[0]}"
            )
            target_balance = adjust_coins(
                conn, row[0], amount, "transfer_in", f"来自 {sender} 的转账"
            )
    except ValueError as error:
        await send_json(websocket, {"type": "coins_error", "message": str(error)})
        return
    user["coins"] = sender_balance
    logger.info("transfer %.2f from %s to %s", amount, sender, row[0])
    await send_json(websocket, {"type": "transfer_success", "coins": sender_balance})
    await push_balance(row[0], target_balance)
    await broadcast_system(
        f"💰 {display_name(sender)} 转账 {amount:.2f} 金币给 {display_name(row[0])}",
        danmaku=True,
    )


def load_open_bet():
    with database() as conn:
        row = conn.execute(
            "SELECT id, question, options, creator, created_at FROM bets "
            "WHERE status = 'open' ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not row:
            return None
        entries = conn.execute(
            "SELECT username, option_index, amount FROM bet_entries "
            "WHERE bet_id = ? ORDER BY id",
            (row[0],),
        ).fetchall()
    return {
        "id": row[0],
        "question": row[1],
        "options": json.loads(row[2]),
        "creator": row[3],
        "created_at": row[4],
        "entries": [
            {"username": name, "option_index": index, "amount": round(amount, 2)}
            for name, index, amount in entries
        ],
    }


def bet_public_state(bet):
    if not bet:
        return None
    totals = [0.0] * len(bet["options"])
    for entry in bet["entries"]:
        if 0 <= entry["option_index"] < len(totals):
            totals[entry["option_index"]] = round(
                totals[entry["option_index"]] + entry["amount"], 2
            )
    return {
        "id": bet["id"],
        "question": bet["question"],
        "options": bet["options"],
        "creator": bet["creator"],
        "created_at": bet["created_at"],
        "entries": bet["entries"],
        "totals": totals,
        "pot": round(sum(totals), 2),
    }


def find_entry(bet, username):
    for entry in bet["entries"]:
        if entry["username"] == username:
            return entry
    return None


async def handle_get_bet(websocket, state, data):
    await send_json(
        websocket, {"type": "bet_state", "bet": bet_public_state(active_bet)}
    )


async def handle_create_bet(websocket, state, data):
    global active_bet
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_bet_action", 2.0):
        await send_json(websocket, {"type": "bet_error", "message": "操作太频繁，请稍后再试"})
        return
    if active_bet:
        await send_json(
            websocket,
            {"type": "bet_error", "message": "已有进行中的竞猜，请等待它结账"},
        )
        return
    question = str(data.get("question", "")).strip()[:BET_QUESTION_LIMIT]
    raw_options = data.get("options")
    options = []
    if isinstance(raw_options, list):
        for item in raw_options:
            text = str(item).strip()[:BET_OPTION_LIMIT]
            if text and text not in options:
                options.append(text)
    if not question:
        await send_json(websocket, {"type": "bet_error", "message": "请输入竞猜问题"})
        return
    if len(options) < 2:
        await send_json(websocket, {"type": "bet_error", "message": "至少需要两个选项"})
        return
    if len(options) > BET_MAX_OPTIONS:
        await send_json(
            websocket,
            {"type": "bet_error", "message": f"选项最多 {BET_MAX_OPTIONS} 个"},
        )
        return
    now = int(time.time())
    with database() as conn, conn:
        cursor = conn.execute(
            "INSERT INTO bets (question, options, creator, status, created_at) "
            "VALUES (?, ?, ?, 'open', ?)",
            (question, json.dumps(options, ensure_ascii=False), user["username"], now),
        )
        bet_id = cursor.lastrowid
    active_bet = {
        "id": bet_id,
        "question": question,
        "options": options,
        "creator": user["username"],
        "created_at": now,
        "entries": [],
    }
    logger.info("bet created by %s: %s", user["username"], question)
    await send_json(websocket, {"type": "bet_created"})
    await broadcast({"type": "bet_update", "bet": bet_public_state(active_bet)})
    await broadcast_system(
        f"🎲 {display_name(user['username'])} 发起了竞猜：{question}"
    )


async def handle_place_bet(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_bet_action", 1.0):
        await send_json(websocket, {"type": "bet_error", "message": "操作太频繁，请稍后再试"})
        return
    bet = active_bet
    if not bet:
        await send_json(websocket, {"type": "bet_error", "message": "当前没有进行中的竞猜"})
        return
    try:
        option_index = int(data.get("option_index"))
    except (TypeError, ValueError):
        option_index = -1
    if not 0 <= option_index < len(bet["options"]):
        await send_json(websocket, {"type": "bet_error", "message": "请选择一个选项"})
        return
    amount = parse_amount(data.get("amount"))
    if amount is None:
        await send_json(websocket, {"type": "bet_error", "message": "投注金额无效"})
        return
    username = user["username"]
    try:
        with database() as conn, conn:
            if find_entry(bet, username):
                raise ValueError("你已经参与过这个竞猜")
            balance = round(
                conn.execute(
                    "SELECT coins FROM users WHERE username = ?", (username,)
                ).fetchone()[0] or 0.0,
                2,
            )
            if amount > balance:
                raise ValueError("金币不足")
            if balance >= BET_MIN_STAKE and amount < BET_MIN_STAKE:
                raise ValueError(f"最低投注 {BET_MIN_STAKE:.0f} 金币")
            if balance < BET_MIN_STAKE and amount < balance:
                raise ValueError("金币不足 10 时只能全部投上")
            new_balance = adjust_coins(
                conn, username, -amount, "bet_stake", f"竞猜投注：{bet['question']}"
            )
            conn.execute(
                "INSERT INTO bet_entries (bet_id, username, option_index, amount, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (bet["id"], username, option_index, amount, int(time.time())),
            )
    except ValueError as error:
        await send_json(websocket, {"type": "bet_error", "message": str(error)})
        return
    bet["entries"].append(
        {"username": username, "option_index": option_index, "amount": amount}
    )
    user["coins"] = new_balance
    await send_json(
        websocket,
        {
            "type": "bet_placed",
            "coins": new_balance,
            "option_index": option_index,
            "amount": amount,
        },
    )
    await broadcast({"type": "bet_update", "bet": bet_public_state(bet)})


async def cancel_active_bet(reason, message=None, refund_prefix="竞猜取消"):
    global active_bet
    bet = active_bet
    if not bet:
        return
    with database() as conn, conn:
        rows = conn.execute(
            "SELECT username, amount FROM bet_entries WHERE bet_id = ? ORDER BY id",
            (bet["id"],),
        ).fetchall()
        for name, amount in rows:
            try:
                adjust_coins(
                    conn, name, amount, "bet_refund", f"{refund_prefix}：{bet['question']}"
                )
            except KeyError:
                continue
        conn.execute(
            "UPDATE bets SET status = 'cancelled', settled_at = ? WHERE id = ?",
            (int(time.time()), bet["id"]),
        )
    active_bet = None
    logger.info("bet cancelled: %s (%s)", bet["question"], reason)
    await broadcast({"type": "bet_update", "bet": None})
    await broadcast(
        {"type": "bet_cancelled", "question": bet["question"], "reason": reason}
    )
    await broadcast_system(message or f"🎲 竞猜已取消（{reason}），投注已退还")


async def handle_settle_bet(websocket, state, data):
    global active_bet
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    bet = active_bet
    if not bet:
        await send_json(websocket, {"type": "bet_error", "message": "当前没有进行中的竞猜"})
        return
    if user["username"] != bet["creator"]:
        await send_json(websocket, {"type": "bet_error", "message": "只有发起者可以结账"})
        return
    try:
        correct_index = int(data.get("correct_index"))
    except (TypeError, ValueError):
        correct_index = -1
    if not 0 <= correct_index < len(bet["options"]):
        await send_json(websocket, {"type": "bet_error", "message": "请选择正确选项"})
        return
    question = bet["question"]
    answer = bet["options"][correct_index]
    results = []
    winner_texts = []
    loser_texts = []
    refunded = False
    with database() as conn, conn:
        rows = conn.execute(
            "SELECT username, option_index, amount FROM bet_entries "
            "WHERE bet_id = ? ORDER BY id",
            (bet["id"],),
        ).fetchall()
        winners = [(name, amount) for name, index, amount in rows if index == correct_index]
        losers = [(name, amount) for name, index, amount in rows if index != correct_index]
        pot = round(sum(amount for _, amount in losers), 2)
        win_stake = round(sum(amount for _, amount in winners), 2)
        if winners and pot > 0:
            shares = [round(pot * amount / win_stake, 2) for _, amount in winners]
            shares[-1] = round(shares[-1] + pot - sum(shares), 2)
            for (name, amount), share in zip(winners, shares):
                try:
                    balance = adjust_coins(
                        conn, name, amount + share, "bet_win", f"竞猜猜中：{question}"
                    )
                except KeyError:
                    continue
                results.append(
                    {"username": name, "change": round(share, 2), "coins": balance}
                )
                winner_texts.append(f"{display_name(name)} +{share:.2f}")
            for name, amount in losers:
                row = conn.execute(
                    "SELECT coins FROM users WHERE username = ?", (name,)
                ).fetchone()
                results.append(
                    {
                        "username": name,
                        "change": round(-amount, 2),
                        "coins": round(row[0] or 0.0, 2) if row else 0.0,
                    }
                )
                loser_texts.append(f"{display_name(name)} -{amount:.2f}")
        else:
            refunded = True
            for name, amount in rows:
                try:
                    balance = adjust_coins(
                        conn, name, amount, "bet_refund", f"竞猜退款：{question}"
                    )
                except KeyError:
                    continue
                results.append(
                    {"username": name, "change": round(amount, 2), "coins": balance}
                )
        conn.execute(
            "UPDATE bets SET status = 'settled', correct_index = ?, settled_at = ? "
            "WHERE id = ?",
            (correct_index, int(time.time()), bet["id"]),
        )
    active_bet = None
    logger.info("bet settled: %s answer=%s", question, answer)
    await broadcast(
        {
            "type": "bet_settled",
            "question": question,
            "answer": answer,
            "refunded": refunded,
            "results": results,
        }
    )
    if refunded:
        await broadcast_system(f"🎲 竞猜结账：{question}｜无人猜对，投注已退还")
    else:
        await broadcast_system(
            f"🎲 竞猜结账：{question}｜答案：{answer}｜"
            f"赢家：{'、'.join(winner_texts) or '无'}｜"
            f"输家：{'、'.join(loser_texts) or '无'}"
        )


async def handle_cancel_bet(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_bet_action", 2.0):
        await send_json(websocket, {"type": "bet_error", "message": "操作太频繁，请稍后再试"})
        return
    bet = active_bet
    if not bet:
        await send_json(websocket, {"type": "bet_error", "message": "当前没有进行中的竞猜"})
        return
    if user["username"] != bet["creator"]:
        await send_json(websocket, {"type": "bet_error", "message": "只有发起者可以流局"})
        return
    logger.info("bet drawn by %s: %s", user["username"], bet["question"])
    await cancel_active_bet(
        "发起者流局",
        message=f"🎲 竞猜流局：{bet['question']}｜投注已全部退还",
        refund_prefix="竞猜流局",
    )


# =========================================================
# 游戏厅：德州扑克
# =========================================================

HAND_NAMES = ["高牌", "一对", "两对", "三条", "顺子", "同花", "葫芦", "四条", "同花顺"]


def hand_name(score):
    if score[0] == 8 and score[1] == 14:
        return "皇家同花顺"
    return HAND_NAMES[score[0]]


def evaluate5(cards):
    """返回可比较的牌型分值元组，越大越强。cards: [(rank 2-14, suit 0-3), ...]"""
    ranks = sorted((c[0] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    uniq = sorted(set(ranks), reverse=True)
    straight_high = 0
    if len(uniq) == 5:
        if uniq[0] - uniq[4] == 4:
            straight_high = uniq[0]
        elif uniq == [14, 5, 4, 3, 2]:
            straight_high = 5
    is_flush = len(set(suits)) == 1
    if is_flush and straight_high:
        return (8, straight_high)
    counts = {}
    for r in ranks:
        counts[r] = counts.get(r, 0) + 1
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)
    pattern = [c for _, c in groups]
    tie = [r for r, _ in groups]
    if pattern == [4, 1]:
        return (7, *tie)
    if pattern == [3, 2]:
        return (6, *tie)
    if is_flush:
        return (5, *ranks)
    if straight_high:
        return (4, straight_high)
    if pattern == [3, 1, 1]:
        return (3, *tie)
    if pattern == [2, 2, 1]:
        return (2, *tie)
    if pattern == [2, 1, 1, 1]:
        return (1, *tie)
    return (0, *ranks)


def best7(cards7):
    return max(evaluate5(list(group)) for group in combinations(cards7, 5))


def build_side_pots(committed, folded):
    """按投入分层构造边池：[{amount, eligible}]，eligible 为未弃牌且投入达层的玩家。"""
    levels = sorted({v for v in committed.values() if v > 0})
    pots = []
    prev = 0.0
    for level in levels:
        amount = 0.0
        eligible = []
        for name, chips in committed.items():
            if chips > prev:
                amount += min(chips, level) - prev
                if chips >= level and name not in folded:
                    eligible.append(name)
        if amount > 0:
            pots.append({"amount": round(amount, 2), "eligible": eligible})
        prev = level
    return pots


def distribute_pots(pots, hands):
    """按牌型把每个池分给符合条件的最大玩家，浮点尾差给第一个赢家。"""
    payouts = {}
    for pot in pots:
        best = max(hands[name] for name in pot["eligible"])
        winners = [name for name in pot["eligible"] if hands[name] == best]
        share = round(pot["amount"] / len(winners), 2)
        paid = 0.0
        for index, name in enumerate(winners):
            amount = share
            if index == len(winners) - 1:
                amount = round(pot["amount"] - paid, 2)
            paid = round(paid + amount, 2)
            payouts[name] = round(payouts.get(name, 0) + amount, 2)
    return payouts


def new_deck():
    deck = [(rank, suit) for rank in range(2, 15) for suit in range(4)]
    random.shuffle(deck)
    return deck


def find_user_room(username):
    for room in game_rooms.values():
        if username in room["members"]:
            return room
    return None


def room_summary(room):
    return {
        "id": room["id"],
        "name": room["name"],
        "game": room.get("game_type", "holdem"),
        "owner": room["owner"],
        "owner_name": display_name(room["owner"]),
        "buy_in": room["buy_in"],
        "blind": room["blind"],
        "status": room["status"],
        "hand_no": room["game"]["hand_no"] if room.get("game") else 0,
        "players": [
            {
                "username": name,
                "nickname": display_name(name),
                "stack": room["members"][name]["stack"],
            }
            for name in room["seating"]
        ],
    }


async def broadcast_room_list():
    await broadcast(
        {"type": "room_list", "rooms": [room_summary(r) for r in game_rooms.values()]}
    )


async def broadcast_room(room, build):
    for socket, client_state in list(clients.items()):
        user = client_state.get("user")
        if not user or user["username"] not in room["members"]:
            continue
        try:
            await send_json(socket, build(user["username"]))
        except Exception:
            clients.pop(socket, None)


def legal_actions(room, username):
    g = room["game"]
    member = room["members"][username]
    to_call = round(g["current_bet"] - g["street_committed"].get(username, 0), 2)
    can_raise = username not in g["acted"]
    raise_max = round(g["street_committed"].get(username, 0) + member["stack"], 2)
    return {
        "fold": True,
        "check": to_call <= 0,
        "call": 0 < to_call <= member["stack"],
        "call_amount": round(min(to_call, member["stack"]), 2),
        "can_raise": can_raise and member["stack"] > 0,
        "raise_min": round(g["current_bet"] + g["min_raise"], 2),
        "raise_max": raise_max,
        "allin": member["stack"] > 0,
        "allin_to": raise_max,
    }


def game_view(room, username):
    g = room.get("game")
    if not isinstance(g, dict):
        g = None
    view = {
        "type": "game_update",
        "room_id": room["id"],
        "name": room["name"],
        "game_type": room.get("game_type", "holdem"),
        "paused": bool(room.get("paused")),
        "owner": room["owner"],
        "owner_name": display_name(room["owner"]),
        "buy_in": room["buy_in"],
        "blind": room["blind"],
        "status": room["status"],
        "players": [],
    }
    dealer_u = g.get("dealer") if g else None
    for name in room["seating"]:
        member = room["members"][name]
        view["players"].append(
            {
                "username": name,
                "nickname": display_name(name),
                "stack": member["stack"],
                "bet": round(g["street_committed"].get(name, 0), 2) if g else 0,
                "folded": bool(g and name in g["folded"]),
                "allin": bool(g and name in g["allin"]),
                "in_hand": bool(g and name in g["order"]),
                "dealer": name == dealer_u,
            }
        )
    if g:
        pot = round(sum(g["committed"].values()), 2)
        view.update(
            {
                "hand_no": g["hand_no"],
                "stage": g["stage"],
                "board": [{"r": r, "s": s} for r, s in g["board"]],
                "pot": pot,
                "current_bet": g["current_bet"],
                "to_act": g["to_act"],
                "turn_left": round(max(0, g["deadline"] - time.time()), 1)
                if g["to_act"]
                else 0,
                "dealer": dealer_u,
                "last_action": g.get("last_action"),
                "result": g.get("result"),
            }
        )
        if username in g["holes"]:
            view["your_hole"] = [{"r": r, "s": s} for r, s in g["holes"][username]]
            if g["to_act"] == username:
                view["your_options"] = legal_actions(room, username)
    return view


async def broadcast_game(room):
    await broadcast_room(room, lambda name: game_view(room, name))


def cancel_room_timer(room, key):
    handle = room.get(key)
    if handle:
        handle.cancel()
        room[key] = None


def schedule_turn_timer(room):
    cancel_room_timer(room, "turn_timer")
    if not room.get("game") or not room["game"].get("to_act"):
        return
    room_id = room["id"]
    deadline = room["game"]["deadline"]

    def fire():
        r = game_rooms.get(room_id)
        if not r or r.get("paused") or not r.get("game") or not r["game"].get("to_act"):
            return
        remaining = r["game"]["deadline"] - time.time()
        if remaining > 0.05:
            r["turn_timer"] = asyncio.get_running_loop().call_later(
                remaining, fire
            )
            return
        username = r["game"]["to_act"]
        if r["game"]["street_committed"].get(username, 0) >= r["game"]["current_bet"]:
            action = "check"
        else:
            action = "fold"
        asyncio.ensure_future(perform_action(r, username, action, auto=True))

    room["turn_timer"] = asyncio.get_running_loop().call_later(
        max(0.05, deadline - time.time()), fire
    )


def commit_chips(room, username, amount):
    g = room["game"]
    member = room["members"][username]
    amount = round(min(amount, member["stack"]), 2)
    member["stack"] = round(member["stack"] - amount, 2)
    g["committed"][username] = round(g["committed"].get(username, 0) + amount, 2)
    g["street_committed"][username] = round(
        g["street_committed"].get(username, 0) + amount, 2
    )
    if member["stack"] <= 0:
        g["allin"].add(username)
    return amount


def is_pending(g, username):
    return (
        username in g["order"]
        and username not in g["folded"]
        and username not in g["allin"]
        and (
            g["street_committed"].get(username, 0) < g["current_bet"]
            or username not in g["acted"]
        )
    )


def next_pending_after(room, anchor):
    g = room["game"]
    order = g["order"]
    start = order.index(anchor) if anchor in order else -1
    for step in range(1, len(order) + 1):
        candidate = order[(start + step) % len(order)]
        if is_pending(g, candidate):
            return candidate
    return None


def stack_owners(room):
    return [name for name in room["seating"] if room["members"][name]["stack"] > 0]


async def start_hand(room):
    eligible = stack_owners(room)
    if len(eligible) < 2:
        room["status"] = "waiting"
        room["game"] = None
        await broadcast_game(room)
        await broadcast_room_list()
        return
    blind = room["blind"]
    big_blind = round(blind * 2, 2)
    previous_dealer = room.get("dealer")
    if previous_dealer in eligible:
        start = eligible.index(previous_dealer)
        dealer_u = eligible[(start + 1) % len(eligible)]
    else:
        dealer_u = eligible[0]
    room["dealer"] = dealer_u
    order = eligible[eligible.index(dealer_u) + 1 :] + eligible[: eligible.index(dealer_u) + 1]
    deck = new_deck()
    holes = {name: [deck.pop(), deck.pop()] for name in order}
    room["game"] = {
        "hand_no": room.get("hand_seq", 0) + 1,
        "stage": "preflop",
        "deck": deck,
        "board": [],
        "holes": holes,
        "order": order,
        "committed": {name: 0.0 for name in order},
        "street_committed": {name: 0.0 for name in order},
        "folded": set(),
        "allin": set(),
        "acted": set(),
        "current_bet": big_blind,
        "min_raise": big_blind,
        "dealer": dealer_u,
        "to_act": None,
        "deadline": 0,
        "last_action": None,
        "result": None,
    }
    room["hand_seq"] = room["game"]["hand_no"]
    g = room["game"]
    if len(order) == 2:
        small_u, big_u = dealer_u, order[0]
    else:
        small_u, big_u = order[0], order[1]
    commit_chips(room, small_u, blind)
    commit_chips(room, big_u, big_blind)
    first = next_pending_after(room, big_u)
    if first is None:
        await advance_street(room)
        return
    g["to_act"] = first
    g["deadline"] = time.time() + GAME_TURN_TIMEOUT
    schedule_turn_timer(room)
    await broadcast_game(room)


async def perform_action(room, username, action, raise_to=None, auto=False):
    g = room["game"]
    if not g or room.get("paused") or g.get("to_act") != username:
        return
    options = legal_actions(room, username)
    nickname = display_name(username)
    text = ""
    if action == "fold":
        g["folded"].add(username)
        text = "弃牌"
    elif action == "check" and options["check"]:
        g["acted"].add(username)
        text = "看牌"
    elif action == "call" and options["call"]:
        paid = commit_chips(room, username, options["call_amount"])
        g["acted"].add(username)
        text = "全下跟注" if username in g["allin"] else f"跟注 {paid:.2f}"
    elif action == "raise":
        if not options["can_raise"]:
            return
        allin_to = options["allin_to"]
        raise_min = options["raise_min"]
        target = round(min(max(raise_to or raise_min, min(raise_min, allin_to)), allin_to), 2)
        commit_chips(room, username, round(target - g["street_committed"][username], 2))
        if target > g["current_bet"]:
            if target - g["current_bet"] >= g["min_raise"]:
                g["min_raise"] = round(target - g["current_bet"], 2)
                g["acted"] = {username}
            else:
                g["acted"].add(username)
            g["current_bet"] = target
        else:
            g["acted"].add(username)
        text = f"全下 {target:.2f}" if username in g["allin"] else f"加注到 {target:.2f}"
    else:
        return
    g["last_action"] = {
        "username": username,
        "nickname": nickname,
        "text": ("超时自动" if auto else "") + text,
    }
    logger.info("poker %s@%s: %s %s", username, room["id"], action, text)
    await progress_game(room)


async def progress_game(room):
    cancel_room_timer(room, "turn_timer")
    g = room["game"]
    if not g:
        return
    alive = [name for name in g["order"] if name not in g["folded"]]
    if len(alive) == 1:
        await end_hand(room, reveal=False)
        return
    nxt = next_pending_after(room, g.get("to_act") or g["dealer"])
    if nxt is None:
        if g["stage"] == "river":
            await end_hand(room, reveal=True)
        else:
            await advance_street(room)
        return
    g["to_act"] = nxt
    g["deadline"] = time.time() + GAME_TURN_TIMEOUT
    schedule_turn_timer(room)
    await broadcast_game(room)


async def advance_street(room):
    g = room["game"]
    if g["stage"] == "preflop":
        g["board"].extend([g["deck"].pop() for _ in range(3)])
        g["stage"] = "flop"
    elif g["stage"] == "flop":
        g["board"].append(g["deck"].pop())
        g["stage"] = "turn"
    elif g["stage"] == "turn":
        g["board"].append(g["deck"].pop())
        g["stage"] = "river"
    else:
        await end_hand(room, reveal=True)
        return
    g["acted"] = set()
    g["current_bet"] = 0
    g["min_raise"] = round(room["blind"] * 2, 2)
    for name in g["order"]:
        g["street_committed"][name] = 0.0
    nxt = next_pending_after(room, g["dealer"])
    if nxt is None:
        if g["stage"] == "river":
            await end_hand(room, reveal=True)
        else:
            await broadcast_game(room)
            await advance_street(room)
        return
    g["to_act"] = nxt
    g["deadline"] = time.time() + GAME_TURN_TIMEOUT
    schedule_turn_timer(room)
    await broadcast_game(room)


async def end_hand(room, reveal):
    cancel_room_timer(room, "turn_timer")
    g = room["game"]
    pot = round(sum(g["committed"].values()), 2)
    alive = [name for name in g["order"] if name not in g["folded"]]
    hands = {}
    if reveal:
        hands = {name: best7(g["holes"][name] + g["board"]) for name in alive}
    pots = build_side_pots(g["committed"], g["folded"])
    payouts = distribute_pots(pots, hands) if hands else {alive[0]: pot}
    for name, amount in payouts.items():
        if amount > 0 and name in room["members"]:
            room["members"][name]["stack"] = round(
                room["members"][name]["stack"] + amount, 2
            )
    for name in list(room["members"]):
        set_escrow(name, room["id"], room["members"][name]["stack"])
    g["stage"] = "showdown"
    g["to_act"] = None
    g["deadline"] = 0
    g["result"] = {
        "board": [{"r": r, "s": s} for r, s in g["board"]],
        "pot": pot,
        "reveal": [
            {
                "username": name,
                "cards": [{"r": r, "s": s} for r, s in g["holes"][name]],
                "hand_name": hand_name(hands[name]) if name in hands else "",
            }
            for name in alive
        ]
        if reveal
        else [],
        "payouts": payouts,
    }
    logger.info(
        "poker hand #%d done in room %s, pot %.2f, winners %s",
        g["hand_no"],
        room["id"],
        pot,
        {k: v for k, v in payouts.items() if v > 0},
    )
    payload = {"type": "hand_result", "room_id": room["id"], **g["result"]}
    await broadcast_room(room, lambda _name: dict(payload))
    await broadcast_game(room)
    await broadcast_room_list()
    schedule_next_hand(room)


def schedule_next_hand(room):
    cancel_room_timer(room, "next_timer")
    room_id = room["id"]

    def fire():
        r = game_rooms.get(room_id)
        if r and r["status"] == "playing" and not r.get("paused"):
            asyncio.ensure_future(next_hand(r))

    room["next_timer"] = asyncio.get_running_loop().call_later(
        GAME_INTERMISSION, fire
    )


async def next_hand(room):
    if not room.get("game"):
        return
    room["game"] = None
    await start_hand(room)


def cancel_room_tasks(room):
    cancel_room_timer(room, "turn_timer")
    cancel_room_timer(room, "next_timer")


async def dissolve_room(room, reason):
    cancel_room_tasks(room)
    game_rooms.pop(room["id"], None)
    with database() as conn, conn:
        for username, member in room["members"].items():
            refund = member["stack"]
            g = room.get("game")
            if g and username in g["order"]:
                refund = round(refund + g["committed"].get(username, 0), 2)
            if refund > 0:
                try:
                    adjust_coins(
                        conn, username, refund, "game_settle", f"游戏厅流局退款：{room['name']}"
                    )
                except (KeyError, ValueError):
                    continue
        conn.execute("DELETE FROM game_escrows WHERE room_id = ?", (room["id"],))
    logger.info("game room %s dissolved: %s", room["id"], reason)
    await broadcast_room(room, lambda _name: {"type": "room_closed", "reason": reason})
    await broadcast_room_list()


async def leave_room_internal(room, username):
    member = room["members"].pop(username, None)
    room["seating"] = [name for name in room["seating"] if name != username]
    if not member:
        return
    refund = member["stack"]
    g = room.get("game")
    mid_hand = bool(g and username in g["order"] and username not in g["folded"])
    if mid_hand:
        g["folded"].add(username)
    set_escrow(username, room["id"], None)
    if refund > 0:
        with database() as conn, conn:
            try:
                adjust_coins(
                    conn, username, refund, "game_settle", f"游戏厅离桌：{room['name']}"
                )
            except (KeyError, ValueError):
                pass
    logger.info("%s left game room %s", username, room["id"])
    if not room["members"]:
        cancel_room_tasks(room)
        game_rooms.pop(room["id"], None)
        await broadcast_room_list()
        return
    if mid_hand:
        await progress_game(room)
    else:
        await broadcast_game(room)
    await broadcast_room_list()


async def handle_list_rooms(websocket, state, data):
    await send_json(
        websocket,
        {"type": "room_list", "rooms": [room_summary(r) for r in game_rooms.values()]},
    )


async def handle_get_room(websocket, state, data):
    user = state.get("user")
    if not user:
        return
    if rate_limited(state, "last_get_room", 0.2):
        return
    room = find_user_room(user["username"])
    if room:
        await send_json(websocket, game_view(room, user["username"]))
        await send_json(
            websocket,
            {
                "type": "room_chat_history",
                "room_id": room["id"],
                "messages": list(room["chat"]),
            },
        )
    else:
        await send_json(websocket, {"type": "room_closed", "reason": ""})


async def handle_create_room(websocket, state, data):
    global room_seq
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_room_op", 3.0):
        await send_json(websocket, {"type": "game_error", "message": "操作太频繁，请稍后再试"})
        return
    username = user["username"]
    if find_user_room(username):
        await send_json(websocket, {"type": "game_error", "message": "你已在一个房间中，请先退出"})
        return
    name = str(data.get("name", "")).strip()[:20]
    game = str(data.get("game") or "holdem")
    if game not in GAME_TYPES:
        game = "holdem"
    buy_in = parse_amount(data.get("buy_in"))
    blind = data.get("blind")
    blind = blind if blind in GAME_BLIND_PRESETS else 5
    if buy_in is None or buy_in < blind * 20:
        await send_json(
            websocket,
            {"type": "game_error", "message": f"买入至少需要 {blind * 20:.0f} 金币（20 倍小盲注）"},
        )
        return
    try:
        with database() as conn, conn:
            balance = conn.execute(
                "SELECT coins FROM users WHERE username = ?", (username,)
            ).fetchone()[0] or 0.0
            if balance < buy_in:
                raise ValueError("金币不足，无法买入")
            adjust_coins(
                conn, username, -buy_in, "game_buyin", f"游戏厅买入：{name}"
            )
    except ValueError as error:
        await send_json(websocket, {"type": "game_error", "message": str(error)})
        return
    room_seq += 1
    room = {
        "id": int(time.time() * 1000) % 1_000_000_000 + room_seq,
        "name": name or f"{display_name(username)}的房间",
        # room["game"] 只存牌局状态（未开局时为 None），游戏名放在 game_type
        "game": None,
        "game_type": game,
        "owner": username,
        "buy_in": buy_in,
        "blind": blind,
        "status": "waiting",
        "seating": [username],
        "members": {username: {"stack": buy_in}},
        "chat": deque(maxlen=30),
        "dealer": None,
        "hand_seq": 0,
        "turn_timer": None,
        "next_timer": None,
    }
    game_rooms[room["id"]] = room
    set_escrow(username, room["id"], buy_in)
    logger.info("game room %s created by %s", room["id"], username)
    await send_json(websocket, {"type": "game_joined", "room": game_view(room, username)})
    await broadcast_room_list()


async def handle_join_room(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_room_op", 1.0):
        await send_json(websocket, {"type": "game_error", "message": "操作太频繁，请稍后再试"})
        return
    username = user["username"]
    if find_user_room(username):
        await send_json(websocket, {"type": "game_error", "message": "你已在一个房间中，请先退出"})
        return
    room = game_rooms.get(data.get("room_id"))
    if not room:
        await send_json(websocket, {"type": "game_error", "message": "房间不存在或已解散"})
        return
    if len(room["seating"]) >= GAME_MAX_PLAYERS:
        await send_json(websocket, {"type": "game_error", "message": "房间已满"})
        return
    buy_in = room["buy_in"]
    try:
        with database() as conn, conn:
            balance = conn.execute(
                "SELECT coins FROM users WHERE username = ?", (username,)
            ).fetchone()[0] or 0.0
            if balance < buy_in:
                raise ValueError(f"金币不足，进入该房间需要买入 {buy_in:.2f} 金币")
            adjust_coins(
                conn, username, -buy_in, "game_buyin", f"游戏厅买入：{room['name']}"
            )
    except ValueError as error:
        await send_json(websocket, {"type": "game_error", "message": str(error)})
        return
    room["seating"].append(username)
    room["members"][username] = {"stack": buy_in}
    set_escrow(username, room["id"], buy_in)
    await send_json(websocket, {"type": "game_joined", "room": game_view(room, username)})
    await send_json(
        websocket,
        {
            "type": "room_chat_history",
            "room_id": room["id"],
            "messages": list(room["chat"]),
        },
    )
    await broadcast_game(room)
    await broadcast_room_list()


async def handle_leave_room(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    room = find_user_room(user["username"])
    if not room:
        await send_json(websocket, {"type": "game_error", "message": "你不在任何房间中"})
        return
    if room["owner"] == user["username"]:
        reason = "房主流局" if room["status"] == "playing" else "房主解散了房间"
        await dissolve_room(room, reason)
        return
    await leave_room_internal(room, user["username"])
    await broadcast_game(room)
    await send_json(websocket, {"type": "room_closed", "reason": "已离桌"})


async def handle_start_game(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    room = find_user_room(user["username"])
    if not room or room["owner"] != user["username"]:
        await send_json(websocket, {"type": "game_error", "message": "只有房主可以开始游戏"})
        return
    if room["status"] == "playing":
        await send_json(websocket, {"type": "game_error", "message": "游戏已在进行中"})
        return
    if len(stack_owners(room)) < 2:
        await send_json(
            websocket,
            {"type": "game_error", "message": "至少需要两名有筹码的玩家才能开局"},
        )
        return
    room["status"] = "playing"
    room["dealer"] = None
    logger.info("game room %s started by %s", room["id"], user["username"])
    await start_hand(room)
    await broadcast_room_list()


async def handle_poker_action(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_poker_action", 0.3):
        return
    room = find_user_room(user["username"])
    if not room or not room.get("game"):
        return
    action = str(data.get("action", ""))
    await perform_action(
        room, user["username"], action, parse_amount(data.get("raise_to"))
    )


def cancel_leave_timer(room_id, username):
    handle = room_leave_timers.pop((room_id, username), None)
    if handle:
        handle.cancel()


def fire_leave_timer(room_id, username):
    room_leave_timers.pop((room_id, username), None)
    asyncio.ensure_future(delayed_room_cleanup(room_id, username))


async def delayed_room_cleanup(room_id, username):
    """断线宽限期内没有回到游戏厅（或直播间），再结算房间去留。"""
    await asyncio.sleep(GAME_DISCONNECT_GRACE)
    room = game_rooms.get(room_id)
    if not room or username not in room["members"]:
        return
    for client_state in clients.values():
        other = client_state.get("user")
        if other and other["username"] == username:
            return
    if room["owner"] == username:
        await dissolve_room(room, "房主离开游戏厅较久")
    else:
        await leave_room_internal(room, username)
        await broadcast_game(room)


async def handle_pause_game(websocket, state, data):
    """房主暂停/继续牌局：停掉回合与下一手计时器，恢复时按剩余时间续上。"""
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    room = find_user_room(user["username"])
    if not room or room["owner"] != user["username"] or room["status"] != "playing":
        await send_json(websocket, {"type": "game_error", "message": "只有房主可以在游戏中管理牌局"})
        return
    if rate_limited(state, "last_game_admin", 0.5):
        return
    paused = bool(data.get("paused"))
    if paused == bool(room.get("paused")):
        return
    room["paused"] = paused
    if paused:
        cancel_room_timer(room, "turn_timer")
        cancel_room_timer(room, "next_timer")
        g = room.get("game")
        if g and g.get("deadline"):
            g["pause_remaining"] = max(1.0, g["deadline"] - time.time())
        logger.info("game room %s paused by %s", room["id"], user["username"])
    else:
        g = room.get("game")
        if g and g.get("to_act"):
            g["deadline"] = time.time() + (g.get("pause_remaining") or GAME_TURN_TIMEOUT)
            schedule_turn_timer(room)
        elif not g:
            schedule_next_hand(room)
        logger.info("game room %s resumed by %s", room["id"], user["username"])
    await broadcast_game(room)
    await broadcast_room_list()


async def handle_restart_game(websocket, state, data):
    """房主重新开始：本手已投入的筹码退回各家，随后重新发一手。"""
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    room = find_user_room(user["username"])
    if not room or room["owner"] != user["username"]:
        await send_json(websocket, {"type": "game_error", "message": "只有房主可以重新开始"})
        return
    if room["status"] != "playing":
        await send_json(websocket, {"type": "game_error", "message": "游戏尚未开始"})
        return
    if rate_limited(state, "last_game_admin", 0.5):
        return
    cancel_room_timer(room, "turn_timer")
    cancel_room_timer(room, "next_timer")
    g = room.get("game")
    if g:
        for name, amount in g.get("committed", {}).items():
            member = room["members"].get(name)
            if member and amount > 0:
                member["stack"] = round(member["stack"] + amount, 2)
        for name in room["members"]:
            set_escrow(name, room["id"], room["members"][name]["stack"])
    room["game"] = None
    room["paused"] = False
    logger.info("game room %s restarted by %s", room["id"], user["username"])
    await broadcast_room(room, lambda _name: {"type": "game_restart"})
    await start_hand(room)


async def handle_room_chat(websocket, state, data):
    """房间内聊天：只广播给房间成员，记录在内存里随房间销毁。"""
    user = state.get("user")
    if not user:
        return
    room = find_user_room(user["username"])
    if not room:
        return
    if rate_limited(state, "last_room_message", 1.0):
        await send_json(websocket, {"type": "error", "message": "发送太快了"})
        return
    text = str(data.get("text", "")).strip()[:MAX_CHAT_LENGTH]
    if not text:
        return
    message = {
        "type": "room_chat",
        "room_id": room["id"],
        "username": user["username"],
        "nickname": user.get("nickname") or "",
        "role": user["role"],
        "text": text,
        "time": time.strftime("%m/%d %H:%M"),
    }
    room["chat"].append(message)
    await broadcast_room(room, lambda _name: dict(message))


async def cleanup_rooms_on_disconnect(state):
    user = state.get("user")
    if not user:
        return
    username = user["username"]
    for client_state in clients.values():
        other = client_state.get("user")
        if other and other["username"] == username:
            return
    room = find_user_room(username)
    if not room:
        return
    # 页面间跳转（游戏厅 <-> 直播间）会短暂断线，延迟再结算，回到页面即取消
    cancel_leave_timer(room["id"], username)
    room_leave_timers[(room["id"], username)] = (
        asyncio.get_running_loop().call_later(
            GAME_DISCONNECT_GRACE,
            fire_leave_timer,
            room["id"],
            username,
        )
    )


def on_user_authenticated(username):
    """登录/恢复会话时取消该用户的离桌倒计时。"""
    room = find_user_room(username)
    if room:
        cancel_leave_timer(room["id"], username)


async def handle_admin_set_coins(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if user.get("role") not in ("admin", "streamer"):
        await send_json(websocket, {"type": "coins_error", "message": "没有权限执行此操作"})
        return
    target = str(data.get("username", "")).strip()
    try:
        coins = round(float(data.get("coins")), 2)
    except (TypeError, ValueError):
        coins = -1.0
    if not target:
        await send_json(websocket, {"type": "coins_error", "message": "请输入用户名"})
        return
    if not math.isfinite(coins) or coins < 0:
        await send_json(
            websocket,
            {"type": "coins_error", "message": "金币数量无效（不能低于 0）"},
        )
        return
    try:
        with database() as conn, conn:
            old = conn.execute(
                "SELECT coins FROM users WHERE username = ?", (target,)
            ).fetchone()
            if old is None:
                raise ValueError("用户不存在")
            delta = round(coins - (old[0] or 0.0), 2)
            conn.execute(
                "UPDATE users SET coins = ? WHERE username = ?", (coins, target)
            )
            record_coins(conn, target, delta, coins, "admin", "管理员调整")
    except ValueError as error:
        await send_json(websocket, {"type": "coins_error", "message": str(error)})
        return
    logger.info("admin %s set coins of %s to %.2f", user["username"], target, coins)
    await send_json(
        websocket, {"type": "admin_coins_done", "username": target, "coins": coins}
    )
    await push_balance(target, coins)


async def handle_list_invites(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    with database() as conn:
        rows = conn.execute(
            "SELECT code, created_at FROM invite_codes "
            "WHERE created_by = ? AND used_by IS NULL ORDER BY created_at DESC",
            (user["username"],),
        ).fetchall()
    await send_json(
        websocket,
        {
            "type": "invite_list",
            "codes": [
                {"code": code, "created_at": created_at} for code, created_at in rows
            ],
        },
    )


async def handle_create_invite(websocket, state, data):
    user = state.get("user")
    if not user:
        await send_json(websocket, {"type": "auth_error", "message": "请先登录"})
        return
    if rate_limited(state, "last_invite_create", 5.0):
        await send_json(websocket, {"type": "invite_error", "message": "操作太频繁，请稍后再试"})
        return
    with database() as conn, conn:
        unused = conn.execute(
            "SELECT COUNT(*) FROM invite_codes "
            "WHERE created_by = ? AND used_by IS NULL",
            (user["username"],),
        ).fetchone()[0]
        if unused >= INVITE_UNUSED_LIMIT:
            await send_json(
                websocket,
                {"type": "invite_error", "message": "未使用的邀请码已达上限（5 个），请先用掉一些"},
            )
            return
        code = secrets.token_urlsafe(8)
        conn.execute(
            "INSERT INTO invite_codes (code, created_at, created_by) VALUES (?, ?, ?)",
            (code, int(time.time()), user["username"]),
        )
    logger.info("invite created by %s", user["username"])
    await send_json(websocket, {"type": "invite_created", "code": code})


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
        "time": time.strftime("%m/%d %H:%M"),
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
    "list_invites": handle_list_invites,
    "create_invite": handle_create_invite,
    "chat": handle_chat,
    "get_finance": handle_get_finance,
    "transfer_coins": handle_transfer_coins,
    "get_bet": handle_get_bet,
    "create_bet": handle_create_bet,
    "place_bet": handle_place_bet,
    "settle_bet": handle_settle_bet,
    "cancel_bet": handle_cancel_bet,
    "admin_set_coins": handle_admin_set_coins,
    "list_rooms": handle_list_rooms,
    "get_room": handle_get_room,
    "create_room": handle_create_room,
    "join_room": handle_join_room,
    "leave_room": handle_leave_room,
    "start_game": handle_start_game,
    "poker_action": handle_poker_action,
    "pause_game": handle_pause_game,
    "restart_game": handle_restart_game,
    "room_chat": handle_room_chat,
}


def connection_client(websocket):
    """兼容新旧 websockets 实现取连接路径，识别游戏厅独立页。"""
    request = getattr(websocket, "request", None)
    path = getattr(request, "path", None) or getattr(websocket, "path", "")
    return "game" if "client=game" in str(path) else ""


async def handler(websocket):
    state = {
        "user": None,
        "client": connection_client(websocket),
        "send_lock": asyncio.Lock(),
        "last_message": 0.0,
        "last_auth_attempt": 0.0,
        "last_profile_update": 0.0,
        "last_invite_create": 0.0,
        "last_transfer": 0.0,
        "last_bet_action": 0.0,
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
        await cleanup_rooms_on_disconnect(state)
        await broadcast_online_count()


async def main():
    global active_bet
    init_db()
    refund_game_escrows()
    active_bet = load_open_bet()
    if active_bet:
        logger.info(
            "resumed open bet #%d from %s: %s",
            active_bet["id"],
            active_bet["creator"],
            active_bet["question"],
        )
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
