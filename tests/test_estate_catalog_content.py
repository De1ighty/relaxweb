#!/usr/bin/env python3
"""小胖庄园扩充内容目录契约。"""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from estate.catalog import CROPS, FISH, FISHING_TREASURES, item_info, public_catalog


class EstateCatalogContentTests(unittest.TestCase):
    def test_catalog_has_twenty_four_crops_and_fish(self):
        self.assertEqual(len(CROPS), 24)
        self.assertEqual(len(FISH), 24)
        self.assertEqual(len(FISHING_TREASURES), 4)

    def test_xiaopang_content_is_present_and_endgame_rare(self):
        self.assertEqual(CROPS["xiaopang_grass"]["name"], "小胖草")
        self.assertEqual(CROPS["xiaopang_flower"]["name"], "小胖花")
        self.assertGreaterEqual(CROPS["xiaopang_grass"]["unlock_level"], 6)
        self.assertEqual(FISH["xiaopang_fish"]["name"], "小胖鱼")
        self.assertGreaterEqual(FISH["xiaopang_fish"]["rarity"], 6)
        underwear = FISHING_TREASURES["xiaopang_underwear"]
        self.assertEqual(underwear["name"], "小胖的内裤")
        self.assertEqual(underwear["rarity"], max(v["rarity"] for v in FISHING_TREASURES.values()))
        self.assertGreaterEqual(underwear["required_rod_level"], 3)

    def test_collectibles_are_public_inventory_items(self):
        catalog = public_catalog()
        self.assertIn("fishing_treasures", catalog)
        info = item_info("collectible:xiaopang_underwear")
        self.assertEqual(info["kind"], "collectible")
        self.assertFalse(info["sellable"])
        self.assertEqual(info["name"], "小胖的内裤")

    def test_catalog_uses_reviewed_economy_version(self):
        self.assertEqual(public_catalog()["balance_version"], "v1")
        for entry in (*CROPS.values(), *FISH.values(), *FISHING_TREASURES.values()):
            self.assertEqual(entry["balance_status"], "v1")


if __name__ == "__main__":
    unittest.main(verbosity=2)
