# -*- coding: utf-8 -*-
"""连通性规则（落差上限）可配置 + 规则变了自动重烘（2026-11-18）。

背景：烘焙图原来把"落差 > 5 格"整个禁掉（理由是"5 格内落地没伤害"——
那是 **hard 难度生存服**的要求）。但枪战服 `difficulty=peaceful`，
摔落一点血都不掉，这条规则纯属过度保守：它把大量"走下 6~8 格坎就到了"
的地方切成了孤岛，AI 站在原地不动，日志刷"不可达"。

实测（重建整张图）：
    harbor      MAX_DOWN  5 → 26 分量 / 孤岛 531(14.8%)
               MAX_DOWN 10 → 10 分量 / 孤岛  99(2.8%)
    炼狱小镇    MAX_DOWN  5 → 258 分量 / 孤岛 10262(21.6%)
               MAX_DOWN 10 → 152 分量 / 孤岛 5119(10.8%)

现在落差上限做成 settings.yml 的 `NAV_MAX_DOWN` / `NAV_MAX_UP`，
改完**自动重烘**（烘焙产物里记着当时的规则，对不上就当缓存作废）。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.nav.blocks_v1 import write_map  # noqa: E402
from endstone_arc_shooter_game.nav.navmap import NavService  # noqa: E402


class _Log:
    def __init__(self):
        self.infos = []

    def info(self, msg):
        self.infos.append(str(msg))

    def warning(self, msg):
        self.infos.append(str(msg))

    error = warning


def build_drop_map(path: Path, tower_height: int = 8) -> None:
    """5×5 地板（表面 y=64）+ (4,4) 一座 8 格高的台子（表面 y=72）。

    台顶到旁边地板落差 = 8 格 —— 现实里走下坡就掉下去了（和平难度不掉血），
    但 MAX_DOWN=5 的图里这是一堵墙。
    """
    columns = []
    for x in range(5):
        for z in range(5):
            blocks = [{"y": 63, "name": "minecraft:stone"}]
            if (x, z) == (4, 4):
                for y in range(64, 64 + tower_height):
                    blocks.append({"y": y, "name": "minecraft:stone"})
            columns.append((x, z, blocks))
    write_map(path, map_id="drop", display_name="落差图",
              bounds=[0, 4, 60, 66 + tower_height, 0, 4], step=1, columns=columns,
              total_columns=25, unloaded_columns=0)


class MaxDownRuleTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        maps_dir = self.data_dir / "nav" / "maps"
        maps_dir.mkdir(parents=True)
        build_drop_map(maps_dir / "drop.json")
        self.log = _Log()

    def tearDown(self):
        self._tmp.cleanup()

    def _svc(self, max_down):
        return NavService(self.data_dir, self.log, max_up=1, max_down=max_down)

    def test_drop_blocked_with_strict_rule(self):
        svc = self._svc(5)
        res = svc.query("drop", (4, 72, 4), (3, 64, 3))
        self.assertFalse(res["ok"], res["text"])

    def test_drop_allowed_with_loose_rule(self):
        svc = self._svc(10)
        res = svc.query("drop", (4, 72, 4), (3, 64, 3))
        self.assertTrue(res["ok"], res["text"])
        self.assertEqual(res["path"][0], [4, 72, 4])
        self.assertEqual(res["path"][-1], [3, 64, 3])

    def test_baked_file_records_rule(self):
        svc = self._svc(8)
        svc.bake("drop", force=True)
        raw = json.loads((self.data_dir / "nav" / "drop.nav.json")
                         .read_text(encoding="utf-8"))
        self.assertEqual(raw["rule"]["max_up"], 1)
        self.assertEqual(raw["rule"]["max_down"], 8)

    def test_rule_change_triggers_rebake(self):
        # 先按 5 烘 → 台顶与地板断成两块
        svc5 = self._svc(5)
        nav5 = svc5.bake("drop", force=True)
        self.assertGreater(nav5.component_count, 1)
        path = self.data_dir / "nav" / "drop.nav.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw["rule"]["max_down"], 5)

        # 换成 10 → 缓存规则对不上 → 自动重烘 → 接成一块
        svc10 = self._svc(10)
        nav10 = svc10.bake("drop")
        self.assertEqual(nav10.component_count, 1)
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(raw["rule"]["max_down"], 10)
        self.assertTrue(any("重烘" in m for m in self.log.infos), self.log.infos)

    def test_same_rule_reuses_cache(self):
        svc = self._svc(10)
        svc.bake("drop", force=True)
        before = len(self.log.infos)
        svc.bake("drop")
        # 规则没变 → 不该重烘
        self.assertEqual(len(self.log.infos), before)

    def test_default_rule_is_loose(self):
        # 默认必须比老规矩宽（老规矩 5 把大片区域切断了）
        svc = NavService(self.data_dir, self.log)
        self.assertEqual(svc.max_up, 1)
        self.assertGreaterEqual(svc.max_down, 8)


if __name__ == "__main__":
    unittest.main()
