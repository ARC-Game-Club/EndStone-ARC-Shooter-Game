# -*- coding: utf-8 -*-
"""不可达原因分类测试（2026-11-18）。

背景：服主问"怎么经常不可达了，是不是多样性寻路有问题"。实测**不是**——
两张图的连通分量本来就断成好几块（炼狱小镇 47467 节点 / 258 个分量，
最大一块只占 78.4%），而且"超预算"和"真不可达"以前共用一句文案，
把排查带偏了。

这里把三件事钉死：
  1. A* 能说清失败原因（ok / budget / unreachable）；
  2. NavService.query() 把"不可达"分成三类并带分量编号；
  3. api_nav_status 暴露孤岛节点数。
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.nav import navmap as navmap_mod  # noqa: E402
from endstone_arc_shooter_game.nav.astar import astar  # noqa: E402
from endstone_arc_shooter_game.nav.graph import NavGraph  # noqa: E402
from endstone_arc_shooter_game.nav.navmap import NavService  # noqa: E402


class _Log:
    def warning(self, msg):
        pass

    info = warning
    error = warning


def write_nav(path: Path, map_id: str, nodes, offsets, targets, component) -> None:
    """手写一张 nav-v1 图（绕开 blocks-v1，直接给节点/边/分量）。"""
    payload = {
        "format": "nav-v1", "map_id": map_id,
        "baked_at": "2026-11-18T00:00:00",
        "source_exported_at": "2026-11-18T00:00:00",
        "rule": {"max_up": 1, "max_down": 5, "neighbors": 8},
        "nodes": [list(n) for n in nodes],
        "grounds": ["stone"] * len(nodes),
        "edges": {"offsets": list(offsets), "targets": list(targets)},
        "component": list(component),
        "stats": {"standables": len(nodes)},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


class AStarReasonTests(unittest.TestCase):
    """A* 自身的失败原因。"""

    def _graph(self):
        # 0 → 1 单向边（1 没有出边）
        g = NavGraph(nodes=[(0, 64, 0), (1, 64, 1)], grounds=["stone", "stone"],
                     offsets=[0, 1, 1], targets=[1], component=[0, 0])
        return g

    def test_ok_reason(self):
        st = {}
        p = astar(self._graph(), 0, 1, stats=st)
        self.assertIsNotNone(p)
        self.assertEqual(st["reason"], "ok")
        self.assertGreaterEqual(st["expansions"], 1)

    def test_unreachable_reason(self):
        st = {}
        p = astar(self._graph(), 1, 0, stats=st)
        self.assertIsNone(p)
        self.assertEqual(st["reason"], "unreachable")
        self.assertEqual(st["expansions"], 1)

    def test_budget_reason(self):
        st = {}
        p = astar(self._graph(), 0, 1, max_expansions=0, stats=st)
        self.assertIsNone(p)
        self.assertEqual(st["reason"], "budget")

    def test_no_stats_param_keeps_legacy_behaviour(self):
        # 不传 stats 的老调用方式照旧：None / 路径
        self.assertIsNone(astar(self._graph(), 1, 0))
        self.assertIsNotNone(astar(self._graph(), 0, 1))

    def test_start_equals_goal(self):
        st = {}
        p = astar(self._graph(), 0, 0, stats=st)
        self.assertEqual(p, [0])
        self.assertEqual(st["reason"], "ok")


class UnreachableReasonTests(unittest.TestCase):
    """NavService.query() 的三类失败原因 + 孤岛统计。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmp.name)
        self.svc = NavService(self.data_dir, _Log())
        self.nav_dir = self.data_dir / "nav"

    def tearDown(self):
        self._tmp.cleanup()

    def _two_islands(self):
        # 两块毫无关系的孤岛：分量 0 / 分量 1
        write_nav(self.nav_dir / "isles.nav.json", "isles",
                  nodes=[(0, 64, 0), (5, 64, 5)],
                  offsets=[0, 0, 0], targets=[], component=[0, 1])

    def _one_way(self):
        # 同一分量，但边是单向的：0 → 1（1 没有出边）
        write_nav(self.nav_dir / "oneway.nav.json", "oneway",
                  nodes=[(0, 64, 0), (1, 64, 1)],
                  offsets=[0, 1, 1], targets=[1], component=[7, 7])

    def test_component_split(self):
        self._two_islands()
        res = self.svc.query("isles", (0, 64, 0), (5, 64, 5))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "component_split")
        self.assertNotEqual(res["start_component"], res["goal_component"])
        self.assertIn("连通分量", res["text"])
        # 旧的那句笼统文案不许再出现
        self.assertNotIn("分量断开或只有单向跳崖边", res["text"])

    def test_one_way(self):
        self._one_way()
        # 反向走不通（1 → 0）
        res = self.svc.query("oneway", (1, 64, 1), (0, 64, 0))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "oneway")
        self.assertEqual(res["start_component"], res["goal_component"])
        self.assertIn("单向", res["text"])
        # 正向走得通
        ok = self.svc.query("oneway", (0, 64, 0), (1, 64, 1))
        self.assertTrue(ok["ok"], ok["text"])
        self.assertEqual(len(ok["path"]), 2)

    def test_budget(self):
        self._one_way()
        with patch.object(navmap_mod, "DEFAULT_MAX_EXPANSIONS", 0):
            res = self.svc.query("oneway", (0, 64, 0), (1, 64, 1))
        self.assertFalse(res["ok"])
        self.assertEqual(res["reason"], "budget")
        self.assertIn("展开超预算", res["text"])

    def test_failure_payload_has_structured_fields(self):
        self._two_islands()
        res = self.svc.query("isles", (0, 64, 0), (5, 64, 5))
        for key in ("reason", "start_component", "goal_component",
                    "start_node", "goal_node", "expansions"):
            self.assertIn(key, res)
        self.assertEqual(res["start_node"], [0, 64, 0])
        self.assertEqual(res["goal_node"], [5, 64, 5])

    def test_status_exposes_islands(self):
        self._two_islands()
        self.svc.bake("isles")
        st = self.svc.status("isles")
        self.assertTrue(st["ok"])
        info = st["maps"][0]
        self.assertEqual(info["components"], 2)
        self.assertEqual(info["island_nodes"], 1)
        self.assertEqual(info["island_pct"], 50.0)
        # top_components = [(分量号, 节点数), ...]，按大小降序
        self.assertEqual(len(info["top_components"]), 2)
        self.assertEqual(sorted(c for c, _n in info["top_components"]), [0, 1])


if __name__ == "__main__":
    unittest.main()
