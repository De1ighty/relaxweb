#!/usr/bin/env python3
"""游戏引擎单元测试：python3 tests/test_games.py

只测纯逻辑（不发网络请求）：
  - 德州扑克牌力判定与边池分配（games/holdem.py 纯函数）
  - BaseRoom 计时器/暂停/成员管理（games/base.py）

新增游戏时请照此为它的纯函数补一组用例。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from games.base import BaseRoom, ROOM_TYPES, create_room  # noqa: E402
from games.holdem import best7, build_side_pots, distribute_pots, evaluate5  # noqa: E402

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def card(rank, suit):
    return (rank, suit)


def test_evaluate():
    royal = [card(14, s) for s in (0, 1)] + [card(13, 0), card(12, 0), card(11, 0), card(10, 0)]
    check("皇家同花顺", best7(royal) == (8, 14))
    quads = [card(9, 0), card(9, 1), card(9, 2), card(9, 3), card(5, 0), card(6, 1), card(7, 2)]
    check("四条", best7(quads) == (7, 9, 7))
    wheel = [card(14, 0), card(5, 1), card(4, 0), card(3, 2), card(2, 1), card(9, 3), card(9, 0)]
    check("A5低顺", best7(wheel) == (4, 5))
    pair = [card(2, 0), card(2, 1), card(5, 0), card(6, 1), card(8, 2)]
    check("一对", evaluate5(pair) == (1, 2, 8, 6, 5))


def test_side_pots():
    committed = {"a": 100.0, "b": 100.0, "c": 40.0}
    folded = {"b"}
    pots = build_side_pots(committed, folded)
    # c 只有 40：主池 120（a/b/c），边池 120（仅 a）
    check("边池分层", len(pots) == 2 and pots[0]["amount"] == 120 and pots[1]["amount"] == 120,
          str(pots))
    hands = {"a": (1, 13), "b": (1, 12), "c": (3, 7)}
    payouts = distribute_pots(pots, hands)
    check("边池分配", payouts == {"c": 120.0, "a": 120.0}, str(payouts))


def test_room_lifecycle():
    async def run():
        room = create_room("holdem", room_id=1, name="测试", owner="a", buy_in=100, blind=5)
        room.add_member("a", 100)
        room.add_member("b", 100)
        views = []

        async def broadcast_views():
            views.append(1)

        room.broadcast_views = broadcast_views
        await room.start()
        started = room.in_hand() and room.status == "playing"
        room.pause()
        paused = room.paused and not room.timers
        room.resume()
        resumed = not room.paused
        left = room.remove_member("b")
        return started, paused, resumed, left

    started, paused, resumed, left = asyncio.run(run())
    check("开局发牌", started)
    check("暂停清计时器", paused)
    check("恢复", resumed)
    check("成员移除", left == {"stack": 90.0}, "开局后大盲注已提交")


def test_registry():
    check("注册表包含holdem", "holdem" in ROOM_TYPES)
    try:
        create_room("unknown")
        check("未注册类型报错", False)
    except ValueError:
        check("未注册类型报错", True)


test_evaluate()
test_side_pots()
test_room_lifecycle()
test_registry()
failed = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
