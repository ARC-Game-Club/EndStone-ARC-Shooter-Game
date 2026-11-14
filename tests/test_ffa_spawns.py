# -*- coding: utf-8 -*-
"""个人死斗出生点池测试——最大连通域采样、间距、region 过滤、radius=0。

不连服务器：合成 blocks-v1 地形 → NavService 照正常运行路径烘焙，
再对 nav.spawns.compute_ffa_spawn_pool 做断言。
"""
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.nav.blocks_v1 import write_map  # noqa: E402
from endstone_arc_shooter_game.nav.navmap import NavService  # noqa: E402
from endstone_arc_shooter_game.nav.spawns import (  # noqa: E402
    compute_ffa_spawn_pool,
    largest_component_id,
    largest_component_nodes,
)


class _Log:
    def warning(self, msg):
        pass

    info = warning
    error = warning


def build_floor_map(path: Path, size: int = 12) -> None:
    """size×size 石地板（单一连通域）。"""
    columns = []
    for x in range(size):
        for z in range(size):
            columns.append((x, z, [{"y": 63, "name": "minecraft:stone"}]))
    write_map(path, map_id="floor", display_name="平地图",
              bounds=[0, size - 1, 60, 66, 0, size - 1], step=1,
              columns=columns, total_columns=size * size, unloaded_columns=0)


class FFASpawnPoolTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        maps_dir = self.data_dir / "nav" / "maps"
        maps_dir.mkdir(parents=True)
        build_floor_map(maps_dir / "floor.json")
        self.svc = NavService(self.data_dir, _Log())
        self.nav = self.svc.bake("floor")

    def tearDown(self):
        self._tmp.cleanup()

    def test_largest_component_covers_all_floor_nodes(self):
        comp = largest_component_id(self.nav.component)
        idx = largest_component_nodes(self.nav)
        self.assertEqual(len(idx), 12 * 12)
        self.assertEqual({self.nav.component[i] for i in idx}, {comp})

    def test_pool_points_spaced_inside_bounds(self):
        bounds = (0, 11, 60, 66, 0, 11)  # region_bounds 的 (x1,x2,y1,y2,z1,z2)
        pool = compute_ffa_spawn_pool(
            self.nav, bounds, min_spacing=4.0, max_points=64, seed=42
        )
        self.assertTrue(pool)
        r2 = 4.0 * 4.0
        for i, a in enumerate(pool):
            # 节点列全部落在收缩 2 格后的 region 内（x/z 带 +0.5 方块中心偏移）
            self.assertGreaterEqual(a["x"], 2.0)
            self.assertLessEqual(a["x"], 9.5)
            self.assertGreaterEqual(a["z"], 2.0)
            self.assertLessEqual(a["z"], 9.5)
            # radius=0：pick_spawn 不再加抖动（防推进墙）
            self.assertEqual(a["radius"], 0)
            # 方块中心 + 合法脚位
            self.assertAlmostEqual(a["x"] % 1, 0.5)
            self.assertAlmostEqual(a["z"] % 1, 0.5)
            self.assertEqual(a["y"], 64)
            for b in pool[i + 1:]:
                dx = a["x"] - b["x"]
                dz = a["z"] - b["z"]
                self.assertGreaterEqual(dx * dx + dz * dz, r2,
                                        f"两点间距不足 4 格: {a} {b}")

    def test_pool_respects_max_points(self):
        pool = compute_ffa_spawn_pool(
            self.nav, None, min_spacing=2.0, max_points=10, seed=7
        )
        self.assertEqual(len(pool), 10)

    def test_pool_yaw_faces_region_centroid(self):
        pool = compute_ffa_spawn_pool(
            self.nav, None, min_spacing=6.0, max_points=4, seed=1
        )
        self.assertTrue(pool)
        # 候选节点是整张 12×12 图 → 水平质心 (5.5, 5.5)
        for spawn in pool:
            expected = math.degrees(
                math.atan2(-(5.5 - spawn["x"]), (5.5 - spawn["z"]))
            ) % 360.0
            self.assertAlmostEqual(spawn["yaw"], expected, delta=0.5)

    def test_pool_empty_when_no_nodes_in_region(self):
        # region 完全在图外 → 采不出点
        pool = compute_ffa_spawn_pool(
            self.nav, (100, 110, 60, 66, 100, 110), min_spacing=4.0, max_points=8
        )
        self.assertEqual(pool, [])

    def test_pool_from_navservice_like_plugin_path(self):
        # 插件真实路径：nav.ensure(map) → compute_ffa_spawn_pool(bounds)
        nav = self.svc.ensure("floor")
        pool = compute_ffa_spawn_pool(
            nav, (0, 11, 60, 66, 0, 11), min_spacing=3.0, max_points=16
        )
        self.assertLessEqual(len(pool), 16)
        self.assertTrue(pool)


if __name__ == "__main__":
    unittest.main()
