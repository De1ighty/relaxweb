"""小胖庄园服务端权威目录。

数值集中在这里，前端只消费 ``public_catalog`` 的输出，不能提交价格、
成熟时间、产量或经验。首轮数值用于功能测试和 HTML 试玩，PR 前再做
一次人工经济审阅。
"""
import math


INITIAL_PLOTS = 4
MAX_PLOTS = 8

def _crop(name, seed_price, sell_price, grow_minutes, xp, unlock_level, icon, color):
    """创建待平衡作物条目；正式数值确定后只需改本目录。"""
    return {
        "name": name, "seed_price": float(seed_price), "sell_price": float(sell_price),
        "grow_seconds": int(grow_minutes * 60), "yield": 1, "xp": xp,
        "unlock_level": unlock_level, "icon": icon, "color": color,
        "balance_status": "draft",
    }


CROPS = {
    "wheat": _crop("小麦", 20, 30, 5, 5, 1, "🌾", "#e6cb63"),
    "carrot": _crop("胡萝卜", 40, 65, 15, 8, 1, "🥕", "#f28b36"),
    "rice": _crop("水稻", 28, 44, 9, 6, 1, "🌾", "#ddd477"),
    "potato": _crop("土豆", 34, 54, 12, 7, 1, "🥔", "#c99b61"),
    "tomato": _crop("番茄", 52, 84, 20, 10, 1, "🍅", "#df5b45"),
    "cabbage": _crop("卷心菜", 64, 104, 28, 12, 2, "🥬", "#78b95d"),
    "cucumber": _crop("黄瓜", 72, 118, 35, 14, 2, "🥒", "#5da653"),
    "soybean": _crop("大豆", 82, 136, 42, 16, 2, "🫘", "#d0b65d"),
    "corn": _crop("玉米", 100, 170, 60, 20, 2, "🌽", "#f4cf46"),
    "peanut": _crop("花生", 116, 198, 75, 23, 2, "🥜", "#c78b50"),
    "sweet_potato": _crop("红薯", 132, 228, 90, 26, 3, "🍠", "#b75c49"),
    "eggplant": _crop("茄子", 150, 260, 110, 30, 3, "🍆", "#835c9f"),
    "pepper": _crop("辣椒", 172, 302, 135, 34, 3, "🌶️", "#d94b3d"),
    "pumpkin": _crop("南瓜", 260, 450, 240, 40, 3, "🎃", "#ee7a2d"),
    "strawberry": _crop("草莓", 290, 510, 300, 46, 4, "🍓", "#e85e67"),
    "watermelon": _crop("西瓜", 340, 610, 390, 54, 4, "🍉", "#52a95e"),
    "grape": _crop("葡萄", 410, 750, 480, 62, 4, "🍇", "#8663a8"),
    "spinach": _crop("菠菜", 460, 850, 600, 72, 5, "🥬", "#3e9652"),
    "onion": _crop("洋葱", 530, 990, 750, 84, 5, "🧅", "#d3a5bb"),
    "garlic": _crop("大蒜", 620, 1170, 900, 96, 5, "🧄", "#e7d9b1"),
    "sunflower": _crop("向日葵", 760, 1450, 1080, 112, 6, "🌻", "#f3c84d"),
    "xiaopang_grass": _crop("小胖草", 1100, 2250, 1440, 150, 6, "🌿", "#64c987"),
    "xiaopang_flower": _crop("小胖花", 1800, 3900, 2160, 220, 7, "🌸", "#f28fc2"),
    "starlight_berry": _crop("星露果", 3200, 7200, 2880, 320, 8, "✨", "#8dd9df"),
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

def _fish(name, sell_price, rarity, xp, difficulty, habitat):
    return {
        "name": name, "sell_price": float(sell_price), "rarity": rarity, "xp": xp,
        "difficulty": difficulty, "habitat": habitat, "balance_status": "draft",
    }


FISH = {
    "minnow": _fish("银鲦", 42, 1, 8, .18, "溪流"),
    "carp": _fish("湖鲤", 70, 1, 12, .25, "湖泊"),
    "crucian_carp": _fish("鲫鱼", 58, 1, 10, .22, "湖泊"),
    "tilapia": _fish("罗非鱼", 64, 1, 11, .24, "暖水湖"),
    "loach": _fish("泥鳅", 52, 1, 9, .21, "浅滩"),
    "perch": _fish("金鲈", 115, 2, 18, .36, "湖泊"),
    "catfish": _fish("鲶鱼", 128, 2, 20, .39, "河底"),
    "grass_carp": _fish("草鱼", 138, 2, 21, .38, "湖泊"),
    "silver_carp": _fish("鲢鱼", 146, 2, 22, .41, "河流"),
    "bream": _fish("鳊鱼", 152, 2, 23, .42, "湖泊"),
    "snakehead": _fish("黑鱼", 185, 3, 27, .47, "芦苇荡"),
    "bass": _fish("大口鲈", 205, 3, 30, .5, "深水湖"),
    "trout": _fish("虹鳟", 228, 3, 33, .53, "溪流"),
    "koi": _fish("锦鲤", 245, 3, 34, .5, "湖泊"),
    "pike": _fish("白斑狗鱼", 310, 4, 42, .59, "深水湖"),
    "salmon": _fish("鲑鱼", 340, 4, 45, .61, "河口"),
    "sardine": _fish("沙丁鱼", 285, 4, 39, .56, "近海"),
    "mackerel": _fish("鲭鱼", 390, 4, 50, .64, "近海"),
    "moon_eel": _fish("欧洲鳗鲡", 430, 4, 52, .66, "夜间河口"),
    "sturgeon": _fish("中华鲟", 590, 5, 65, .72, "大河"),
    "tuna": _fish("蓝鳍金枪鱼", 760, 5, 76, .78, "远海"),
    "crystal_fish": _fish("玻璃鱼", 680, 5, 70, .74, "清澈湖泊"),
    "cloudfin": _fish("云鳍鱼", 1200, 6, 105, .84, "雨后云影"),
    "xiaopang_fish": _fish("小胖鱼", 1680, 6, 135, .9, "小胖湖深处"),
}


FISHING_TREASURES = {
    "xiaopang_bottle": {
        "name": "小胖漂流瓶", "rarity": 5, "xp": 45, "difficulty": .68,
        "required_rod_level": 2, "weight": 5.0, "balance_status": "draft",
    },
    "xiaopang_button": {
        "name": "小胖的金纽扣", "rarity": 6, "xp": 70, "difficulty": .76,
        "required_rod_level": 2, "weight": 2.4, "balance_status": "draft",
    },
    "xiaopang_watch": {
        "name": "小胖旧怀表", "rarity": 7, "xp": 110, "difficulty": .84,
        "required_rod_level": 3, "weight": .8, "balance_status": "draft",
    },
    "xiaopang_underwear": {
        "name": "小胖的内裤", "rarity": 8, "xp": 180, "difficulty": .92,
        "required_rod_level": 3, "weight": .18, "balance_status": "draft",
    },
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


def collectible_item(collectible_id):
    return f"collectible:{collectible_id}"


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
    groups = {"bait": BAITS, "fish": FISH, "mineral": MINERALS,
              "collectible": FISHING_TREASURES}
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
        "fishing_treasures": {
            key: {"id": key, "item_id": collectible_item(key), **value}
            for key, value in FISHING_TREASURES.items()
        },
        "minerals": {key: {"id": key, "item_id": mineral_item(key), **value}
                     for key, value in MINERALS.items()},
        "mining_levels": MINING_LEVELS,
        "initial_plots": INITIAL_PLOTS,
        "max_plots": MAX_PLOTS,
    }
