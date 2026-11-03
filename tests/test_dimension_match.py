# -*- coding: utf-8 -*-
"""维度名归一 + 按起点定位地图（2026-11-03 假人导航卡死的回归测试）。

背景：地图在 DB 里存 ``'Overworld'``（建图时从 location.dimension.id 抄的），
调用方给的是 ``'overworld'`` / ``'minecraft:overworld'``。原来
``find_maps_at_point`` 大小写敏感地直接比字符串 → 一张图都匹配不上 →
``api_request_path`` 回"起点不在任何已导出的地图里" → 假人拿不到路径，
原地罚站（日志里全是"arena 卡死 … 本段已走 0.0 格"）。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.config import (  # noqa: E402
    find_maps_at_point,
    normalize_dimension_name,
    normalize_map,
)


def _map(map_id="harbor", dimension="Overworld"):
    return normalize_map({
        "id": map_id,
        "display_name": "港口-装卸货场",
        "dimension": dimension,
        "region": {
            "pos1": {"x": -1028.47, "y": 63.0, "z": 1030.52},
            "pos2": {"x": -971.46, "y": 80.0, "z": 972.40},
        },
        "modes": [],
    })


class DimensionNormalizeTests(unittest.TestCase):
    def test_strips_prefix_and_lowercases(self):
        for raw in ("overworld", "Overworld", "OVERWORLD",
                    "minecraft:overworld", "minecraft:Overworld", " Overworld "):
            self.assertEqual(normalize_dimension_name(raw), "overworld", raw)

    def test_empty_defaults_to_overworld(self):
        for raw in ("", None, "   "):
            self.assertEqual(normalize_dimension_name(raw), "overworld", raw)

    def test_other_dimensions(self):
        self.assertEqual(normalize_dimension_name("minecraft:the_nether"), "the_nether")
        self.assertEqual(normalize_dimension_name("Nether"), "nether")


class FindMapsAtPointTests(unittest.TestCase):
    def setUp(self):
        self.maps = {"harbor": _map()}

    def test_dimension_spellings_all_match(self):
        for dim in ("overworld", "Overworld", "minecraft:overworld"):
            hits = find_maps_at_point(self.maps, -1000.7, 64.5, 996.9, dim)
            self.assertEqual([h["id"] for h in hits], ["harbor"], dim)

    def test_other_dimension_does_not_match(self):
        hits = find_maps_at_point(self.maps, -1000.7, 64.5, 996.9, "nether")
        self.assertEqual(hits, [])

    def test_point_outside_region(self):
        hits = find_maps_at_point(self.maps, 1084.5, 60.0, 965.1, "overworld")
        self.assertEqual(hits, [])


if __name__ == "__main__":
    unittest.main()
