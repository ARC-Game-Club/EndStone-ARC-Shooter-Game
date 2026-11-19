# -*- coding: utf-8 -*-
"""死斗复活点按「强连通域（互相可达）」采样（2026-11-19）。

背景：服主问"死斗怎么老复活在房顶上，这些地方真的是最大连通域吗"。
核查结论（炼狱小镇实测）：

    弱连通（代码原来用的，忽略边方向）：152 块，最大 42348 节点（89.2%），
        其中 34% 的节点在 y≥69 —— 屋顶平台被"单向落差边"算进了主城区。
    强连通（互相可达）：604 块，最大 16735 节点（35.3%），全是街道层。
    现有 64 个复活点里 35 个落在主城区之外的小块（屋顶各自成块，61~707 节点）。

所以这里把三件事钉死：
  1. 弱连通会把"只能往下跳、爬不回去"的平台并进主城区；
  2. 强连通把它们分开；
  3. 复活点按强连通采样 → 不会再刷到单向可达的屋顶平台上。
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
from endstone_arc_shooter_game.nav.spawns import (  # noqa: E402
    MODE_SCC,
    MODE_WEAK,
    compute_ffa_spawn_pool,
    compute_ffa_spawn_pool_ex,
    largest_component_nodes,
    largest_scc_nodes,
)


class _Log:
    def warning(self, msg):
        pass

    info = warning
    error = warning


def build_one_way_map(path: Path, size: int = 12, plat: int = 4,
                      plat_dy: int = 7) -> None:
    """平地 + 一块只能往下掉、爬不回去的高台。

    - 平地：size×size，块在 y=63 → 站立面 y=64
    - 高台：紧贴平地北侧的 plat×plat，块在 y=70 → 站立面 y=71
      （高 7 格：往下掉 7 格合法（max_down=10），往上爬 7 格不可能
       （max_up=1）→ 两个方向**不互为可达**）
    """
    columns = []
    for x in range(size):
        for z in range(size):
            columns.append((x, z, [{"y": 63, "name": "minecraft:stone"}]))
    top = 63 + plat_dy
    for x in range(plat):
        for z in range(size, size + plat):
            columns.append((x, z, [{"y": top, "name": "minecraft:stone"}]))
    write_map(path, map_id="oneway", display_name="单向高台",
              bounds=[0, size + plat - 1, 60, 80, 0, size + plat - 1], step=1,
              columns=columns, total_columns=len(columns), unloaded_columns=0)


class StrongConnectivityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        maps_dir = self.data_dir / "nav" / "maps"
        maps_dir.mkdir(parents=True)
        build_one_way_map(maps_dir / "oneway.json")
        self.svc = NavService(self.data_dir, _Log())
        self.nav = self.svc.bake("oneway")
        self.plateau_y = 71.0
        self.floor_y = 64.0

    def tearDown(self):
        self._tmp.cleanup()

    # ---------------------------------------------------------------- 基础
    def test_weak_connectivity_merges_the_one_way_plateau(self):
        """弱连通：单向落差边把高台并进了主城区（这就是刷到房顶的根因）。"""
        weak = largest_component_nodes(self.nav)
        self.assertEqual(len(weak), 12 * 12 + 4 * 4)
        ys = {self.nav.nodes[i][1] for i in weak}
        self.assertIn(self.floor_y, ys)
        self.assertIn(self.plateau_y, ys)

    def test_strong_connectivity_separates_the_one_way_plateau(self):
        """强连通：高台爬不回去 → 各自成块。"""
        self.assertGreaterEqual(self.nav.scc_count, 2)
        strong = largest_scc_nodes(self.nav)
        self.assertEqual(len(strong), 12 * 12)
        ys = {self.nav.nodes[i][1] for i in strong}
        self.assertIn(self.floor_y, ys)
        self.assertNotIn(self.plateau_y, ys)

    def test_nav_file_contains_scc(self):
        path = self.data_dir / "nav" / "oneway.nav.json"
        self.assertTrue(path.exists())
        raw = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("scc", raw)
        self.assertEqual(len(raw["scc"]), len(raw["nodes"]))
        self.assertEqual(raw["stats"]["scc_components"], self.nav.scc_count)

    # ---------------------------------------------------------------- 采样
    def test_pool_from_strong_component_skips_the_plateau(self):
        """按强连通采样 → 复活点全在平地，高台一个都不刷。"""
        pool, mode = compute_ffa_spawn_pool_ex(
            self.nav, (0, 15, 60, 80, 0, 15), min_spacing=4.0, max_points=64,
            seed=11,
        )
        self.assertEqual(mode, MODE_SCC)
        self.assertTrue(pool)
        for spawn in pool:
            self.assertNotAlmostEqual(spawn["y"], self.plateau_y, places=3)

    def test_pool_weak_mode_can_reach_the_plateau(self):
        """退回弱连通（老缓存无强连通数据时的退路）→ 高台又会刷到。"""
        pool, mode = compute_ffa_spawn_pool_ex(
            self.nav, (0, 15, 60, 80, 0, 15), min_spacing=1.0, max_points=200,
            seed=11, strict=False,
        )
        self.assertEqual(mode, MODE_WEAK)
        self.assertTrue(any(abs(s["y"] - self.plateau_y) < 0.01 for s in pool))

    def test_pool_falls_back_to_weak_when_nav_has_no_scc(self):
        """没有强连通数据的老 nav 对象 → 自动退回弱连通，不采不出点。"""
        class _NoScc:
            def __init__(self, nav):
                self.nodes = nav.nodes
                self.component = nav.component

        pool, mode = compute_ffa_spawn_pool_ex(
            _NoScc(self.nav), (0, 15, 60, 80, 0, 15), min_spacing=4.0,
            max_points=64, seed=3,
        )
        self.assertEqual(mode, MODE_WEAK)
        self.assertTrue(pool)

    def test_compat_wrapper_still_returns_list(self):
        pool = compute_ffa_spawn_pool(
            self.nav, (0, 15, 60, 80, 0, 15), min_spacing=4.0, max_points=16,
            seed=5,
        )
        self.assertIsInstance(pool, list)
        self.assertTrue(pool)
        # 12×12 平地放不下 16 个间距 4 的点（贪心采样自然收不满）
        self.assertLessEqual(len(pool), 16)

    def test_old_nav_file_without_scc_is_recomputed_not_invalidated(self):
        """老烘焙产物（没有 scc 字段）→ 现场从边算强连通，不作废缓存。"""
        path = self.data_dir / "nav" / "oneway.nav.json"
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("scc", None)
        path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")

        svc2 = NavService(self.data_dir, _Log())
        nav2 = svc2.bake("oneway")
        self.assertTrue(nav2.scc)
        self.assertGreaterEqual(nav2.scc_count, 2)
        strong = largest_scc_nodes(nav2)
        self.assertEqual(len(strong), 12 * 12)


if __name__ == "__main__":
    unittest.main()
