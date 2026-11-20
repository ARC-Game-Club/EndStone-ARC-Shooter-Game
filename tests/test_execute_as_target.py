# -*- coding: utf-8 -*-
"""`execute as @p run <命令>` 转发过来的 sender 怎么反查目标玩家。

背景（2026-11-19 服主报：`execute as @p run gs armory` 又开始提示"该指令只能由玩家使用"）
--------------------------------------------------------------------------
Endstone 0.11.15 之前，转发过来的 sender 是 `ProxiedCommandSender`（带 callee /
caller），插件靠 `sender.name` 就能拿到玩家名。上游 2025-06-22 把它删了
（commit f5e6c039），转发过来的 sender 退化成基类 `CommandSender`：

* `name` 是**空串**——实测 `execute as @p run say x` 在服务器日志里是 `[] x`，
  而控制台直连是 `[Server] x`；
* 没有 `is_player` / `xuid`；
* 也拿不到 BDS 的 origin 实体（`CommandOriginWrapper` 只暴露 4 个方法）。

所以身份**无法**从 sender 上恢复，只能退一步：线上唯一真人就代他执行；
多个真人无法猜 → 提示改用新加的 `/gsas <玩家> <命令>` 显式点名。

这里钉住：
1. 匿名 sender + 唯一真人 → 解析到那个真人；
2. 匿名 sender + 多真人 → 解析失败，但提示里要说清"有几个人在线"；
3. 控制台 sender → 仍然"只能由玩家使用"（旧行为不变）；
4. `/gsas` 注册成**顶层命令**，且第二个参数是 `message` 类型（吃掉整行剩余文本）；
5. `/gsas` 用 `perform_command` 以目标玩家身份下发命令。
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402  装 endstone stub
stub.add_src_to_path()

from endstone import Player  # noqa: E402
from endstone_arc_shooter_game.arc_shooter_game_plugin import (  # noqa: E402
    ARCShooterGamePlugin,
)
from endstone_arc_shooter_game.language import DEFAULT_TEXTS  # noqa: E402


class FakeDimension:
    def __init__(self, dimension_id="overworld"):
        self.id = dimension_id


class FakeLocation:
    def __init__(self, x, y, z, dimension="overworld"):
        self.x, self.y, self.z = x, y, z
        self.dimension = FakeDimension(dimension)


class FakePlayer(Player):
    """在线玩家（真人 xuid 非空，假人 xuid 为空）。"""

    def __init__(self, name, xuid="", location=None):
        self.name = name
        self.xuid = xuid
        self.location = location or FakeLocation(0, 64, 0)
        self.performed = []

    def perform_command(self, command):
        self.performed.append(command)


class FakeBlock:
    def __init__(self, x, y, z, dimension="overworld"):
        self.location = FakeLocation(x, y, z, dimension)


class FakeServer:
    def __init__(self, players, console=None):
        self.online_players = players
        self.command_sender = console

    def get_player(self, name):
        for player in self.online_players:
            if player.name == name:
                return player
        return None


class AnonymousSender:
    """execute 转发过来的 sender：名字空串。"""

    name = ""

    def __init__(self):
        self.messages = []

    def send_message(self, text):
        self.messages.append(text)


class NamedSender(AnonymousSender):
    def __init__(self, name):
        super().__init__()
        self.name = name


class BlockSender(AnonymousSender):
    """命令方块 sender：Endstone 暴露 `.block`，`Block` 暴露 `.location`。"""

    def __init__(self, x=0, y=64, z=0, dimension="overworld"):
        super().__init__()
        self.block = FakeBlock(x, y, z, dimension)


class FakeLanguageManager:
    def __init__(self):
        self.texts = dict(DEFAULT_TEXTS)

    def GetText(self, key, lang_code=None):
        return self.texts.get(key, key)


def make_plugin(players, console=None):
    plugin = object.__new__(ARCShooterGamePlugin)
    plugin.server = FakeServer(players, console=console)
    plugin.language_manager = FakeLanguageManager()
    return plugin


class ExecuteAsTargetTests(unittest.TestCase):
    def test_anonymous_sender_falls_back_to_the_only_human(self):
        """匿名 sender（execute 转发）+ 线上唯一真人 → 代他执行。"""
        human = FakePlayer("DEVILENMO", "2535408197449845")
        bots = [FakePlayer(f"bot_{i}") for i in range(7)]
        plugin = make_plugin([human] + bots)
        sender = AnonymousSender()
        self.assertIs(plugin._resolve_player_for_command_sender(sender), human)

    def test_anonymous_sender_with_two_humans_is_ambiguous(self):
        """两个真人 → 猜不出来（None），但提示要说清有几个人在线。"""
        plugin = make_plugin([FakePlayer("A", "1"), FakePlayer("B", "2")])
        sender = AnonymousSender()
        self.assertIsNone(plugin._resolve_player_for_command_sender(sender))
        message = plugin._player_only_message(sender)
        self.assertIn("无法确定目标玩家", message)
        self.assertIn("2", message)
        self.assertIn("/gsas", message)

    def test_console_sender_keeps_old_behaviour(self):
        """控制台 sender → 仍然"只能由玩家使用"（不代唯一真人执行）。"""
        human = FakePlayer("DEVILENMO", "2535")
        console = NamedSender("Server")
        plugin = make_plugin([human], console=console)
        self.assertIsNone(plugin._resolve_player_for_command_sender(console))
        self.assertIn("只能由玩家使用", plugin._player_only_message(console))

    def test_named_sender_resolves_by_name(self):
        """命令方块/代理：sender 有名字 → 按名字解析在线玩家。"""
        human = FakePlayer("DEVILENMO", "2535")
        plugin = make_plugin([human])
        sender = NamedSender("§rDEVILENMO")
        self.assertIs(plugin._resolve_player_for_command_sender(sender), human)

    def test_player_sender_returns_itself(self):
        human = FakePlayer("DEVILENMO", "2535")
        plugin = make_plugin([human])
        self.assertIs(plugin._resolve_player_for_command_sender(human), human)

    # ---------- 命令方块（踏板玩法）----------

    def test_block_sender_picks_the_nearest_human(self):
        """命令方块 → 离方块最近的真人（这就是 BDS `@p` 的意思）。"""
        near = FakePlayer("NEAR", "1", FakeLocation(3, 64, 0))
        far = FakePlayer("FAR", "2", FakeLocation(50, 64, 0))
        plugin = make_plugin([near, far])
        sender = BlockSender(0, 64, 0)
        self.assertIs(plugin._resolve_player_for_command_sender(sender), near)

    def test_block_sender_ignores_bots(self):
        """假人离得更近也不该抢——它没有客户端，抢到也看不见界面。"""
        bot = FakePlayer("bot_a", "", FakeLocation(1, 64, 0))
        human = FakePlayer("DEVILENMO", "2535", FakeLocation(20, 64, 0))
        plugin = make_plugin([bot, human])
        sender = BlockSender(0, 64, 0)
        self.assertIs(plugin._resolve_player_for_command_sender(sender), human)

    def test_block_sender_skips_other_dimensions(self):
        """别的维度的玩家不算距离。"""
        human = FakePlayer("DEVILENMO", "2535", FakeLocation(1, 64, 0, "nether"))
        plugin = make_plugin([human])
        sender = BlockSender(0, 64, 0, "overworld")
        self.assertIsNone(plugin._resolve_player_for_command_sender(sender))

    def test_block_sender_without_players_gives_clear_message(self):
        """方块附近没人 → 提示要说清是"附近没人"，不是"只能由玩家使用"。"""
        plugin = make_plugin([])
        sender = BlockSender(0, 64, 0)
        self.assertIsNone(plugin._resolve_player_for_command_sender(sender))
        self.assertIn("附近没有玩家", plugin._player_only_message(sender))

    def test_gsas_is_a_top_level_command(self):
        """/gsas 带参数 → 必须注册成顶层命令（gs 家族只能两段）。"""
        self.assertIn("gsas", ARCShooterGamePlugin.commands)
        usages = ARCShooterGamePlugin.commands["gsas"]["usages"]
        self.assertTrue(any(u.startswith("/gsas ") for u in usages))

    def test_gsas_takes_the_rest_of_the_line_as_message(self):
        """第二个参数必须是 `message` 类型且排在最后——它会吃掉整行剩余文本。

        Endstone 的 parseNode 对最后一个参数走 "consume all remaining text" 分支，
        所以 `/gsas DEVILENMO gs armory` 的 args 是 ["DEVILENMO", "gs armory"]。
        """
        usage = ARCShooterGamePlugin.commands["gsas"]["usages"][0]
        self.assertIn("<cmd: message>", usage)
        self.assertTrue(usage.rstrip().endswith("<cmd: message>"))
        self.assertIn("<player: str>", usage)

    def test_gsas_permission_defaults_to_op(self):
        """gsas 能以别人身份跑命令 → 权限必须 op（防越权）。"""
        perms = ARCShooterGamePlugin.permissions
        self.assertIn("arc_shooter_game.command.gsas", perms)
        self.assertEqual(perms["arc_shooter_game.command.gsas"]["default"], "op")

    def test_gsas_runs_command_as_the_target_player(self):
        """`/gsas DEVILENMO gs armory` → 用目标玩家的身份下发。"""
        human = FakePlayer("DEVILENMO", "2535")
        plugin = make_plugin([human])
        sender = NamedSender("Server")
        plugin._handle_run_as_command(sender, ["DEVILENMO", "gs armory"])
        self.assertEqual(human.performed, ["gs armory"])

    def test_gsas_rejects_unknown_target(self):
        plugin = make_plugin([FakePlayer("DEVILENMO", "2535")])
        sender = NamedSender("Server")
        plugin._handle_run_as_command(sender, ["NOBODY", "gs armory"])
        self.assertTrue(any("找不到在线玩家" in m for m in sender.messages))
        self.assertEqual(plugin.server.online_players[0].performed, [])

    def test_gsas_rejects_recursion(self):
        human = FakePlayer("DEVILENMO", "2535")
        plugin = make_plugin([human])
        sender = NamedSender("Server")
        plugin._handle_run_as_command(sender, ["DEVILENMO", "gsas OTHER gs armory"])
        self.assertTrue(any("不能把 gsas 自己套给自己" in m for m in sender.messages))
        self.assertEqual(human.performed, [])

    def test_gsas_requires_both_arguments(self):
        plugin = make_plugin([])
        sender = NamedSender("Server")
        plugin._handle_run_as_command(sender, ["DEVILENMO"])
        self.assertTrue(any("用法" in m for m in sender.messages))

    def test_gsas_is_dispatched_by_on_command(self):
        """on_command 里要真的分发 gsas（不然注册了也是死的）。"""
        human = FakePlayer("DEVILENMO", "2535")
        plugin = make_plugin([human])
        sender = NamedSender("Server")
        command = type("Cmd", (), {"name": "gsas"})()
        plugin.on_command(sender, command, ["DEVILENMO", "gs armory"])
        self.assertEqual(human.performed, ["gs armory"])

    def test_language_defaults_have_the_new_keys(self):
        for key in ("CMD_AMBIGUOUS_TARGET", "GSAS_USAGE", "GSAS_RECURSIVE",
                    "GSAS_NO_TARGET", "GSAS_FAIL", "GSAS_OK"):
            self.assertIn(key, DEFAULT_TEXTS)


if __name__ == "__main__":
    result = unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(ExecuteAsTargetTests))
    if result.wasSuccessful():
        print(f"全部 {result.testsRun} 项通过")
    raise SystemExit(0 if result.wasSuccessful() else 1)
