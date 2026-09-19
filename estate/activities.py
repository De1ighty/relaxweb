"""小胖庄园工具、钓鱼和矿场领域规则。"""
import json
import random
import secrets

from estate.catalog import (
    BAITS, FISH, FISHING_TREASURES, MINERALS, MINING_LEVELS, TOOLS,
    bait_item, collectible_item, fish_item, mineral_item, xp_for_next,
)
from estate.service import (
    EstateError, _action, _change_inventory, _debit, _profile,
    _require_capacity,
)


def _tool(conn, username, tool_type):
    row = conn.execute(
        "SELECT level,durability FROM estate_tools WHERE username=? AND tool_type=?",
        (username, tool_type),
    ).fetchone()
    return {"level": row[0], "durability": row[1]} if row else None


def buy_tool(conn, username, request_id, tool_type, now, adjust_coins):
    tool_type = str(tool_type or "")

    def mutate():
        if tool_type not in TOOLS:
            raise EstateError("unknown_tool", "工具不存在")
        if _tool(conn, username, tool_type):
            raise EstateError("tool_owned", "已经拥有这件工具")
        profile = _profile(conn, username)
        rule = TOOLS[tool_type][1]
        if profile["level"] < rule["unlock_level"]:
            raise EstateError("level_locked", "庄园等级不足")
        balance = _debit(adjust_coins, conn, username, rule["price"],
                         f"小胖庄园购买：{rule['name']}", request_id)
        conn.execute(
            "INSERT INTO estate_tools(username,tool_type,level,durability,updated_at) "
            "VALUES (?,?,?,?,?)",
            (username, tool_type, 1, rule["max_durability"], int(now)),
        )
        return {"action": "buy_tool", "tool_type": tool_type, "level": 1,
                "durability": rule["max_durability"], "coins": balance}

    return _action(conn, username, request_id, "buy_tool", {"tool_type": tool_type}, now, mutate)


def upgrade_tool(conn, username, request_id, tool_type, now, adjust_coins):
    tool_type = str(tool_type or "")

    def mutate():
        current = _tool(conn, username, tool_type)
        if not current or tool_type not in TOOLS:
            raise EstateError("tool_missing", "请先购买工具")
        rule = TOOLS[tool_type].get(current["level"])
        next_level = current["level"] + 1
        target = TOOLS[tool_type].get(next_level)
        if not rule or not target or rule["upgrade_price"] is None:
            raise EstateError("max_level", "工具已达到最高等级")
        if _profile(conn, username)["level"] < target["unlock_level"]:
            raise EstateError("level_locked", "庄园等级不足")
        balance = _debit(adjust_coins, conn, username, rule["upgrade_price"],
                         f"小胖庄园升级：{target['name']}", request_id)
        conn.execute(
            "UPDATE estate_tools SET level=?,durability=?,updated_at=? "
            "WHERE username=? AND tool_type=?",
            (next_level, target["max_durability"], int(now), username, tool_type),
        )
        return {"action": "upgrade_tool", "tool_type": tool_type,
                "level": next_level, "durability": target["max_durability"],
                "coins": balance}

    return _action(conn, username, request_id, "upgrade_tool", {"tool_type": tool_type}, now, mutate)


def repair_tool(conn, username, request_id, tool_type, now, adjust_coins):
    tool_type = str(tool_type or "")

    def mutate():
        current = _tool(conn, username, tool_type)
        if not current or tool_type not in TOOLS:
            raise EstateError("tool_missing", "请先购买工具")
        rule = TOOLS[tool_type][current["level"]]
        if current["durability"] >= rule["max_durability"]:
            raise EstateError("repair_unneeded", "工具耐久已满")
        missing = rule["max_durability"] - current["durability"]
        cost = max(1.0, round(rule["repair_price"] * missing / rule["max_durability"], 2))
        balance = _debit(adjust_coins, conn, username, cost,
                         f"小胖庄园修理：{rule['name']}", request_id)
        conn.execute(
            "UPDATE estate_tools SET durability=?,updated_at=? "
            "WHERE username=? AND tool_type=?",
            (rule["max_durability"], int(now), username, tool_type),
        )
        return {"action": "repair_tool", "tool_type": tool_type,
                "durability": rule["max_durability"], "cost": cost, "coins": balance}

    return _action(conn, username, request_id, "repair_tool", {"tool_type": tool_type}, now, mutate)


