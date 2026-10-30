# -*- coding: utf-8 -*-
"""枪战战报 → QQ 群 冒烟测试：真跑 _enter_playing / _end_match（stub endstone）。

为什么要有这个：单元测试只验了"拼文本"和"发消息"两个零件，
这里验的是**接缝**——开局那一刻到底有没有发、终局战报拿到的是不是
最后一刻的比分（_end_match 会把大厅摘掉，晚一步就读不到了）。

不连服务器：群服互通插件、玩家、大厅全用替身。
"""
import sys
import time
from pathlib import Path

# Windows 控制台默认 GBK，打印 emoji 会 UnicodeEncodeError —— 换成 UTF-8。
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _endstone_stub_shooter as stub  # 安装 endstone stub
stub.add_src_to_path()

from endstone_arc_shooter_game.arc_shooter_game_plugin import ARCShooterGamePlugin
from endstone_arc_shooter_game.session import Lobby, PlayerState


MAP_CFG = {
    "id": "arc_map",
    "display_name": "ARCShooterGame",
    "mode": "tdm",
    "max_players_per_team": 8,
    "target_score": 20,
    "match_time_minutes": 5,
    "teams": {
        "a": {"name": "红队", "spawns": [{"x": 0, "y": 64, "z": 0}]},
        "b": {"name": "蓝队", "spawns": [{"x": 10, "y": 64, "z": 0}]},
    },
}


class FakeLogger:
    def __init__(self):
        self.errors = []
        self.infos = []

    def info(self, m):
        self.infos.append(m)

    def warning(self, m):
        self.infos.append(m)

    def error(self, m):
        self.errors.append(m)


class FakeQQPlugin:
    """群服互通插件的替身。"""

    def __init__(self):
        self.calls = []

    def api_send_event(self, event_type, display_name, raw_player_name,
                       message="", **kwargs):
        self.calls.append((event_type, message, kwargs))
        return True


class FakeSettings:
    def __init__(self, values):
        self.values = dict(values)

    def GetSetting(self, key):
        return self.values.get(key)


class FakeConfigStore:
    """只实现 _end_match 这条链上真正会被调到的方法。"""

    def __init__(self):
        self.settings = FakeSettings({
            "QQ_REPORT_ENABLED": "1",
            "QQ_REPORT_START": "1",
            "QQ_REPORT_END": "1",
        })

    # 奖励相关：全 0 → _distribute_match_rewards 直接返回，不会碰 arc_core
    def match_money_per_kill(self):
        return 0

    def match_win_bonus(self):
        return 0

    def match_mvp_bonus(self):
        return 0

    def win_guild_contribution_per_kd(self):
        return 0

    def match_assist_weight(self):
        return 0.5

    def match_tk_weight(self):
        return 1.5


class FakeServer:
    def __init__(self, qq):
        self.online_players = []
        self.plugin_manager = type(
            "PM", (), {"get_plugin": staticmethod(
                lambda name: qq if name == "arc_qq_sync_astrbot" else None)})()

    def get_player(self, name):
        return None


def make_plugin(qq):
    plugin = object.__new__(ARCShooterGamePlugin)
    plugin.logger = FakeLogger()
    plugin.server = FakeServer(qq)
    plugin.config_store = FakeConfigStore()
    plugin.language_manager = None   # _t() 退化成返回 key
    plugin.career_store = None       # 不记生涯，避免碰磁盘
    plugin.lobbies = {}
    plugin.player_to_lobby = {}
    return plugin


def make_lobby():
    lobby = Lobby(admin="Steve", map_id="arc_map", mode="tdm",
                  map_cfg=dict(MAP_CFG))
    lobby.players["BloodShot"] = PlayerState(
        name="BloodShot", team="a", points=1000, kills=5, deaths=1, assists=2)
    lobby.players["lowkey"] = PlayerState(
        name="lowkey", team="b", points=1000, kills=3, deaths=4, assists=1,
        team_kills=1)
    lobby.score_a = 5
    lobby.score_b = 3
    return lobby


qq = FakeQQPlugin()
plugin = make_plugin(qq)
lobby = make_lobby()
plugin.lobbies[lobby.lobby_id] = lobby

print("== 1) 开赛：_enter_playing 之后群里应该有一条开局播报")
plugin._enter_playing(lobby, time.time())
assert len(qq.calls) == 1, qq.calls
event_type, message, kwargs = qq.calls[0]
assert event_type == "custom", event_type
assert "开局" in message, message
assert "ARCShooterGame" in message, message
assert "BloodShot" in message and "lowkey" in message, message
print("   开局播报 ok：", message.replace("\n", " / "))

print("\n== 2) 终局：_end_match 之后群里应该有一条终局战报，比分是终局那一刻的")
plugin._end_match(lobby, "a")
assert len(qq.calls) == 2, qq.calls
event_type, message, kwargs = qq.calls[1]
assert event_type == "custom", event_type
assert "战报" in message, message
assert "5 - 3" in message, message
assert "BloodShot 5/1/2" in message, message
assert "lowkey 3/4/1" in message, message
assert "TK1" in message, message
print("   终局战报 ok：", message.replace("\n", " / "))

print("\n== 3) 大厅已经被摘掉（_end_match 最后 lobbies.pop）")
assert lobby.lobby_id not in plugin.lobbies
print("   大厅已摘除 ok")

print("\n== 4) 关掉开关后不再发")
qq2 = FakeQQPlugin()
plugin2 = make_plugin(qq2)
plugin2.config_store.settings.values["QQ_REPORT_ENABLED"] = "0"
lobby2 = make_lobby()
plugin2.lobbies[lobby2.lobby_id] = lobby2
plugin2._enter_playing(lobby2, time.time())
plugin2._end_match(lobby2, "a")
assert qq2.calls == [], qq2.calls
print("   开关生效 ok")

print("\n== 5) 没有群服互通插件时也不许炸")
plugin3 = make_plugin(None)
lobby3 = make_lobby()
plugin3.lobbies[lobby3.lobby_id] = lobby3
plugin3._enter_playing(lobby3, time.time())
plugin3._end_match(lobby3, "a")
assert not plugin3.logger.errors, plugin3.logger.errors
print("   无群服互通插件也不炸 ok")

print("\nALL QQ REPORT SMOKE TESTS PASSED")
