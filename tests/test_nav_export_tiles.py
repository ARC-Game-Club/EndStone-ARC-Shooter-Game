# -*- coding: utf-8 -*-
"""导出器纯逻辑测试——切块、自适应预算、blocks-v1 落盘（不连服务器）。

 tickingarea/维度交互靠 Mock 维度对象：get_block_at 返回合成方块。
"""
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.nav.exporter import (  # noqa: E402
    TickingAreaMapExporter,
    split_tiles,
)
from endstone_arc_shooter_game.nav.blocks_v1 import load_map  # noqa: E402


class SplitTilesTests(unittest.TestCase):
    def test_exact(self):
        tiles = split_tiles(0, 63, 100, 163)
        self.assertEqual(len(tiles), 1)
        self.assertEqual(tiles[0], {"x1": 0, "x2": 63, "z1": 100, "z2": 163})

    def test_two_by_one(self):
        tiles = split_tiles(0, 100, 0, 30, tile=64)
        self.assertEqual(len(tiles), 2)
        self.assertEqual(tiles[0]["x1"], 0)
        self.assertEqual(tiles[0]["x2"], 63)
        self.assertEqual(tiles[1]["x1"], 64)
        self.assertEqual(tiles[1]["x2"], 100)

    def test_big_region(self):
        # 炼狱小镇量级 194×190 → 4×3=12 块
        tiles = split_tiles(906, 1100, 912, 1101)
        self.assertEqual(len(tiles), 12)
        for t in tiles:
            self.assertLessEqual(t["x2"] - t["x1"] + 1, 64)
            self.assertLessEqual(t["z2"] - t["z1"] + 1, 64)


class _FakeBlock:
    def __init__(self, name):
        self.type = name
        self.data = None


class _FakeDimension:
    """x+z 为偶数的列有地板(y=63)，其余全空。"""

    def get_block_at(self, x, y, z):
        return _FakeBlock("minecraft:stone") if (
            (x + z) % 2 == 0 and y == 63) else _FakeBlock("minecraft:air")


class _FakeServer:
    def __init__(self):
        self.commands = []

    def dispatch_command(self, sender, cmd):
        self.commands.append(cmd)


class _FakePlugin:
    def __init__(self):
        self.server = SimpleNamespace(command_sender="console",
                                      get_dimension=None)
        self.server = self.server
        self.server = type("S", (), {
            "command_sender": "console",
            "dispatch_command": self._dispatch,
        })()
        self.logger = SimpleNamespace(
            info=lambda *a, **k: None, warning=lambda *a, **k: None)
        self._cmds = []

    def _dispatch(self, sender, cmd):
        self._cmds.append(cmd)


class ExporterTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.plugin = _FakePlugin()
        self.out_dir = Path(self._tmp.name) / "nav"
        self.done = []
        self.exp = TickingAreaMapExporter(
            self.plugin, self.out_dir, on_done=lambda mid, ok, d: self.done.append((mid, ok, d)))

    def tearDown(self):
        self._tmp.cleanup()

    def _run_to_completion(self, max_ticks: int = 5000):
        ok = self.exp.start("mini", "迷你", _FakeDimension(),
                            [0, 10, 60, 70, 0, 10],
                            y_pad_below=1, y_pad_above=1)
        self.assertTrue(ok)
        for _ in range(max_ticks):
            st = self.exp.tick()
            if st and st.get("done"):
                return st
        self.fail("导出没在预算 tick 数内完成")

    def test_full_export(self):
        st = self._run_to_completion()
        self.assertTrue(st["done"])
        self.assertEqual(st["unloaded"], 0)
        # on_done 回调触发且成功
        self.assertEqual(len(self.done), 1)
        self.assertTrue(self.done[0][1])
        # 落盘的 blocks-v1 能读回来，且偶数列有 stone
        bmap = load_map(self.out_dir / "maps" / "mini.json")
        self.assertEqual(bmap.map_id, "mini")
        self.assertIn("stone", bmap.columns[(0, 0)].values())
        self.assertNotIn((1, 0), bmap.columns)
        # tickingarea 加了也删了
        adds = [c for c in self.plugin._cmds if c.startswith("tickingarea add")]
        removes = [c for c in self.plugin._cmds if c.startswith("tickingarea remove")]
        self.assertTrue(adds)
        self.assertEqual(len(adds), len(removes))
        # 名字必须是 BDS 命令安全的（ASCII 无空格）
        for c in adds:
            name = c.split()[-1]
            self.assertTrue(name.isascii() and " " not in name, name)

    def test_start_rejects_bad_bounds(self):
        self.assertFalse(self.exp.start("mini", "m", _FakeDimension(), [5, 0, 60, 70, 0, 10]))
        self.assertFalse(self.exp.start("mini", "m", None, [0, 10, 60, 70, 0, 10]))

    def test_busy(self):
        self.assertTrue(self.exp.start("mini", "m", _FakeDimension(),
                                       [0, 10, 60, 70, 0, 10]))
        # 上一个没跑完，第二个拒绝
        self.assertFalse(self.exp.start("other", "o", _FakeDimension(),
                                        [0, 10, 60, 70, 0, 10]))

    def test_cancel_removes_area(self):
        self.exp.start("mini", "m", _FakeDimension(), [0, 10, 60, 70, 0, 10])
        self.exp.tick()   # 进 add 阶段
        self.exp.cancel()
        self.assertTrue(any(c.startswith("tickingarea remove")
                            for c in self.plugin._cmds))
        self.assertIsNone(self.exp.status())


if __name__ == "__main__":
    unittest.main()
