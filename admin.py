#!/usr/bin/env python3
"""资产后端管理入口（命令行）。

数据库与 chat_server 一致：读 config.json 的 database.file，可用环境变量 LIVE_DB_FILE 覆盖：
  python3 admin.py <命令> [参数]
  LIVE_DB_FILE=/path/users.db python3 admin.py <命令> [参数]

命令：
  list [用户名]         查看全部用户金币概览 / 指定用户的金币与最近记录
  set <用户名> <数量>    直接设置金币数量（记一条「管理员调整」明细）
  add <用户名> <数量>    增加金币
  sub <用户名> <数量>    扣除金币
  restore <用户名>       一键还原该用户：金币回新玩家默认值，删除其全部金币记录
  restore-all [-y]      一键还原所有用户：全员金币回默认值，清空全部金币记录
  clear-log [-y]        仅清空全部金币记录（不改变现有余额）

说明：还原/清空是物理删除记录、不写对账明细；set/add/sub 会记一条
「管理员调整」明细。修改新玩家默认金币请改 config.json 的
economy.new_user_coins（或环境变量 NEW_USER_COINS），改后需重启 live-chat 服务。
"""
import sys

from chat_server import NEW_USER_COINS, adjust_coins, database, init_db

PROG = "admin.py"


def fail(message):
    print(f"失败：{message}")
    sys.exit(1)


def get_user(conn, username):
    return conn.execute(
        "SELECT username, nickname, coins FROM users WHERE username = ?",
        (username,),
    ).fetchone()


def money_arg(raw):
    try:
        value = round(float(raw), 2)
    except ValueError:
        fail("数量必须是数字")
    if value < 0:
        fail("数量不能为负")
    return value


def confirm(prompt, assume_yes):
    if assume_yes:
        return True
    try:
        answer = input(f"{prompt} (y/N) ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def cmd_list(username=None):
    with database() as conn:
        if username:
            row = get_user(conn, username)
            if not row:
                fail("用户不存在")
            print(f"用户 {row[0]}  昵称 {row[1] or '-'}  金币 {row[2]:.2f}")
            rows = conn.execute(
                "SELECT amount, balance, kind, detail, created_at "
                "FROM coin_transactions WHERE username = ? "
                "ORDER BY id DESC LIMIT 20",
                (username,),
            ).fetchall()
            if not rows:
                print("（无金币记录）")
                return
            for amount, balance, kind, detail, _ in rows:
                print(f"  {amount:+.2f}  余额 {balance:.2f}  [{kind}] {detail}")
            return
        rows = conn.execute(
            "SELECT username, nickname, coins FROM users ORDER BY username"
        ).fetchall()
        total = 0.0
        for name, nickname, coins in rows:
            total += coins or 0.0
            print(f"{name}  {nickname or '-'}  {coins:.2f}")
        print(f"-- 共 {len(rows)} 名用户，金币总量 {total:.2f}")


def cmd_adjust(mode, username, raw):
    amount = money_arg(raw)
    init_db()
    with database() as conn, conn:
        row = get_user(conn, username)
        if not row:
            fail("用户不存在")
        if mode == "add":
            delta = amount
        elif mode == "sub":
            delta = -amount
        else:
            delta = round(amount - (row[2] or 0.0), 2)
            if delta == 0:
                print(f"完成：{username} 金币已为 {amount:.2f}（无变化）")
                return
        try:
            balance = adjust_coins(conn, username, delta, "admin", "管理员调整")
        except ValueError as error:
            fail(str(error))
        print(f"完成：{username} 当前金币 {balance:.2f}")


def cmd_restore(username=None, assume_yes=False):
    if username is None:
        with database() as conn:
            count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if not confirm(
            f"将 {count} 名用户的金币全部重置为 {NEW_USER_COINS:.0f} "
            "并删除全部金币记录？",
            assume_yes,
        ):
            print("已取消")
            return
        init_db()
        with database() as conn, conn:
            conn.execute("UPDATE users SET coins = ?", (NEW_USER_COINS,))
            conn.execute("DELETE FROM coin_transactions")
        print(
            f"完成：{count} 名用户金币已重置为 {NEW_USER_COINS:.2f}，"
            "金币记录已全部删除"
        )
        return
    init_db()
    with database() as conn, conn:
        if not get_user(conn, username):
            fail("用户不存在")
        conn.execute(
            "UPDATE users SET coins = ? WHERE username = ?",
            (NEW_USER_COINS, username),
        )
        conn.execute("DELETE FROM coin_transactions WHERE username = ?", (username,))
    print(f"完成：{username} 金币已重置为 {NEW_USER_COINS:.2f}，其金币记录已删除")


def cmd_clear_log(assume_yes=False):
    if not confirm("确认清空全部金币记录？（不改变现有余额）", assume_yes):
        print("已取消")
        return
    init_db()
    with database() as conn, conn:
        conn.execute("DELETE FROM coin_transactions")
    print("完成：金币记录已清空（余额不变）")


def main(argv):
    args = [a for a in argv if a != "-y"]
    assume_yes = len(args) != len(argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    command, rest = args[0], args[1:]

    if command == "list":
        cmd_list(rest[0] if rest else None)
    elif command == "set" and len(rest) == 2:
        cmd_adjust("set", rest[0], rest[1])
    elif command == "add" and len(rest) == 2:
        cmd_adjust("add", rest[0], rest[1])
    elif command == "sub" and len(rest) == 2:
        cmd_adjust("sub", rest[0], rest[1])
    elif command == "restore" and len(rest) == 1:
        cmd_restore(rest[0], assume_yes)
    elif command == "restore-all":
        cmd_restore(None, assume_yes)
    elif command == "clear-log":
        cmd_clear_log(assume_yes)
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main(sys.argv[1:])
