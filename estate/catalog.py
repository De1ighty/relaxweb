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


def seed_item(crop_id):
    return f"seed:{crop_id}"


def crop_item(crop_id):
    return f"crop:{crop_id}"


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
    crop = CROPS.get(crop_id)
    if not crop or kind not in ("seed", "crop"):
        return None
    return {
        "id": item_id,
        "kind": kind,
        "crop_id": crop_id,
        "name": f"{crop['name']}种子" if kind == "seed" else crop["name"],
        "sellable": kind == "crop",
        "sell_price": crop["sell_price"] if kind == "crop" else None,
    }


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
        "initial_plots": INITIAL_PLOTS,
        "max_plots": MAX_PLOTS,
    }
