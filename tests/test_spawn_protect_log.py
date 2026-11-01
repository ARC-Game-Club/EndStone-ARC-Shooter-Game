# -*- coding: utf-8 -*-
"""无敌窗的日志：开始 / 结束 / 进入对局时取消。

2026-11-01 服主实测：对局里打假人，中途出现 3~4 秒"无敌中、扣血 0"，
而假人头顶**没有**显示[无敌状态]。分不清那是复活保护、准备阶段整段无敌，
还是桥接包的无敌名单串味了（名单是 JS 侧的**全局**状态）。

要能对上打击日志，就必须在枪战插件这侧留下：
  · 什么时候、因为什么、给谁开了多久的无敌窗；
  · 什么时候、因为什么结束，结束时还剩多少秒被取消。

这里同时守住一个真 bug 的回归：
`_enter_playing` 原来先 `_get_player()`，拿不到就 `continue`——于是拿不到
玩家句柄的人（模拟玩家尤其常见）**永远取消不了无敌窗**，只能等它自然到期，
表现就是"对局开打了，打他还是 0 伤害，头顶又没提示"。

测试不需要真服务器：用 `object.__new__` 造插件，只挂上被测方法依赖的字段。
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import _endstone_stub_shooter as _endstone_stub

_endstone_stub.add_src_to_path()

from endstone_arc_shooter_game.arc_shooter_game_plugin import (  # noqa: E402
    ARCShooterGamePlugin,
)


class _Logger:
    def __init__(self):
        self.lines = []

    def info(self, msg, *a, **kw):
        self.lines.append(str(msg))

    def warning(self, msg, *a, **kw):
        self.lines.append(str(msg))

    def error(self, msg, *a, **kw):
        self.lines.append(str(msg))

    def debug(self, msg, *a, **kw):
        pass

    def text(self) -> str:
        return "\n".join(self.lines)


class _Player:
    def __init__(self, name):
        self.name = name


class _Lobby:
    def __init__(self, names, state="playing"):
        self._names = list(names)
        self.state = state

    def online_players(self):
        return [_Player(n) for n in self._names]


def _make_plugin():
    """只挂被测方法要用的字段（跳过 __init__ 的文件存储）。"""
    plug = object.__new__(ARCShooterGamePlugin)
    plug.logger = _Logger()
    plug._spawn_protect_until = {}
    plug._spawn_protect_reason = {}
    plug._spawn_protect_started = {}
    plug._prep_frozen = set()
    plug._give_arc_coin = lambda player: None
    plug._take_arc_coin = lambda player: None
    plug._apply_team_name_tag = lambda player, lobby: None
    plug._apply_match_buffs = lambda player: None
    plug._clear_preparation_freeze = lambda player: None
    plug._tp_to_team_spawn = lambda player, lobby: None
    plug._send_toast = lambda player, *a, **kw: None
    plug._broadcast = lambda lobby, *a, **kw: None
    plug._t = lambda key, *a, **kw: str(key)
    plug._lobby_of = lambda name: None
    plug._get_player = lambda name: None          # 模拟"句柄拿不到"
    return plug


class SpawnProtectLogTests(unittest.TestCase):
    def test_start_logs_duration_and_reason(self):
        plug = _make_plugin()
        plug._apply_spawn_protect(_Player("paishoushen"), duration=3.0,
                                  reason="复活")
        log = plug.logger.text()
        self.assertIn("[无敌] paishoushen 开始 3.0s", log)
        self.assertIn("来源 复活", log)
        self.assertIn("paishoushen", plug._spawn_protect_until)

    def test_zero_duration_does_not_start(self):
        plug = _make_plugin()
        plug._apply_spawn_protect(_Player("a"), duration=0,
                                  reason="复活")
        self.assertEqual(plug._spawn_protect_until, {})
        self.assertNotIn("开始", plug.logger.text())

    def test_end_logs_reason_sustained_and_remaining(self):
        plug = _make_plugin()
        plug._apply_spawn_protect(_Player("a"), duration=20.0,
                                  reason="开局准备阶段")
        plug._log_protect_end("a", "进入对局")
        log = plug.logger.text()
        self.assertIn("[无敌] a 结束（进入对局）", log)
        self.assertIn("来源 开局准备阶段", log)
        self.assertIn("已持续", log)
        self.assertIn("取消时剩", log)
        self.assertNotIn("a", plug._spawn_protect_until)
        self.assertNotIn("a", plug._spawn_protect_reason)
        self.assertNotIn("a", plug._spawn_protect_started)

    def test_end_without_window_is_silent(self):
        """本来就没有无敌窗 → 不打日志（否则每次清场都刷屏）。"""
        plug = _make_plugin()
        plug._log_protect_end("nobody", "清场/离开对局")
        self.assertNotIn("结束", plug.logger.text())

    def test_enter_playing_clears_window_without_player_handle(self):
        """进入对局必须无条件取消无敌窗，**不依赖**拿到玩家句柄。

        这是一条真 bug 的回归：老代码 `if member is None: continue` 在前面，
        拿不到句柄的人就永远留着无敌窗，导致"开打了还打不动、头顶也没提示"。
        """
        plug = _make_plugin()
        plug._apply_spawn_protect(_Player("bot1"), duration=20.0,
                                  reason="开局准备阶段")

        class _L:
            state = "playing"
            match_time_seconds = 300
            match_time_minutes = 5
            target_score = 20

            def online_players(self):
                return [_Player("bot1")]

            def begin_playing(self, *a, **kw):
                pass

        plug._enter_playing(_L(), now=0.0)
        self.assertNotIn("bot1", plug._spawn_protect_until)
        self.assertIn("结束（进入对局）", plug.logger.text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
