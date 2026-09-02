# -*- coding: utf-8 -*-
"""比赛期间背包备份 / 清空 / 按格子发放。

布局相关操作（热键定点、护甲、整包快照）优先走弧光背包管理器 API；
本模块保留磁盘备份与位置/模式等枪战域数据，并在未绑定管理器时本地回退。
"""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from endstone_arc_shooter_game.language import PLUGIN_DATA_DIR

ARMOR_ATTRS = ("helmet", "chestplate", "leggings", "boots", "item_in_off_hand")
ARMOR_ITEM_SLOTS = {
    "minecraft:leather_helmet": "helmet",
    "minecraft:chainmail_helmet": "helmet",
    "minecraft:iron_helmet": "helmet",
    "minecraft:golden_helmet": "helmet",
    "minecraft:diamond_helmet": "helmet",
    "minecraft:netherite_helmet": "helmet",
    "minecraft:copper_helmet": "helmet",
    "arc:6b47_helmet": "helmet",
    "minecraft:leather_chestplate": "chestplate",
    "minecraft:chainmail_chestplate": "chestplate",
    "minecraft:iron_chestplate": "chestplate",
    "minecraft:golden_chestplate": "chestplate",
    "minecraft:diamond_chestplate": "chestplate",
    "minecraft:netherite_chestplate": "chestplate",
    "minecraft:copper_chestplate": "chestplate",
    "arc:6b45_vest": "chestplate",
    "minecraft:leather_leggings": "leggings",
    "minecraft:chainmail_leggings": "leggings",
    "minecraft:iron_leggings": "leggings",
    "minecraft:golden_leggings": "leggings",
    "minecraft:diamond_leggings": "leggings",
    "minecraft:netherite_leggings": "leggings",
    "minecraft:copper_leggings": "leggings",
    "arc:emr_suit": "leggings",
    "minecraft:leather_boots": "boots",
    "minecraft:chainmail_boots": "boots",
    "minecraft:iron_boots": "boots",
    "minecraft:golden_boots": "boots",
    "minecraft:diamond_boots": "boots",
    "minecraft:netherite_boots": "boots",
    "minecraft:copper_boots": "boots",
    "arc:balaclava": "boots",
}
_UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\\\|?*]')

# 由枪战插件 on_enable 注入 arc_inventory 插件实例
_arc_inventory: Any = None


def bind_arc_inventory(plugin: Any) -> None:
    global _arc_inventory
    _arc_inventory = plugin


def get_arc_inventory() -> Any:
    return _arc_inventory


def _inventory_manager() -> Any:
    plugin = _arc_inventory
    if plugin is None:
        return None
    getter = getattr(plugin, "api_get_inventory_manager", None)
    if callable(getter):
        try:
            return getter()
        except Exception:
            return None
    return getattr(plugin, "inventory_manager", None)


def backup_dir() -> Path:
    path = PLUGIN_DATA_DIR / "backups"
    path.mkdir(parents=True, exist_ok=True)
    return path


def backup_path_for(player_name: str) -> Path:
    safe = _UNSAFE_FILE_CHARS.sub("_", player_name or "unknown")
    return backup_dir() / f"{safe}.json"


def _item_type_id(stack: Any) -> str:
    item_type = getattr(stack, "type", None)
    if item_type is None:
        return ""
    ident = getattr(item_type, "id", None)
    if ident:
        return str(ident)
    return str(item_type)


def serialize_item(stack: Any) -> Optional[Dict[str, Any]]:
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_serialize_item"):
        try:
            return plugin.api_serialize_item(stack)
        except Exception:
            pass
    mgr = _inventory_manager()
    if mgr is not None and hasattr(mgr, "serialize_item"):
        try:
            return mgr.serialize_item(stack)
        except Exception:
            pass
    if stack is None:
        return None
    try:
        if int(getattr(stack, "amount", 0) or 0) <= 0:
            return None
        type_id = _item_type_id(stack)
        if not type_id or type_id == "minecraft:air":
            return None
        entry: Dict[str, Any] = {
            "type": type_id,
            "count": int(stack.amount),
            "data": int(getattr(stack, "data", 0) or 0),
        }
        nbt = getattr(stack, "nbt", None)
        if nbt is not None:
            try:
                raw = nbt.dump(byte_order="little")
                if raw:
                    entry["nbt_b64"] = base64.b64encode(raw).decode("ascii")
            except Exception:
                pass
        return entry
    except Exception:
        return None


