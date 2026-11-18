# -*- coding: utf-8 -*-
"""个人死斗（ffa）：模式选定后全员并入 A 池。

背景（2026-11-18 服主反馈："gs quick 现在会随机创建个人死斗模式嘛，
我怎么看着还是红蓝团队死斗？"）：

机器人在**大厅阶段**就分好队了——那时模式还没定，`active_mode` 是空串，
走的是"红蓝平衡分队"那条分支。模式定成 ffa 之后如果不并队：

  · B 队没有出生点（ffa 的点位全在 A 池），`_tp_to_team_spawn` 拿不到
    spawns 直接 return → 那半边人不会被传送；
  · `api_lobby_info` 的"敌人"按队伍不同算 → 每个人只把一半人当敌人，
    同队的人反倒成了"队友"。

于是"个人死斗"打起来长得跟团队死斗一模一样 —— 服主看到的正是这个。
"""
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402
stub.add_src_to_path()

from endstone_arc_shooter_game.session import Lobby, TEAM_A, TEAM_B  # noqa: E402
from endstone_arc_shooter_game.arc_shooter_game_plugin import (  # noqa: E402
    ARCShooterGamePlugin,
)


class _Logger:
    def __init__(self):
        self.lines = []

    def _w(self, msg):
        self.lines.append(str(msg))

    info = _w
    warning = _w
    error = _w
    debug = _w


def _plugin():
    plug = object.__new__(ARCShooterGamePlugin)
    plug.logger = _Logger()
    return plug


def _ffa_lobby(names=("bot1", "bot2", "bot3", "bot4")):
    """一个大厅：4 个玩家在大厅阶段按 A/B 平衡分好队。"""
    lobby = Lobby(admin=names[0])
    for name in names:
        lobby.join(name, 1000, now=1.0)
    # 模式定成 ffa（map_cfg 决定 active_mode）
    lobby.map_cfg = {
        "mode": "ffa",
        "teams": {
            "a": {"name": "玩家", "spawns": [{"x": 1, "y": 2, "z": 3}]},
            "b": {"name": "蓝队", "spawns": []},
        },
    }
    return lobby


class FFAMergeTests(unittest.TestCase):
    def test_during_lobby_players_are_split_into_two_teams(self):
        """前提：大厅阶段（模式未定）确实是 A/B 平衡分队——这就是坑的来源。"""
        lobby = Lobby(admin="bot1")
        for name in ("bot1", "bot2", "bot3", "bot4"):
            lobby.join(name, 1000, now=1.0)
        self.assertEqual(lobby.team_count(TEAM_A), 2)
        self.assertEqual(lobby.team_count(TEAM_B), 2)

    def test_merge_moves_everyone_to_team_a(self):
        lobby = _ffa_lobby()
        plug = _plugin()
        plug._merge_ffa_teams(lobby)
        self.assertEqual(lobby.team_count(TEAM_A), 4)
        self.assertEqual(lobby.team_count(TEAM_B), 0)
        for ps in lobby.online_players():
            self.assertEqual(ps.team, TEAM_A)

    def test_merge_is_idempotent(self):
        lobby = _ffa_lobby()
        plug = _plugin()
        plug._merge_ffa_teams(lobby)
        plug._merge_ffa_teams(lobby)
        self.assertEqual(lobby.team_count(TEAM_A), 4)
        self.assertEqual(lobby.team_count(TEAM_B), 0)

    def test_merge_does_nothing_in_tdm(self):
        """团队死斗不能并队——那是两队互殴。"""
        lobby = Lobby(admin="bot1")
        for name in ("bot1", "bot2", "bot3", "bot4"):
            lobby.join(name, 1000, now=1.0)
        lobby.map_cfg = {"mode": "tdm", "teams": {"a": {}, "b": {}}}
        plug = _plugin()
        plug._merge_ffa_teams(lobby)
        self.assertEqual(lobby.team_count(TEAM_B), 2)

    def test_merge_logs_when_players_moved(self):
        """要留痕：并队了几个人，服务端日志里查得到。"""
        lobby = _ffa_lobby()
        plug = _plugin()
        plug._merge_ffa_teams(lobby)
        self.assertTrue(any("并入 A 池" in ln for ln in plug.logger.lines))


if __name__ == "__main__":
    unittest.main()
