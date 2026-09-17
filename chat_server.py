import asyncio
import base64
import hashlib
import hmac
import json
import logging
import math
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

clients = {}
history = deque(maxlen=50)
register_ip_times = {}
active_bet = None
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
            try:
                await socket.send(payload)
            except Exception:
                clients.pop(socket, None)


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
}


async def handler(websocket):
    state = {
        "user": None,
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
        await broadcast_online_count()


async def main():
    global active_bet
    init_db()
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
