# -*- coding: utf-8 -*-
"""比赛期间背包备份 / 清空 / 按格子发放。不依赖其它 ARC 插件。"""
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
    "minecraft:leather_chestplate": "chestplate",
    "minecraft:chainmail_chestplate": "chestplate",
    "minecraft:iron_chestplate": "chestplate",
    "minecraft:golden_chestplate": "chestplate",
    "minecraft:diamond_chestplate": "chestplate",
    "minecraft:netherite_chestplate": "chestplate",
    "minecraft:copper_chestplate": "chestplate",
    "minecraft:leather_leggings": "leggings",
    "minecraft:chainmail_leggings": "leggings",
    "minecraft:iron_leggings": "leggings",
    "minecraft:golden_leggings": "leggings",
    "minecraft:diamond_leggings": "leggings",
    "minecraft:netherite_leggings": "leggings",
    "minecraft:copper_leggings": "leggings",
    "minecraft:leather_boots": "boots",
    "minecraft:chainmail_boots": "boots",
    "minecraft:iron_boots": "boots",
    "minecraft:golden_boots": "boots",
    "minecraft:diamond_boots": "boots",
    "minecraft:netherite_boots": "boots",
    "minecraft:copper_boots": "boots",
}
_UNSAFE_FILE_CHARS = re.compile(r'[<>:"/\\\\|?*]')


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
    inv = getattr(player, "inventory", None)
    game_mode = getattr(player, "game_mode", None)
    gm_name = ""
    if game_mode is not None:
        gm_name = getattr(game_mode, "name", None) or str(game_mode)
    return {
        "name": getattr(player, "name", ""),
        "inventory": serialize_inventory(inv) if inv is not None else {"size": 0, "slots": []},
        "armor": serialize_armor(inv) if inv is not None else {},
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
    inv = getattr(player, "inventory", None)
    if inv is None:
        return
    for item_id, count in (extras or {}).items():
        if int(count or 0) <= 0:
            continue
        slot = ARMOR_ITEM_SLOTS.get(str(item_id))
        if slot is None or not hasattr(inv, slot):
            continue
        try:
            setattr(inv, slot, make_item_stack(str(item_id), 1, data))
        except Exception:
            continue


def remove_armor_extras(player: Any, extras: Dict[str, int]) -> None:
    inv = getattr(player, "inventory", None)
    if inv is None:
        return
    for item_id in (extras or {}).keys():
        slot = ARMOR_ITEM_SLOTS.get(str(item_id))
        if slot is None or not hasattr(inv, slot):
            continue
        try:
            existing = getattr(inv, slot, None)
            if existing is not None and _item_type_id(existing) == str(item_id):
                setattr(inv, slot, None)
        except Exception:
            continue


def make_item_stack(item_id: str, amount: int, data: int = 0) -> Any:
    from endstone.inventory import ItemStack

    return ItemStack(str(item_id), max(1, int(amount)), int(data or 0))


def set_slot_item(player: Any, slot: int, item_id: str, amount: int, data: int = 0) -> None:
    inv = player.inventory
    inv.set_item(int(slot), make_item_stack(item_id, amount, data))


def give_to_end_slots(player: Any, item_id: str, amount: int, reserved: int, data: int = 0) -> None:
    """从背包末尾向前填充空格/可堆叠格；放不下再 add_item。"""
    inv = player.inventory
    remaining = max(0, int(amount))
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
    while remaining > 0:
        put = min(remaining, 64)
        leftover = inv.add_item(make_item_stack(item_id, put, data))
        remaining -= put
        if leftover:
            break


def remove_item_count(player: Any, item_id: str, amount: int) -> int:
    """按类型从背包移除最多 amount 个，返回实际移除数量。不要求精确格子。"""
    inv = player.inventory
    remaining = max(0, int(amount))
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
        have = int(getattr(stack, "amount", 0) or 0)
        take = min(have, remaining)
        new_amount = have - take
        if new_amount <= 0:
            inv.set_item(i, None)
        else:
            stack.amount = new_amount
            inv.set_item(i, stack)
        remaining -= take
        removed += take
    return removed
