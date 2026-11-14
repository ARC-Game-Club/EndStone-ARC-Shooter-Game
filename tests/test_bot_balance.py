# -*- coding: utf-8 -*-
"""假人调度（在线配额 + AI 单房限制 + 巡检迁移）的回归测试。

锁三件事：
1. 配额公式：地图规模（可玩地图数 ×2）与等待大厅数共同决定天花板；
2. 巡检选房：只帮"真人建的、等待中、没满、人没齐"的大厅，等最久的先；
3. quick 建房：已有纯 AI 等待房时假人不许再建，真人不受限。
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))
import _endstone_stub_shooter as _endstone_stub

_endstone_stub.add_src_to_path()

from endstone_arc_shooter_game.session import (  # noqa: E402
    STATE_COUNTDOWN,
    STATE_LOBBY,
    STATE_PLAYING,
    Lobby,
    compute_bot_online_quota,
    pick_assist_lobby,
)


def _desc(lobby_id, started_at=0.0, *, has_human=True, waiting=True,
          joinable=True, ready=False):
    return {
        "lobby_id": lobby_id,
        "started_at": started_at,
        "has_human": has_human,
        "waiting": waiting,
        "joinable": joinable,
        "ready": ready,
    }


class BotOnlineQuotaTests(unittest.TestCase):
    """在线假人配额 = clamp(base + per_lobby×等待房数, base, min(硬上限, max(base, 地图数×2)))。"""

    def test_base_when_no_waiting_lobbies(self):
        self.assertEqual(
            compute_bot_online_quota(0, 2, base=2, per_lobby=2, hard_max=10), 2)

    def test_each_waiting_lobby_adds_quota(self):
        self.assertEqual(
            compute_bot_online_quota(2, 3, base=2, per_lobby=2, hard_max=10), 6)

    def test_map_scale_is_ceiling(self):
        # 地图 ×2 封顶：2 张图最多 4 人，等待再多房间也不突破
        self.assertEqual(
            compute_bot_online_quota(5, 2, base=2, per_lobby=2, hard_max=10), 4)

    def test_hard_max_overrides_map_ceiling(self):
        self.assertEqual(
            compute_bot_online_quota(3, 10, base=2, per_lobby=2, hard_max=5), 5)

    def test_floor_is_base(self):
        # 地图数 0 时 max(base, 0) 兜底，配额不会掉到 base 以下
        self.assertEqual(
            compute_bot_online_quota(0, 0, base=2, per_lobby=2, hard_max=10), 2)


class PickAssistLobbyTests(unittest.TestCase):
    """巡检迁移目标：真人 + 等待中 + 可加入 + 未人齐，等最久的优先。"""

    def test_picks_earliest_qualifying_human_lobby(self):
        self.assertEqual(
            pick_assist_lobby([
                _desc("later", started_at=200.0),
                _desc("earlier", started_at=100.0),
            ]),
            "earlier",
        )

    def test_skips_bot_only_lobbies(self):
        self.assertIsNone(pick_assist_lobby([_desc("b1", has_human=False)]))

    def test_skips_running_or_full_or_ready_lobbies(self):
        self.assertIsNone(pick_assist_lobby([
            _desc("running", waiting=False),
            _desc("full", joinable=False),
            _desc("ready", ready=True),
        ]))

    def test_ready_lobby_needs_no_assist(self):
        # 人齐的房不需要支援——再塞是打扰
        self.assertIsNone(pick_assist_lobby([_desc("ok", ready=True)]))

    def test_empty_list_returns_none(self):
        self.assertIsNone(pick_assist_lobby([]))

    def test_tie_breaks_by_lobby_id(self):
        # started_at 相同 → 按 lobby_id 稳定排序，行为可预测
        self.assertEqual(
            pick_assist_lobby([_desc("bbb"), _desc("aaa")]), "aaa")


class QuickJoinLobbyLimitTests(unittest.TestCase):
    """AI 群体最多自建一间：已有纯 AI 等待房时，假人 quick 不建房。"""

    def setUp(self):
        from endstone_arc_shooter_game.arc_shooter_game_plugin import (
            ARCShooterGamePlugin,
        )
        self.plugin = ARCShooterGamePlugin()
        self.plugin._safe_log = lambda *a, **k: None
        self.messages = []

        class _P:
            def __init__(self, name, xuid):
                self.name = name
                self.xuid = xuid  # 假人判据：xuid 为空
                self.messages = []

            def send_message(self, m):
                self.messages.append(str(m))

        self.bot = _P("Bot1", "")
        self.human = _P("Steve", "12345")
        # 一间纯 AI 等待房（两个假人，已满员 → quick 找不到可加入的房，
        # 只能走建房分支）
        lobby = Lobby(admin="Bot0")
        lobby.map_cfg = {"max_players_per_team": 1}
        lobby.join("Bot0", 0, now=1)
        lobby.join("Bot1", 0, now=2)
        self.plugin.lobbies = {"L1": lobby}
        self.plugin.player_to_lobby = {}
        self.plugin._is_bot_player = lambda name: not name.startswith("S")
        self.plugin._playable_maps = lambda: [{"id": "m1"}]

    def _run_quick(self, player):
        # 构造"无可加入房"状态：can_join 已在 setUp 的满员房上返回 False，
        # quick 会走到建房分支——拦截与否就在那一步见分晓。
        self.plugin._lobby_of = lambda name: None
        self.plugin._create_lobby = lambda p: self.plugin.lobbies.setdefault(
            "NEW", Lobby(admin=p.name))
        self.plugin._t = lambda key: key
        self.plugin._handle_quick_join(player)

    def _full_mixed_lobby(self):
        lobby = Lobby(admin="Steve")
        lobby.map_cfg = {"max_players_per_team": 1}
        lobby.join("Steve", 0, now=1)
        lobby.join("Bot1", 0, now=2)
        return lobby

    def test_bot_cannot_create_second_lobby(self):
        self._run_quick(self.bot)
        self.assertNotIn("NEW", self.plugin.lobbies,
                         "已有纯 AI 等待房时假人不得再建房")

    def test_human_can_always_create(self):
        self._run_quick(self.human)
        self.assertIn("NEW", self.plugin.lobbies, "真人 quick 建房不受限")

    def test_bot_can_create_when_no_bot_only_lobby(self):
        self.plugin.lobbies = {}
        self._run_quick(self.bot)
        self.assertIn("NEW", self.plugin.lobbies,
                      "没有 AI 房时假人可以建第一间")

    def test_mixed_lobby_does_not_block_bot_creation(self):
        # 有真人的房不算"纯 AI 房"——不拦截
        self.plugin.lobbies = {"L2": self._full_mixed_lobby()}
        self._run_quick(self.bot)
        self.assertIn("NEW", self.plugin.lobbies)

    def test_running_bot_lobby_does_not_block(self):
        # 对局中的 AI 房不算"等待房"，不拦截建房
        lobby = Lobby(admin="Bot0")
        lobby.map_cfg = {"max_players_per_team": 1}
        lobby.join("Bot0", 0, now=1)
        lobby.join("Bot1", 0, now=2)
        lobby.begin_buy(0)
        lobby.begin_playing()
        self.plugin.lobbies = {"L3": lobby}
        self._run_quick(self.bot)
        self.assertIn("NEW", self.plugin.lobbies)


if __name__ == "__main__":
    unittest.main()
