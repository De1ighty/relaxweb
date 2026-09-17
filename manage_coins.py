#!/usr/bin/env python3
"""金币后台管理：python3 manage_coins.py set|add|sub 用户名 数量"""
import sys

from chat_server import adjust_coins, database, init_db


def main():
    if len(sys.argv) != 4 or sys.argv[1] not in ("set", "add", "sub"):
        print(__doc__)
        sys.exit(1)
    command, username, raw = sys.argv[1], sys.argv[2].strip(), sys.argv[3]
    try:
        amount = round(float(raw), 2)
    except ValueError:
        print("数量必须是数字")
        sys.exit(1)
    if amount < 0:
        print("数量不能为负")
        sys.exit(1)
    init_db()
    try:
        with database() as conn, conn:
            row = conn.execute(
                "SELECT username, coins FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not row:
                print(f"用户不存在：{username}")
                sys.exit(1)
            if command == "set":
                delta = round(amount - (row[1] or 0.0), 2)
                balance = (
                    adjust_coins(conn, row[0], delta, "admin", "管理员调整")
                    if delta
                    else round(row[1] or 0.0, 2)
                )
            elif command == "add":
                balance = adjust_coins(conn, row[0], amount, "admin", "管理员调整")
            else:
                balance = adjust_coins(conn, row[0], -amount, "admin", "管理员调整")
    except ValueError as error:
        print(f"失败：{error}")
        sys.exit(1)
    print(f"完成：{row[0]} 当前金币 {balance:.2f}")


if __name__ == "__main__":
    main()
