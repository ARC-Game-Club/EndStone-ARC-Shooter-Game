# -*- coding: utf-8 -*-
"""导航规则单元测试——合成微地图逐条断言（navlab test_rules 的移植）。

规则（服主 2026-11-03 定稿）：
  · 可站立：脚下实心（液体/装饰不算，树叶算）+ 头顶两格空气
  · 8 邻接有向边：上≤1 / 下≥-5 / 斜向防切角 / 下落净空走廊
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.nav.blocks_v1 import BlockMap  # noqa: E402
from endstone_arc_shooter_game.nav.graph import build_graph, label_components  # noqa: E402
from endstone_arc_shooter_game.nav.standable import (  # noqa: E402
    all_standables,
    column_standables,
)
from endstone_arc_shooter_game.nav import find_path  # noqa: E402


def mkmap(columns: dict, span: int = 6) -> BlockMap:
    return BlockMap(
        map_id="t", display_name="t", bounds=[0, span, 60, 80, 0, span],
        x_min=0, x_max=span, z_min=0, z_max=span, y_min=60, y_max=80,
        step=1, total_columns=len(columns), unloaded_columns=0,
        exported_at="", source_path="(synthetic)", columns=columns)


def floor(cells: dict, y: int = 64, block: str = "stone") -> dict:
    out = {}
    for (x, z), b in cells.items():
        if b is not None:
            out[(x, z)] = {y: b}
    return out


class StandableTests(unittest.TestCase):
    def test_flat(self):
        m = mkmap({(0, 0): {64: "stone"}})
        self.assertEqual(column_standables(m, 0, 0), [(65, "stone")])

    def test_one_air_above(self):
        # 一格高走廊：地板 63、天花板 65 → 脚 64 只有 1 格净空不可站；顶可站
        m = mkmap({(0, 0): {63: "stone", 65: "stone"}})
        self.assertEqual(column_standables(m, 0, 0), [(66, "stone")])

    def test_two_air_above(self):
        m = mkmap({(0, 0): {63: "stone", 66: "stone"}})
        self.assertEqual(column_standables(m, 0, 0),
                         [(64, "stone"), (67, "stone")])

    def test_water(self):
        m = mkmap({(0, 0): {63: "stone", 64: "water", 65: "water"}})
        self.assertEqual(column_standables(m, 0, 0), [])

    def test_water_surface(self):
        m = mkmap({(0, 0): {64: "water"}})
        self.assertEqual(column_standables(m, 0, 0), [])

    def test_decor_is_air(self):
        m = mkmap({(0, 0): {64: "stone", 65: "tallgrass"}})
        self.assertEqual(column_standables(m, 0, 0), [(65, "stone")])

    def test_leaves_support(self):
        m = mkmap({(0, 0): {64: "spruce_leaves"}})
        self.assertEqual(column_standables(m, 0, 0), [(65, "spruce_leaves")])

    def test_torch_no_support(self):
        m = mkmap({(0, 0): {64: "torch"}})
        self.assertEqual(column_standables(m, 0, 0), [])

    def test_solid_pillar_only_top(self):
        m = mkmap({(0, 0): {y: "stone" for y in range(64, 68)}})
        self.assertEqual(column_standables(m, 0, 0), [(68, "stone")])


class EdgeRuleTests(unittest.TestCase):
    def _two_col(self, ha: int, hb: int):
        m = mkmap({(0, 0): {ha: "stone"}, (1, 0): {hb: "stone"}})
        sts = all_standables(m)
        g = build_graph(m, [p for p, _ in sts], [n for _, n in sts])
        idx = g.node_index()
        return g, idx, (0, ha + 1, 0), (1, hb + 1, 0)

    @staticmethod
    def _linked(g, idx, a, b) -> bool:
        return (a in idx and b in idx
                and idx[b] in g.neighbors_of(idx[a]))

    def test_flat(self):
        g, idx, a, b = self._two_col(64, 64)
        self.assertTrue(self._linked(g, idx, a, b))
        self.assertTrue(self._linked(g, idx, b, a))

    def test_up1_jump(self):
        g, idx, a, b = self._two_col(64, 65)
        self.assertTrue(self._linked(g, idx, a, b))
        self.assertTrue(self._linked(g, idx, b, a))

    def test_up2_forbidden_down_ok(self):
        # 上 2 爬不上去；但高柱能往下跳 2（有向性）
        g, idx, a, b = self._two_col(64, 66)
        self.assertFalse(self._linked(g, idx, a, b))
        self.assertTrue(self._linked(g, idx, b, a))

    def test_down5_ok_down6_no(self):
        g, idx, a, b = self._two_col(65, 60)
        self.assertTrue(self._linked(g, idx, a, b))
        g, idx, a, b = self._two_col(65, 59)
        self.assertFalse(self._linked(g, idx, a, b))

    def test_drop_corridor_blocked(self):
        # 落差 5 但目标列 63 有实体挡道：底面(脚61)应孤立（挡板自身是合法落脚点）
        m = mkmap({(0, 0): {65: "stone"},
                   (1, 0): {60: "stone", 63: "stone"}})
        sts = all_standables(m)
        g = build_graph(m, [p for p, _ in sts], [n for _, n in sts])
        idx = g.node_index()
        self.assertIn((1, 64, 0), idx)
        self.assertEqual(g.degree(idx[(1, 61, 0)]), 0)
        self.assertEqual(g.targets.count(idx[(1, 61, 0)]), 0)

    def test_high_blocker_irrelevant(self):
        # 头顶之上的挡板不挡下落
        m = mkmap({(0, 0): {65: "stone"},
                   (1, 0): {60: "stone", 68: "stone"}})
        sts = all_standables(m)
        g = build_graph(m, [p for p, _ in sts], [n for _, n in sts])
        idx = g.node_index()
        self.assertGreater(g.targets.count(idx[(1, 61, 0)]), 0)


class DiagonalTests(unittest.TestCase):
    def _graph(self, extra: dict):
        cells = {(x, z): "stone" for x in range(3) for z in range(3)}
        cols = floor(cells)
        for k, v in extra.items():
            cols.setdefault(k, {}).update(v)
        m = mkmap(cols)
        sts = all_standables(m)
        g = build_graph(m, [p for p, _ in sts], [n for _, n in sts])
        return g, g.node_index()

    def test_flat_diagonal(self):
        g, idx = self._graph({})
        self.assertIn(idx[(1, 65, 1)], g.neighbors_of(idx[(0, 65, 0)]))

    def test_corner_blocked(self):
        # 角列 (1,0) 升起两格墙 → 斜边被禁，但直行边仍在
        g, idx = self._graph({(1, 0): {66: "stone", 67: "stone"}})
        self.assertNotIn(idx[(1, 65, 1)], g.neighbors_of(idx[(0, 65, 0)]))
        self.assertIn(idx[(0, 65, 1)], g.neighbors_of(idx[(0, 65, 0)]))


class AstarTests(unittest.TestCase):
    def test_wall_detour(self):
        # 两格高墙（一格的墙按规则就能跳上去），路径必须绕门
        cols = {}
        for x in range(5):
            for z in range(5):
                cols[(x, z)] = {64: "stone"}
        for z in range(4):
            cols[(2, z)][65] = "stone"
            cols[(2, z)][66] = "stone"
        m = mkmap(cols)
        sts = all_standables(m)
        g = build_graph(m, [p for p, _ in sts], [n for _, n in sts])
        label_components(g)
        path = find_path(g, (0, 65, 0), (4, 65, 0))
        self.assertIsNotNone(path)
        self.assertEqual(path[0], (0, 65, 0))
        self.assertEqual(path[-1], (4, 65, 0))
        self.assertTrue((2, 65, 4) in path or (3, 65, 4) in path)
        for p, q in zip(path, path[1:]):
            self.assertEqual(max(abs(q[0] - p[0]), abs(q[2] - p[2])), 1)
            self.assertLessEqual(q[1] - p[1], 1)
            self.assertLessEqual(p[1] - q[1], 5)
        for p in path:
            self.assertFalse(p[0] == 2 and p[2] < 4 and p[1] == 67)


if __name__ == "__main__":
    unittest.main()


class SlabHeightTests(unittest.TestCase):
    """半高度支撑（2026-11-03 枪战服卡点）：底半砖/正楼梯脚位 = Y+0.5。"""

    def _map(self, columns, span=3):
        return mkmap(columns, span)

    def test_bottom_slab_foot_half(self):
        m = self._map({(0, 0): {64: "brick_slab"}})
        st = column_standables(m, 0, 0)
        # col_states 没有状态时按 bottom（缺省）→ 脚位 64.5
        self.assertEqual(st, [(64.5, "brick_slab")])

    def test_top_slab_foot_full(self):
        m = self._map({(0, 0): {64: "brick_slab"}})
        m.col_states[(0, 0)] = {64: {"vertical_half": "top"}}
        self.assertEqual(column_standables(m, 0, 0), [(65.0, "brick_slab")])

    def test_double_slab_foot_full(self):
        m = self._map({(0, 0): {64: "brick_double_slab"}})
        self.assertEqual(column_standables(m, 0, 0), [(65.0, "brick_double_slab")])

    def test_upright_stairs_half(self):
        m = self._map({(0, 0): {64: "birch_stairs"}})
        self.assertEqual(column_standables(m, 0, 0), [(64.5, "birch_stairs")])

    def test_upside_down_stairs_full(self):
        m = self._map({(0, 0): {64: "birch_stairs"}})
        m.col_states[(0, 0)] = {64: {"upside_down_bit": True}}
        self.assertEqual(column_standables(m, 0, 0), [(65.0, "birch_stairs")])

    def test_slab_to_full_half_step_edge(self):
        # 半砖(64.5) ↔ 整块(65.0)：dy=±0.5，双向都该连边
        m = self._map({(0, 0): {64: "brick_slab"}, (1, 0): {64: "stone"}})
        sts = all_standables(m)
        g = build_graph(m, [p for p, _ in sts], [n for _, n in sts])
        idx = g.node_index()
        a, b = idx[(0, 64.5, 0)], idx[(1, 65.0, 0)]
        self.assertIn(b, g.neighbors_of(a))
        self.assertIn(a, g.neighbors_of(b))
