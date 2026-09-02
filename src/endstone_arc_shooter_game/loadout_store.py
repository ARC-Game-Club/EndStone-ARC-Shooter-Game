# -*- coding: utf-8 -*-
"""玩家军械库配装持久化：每名玩家 5 套预设（SQLite）。"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from endstone_arc_shooter_game.language import PLUGIN_DATA_DIR

PRESET_COUNT = 5

_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_loadout_presets (
    name TEXT NOT NULL,
    slot INTEGER NOT NULL,
    primary_id TEXT,
    secondary_id TEXT,
    melee_id TEXT,
    armor_id TEXT,
    gadget0 TEXT,
    gadget1 TEXT,
    updated_at REAL NOT NULL DEFAULT 0,
    PRIMARY KEY (name, slot)
);
CREATE TABLE IF NOT EXISTS player_loadout_active (
    name TEXT PRIMARY KEY,
    active_slot INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS player_loadout (
    name TEXT PRIMARY KEY,
    primary_id TEXT,
    secondary_id TEXT,
    melee_id TEXT,
    armor_id TEXT,
    gadget0 TEXT,
    gadget1 TEXT,
    updated_at REAL NOT NULL DEFAULT 0
);
"""


@dataclass
class SavedLoadout:
    name: str
    primary_id: Optional[str] = None
    secondary_id: Optional[str] = None
    melee_id: Optional[str] = None
    armor_id: Optional[str] = None
    gadgets: List[Optional[str]] = field(default_factory=list)
    slot: int = 0

    def slot_weapon(self, slot: str, index: int = 0) -> Optional[str]:
        if slot == "primary":
            return self.primary_id
        if slot == "secondary":
            return self.secondary_id
        if slot == "melee":
            return self.melee_id
        if slot == "armor":
            return self.armor_id
        if slot == "gadget":
            if 0 <= index < len(self.gadgets):
                return self.gadgets[index]
            return None
        return None


def weapon_unlocked(weapon: Optional[Dict[str, Any]], level: int) -> bool:
    if not weapon:
        return False
    try:
        need = max(0, int(weapon.get("unlock_level") or 0))
    except (TypeError, ValueError):
        need = 0
    return int(level) >= need


def default_loadout(name: str, defaults: Dict[str, str], *, slot: int = 0) -> SavedLoadout:
    """Lv.0 默认配装（各套预设初始值）。"""
    gadgets: List[Optional[str]] = []
    g = str(defaults.get("gadget") or "").strip() or None
    if g:
        gadgets.append(g)
    return SavedLoadout(
        name=str(name or "").strip(),
        primary_id=str(defaults.get("primary") or "").strip() or None,
        secondary_id=str(defaults.get("secondary") or "").strip() or None,
        melee_id=str(defaults.get("melee") or "").strip() or None,
        armor_id=str(defaults.get("armor") or "").strip() or None,
        gadgets=gadgets,
        slot=int(slot),
    )


def sanitize_loadout(
    loadout: SavedLoadout,
    weapons: Dict[str, Dict[str, Any]],
    defaults: Dict[str, str],
    level: int,
    *,
    gadget_slots: int = 2,
) -> SavedLoadout:
    """校验解锁；非法槽位回退默认（默认也需解锁，否则清空）。"""

    def pick(slot: str, current: Optional[str]) -> Optional[str]:
        cur = str(current or "").strip() or None
        if cur and cur in weapons and weapons[cur].get("type") == slot and weapon_unlocked(weapons[cur], level):
            return cur
        fallback = str(defaults.get(slot) or "").strip() or None
        if (
            fallback
            and fallback in weapons
            and weapons[fallback].get("type") == slot
            and weapon_unlocked(weapons[fallback], level)
        ):
            return fallback
        return None

    gadgets: List[Optional[str]] = []
    raw_gadgets = list(loadout.gadgets or [])
    default_g = str(defaults.get("gadget") or "").strip() or None
    for i in range(max(0, int(gadget_slots))):
        cur = raw_gadgets[i] if i < len(raw_gadgets) else None
        cur_s = str(cur or "").strip() or None
        if (
            cur_s
            and cur_s in weapons
            and weapons[cur_s].get("type") == "gadget"
            and weapon_unlocked(weapons[cur_s], level)
        ):
            gadgets.append(cur_s)
            continue
        if (
            i == 0
            and default_g
            and default_g in weapons
            and weapons[default_g].get("type") == "gadget"
            and weapon_unlocked(weapons[default_g], level)
        ):
            gadgets.append(default_g)
        else:
            gadgets.append(None)
    while gadgets and gadgets[-1] is None:
        gadgets.pop()

    return SavedLoadout(
        name=loadout.name,
        primary_id=pick("primary", loadout.primary_id),
        secondary_id=pick("secondary", loadout.secondary_id),
        melee_id=pick("melee", loadout.melee_id),
        armor_id=pick("armor", loadout.armor_id),
        gadgets=gadgets,
        slot=int(getattr(loadout, "slot", 0) or 0),
    )


