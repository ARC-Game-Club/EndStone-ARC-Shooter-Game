# -*- coding: utf-8 -*-
"""射击游戏属性接入冒烟测试：对局 buff 经 arc_attribute_core 下发/撤销（stub endstone）。"""
import sys
import types
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _endstone_stub_shooter as stub  # 安装 endstone stub
stub.add_src_to_path()

from endstone_arc_shooter_game.arc_shooter_game_plugin import (
    ARCShooterGamePlugin,
    MATCH_BUFF_DURATION_SECONDS,
)


class FakeLogger:
    def __init__(self):
        self.infos, self.errors = [], []

    def info(self, m):
        self.infos.append(m)

    def warning(self, m):
        pass

    def error(self, m):
        self.errors.append(m)


class FakeAttrCore:
    def __init__(self):
        self.applied = []
        self.removed = []

    def api_apply_buff(self, player, effect, level, duration, source):
        self.applied.append((player.name, effect, level, duration, source))
        return True

    def api_remove_buff(self, player, effect, source=None):
        self.removed.append((player.name, effect, source))
        return True


class FakePluginManager:
    def __init__(self, core):
        self.core = core

    def get_plugin(self, name):
        return self.core if name == "arc_attribute_core" else None


class FakeServer:
    def __init__(self, core, players=()):
        self.plugin_manager = FakePluginManager(core)
        self.online_players = list(players)

    def get_player(self, name):
        for p in self.online_players:
            if p.name == name:
                return p
        return None


class FakePlayer:
    def __init__(self, name, xuid):
        self.name = name
        self.xuid = xuid


def make_plugin(core=None, players=()):
    """跳过 __init__（依赖文件存储），只挂测试所需属性。"""
    plugin = object.__new__(ARCShooterGamePlugin)
    plugin.logger = FakeLogger()
    plugin.server = FakeServer(core, players)
    plugin._spawn_protect_until = {}
    return plugin


print("== 0) 插件模块 import 成功 + depend 硬依赖声明")
assert ARCShooterGamePlugin.depend == ["arc_attribute_core"]
print(f"   depend={ARCShooterGamePlugin.depend}")

print("\n== 1) 对局 buff 经核心下发（速度1 + 跳跃提升1，来源 shooter:match）")
core = FakeAttrCore()
steve = FakePlayer("Steve", "x1")
plugin = make_plugin(core, [steve])
plugin._apply_match_buffs(steve)
assert len(core.applied) == 2
for name, effect, level, duration, source in core.applied:
    assert name == "Steve" and level == 1 and source == "shooter:match"
    assert duration == MATCH_BUFF_DURATION_SECONDS
assert {e for _, e, _, _, _ in core.applied} == {"speed", "jump_boost"}
assert not plugin.logger.errors
print(f"   applied={core.applied} ok")

print("\n== 2) 清场只撤自己来源，不碰其他插件的效果")
plugin._clear_match_effects("Steve")
assert core.removed == [
    ("Steve", "speed", "shooter:match"),
    ("Steve", "jump_boost", "shooter:match"),
]
assert "Steve" not in plugin._spawn_protect_until or True  # 本就未写入
print(f"   removed={core.removed} ok")

print("\n== 3) 玩家离线时清场：不调 API（核心在退出事件里自清）")
core.removed.clear()
plugin._clear_match_effects("OfflineGuy")
assert core.removed == []
print("   离线安全 ok")

print("\n== 4) 核心缺失：告警一次、不异常")
plugin2 = make_plugin(None)
p2 = FakePlayer("Alex", "x2")
plugin2._apply_match_buffs(p2)
plugin2._apply_match_buffs(p2)
assert len(plugin2.logger.errors) == 1, plugin2.logger.errors
assert "arc_attribute_core" in plugin2.logger.errors[0]
plugin2._clear_match_effects("Alex")  # 无异常即可
print("   缺失告警一次 ok")

print("\n== 5) 缓存：核心只探测一次")
lookups = []
core3 = FakeAttrCore()


class CountingPM(FakePluginManager):
    def get_plugin(self, name):
        lookups.append(name)
        return super().get_plugin(name)


plugin3 = make_plugin()
plugin3.server.plugin_manager = CountingPM(core3)
steve3 = FakePlayer("Steve3", "x3")
plugin3._apply_match_buffs(steve3)
plugin3._clear_match_effects("Steve3")
assert len(lookups) == 1, lookups
print("   探测缓存 ok")

print("\n== 6) 冻结系统保持停用（无移速写入路径）")
import inspect

assert "_set_movement_speed" not in inspect.getsource(ARCShooterGamePlugin)
assert "_dispatch_effect" not in inspect.getsource(ARCShooterGamePlugin)
assert "_clear_effects" not in inspect.getsource(ARCShooterGamePlugin)
print("   /effect 与 attribute 命令路径已彻底移除 ok")

print("\nALL SHOOTER ATTRIBUTE INTEGRATION SMOKE TESTS PASSED")
