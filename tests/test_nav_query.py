# -*- coding: utf-8 -*-
"""NavService 测试——烘焙/查询/吸附/出生点连通（临时目录 + 合成图）。

不连服务器：BlockMap 数据用 blocks_v1.write_map 写进临时目录，NavService
照正常运行路径加载烘焙。
"""
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
    def warning(self, msg):
        pass

    info = warning
    error = warning


def build_synthetic_map(path: Path) -> None:
    """5×5 石地板 + (4,4) 上 2 格高瞭望台（顶可站但爬不上去）。"""
    columns = []
    for x in range(5):
        for z in range(5):
            blocks = [{"y": 63, "name": "minecraft:stone"}]
            if (x, z) == (4, 4):
                blocks += [{"y": 64, "name": "minecraft:stone"},
                           {"y": 65, "name": "minecraft:stone"}]
            columns.append((x, z, blocks))
    write_map(path, map_id="mini", display_name="迷你图",
              bounds=[0, 4, 60, 66, 0, 4], step=1, columns=columns,
              total_columns=25, unloaded_columns=0)


class NavServiceTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        maps_dir = self.data_dir / "nav" / "maps"
        maps_dir.mkdir(parents=True)
        build_synthetic_map(maps_dir / "mini.json")
        self.svc = NavService(self.data_dir, _Log())

    def tearDown(self):
        self._tmp.cleanup()

    def test_bake_and_query(self):
        nav = self.svc.bake("mini")
        # 24 地板（瞭望台那列的地板面被塔身占了）+ 塔顶 1 = 25 站立点
        self.assertEqual(nav.stats["standables"], 25)
        res = self.svc.query("mini", (0, 64, 0), (4, 64, 3))
        self.assertTrue(res["ok"], res["text"])
        self.assertEqual(res["path"][0], [0, 64, 0])
        self.assertEqual(res["path"][-1], [4, 64, 3])

    def test_snap_slab_ceiling(self):
        # 半砖脚位 y=64.5 → 吸附取上整 65？本图没有 65 面的列 →
        # 用 (0, 64.5, 0)：吸附应回落到本列 64
        nav = self.svc.ensure("mini")
        i = self.svc.snap(nav, (0.2, 64.5, 0.2))
        self.assertIsNotNone(i)
        self.assertEqual(nav.nodes[i], (0, 64, 0))

    def test_tower_unreachable(self):
        # 瞭望台顶 (4,66,4) 上 2 爬不上去 → 从地面不可达
        res = self.svc.query("mini", (0, 64, 0), (4, 66.9, 4))
        self.assertFalse(res["ok"])

    def test_spawn_check_ok(self):
        res = self.svc.spawn_check("mini", [
            ("A1", 0.5, 64.0, 0.5), ("A2", 0.5, 64.0, 4.5),
            ("B1", 4.5, 64.0, 0.5),
        ])
        self.assertTrue(res["ok"], res["text"])
        self.assertIn("全部双向可达", res["text"])

    def test_spawn_check_isolated(self):
        # 瞭望台顶当出生点：单向（下得来上不去）→ 报问题
        res = self.svc.spawn_check("mini", [
            ("A1", 0.5, 64.0, 0.5), ("T1", 4.5, 66.0, 4.5),
        ])
        self.assertFalse(res["ok"])
        # T1 → A1 可达（跳下来），A1 → T1 不可达 → 两类问题各一
        self.assertTrue(res["oneway"] or res["unreachable"])

    def test_status_and_has_blocks(self):
        self.assertTrue(self.svc.has_blocks("mini"))
        st = self.svc.status("mini")
        self.assertTrue(st["ok"])
        self.assertEqual(st["maps"][0]["state"], "有地形未烘焙")
        self.svc.bake("mini")
        st = self.svc.status("mini")
        self.assertEqual(st["maps"][0]["state"], "已烘焙")

    def test_query_missing_map(self):
        res = self.svc.query("nope", (0, 64, 0), (1, 64, 0))
        self.assertFalse(res["ok"])

    def test_nav_file_roundtrip(self):
        # 烘焙 → 清缓存 → 从 nav.json 恢复，查询结果一致
        self.svc.bake("mini")
        self.svc._cache.clear()
        res = self.svc.query("mini", (0, 64, 0), (4, 64, 3))
        self.assertTrue(res["ok"])
        self.assertEqual(res["path"][-1], [4, 64, 3])


if __name__ == "__main__":
    unittest.main()