def apply_saved_loadout_to_player(ps: Any, loadout: SavedLoadout) -> None:
    from endstone_arc_shooter_game.loadout import clear_owned_loadout

    clear_owned_loadout(ps)
    ps.primary_id = loadout.primary_id
    ps.secondary_id = loadout.secondary_id
    ps.melee_id = loadout.melee_id
    ps.armor_id = loadout.armor_id
    ps.gadgets = list(loadout.gadgets or [])


class LoadoutStore:
    def __init__(self, db_path: Optional[Path] = None, logger=None):
        self.db_path = db_path or (PLUGIN_DATA_DIR / "shooter.db")
        self.logger = logger
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate_legacy()
        self._conn.commit()

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _migrate_legacy(self) -> None:
        """旧单表 player_loadout → 预设 0。"""
        try:
            rows = self._conn.execute("SELECT * FROM player_loadout").fetchall()
        except sqlite3.Error:
            return
        for row in rows:
            name = str(row["name"] or "").strip()
            if not name:
                continue
            exists = self._conn.execute(
                "SELECT 1 FROM player_loadout_presets WHERE name = ? AND slot = 0",
                (name,),
            ).fetchone()
            if exists:
                continue
            gadgets: List[Optional[str]] = []
            for key in ("gadget0", "gadget1"):
                val = row[key] if key in row.keys() else None
                gadgets.append(str(val).strip() if val else None)
            loadout = SavedLoadout(
                name=name,
                primary_id=str(row["primary_id"]).strip() if row["primary_id"] else None,
                secondary_id=str(row["secondary_id"]).strip() if row["secondary_id"] else None,
                melee_id=str(row["melee_id"]).strip() if row["melee_id"] else None,
                armor_id=str(row["armor_id"]).strip() if row["armor_id"] else None,
                gadgets=gadgets,
                slot=0,
            )
            self._upsert_preset(loadout)
            self._conn.execute(
                """
                INSERT INTO player_loadout_active (name, active_slot, updated_at)
                VALUES (?, 0, ?)
                ON CONFLICT(name) DO NOTHING
                """,
                (name, time.time()),
            )

    def _row_to_loadout(self, row: sqlite3.Row, *, slot: int) -> SavedLoadout:
        gadgets: List[Optional[str]] = []
        for key in ("gadget0", "gadget1"):
            val = row[key] if key in row.keys() else None
            gadgets.append(str(val).strip() if val else None)
        while gadgets and gadgets[-1] is None:
            gadgets.pop()
        return SavedLoadout(
            name=str(row["name"]),
            primary_id=str(row["primary_id"]).strip() if row["primary_id"] else None,
            secondary_id=str(row["secondary_id"]).strip() if row["secondary_id"] else None,
            melee_id=str(row["melee_id"]).strip() if row["melee_id"] else None,
            armor_id=str(row["armor_id"]).strip() if row["armor_id"] else None,
            gadgets=gadgets,
            slot=int(slot),
        )

    def _upsert_preset(self, loadout: SavedLoadout) -> None:
        name_s = str(loadout.name or "").strip()
        slot = max(0, min(PRESET_COUNT - 1, int(loadout.slot)))
        if not name_s:
            return
        gadgets = list(loadout.gadgets or [])
        g0 = gadgets[0] if len(gadgets) > 0 else None
        g1 = gadgets[1] if len(gadgets) > 1 else None
        now = time.time()
        self._conn.execute(
            """
            INSERT INTO player_loadout_presets (
                name, slot, primary_id, secondary_id, melee_id, armor_id, gadget0, gadget1, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name, slot) DO UPDATE SET
                primary_id=excluded.primary_id,
                secondary_id=excluded.secondary_id,
                melee_id=excluded.melee_id,
                armor_id=excluded.armor_id,
                gadget0=excluded.gadget0,
                gadget1=excluded.gadget1,
                updated_at=excluded.updated_at
            """,
            (
                name_s,
                slot,
                loadout.primary_id,
                loadout.secondary_id,
                loadout.melee_id,
                loadout.armor_id,
                g0,
                g1,
                now,
            ),
        )

    def ensure_presets(self, name: str, defaults: Dict[str, str]) -> None:
        name_s = str(name or "").strip()
        if not name_s:
            return
        for slot in range(PRESET_COUNT):
            row = self._conn.execute(
                "SELECT 1 FROM player_loadout_presets WHERE name = ? AND slot = ?",
                (name_s, slot),
            ).fetchone()
            if row is None:
                self._upsert_preset(default_loadout(name_s, defaults, slot=slot))
        active = self._conn.execute(
            "SELECT active_slot FROM player_loadout_active WHERE name = ?",
            (name_s,),
        ).fetchone()
        if active is None:
            self._conn.execute(
                "INSERT INTO player_loadout_active (name, active_slot, updated_at) VALUES (?, 0, ?)",
                (name_s, time.time()),
            )
        self._conn.commit()

    def get_active_slot(self, name: str) -> int:
        name_s = str(name or "").strip()
        row = self._conn.execute(
            "SELECT active_slot FROM player_loadout_active WHERE name = ?",
            (name_s,),
        ).fetchone()
        if row is None:
            return 0
        try:
            return max(0, min(PRESET_COUNT - 1, int(row["active_slot"])))
        except (TypeError, ValueError):
            return 0

    def set_active_slot(self, name: str, slot: int) -> int:
        name_s = str(name or "").strip()
        slot_i = max(0, min(PRESET_COUNT - 1, int(slot)))
        if not name_s:
            return 0
        self._conn.execute(
            """
            INSERT INTO player_loadout_active (name, active_slot, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                active_slot=excluded.active_slot,
                updated_at=excluded.updated_at
            """,
            (name_s, slot_i, time.time()),
        )
        self._conn.commit()
        return slot_i

    def get_preset(
        self,
        name: str,
        slot: int,
        *,
        defaults: Optional[Dict[str, str]] = None,
    ) -> SavedLoadout:
        name_s = str(name or "").strip()
        slot_i = max(0, min(PRESET_COUNT - 1, int(slot)))
        defaults = defaults or {}
        if defaults:
            self.ensure_presets(name_s, defaults)
        row = self._conn.execute(
            "SELECT * FROM player_loadout_presets WHERE name = ? AND slot = ?",
            (name_s, slot_i),
        ).fetchone()
        if row is None:
            return default_loadout(name_s, defaults, slot=slot_i)
        return self._row_to_loadout(row, slot=slot_i)

    def list_presets(
        self,
        name: str,
        *,
        defaults: Optional[Dict[str, str]] = None,
    ) -> List[SavedLoadout]:
        defaults = defaults or {}
        self.ensure_presets(name, defaults)
        return [self.get_preset(name, i, defaults=defaults) for i in range(PRESET_COUNT)]

    def get(self, name: str, *, defaults: Optional[Dict[str, str]] = None) -> SavedLoadout:
        """当前激活预设。"""
        defaults = defaults or {}
        self.ensure_presets(name, defaults)
        return self.get_preset(name, self.get_active_slot(name), defaults=defaults)

    def save(self, loadout: SavedLoadout) -> SavedLoadout:
        self._upsert_preset(loadout)
        self._conn.commit()
        return self.get_preset(loadout.name, loadout.slot)

    def set_slot(
        self,
        name: str,
        slot: str,
        weapon_id: Optional[str],
        *,
        index: int = 0,
        preset: Optional[int] = None,
        weapons: Optional[Dict[str, Dict[str, Any]]] = None,
        level: int = 0,
        gadget_slots: int = 2,
        defaults: Optional[Dict[str, str]] = None,
    ) -> Tuple[bool, str, SavedLoadout]:
        """设置某套预设的武器槽。失败返回 (False, reason_key, loadout)。"""
        name_s = str(name or "").strip()
        defaults = defaults or {}
        preset_i = self.get_active_slot(name_s) if preset is None else max(
            0, min(PRESET_COUNT - 1, int(preset))
        )
        loadout = self.get_preset(name_s, preset_i, defaults=defaults)
        wid = str(weapon_id or "").strip() or None
        weapons = weapons or {}
        if wid:
            w = weapons.get(wid)
            if not w:
                return False, "unknown", loadout
            if str(w.get("type") or "") != slot:
                return False, "bad_type", loadout
            if not weapon_unlocked(w, level):
                return False, "locked", loadout
        if slot == "primary":
            loadout.primary_id = wid
        elif slot == "secondary":
            loadout.secondary_id = wid
        elif slot == "melee":
            loadout.melee_id = wid
        elif slot == "armor":
            loadout.armor_id = wid
        elif slot == "gadget":
            caps = max(0, int(gadget_slots))
            while len(loadout.gadgets) < caps:
                loadout.gadgets.append(None)
            if index < 0 or index >= caps:
                return False, "bad_slot", loadout
            loadout.gadgets[index] = wid
        else:
            return False, "bad_slot", loadout
        loadout.slot = preset_i
        saved = self.save(loadout)
        return True, "ok", saved