def deserialize_item(data: Optional[Dict[str, Any]]) -> Any:
    if not data:
        return None
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_make_item_stack"):
        try:
            stack = plugin.api_make_item_stack(data)
            if stack is not None:
                return stack
        except Exception:
            pass
    mgr = _inventory_manager()
    if mgr is not None and hasattr(mgr, "make_item_stack"):
        try:
            stack = mgr.make_item_stack(data)
            if stack is not None:
                return stack
        except Exception:
            pass
    type_id = data.get("type")
    if not type_id or type_id == "minecraft:air":
        return None
    from endstone.inventory import ItemStack

    stack = ItemStack(str(type_id), int(data.get("count", 1) or 1), int(data.get("data", 0) or 0))
    nbt_b64 = data.get("nbt_b64")
    if nbt_b64:
        try:
            from endstone.nbt import load

            tag, _name = load(base64.b64decode(nbt_b64), byte_order="little")
            if tag is not None and hasattr(stack, "nbt"):
                stack.nbt = tag
        except Exception:
            pass
    return stack


def serialize_inventory(inv: Any) -> Dict[str, Any]:
    slots: List[Optional[Dict[str, Any]]] = []
    size = int(getattr(inv, "size", 0) or 0)
    for i in range(size):
        try:
            slots.append(serialize_item(inv.get_item(i)))
        except Exception:
            slots.append(None)
    return {"size": size, "slots": slots}


def apply_inventory(inv: Any, saved: Dict[str, Any]) -> None:
    if hasattr(inv, "clear"):
        inv.clear()
    slots = saved.get("slots") or []
    size = int(getattr(inv, "size", 0) or 0)
    for i, slot in enumerate(slots):
        if i >= size:
            break
        item = deserialize_item(slot)
        try:
            inv.set_item(i, item)
        except Exception:
            continue


