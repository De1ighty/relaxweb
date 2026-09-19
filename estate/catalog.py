"""小胖庄园服务端权威目录。

数值集中在这里，前端只消费 ``public_catalog`` 的输出，不能提交价格、
成熟时间、产量或经验。首轮数值用于功能测试和 HTML 试玩，PR 前再做
一次人工经济审阅。
"""
import math


INITIAL_PLOTS = 4
MAX_PLOTS = 8

CROPS = {
    "wheat": {
        "name": "小麦", "seed_price": 20.0, "sell_price": 30.0,
        "grow_seconds": 5 * 60, "yield": 1, "xp": 5, "unlock_level": 1,
    },
    "carrot": {
        "name": "胡萝卜", "seed_price": 40.0, "sell_price": 65.0,
        "grow_seconds": 15 * 60, "yield": 1, "xp": 8, "unlock_level": 1,
    },
    "corn": {
        "name": "玉米", "seed_price": 100.0, "sell_price": 170.0,
        "grow_seconds": 60 * 60, "yield": 1, "xp": 20, "unlock_level": 2,
    },
    "pumpkin": {
        "name": "南瓜", "seed_price": 260.0, "sell_price": 450.0,
        "grow_seconds": 4 * 60 * 60, "yield": 1, "xp": 40, "unlock_level": 3,
    },
}

LAND_LEVELS = {
    1: {"multiplier": 1.0, "upgrade_price": 500.0, "unlock_level": 2},
    2: {"multiplier": 0.85, "upgrade_price": 1500.0, "unlock_level": 4},
    3: {"multiplier": 0.65, "upgrade_price": None, "unlock_level": 6},
}

PLOT_UNLOCKS = {
    4: {"price": 500.0, "unlock_level": 2},
    5: {"price": 900.0, "unlock_level": 3},
    6: {"price": 1600.0, "unlock_level": 4},
    7: {"price": 2600.0, "unlock_level": 5},
}

WAREHOUSE_LEVELS = {
    1: {"capacity": 100, "upgrade_price": 1000.0, "unlock_level": 2},
    2: {"capacity": 200, "upgrade_price": 3000.0, "unlock_level": 4},
    3: {"capacity": 350, "upgrade_price": None, "unlock_level": 6},
}

TOOLS = {
    "rod": {
        1: {"name": "榛木鱼竿", "price": 300.0, "max_durability": 20,
            "repair_price": 90.0, "upgrade_price": 900.0, "unlock_level": 1,
            "tension_factor": 1.0},
        2: {"name": "碳素鱼竿", "price": None, "max_durability": 35,
            "repair_price": 220.0, "upgrade_price": 2400.0, "unlock_level": 3,
            "tension_factor": 0.82},
        3: {"name": "星纹鱼竿", "price": None, "max_durability": 55,
            "repair_price": 480.0, "upgrade_price": None, "unlock_level": 6,
            "tension_factor": 0.68},
    },
    "pickaxe": {
        1: {"name": "铜矿镐", "price": 350.0, "max_durability": 20,
            "repair_price": 110.0, "upgrade_price": 1100.0, "unlock_level": 1,
            "strikes": 8},
        2: {"name": "铁矿镐", "price": None, "max_durability": 35,
            "repair_price": 260.0, "upgrade_price": 2800.0, "unlock_level": 3,
            "strikes": 11},
        3: {"name": "秘银矿镐", "price": None, "max_durability": 55,
            "repair_price": 550.0, "upgrade_price": None, "unlock_level": 6,
            "strikes": 14},
    },
}

BAITS = {
    "worm": {"name": "蚯蚓鱼饵", "price": 15.0, "unlock_level": 1, "rarity_bonus": 0},
    "glow_grub": {"name": "荧光虫饵", "price": 45.0, "unlock_level": 3, "rarity_bonus": 1},
}

