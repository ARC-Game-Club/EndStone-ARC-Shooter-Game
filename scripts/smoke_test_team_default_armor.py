# -*- coding: utf-8 -*-
"""OP 一键设置队伍默认铠甲冒烟测试（stub endstone）。

覆盖：read_player_armor 走 arc_inventory API 且保留完整 item_info（data/附魔/Lore/NBT）、
set_default_team_armor 写回 settings.yml 后 default_team_armor 读回一致（含 NBT）、
旧格式纯 id 字符串自动归一、apply_armor_slot_items 逐槽走 api_set_armor_slot、
插件 _set_team_default_armor 的 OP 校验 / 空穿戴保护 / 成功保存。
"""
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _endstone_stub_shooter as stub  # 安装 endstone stub
stub.add_src_to_path()

from endstone import Player as StubPlayer

from endstone_arc_shooter_game import inventory as inv_mod
from endstone_arc_shooter_game.arc_shooter_game_plugin import ARCShooterGamePlugin
from endstone_arc_shooter_game.config import ConfigStore, SettingManager
from endstone_arc_shooter_game.session import TEAM_A, TEAM_B

# settings.yml 等文件写进临时目录（PLUGIN_DATA_DIR 是相对 cwd 的路径），避免污染真实数据
os.chdir(tempfile.mkdtemp(prefix="arc_shooter_armor_smoke_"))


class FakeLogger:
    def __init__(self):
        self.errors = []

    def info(self, m):
        pass

    def warning(self, m):
        pass

    def error(self, m):
        self.errors.append(m)


class _ItemTypeId:
    def __init__(self, id_):
        self.id = id_


class FakeItemStack:
    def __init__(self, type_id, amount=1, data=0, enchants=None, lore=None, nbt_b64=None):
        self.type = _ItemTypeId(type_id)
        self.amount = amount
        self.data = data
        self.enchants = enchants or {}
        self.lore = lore or []
        self.nbt_b64 = nbt_b64


class FakeInventory:
    def __init__(self):
        self.size = 9
        self.slots = [None] * self.size
        for attr in inv_mod.ARMOR_ATTRS:
            setattr(self, attr, None)


class FakePlayer(StubPlayer):
    def __init__(self, name, is_op=True):
        self.name = name
        self.is_op = is_op
        self.inventory = FakeInventory()
        self.messages = []

    def send_message(self, m):
        self.messages.append(m)

    def wear(self, **slots):
        for slot, stack in slots.items():
            setattr(self.inventory, slot, stack)


class FakeArcInventory:
    """替代 arc_inventory：api_get_inventory_items 按 InventoryManager 契约返回条目。"""

    def api_get_inventory_items(
        self,
        player,
        *,
        include_armor: bool = False,
        slot_min=None,
        slot_max=None,
    ):
        items = []
        inv = player.inventory

        def entry(stack, slot_index, armor_slot=None):
            # 与 InventoryManager._build_item_entry 契约一致：空堆 / 无 type 不吐条目
            if stack is None or getattr(stack, "type", None) is None:
                return
            if int(getattr(stack, "amount", 0) or 0) <= 0:
                return
            item = {
                "type": stack.type.id,
                "count": stack.amount,
                "data": getattr(stack, "data", 0),
                "slot_index": slot_index,
            }
            if stack.enchants:
                item["enchants"] = dict(stack.enchants)
            if stack.lore:
                item["lore"] = list(stack.lore)
            if stack.nbt_b64:
                item["nbt_b64"] = stack.nbt_b64
            if armor_slot:
                item["armor_slot"] = armor_slot
            items.append(item)

        for i in range(inv.size):
            entry(inv.slots[i], i)
        if include_armor:
            for attr in inv_mod.ARMOR_ATTRS:
                entry(getattr(inv, attr, None), attr, armor_slot=attr)
        return items


class RecordingArcInventory(FakeArcInventory):
    """额外记录 api_set_armor_slot 写入，验证发放 item_info 完整。"""

    def __init__(self):
        self.armor_writes = []

    def api_set_armor_slot(self, player, armor_slot, item_info):
        self.armor_writes.append((player.name, armor_slot, dict(item_info or {})))
        return True


def make_store():
    store = object.__new__(ConfigStore)
    store.logger = FakeLogger()
    store.settings = SettingManager()
    return store


def make_plugin(store):
    plugin = object.__new__(ARCShooterGamePlugin)
    plugin.logger = FakeLogger()
    plugin.config_store = store
    plugin._t = lambda key: key
    plugin._show_root_menu = lambda p: None
    return plugin


# 全程绑定假背包管理器：读取/发放都必须走 arc_inventory API
inv_mod.bind_arc_inventory(FakeArcInventory())

print("== 1) read_player_armor：只收四个护甲槽，且保留 data/附魔/Lore/NBT")
steve = FakePlayer("Steve")
steve.wear(
    helmet=FakeItemStack(
        "arc:6b47_helmet_red", enchants={"protection": 2}, lore=["红队盔"], nbt_b64="abc123=="
    ),
    chestplate=FakeItemStack("arc:6b45_vest"),
    leggings=FakeItemStack("arc:emr_suit_red", data=1),
    boots=FakeItemStack("arc:balaclava"),
)
steve.inventory.item_in_off_hand = FakeItemStack("minecraft:shield")  # 不该被收进来
worn = inv_mod.read_player_armor(steve)
assert worn == {
    "helmet": {
        "type": "arc:6b47_helmet_red",
        "enchants": {"protection": 2},
        "lore": ["红队盔"],
        "nbt_b64": "abc123==",
        "count": 1,
    },
    "chestplate": {"type": "arc:6b45_vest", "count": 1},
    "leggings": {"type": "arc:emr_suit_red", "data": 1, "count": 1},
    "boots": {"type": "arc:balaclava", "count": 1},
}, worn