def serialize_armor(inv: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for attr in ARMOR_ATTRS:
        if hasattr(inv, attr):
            out[attr] = serialize_item(getattr(inv, attr, None))
    return out


def apply_armor(inv: Any, saved: Dict[str, Any]) -> None:
    for attr in ARMOR_ATTRS:
        if not hasattr(inv, attr):
            continue
        try:
            setattr(inv, attr, deserialize_item(saved.get(attr) if saved else None))
        except Exception:
            try:
                setattr(inv, attr, None)
            except Exception:
                pass


def clear_player_inventory(player: Any) -> None:
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_clear_inventory"):
        try:
            if plugin.api_clear_inventory(player, include_contents=True, include_armor=True):
                return
        except Exception:
            pass
    inv = getattr(player, "inventory", None)
    if inv is None:
        return
    if hasattr(inv, "clear"):
        inv.clear()
    for attr in ARMOR_ATTRS:
        if hasattr(inv, attr):
            try:
                setattr(inv, attr, None)
            except Exception:
                pass


def snapshot_player(player: Any, dimension_id: str) -> Dict[str, Any]:
    loc = getattr(player, "location", None)
    game_mode = getattr(player, "game_mode", None)
    gm_name = ""
    if game_mode is not None:
        gm_name = getattr(game_mode, "name", None) or str(game_mode)

    inv_snap: Dict[str, Any] = {"size": 0, "slots": []}
    armor_snap: Dict[str, Any] = {}
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_snapshot_inventory"):
        try:
            snap = plugin.api_snapshot_inventory(player, include_armor=True) or {}
            inv_snap = {
                "size": int(snap.get("size", 0) or 0),
                "slots": list(snap.get("slots") or []),
            }
            armor_snap = dict(snap.get("armor") or {})
        except Exception:
            inv = getattr(player, "inventory", None)
            if inv is not None:
                inv_snap = serialize_inventory(inv)
                armor_snap = serialize_armor(inv)
    else:
        inv = getattr(player, "inventory", None)
        if inv is not None:
            inv_snap = serialize_inventory(inv)
            armor_snap = serialize_armor(inv)

    return {
        "name": getattr(player, "name", ""),
        "inventory": inv_snap,
        "armor": armor_snap,
        "location": {
            "x": float(getattr(loc, "x", 0) or 0),
            "y": float(getattr(loc, "y", 64) or 64),
            "z": float(getattr(loc, "z", 0) or 0),
            "yaw": float(getattr(loc, "yaw", 0) or 0),
            "pitch": float(getattr(loc, "pitch", 0) or 0),
            "dimension": dimension_id,
        },
        "game_mode": gm_name,
    }


def restore_inventory(player: Any, snapshot: Dict[str, Any]) -> None:
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_restore_inventory"):
        try:
            if plugin.api_restore_inventory(player, snapshot, include_armor=True):
                return
        except Exception:
            pass
    inv = getattr(player, "inventory", None)
    if inv is None:
        return
    apply_inventory(inv, snapshot.get("inventory") or {})
    apply_armor(inv, snapshot.get("armor") or {})


def save_snapshot_disk(player_name: str, snapshot: Dict[str, Any]) -> None:
    path = backup_path_for(player_name)
    path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")


def load_snapshot_disk(player_name: str) -> Optional[Dict[str, Any]]:
    path = backup_path_for(player_name)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def delete_snapshot_disk(player_name: str) -> None:
    path = backup_path_for(player_name)
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass


def clear_armor(player: Any) -> None:
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_clear_inventory"):
        try:
            if plugin.api_clear_inventory(
                player, include_contents=False, include_armor=True
            ):
                return
        except Exception:
            pass
    inv = getattr(player, "inventory", None)
    if inv is None:
        return
    for attr in ARMOR_ATTRS:
        if hasattr(inv, attr):
            try:
                setattr(inv, attr, None)
            except Exception:
                pass


def apply_armor_extras(player: Any, extras: Dict[str, int], data: int = 0) -> None:
    plugin = _arc_inventory
    for item_id, count in (extras or {}).items():
        if int(count or 0) <= 0:
            continue
        slot = ARMOR_ITEM_SLOTS.get(str(item_id))
        if slot is None:
            continue
        item_info = {
            "type": str(item_id),
            "count": 1,
            "data": int(data or 0),
        }
        if plugin is not None and hasattr(plugin, "api_set_armor_slot"):
            try:
                plugin.api_set_armor_slot(player, slot, item_info)
                continue
            except Exception:
                pass
        if plugin is not None and hasattr(plugin, "api_give_item"):
            try:
                plugin.api_give_item(player, item_info, armor_slot=slot)
                continue
            except Exception:
                pass
        inv = getattr(player, "inventory", None)
        if inv is None or not hasattr(inv, slot):
            continue
        try:
            setattr(inv, slot, make_item_stack(str(item_id), 1, data))
        except Exception:
            continue


def remove_armor_extras(player: Any, extras: Dict[str, int]) -> None:
    plugin = _arc_inventory
    inv = getattr(player, "inventory", None)
    for item_id in (extras or {}).keys():
        slot = ARMOR_ITEM_SLOTS.get(str(item_id))
        if slot is None:
            continue
        existing = None
        if inv is not None and hasattr(inv, slot):
            try:
                existing = getattr(inv, slot, None)
            except Exception:
                existing = None
        if existing is None or _item_type_id(existing) != str(item_id):
            continue
        if plugin is not None and hasattr(plugin, "api_set_armor_slot"):
            try:
                plugin.api_set_armor_slot(player, slot, None)
                continue
            except Exception:
                pass
        if inv is None:
            continue
        try:
            setattr(inv, slot, None)
        except Exception:
            continue


def make_item_stack(item_id: str, amount: int, data: int = 0) -> Any:
    item_info = {
        "type": str(item_id),
        "count": max(1, int(amount)),
        "data": int(data or 0),
    }
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_make_item_stack"):
        try:
            stack = plugin.api_make_item_stack(item_info)
            if stack is not None:
                return stack
        except Exception:
            pass
    mgr = _inventory_manager()
    if mgr is not None and hasattr(mgr, "make_item_stack"):
        try:
            return mgr.make_item_stack(item_info)
        except Exception:
            pass
    from endstone.inventory import ItemStack

    return ItemStack(str(item_id), max(1, int(amount)), int(data or 0))


def set_slot_item(player: Any, slot: int, item_id: str, amount: int, data: int = 0) -> None:
    item_info = {
        "type": str(item_id),
        "count": max(1, int(amount)),
        "data": int(data or 0),
    }
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_set_slot"):
        try:
            if plugin.api_set_slot(player, int(slot), item_info):
                return
        except Exception:
            pass
    if plugin is not None and hasattr(plugin, "api_give_item_count"):
        try:
            if plugin.api_give_item_count(player, item_info, slot=int(slot)) > 0:
                return
        except Exception:
            pass
    inv = player.inventory
    inv.set_item(int(slot), make_item_stack(item_id, amount, data))


def give_item(player: Any, item_id: str, amount: int, data: int = 0) -> int:
    """通过 arc_inventory 发放；未绑定时退回 add_item。返回实际入包数量。"""
    amount = max(0, int(amount))
    if amount <= 0:
        return 0
    item_info = {"type": str(item_id), "count": amount, "data": int(data or 0)}
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_give_item_count"):
        try:
            return int(plugin.api_give_item_count(player, item_info) or 0)
        except Exception:
            pass
    mgr = _inventory_manager()
    if mgr is not None:
        try:
            return int(mgr.give_item_count(player, item_info) or 0)
        except Exception:
            pass
    inv = player.inventory
    remaining = amount
    given = 0
    while remaining > 0:
        put = min(remaining, 64)
        leftover = inv.add_item(make_item_stack(item_id, put, data))
        if leftover:
            break
        remaining -= put
        given += put
    return given


def give_to_end_slots(player: Any, item_id: str, amount: int, reserved: int, data: int = 0) -> None:
    """从背包末尾向前填充，避开前 reserved 格（武器热键）。"""
    amount = max(0, int(amount))
    if amount <= 0:
        return
    item_info = {"type": str(item_id), "count": amount, "data": int(data or 0)}
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_give_item_count"):
        try:
            plugin.api_give_item_count(
                player,
                item_info,
                reserved=int(reserved or 0),
                prefer_end=True,
            )
            return
        except Exception:
            pass
    inv = player.inventory
    remaining = amount
    size = int(getattr(inv, "size", 0) or 0)
    start = max(int(reserved), 0)
    for i in range(size - 1, start - 1, -1):
        if remaining <= 0:
            break
        try:
            existing = inv.get_item(i)
        except Exception:
            continue
        if existing is None or not _item_type_id(existing) or int(getattr(existing, "amount", 0) or 0) <= 0:
            put = min(remaining, 64)
            inv.set_item(i, make_item_stack(item_id, put, data))
            remaining -= put
            continue
        if _item_type_id(existing) != item_id:
            continue
        space = 64 - int(existing.amount)
        if space <= 0:
            continue
        put = min(space, remaining)
        existing.amount = int(existing.amount) + put
        inv.set_item(i, existing)
        remaining -= put
    if remaining > 0:
        give_item(player, item_id, remaining, data)


def remove_item_count(player: Any, item_id: str, amount: int, data: int = 0) -> int:
    """按类型从背包移除最多 amount 个，优先走 arc_inventory。"""
    amount = max(0, int(amount))
    if amount <= 0:
        return 0
    item_info = {"type": str(item_id), "count": amount, "data": int(data or 0)}
    plugin = _arc_inventory
    if plugin is not None and hasattr(plugin, "api_remove_item"):
        try:
            return int(
                plugin.api_remove_item(player, item_info, partial=True) or 0
            )
        except TypeError:
            # 旧版无 partial 参数：先统计再精确扣
            try:
                have = 0
                for entry in plugin.api_get_inventory_items(player) or []:
                    if str(entry.get("type") or "") != str(item_id):
                        continue
                    if int(entry.get("data", 0) or 0) != int(data or 0):
                        continue
                    have += int(entry.get("count", 0) or 0)
                take = min(have, amount)
                if take > 0 and plugin.api_remove_item(
                    player, {"type": str(item_id), "count": take, "data": int(data or 0)}
                ):
                    return take
            except Exception:
                pass
        except Exception:
            pass
    mgr = _inventory_manager()
    if mgr is not None:
        try:
            return int(mgr.remove_item(player, item_info, partial=True) or 0)
        except TypeError:
            try:
                if mgr.remove_item(player, item_info):
                    return amount
            except Exception:
                pass
        except Exception:
            pass

    inv = player.inventory
    remaining = amount
    removed = 0
    size = int(getattr(inv, "size", 0) or 0)
    for i in range(size):
        if remaining <= 0:
            break
        try:
            stack = inv.get_item(i)
        except Exception:
            continue
        if stack is None or _item_type_id(stack) != item_id:
            continue
        if int(getattr(stack, "data", 0) or 0) != int(data or 0):
            continue
        have_slot = int(getattr(stack, "amount", 0) or 0)
        take_slot = min(have_slot, remaining)
        new_amount = have_slot - take_slot
        if new_amount <= 0:
            inv.set_item(i, None)
        else:
            stack.amount = new_amount
            inv.set_item(i, stack)
        remaining -= take_slot
        removed += take_slot
    return removed
