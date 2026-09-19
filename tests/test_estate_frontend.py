#!/usr/bin/env python3
"""小胖庄园前端装配与双端输入的静态契约。"""
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parent.parent


class EstateFrontendTests(unittest.TestCase):
    def read(self, relative):
        return (ROOT / relative).read_text(encoding="utf-8")

    def test_solo_hall_route_is_metadata_driven(self):
        config = self.read("assets/js/game-config.js")
        hall = self.read("assets/js/hall.js")
        core = self.read("assets/js/core.js")
        self.assertIn('id: "estate"', config)
        self.assertIn('mode: "solo"', config)
        self.assertIn('view: "estate"', config)
        self.assertIn("ROOM_GAME_TYPES", config)
        self.assertIn('game.mode === "solo" ? game.view : "rooms"', hall)
        self.assertIn('renderView(state.hallPage)', core)
        self.assertNotIn('game.id === "estate"', hall)

    def test_entry_reaches_all_estate_modules_and_style(self):
        main = self.read("assets/js/main.js")
        page = self.read("game.html")
        self.assertIn('import "./estate/view.js"', main)
        self.assertIn('assets/css/estate.css?v=', page)
        for name in ("state", "protocol", "input", "art", "sprites", "map", "ui", "fishing", "mining", "view"):
            self.assertTrue((ROOT / f"assets/js/estate/{name}.js").is_file())

    def test_cc0_pixel_atlases_are_local_and_documented(self):
        attribution = self.read("assets/estate/ATTRIBUTION.md")
        sprites = self.read("assets/js/estate/sprites.js")
        for name in ("tiny-farm", "tiny-town"):
            self.assertTrue((ROOT / f"assets/estate/kenney/{name}.png").is_file())
            self.assertIn(f"kenney/{name}.png", attribution)
            self.assertIn(f"assets/estate/kenney/{name}.png", sprites)
        self.assertIn("CC0", attribution)
        self.assertTrue((ROOT / "assets/estate/kenney/License-tiny-farm.txt").is_file())
        self.assertTrue((ROOT / "assets/estate/kenney/License-tiny-town.txt").is_file())

    def test_desktop_and_mobile_controls_are_present(self):
        source = self.read("assets/js/estate/input.js")
        world = self.read("assets/js/estate/map.js")
        style = self.read("assets/css/estate.css")
        for key in ("ArrowRight", "ArrowLeft", "KeyW", "KeyA", "KeyE", "Space", "ShiftLeft"):
            self.assertIn(key, source)
        self.assertIn("sprinting", source)
        self.assertIn("input.sprinting", world)
        self.assertIn("190", world)
        for event in ("pointerdown", "pointermove", "pointerup", "pointercancel"):
            self.assertIn(event, source)
        self.assertIn("touch-action: none", style)
        self.assertIn("(pointer: coarse)", style)

    def test_map_and_economy_actions_are_wired(self):
        world = self.read("assets/js/estate/map.js")
        art = self.read("assets/js/estate/art.js")
        ui = self.read("assets/js/estate/ui.js")
        self.assertIn("requestAnimationFrame", world)
        self.assertIn("collides", world)
        self.assertIn("drawPathSurface", world)
        self.assertNotIn('drawSprite(ctx, "town", 12', world)
        self.assertNotIn('drawSprite(ctx, "town", 24', world)
        self.assertIn('direction: "down"', world)
        self.assertIn("drawPlotFrame", world)
        self.assertNotIn('stableSprite(x, [3, 4, 5, 8, 9, 10])', world)
        for direction in ('"up"', '"down"', '"left"', '"right"'):
            self.assertIn(direction, art)
        for action in ("estate_buy", "estate_plant", "estate_harvest", "estate_sell", "estate_sell_all"):
            self.assertIn(action, ui)
        for action in ("estate_buy_tool", "estate_start_fishing", "estate_start_mining"):
            self.assertIn(action, ui)
        self.assertIn("estate_finish_fishing", self.read("assets/js/estate/fishing.js"))
        fishing = self.read("assets/js/estate/fishing.js")
        self.assertIn("Math.floor(trace.length / 10)", fishing)
        self.assertNotIn("Math.floor(elapsed)", fishing)
        self.assertIn("fishing-catch-card", fishing)
        self.assertIn("继续钓鱼", fishing)
        self.assertIn("返回小胖钓场", fishing)
        self.assertIn("estate_mine_cell", self.read("assets/js/estate/mining.js"))
        mining = self.read("assets/js/estate/mining.js")
        self.assertIn('bomb: "💣"', mining)
        self.assertIn("mine-explosion", mining)

    def test_all_interactive_places_use_xiaopang_branding(self):
        combined = "\n".join([
            self.read("assets/js/estate/map.js"),
            self.read("assets/js/estate/ui.js"),
            self.read("assets/js/estate/fishing.js"),
        ])
        for name in ("小胖种子铺", "小胖谷仓", "小胖湖钓场", "小胖矿洞", "小胖农田"):
            self.assertIn(name, combined)
        for old_name in ("露露种子铺", "丰收谷仓", "星石矿洞", "月牙湖钓场", "谷仓库存"):
            self.assertNotIn(old_name, combined)

    def test_javascript_parses(self):
        for path in (ROOT / "assets/js/estate").glob("*.js"):
            result = subprocess.run(
                ["node", "--check", str(path)], capture_output=True, text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
