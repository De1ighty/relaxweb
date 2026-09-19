"""小胖庄园领域服务。

所有函数只依赖一个已打开的 SQLite 连接；WebSocket、全局数据库路径和
在线连接管理留给宿主。调用方负责用连接上下文开启/提交事务。
"""
import hashlib
import json

from estate.catalog import (
    BAITS, CROPS, INITIAL_PLOTS, LAND_LEVELS, MAX_PLOTS, PLOT_UNLOCKS, TOOLS,
    WAREHOUSE_LEVELS, crop_item, grow_seconds, item_info, public_catalog,
    bait_item, seed_item, xp_for_next,
)


class EstateError(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def _positive_int(value, code="invalid_quantity", message="数量无效", maximum=9999):
    if isinstance(value, bool):
        raise EstateError(code, message)
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise EstateError(code, message) from None
    if number <= 0 or number > maximum or str(value).strip() not in (str(number), f"{number}.0"):
        raise EstateError(code, message)
    return number


def _plot_index(value):
    if isinstance(value, bool):
        raise EstateError("invalid_plot", "土地编号无效")
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise EstateError("invalid_plot", "土地编号无效") from None
    if number < 0 or number >= MAX_PLOTS:
        raise EstateError("invalid_plot", "土地编号无效")
    return number


def ensure_estate(conn, username, now):
    now = int(now)
    conn.execute(
        "INSERT OR IGNORE INTO estate_profiles"
        "(username,level,xp,warehouse_level,plot_count,version,created_at,updated_at) "
        "VALUES (?,1,0,1,?,1,?,?)",
        (username, INITIAL_PLOTS, now, now),
    )
    conn.executemany(
        "INSERT OR IGNORE INTO estate_plots(username,plot_index,land_level) "
        "VALUES (?,?,1)",
        ((username, index) for index in range(MAX_PLOTS)),
    )


def _profile(conn, username):
    row = conn.execute(
        "SELECT level,xp,warehouse_level,plot_count,reserved_capacity,version,created_at,updated_at "
        "FROM estate_profiles WHERE username = ?", (username,),
    ).fetchone()
    if not row:
        raise EstateError("estate_missing", "庄园存档不存在")
    return {
        "level": row[0], "xp": row[1], "warehouse_level": row[2],
        "plot_count": row[3], "reserved_capacity": row[4], "version": row[5],
        "created_at": row[6], "updated_at": row[7],
    }


def _inventory_rows(conn, username):
    return conn.execute(
        "SELECT item_id,quantity FROM estate_inventory "
        "WHERE username = ? ORDER BY item_id", (username,),
    ).fetchall()


def _inventory_used(conn, username):
    row = conn.execute(
        "SELECT COALESCE(SUM(quantity),0) FROM estate_inventory WHERE username = ?",
        (username,),
    ).fetchone()
    return int(row[0] or 0)


def _capacity(profile):
    try:
        return WAREHOUSE_LEVELS[profile["warehouse_level"]]["capacity"]
    except KeyError:
        raise EstateError("invalid_save", "仓库等级数据异常") from None


def estate_state(conn, username, now):
    now = int(now)
    ensure_estate(conn, username, now)
    expired = conn.execute(
        "SELECT COUNT(*) FROM estate_fishing_sessions "
        "WHERE username=? AND status='active' AND expires_at<?", (username, now),
    ).fetchone()[0]
    if expired:
        expired_result = json.dumps({"action": "finish_fishing", "outcome": "expired",
                                     "progress": 0, "peak_tension": 0},
                                    ensure_ascii=False)
        conn.execute(
            "UPDATE estate_fishing_sessions SET status='finished',result_json=? "
            "WHERE username=? AND status='active' AND expires_at<?",
            (expired_result, username, now),
        )
        conn.execute(
            "UPDATE estate_profiles SET reserved_capacity=max(0,reserved_capacity-?) "
            "WHERE username=?", (expired, username),
        )
    profile = _profile(conn, username)
    used = _inventory_used(conn, username)
    balance = conn.execute(
        "SELECT coins FROM users WHERE username = ?", (username,)
    ).fetchone()
    if not balance:
        raise EstateError("user_missing", "账号不存在")

    plots = []
    for index, land_level, crop_id, planted_at, ready_at in conn.execute(
        "SELECT plot_index,land_level,crop_id,planted_at,ready_at "
        "FROM estate_plots WHERE username = ? ORDER BY plot_index", (username,),
    ):
        locked = index >= profile["plot_count"]
        remaining = max(0, int(ready_at - now)) if ready_at is not None else None
        plots.append({
            "index": index,
            "locked": locked,
            "land_level": land_level,
            "crop_id": crop_id,
            "planted_at": planted_at,
            "ready_at": ready_at,
            "remaining_seconds": remaining,
            "mature": bool(crop_id is not None and ready_at <= now),
        })

    inventory = []
    for item_id, quantity in _inventory_rows(conn, username):
        info = item_info(item_id) or {"id": item_id, "name": item_id, "kind": "unknown",
                                      "sellable": False, "sell_price": None}
        inventory.append({**info, "quantity": quantity})

    tools = {}
    for tool_type, level, durability in conn.execute(
        "SELECT tool_type,level,durability FROM estate_tools WHERE username=?",
        (username,),
    ):
        rule = TOOLS.get(tool_type, {}).get(level, {})
        tools[tool_type] = {"type": tool_type, "level": level,
                            "durability": durability,
                            "max_durability": rule.get("max_durability", durability),
                            "name": rule.get("name", tool_type)}

    fishing_session = None
    row = conn.execute(
        "SELECT session_id,bait_id,rod_level,fish_id,pattern_json,started_at,expires_at "
        "FROM estate_fishing_sessions WHERE username=? AND status='active' "
        "ORDER BY started_at DESC LIMIT 1", (username,),
    ).fetchone()
    if row:
        fishing_session = {"session_id": row[0], "bait_id": row[1], "rod_level": row[2],
                           "fish_name": "水下的鱼影", "pattern": json.loads(row[4]),
                           "started_at": row[5], "expires_at": row[6],
                           "duration_limit": 36}
    mining_run = None
    row = conn.execute(
        "SELECT run_id,mine_level,strikes_left,revealed_json,loot_json,board_json "
        "FROM estate_mining_runs WHERE username=? AND status='active' "
        "ORDER BY started_at DESC LIMIT 1", (username,),
    ).fetchone()
    if row:
        revealed = json.loads(row[3])
        board = json.loads(row[5])
        mining_run = {"run_id": row[0], "mine_level": row[1],
                      "mine_name": public_catalog()["mining_levels"][row[1]]["name"],
                      "strikes_left": row[2], "revealed": revealed,
                      "revealed_cells": {str(index): board[index] for index in revealed},
                      "loot": json.loads(row[4]), "size": 5}

    return {
        "version": profile["version"],
        "server_time": now,
        "coins": round(float(balance[0] or 0), 2),
        "profile": {
            **profile,
            "xp_next": xp_for_next(profile["level"]),
            "warehouse_capacity": _capacity(profile),
            "warehouse_used": used + profile["reserved_capacity"],
            "warehouse_items": used,
            "warehouse_reserved": profile["reserved_capacity"],
        },
        "plots": plots,
        "inventory": inventory,
        "tools": tools,
        "fishing_session": fishing_session,
        "mining_run": mining_run,
        "catalog": public_catalog(),
    }


def _change_inventory(conn, username, item_id, delta):
    row = conn.execute(
        "SELECT quantity FROM estate_inventory WHERE username = ? AND item_id = ?",
        (username, item_id),
    ).fetchone()
    current = int(row[0]) if row else 0
    updated = current + int(delta)
    if updated < 0:
        raise EstateError("inventory_short", "库存数量不足")
    if updated == 0:
        conn.execute(
            "DELETE FROM estate_inventory WHERE username = ? AND item_id = ?",
            (username, item_id),
        )
    else:
        conn.execute(
            "INSERT INTO estate_inventory(username,item_id,quantity) VALUES (?,?,?) "
            "ON CONFLICT(username,item_id) DO UPDATE SET quantity=excluded.quantity",
            (username, item_id, updated),
        )
    return updated


def _require_capacity(conn, username, profile, extra):
    if _inventory_used(conn, username) + profile.get("reserved_capacity", 0) + extra > _capacity(profile):
        raise EstateError("warehouse_full", "仓库空间不足")


def _request_hash(action_type, payload):
    raw = json.dumps(
        {"action": action_type, "payload": payload},
        ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _validate_request_id(request_id):
    if not isinstance(request_id, str):
        raise EstateError("invalid_request", "请求编号无效")
    request_id = request_id.strip()
    if not 8 <= len(request_id) <= 80 or any(ord(char) < 33 for char in request_id):
        raise EstateError("invalid_request", "请求编号无效")
    return request_id


def _bump(conn, username, now):
    conn.execute(
        "UPDATE estate_profiles SET version=version+1,updated_at=? WHERE username=?",
        (int(now), username),
    )


def _action(conn, username, request_id, action_type, payload, now, mutate):
    request_id = _validate_request_id(request_id)
    ensure_estate(conn, username, now)
    digest = _request_hash(action_type, payload)
    existing = conn.execute(
        "SELECT action_type,request_hash,result_json FROM estate_actions "
        "WHERE username=? AND request_id=?", (username, request_id),
    ).fetchone()
    if existing:
        if existing[0] != action_type or existing[1] != digest:
            raise EstateError("request_conflict", "请求编号已被其他操作使用")
        return {**json.loads(existing[2]), "replayed": True, "request_id": request_id}

    result = mutate()
    _bump(conn, username, now)
    stored = {**result, "replayed": False, "request_id": request_id}
    conn.execute(
        "INSERT INTO estate_actions"
        "(username,request_id,action_type,request_hash,result_json,created_at) "
        "VALUES (?,?,?,?,?,?)",
        (username, request_id, action_type, digest,
         json.dumps(stored, ensure_ascii=False, separators=(",", ":")), int(now)),
    )
    return stored


def _debit(adjust_coins, conn, username, amount, detail, request_id):
    try:
        return adjust_coins(
            conn, username, -round(amount, 2), "estate_purchase", detail,
            ref=f"estate:{request_id}",
        )
    except ValueError as error:
        raise EstateError("insufficient_coins", str(error) or "金币不足") from None


def buy(conn, username, request_id, item_kind, item_id, quantity, now, adjust_coins):
    item_kind = str(item_kind or "")
    payload = {"kind": item_kind, "item_id": item_id, "quantity": quantity}

    def mutate():
        profile = _profile(conn, username)
        if item_kind == "seed":
            crop = CROPS.get(str(item_id))
            count = _positive_int(quantity, maximum=999)
            if not crop:
                raise EstateError("unknown_item", "种子不存在")
            if profile["level"] < crop["unlock_level"]:
                raise EstateError("level_locked", "庄园等级不足")
            _require_capacity(conn, username, profile, count)
            total = round(crop["seed_price"] * count, 2)
            balance = _debit(adjust_coins, conn, username, total,
                             f"小胖庄园购买：{crop['name']}种子 ×{count}", request_id)
            _change_inventory(conn, username, seed_item(str(item_id)), count)
            return {"action": "buy", "kind": "seed", "item_id": item_id,
                    "quantity": count, "cost": total, "coins": balance}

        if item_kind == "bait":
            bait = BAITS.get(str(item_id))
            count = _positive_int(quantity, maximum=999)
            if not bait:
                raise EstateError("unknown_item", "鱼饵不存在")
            if profile["level"] < bait["unlock_level"]:
                raise EstateError("level_locked", "庄园等级不足")
            _require_capacity(conn, username, profile, count)
            total = round(bait["price"] * count, 2)
            balance = _debit(adjust_coins, conn, username, total,
                             f"小胖庄园购买：{bait['name']} ×{count}", request_id)
            _change_inventory(conn, username, bait_item(str(item_id)), count)
            return {"action": "buy", "kind": "bait", "item_id": item_id,
                    "quantity": count, "cost": total, "coins": balance}

        if item_kind == "plot":
            index = _plot_index(item_id)
            if index != profile["plot_count"] or index not in PLOT_UNLOCKS:
                raise EstateError("plot_unavailable", "该土地当前无法购买")
            rule = PLOT_UNLOCKS[index]
            if profile["level"] < rule["unlock_level"]:
                raise EstateError("level_locked", "庄园等级不足")
            balance = _debit(adjust_coins, conn, username, rule["price"],
                             f"小胖庄园购买：第 {index + 1} 块土地", request_id)
            conn.execute(
                "UPDATE estate_profiles SET plot_count=plot_count+1 WHERE username=?",
                (username,),
            )
            return {"action": "buy", "kind": "plot", "item_id": index,
                    "quantity": 1, "cost": rule["price"], "coins": balance}

        if item_kind == "land":
            index = _plot_index(item_id)
            if index >= profile["plot_count"]:
                raise EstateError("plot_locked", "土地尚未解锁")
            row = conn.execute(
                "SELECT land_level,crop_id FROM estate_plots "
                "WHERE username=? AND plot_index=?", (username, index),
            ).fetchone()
            if not row:
                raise EstateError("invalid_plot", "土地不存在")
            if row[1] is not None:
                raise EstateError("plot_busy", "有作物时不能升级土地")
            current = LAND_LEVELS.get(row[0])
            next_level = row[0] + 1
            if not current or current["upgrade_price"] is None or next_level not in LAND_LEVELS:
                raise EstateError("max_level", "土地已达到最高等级")
            if profile["level"] < current["unlock_level"]:
                raise EstateError("level_locked", "庄园等级不足")
            balance = _debit(adjust_coins, conn, username, current["upgrade_price"],
                             f"小胖庄园升级：第 {index + 1} 块土地", request_id)
            conn.execute(
                "UPDATE estate_plots SET land_level=? WHERE username=? AND plot_index=?",
                (next_level, username, index),
            )
            return {"action": "buy", "kind": "land", "item_id": index,
                    "land_level": next_level, "cost": current["upgrade_price"],
                    "coins": balance}

        if item_kind == "warehouse":
            current = WAREHOUSE_LEVELS.get(profile["warehouse_level"])
            next_level = profile["warehouse_level"] + 1
            if not current or current["upgrade_price"] is None or next_level not in WAREHOUSE_LEVELS:
                raise EstateError("max_level", "仓库已达到最高等级")
            if profile["level"] < current["unlock_level"]:
                raise EstateError("level_locked", "庄园等级不足")
            balance = _debit(adjust_coins, conn, username, current["upgrade_price"],
                             "小胖庄园升级：仓库扩容", request_id)
            conn.execute(
                "UPDATE estate_profiles SET warehouse_level=? WHERE username=?",
                (next_level, username),
            )
            return {"action": "buy", "kind": "warehouse", "item_id": next_level,
                    "warehouse_level": next_level, "cost": current["upgrade_price"],
                    "coins": balance}

        raise EstateError("unknown_purchase", "未知购买项目")

    return _action(conn, username, request_id, "buy", payload, now, mutate)


def plant(conn, username, request_id, plot_id, crop_id, now):
    index = _plot_index(plot_id)
    crop_id = str(crop_id or "")
    payload = {"plot_id": index, "crop_id": crop_id}

    def mutate():
        profile = _profile(conn, username)
        crop = CROPS.get(crop_id)
        if not crop:
            raise EstateError("unknown_crop", "作物不存在")
        if profile["level"] < crop["unlock_level"]:
            raise EstateError("level_locked", "庄园等级不足")
        if index >= profile["plot_count"]:
            raise EstateError("plot_locked", "土地尚未解锁")
        row = conn.execute(
            "SELECT land_level,crop_id FROM estate_plots WHERE username=? AND plot_index=?",
            (username, index),
        ).fetchone()
        if not row:
            raise EstateError("invalid_plot", "土地不存在")
        if row[1] is not None:
            raise EstateError("plot_busy", "土地上已有作物")
        _change_inventory(conn, username, seed_item(crop_id), -1)
        ready_at = int(now) + grow_seconds(crop_id, row[0])
        conn.execute(
            "UPDATE estate_plots SET crop_id=?,planted_at=?,ready_at=? "
            "WHERE username=? AND plot_index=?",
            (crop_id, int(now), ready_at, username, index),
        )
        return {"action": "plant", "plot_id": index, "crop_id": crop_id,
                "ready_at": ready_at}

    return _action(conn, username, request_id, "plant", payload, now, mutate)


def harvest(conn, username, request_id, plot_id, now):
    index = _plot_index(plot_id)
    payload = {"plot_id": index}

    def mutate():
        profile = _profile(conn, username)
        if index >= profile["plot_count"]:
            raise EstateError("plot_locked", "土地尚未解锁")
        row = conn.execute(
            "SELECT crop_id,ready_at FROM estate_plots WHERE username=? AND plot_index=?",
            (username, index),
        ).fetchone()
        if not row or not row[0]:
            raise EstateError("plot_empty", "土地上没有作物")
        if row[1] > int(now):
            raise EstateError("crop_growing", "作物还没有成熟")
        crop_id = row[0]
        crop = CROPS.get(crop_id)
        if not crop:
            raise EstateError("invalid_save", "作物数据异常")
        _require_capacity(conn, username, profile, crop["yield"])
        _change_inventory(conn, username, crop_item(crop_id), crop["yield"])
        conn.execute(
            "UPDATE estate_plots SET crop_id=NULL,planted_at=NULL,ready_at=NULL "
            "WHERE username=? AND plot_index=?", (username, index),
        )
        level = profile["level"]
        xp = profile["xp"] + crop["xp"]
        levels_gained = 0
        while xp >= xp_for_next(level):
            xp -= xp_for_next(level)
            level += 1
            levels_gained += 1
        conn.execute(
            "UPDATE estate_profiles SET level=?,xp=? WHERE username=?",
            (level, xp, username),
        )
        return {"action": "harvest", "plot_id": index, "crop_id": crop_id,
                "quantity": crop["yield"], "xp_awarded": crop["xp"],
                "levels_gained": levels_gained, "level": level}

    return _action(conn, username, request_id, "harvest", payload, now, mutate)


def sell(conn, username, request_id, item_id, quantity, now, adjust_coins):
    item_id = str(item_id or "")
    count = _positive_int(quantity, maximum=9999)
    payload = {"item_id": item_id, "quantity": count}

    def mutate():
        info = item_info(item_id)
        if not info or not info["sellable"]:
            raise EstateError("not_sellable", "该物品不能出售")
        _change_inventory(conn, username, item_id, -count)
        total = round(info["sell_price"] * count, 2)
        balance = adjust_coins(
            conn, username, total, "estate_sale",
            f"小胖庄园出售：{info['name']} ×{count}", ref=f"estate:{request_id}",
        )
        return {"action": "sell", "item_id": item_id, "quantity": count,
                "earned": total, "coins": balance}

    return _action(conn, username, request_id, "sell", payload, now, mutate)


def sell_all(conn, username, request_id, now, adjust_coins):
    payload = {"sell_all": True}

    def mutate():
        sold = []
        total = 0.0
        for item_id, quantity in _inventory_rows(conn, username):
            info = item_info(item_id)
            if not info or not info["sellable"]:
                continue
            amount = round(info["sell_price"] * quantity, 2)
            sold.append({"item_id": item_id, "quantity": quantity, "earned": amount})
            total += amount
        if not sold:
            raise EstateError("nothing_to_sell", "仓库里没有可出售的产品")
        for entry in sold:
            _change_inventory(conn, username, entry["item_id"], -entry["quantity"])
        total = round(total, 2)
        balance = adjust_coins(
            conn, username, total, "estate_sale", "小胖庄园一键出售",
            ref=f"estate:{request_id}",
        )
        return {"action": "sell_all", "sold": sold, "earned": total,
                "coins": balance}

    return _action(conn, username, request_id, "sell_all", payload, now, mutate)
