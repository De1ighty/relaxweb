#!/usr/bin/env python3
"""掼蛋引擎单元测试：python3 tests/test_guandan.py

只测纯逻辑（不发网络请求）：
  - 牌堆构成、级牌大小序（games/guandan.py 纯函数）
  - 牌型解析（含逢人配）与压制关系
  - 一手牌流程：出牌/过/自由出牌/双上结算/投票重发
  - 打 A 规则、离桌作废
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from games.base import ROOM_TYPES, create_room  # noqa: E402
from games.guandan import (  # noqa: E402
    build_deck, beats, find_moves, resolve_combo, rank_value,
)

results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(f"{'PASS' if ok else 'FAIL'}  {name}  {detail}")


def card(rank, suit=0):
    return {"r": rank, "s": suit}


def joker(small=True):
    return {"r": 16 if small else 17, "s": 4}


def combo(cards, wild=None, levels=frozenset({2})):
    return resolve_combo(cards, wild, set(levels))


def test_deck():
    deck = build_deck()
    check("掼蛋牌堆108张", len(deck) == 108)
    ranks = {}
    for c in deck:
        ranks[c["r"]] = ranks.get(c["r"], 0) + 1
    check("2~A 每点数8张", all(ranks.get(r) == 8 for r in range(2, 15)), str(ranks))
    check("大小王各2张", ranks.get(16) == 2 and ranks.get(17) == 2)


def test_rank_value():
    levels = {5, 8}
    order = [rank_value(2, levels), rank_value(14, levels), rank_value(5, levels),
             rank_value(8, levels), rank_value(16, levels), rank_value(17, levels)]
    check("2<A<级牌5<级牌8<小王<大王", order == sorted(order), str(order))


def test_resolve():
    check("单张", combo([card(7)])["type"] == "single")
    check("对子（两副牌取两张）", combo([card(7, 0), card(7, 1)])["type"] == "pair")
    check("三张", combo([card(7, 0), card(7, 1), card(7, 2)])["type"] == "triple")
    tp = combo([card(7, 0), card(7, 1), card(7, 2), card(9, 0), card(9, 1)])
    check("三带二", tp["type"] == "triple_pair" and tp["main"] == rank_value(7, {2}))
    # 混花色才是普通顺子；同花 34567 是更大的同花顺
    check("最小顺子34567",
          combo([card(3, 0), card(4, 1), card(5, 2), card(6, 0), card(7, 1)])["type"] == "straight")
    check("同花34567是同花顺",
          combo([card(3), card(4), card(5), card(6), card(7)])["type"] == "flush_straight")
    check("最大顺子10JQKA",
          combo([card(10, 0), card(11, 1), card(12, 2), card(13, 0), card(14, 1)])["type"] == "straight")
    check("2不能入顺", combo([card(2), card(3), card(4), card(5), card(6)]) is None)
    check("A2开头不算顺", combo([card(12), card(13), card(14), card(2), card(3)]) is None)
    ps = combo([card(3, 0), card(3, 1), card(4, 0), card(4, 1), card(5, 0), card(5, 1)])
    check("三连对", ps["type"] == "pairs_seq" and ps["len"] == 6)
    check("两连对不算连对",
          combo([card(3, 0), card(3, 1), card(4, 0), card(4, 1)]) is None)
    ts = combo([card(3, 0), card(3, 1), card(3, 2), card(4, 0), card(4, 1), card(4, 2)])
    check("钢板", ts["type"] == "triple_seq")
    b = combo([card(9, s) for s in range(4)])
    check("四张炸弹", b["type"] == "bomb" and b["tier"] == 4)
    b8 = combo([card(9, s) for s in range(4)] + [card(9, 0), card(9, 1), card(9, 2), card(9, 3)])
    check("八张炸弹", b8["type"] == "bomb" and b8["tier"] == 8)
    kb = combo([joker(True), joker(True), joker(False), joker(False)])
    check("天王炸", kb["type"] == "king_bomb")
    fs = combo([card(5, 1), card(6, 1), card(7, 1), card(8, 1), card(9, 1)])
    check("同花顺", fs["type"] == "flush_straight")
    check("不同花不是同花顺",
          combo([card(5, 1), card(6, 1), card(7, 1), card(8, 1), card(9, 2)])["type"] == "straight")
    # 五张同点：最强解释是炸弹而不是三带二
    five = combo([card(9, 0), card(9, 1), card(9, 2), card(9, 3), card(9, 0)])
    check("五张同点解析为炸弹", five["type"] == "bomb")


def test_wild():
    levels = {8}
    # 红桃级牌当 7 补顺
    c = combo([card(8, 1), card(3, 0), card(4, 1), card(5, 2), card(6, 0)],
              wild=8, levels=levels)
    check("逢人配补顺", c is not None and c["type"] == "straight")
    # 当 8 本身补顺（6789T）
    c = combo([card(8, 1), card(6, 0), card(7, 1), card(9, 2), card(10, 0)],
              wild=8, levels=levels)
    check("逢人配按本级补顺", c is not None and c["type"] == "straight")
    # 配成同花顺
    c = combo([card(8, 1), card(3), card(4), card(5), card(6)], wild=8, levels=levels)
    check("逢人配补同花顺", c is not None and c["type"] == "flush_straight")
    # 不能配炸弹
    c = combo([card(8, 1), card(9, 0), card(9, 1), card(9, 2)], wild=8, levels=levels)
    check("逢人配不能配炸弹", c is None)
    # 不能配王
    c = combo([card(8, 1), joker(True)], wild=8, levels=levels)
    check("逢人配不能配王", c is None)
    # 单出按级牌（大于A）
    c = combo([card(8, 1)], wild=8, levels=levels)
    check("逢人配单出=级牌", c["main"] == (2, 8))
    # 关闭规则时红桃级牌是普通牌
    c = combo([card(8, 1), card(9, 0), card(9, 1), card(9, 2)], wild=None, levels=levels)
    check("关闭逢人配则不可代", c is None)
    c = combo([card(8, 1)], wild=None, levels=levels)
    check("关闭时红桃8单出", c is not None and c["type"] == "single")


def test_beats():
    s9 = {"type": "straight", "tier": 0, "main": (1, 9), "len": 5}
    s10 = {"type": "straight", "tier": 0, "main": (1, 10), "len": 5}
    s9b = {"type": "straight", "tier": 0, "main": (1, 9), "len": 5}
    p = {"type": "pair", "tier": 0, "main": (2, 8), "len": 2}
    b4 = {"type": "bomb", "tier": 4, "main": (1, 3), "len": 4}
    b5 = {"type": "bomb", "tier": 5, "main": (1, 3), "len": 5}
    b6 = {"type": "bomb", "tier": 6, "main": (1, 3), "len": 6}
    fs = {"type": "flush_straight", "tier": 5.5, "main": (1, 9), "len": 5}
    kb = {"type": "king_bomb", "tier": 99, "main": (4, 0), "len": 4}
    check("顺子压同长顺子", beats(s10, s9))
    check("等大牌不能压", not beats(s9b, s9))
    check("顺子不能压对子", not beats(s10, p))
    check("级牌对子压顺子？不能", not beats(p, s10))
    check("炸弹压顺子", beats(b4, s10))
    check("4炸不能压5炸", not beats(b4, b5))
    check("同花顺压五炸", beats(fs, b5))
    check("五炸不能压同花顺", not beats(b5, fs))
    check("六炸压同花顺", beats(b6, fs))
    check("天王炸压一切", beats(kb, b6) and beats(kb, fs))


def test_find_moves():
    levels = {2}
    hand = [card(3), card(3, 1), card(7), card(9), card(14)]
    free = find_moves(hand, None, levels, None)
    check("自由出牌含最小单张", free[0]["type"] == "single"
          and free[0]["cards"][0]["r"] == 3)
    check("自由出牌含对子", any(m["type"] == "pair" for m in free))
    standing = {"type": "single", "tier": 0, "main": (1, 8), "len": 1}
    follow = find_moves(hand, None, levels, standing)
    check("跟牌只给压得过的", follow and all(beats(m, standing) for m in follow)
          and [m["cards"][0]["r"] for m in follow] == [9, 14])
    bomb_standing = {"type": "bomb", "tier": 4, "main": (1, 3), "len": 4}
    check("炸弹压顶时无解", find_moves(hand, None, levels, bomb_standing) == [])


def make_room(rules=None):
    room = create_room("guandan", room_id=99, name="掼蛋测试", owner="a",
                       buy_in=100, blind=5, rules=rules or {})
    for name in ("a", "b", "c", "d"):
        room.add_member(name, 100)

    async def noop(*_args, **_kwargs):
        return None

    room.broadcast_views = noop
    room.broadcast_payload = noop
    room.on_rooms_changed = noop
    return room


def index_of(hand, target):
    for i, c in enumerate(hand):
        if c == target:
            return i
    raise AssertionError(f"{target} 不在手牌里")


def test_lifecycle():
    async def run():
        room = make_room()
        await room.start()
        g = room.game
        dealt = room.in_hand() and all(len(h) == 27 for h in g["hands"].values())
        teams_ok = (g["teams"]["a"] == g["teams"]["c"] == 0
                    and g["teams"]["b"] == g["teams"]["d"] == 1)
        leader_ok = g["to_act"] == "a" and g["free_lead"]

        # 换成已知牌：a 两张 8，b 3/4，c 5，d 3/4（都压不过单张 8）
        g["hands"]["a"] = [card(8), card(8, 1)]
        g["hands"]["b"] = [card(3), card(4)]
        g["hands"]["c"] = [card(5)]
        g["hands"]["d"] = [card(3, 1), card(4, 1)]
        await room.perform_action("a", "play", {"cards": [0]})
        played = g["standing"]["label"].startswith("单张") and g["to_act"] == "b"
        # 跟牌阶段 b/c/d 全过 → 出牌者 a 自由出牌
        await room.perform_action("b", "pass", {})
        await room.perform_action("c", "pass", {})
        await room.perform_action("d", "pass", {})
        free_again = g["free_lead"] and g["to_act"] == "a"
        # a 出完 → 头游；standing 仍是单张 8，其余全过后轮到 b 自由出
        await room.perform_action("a", "play", {"cards": [0]})
        head = g["finish"] == ["a"]
        await room.perform_action("b", "pass", {})
        await room.perform_action("c", "pass", {})
        await room.perform_action("d", "pass", {})
        lead_after_head = g["free_lead"] and g["to_act"] == "b"
        # b 引 3，c 用 5 一压即出完 → 二游与 a 同队 = 双上
        await room.perform_action("b", "play", {"cards": [0]})
        await room.perform_action("c", "play", {"cards": [0]})
        result = g["result"]
        settled = not room.in_hand() and g["stage"] == "showdown"
        return room, dealt, teams_ok, leader_ok, played, free_again, head, \
            lead_after_head, settled, result

    (room, dealt, teams_ok, leader_ok, played, free_again, head,
     lead_after_head, settled, result) = asyncio.run(run())
    check("开局每人27张", dealt)
    check("座位间隔分队", teams_ok)
    check("首局房主先出", leader_ok)
    check("出牌后轮下家", played)
    check("全过回到出牌者自由出", free_again)
    check("先出完即头游", head)
    check("头游后由未完者自由出", lead_after_head)
    check("双上后进入结算", settled)
    check("名次 a头游c二游", result["finish"] == ["a", "c", "b", "d"],
          str(result["finish"]))
    check("双上升3级", result["gain"] == 3
          and result["levels_after"][0] == 5, str(result["levels_after"]))
    # 输家各付 5×1×2=10，赢家平分
    check("输家各付10", result["payouts"] == {"b": 10, "d": 10}, str(result["payouts"]))
    check("赢家平分", result["gains"] == {"a": 10, "c": 10}, str(result["gains"]))
    check("筹码更新", room.members["b"]["stack"] == 90
          and room.members["a"]["stack"] == 110)
    check("结算载荷带段位明细", "ratings" in result)

    async def vote():
        for name in ("a", "b", "c", "d"):
            await room.cast_vote(name, "next", 5)
        return room.in_hand() and all(len(h) == 27 for h in room.game["hands"].values())

    check("投票通过重发牌且级数保留", asyncio.run(vote())
          and room.levels[0] == 5)


def test_ace_rules():
    async def double_head(room):
        """a 打两轮单 8 当头游，b 引 3，d 5 一压当二游，b 再引 4 当三游。"""
        g = room.game
        g["hands"]["a"] = [card(8), card(8, 1)]
        g["hands"]["b"] = [card(3), card(4)]
        g["hands"]["c"] = [card(3, 1)]
        g["hands"]["d"] = [card(5)]
        await room.perform_action("a", "play", {"cards": [0]})
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("a", "play", {"cards": [0]})     # a 头游
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})            # 自由出到 b
        await room.perform_action("b", "play", {"cards": [0]})     # b 引 3
        await room.perform_action("c", "pass", {})
        await room.perform_action("d", "play", {"cards": [0]})     # d 5 → 二游
        await room.perform_action("b", "pass", {})
        await room.perform_action("c", "pass", {})
        await room.perform_action("b", "play", {"cards": [0]})     # b 三游
        return room.game["result"]

    async def run_strict():
        room = make_room({"ace_strict": True})
        await room.start()
        room.levels = {0: 14, 1: 5}
        return await double_head(room), room

    async def run_strict_gain3():
        room = make_room({"ace_strict": True})
        await room.start()
        room.levels = {0: 14, 1: 5}
        g = room.game
        g["hands"]["a"] = [card(8), card(8, 1)]
        g["hands"]["b"] = [card(3), card(4)]
        g["hands"]["c"] = [card(5)]
        g["hands"]["d"] = [card(3, 1)]
        await room.perform_action("a", "play", {"cards": [0]})
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("a", "play", {"cards": [0]})
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("b", "play", {"cards": [0]})
        await room.perform_action("c", "play", {"cards": [0]})     # c 二游 = 双上
        return room.game["result"], room

    result, room = asyncio.run(run_strict())
    check("严格打A：升1级不过A", result["match_win"] is None
          and result["gain"] == 1 and result["levels_after"][0] == 14
          and room.match_winner is None, str(result["levels_after"]))
    check("升1级输家各付底注", result["payouts"] == {"b": 5, "d": 5},
          str(result["payouts"]))
    result3, room3 = asyncio.run(run_strict_gain3())
    check("严格打A：双上过A", result3["match_win"] == 0
          and room3.match_winner == 0 and result3["levels_after"][0] == 14)

    async def run_loose():
        """a 头游、d 二游、c 三游（升 2 级）验证宽松过 A。"""
        room = make_room({"ace_strict": False})
        await room.start()
        room.levels = {0: 14, 1: 5}
        g = room.game
        g["hands"]["a"] = [card(8), card(8, 1)]
        g["hands"]["b"] = [card(3), card(4)]
        g["hands"]["c"] = [card(6)]
        g["hands"]["d"] = [card(4, 1)]
        await room.perform_action("a", "play", {"cards": [0]})
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("a", "play", {"cards": [0]})     # a 头游
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("b", "play", {"cards": [0]})     # b 引 3
        await room.perform_action("c", "pass", {})
        await room.perform_action("d", "play", {"cards": [0]})     # d 4 → 二游
        await room.perform_action("b", "pass", {})
        await room.perform_action("c", "play", {"cards": [0]})     # c 6 压 4 → 三游
        return room.game["result"], room

    result4, room4 = asyncio.run(run_loose())
    check("宽松打A：非末游即过A", result4["match_win"] == 0
          and result4["gain"] == 2 and room4.match_winner == 0,
          str(result4["levels_after"]))


def test_abort_and_rules():
    async def run():
        room = make_room({"wild": False, "bomb_cap": 4})
        check("规则清洗生效", room.rules == {"wild": False, "bomb_cap": 4, "ace_strict": True})
        await room.start()
        g = room.game
        # 两个炸弹：倍率 2²=4 封顶 4；双上 ×2 → 输家各付 5×4×2=40
        g["bombs"] = 2
        g["hands"]["a"] = [card(8), card(8, 1)]
        g["hands"]["b"] = [card(3), card(4)]
        g["hands"]["c"] = [card(5)]
        g["hands"]["d"] = [card(3, 1), card(4, 1)]
        await room.perform_action("a", "play", {"cards": [0]})
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("a", "play", {"cards": [0]})
        for name in ("b", "c", "d"):
            await room.perform_action(name, "pass", {})
        await room.perform_action("b", "play", {"cards": [0]})
        await room.perform_action("c", "play", {"cards": [0]})
        result = room.game["result"]
        doubled_ok = (result["multiplier"] == 4
                      and result["payouts"] == {"b": 40, "d": 40})
        # 投票再来一局后，在手牌进行中离桌 → 本手作废、筹码不动
        for name in ("a", "b", "c", "d"):
            await room.cast_vote(name, "next", 5)
        g = room.game
        g["hands"]["a"] = [card(8), card(8, 1)]
        g["hands"]["b"] = [card(3), card(4)]
        g["hands"]["c"] = [card(5)]
        g["hands"]["d"] = [card(3, 1), card(4, 1)]
        await room.perform_action("a", "play", {"cards": [0]})
        mid_hand = room.in_hand()
        stacks_before = {n: m["stack"] for n, m in room.members.items()}
        room.remove_member("b")
        await room.progress_game()
        aborted = (mid_hand and not room.in_hand()
                   and room.game["result"]["aborted"]
                   and not room.game["result"]["payouts"])
        stacks_same = all(room.members[n]["stack"] == s
                          for n, s in stacks_before.items() if n != "b")
        # 只剩 3 人时不能开局
        try:
            await room.start()
            restart_blocked = False
        except ValueError:
            restart_blocked = True
        return doubled_ok, aborted, stacks_same, restart_blocked, room

    doubled_ok, aborted, stacks_same, restart_blocked, room = asyncio.run(run())
    check("炸弹翻倍封顶生效", doubled_ok, "")
    check("离桌本手作废", aborted)
    check("作废不动筹码", stacks_same)
    check("人数不足不能开局", restart_blocked)


def test_registry():
    check("注册表包含guandan", "guandan" in ROOM_TYPES)
    check("guandan房间4人上限", create_room("guandan", room_id=1, name="x", owner="a",
                                           buy_in=100, blind=5).max_seats == 4)


test_deck()
test_rank_value()
test_resolve()
test_wild()
test_beats()
test_find_moves()
test_lifecycle()
test_ace_rules()
test_abort_and_rules()
test_registry()
failed = [name for name, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} passed")
sys.exit(1 if failed else 0)