FISH = {
    "minnow": {"name": "银鲦", "sell_price": 42.0, "rarity": 1, "xp": 8, "difficulty": .18},
    "carp": {"name": "湖鲤", "sell_price": 70.0, "rarity": 1, "xp": 12, "difficulty": .25},
    "perch": {"name": "金鲈", "sell_price": 115.0, "rarity": 2, "xp": 18, "difficulty": .36},
    "koi": {"name": "锦鲤", "sell_price": 210.0, "rarity": 3, "xp": 30, "difficulty": .48},
    "moon_eel": {"name": "月影鳗", "sell_price": 390.0, "rarity": 4, "xp": 46, "difficulty": .62},
    "crystal_fish": {"name": "水晶鱼", "sell_price": 720.0, "rarity": 5, "xp": 70, "difficulty": .75},
}

MINERALS = {
    "stone": {"name": "石料", "sell_price": 18.0, "rarity": 1},
    "coal": {"name": "煤块", "sell_price": 32.0, "rarity": 1},
    "copper": {"name": "铜矿", "sell_price": 65.0, "rarity": 2},
    "iron": {"name": "铁矿", "sell_price": 120.0, "rarity": 3},
    "amethyst": {"name": "紫晶", "sell_price": 260.0, "rarity": 4},
    "star_gem": {"name": "星辉宝石", "sell_price": 620.0, "rarity": 5},
}

MINING_LEVELS = {
    1: {"name": "青苔浅层", "unlock_level": 1, "weights": [42, 18, 20, 7, 2, 0]},
    2: {"name": "赤铜中层", "unlock_level": 3, "weights": [28, 16, 25, 15, 5, 1]},
    3: {"name": "星晶深层", "unlock_level": 6, "weights": [18, 12, 20, 24, 10, 3]},
}


def seed_item(crop_id):
    return f"seed:{crop_id}"


def crop_item(crop_id):
    return f"crop:{crop_id}"


def bait_item(bait_id):
    return f"bait:{bait_id}"


def fish_item(fish_id):
    return f"fish:{fish_id}"


def mineral_item(mineral_id):
    return f"mineral:{mineral_id}"


def xp_for_next(level):
    """当前等级升到下一级所需经验。"""
    return 100 * max(1, int(level))


def grow_seconds(crop_id, land_level):
    crop = CROPS[crop_id]
    land = LAND_LEVELS[land_level]
    return max(1, math.ceil(crop["grow_seconds"] * land["multiplier"]))


def item_info(item_id):
    if not isinstance(item_id, str) or ":" not in item_id:
        return None
    kind, crop_id = item_id.split(":", 1)
    if kind in ("seed", "crop") and crop_id in CROPS:
        crop = CROPS[crop_id]
        return {"id": item_id, "kind": kind, "crop_id": crop_id,
                "name": f"{crop['name']}种子" if kind == "seed" else crop["name"],
                "sellable": kind == "crop",
                "sell_price": crop["sell_price"] if kind == "crop" else None}
    groups = {"bait": BAITS, "fish": FISH, "mineral": MINERALS}
    group = groups.get(kind)
    if not group or crop_id not in group:
        return None
    entry = group[crop_id]
    return {"id": item_id, "kind": kind, f"{kind}_id": crop_id,
            "name": entry["name"], "sellable": kind in ("fish", "mineral"),
            "sell_price": entry.get("sell_price")}


def public_catalog():
    return {
        "crops": {
            crop_id: {
                "id": crop_id,
                "name": crop["name"],
                "seed_item": seed_item(crop_id),
                "product_item": crop_item(crop_id),
                **crop,
            }
            for crop_id, crop in CROPS.items()
        },
        "land_levels": LAND_LEVELS,
        "plot_unlocks": PLOT_UNLOCKS,
        "warehouse_levels": WAREHOUSE_LEVELS,
        "tools": TOOLS,
        "baits": {key: {"id": key, "item_id": bait_item(key), **value}
                  for key, value in BAITS.items()},
        "fish": {key: {"id": key, "item_id": fish_item(key), **value}
                 for key, value in FISH.items()},
        "minerals": {key: {"id": key, "item_id": mineral_item(key), **value}
                     for key, value in MINERALS.items()},
        "mining_levels": MINING_LEVELS,
        "initial_plots": INITIAL_PLOTS,
        "max_plots": MAX_PLOTS,
    }