steve.inventory.chestplate = FakeItemStack("minecraft:air")
steve.inventory.leggings = FakeItemStack("arc:emr_suit_red", amount=0)
assert inv_mod.read_player_armor(steve) == {
    "helmet": {
        "type": "arc:6b47_helmet_red",
        "enchants": {"protection": 2},
        "lore": ["红队盔"],
        "nbt_b64": "abc123==",
        "count": 1,
    },
    "boots": {"type": "arc:balaclava", "count": 1},
}
print("   槽位过滤 + 完整 item_info ok")

print("\n== 2) ConfigStore 往返：set → default 读回一致（含 NBT），另一队不受影响")
store = make_store()
default_a_before = store.default_team_armor(TEAM_A)
assert default_a_before["helmet"]["type"] == "arc:6b47_helmet_red", default_a_before  # settings.yml 自带默认（旧格式归一）

store.set_default_team_armor(TEAM_A, worn)
assert store.default_team_armor(TEAM_A) == worn, store.default_team_armor(TEAM_A)
assert store.default_team_armor(TEAM_B)["helmet"]["type"] == "arc:6b47_helmet_blue"

raw = Path("plugins/ARCShooterGame/settings.yml").read_text(encoding="utf-8")
assert "TEAM_A_DEFAULT_ARMOR=" in raw and "abc123==" in raw, raw
print("   往返 + NBT 落盘 + 蓝方隔离 ok")

print("\n== 3) 旧格式兼容：纯 id 字符串自动归一为 item_info")
store.settings.SetSetting(
    "TEAM_A_DEFAULT_ARMOR",
    '{"helmet":"arc:6b47_helmet_red","chestplate":"arc:6b45_vest"}',
)
assert store.default_team_armor(TEAM_A) == {
    "helmet": {"type": "arc:6b47_helmet_red", "count": 1},
    "chestplate": {"type": "arc:6b45_vest", "count": 1},
}, store.default_team_armor(TEAM_A)
print("   旧格式归一 ok")

print("\n== 4) apply_armor_slot_items：逐槽走 api_set_armor_slot，item_info 完整且 count=1")
rec = RecordingArcInventory()
inv_mod.bind_arc_inventory(rec)
alex = FakePlayer("Alex")
inv_mod.apply_armor_slot_items(
    alex,
    {
        "helmet": {"type": "arc:6b47_helmet_blue", "nbt_b64": "zz==", "name": "不该带出去"},
        "chestplate": {"type": ""},
    },
)
assert rec.armor_writes == [
    ("Alex", "helmet", {"type": "arc:6b47_helmet_blue", "nbt_b64": "zz==", "count": 1})
], rec.armor_writes
inv_mod.bind_arc_inventory(FakeArcInventory())
print("   逐槽发放 ok")

print("\n== 5) 插件处理器：OP 穿好铠甲 → 一键存为蓝方默认（NBT 落盘）")
alex.wear(
    helmet=FakeItemStack("arc:6b47_helmet_blue", nbt_b64="blue-nbt=="),
    chestplate=FakeItemStack("arc:6b45_vest"),
    leggings=FakeItemStack("arc:emr_suit_blue"),
)
plugin = make_plugin(store)
plugin._set_team_default_armor(alex, TEAM_B)
assert store.default_team_armor(TEAM_B) == {
    "helmet": {"type": "arc:6b47_helmet_blue", "nbt_b64": "blue-nbt==", "count": 1},
    "chestplate": {"type": "arc:6b45_vest", "count": 1},
    "leggings": {"type": "arc:emr_suit_blue", "count": 1},
}, store.default_team_armor(TEAM_B)
raw = Path("plugins/ARCShooterGame/settings.yml").read_text(encoding="utf-8")
assert "TEAM_B_DEFAULT_ARMOR=" in raw and "blue-nbt==" in raw, raw
assert any(m.startswith("ARMOR_SET_OK") for m in alex.messages), alex.messages
assert not plugin.logger.errors
print("   蓝方保存 ok")

print("\n== 6) 插件处理器：没穿铠甲 → 提示且不覆盖旧配置")
before_a = store.default_team_armor(TEAM_A)
empty = FakePlayer("Empty")
plugin._set_team_default_armor(empty, TEAM_A)
assert any(m == "ARMOR_SET_EMPTY" for m in empty.messages), empty.messages
assert store.default_team_armor(TEAM_A) == before_a
print("   空穿戴保护 ok")

print("\n== 7) 插件处理器：非 OP → 拒绝且不改配置")
mallory = FakePlayer("Mallory", is_op=False)
mallory.wear(helmet=FakeItemStack("arc:6b47_helmet_red"))
plugin._set_team_default_armor(mallory, TEAM_A)
assert any(m == "CMD_NO_PERMISSION" for m in mallory.messages), mallory.messages
assert store.default_team_armor(TEAM_A) == before_a
print("   权限校验 ok")

print("\n== 8) 未绑定背包管理器 → 读取返回空、发放静默跳过，不自己兜底")
inv_mod.bind_arc_inventory(None)
nobody = FakePlayer("Nobody")
nobody.wear(helmet=FakeItemStack("arc:6b47_helmet_red"))
assert inv_mod.read_player_armor(nobody) == {}
inv_mod.apply_armor_slot_items(nobody, {"helmet": {"type": "arc:6b47_helmet_red"}})
inv_mod.bind_arc_inventory(FakeArcInventory())
print("   仅走 arc_inventory API ok")

print("\nALL TEAM DEFAULT ARMOR SMOKE TESTS PASSED")