def _active(conn, table, username):
    return conn.execute(
        f"SELECT 1 FROM {table} WHERE username=? AND status='active' LIMIT 1",
        (username,),
    ).fetchone()


def _award_xp(conn, username, amount):
    profile = _profile(conn, username)
    level, xp = profile["level"], profile["xp"] + int(amount)
    while xp >= xp_for_next(level):
        xp -= xp_for_next(level)
        level += 1
    conn.execute("UPDATE estate_profiles SET level=?,xp=? WHERE username=?",
                 (level, xp, username))
    return level


def _pick_fishing_catch(rng, bait, rod):
    """从服务端目录选择鱼或极稀有收藏物。"""
    rarity_cap = 2 + bait["rarity_bonus"] + rod["level"]
    treasure_rarity_cap = 4 + bait["rarity_bonus"] + rod["level"]
    treasures = [
        (key, value) for key, value in FISHING_TREASURES.items()
        if value["required_rod_level"] <= rod["level"]
        and value["rarity"] <= treasure_rarity_cap
    ]
    treasure_chance = .006 + bait["rarity_bonus"] * .012 + max(0, rod["level"] - 1) * .009
    if treasures and rng.random() < treasure_chance:
        treasure_id = rng.choices(
            [key for key, _ in treasures],
            weights=[value["weight"] for _, value in treasures], k=1,
        )[0]
        return f"treasure:{treasure_id}", FISHING_TREASURES[treasure_id]
    allowed = [key for key, value in FISH.items() if value["rarity"] <= rarity_cap]
    weights = [max(.35, 9 - FISH[key]["rarity"] * 1.45) for key in allowed]
    fish_id = rng.choices(allowed, weights=weights, k=1)[0]
    return fish_id, FISH[fish_id]


def start_fishing(conn, username, request_id, bait_id, now):
    bait_id = str(bait_id or "")

    def mutate():
        profile = _profile(conn, username)
        rod = _tool(conn, username, "rod")
        bait = BAITS.get(bait_id)
        if not rod:
            raise EstateError("tool_missing", "请先购买鱼竿")
        if rod["durability"] < 1:
            raise EstateError("tool_broken", "鱼竿需要修理")
        if not bait:
            raise EstateError("unknown_item", "鱼饵不存在")
        if _active(conn, "estate_fishing_sessions", username):
            raise EstateError("session_active", "已有一局钓鱼正在进行")
        _require_capacity(conn, username, profile, 1)
        _change_inventory(conn, username, bait_item(bait_id), -1)
        conn.execute("UPDATE estate_tools SET durability=durability-1,updated_at=? "
                     "WHERE username=? AND tool_type='rod'", (int(now), username))
        seed = secrets.randbelow(2_000_000_000)
        rng = random.Random(seed)
        fish_id, catch = _pick_fishing_catch(rng, bait, rod)
        difficulty = catch["difficulty"]
        pattern = [round(min(.95, max(.08, rng.random() * .55 + difficulty * .45)), 3)
                   for _ in range(36)]
        session_id = secrets.token_urlsafe(12)
        conn.execute(
            "INSERT INTO estate_fishing_sessions"
            "(session_id,username,bait_id,rod_level,fish_id,seed,pattern_json,started_at,expires_at) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (session_id, username, bait_id, rod["level"], fish_id, seed,
             json.dumps(pattern), int(now), int(now) + 90),
        )
        conn.execute("UPDATE estate_profiles SET reserved_capacity=reserved_capacity+1 "
                     "WHERE username=?", (username,))
        return {"action": "start_fishing", "session_id": session_id,
                "fish_name": "水下的鱼影", "pattern": pattern,
                "difficulty": difficulty, "duration_limit": 36,
                "rod_level": rod["level"]}

    return _action(conn, username, request_id, "start_fishing", {"bait_id": bait_id}, now, mutate)


