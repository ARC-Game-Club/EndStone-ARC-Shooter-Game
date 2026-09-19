# -*- coding: utf-8 -*-
"""比赛结束背包还原冒烟测试：after_match=True 也必须还原赛前快照（stub endstone）。

回归背景：v0.2.2 起 _restore_player(after_match=True) 只 /clear 不还原，
对局结束/中途退赛时赛前背包被静默丢弃（死着结束的反而走 pending 恢复了）。
"""
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _endstone_stub_shooter as stub  # 安装 endstone stub
stub.add_src_to_path()

from endstone_arc_shooter_game import inventory as inv_mod
from endstone_arc_shooter_game.arc_shooter_game_plugin import ARCShooterGamePlugin

# 快照磁盘文件写进临时目录，避免污染真实插件数据目录
inv_mod.PLUGIN_DATA_DIR = Path(tempfile.mkdtemp(prefix="arc_shooter_smoke_"))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def info(self, m):
        pass

    def warning(self, m):
        pass

    def error(self, m):
        self.errors.append(m)


class FakeInventory:
    def __init__(self):
        self.size = 9
        self.slots = [None] * 9
        for attr in inv_mod.ARMOR_ATTRS:
            setattr(self, attr, None)

    def clear(self):
        self.slots = [None] * self.size

    def get_item(self, i):
        return self.slots[i]

    def set_item(self, i, item):
        self.slots[i] = item


class FakePlayer:
    def __init__(self, name, health=20.0):
        self.name = name
        self.health = health
        self.inventory = FakeInventory()
        self.messages = []

    def send_message(self, m):
        self.messages.append(m)


class FakeArcInventory:
    """替代 arc_inventory：按快照整包覆盖玩家背包与护甲。"""

    def __init__(self):
        self.restores = []

    def api_restore_inventory(self, player, snapshot, include_armor=True):
        self.restores.append((player.name, snapshot, include_armor))
        fake_inv = player.inventory
        fake_inv.clear()
        slots = (snapshot.get("inventory") or {}).get("slots") or []
        for i, slot in enumerate(slots):
            if i < fake_inv.size:
                fake_inv.slots[i] = slot
        for attr, val in (snapshot.get("armor") or {}).items():
            setattr(fake_inv, attr, val)
        return True


class FakeServer:
    def __init__(self, players=()):
        self.online_players = list(players)
        self.command_sender = "CONSOLE"
        self.commands = []

    def dispatch_command(self, sender, cmd):
        self.commands.append(cmd)
        if cmd.startswith("clear "):
            target = cmd.split(" ", 1)[1]
            for p in self.online_players:
                if p.name == target:
                    p.inventory.clear()
                    for attr in inv_mod.ARMOR_ATTRS:
                        setattr(p.inventory, attr, None)

    def get_player(self, name):
        for p in self.online_players:
            if p.name == name:
                return p
        return None


def make_plugin(arc, players):
    """跳过 __init__（依赖文件存储），只挂测试所需属性。"""
    plugin = object.__new__(ARCShooterGamePlugin)
    plugin.logger = FakeLogger()
    plugin.server = FakeServer(players)
    plugin.backups = {}
    plugin._pending_restore = set()
    plugin._t = lambda key, **kw: key
    return plugin


def sample_snapshot(name):
    return {
        "name": name,
        "inventory": {
            "size": 9,
            "slots": [
                {"type": "minecraft:iron_sword", "count": 1, "data": 0},
                *([None] * 7),
                {"type": "minecraft:apple", "count": 5, "data": 0},
            ],
        },
        "armor": {
            "helmet": {"type": "minecraft:iron_helmet", "count": 1, "data": 0},
            "chestplate": None,
            "leggings": None,
            "boots": None,
            "item_in_off_hand": None,
        },
        "location": {"x": 1.0, "y": 64.0, "z": 2.0, "yaw": 0.0, "pitch": 0.0, "dimension": "overworld"},
        "game_mode": "survival",
    }


arc = FakeArcInventory()
inv_mod.bind_arc_inventory(arc)

print("== 1) 对局结束（存活）：先 /clear 对局物品，再还原赛前快照")
steve = FakePlayer("Steve")
steve.inventory.slots[0] = {"type": "arc:match_gun", "count": 1, "data": 0}  # 对局物品
steve.inventory.helmet = {"type": "arc:6b47_helmet_red", "count": 1, "data": 0}  # 队色护甲
plugin = make_plugin(arc, [steve])
snap = sample_snapshot("Steve")
plugin.backups["Steve"] = snap
inv_mod.save_snapshot_disk("Steve", snap)

plugin._restore_player(steve, after_match=True)

assert plugin.server.commands[0].startswith("clear Steve"), plugin.server.commands
assert arc.restores == [("Steve", snap, True)], arc.restores
assert steve.inventory.slots[0] == {"type": "minecraft:iron_sword", "count": 1, "data": 0}
assert steve.inventory.slots[8] == {"type": "minecraft:apple", "count": 5, "data": 0}
assert steve.inventory.helmet == {"type": "minecraft:iron_helmet", "count": 1, "data": 0}
assert "Steve" not in plugin.backups
assert not inv_mod.load_snapshot_disk("Steve"), "磁盘快照应已删除"
assert steve.messages and steve.messages[-1] == "RESTORED"
assert not plugin.logger.errors
print("   快照已还原 + 磁盘清理 ok")

print("\n== 2) 对局结束（死亡）：进 pending 延迟到重生，不消费快照")
arc.restores.clear()
alex = FakePlayer("Alex", health=0.0)
plugin2 = make_plugin(arc, [alex])
snap2 = sample_snapshot("Alex")
plugin2.backups["Alex"] = snap2
inv_mod.save_snapshot_disk("Alex", snap2)

plugin2._restore_player(alex, after_match=True)
assert "Alex" in plugin2._pending_restore
assert arc.restores == [], "死亡时不该立即还原"
assert plugin2.server.commands == [], "死亡时不该 /clear"
assert inv_mod.load_snapshot_disk("Alex") is not None, "快照必须保留待重生"

plugin2._restore_player(alex, force=True)
assert "Alex" not in plugin2._pending_restore
assert arc.restores == [("Alex", snap2, True)]
assert not inv_mod.load_snapshot_disk("Alex")
print("   延迟还原 ok")

print("\n== 3) 掉线重连恢复（after_match=False）：直接还原，不发 /clear")
arc.restores.clear()
bob = FakePlayer("Bob")
plugin3 = make_plugin(arc, [bob])
snap3 = sample_snapshot("Bob")
inv_mod.save_snapshot_disk("Bob", snap3)

plugin3._restore_player(bob)
assert arc.restores == [("Bob", snap3, True)]
assert not any(c.startswith("clear") for c in plugin3.server.commands)
assert not inv_mod.load_snapshot_disk("Bob")
print("   崩溃恢复语义不变 ok")

inv_mod.bind_arc_inventory(None)
print("\nALL MATCH END RESTORE SMOKE TESTS PASSED")
