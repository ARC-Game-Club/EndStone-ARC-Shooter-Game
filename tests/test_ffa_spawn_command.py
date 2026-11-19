# -*- coding: utf-8 -*-
"""命令注册回归测试：`/gs` 家族只能两段，带参数的必须注册成顶层命令。

背景（2026-11-19 服主指出："这个指令不能注册三段的，我之前说过很多次了"）
--------------------------------------------------------------------------
BDS 按 `commands["gs"]["usages"]` 建命令语法树，**gs 家族只能注册两段形式**。
于是：

* `/gs ffaspawn 炼狱小镇` → `Syntax error: Unexpected "ffaspawn"` → on_command
  里那段分支**从来没被执行过**（个人死斗出生点池只能"创建死斗模式时算一次"，
  导航重烘后不会自动更新）；
* `/gs bake harbor` → 同样挂在解析阶段（2026-11-03 日志里就有）；
* `/gs report start on` → 同理，一直是死代码。

要带参数就得注册成**顶层命令**（`/addspawn <mode> [team]`、
`/connecttoserver <server_name: str>` 都是这么写的）。

这里钉住四件事：
1. gs 的 usages 一律两段（没有"子命令 + 参数"这种三段形式）；
2. on_command 里每个 `sub == "xxx"` 分支都必须在 gs 的 usages 里出现；
3. 需要参数的 ffaspawn / gsreport 注册成**顶层**命令；
4. 顶层命令的占位符必须是纯 ASCII（BDS 遇到非 ASCII 直接拒绝注册整条命令）。
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402  装 endstone stub
stub.add_src_to_path()

from endstone_arc_shooter_game.arc_shooter_game_plugin import (  # noqa: E402
    ARCShooterGamePlugin,
)

PLUGIN_SRC = (Path(__file__).resolve().parent.parent / "src"
              / "endstone_arc_shooter_game" / "arc_shooter_game_plugin.py")


class GsUsageGrammarTests(unittest.TestCase):
    def setUp(self):
        self.cmds = ARCShooterGamePlugin.commands
        self.src = PLUGIN_SRC.read_text(encoding="utf-8")

    def test_gs_usages_are_at_most_two_segments(self):
        """gs 的 usages 只能两段：`/gs` 或 `/gs <子命令>`。

        三段（`/gs ffaspawn 炼狱小镇`）在这个 BDS 上注册不出来——解析阶段
        就报 "Syntax error: Unexpected ..."，命令处理器根本收不到。
        """
        for usage in self.cmds["gs"]["usages"]:
            parts = usage.split()
            self.assertLessEqual(
                len(parts), 2,
                f"{usage!r} 是三段以上，注册不出来——带参数的命令要注册成顶层命令")

    def test_every_gs_subcommand_branch_is_registered(self):
        """on_command 里每个 `sub == "xxx"` 分支都必须在 gs 的 usages 里。

        只扫 on_command 函数体——别的命令（如 setrange）也有自己的
        `sub ==` 分支，不属于 gs 家族。
        """
        start = self.src.index("def on_command(")
        body = self.src[start:self.src.index("\n    def ", start + 10)]
        branches = set(re.findall(r'if sub == "([a-z_]+)":', body))
        self.assertTrue(branches, "没解析出任何 gs 子命令分支")
        registered = {u.split()[1] for u in self.cmds["gs"]["usages"]
                      if len(u.split()) == 2}
        missing = sorted(branches - registered)
        self.assertEqual(missing, [],
                         f"这些 gs 子命令没有注册进 usages，永远执行不到：{missing}")

    def test_ffaspawn_is_a_top_level_command(self):
        """ffaspawn 要带地图 id → 必须是顶层命令。"""
        self.assertIn("ffaspawn", self.cmds)
        usages = self.cmds["ffaspawn"]["usages"]
        self.assertTrue(any(u.startswith("/ffaspawn ") for u in usages),
                        "顶层 ffaspawn 必须能带地图 id 参数")
        self.assertTrue(any("[map_id" in u for u in usages),
                        "ffaspawn 的 usage 要声明 map_id 占位符")

    def test_gsreport_is_a_top_level_command(self):
        """report 的开关参数同样是两段以上 → 顶层命令。"""
        self.assertIn("gsreport", self.cmds)
        usages = self.cmds["gsreport"]["usages"]
        self.assertTrue(any("[target" in u and "[mode" in u for u in usages),
                        "gsreport 的 usage 要声明 target / mode 占位符")

    def test_top_level_placeholders_are_ascii(self):
        """占位符必须纯 ASCII：BDS 遇到非 ASCII 直接拒绝注册整条命令。"""
        for name, spec in self.cmds.items():
            for usage in spec.get("usages", []):
                for ph in re.findall(r"[<\[]\s*([^\s>\]:]+)", usage):
                    self.assertTrue(
                        ph.isascii(),
                        f"{name}: 占位符 {ph!r} 含非 ASCII，整条命令会注册失败")

    def test_ffaspawn_and_gsreport_are_dispatched(self):
        """两个顶层命令都要在 on_command 里被分发。"""
        self.assertIn('command.name == "ffaspawn"', self.src)
        self.assertIn('command.name == "gsreport"', self.src)

    def test_resolve_map_id_accepts_id_and_display_name(self):
        """地图名解析：id / 显示名 / 模糊，三种都认。"""
        plug = object.__new__(ARCShooterGamePlugin)
        plug.config_store = type("S", (), {
            "maps": {
                "harbor": {"display_name": "港口-装卸货场"},
                "炼狱小镇": {"display_name": "炼狱小镇"},
            }})()
        resolve = plug._resolve_map_id
        self.assertEqual(resolve("harbor"), "harbor")
        self.assertEqual(resolve("港口-装卸货场"), "harbor")
        self.assertEqual(resolve("炼狱小镇"), "炼狱小镇")
        self.assertEqual(resolve("港口"), "harbor")
        self.assertEqual(resolve("不存在的图"), "")


if __name__ == "__main__":
    loader = unittest.defaultTestLoader
    suite = unittest.TestSuite([
        loader.loadTestsFromTestCase(GsUsageGrammarTests),
    ])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print(f"全部 {result.testsRun} 项通过")
    raise SystemExit(0 if result.wasSuccessful() else 1)
