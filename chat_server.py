import asyncio
import base64
import hashlib
import hmac
import json
import os
import re
import sqlite3
import time
from collections import deque

import websockets


HOST = "0.0.0.0"
PORT = 8765

DB_FILE = "/path/to/relaxweb/users.db"

clients = {}
history = deque(maxlen=50)


# ==============================
# 数据库
# ==============================

def init_db():
    conn = sqlite3.connect(DB_FILE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE COLLATE NOCASE,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()


# ==============================
# 密码处理
# ==============================

def hash_password(password, salt=None):

    if salt is None:
        salt_bytes = os.urandom(16)
    else:
        salt_bytes = base64.b64decode(salt)

    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        310000
    )

    return (
        base64.b64encode(password_hash).decode(),
        base64.b64encode(salt_bytes).decode()
    )


def verify_password(password, saved_hash, salt):

    calculated_hash, _ = hash_password(
        password,
        salt
    )

    return hmac.compare_digest(
        calculated_hash,
        saved_hash
    )


# ==============================
# 用户名检查
# ==============================

def valid_username(username):

    if len(username) < 2 or len(username) > 20:
        return False

    pattern = r"^[\u4e00-\u9fa5A-Za-z0-9_-]+$"

    return re.match(pattern, username) is not None


# ==============================
# 注册
# ==============================

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

        conn = sqlite3.connect(DB_FILE)

        conn.execute(
            """
            INSERT INTO users
            (username, password_hash, salt, role, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                username,
                password_hash,
                salt,
                "user",
                int(time.time())
            )
        )

        conn.commit()
        conn.close()

        return True, "注册成功"

    except sqlite3.IntegrityError:

        return False, "这个用户名已经被注册"


# ==============================
# 登录
# ==============================

def authenticate_user(username, password):

    conn = sqlite3.connect(DB_FILE)

    cursor = conn.execute(
        """
        SELECT username, password_hash, salt, role
        FROM users
        WHERE username = ?
        """,
        (username.strip(),)
    )

    row = cursor.fetchone()

    conn.close()

    if not row:
        return None

    real_username, saved_hash, salt, role = row

    if not verify_password(
        password,
        saved_hash,
        salt
    ):
        return None

    return {
        "username": real_username,
        "role": role
    }


# ==============================
# WebSocket工具
# ==============================

async def send_json(websocket, data):

    await websocket.send(
        json.dumps(
            data,
            ensure_ascii=False
        )
    )


async def broadcast(data):

    if not clients:
        return

    message = json.dumps(
        data,
        ensure_ascii=False
    )

    dead_clients = []

    for websocket in list(clients.keys()):

        try:
            await websocket.send(message)

        except Exception:
            dead_clients.append(websocket)

    for websocket in dead_clients:
        clients.pop(websocket, None)


async def broadcast_online_count():

    await broadcast({
        "type": "online",
        "count": len(clients)
    })


# ==============================
# 连接处理
# ==============================

async def handler(websocket):

    clients[websocket] = {
        "user": None,
        "last_message": 0,
        "last_auth_attempt": 0
    }

    print(
        f"新连接，当前在线：{len(clients)}"
    )

    await send_json(
        websocket,
        {
            "type": "history",
            "messages": list(history)
        }
    )

    await broadcast_online_count()

    try:

        async for raw_message in websocket:

            try:
                data = json.loads(raw_message)
            except json.JSONDecodeError:
                continue

            message_type = data.get("type")


            # ======================
            # 注册
            # ======================

            if message_type == "register":

                now = time.time()

                if (
                    now -
                    clients[websocket]["last_auth_attempt"]
                    < 1.5
                ):

                    await send_json(
                        websocket,
                        {
                            "type": "auth_error",
                            "message": "操作太频繁，请稍后再试"
                        }
                    )

                    continue

                clients[websocket][
                    "last_auth_attempt"
                ] = now

                username = str(
                    data.get("username", "")
                ).strip()

                password = str(
                    data.get("password", "")
                )

                success, message = register_user(
                    username,
                    password
                )

                if success:

                    await send_json(
                        websocket,
                        {
                            "type": "register_success",
                            "message": message
                        }
                    )

                else:

                    await send_json(
                        websocket,
                        {
                            "type": "auth_error",
                            "message": message
                        }
                    )


            # ======================
            # 登录
            # ======================

            elif message_type == "login":

                username = str(
                    data.get("username", "")
                ).strip()

                password = str(
                    data.get("password", "")
                )

                user = authenticate_user(
                    username,
                    password
                )

                if not user:

                    await send_json(
                        websocket,
                        {
                            "type": "auth_error",
                            "message": "用户名或密码错误"
                        }
                    )

                    continue


                clients[websocket]["user"] = user

                print(
                    f"用户登录：{user['username']}"
                )

                await send_json(
                    websocket,
                    {
                        "type": "login_success",
                        "username": user["username"],
                        "role": user["role"]
                    }
                )


            # ======================
            # 聊天
            # ======================

            elif message_type == "chat":

                user = clients[
                    websocket
                ].get("user")

                if not user:

                    await send_json(
                        websocket,
                        {
                            "type": "auth_error",
                            "message": "请先登录"
                        }
                    )

                    continue


                text = str(
                    data.get("text", "")
                ).strip()

                if not text:
                    continue

                if len(text) > 200:
                    text = text[:200]


                now = time.time()

                last_message = clients[
                    websocket
                ]["last_message"]

                if now - last_message < 1:

                    await send_json(
                        websocket,
                        {
                            "type": "error",
                            "message": "发送太快了"
                        }
                    )

                    continue


                clients[
                    websocket
                ]["last_message"] = now


                message = {
                    "type": "chat",
                    "username": user["username"],
                    "role": user["role"],
                    "text": text,
                    "time": time.strftime("%H:%M")
                }

                history.append(message)

                print(
                    f"[{user['username']}] {text}"
                )

                await broadcast(message)


    except websockets.ConnectionClosed:
        pass

    finally:

        clients.pop(
            websocket,
            None
        )

        print(
            f"连接断开，当前在线：{len(clients)}"
        )

        await broadcast_online_count()


# ==============================
# 主程序
# ==============================

async def main():

    init_db()

    print(
        f"用户数据库：{DB_FILE}"
    )

    print(
        f"聊天室服务器：ws://{HOST}:{PORT}"
    )

    async with websockets.serve(
        handler,
        HOST,
        PORT
    ):

        await asyncio.Future()


if __name__ == "__main__":

    asyncio.run(main())

