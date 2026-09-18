"""每日签到与免费抽奖。所有写操作由宿主在同一个 SQLite 写事务中调用。"""
import re
import secrets
from datetime import datetime, timedelta, timezone

CHECKIN_TICKETS = 5
CHECKIN_TZ = timezone(timedelta(hours=8))
PRIZE_TIERS = ((20, 100, 88), (101, 200, 10), (201, 500, 2))


def init_rewards(conn):
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "lottery_tickets" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN lottery_tickets INTEGER NOT NULL DEFAULT 0")
    conn.execute("""CREATE TABLE IF NOT EXISTS daily_checkins (
        user_id INTEGER NOT NULL, day TEXT NOT NULL, created_at INTEGER NOT NULL,
        PRIMARY KEY(user_id, day))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS lottery_draws (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL,
        request_id TEXT NOT NULL, amount INTEGER NOT NULL, created_at INTEGER NOT NULL,
        UNIQUE(user_id, request_id))""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_lottery_user ON lottery_draws(user_id, id)")


def checkin_day(now):
    return datetime.fromtimestamp(now, CHECKIN_TZ).date().isoformat()


def rewards_state(conn, username, now):
    user = conn.execute("SELECT id, lottery_tickets, coins FROM users WHERE username = ?",
                        (username,)).fetchone()
    if user is None:
        raise ValueError("账号不存在，请重新登录")
    day = checkin_day(now)
    checked_in = conn.execute("SELECT 1 FROM daily_checkins WHERE user_id = ? AND day = ?",
                              (user[0], day)).fetchone() is not None
    midnight = datetime.fromtimestamp(now, CHECKIN_TZ).replace(hour=0, minute=0, second=0, microsecond=0)
    recent = conn.execute("SELECT amount, created_at FROM lottery_draws WHERE user_id = ? "
                          "ORDER BY id DESC LIMIT 10", (user[0],)).fetchall()
    return {"username": username, "day": day, "checked_in": checked_in,
            "tickets": user[1], "coins": round(user[2], 2), "daily_tickets": CHECKIN_TICKETS,
            "server_time": int(now),
            "next_reset_at": int((midnight + timedelta(days=1)).timestamp()),
            "prize_tiers": [{"min": low, "max": high, "percent": weight}
                            for low, high, weight in PRIZE_TIERS],
            "history": [{"amount": amount, "created_at": created} for amount, created in recent]}


def claim_checkin(conn, username, now):
    user = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if user is None:
        raise ValueError("账号不存在，请重新登录")
    inserted = conn.execute("INSERT OR IGNORE INTO daily_checkins(user_id, day, created_at) "
                            "VALUES (?, ?, ?)", (user[0], checkin_day(now), int(now))).rowcount
    if inserted:
        conn.execute("UPDATE users SET lottery_tickets = lottery_tickets + ? WHERE id = ?",
                     (CHECKIN_TICKETS, user[0]))
    return CHECKIN_TICKETS if inserted else 0


def pick_prize():
    """先按整百分比选档，再在该档的整数金币范围内均匀抽取（均含端点）。"""
    roll = secrets.randbelow(100)
    for low, high, weight in PRIZE_TIERS:
        if roll < weight:
            return low + secrets.randbelow(high - low + 1)
        roll -= weight
    raise AssertionError("奖池权重必须合计 100")


def draw_lottery(conn, username, request_id, now, credit_coins):
    if not isinstance(request_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{8,80}", request_id):
        raise ValueError("抽奖请求无效，请重新打开抽奖面板")
    user = conn.execute("SELECT id, lottery_tickets FROM users WHERE username = ?",
                        (username,)).fetchone()
    if user is None:
        raise ValueError("账号不存在，请重新登录")
    saved = conn.execute("SELECT amount FROM lottery_draws WHERE user_id = ? AND request_id = ?",
                         (user[0], request_id)).fetchone()
    if saved:
        return saved[0], True
    if user[1] <= 0:
        raise ValueError("抽奖机会不足，签到可领取 5 次机会")
    amount = pick_prize()
    conn.execute("UPDATE users SET lottery_tickets = lottery_tickets - 1 WHERE id = ?", (user[0],))
    draw = conn.execute("INSERT INTO lottery_draws(user_id, request_id, amount, created_at) "
                        "VALUES (?, ?, ?, ?)", (user[0], request_id, amount, int(now)))
    credit_coins(conn, username, amount, "lottery_win", "每日签到抽奖奖励",
                 ref=f"lottery:{draw.lastrowid}")
    return amount, False
