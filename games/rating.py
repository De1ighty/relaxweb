"""收益率段位分：只依赖真实结算金额，不依赖金币余额或房间注额。"""
from decimal import Decimal, ROUND_HALF_UP

INITIAL_RATING = 1000
WIN_FACTOR = 40
LOSS_FACTOR = 20
TIERS = ((0, "青铜"), (800, "白银"), (1200, "黄金"),
         (1600, "铂金"), (2000, "钻石"), (2400, "大师"))


def rating_info(score=INITIAL_RATING, games=0):
    floor, tier = next((floor, tier) for floor, tier in reversed(TIERS) if score >= floor)
    next_tier = next(((floor, tier) for floor, tier in TIERS if floor > score), None)
    return {"score": score, "tier": tier, "games": games, "floor": floor,
            "next_score": next_tier[0] if next_tier else None,
            "next_tier": next_tier[1] if next_tier else None}


def rating_change(initial, final):
    """四舍五入到整数（负数也远离零）；无效金额不能进入评分。"""
    initial, final = Decimal(str(initial)), Decimal(str(final))
    if not initial.is_finite() or not final.is_finite() or initial <= 0 or final < 0:
        raise ValueError("段位结算金额无效")
    factor = WIN_FACTOR if final >= initial else LOSS_FACTOR
    change = factor * (final - initial) / initial
    return int(Decimal(max(-LOSS_FACTOR, min(WIN_FACTOR, change))).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP))
