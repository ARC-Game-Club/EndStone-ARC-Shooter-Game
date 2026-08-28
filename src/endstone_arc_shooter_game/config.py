# -*- coding: utf-8 -*-
"""地图、武器、全局设置。地图用 SQLite；武器仍用 JSON；简单键值用 settings.yml。"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from endstone_arc_shooter_game.language import PLUGIN_DATA_DIR

IMPLEMENTED_MODES = {"tdm"}
KNOWN_MODES = ("tdm", "ffa", "ctf")
WEAPON_TYPES = ("primary", "secondary", "gadget", "armor")

DEFAULT_SETTINGS = {
    "DEFAULT_LANGUAGE_CODE": "ZH-CN",
    "PRIMARY_WEAPON_SLOTS": "1",
    "SECONDARY_WEAPON_SLOTS": "1",
    "GADGET_SLOTS": "3",
    "STARTING_POINTS": "1000",
    "KILL_REWARD_POINTS": "50",
    "LOBBY_TIMEOUT_SECONDS": "900",
    "BUY_TIME_SECONDS": "10",
    "START_COUNTDOWN_SECONDS": "5",
    "MATCH_TIME_SECONDS": "300",
    "WIN_GUILD_CONTRIBUTION_PER_KD": "10",
    "MATCH_MONEY_PER_KD": "100",
}

DEFAULT_MAPS = {
    "_comment": "已弃用：地图数据现存储在 shooter.db（SQLite）。首次启动若存在 maps.json 会自动迁移。",
    "maps": [],
}

DEFAULT_WEAPONS = {
    "_comment": "起始 1000 可买普通主+副；击杀 +50 攒点。MP5/RPG 为副武器。",
    "weapons": [
        {"id": "mp5a5", "display_name": "HK MP5-A5 冲锋枪", "item": "trenbankai:mp5a5", "cost": 500, "type": "secondary", "extras": {"trenbankai:mp5a5_mag": 9}, "ammo_scoreboard": "mp5a5", "default_ammo": 30},
        {"id": "aks74u", "display_name": "AKS-74U 短突击步枪", "item": "trenbankai:aks74u", "cost": 550, "type": "primary", "extras": {"trenbankai:ak74_mag": 6}, "ammo_scoreboard": "aks74u", "default_ammo": 30},
        {"id": "m4a1", "display_name": "M4A1 卡宾枪", "item": "trenbankai:m4a1", "cost": 650, "type": "primary", "extras": {"trenbankai:m4a1_mag": 6}, "ammo_scoreboard": "m4a1", "default_ammo": 30},
        {"id": "ak74", "display_name": "AK-74 突击步枪", "item": "trenbankai:ak74", "cost": 650, "type": "primary", "extras": {"trenbankai:ak74_mag": 6}, "ammo_scoreboard": "ak74", "default_ammo": 30},
        {"id": "ak12", "display_name": "AK-12 突击步枪", "item": "trenbankai:ak12", "cost": 700, "type": "primary", "extras": {"trenbankai:ak12_mag": 6}, "ammo_scoreboard": "ak12", "default_ammo": 30},
        {"id": "mossberg", "display_name": "莫斯伯格 500 霰弹枪", "item": "trenbankai:mossberg", "cost": 700, "type": "primary", "extras": {"trenbankai:bullet_12gauge": 36}, "ammo_scoreboard": "mossberg", "default_ammo": 6},
        {"id": "shield", "display_name": "盾牌", "item": "minecraft:shield", "cost": 700, "type": "primary"},
        {"id": "ak47", "display_name": "AK-47 突击步枪", "item": "trenbankai:ak47", "cost": 900, "type": "primary", "extras": {"trenbankai:ak47_mag": 6}, "ammo_scoreboard": "ak47", "default_ammo": 30},
        {"id": "akm", "display_name": "AKM 突击步枪", "item": "trenbankai:akm", "cost": 900, "type": "primary", "extras": {"trenbankai:akm_mag": 6}, "ammo_scoreboard": "akm", "default_ammo": 30},
        {"id": "m1014", "display_name": "M1014 霰弹枪", "item": "trenbankai:m1014", "cost": 1000, "type": "primary", "extras": {"trenbankai:bullet_12gauge": 42}, "ammo_scoreboard": "m1014", "default_ammo": 7},
        {"id": "parafal", "display_name": "ParaFAL 战斗步枪", "item": "trenbankai:parafal", "cost": 1050, "type": "primary", "extras": {"trenbankai:fnfal_mag": 6}, "ammo_scoreboard": "parafal", "default_ammo": 20},
        {"id": "fnfal", "display_name": "FN FAL 战斗步枪", "item": "trenbankai:fnfal", "cost": 1150, "type": "primary", "extras": {"trenbankai:fnfal_mag": 6}, "ammo_scoreboard": "fnfal", "default_ammo": 20},
        {"id": "m249", "display_name": "M249 轻机枪", "item": "trenbankai:m249", "cost": 1300, "type": "primary", "extras": {"trenbankai:m249_mag": 3}, "ammo_scoreboard": "m249", "default_ammo": 200},
        {"id": "awp", "display_name": "AWP 狙击步枪", "item": "trenbankai:awp", "cost": 1450, "type": "primary", "extras": {"trenbankai:awp_mag": 6}, "ammo_scoreboard": "awp", "default_ammo": 10},
        {"id": "rpg7", "display_name": "RPG-7 火箭筒", "item": "trenbankai:rpg7", "cost": 1500, "type": "secondary", "extras": {"trenbankai:rpg7_rocket": 6}, "ammo_scoreboard": "rpg7", "default_ammo": 1},
        {"id": "glock17", "display_name": "格洛克 17", "item": "trenbankai:glock17", "cost": 300, "type": "secondary", "extras": {"trenbankai:glock_mag": 6}, "ammo_scoreboard": "glock17", "default_ammo": 17},
        {"id": "iron_sword", "display_name": "铁剑", "item": "minecraft:iron_sword", "cost": 100, "type": "secondary"},
        {"id": "glock18", "display_name": "格洛克 18c", "item": "trenbankai:glock18", "cost": 550, "type": "secondary", "extras": {"trenbankai:glock_mag": 6}, "ammo_scoreboard": "glock18", "default_ammo": 17},
        {"id": "deagle", "display_name": "沙漠之鹰", "item": "trenbankai:deagle", "cost": 800, "type": "secondary", "extras": {"trenbankai:deagle_mag": 6}, "ammo_scoreboard": "deagle", "default_ammo": 10},
        {"id": "iron_armor", "display_name": "铁甲全套", "item": "minecraft:iron_helmet", "cost": 500, "type": "armor", "extras": {"minecraft:iron_helmet": 1, "minecraft:iron_chestplate": 1, "minecraft:iron_leggings": 1, "minecraft:iron_boots": 1}},
        {"id": "flare", "display_name": "信号弹", "item": "trenbankai:flare", "cost": 50, "type": "gadget", "amount": 2},
        {"id": "m84_grenade", "display_name": "M84 闪光弹", "item": "trenbankai:m84_grenade", "cost": 70, "type": "gadget"},
        {"id": "mk2_grenade", "display_name": "Mk 2 手榴弹", "item": "trenbankai:mk2_grenade", "cost": 90, "type": "gadget"},
        {"id": "l83a1_grenade", "display_name": "L83A1 手榴弹", "item": "trenbankai:l83a1_grenade", "cost": 90, "type": "gadget"},
        {"id": "landmine", "display_name": "地雷", "item": "trenbankai:landmine_item", "cost": 110, "type": "gadget"},
    ],
}


def slot_layout(primary: int, secondary: int, gadget: int) -> Dict[str, Any]:
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


def slugify_map_id(name: str) -> str:
    raw = str(name or "").strip().lower()
    raw = re.sub(r"[^\w\u4e00-\u9fff]+", "_", raw, flags=re.UNICODE)
    raw = re.sub(r"_+", "_", raw).strip("_")
    return raw or "map"


def _has_xyz(point: Any) -> bool:
    if not isinstance(point, dict):
        return False
    try:
        float(point["x"])
        float(point["y"])
        float(point["z"])
        return True
    except (KeyError, TypeError, ValueError):
        return False


def _normalize_point(point: Any) -> Optional[Dict[str, float]]:
    if not _has_xyz(point):
        return None
    return {
        "x": float(point["x"]),
        "y": float(point["y"]),
        "z": float(point["z"]),
    }


def _normalize_spawn(spawn: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(spawn, dict) or not _has_xyz(spawn):
        return None
    out: Dict[str, Any] = {
        "x": float(spawn["x"]),
        "y": float(spawn["y"]),
        "z": float(spawn["z"]),
        "radius": float(spawn.get("radius") or 0),
    }
    if spawn.get("yaw") is not None:
        out["yaw"] = float(spawn["yaw"])
    if spawn.get("pitch") is not None:
        out["pitch"] = float(spawn["pitch"])
    return out


def _normalize_teams(raw_teams: Any) -> Dict[str, Any]:
    teams_out: Dict[str, Any] = {}
    teams = raw_teams if isinstance(raw_teams, dict) else {}
    for team_id in ("a", "b"):
        team = teams.get(team_id) or {}
        spawns = []
        for spawn in team.get("spawns") or []:
            norm = _normalize_spawn(spawn)
            if norm is not None:
                spawns.append(norm)
        teams_out[team_id] = {
            "name": str(team.get("name") or ("红队" if team_id == "a" else "蓝队")),
            "spawns": spawns,
        }
    return teams_out


def _normalize_mode(raw: Dict[str, Any]) -> Dict[str, Any]:
    mode = str(raw.get("mode") or "tdm").strip().lower()
    try:
        match_minutes = max(1, int(raw.get("match_time_minutes") or 5))
    except (TypeError, ValueError):
        match_minutes = 5
    return {
        "mode": mode,
        "max_players_per_team": max(1, int(raw.get("max_players_per_team") or 8)),
        "target_score": max(1, int(raw.get("target_score") or 50)),
        "match_time_minutes": match_minutes,
        "teams": _normalize_teams(raw.get("teams")),
    }


def migrate_legacy_map(raw: Dict[str, Any]) -> Dict[str, Any]:
    """旧格式（单 mode + teams）迁移到新格式（region + modes[]）。"""
    if isinstance(raw.get("modes"), list):
        return raw
    mode_cfg = {
        "mode": str(raw.get("mode") or "tdm").strip().lower(),
        "max_players_per_team": raw.get("max_players_per_team", 8),
        "target_score": raw.get("target_score", 50),
        "match_time_minutes": raw.get("match_time_minutes", 5),
        "teams": raw.get("teams") or {},
    }
    return {
        "id": raw.get("id"),
        "display_name": raw.get("display_name") or raw.get("id"),
        "dimension": raw.get("dimension") or "overworld",
        "region": raw.get("region") or {},
        "modes": [mode_cfg],
    }


def normalize_map(raw: Dict[str, Any]) -> Dict[str, Any]:
    migrated = migrate_legacy_map(raw)
    region_in = migrated.get("region") if isinstance(migrated.get("region"), dict) else {}
    pos1 = _normalize_point(region_in.get("pos1"))
    pos2 = _normalize_point(region_in.get("pos2"))
    modes_out: List[Dict[str, Any]] = []
    for mode_raw in migrated.get("modes") or []:
        if not isinstance(mode_raw, dict):
            continue
        modes_out.append(_normalize_mode(mode_raw))
    return {
        "id": str(migrated.get("id") or "").strip(),
        "display_name": str(migrated.get("display_name") or migrated.get("id") or "").strip(),
        "dimension": str(migrated.get("dimension") or "overworld").strip(),
        "region": {"pos1": pos1, "pos2": pos2},
        "modes": modes_out,
    }


def validate_map(raw: Dict[str, Any]) -> List[str]:
    errors: List[str] = []
    if not isinstance(raw, dict):
        return ["map is not an object"]
    if not str(raw.get("id") or "").strip():
        errors.append("missing id")
    if not str(raw.get("display_name") or raw.get("id") or "").strip():
        errors.append("missing display_name")
    modes = raw.get("modes")
    if not isinstance(modes, list):
        errors.append("missing modes array")
    return errors


def has_region(map_cfg: Dict[str, Any]) -> bool:
    region = map_cfg.get("region") or {}
    return _normalize_point(region.get("pos1")) is not None and _normalize_point(region.get("pos2")) is not None


def region_bounds(map_cfg: Dict[str, Any]) -> Optional[Tuple[float, float, float, float, float, float]]:
    region = map_cfg.get("region") or {}
    pos1 = _normalize_point(region.get("pos1"))
    pos2 = _normalize_point(region.get("pos2"))
    if pos1 is None or pos2 is None:
        return None
    return (
        min(pos1["x"], pos2["x"]),
        max(pos1["x"], pos2["x"]),
        min(pos1["y"], pos2["y"]),
        max(pos1["y"], pos2["y"]),
        min(pos1["z"], pos2["z"]),
        max(pos1["z"], pos2["z"]),
    )


def point_in_region(map_cfg: Dict[str, Any], x: float, y: float, z: float) -> bool:
    bounds = region_bounds(map_cfg)
    if bounds is None:
        return True
    x1, x2, y1, y2, z1, z2 = bounds
    return x1 <= x <= x2 and y1 <= y <= y2 and z1 <= z <= z2


def get_mode_config(map_cfg: Dict[str, Any], mode: str) -> Optional[Dict[str, Any]]:
    target = str(mode or "").strip().lower()
    for mode_cfg in map_cfg.get("modes") or []:
        if str(mode_cfg.get("mode") or "").lower() == target:
            return mode_cfg
    return None


def mode_has_spawns(mode_cfg: Dict[str, Any]) -> bool:
    teams = mode_cfg.get("teams") or {}
    for team_id in ("a", "b"):
        team = teams.get(team_id) or {}
        spawns = team.get("spawns") or []
        if not spawns:
            return False
    return True


def mode_incomplete_reasons(map_cfg: Dict[str, Any], mode: str) -> List[str]:
    """Return machine-readable reason codes for why a mode is not playable."""
    reasons: List[str] = []
    mode_key = str(mode or "").strip().lower()
    if mode_key not in IMPLEMENTED_MODES:
        reasons.append("reason_unimplemented")
        return reasons
    if not has_region(map_cfg):
        reasons.append("reason_missing_region")
    mode_cfg = get_mode_config(map_cfg, mode_key)
    if mode_cfg is None:
        reasons.append("reason_mode_not_found")
        return reasons
    teams = mode_cfg.get("teams") or {}
    for team_id, code in (("a", "reason_missing_spawn_a"), ("b", "reason_missing_spawn_b")):
        team = teams.get(team_id) or {}
        spawns = team.get("spawns") or []
        if not spawns:
            reasons.append(code)
    return reasons


def map_incomplete_reasons(map_cfg: Dict[str, Any]) -> List[str]:
    """Return reason codes when the map has no playable mode."""
    if playable_modes(map_cfg):
        return []
    reasons: List[str] = []
    if not has_region(map_cfg):
        reasons.append("reason_missing_region")
    modes = map_cfg.get("modes") or []
    if not modes:
        reasons.append("reason_no_modes")
        return reasons
    for mode_cfg in modes:
        mode = str(mode_cfg.get("mode") or "").lower()
        for code in mode_incomplete_reasons(map_cfg, mode):
            if code not in reasons:
                reasons.append(code)
    return reasons


def mode_playable(map_cfg: Dict[str, Any], mode: str) -> bool:
    mode_key = str(mode or "").strip().lower()
    if mode_key not in IMPLEMENTED_MODES:
        return False
    if not has_region(map_cfg):
        return False
    mode_cfg = get_mode_config(map_cfg, mode_key)
    if mode_cfg is None:
        return False
    return mode_has_spawns(mode_cfg)


def playable_modes(map_cfg: Dict[str, Any]) -> List[str]:
    out: List[str] = []
    for mode_cfg in map_cfg.get("modes") or []:
        mode = str(mode_cfg.get("mode") or "").lower()
        if mode_playable(map_cfg, mode):
            out.append(mode)
    return out


def match_kd_score(kills: int, deaths: int) -> int:
    """Positive K-D used for post-match ARC Core rewards."""
    try:
        return max(0, int(kills) - int(deaths))
    except (TypeError, ValueError):
        return 0


def build_runtime_map_cfg(map_cfg: Dict[str, Any], mode: str) -> Optional[Dict[str, Any]]:
    mode_key = str(mode or "").strip().lower()
    mode_cfg = get_mode_config(map_cfg, mode_key)
    if mode_cfg is None:
        return None
    return {
        "id": map_cfg["id"],
        "display_name": map_cfg.get("display_name") or map_cfg["id"],
        "dimension": map_cfg.get("dimension") or "overworld",
        "region": map_cfg.get("region") or {},
        "mode": mode_key,
        "max_players_per_team": int(mode_cfg.get("max_players_per_team") or 8),
        "target_score": int(mode_cfg.get("target_score") or 50),
        "match_time_minutes": max(1, int(mode_cfg.get("match_time_minutes") or 5)),
        "teams": mode_cfg.get("teams") or {},
    }


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
    ammo_sb = raw.get("ammo_scoreboard")
    if ammo_sb is not None and not str(ammo_sb).strip():
        errors.append("ammo_scoreboard cannot be empty when provided")
    if raw.get("default_ammo") is not None:
        try:
            if int(raw.get("default_ammo")) < 0:
                errors.append("default_ammo must be >= 0")
        except (TypeError, ValueError):
            errors.append("default_ammo must be an integer")
    return errors


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
    ammo_scoreboard = str(raw.get("ammo_scoreboard") or "").strip()
    default_ammo_raw = raw.get("default_ammo")
    default_ammo: Optional[int] = None
    if default_ammo_raw is not None and str(default_ammo_raw).strip() != "":
        default_ammo = max(0, int(default_ammo_raw))
        if not ammo_scoreboard:
            ammo_scoreboard = str(raw.get("id") or "").strip()
    out: Dict[str, Any] = {
        "id": str(raw.get("id")).strip(),
        "display_name": str(raw.get("display_name") or raw.get("id")),
        "item": str(raw.get("item")).strip(),
        "cost": max(0, int(raw.get("cost") or 0)),
        "type": str(raw.get("type")).strip().lower(),
        "data": int(raw.get("data") or 0),
        "amount": max(1, int(raw.get("amount") or 1)),
        "extras": extras,
    }
    if ammo_scoreboard and default_ammo is not None:
        out["ammo_scoreboard"] = ammo_scoreboard
        out["default_ammo"] = default_ammo
    return out


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
        from endstone_arc_shooter_game.map_db import MapDatabase

        self.logger = logger
        self.settings = SettingManager()
        self.maps: Dict[str, Dict[str, Any]] = {}
        self.weapons: Dict[str, Dict[str, Any]] = {}
        self.map_db = MapDatabase(logger=logger)
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
        from endstone_arc_shooter_game.map_db import MapDatabase

        self.settings = SettingManager()
        self.map_db = MapDatabase(logger=self.logger)
        self.maps = self.map_db.load_all()
        self.weapons = self._load_json_list(
            self.weapons_path, DEFAULT_WEAPONS, "weapons", validate_weapon, normalize_weapon
        )

    def save_maps(self) -> None:
        for entry in self.maps.values():
            self.map_db.save_map(entry)

    def create_map(self, display_name: str, dimension: str = "overworld") -> Dict[str, Any]:
        base_id = slugify_map_id(display_name)
        map_id = base_id
        suffix = 1
        while map_id in self.maps:
            suffix += 1
            map_id = f"{base_id}_{suffix}"
        entry = normalize_map(
            {
                "id": map_id,
                "display_name": display_name.strip(),
                "dimension": dimension,
                "region": {},
                "modes": [],
            }
        )
        self.maps[map_id] = entry
        self.map_db.save_map(entry)
        return entry

    def update_map(self, map_id: str, updater) -> Optional[Dict[str, Any]]:
        entry = self.maps.get(map_id)
        if entry is None:
            return None
        updater(entry)
        entry = normalize_map(entry)
        self.maps[map_id] = entry
        self.map_db.save_map(entry)
        return entry

    def delete_map(self, map_id: str) -> bool:
        if map_id not in self.maps:
            return False
        del self.maps[map_id]
        return self.map_db.delete_map(map_id)

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
        return max(0, self.settings.GetSettingInt("STARTING_POINTS", 1000))

    def kill_reward(self) -> int:
        return max(0, self.settings.GetSettingInt("KILL_REWARD_POINTS", 50))

    def lobby_timeout(self) -> int:
        return max(30, self.settings.GetSettingInt("LOBBY_TIMEOUT_SECONDS", 900))

    def buy_time(self) -> int:
        return max(0, self.settings.GetSettingInt("BUY_TIME_SECONDS", 10))

    def start_countdown(self) -> int:
        """开赛前传送倒计时秒数（title 倒数）。"""
        return max(1, self.settings.GetSettingInt("START_COUNTDOWN_SECONDS", 5))

    def match_time(self) -> int:
        """全局默认比赛秒数（仅作兜底；实际以各地图模式的 match_time_minutes 为准）。"""
        return max(60, self.settings.GetSettingInt("MATCH_TIME_SECONDS", 300))

    def win_guild_contribution_per_kd(self) -> int:
        return max(0, self.settings.GetSettingInt("WIN_GUILD_CONTRIBUTION_PER_KD", 10))

    def match_money_per_kd(self) -> int:
        return max(0, self.settings.GetSettingInt("MATCH_MONEY_PER_KD", 100))

    def weapons_of_type(self, weapon_type: str) -> List[Dict[str, Any]]:
        return [w for w in self.weapons.values() if w["type"] == weapon_type]
