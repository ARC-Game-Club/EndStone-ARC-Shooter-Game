# -*- coding: utf-8 -*-
"""假人插件 ↔ 枪战插件的两处事件接线。

背景（2026-11-01 假人插件 v3.10.0 重构后）：

假人插件把"自动进对局"从**轮询心跳**改成了**事件驱动**——30 秒定时
quick 被移除，只剩两个入口：

  1. **上线事件**（假人自己上线时 quick 一次）——已有；
  2. **大厅创建事件**（`api_shooter_lobby_created`）——上游明说
     "本仓库没有枪战插件源码，无法替其接线"。

少了第 2 个，新建的大厅就再也不会有假人补位——尤其是**假人自己建的
那间房**：枪战插件原来的 `_maybe_fill_with_bots` 只在**真人**触发时
补位（假人触发会被跳过以防循环），所以假人建房 → 没人进来 → 房间
永远只有它自己。

另外，枪战模式下假人**不主动说话**（需求文档 §1），只在被点名或收到
**结算类**事件时开口。这条事件同样得由枪战插件发：
`api_environment_event(name, text, settlement=True)`。

⚠️ settlement 开关是这里最容易踩的坑：假人侧把非结算类事件在枪战
模式下**一律拒收**（`mode == "gun_game" and not settlement` 直接
return False）。漏传 True，赛后就一声不吭，而且**不报错**——只能靠
读代码发现。所以下面专门有一条测试钉住这个参数。

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
        self.lines.append(str(msg))

    def text(self) -> str:
        return "\n".join(self.lines)


class _Player:
    def __init__(self, name, xuid=""):
        self.name = name
        self.xuid = xuid


class _FakeAfp:
    """假人插件的替身：记录两个接口被怎么调的。"""

    def __init__(self, with_lobby_hook=True, with_event_hook=True,
                 event_accepts_settlement=True):
        self.lobby_calls = []
        self.event_calls = []
        self._with_lobby = with_lobby_hook
        self._with_event = with_event_hook
        self._event_accepts_settlement = event_accepts_settlement

    def api_shooter_lobby_created(self, lobby_id, event_id=""):
        if not self._with_lobby:
            raise AttributeError("no such api")
        self.lobby_calls.append((lobby_id, event_id))
        return {"ok": True, "filled": []}

    def api_environment_event(self, name, text, settlement=False):
        if not self._with_event:
            raise AttributeError("no such api")
        if not self._event_accepts_settlement and settlement:
            raise TypeError("api_environment_event() takes 2 positional "
                            "arguments but 3 were given")
        self.event_calls.append((name, text, settlement))
        return {"ok": True}


class _PluginManager:
    def __init__(self, afp):
        self._afp = afp

    def get_plugin(self, name):
        return self._afp if name == "arc_fake_player" else None


class _Server:
    def __init__(self, afp):
        self.plugin_manager = _PluginManager(afp)


class _FakeLobby:
    """够用的大厅替身：只提供被测方法用到的那几个成员。"""

    def __init__(self, lobby_id="L1", names=("bot1", "bot2"), winner=None):
        self.lobby_id = lobby_id
        self._names = list(names)
        self._winner = winner

    def team_name(self, team_id):
        return "红队" if team_id == "A" else "蓝队"

    def result_rows(self):
        return [_Player(n) for n in self._names]


def _make_plugin(afp=None):
    """只挂被测方法要用的字段（跳过 __init__ 的文件存储）。"""
    plug = object.__new__(ARCShooterGamePlugin)
    plug.logger = _Logger()
    plug._lobby_event_seq = 0
    plug.server = _Server(afp) if afp is not None else _Server(None)
    return plug


class LobbyCreatedHookTests(unittest.TestCase):
    def test_calls_hook_with_lobby_id_and_event_id(self):
        afp = _FakeAfp()
        plug = _make_plugin(afp)
        plug._notify_lobby_created(_FakeLobby(lobby_id="L42"))
        self.assertEqual(len(afp.lobby_calls), 1)
        lobby_id, event_id = afp.lobby_calls[0]
        self.assertEqual(lobby_id, "L42")
        self.assertTrue(event_id, "event_id 不能为空——假人插件靠它去重")

    def test_event_id_is_unique_per_creation(self):
        """大厅 ID 会重用，所以 event_id 必须每次不同。

        假人插件靠 event_id 去重（`_lobby_events_seen`）：两次建房
        撞成同一个 key，第二次就不会再补位——房间又空了。
        """
        afp = _FakeAfp()
        plug = _make_plugin(afp)
        plug._notify_lobby_created(_FakeLobby(lobby_id="SAME"))
        plug._notify_lobby_created(_FakeLobby(lobby_id="SAME"))
        self.assertEqual(len(afp.lobby_calls), 2)
        self.assertNotEqual(afp.lobby_calls[0][1], afp.lobby_calls[1][1])

    def test_missing_hook_is_silent(self):
        """旧版假人插件没这个接口 → 安静跳过，不能把建房搞崩。"""
        afp = _FakeAfp(with_lobby_hook=False)
        plug = _make_plugin(afp)
        plug._notify_lobby_created(_FakeLobby())      # 不抛异常即通过
        self.assertEqual(afp.lobby_calls, [])

    def test_no_fake_player_plugin_is_silent(self):
        plug = _make_plugin(None)
        plug._notify_lobby_created(_FakeLobby())      # 不抛异常即通过


class MatchSettlementHookTests(unittest.TestCase):
    def test_settlement_flag_must_be_true(self):
        """⚠️ 回归护栏：settlement 必须传 True。

        假人侧 `Agent.environment_event` 在枪战模式下把非结算事件
        直接拒收（`mode == "gun_game" and not settlement`），漏传就
        赛后再也不开口，而且**不报错**。
        """
        afp = _FakeAfp()
        plug = _make_plugin(afp)
        plug._notify_match_settlement(_FakeLobby(), None, 5, 3)
        self.assertTrue(afp.event_calls, "结算事件根本没发出去")
        for name, text, settlement in afp.event_calls:
            self.assertTrue(settlement, f"{name} 的结算事件没带 settlement=True")
            self.assertIn("比赛结束", text)

    def test_every_participant_gets_the_event(self):
        afp = _FakeAfp()
        plug = _make_plugin(afp)
        plug._notify_match_settlement(_FakeLobby(names=("bot1", "bot2")), None, 1, 2)
        self.assertEqual([c[0] for c in afp.event_calls], ["bot1", "bot2"])

    def test_result_text_mentions_winner(self):
        afp = _FakeAfp()
        plug = _make_plugin(afp)
        plug._notify_match_settlement(_FakeLobby(names=("bot1",)), "A", 10, 4)
        text = afp.event_calls[0][1]
        self.assertIn("10", text)
        self.assertIn("4", text)
        self.assertIn("红队", text)

    def test_draw_result_text(self):
        afp = _FakeAfp()
        plug = _make_plugin(afp)
        plug._notify_match_settlement(_FakeLobby(names=("bot1",)), None, 7, 7)
        self.assertIn("打平", afp.event_calls[0][1])

    def test_old_signature_falls_back_to_two_args(self):
        """旧版假人插件的 api_environment_event 只认两个参数。"""
        afp = _FakeAfp(event_accepts_settlement=False)
        plug = _make_plugin(afp)
        plug._notify_match_settlement(_FakeLobby(names=("bot1",)), None, 1, 1)
        self.assertEqual(len(afp.event_calls), 1)
        self.assertEqual(afp.event_calls[0][0], "bot1")

    def test_missing_hook_is_silent(self):
        afp = _FakeAfp(with_event_hook=False)
        plug = _make_plugin(afp)
        plug._notify_match_settlement(_FakeLobby(), None, 1, 1)
        self.assertEqual(afp.event_calls, [])


class HookWiringTests(unittest.TestCase):
    """确认两个钩子真的挂在了正确的位置（源码级护栏）。"""

    def setUp(self):
        src = (Path(__file__).resolve().parent.parent
               / "src" / "endstone_arc_shooter_game" / "arc_shooter_game_plugin.py")
        self.text = src.read_text(encoding="utf-8")

    def test_create_lobby_notifies(self):
        """建房必须通知——尤其是假人自己建的那间房。"""
        create_body = self.text.split("def _create_lobby", 1)[1].split(
            "def _join_lobby", 1)[0]
        self.assertIn("self._notify_lobby_created(lobby)", create_body)

    def test_end_match_notifies(self):
        end_body = self.text.split("def _end_match", 1)[1].split(
            "def _send_match_result_toast", 1)[0]
        self.assertIn("self._notify_match_settlement(", end_body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