def simulate_fishing(trace, pattern, rod_level):
    if not isinstance(trace, list) or not 20 <= len(trace) <= 400:
        raise EstateError("invalid_trace", "钓鱼操作记录无效")
    if any(type(value) is not bool for value in trace):
        raise EstateError("invalid_trace", "钓鱼操作记录无效")
    tension, progress = .18, .08
    factor = TOOLS["rod"][rod_level]["tension_factor"]
    peak = tension
    for index, held in enumerate(trace):
        force = pattern[min(len(pattern) - 1, index // 10)]
        if held:
            tension += .026 * (.68 + force) * factor
            progress += .013 * (1.12 - force * .3)
        else:
            tension -= .045
            progress -= .0035 * (.5 + force)
        tension = max(0, tension)
        progress = max(0, progress)
        peak = max(peak, tension)
        if tension >= 1:
            return {"outcome": "snapped", "progress": progress, "peak_tension": peak}
        if progress >= 1:
            return {"outcome": "caught", "progress": 1, "peak_tension": peak}
    return {"outcome": "escaped", "progress": progress, "peak_tension": peak}


def finish_fishing(conn, username, request_id, session_id, trace, now):
    session_id = str(session_id or "")

    def mutate():
        row = conn.execute(
            "SELECT fish_id,rod_level,pattern_json,expires_at,status,result_json "
            "FROM estate_fishing_sessions WHERE session_id=? AND username=?",
            (session_id, username),
        ).fetchone()
        if not row:
            raise EstateError("session_missing", "钓鱼会话不存在")
        if row[4] != "active":
            return {**json.loads(row[5]), "session_replayed": True}
        result = ({"outcome": "expired", "progress": 0, "peak_tension": 0}
                  if int(now) > row[3] else simulate_fishing(trace, json.loads(row[2]), row[1]))
        payload = {**result, "action": "finish_fishing", "session_id": session_id}
        if result["outcome"] == "caught":
            if row[0].startswith("treasure:"):
                catch_id = row[0].split(":", 1)[1]
                catch = FISHING_TREASURES[catch_id]
                item_id = collectible_item(catch_id)
                payload.update({"catch_kind": "collectible", "collectible_id": catch_id})
            else:
                catch_id = row[0]
                catch = FISH[catch_id]
                item_id = fish_item(catch_id)
                payload.update({"catch_kind": "fish", "fish_id": catch_id})
            _change_inventory(conn, username, item_id, 1)
            payload.update({"fish_name": catch["name"], "catch_name": catch["name"],
                            "quantity": 1, "xp_awarded": catch["xp"]})
            payload["level"] = _award_xp(conn, username, catch["xp"])
        conn.execute("UPDATE estate_profiles SET reserved_capacity=max(0,reserved_capacity-1) "
                     "WHERE username=?", (username,))
        conn.execute("UPDATE estate_fishing_sessions SET status='finished',result_json=? "
                     "WHERE session_id=?", (json.dumps(payload, ensure_ascii=False), session_id))
        return payload

    return _action(conn, username, request_id, "finish_fishing",
                   {"session_id": session_id, "trace": trace}, now, mutate)


def _make_board(seed, mine_level):
    rng = random.Random(seed)
    minerals = list(MINERALS)
    rule = MINING_LEVELS[mine_level]
    weights = rule["weights"]
    board = rng.choices(["empty", *minerals], weights=[24, *weights], k=25)
    extra_cells = rng.sample(range(25), 2)
    for index in extra_cells:
        board[index] = "extra"
    bomb_cells = rng.sample([index for index in range(25) if index not in extra_cells],
                            rule["bombs"])
    for index in bomb_cells:
        board[index] = "bomb"
    return board


def start_mining(conn, username, request_id, mine_level, now):
    try:
        mine_level = int(mine_level)
    except (TypeError, ValueError):
        raise EstateError("invalid_mine", "矿层无效") from None

    def mutate():
        profile = _profile(conn, username)
        pickaxe = _tool(conn, username, "pickaxe")
        rule = MINING_LEVELS.get(mine_level)
        if not pickaxe:
            raise EstateError("tool_missing", "请先购买矿镐")
        if pickaxe["durability"] < 1:
            raise EstateError("tool_broken", "矿镐需要修理")
        if not rule or profile["level"] < rule["unlock_level"] or pickaxe["level"] < mine_level:
            raise EstateError("level_locked", "该矿层尚未解锁")
        if _active(conn, "estate_mining_runs", username):
            raise EstateError("session_active", "已有一次挖矿正在进行")
        _require_capacity(conn, username, profile, 12)
        seed = secrets.randbelow(2_000_000_000)
        board = _make_board(seed, mine_level)
        run_id = secrets.token_urlsafe(12)
        strikes = TOOLS["pickaxe"][pickaxe["level"]]["strikes"]
        conn.execute("UPDATE estate_tools SET durability=durability-1,updated_at=? "
                     "WHERE username=? AND tool_type='pickaxe'", (int(now), username))
        conn.execute("UPDATE estate_profiles SET reserved_capacity=reserved_capacity+12 "
                     "WHERE username=?", (username,))
        conn.execute(
            "INSERT INTO estate_mining_runs"
            "(run_id,username,mine_level,pickaxe_level,seed,board_json,strikes_left,started_at) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (run_id, username, mine_level, pickaxe["level"], seed,
             json.dumps(board), strikes, int(now)),
        )
        return {"action": "start_mining", "run_id": run_id,
                "mine_level": mine_level, "mine_name": rule["name"],
                "strikes_left": strikes, "size": 5, "revealed": [], "loot": {}}

    return _action(conn, username, request_id, "start_mining",
                   {"mine_level": mine_level}, now, mutate)


def _finish_run(conn, username, run_id, loot, reason="completed"):
    for mineral_id, quantity in loot.items():
        _change_inventory(conn, username, mineral_item(mineral_id), quantity)
    conn.execute("UPDATE estate_profiles SET reserved_capacity=max(0,reserved_capacity-12) "
                 "WHERE username=?", (username,))
    result = {"action": "finish_mining", "run_id": run_id, "loot": loot,
              "finished": True, "reason": reason}
    conn.execute("UPDATE estate_mining_runs SET status='finished',result_json=? WHERE run_id=?",
                 (json.dumps(result, ensure_ascii=False), run_id))
    return result


def mine_cell(conn, username, request_id, run_id, cell, now):
    run_id = str(run_id or "")
    if isinstance(cell, bool):
        raise EstateError("invalid_cell", "矿格无效")
    try:
        cell = int(cell)
    except (TypeError, ValueError):
        raise EstateError("invalid_cell", "矿格无效") from None
    if not 0 <= cell < 25:
        raise EstateError("invalid_cell", "矿格无效")

    def mutate():
        row = conn.execute(
            "SELECT board_json,revealed_json,loot_json,strikes_left,status "
            "FROM estate_mining_runs WHERE run_id=? AND username=?",
            (run_id, username),
        ).fetchone()
        if not row:
            raise EstateError("run_missing", "矿场记录不存在")
        if row[4] != "active":
            raise EstateError("run_finished", "本次挖矿已经结束")
        board, revealed, loot = json.loads(row[0]), json.loads(row[1]), json.loads(row[2])
        if cell in revealed:
            raise EstateError("cell_revealed", "这个矿格已经敲过")
        revealed.append(cell)
        outcome = board[cell]
        strikes = row[3] - 1
        exploded = outcome == "bomb"
        if exploded:
            strikes = 0
        elif outcome == "extra":
            strikes += 2
        elif outcome in MINERALS:
            loot[outcome] = loot.get(outcome, 0) + 1
        conn.execute(
            "UPDATE estate_mining_runs SET revealed_json=?,loot_json=?,strikes_left=? WHERE run_id=?",
            (json.dumps(revealed), json.dumps(loot), strikes, run_id),
        )
        payload = {"action": "mine_cell", "run_id": run_id, "cell": cell,
                   "outcome": outcome, "strikes_left": strikes, "loot": loot,
                   "revealed": revealed, "finished": exploded or strikes <= 0,
                   "exploded": exploded}
        if payload["finished"]:
            payload["result"] = _finish_run(
                conn, username, run_id, loot, "bomb" if exploded else "exhausted")
        return payload

    return _action(conn, username, request_id, "mine_cell",
                   {"run_id": run_id, "cell": cell}, now, mutate)


def finish_mining(conn, username, request_id, run_id, now):
    run_id = str(run_id or "")

    def mutate():
        row = conn.execute(
            "SELECT loot_json,status,result_json FROM estate_mining_runs "
            "WHERE run_id=? AND username=?", (run_id, username),
        ).fetchone()
        if not row:
            raise EstateError("run_missing", "矿场记录不存在")
        if row[1] != "active":
            return {**json.loads(row[2]), "session_replayed": True}
        return _finish_run(conn, username, run_id, json.loads(row[0]), "left")

    return _action(conn, username, request_id, "finish_mining", {"run_id": run_id}, now, mutate)
