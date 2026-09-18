#!/usr/bin/env python3
"""游戏引擎单元测试：python3 tests/test_games.py

只测纯逻辑（不发网络请求）：
  - 德州扑克牌力判定与边池分配（games/holdem.py 纯函数）
  - UNO 牌堆构成、出牌判定与一局流程（games/uno.py）
  - BaseRoom 计时器/暂停/成员管理（games/base.py）

新增游戏时请照此为它的纯函数补一组用例。
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from games.base import BaseRoom, ROOM_TYPES, create_room  # noqa: E402
from games.holdem import best7, build_side_pots, distribute_pots, evaluate5  # noqa: E402
from games.uno import build_deck, card_label, matches  # noqa: E402

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
    check("注册表包含uno", "uno" in ROOM_TYPES)
    try:
        create_room("unknown")
        check("未注册类型报错", False)
    except ValueError:
        check("未注册类型报错", True)


def test_uno_deck_and_matches():
    deck = build_deck()
    check("UNO 牌堆108张", len(deck) == 108)
    colored = [c for c in deck if c["c"] != "w"]
    check("UNO 每色25张", all(
        sum(1 for c in colored if c["c"] == color) == 25 for color in "rygb"))
    wilds = [c for c in deck if c["c"] == "w"]
    check("UNO 万能牌8张", len(wilds) == 8
          and sum(1 for c in wilds if c["v"] == "wild") == 4)
    check("UNO 同色可出", matches("r", "5", {"c": "r", "v": "7"}))
    check("UNO 同数可出", matches("r", "5", {"c": "b", "v": "5"}))
    check("UNO 万能可出", matches("r", "5", {"c": "w", "v": "wd4"}))
    check("UNO 不匹配不可出", not matches("r", "5", {"c": "g", "v": "9"}))
    check("UNO 牌面名称", card_label({"c": "r", "v": "d2"}) == "红+2"
          and card_label({"c": "w", "v": "wild"}) == "换色")


def test_uno_lifecycle():
    async def run():
        room = create_room("uno", room_id=2, name="UNO测试", owner="a",
                           buy_in=100, blind=5)
        room.add_member("a", 100)
        room.add_member("b", 100)
        room.add_member("c", 100)

        async def broadcast_views():
            pass

        async def broadcast_payload(payload):
            pass

        room.broadcast_views = broadcast_views
        room.broadcast_payload = broadcast_payload
        await room.start()
        g = room.game
        dealt = room.in_hand() and all(len(h) == 7 for h in g["hands"].values())
        first_number = g["discard"][-1]["v"].isdigit()
        order = g["order"]

        # a 出一张同色牌：弃牌堆/当前色更新，轮到下家
        g["hands"]["a"] = [{"c": "r", "v": "3"}, {"c": "b", "v": "8"}]
        g["color"], g["value"] = "r", "5"
        g["idx"] = order.index("a")
        g["to_act"] = "a"
        await room.perform_action("a", "play", {"card": 0})
        played = (g["discard"][-1] == {"c": "r", "v": "3"}
                  and g["color"] == "r" and g["to_act"] != "a")

        # b 摸到不可出的牌：自动轮到 c
        g["hands"]["b"] = [{"c": "g", "v": "2"}]
        g["color"], g["value"] = "r", "5"
        g["idx"] = order.index("b")
        g["to_act"] = "b"
        g["deck"].append({"c": "g", "v": "9"})
        await room.perform_action("b", "draw", {})
        draw_pass = g["to_act"] == "c" and len(g["hands"]["b"]) == 2

        # c 摸到可出的牌：进入二选一，选择保留并跳过
        g["hands"]["c"] = [{"c": "g", "v": "6"}]
        g["color"], g["value"] = "r", "5"
        g["idx"] = order.index("c")
        g["to_act"] = "c"
        g["deck"].append({"c": "r", "v": "4"})
        await room.perform_action("c", "draw", {})
        drawn_pending = g["drawn_state"] == "c" and g["to_act"] == "c"
        await room.perform_action("c", "pass", {})
        kept = g["to_act"] != "c" and g["drawn_state"] is None

        # +2：下家摸 2 且被跳过（b 此前已有 2 张手牌）
        g["hands"]["a"] = [{"c": "r", "v": "d2"}, {"c": "b", "v": "3"}]
        g["color"], g["value"] = "r", "5"
        g["idx"] = order.index("a")
        g["to_act"] = "a"
        await room.perform_action("a", "play", {"card": 0})
        victim = order[(order.index("a") + 1) % len(order)]
        d2 = (len(g["hands"][victim]) == 4 and g["to_act"]
              == order[(order.index("a") + 2) % len(order)])

        # 剩 1 张进入 UNO 窗口：补喊后解除
        pending = "a" in g["uno_pending"]
        await room.perform_action("a", "uno", {})
        called = "a" not in g["uno_pending"]
        return dealt, first_number, played, draw_pass, drawn_pending, kept, d2, pending, called

    (dealt, first_number, played, draw_pass, drawn_pending, kept, d2,
     pending, called) = asyncio.run(run())
    check("UNO 开局发牌", dealt)
    check("UNO 首张为数字牌", first_number)
    check("UNO 出牌换手", played)
    check("UNO 摸牌不出自动过", draw_pass)
    check("UNO 摸牌可出二选一", drawn_pending)
    check("UNO 保留摸牌跳过", kept)
    check("UNO +2 罚摸跳过", d2)
    check("UNO 剩1张待喊", pending)
    check("UNO 补喊解除", called)


def test_uno_settlement():
    async def run():
        room = create_room("uno", room_id=3, name="UNO结算", owner="a",
                           buy_in=100, blind=5)
        room.add_member("a", 100)
        room.add_member("b", 100)

        async def broadcast_views():
            pass

        async def broadcast_payload(payload):
            pass

        async def on_rooms_changed():
            pass

        room.broadcast_views = broadcast_views
        room.broadcast_payload = broadcast_payload
        room.on_rooms_changed = on_rooms_changed
        await room.start()
        g = room.game
        order = g["order"]
        # a 一次性出完手牌获胜：b 剩 3 张按每张 5 赔付
        g["hands"]["a"] = [{"c": "r", "v": "3"}]
        g["hands"]["b"] = [{"c": "g", "v": "2"}, {"c": "g", "v": "7"},
                           {"c": "y", "v": "1"}]
        g["color"], g["value"] = "r", "9"
        g["idx"] = order.index("a")
        g["to_act"] = "a"
        await room.perform_action("a", "play", {"card": 0})
        stacks = (room.members["a"]["stack"], room.members["b"]["stack"])
        settled = (not room.in_hand() and room.status == "playing"
                   and "settle" in room.timers)
        # 结算投票：全员投「再来一局」后重新发牌
        await room.cast_vote("a", "next", 5)
        await room.cast_vote("b", "next", 5)
        redealt = room.in_hand() and all(
            len(h) == 7 for h in room.game["hands"].values())
        return stacks, settled, redealt

    stacks, settled, redealt = asyncio.run(run())
    check("UNO 出完即胜", stacks == (115.0, 85.0), str(stacks))
    check("UNO 胜后进入结算投票", settled)
    check("UNO 投票通过重发牌", redealt)


test_evaluate()
test_side_pots()
test_room_lifecycle()
test_registry()
test_uno_deck_and_matches()
test_uno_lifecycle()
test_uno_settlement()
failed = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
