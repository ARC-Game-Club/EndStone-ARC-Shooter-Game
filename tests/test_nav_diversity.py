# -*- coding: utf-8 -*-
"""路径多样性测试——抖动 + 拥堵热度（2026-11-18 服主："别全走同一条最短路"）。

菱形图：S 和 T 之间两条等长支路（z=0 / z=2，中间 2 高墙隔断）。
确定性 A* 永远走同一条；抖动让它每次略有不同，热度让后到的人换道。
"""

import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.nav import navmap  # noqa: E402
from endstone_arc_shooter_game.nav.astar import astar  # noqa: E402
from endstone_arc_shooter_game.nav.blocks_v1 import write_map  # noqa: E402
from endstone_arc_shooter_game.nav.navmap import NavService  # noqa: E402


class _Log:
    def warning(self, msg):
        pass

    info = warning
    error = warning


def build_diamond_map(path: Path) -> None:
    """S(0,z=1) → T(4,z=1)，两条等长支路 z=0 / z=2，中段 2 高墙隔断。

    每条支路 6 步直线，无对角线——对称菱形，确定性 A* 必然固定走一条。
    中段墙必须 2 格高（y64+y65）：只加 1 格的话墙顶 y65 可站，从 y64
    跳 +1 就上去了，中道反而比两条支路更短（首跑就踩过这个坑）。
    """
    columns = []
    walls = {(1, 1), (2, 1), (3, 1)}
    for x in range(5):
        for z in range(3):
            blocks = [{"y": 63, "name": "minecraft:stone"}]
            if (x, z) in walls:
                blocks += [{"y": 64, "name": "minecraft:stone"},
                           {"y": 65, "name": "minecraft:stone"}]
            columns.append((x, z, blocks))
    write_map(path, map_id="diamond", display_name="菱形图",
              bounds=[0, 4, 62, 66, 0, 2], step=1, columns=columns,
              total_columns=15, unloaded_columns=0)


class NavDiversityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        data_dir = Path(self._tmp.name)
        maps_dir = data_dir / "nav" / "maps"
        maps_dir.mkdir(parents=True)
        build_diamond_map(maps_dir / "diamond.json")
        self.svc = NavService(data_dir, _Log())
        self.start = (0.5, 64.0, 1.5)
        self.goal = (4.5, 64.0, 1.5)

    def tearDown(self):
        self._tmp.cleanup()

    # ---- helpers ----

    def _lane_of(self, path):
        """取支路方向：离开 S 后的第一个点的 z（0=下道，2=上道）。"""
        z = path[1][2]
        self.assertIn(z, (0, 2), f"路径脱轨: {path}")
        return int(z)

    def _query(self, requester):
        res = self.svc.query("diamond", self.start, self.goal,
                             requester=requester)
        self.assertTrue(res.get("ok"), res.get("text"))
        return res["path"]

    # ---- 用例 ----

    def test_plain_astar_is_deterministic(self):
        """无钩子的 astar 回归：同图同起终点两次结果完全一致。"""
        nav = self.svc.ensure("diamond")
        s = self.svc.snap(nav, self.start)
        t = self.svc.snap(nav, self.goal)
        p1 = astar(nav, s, t)
        p2 = astar(nav, s, t)
        self.assertEqual(p1, p2)

    def test_jitter_gives_both_lanes(self):
        """抖动：同一个请求者反复问，两条支路都会被走到。"""
        lanes = {self._lane_of(self._query("A")) for _ in range(30)}
        self.assertEqual(lanes, {0, 2},
                         f"30 次查询只走了一条支路: {lanes}")

    def test_heat_diverts_other_bot(self):
        """热度：A 走过的走廊，紧随其后的 B 换另一条（惩罚 8 ≫ 抖动 1.5）。"""
        lane_a = self._lane_of(self._query("A"))
        lane_b = self._lane_of(self._query("B"))
        self.assertNotEqual(lane_a, lane_b)
        # C 紧随其后：两条都被占了热度 → 依然要在两道里选一条
        lane_c = self._lane_of(self._query("C"))
        self.assertIn(lane_c, (0, 2))

    def test_own_heat_invisible(self):
        """自己的热度对自己不可见：惩罚钩子对本人恒 0。"""
        self._query("A")
        heat = self.svc._heat["diamond"]
        self.assertTrue(heat)
        now = time.monotonic()
        penalty_a = self.svc._make_penalty(heat, now, "A")
        penalty_b = self.svc._make_penalty(heat, now, "B")
        for node in heat:
            self.assertEqual(penalty_a(node), 0.0)
            self.assertGreater(penalty_b(node), 0.0)

    def test_heat_expires(self):
        """TTL 过后热度归零：走廊冷却，重新变回可行。"""
        self._query("A")
        heat = self.svc._heat["diamond"]
        now = time.monotonic()
        stale = self.svc._make_penalty(heat, now + navmap.NAV_HEAT_TTL + 1, "B")
        for node in list(heat):
            self.assertEqual(stale(node), 0.0)

    def test_astar_node_penalty_forces_other_lane(self):
        """astar 的 node_penalty 钩子：给下道全线加价 → 走上道。"""
        nav = self.svc.ensure("diamond")
        s = self.svc.snap(nav, self.start)
        t = self.svc.snap(nav, self.goal)
        p = astar(nav, s, t, node_penalty=lambda n: 5.0
                  if nav.nodes[n][2] == 0 else 0.0)
        zs = {nav.nodes[i][2] for i in p}
        self.assertNotIn(0, zs)


if __name__ == "__main__":
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(NavDiversityTests),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f"全部 {result.testsRun} 项通过")
    raise SystemExit(0 if result.wasSuccessful() else 1)
