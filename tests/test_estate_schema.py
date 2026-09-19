#!/usr/bin/env python3
"""小胖庄园表结构与目录测试。"""
import sqlite3
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from estate.catalog import CROPS, INITIAL_PLOTS, LAND_LEVELS, WAREHOUSE_LEVELS
from estate.schema import init_estate


class EstateSchemaTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        init_estate(self.conn)

    def tearDown(self):
        self.conn.close()

    def test_tables_and_repeated_migration(self):
        init_estate(self.conn)
        tables = {
            row[0] for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        self.assertTrue({"estate_profiles", "estate_plots", "estate_inventory",
                         "estate_actions"}.issubset(tables))

    def test_profile_rejects_invalid_values(self):
        for column, value in (("level", 0), ("xp", -1), ("warehouse_level", 0),
                              ("plot_count", -1), ("version", 0)):
            with self.assertRaises(sqlite3.IntegrityError, msg=column):
                self.conn.execute(
                    f"INSERT INTO estate_profiles(username,{column},created_at,updated_at) "
                    "VALUES ('alice', ?, 0, 0)", (value,)
                )

    def test_plot_and_inventory_constraints(self):
        self.conn.execute(
            "INSERT INTO estate_plots(username,plot_index) VALUES ('alice',0)"
        )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO estate_plots(username,plot_index) VALUES ('alice',0)"
            )
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO estate_inventory(username,item_id,quantity) "
                "VALUES ('alice','seed:wheat',0)"
            )

    def test_catalog_has_profitable_crops_and_valid_progression(self):
        self.assertGreaterEqual(INITIAL_PLOTS, 2)
        for crop in CROPS.values():
            self.assertGreater(crop["sell_price"], crop["seed_price"])
            self.assertGreater(crop["grow_seconds"], 0)
            self.assertGreater(crop["yield"], 0)
            self.assertGreater(crop["xp"], 0)
        self.assertEqual(sorted(LAND_LEVELS), list(range(1, len(LAND_LEVELS) + 1)))
        self.assertEqual(
            sorted(WAREHOUSE_LEVELS), list(range(1, len(WAREHOUSE_LEVELS) + 1))
        )


if __name__ == "__main__":
    unittest.main()
