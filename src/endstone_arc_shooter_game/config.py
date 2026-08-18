# -*- coding: utf-8 -*-
"""地图、武器、全局设置。嵌套数据用 JSON；简单键值用 settings.yml。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from endstone_arc_shooter_game.language import PLUGIN_DATA_DIR

IMPLEMENTED_MODES = {"tdm"}
WEAPON_TYPES = ("primary", "secondary", "gadget")

DEFAULT_SETTINGS = {
    "DEFAULT_LANGUAGE_CODE": "ZH-CN",
    "PRIMARY_WEAPON_SLOTS": "1",
    "SECONDARY_WEAPON_SLOTS": "1",
    "GADGET_SLOTS": "3",
    "STARTING_POINTS": "800",
    "KILL_REWARD_POINTS": "100",
    "LOBBY_TIMEOUT_SECONDS": "900",
    "BUY_TIME_SECONDS": "10",
}

DEFAULT_MAPS = {
    "_comment": "复制并修改 id / 出生点。radius=0 表示精确出生在该坐标。mode 目前仅 tdm 可开局。",
    "maps": [
        {
            "id": "example_tdm",
            "display_name": "示例仓库",
            "mode": "tdm",
            "max_players_per_team": 8,
            "target_score": 50,
            "dimension": "overworld",
            "teams": {
                "a": {
                    "name": "红队",
                    "spawns": [{"x": 0, "y": 64, "z": 0, "radius": 0, "yaw": 0, "pitch": 0}],
                },
                "b": {
                    "name": "蓝队",
                    "spawns": [{"x": 20, "y": 64, "z": 0, "radius": 0, "yaw": 180, "pitch": 0}],
                },
            },
        }
    ],
}

DEFAULT_WEAPONS = {
    "_comment": "item 填 namespace:identifier。extras 为附属物品及数量，会发到背包末尾。",
    "weapons": [
        {
            "id": "bow",
            "display_name": "弓",
            "item": "minecraft:bow",
            "cost": 200,
            "type": "primary",
            "extras": {"minecraft:arrow": 32},
        },
        {
            "id": "crossbow",
            "display_name": "弩",
            "item": "minecraft:crossbow",
            "cost": 350,
            "type": "primary",
            "extras": {"minecraft:arrow": 24},
        },
        {
            "id": "iron_sword",
            "display_name": "铁剑",
            "item": "minecraft:iron_sword",
            "cost": 150,
            "type": "secondary",
            "extras": {},
        },
        {
            "id": "shield",
            "display_name": "盾牌",
            "item": "minecraft:shield",
            "cost": 120,
            "type": "secondary",
            "extras": {},
        },
        {
            "id": "snowball",
            "display_name": "雪球",
            "item": "minecraft:snowball",
            "cost": 50,
            "type": "gadget",
            "amount": 16,
            "extras": {},
        },
        {
            "id": "ender_pearl",
            "display_name": "末影珍珠",
            "item": "minecraft:ender_pearl",
            "cost": 80,
            "type": "gadget",
            "amount": 8,
            "extras": {},
        },
        {
            "id": "golden_apple",
            "display_name": "金苹果",
            "item": "minecraft:golden_apple",
            "cost": 100,
            "type": "gadget",
            "extras": {},
        },
    ],
}


def slot_layout(primary: int, secondary: int, gadget: int) -> Dict[str, Any]:
    """主武器占用热键栏前 n 格，副武器接着，道具再接着。附属物品从背包末尾向前放。"""
    primary = max(0, int(primary))
    secondary = max(0, int(secondary))
    gadget = max(0, int(gadget))
    p0, p1 = 0, primary
    s0, s1 = p1, p1 + secondary
    g0, g1 = s1, s1 + gadget
    return {
        "primary": (p0, p1),
        "secondary": (s0, s1),
        "gadget": (g0, g1),
        "reserved": g1,
    }


def slot_range(layout: Dict[str, Any], weapon_type: str) -> Tuple[int, int]:
    return layout.get(weapon_type, (0, 0))


def validate_map(raw: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(raw, dict):
        return ["map is not an object"]
    if not str(raw.get("id") or "").strip():
        errors.append("missing id")
    mode = str(raw.get("mode") or "").strip().lower()
    if not mode:
        errors.append("missing mode")
    teams = raw.get("teams")
    if not isinstance(teams, dict):
        errors.append("missing teams")
        return errors
    for team_id in ("a", "b"):
        team = teams.get(team_id)
        if not isinstance(team, dict):
            errors.append(f"missing teams.{team_id}")
            continue
        spawns = team.get("spawns")
        if not isinstance(spawns, list) or not spawns:
            errors.append(f"teams.{team_id} needs at least one spawn")
            continue
        for i, spawn in enumerate(spawns):
            if not isinstance(spawn, dict) or not _has_xyz(spawn):
                errors.append(f"teams.{team_id}.spawns[{i}] needs x/y/z")
    return errors


def validate_weapon(raw: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(raw, dict):
        return ["weapon is not an object"]
    if not str(raw.get("id") or "").strip():
        errors.append("missing id")
    if not str(raw.get("item") or "").strip():
        errors.append("missing item")
    wtype = str(raw.get("type") or "").strip().lower()
    if wtype not in WEAPON_TYPES:
        errors.append(f"type must be one of {WEAPON_TYPES}")
    extras = raw.get("extras", {})
    if extras is None:
        extras = {}
    if not isinstance(extras, dict):
        errors.append("extras must be an object of item_id -> count")
    return errors


def _has_xyz(spawn: Dict[str, Any]) -> bool:
    try:
        float(spawn["x"])
        float(spawn["y"])
        float(spawn["z"])
        return True
    except (KeyError, TypeError, ValueError):
        return False


def normalize_map(raw: Dict[str, Any]) -> Dict[str, Any]:
    teams_out: Dict[str, Any] = {}
    for team_id in ("a", "b"):
        team = raw.get("teams", {}).get(team_id) or {}
        spawns = []
        for spawn in team.get("spawns") or []:
            if not isinstance(spawn, dict) or not _has_xyz(spawn):
                continue
            spawns.append(
                {
                    "x": float(spawn["x"]),
                    "y": float(spawn["y"]),
                    "z": float(spawn["z"]),
                    "radius": float(spawn.get("radius") or 0),
                    "yaw": float(spawn["yaw"]) if spawn.get("yaw") is not None else None,
                    "pitch": float(spawn["pitch"]) if spawn.get("pitch") is not None else None,
                }
            )
        teams_out[team_id] = {
            "name": str(team.get("name") or ("红队" if team_id == "a" else "蓝队")),
            "spawns": spawns,
        }
    return {
        "id": str(raw.get("id")).strip(),
        "display_name": str(raw.get("display_name") or raw.get("id")),
        "mode": str(raw.get("mode") or "tdm").strip().lower(),
        "max_players_per_team": max(1, int(raw.get("max_players_per_team") or 8)),
        "target_score": max(1, int(raw.get("target_score") or 50)),
        "dimension": str(raw.get("dimension") or "overworld").strip(),
        "teams": teams_out,
    }


def normalize_weapon(raw: Dict[str, Any]) -> Dict[str, Any]:
    extras_in = raw.get("extras") or {}
    extras: Dict[str, int] = {}
    if isinstance(extras_in, dict):
        for item_id, count in extras_in.items():
            try:
                qty = int(count)
            except (TypeError, ValueError):
                continue
            if qty > 0 and str(item_id).strip():
                extras[str(item_id).strip()] = qty
    return {
        "id": str(raw.get("id")).strip(),
        "display_name": str(raw.get("display_name") or raw.get("id")),
        "item": str(raw.get("item")).strip(),
        "cost": max(0, int(raw.get("cost") or 0)),
        "type": str(raw.get("type")).strip().lower(),
        "data": int(raw.get("data") or 0),
        "amount": max(1, int(raw.get("amount") or 1)),
        "extras": extras,
    }


class SettingManager:
    def __init__(self):
        self.setting_file_path = PLUGIN_DATA_DIR / "settings.yml"
        self.setting_dict: Dict[str, str] = {}
        self._load()
        self._ensure_defaults()

    def _load(self):
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.setting_file_path.exists():
            self.setting_file_path.touch()
        with self.setting_file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    self.setting_dict[key.strip()] = value.strip()

    def _ensure_defaults(self):
        changed = False
        for key, value in DEFAULT_SETTINGS.items():
            if key not in self.setting_dict or self.setting_dict[key] == "":
                self.setting_dict[key] = value
                changed = True
        if changed:
            self._rewrite()

    def _rewrite(self):
        with self.setting_file_path.open("w", encoding="utf-8") as f:
            for key, value in self.setting_dict.items():
                f.write(f"{key}={value}\n")

    def GetSetting(self, key: str) -> Optional[str]:
        if key not in self.setting_dict:
            self.setting_dict[key] = ""
            with self.setting_file_path.open("a", encoding="utf-8") as f:
                f.write(f"{key}=\n")
            return None
        return self.setting_dict[key] or None

    def GetSettingInt(self, key: str, default: int = 0) -> int:
        raw = self.GetSetting(key)
        if raw is None:
            return default
        try:
            return int(float(raw))
        except ValueError:
            return default

    def SetSetting(self, key: str, value: Any) -> None:
        self.setting_dict[key] = str(value)
        self._rewrite()


class ConfigStore:
    def __init__(self, logger=None):
        self.logger = logger
        self.settings = SettingManager()
        self.maps: Dict[str, Dict[str, Any]] = {}
        self.weapons: Dict[str, Dict[str, Any]] = {}
        self.maps_path = PLUGIN_DATA_DIR / "maps.json"
        self.weapons_path = PLUGIN_DATA_DIR / "weapons.json"
        self.reload()

    def _log(self, level: str, message: str) -> None:
        if self.logger is not None:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(message)
                return
        print(f"[{level.upper()}] {message}")

    def reload(self) -> None:
        self.settings = SettingManager()
        self.maps = self._load_json_list(
            self.maps_path, DEFAULT_MAPS, "maps", validate_map, normalize_map
        )
        self.weapons = self._load_json_list(
            self.weapons_path, DEFAULT_WEAPONS, "weapons", validate_weapon, normalize_weapon
        )

    def _load_json_list(
        self,
        path: Path,
        default_doc: Dict[str, Any],
        list_key: str,
        validate_fn,
        normalize_fn,
    ) -> Dict[str, Dict[str, Any]]:
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_text(
                json.dumps(default_doc, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            self._log("error", f"[ARCShooterGame] Failed to read {path.name}: {e}")
            doc = default_doc
        items = doc.get(list_key) if isinstance(doc, dict) else None
        if not isinstance(items, list):
            self._log("error", f"[ARCShooterGame] {path.name} missing '{list_key}' array")
            return {}
        result: Dict[str, Dict[str, Any]] = {}
        for raw in items:
            errors = validate_fn(raw)
            if errors:
                self._log("warning", f"[ARCShooterGame] Skip invalid entry in {path.name}: {errors}")
                continue
            item = normalize_fn(raw)
            item_id = item["id"]
            if item_id in result:
                self._log("warning", f"[ARCShooterGame] Duplicate id '{item_id}' in {path.name}, later wins")
            result[item_id] = item
        return result

    def layout(self) -> Dict[str, Any]:
        return slot_layout(
            self.settings.GetSettingInt("PRIMARY_WEAPON_SLOTS", 1),
            self.settings.GetSettingInt("SECONDARY_WEAPON_SLOTS", 1),
            self.settings.GetSettingInt("GADGET_SLOTS", 3),
        )

    def starting_points(self) -> int:
        return max(0, self.settings.GetSettingInt("STARTING_POINTS", 800))

    def kill_reward(self) -> int:
        return max(0, self.settings.GetSettingInt("KILL_REWARD_POINTS", 100))

    def lobby_timeout(self) -> int:
        return max(30, self.settings.GetSettingInt("LOBBY_TIMEOUT_SECONDS", 900))

    def buy_time(self) -> int:
        return max(0, self.settings.GetSettingInt("BUY_TIME_SECONDS", 10))

    def weapons_of_type(self, weapon_type: str) -> List[Dict[str, Any]]:
        return [w for w in self.weapons.values() if w["type"] == weapon_type]
