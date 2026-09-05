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
WEAPON_TYPES = ("primary", "secondary", "melee", "gadget", "armor")
WEAPON_CATEGORIES = (
    "assault_rifle",
    "smg",
    "pistol",
    "shotgun",
    "lmg",
    "dmr",
    "sniper",
    "shield",
    "knife",
    "frag",
    "flash",
    "smoke",
    "mine",
)
# 槽位 type → 常见分类顺序（军械库 / 商店二级菜单）
# 注意：armor 类别已移除（2026-09-05）— 护甲由插件按队伍颜色自动发放，
# 不再允许在军械库 / 商店中配置。
CATEGORIES_BY_TYPE = {
    "primary": ("assault_rifle", "smg", "shotgun", "lmg", "dmr", "sniper", "shield"),
    "secondary": ("pistol",),
    "melee": ("knife",),
    "gadget": ("frag", "flash", "smoke", "mine"),
}
DEFAULT_WEAPON_SETTING_KEYS = {
    "primary": "DEFAULT_PRIMARY_WEAPON",
    "secondary": "DEFAULT_SECONDARY_WEAPON",
    "melee": "DEFAULT_MELEE_WEAPON",
    "gadget": "DEFAULT_GADGET_WEAPON",
    "armor": "DEFAULT_ARMOR_WEAPON",
}

DEFAULT_SETTINGS = {
    "DEFAULT_LANGUAGE_CODE": "ZH-CN",
    "PRIMARY_WEAPON_SLOTS": "1",
    "SECONDARY_WEAPON_SLOTS": "1",
    "MELEE_WEAPON_SLOTS": "1",
    "GADGET_SLOTS": "2",
    "DEFAULT_PRIMARY_WEAPON": "m4",
    "DEFAULT_SECONDARY_WEAPON": "m1911",
    "DEFAULT_MELEE_WEAPON": "silencefd",
    "DEFAULT_GADGET_WEAPON": "mk2_grenade",
    "DEFAULT_ARMOR_WEAPON": "",
    "STARTING_POINTS": "1000",
    "KILL_REWARD_POINTS": "50",
    "LOBBY_TIMEOUT_SECONDS": "900",
    # 开局准备时间（购买/换装窗）：全部玩家在开局时进入准备状态（移速 0 + 无敌 + 弧光币）。
    "PREPARATION_TIME_SECONDS": "20",
    # 复活后无敌时间：仅作用于 STATE_PLAYING 中被复活的玩家（无敌 + 弧光币；不冻结移速）。
    # 设为 0 表示关闭复活无敌窗（玩家复活即直接进入战斗）。
    "RESPAWN_INVULNERABLE_SECONDS": "3",
    "START_COUNTDOWN_SECONDS": "5",
    "MATCH_TIME_SECONDS": "300",
    "WIN_GUILD_CONTRIBUTION_PER_KD": "10",
    "MATCH_MONEY_PER_KILL": "200",
    "MATCH_WIN_BONUS": "2000",
    "MATCH_MVP_BONUS": "500",
    "ASSIST_WINDOW_SECONDS": "3",
    "MATCH_ASSIST_WEIGHT": "0.5",
    "MATCH_TK_WEIGHT": "1.5",
    "XP_PER_KILL": "5",
    "XP_KILL_PER_TEAMMATE": "2",
    "XP_PER_LEVEL": "100",
    "MAX_LEVEL": "100",
    "XP_WIN_BONUS_PERCENT": "20",
    "XP_MVP_PER_TEAMMATE": "10",
    # 兼容旧键（已弃用，请用 XP_MVP_PER_TEAMMATE）
    "XP_MVP_BONUS": "10",
    # 兼容旧键：若仍存在则忽略，以 MATCH_MONEY_PER_KILL 为准
    "MATCH_MONEY_PER_KD": "100",
    # === 2026-09-05 队伍默认护甲（按队伍颜色自动发） ===
    # 格式：JSON 字符串 {"helmet": "<item_id>", "chestplate": "<item_id>", "leggings": "<item_id>"}
    # OP 改 settings.yml 即可调整每队默认护甲，无需改代码。
    "TEAM_A_DEFAULT_ARMOR": '{"helmet":"arc:6b47_helmet_red","chestplate":"arc:6b45_vest","leggings":"arc:emr_suit_red"}',
    "TEAM_B_DEFAULT_ARMOR": '{"helmet":"arc:6b47_helmet_blue","chestplate":"arc:6b45_vest","leggings":"arc:emr_suit_blue"}',
}

DEFAULT_MAPS = {
    "_comment": "已弃用：地图数据现存储在 shooter.db（SQLite）。首次启动若存在 maps.json 会自动迁移。",
    "maps": [],
}

DEFAULT_WEAPONS = {'_comment': '弧光枪械：type=槽位；category=分类筛选；unlock_level=军械库解锁等级。',
 'weapons': [{'id': 'm4',
              'display_name': 'M4',
              'item': 'arc:m4',
              'cost': 650,
              'type': 'primary',
              'ammo_scoreboard': 'm4Ammo',
              'default_ammo': 30,
              'category': 'assault_rifle',
              'unlock_level': 0},
             {'id': 'scarl',
              'display_name': '改装型 FN SCAR-L',
              'item': 'arc:scarl',
              'cost': 700,
              'type': 'primary',
              'ammo_scoreboard': 'scarlAmmo',
              'default_ammo': 25,
              'category': 'assault_rifle',
              'unlock_level': 8},
             {'id': 'qbz95',
              'display_name': 'QBZ-95',
              'item': 'arc:qbz95',
              'cost': 700,
              'type': 'primary',
              'ammo_scoreboard': 'qbz95Ammo',
              'default_ammo': 30,
              'category': 'assault_rifle',
              'unlock_level': 10},
             {'id': 'qbz191',
              'display_name': 'QBZ191',
              'item': 'arc:qbz191',
              'cost': 720,
              'type': 'primary',
              'ammo_scoreboard': 'qbz191Ammo',
              'default_ammo': 30,
              'category': 'assault_rifle',
              'unlock_level': 20},
             {'id': 'sar80',
              'display_name': 'SAR-80',
              'item': 'arc:sar80',
              'cost': 720,
              'type': 'primary',
              'ammo_scoreboard': 'sar80Ammo',
              'default_ammo': 30,
              'category': 'assault_rifle',
              'unlock_level': 20},
             {'id': 'ak12',
              'display_name': 'AK-12',
              'item': 'arc:ak12',
              'cost': 750,
              'type': 'primary',
              'ammo_scoreboard': 'ak12Ammo',
              'default_ammo': 30,
              'category': 'assault_rifle',
              'unlock_level': 20},
             {'id': 'fp6',
              'display_name': 'FP6',
              'item': 'arc:fp6',
              'cost': 700,
              'type': 'primary',
              'ammo_scoreboard': 'fp6Ammo',
              'default_ammo': 6,
              'category': 'shotgun',
              'unlock_level': 5},
             {'id': 'ak47',
              'display_name': 'AK-47',
              'item': 'arc:ak47',
              'cost': 800,
              'type': 'primary',
              'ammo_scoreboard': 'ak47Ammo',
              'default_ammo': 30,
              'category': 'assault_rifle',
              'unlock_level': 25},
             {'id': 'spas12',
              'display_name': '弗兰基 SPAS-12',
              'item': 'arc:spas12',
              'cost': 850,
              'type': 'primary',
              'ammo_scoreboard': 'spas12Ammo',
              'default_ammo': 8,
              'category': 'shotgun',
              'unlock_level': 15},
             {'id': 'scarh',
              'display_name': 'FN SCAR-H',
              'item': 'arc:scarh',
              'cost': 900,
              'type': 'primary',
              'ammo_scoreboard': 'scarhAmmo',
              'default_ammo': 20,
              'category': 'assault_rifle',
              'unlock_level': 30},
             {'id': 'saiga308',
              'display_name': 'SAIGA-308',
              'item': 'arc:saiga308',
              'cost': 900,
              'type': 'primary',
              'ammo_scoreboard': 'saiga308Ammo',
              'default_ammo': 8,
              'category': 'dmr',
              'unlock_level': 25},
             {'id': 'rpk74',
              'display_name': 'RPK-74',
              'item': 'arc:rpk74',
              'cost': 950,
              'type': 'primary',
              'ammo_scoreboard': 'rpk74Ammo',
              'default_ammo': 45,
              'category': 'lmg',
              'unlock_level': 30},
             {'id': 'aa12',
              'display_name': 'AA-12',
              'item': 'arc:aa12',
              'cost': 1000,
              'type': 'primary',
              'ammo_scoreboard': 'aa12Ammo',
              'default_ammo': 20,
              'category': 'shotgun',
              'unlock_level': 40},
             {'id': 'hcar',
              'display_name': 'HCAR',
              'item': 'arc:hcar',
              'cost': 1000,
              'type': 'primary',
              'ammo_scoreboard': 'hcarAmmo',
              'default_ammo': 20,
              'category': 'dmr',
              'unlock_level': 40},
             {'id': 'qbb95',
              'display_name': 'QBB95',
              'item': 'arc:qbb95',
              'cost': 1100,
              'type': 'primary',
              'ammo_scoreboard': 'qbb95Ammo',
              'default_ammo': 60,
              'category': 'lmg',
              'unlock_level': 50},
             {'id': 'ultraleggero',
              'display_name': '贝瑞塔 Ultraleggero',
              'item': 'arc:ultraleggero',
              'cost': 1200,
              'type': 'primary',
              'ammo_scoreboard': 'ultraleggeroAmmo',
              'default_ammo': 2,
              'category': 'shotgun',
              'unlock_level': 50},
             {'id': 'svch',
              'display_name': 'SVCh',
              'item': 'arc:svch',
              'cost': 1200,
              'type': 'primary',
              'ammo_scoreboard': 'svchAmmo',
              'default_ammo': 10,
              'category': 'dmr',
              'unlock_level': 10},
             {'id': 'm249',
              'display_name': 'M249',
              'item': 'arc:m249',
              'cost': 1300,
              'type': 'primary',
              'ammo_scoreboard': 'm249Ammo',
              'default_ammo': 75,
              'category': 'lmg',
              'unlock_level': 60},
             {'id': 'minimi',
              'display_name': 'FN 米尼米',
              'item': 'arc:minimi',
              'cost': 1300,
              'type': 'primary',
              'ammo_scoreboard': 'minimiAmmo',
              'default_ammo': 75,
              'category': 'lmg',
              'unlock_level': 60},
             {'id': 'mrad',
              'display_name': '巴雷特 MRAD',
              'item': 'arc:mrad',
              'cost': 1400,
              'type': 'primary',
              'ammo_scoreboard': 'mradAmmo',
              'default_ammo': 7,
              'category': 'sniper',
              'unlock_level': 70},
             {'id': 'vshk',
              'display_name': 'VSHk',
              'item': 'arc:vshk',
              'cost': 1450,
              'type': 'primary',
              'ammo_scoreboard': 'vshkAmmo',
              'default_ammo': 5,
              'category': 'sniper',
              'unlock_level': 80},
             {'id': 'gm6_lynx',
              'display_name': 'GM6 山猫',
              'item': 'arc:gm6_lynx',
              'cost': 1500,
              'type': 'primary',
              'ammo_scoreboard': 'gm6_lynxAmmo',
              'default_ammo': 5,
              'category': 'sniper',
              'unlock_level': 90},
             {'id': 'shield',
              'display_name': '盾牌',
              'item': 'minecraft:shield',
              'cost': 700,
              'type': 'primary',
              'category': 'shield',
              'unlock_level': 10},
             {'id': 'm1911',
              'display_name': 'M1911',
              'item': 'arc:m1911',
              'cost': 250,
              'type': 'secondary',
              'ammo_scoreboard': 'm1911Ammo',
              'default_ammo': 7,
              'category': 'pistol',
              'unlock_level': 0},
             {'id': 'glock17',
              'display_name': '格洛克 17',
              'item': 'arc:glock17',
              'cost': 300,
              'type': 'secondary',
              'ammo_scoreboard': 'glock17Ammo',
              'default_ammo': 18,
              'category': 'pistol',
              'unlock_level': 2},
             {'id': 'pdp',
              'display_name': '瓦尔特 PDP',
              'item': 'arc:pdp',
              'cost': 320,
              'type': 'secondary',
              'ammo_scoreboard': 'pdpAmmo',
              'default_ammo': 18,
              'category': 'pistol',
              'unlock_level': 5},
             {'id': 'mpl1',
              'display_name': '列别捷夫战术 MPL1',
              'item': 'arc:mpl1',
              'cost': 350,
              'type': 'secondary',
              'ammo_scoreboard': 'mpl1Ammo',
              'default_ammo': 18,
              'category': 'pistol',
              'unlock_level': 8},
             {'id': 'pp2000',
              'display_name': 'PP-2000',
              'item': 'arc:pp2000',
              'cost': 450,
              'type': 'primary',
              'ammo_scoreboard': 'pp2000Ammo',
              'default_ammo': 20,
              'category': 'smg',
              'unlock_level': 4},
             {'id': 'pmx',
              'display_name': '贝瑞塔 PMX',
              'item': 'arc:pmx',
              'cost': 480,
              'type': 'primary',
              'ammo_scoreboard': 'pmxAmmo',
              'default_ammo': 20,
              'category': 'smg',
              'unlock_level': 10},
             {'id': 'mp5',
              'display_name': '黑克勒-科赫 MP5',
              'item': 'arc:mp5',
              'cost': 500,
              'type': 'primary',
              'ammo_scoreboard': 'mp5Ammo',
              'default_ammo': 30,
              'category': 'smg',
              'unlock_level': 15},
             {'id': 'ump45',
              'display_name': '黑克勒-科赫 UMP-45',
              'item': 'arc:ump45',
              'cost': 520,
              'type': 'primary',
              'ammo_scoreboard': 'ump45Ammo',
              'default_ammo': 30,
              'category': 'smg',
              'unlock_level': 20},
             {'id': 'k7',
              'display_name': '大宇电信 K7',
              'item': 'arc:k7',
              'cost': 550,
              'type': 'primary',
              'ammo_scoreboard': 'k7Ammo',
              'default_ammo': 30,
              'category': 'smg',
              'unlock_level': 25},
             {'id': 'p90',
              'display_name': 'P90',
              'item': 'arc:p90',
              'cost': 600,
              'type': 'primary',
              'ammo_scoreboard': 'p90Ammo',
              'default_ammo': 50,
              'category': 'smg',
              'unlock_level': 30},
             {'id': 'silencefd',
              'display_name': '战术匕首',
              'item': 'arc:silencefd',
              'cost': 100,
              'type': 'melee',
              'category': 'knife',
              'unlock_level': 0},
             {'id': 'arc_armor',
              'display_name': '弧光防弹套装',
              'item': 'arc:6b47_helmet',
              'cost': 500,
              'type': 'armor',
              'extras': {'arc:6b47_helmet': 1, 'arc:6b45_vest': 1, 'arc:emr_suit': 1, 'arc:balaclava': 1},
              'category': 'armor',
              'unlock_level': 15},
             {'id': 'm84_grenade',
              'display_name': 'M84 闪光弹',
              'item': 'arc:m84_grenade',
              'cost': 70,
              'type': 'gadget',
              'category': 'flash',
              'unlock_level': 2},
             {'id': 'mk2_grenade',
              'display_name': 'Mk 2 破片手雷',
              'item': 'arc:mk2_grenade',
              'cost': 90,
              'type': 'gadget',
              'category': 'frag',
              'unlock_level': 0},
             {'id': 'l83a1_grenade',
              'display_name': 'L83A1 烟雾弹',
              'item': 'arc:l83a1_grenade',
              'cost': 90,
              'type': 'gadget',
              'category': 'smoke',
              'unlock_level': 4},
             {'id': 'landmine',
              'display_name': '地雷',
              'item': 'arc:landmine_item',
              'cost': 110,
              'type': 'gadget',
              'category': 'mine',
              'unlock_level': 8}]}


def slot_layout(primary: int, secondary: int, melee: int, gadget: int) -> Dict[str, Any]:
    primary = max(0, int(primary))
    secondary = max(0, int(secondary))
    melee = max(0, int(melee))
    gadget = max(0, int(gadget))
    p0, p1 = 0, primary
    s0, s1 = p1, p1 + secondary
    m0, m1 = s1, s1 + melee
    g0, g1 = m1, m1 + gadget
    return {
        "primary": (p0, p1),
        "secondary": (s0, s1),
        "melee": (m0, m1),
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
    from endstone_arc_shooter_game.loadout import normalize_acquire_key

    acquire = normalize_acquire_key(raw.get("weapon_acquire"))
    # TDM 固定军械库（暂不用商店）；其它模式未配置时默认商店
    if mode == "tdm":
        acquire = "armory"
    elif raw.get("weapon_acquire") is None or str(raw.get("weapon_acquire") or "").strip() == "":
        acquire = "shop"
    out: Dict[str, Any] = {
        "mode": mode,
        "max_players_per_team": max(1, int(raw.get("max_players_per_team") or 8)),
        "target_score": max(1, int(raw.get("target_score") or 50)),
        "match_time_minutes": match_minutes,
        "weapon_acquire": acquire,
        "teams": _normalize_teams(raw.get("teams")),
    }
    # 预设 / 随机 / 武器大师扩展字段原样保留（经轻度清洗）
    preset = raw.get("preset_loadout")
    if isinstance(preset, dict):
        out["preset_loadout"] = {
            "primary": str(preset.get("primary") or "").strip() or None,
            "secondary": str(preset.get("secondary") or "").strip() or None,
            "melee": str(preset.get("melee") or "").strip() or None,
            "armor": str(preset.get("armor") or "").strip() or None,
            "gadgets": [
                str(g).strip()
                for g in (preset.get("gadgets") or [])
                if str(g or "").strip()
            ],
        }
    if "random_gadget_count" in raw:
        try:
            out["random_gadget_count"] = max(0, int(raw.get("random_gadget_count") or 0))
        except (TypeError, ValueError):
            out["random_gadget_count"] = 0
    if "random_include_armor" in raw:
        out["random_include_armor"] = bool(raw.get("random_include_armor"))
    master_ids = raw.get("master_weapon_ids")
    if isinstance(master_ids, (list, tuple)):
        out["master_weapon_ids"] = [str(x).strip() for x in master_ids if str(x or "").strip()]
    elif isinstance(master_ids, str) and master_ids.strip():
        out["master_weapon_ids"] = [master_ids.strip()]
    return out


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
    """兼容旧逻辑：正的 K-D（已由 KDA 结算替代，测试仍可用）。"""
    try:
        return max(0, int(kills) - int(deaths))
    except (TypeError, ValueError):
        return 0


def match_performance_score(
    kills: int,
    assists: int = 0,
    team_kills: int = 0,
    *,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> float:
    """表现分：K + A×assist_weight − TK×tk_weight。"""
    try:
        return (
            float(kills)
            + float(assists) * float(assist_weight)
            - float(team_kills) * float(tk_weight)
        )
    except (TypeError, ValueError):
        return 0.0


def match_reward_coefficient(
    kills: int,
    deaths: int,
    assists: int = 0,
    team_kills: int = 0,
    *,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> float:
    """调节系数 (K + A×w_a − TK×w_tk) / max(D, 1)，下限 0。"""
    score = match_performance_score(
        kills,
        assists,
        team_kills,
        assist_weight=assist_weight,
        tk_weight=tk_weight,
    )
    try:
        d = max(1, int(deaths))
    except (TypeError, ValueError):
        d = 1
    return max(0.0, score / float(d))


def calc_match_money(
    kills: int,
    deaths: int,
    assists: int = 0,
    team_kills: int = 0,
    *,
    money_per_kill: int = 200,
    win_bonus: int = 0,
    won: bool = False,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> int:
    """赛后金钱：((击杀×单价) + 胜场奖) × KDA 调节系数。"""
    try:
        base = max(0, int(kills)) * max(0, int(money_per_kill))
        if won:
            base += max(0, int(win_bonus))
        coeff = match_reward_coefficient(
            kills,
            deaths,
            assists,
            team_kills,
            assist_weight=assist_weight,
            tk_weight=tk_weight,
        )
        return max(0, int(round(base * coeff)))
    except (TypeError, ValueError):
        return 0


def match_kda(
    kills: int,
    deaths: int,
    assists: int = 0,
    team_kills: int = 0,
    *,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> float:
    """本场 KDA：(K + A×assist_weight − TK×tk_weight) / max(D, 1)。"""
    return match_reward_coefficient(
        kills,
        deaths,
        assists,
        team_kills,
        assist_weight=assist_weight,
        tk_weight=tk_weight,
    )


def team_average_match_kda(
    players: List[Any],
    *,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> float:
    if not players:
        return 0.0
    total = 0.0
    for ps in players:
        try:
            total += match_kda(
                int(getattr(ps, "kills", 0) or 0),
                int(getattr(ps, "deaths", 0) or 0),
                int(getattr(ps, "assists", 0) or 0),
                int(getattr(ps, "team_kills", 0) or 0),
                assist_weight=assist_weight,
                tk_weight=tk_weight,
            )
        except (TypeError, ValueError):
            continue
    return total / float(len(players))


def xp_kill_for_team(team_size: int, *, per_teammate: int = 2) -> int:
    """击杀 XP = 队伍人数 × per_teammate（默认 ×2）。"""
    return max(1, int(team_size)) * max(0, int(per_teammate))


def xp_assist_for_team(team_size: int, *, per_teammate: int = 2) -> int:
    """助攻 XP = 击杀 XP 的一半。"""
    return max(0, xp_kill_for_team(team_size, per_teammate=per_teammate) // 2)


def match_mvp_score(
    kills: int,
    deaths: int,
    assists: int = 0,
    team_kills: int = 0,
    *,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> float:
    """队内 MVP 分：KDA 调节系数 + 击杀数/10。"""
    coeff = match_reward_coefficient(
        kills,
        deaths,
        assists,
        team_kills,
        assist_weight=assist_weight,
        tk_weight=tk_weight,
    )
    try:
        return float(coeff) + float(kills) / 10.0
    except (TypeError, ValueError):
        return float(coeff)


def pick_team_mvp(
    players: List[Any],
    *,
    assist_weight: float = 0.5,
    tk_weight: float = 1.5,
) -> Optional[Any]:
    """队内 MVP：KDA > 1 且 KDA ≥ 队伍平均，取 KDA 最高者。"""
    if not players:
        return None
    avg = team_average_match_kda(
        players, assist_weight=assist_weight, tk_weight=tk_weight
    )
    best = None
    best_key: Optional[Tuple[float, int, int, str]] = None
    for ps in players:
        try:
            kills = int(getattr(ps, "kills", 0) or 0)
            deaths = int(getattr(ps, "deaths", 0) or 0)
            assists = int(getattr(ps, "assists", 0) or 0)
            team_kills = int(getattr(ps, "team_kills", 0) or 0)
            name = str(getattr(ps, "name", "") or "")
        except (TypeError, ValueError):
            continue
        kda = match_kda(
            kills,
            deaths,
            assists,
            team_kills,
            assist_weight=assist_weight,
            tk_weight=tk_weight,
        )
        if kda <= 1.0:
            continue
        if kda + 1e-9 < avg:
            continue
        key = (kda, kills, assists, name)
        if best_key is None or key > best_key:
            best_key = key
            best = ps
    return best


def collect_assist_and_tk(
    damage_times: Dict[str, float],
    *,
    now: float,
    window: float,
    killer_name: Optional[str],
    victim_team: str,
    team_of: Dict[str, str],
) -> Tuple[List[str], List[str]]:
    """死亡前 window 秒内：敌方伤害 → 助攻（不含击杀者）；友方伤害 → TK。"""
    assists: List[str] = []
    team_kills: List[str] = []
    for name, ts in (damage_times or {}).items():
        if not name or name == killer_name:
            continue
        try:
            if float(now) - float(ts) > float(window):
                continue
        except (TypeError, ValueError):
            continue
        team = team_of.get(name)
        if not team:
            continue
        if team == victim_team:
            team_kills.append(name)
        else:
            assists.append(name)
    return assists, team_kills


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
        "weapon_acquire": "armory" if mode_key == "tdm" else (
            mode_cfg.get("weapon_acquire") or "shop"
        ),
        "preset_loadout": mode_cfg.get("preset_loadout"),
        "random_gadget_count": mode_cfg.get("random_gadget_count"),
        "random_include_armor": mode_cfg.get("random_include_armor"),
        "master_weapon_ids": mode_cfg.get("master_weapon_ids"),
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
    category = str(raw.get("category") or "").strip().lower()
    if category and category not in WEAPON_CATEGORIES:
        errors.append(f"category must be one of {WEAPON_CATEGORIES}")
    if raw.get("unlock_level") is not None:
        try:
            if int(raw.get("unlock_level")) < 0:
                errors.append("unlock_level must be >= 0")
        except (TypeError, ValueError):
            errors.append("unlock_level must be an integer")
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
        "category": str(raw.get("category") or "").strip().lower(),
        "unlock_level": max(0, int(raw.get("unlock_level") or 0)),
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
        # 旧键 BUY_TIME_SECONDS → 新键 PREPARATION_TIME_SECONDS 自动迁移：
        # 仅当用户写了旧键、新键还没被用户显式设置时，把旧值搬过去。
        legacy_buy = self.setting_dict.get("BUY_TIME_SECONDS", "")
        new_prep = self.setting_dict.get("PREPARATION_TIME_SECONDS", "")
        if legacy_buy and not new_prep:
            self.setting_dict["PREPARATION_TIME_SECONDS"] = legacy_buy
            changed = True
        # 旧键 RESPAWN_PREPARATION_TIME_SECONDS → RESPAWN_INVULNERABLE_SECONDS 自动迁移。
        legacy_resp = self.setting_dict.get("RESPAWN_PREPARATION_TIME_SECONDS", "")
        new_resp = self.setting_dict.get("RESPAWN_INVULNERABLE_SECONDS", "")
        if legacy_resp and not new_resp:
            self.setting_dict["RESPAWN_INVULNERABLE_SECONDS"] = legacy_resp
            changed = True
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

    def GetSettingFloat(self, key: str, default: float = 0.0) -> float:
        raw = self.GetSetting(key)
        if raw is None:
            return float(default)
        try:
            return float(raw)
        except ValueError:
            return float(default)

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

    def default_team_armor(self, team_id):
        """Return default armor {helmet, chestplate, leggings} item ids for a team.
        Read JSON from settings.yml (TEAM_A_DEFAULT_ARMOR / TEAM_B_DEFAULT_ARMOR).
        Fallback to hardcoded defaults if missing/parse-fails.
        """
        # 延迟导入避免 config<->session 循环引用
        from endstone_arc_shooter_game.session import TEAM_A, TEAM_B
        import json as _json
        if team_id == TEAM_A:
            raw = self.settings.GetSetting('TEAM_A_DEFAULT_ARMOR') or ''
        elif team_id == TEAM_B:
            raw = self.settings.GetSetting('TEAM_B_DEFAULT_ARMOR') or ''
        else:
            return {}
        if raw:
            try:
                parsed = _json.loads(raw)
                if isinstance(parsed, dict):
                    return {
                        'helmet': str(parsed.get('helmet') or '').strip(),
                        'chestplate': str(parsed.get('chestplate') or '').strip(),
                        'leggings': str(parsed.get('leggings') or '').strip(),
                    }
            except Exception:
                pass
        # Fallback: 跟随 mod 原本的"原版绿色防弹衣 + 红/蓝头盔/迷彩服"
        if team_id == TEAM_A:
            return {'helmet': 'arc:6b47_helmet_red', 'chestplate': 'arc:6b45_vest', 'leggings': 'arc:emr_suit_red'}
        if team_id == TEAM_B:
            return {'helmet': 'arc:6b47_helmet_blue', 'chestplate': 'arc:6b45_vest', 'leggings': 'arc:emr_suit_blue'}
        return {}

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
            self.settings.GetSettingInt("MELEE_WEAPON_SLOTS", 1),
            self.settings.GetSettingInt("GADGET_SLOTS", 2),
        )

    def default_weapons(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        for wtype, key in DEFAULT_WEAPON_SETTING_KEYS.items():
            out[wtype] = str(self.settings.GetSetting(key) or "").strip()
        return out

    def starting_points(self) -> int:
        return max(0, self.settings.GetSettingInt("STARTING_POINTS", 1000))

    def kill_reward(self) -> int:
        return max(0, self.settings.GetSettingInt("KILL_REWARD_POINTS", 50))

    def lobby_timeout(self) -> int:
        return max(30, self.settings.GetSettingInt("LOBBY_TIMEOUT_SECONDS", 900))

    def preparation_time(self) -> int:
        """开局准备时间秒数（购买/换装窗）。
        兼容旧键 BUY_TIME_SECONDS：当 settings.yml 仍使用旧键且未写入
        PREPARATION_TIME_SECONDS 时回退到旧值。
        """
        new_val = self.settings.GetSetting("PREPARATION_TIME_SECONDS")
        if new_val is not None and str(new_val).strip() != "":
            return max(0, int(float(new_val)))
        legacy = self.settings.GetSetting("BUY_TIME_SECONDS")
        if legacy is not None and str(legacy).strip() != "":
            return max(0, int(float(legacy)))
        return 20

    def respawn_invuln_time(self) -> int:
        """复活后无敌时间秒数（仅无敌 + 弧光币；不冻结移速）。0 表示关闭。"""
        return max(
            0, self.settings.GetSettingInt("RESPAWN_INVULNERABLE_SECONDS", 3)
        )

    def start_countdown(self) -> int:
        """开赛前传送倒计时秒数（title 倒数）。"""
        return max(1, self.settings.GetSettingInt("START_COUNTDOWN_SECONDS", 5))

    def match_time(self) -> int:
        """全局默认比赛秒数（仅作兜底；实际以各地图模式的 match_time_minutes 为准）。"""
        return max(60, self.settings.GetSettingInt("MATCH_TIME_SECONDS", 300))

    def win_guild_contribution_per_kd(self) -> int:
        """胜队公会贡献：表现分 × 本倍率。"""
        return max(0, self.settings.GetSettingInt("WIN_GUILD_CONTRIBUTION_PER_KD", 10))

    def match_money_per_kill(self) -> int:
        return max(0, self.settings.GetSettingInt("MATCH_MONEY_PER_KILL", 200))

    def match_win_bonus(self) -> int:
        return max(0, self.settings.GetSettingInt("MATCH_WIN_BONUS", 2000))

    def match_mvp_bonus(self) -> int:
        return max(0, self.settings.GetSettingInt("MATCH_MVP_BONUS", 500))

    def assist_window_seconds(self) -> float:
        return max(0.5, self.settings.GetSettingFloat("ASSIST_WINDOW_SECONDS", 3.0))

    def match_assist_weight(self) -> float:
        return max(0.0, self.settings.GetSettingFloat("MATCH_ASSIST_WEIGHT", 0.5))

    def match_tk_weight(self) -> float:
        return max(0.0, self.settings.GetSettingFloat("MATCH_TK_WEIGHT", 1.5))

    def xp_per_kill(self) -> int:
        """已弃用：请用 xp_kill_for_team(team_size)。"""
        return max(0, self.settings.GetSettingInt("XP_PER_KILL", 5))

    def xp_kill_per_teammate(self) -> int:
        return max(0, self.settings.GetSettingInt("XP_KILL_PER_TEAMMATE", 2))

    def xp_kill_for_team(self, team_size: int) -> int:
        return xp_kill_for_team(team_size, per_teammate=self.xp_kill_per_teammate())

    def xp_assist_for_team(self, team_size: int) -> int:
        return xp_assist_for_team(team_size, per_teammate=self.xp_kill_per_teammate())

    def xp_per_level(self) -> int:
        return max(1, self.settings.GetSettingInt("XP_PER_LEVEL", 100))

    def max_level(self) -> int:
        return max(1, self.settings.GetSettingInt("MAX_LEVEL", 100))

    def xp_win_bonus_percent(self) -> int:
        return max(0, self.settings.GetSettingInt("XP_WIN_BONUS_PERCENT", 20))

    def xp_mvp_per_teammate(self) -> int:
        """MVP 额外 XP = 队伍人数 × 本值。"""
        return max(0, self.settings.GetSettingInt("XP_MVP_PER_TEAMMATE", 10))

    def match_money_per_kd(self) -> int:
        """已弃用，保留以免旧调用报错；请用 match_money_per_kill。"""
        return self.match_money_per_kill()

    def weapons_of_type(self, weapon_type: str) -> List[Dict[str, Any]]:
        return [w for w in self.weapons.values() if w["type"] == weapon_type]

    def weapons_of_category(self, weapon_type: str, category: str) -> List[Dict[str, Any]]:
        cat = str(category or "").strip().lower()
        return [
            w
            for w in self.weapons.values()
            if w["type"] == weapon_type and str(w.get("category") or "") == cat
        ]

    def categories_for_type(self, weapon_type: str) -> List[str]:
        preferred = list(CATEGORIES_BY_TYPE.get(weapon_type, ()))
        present = {
            str(w.get("category") or "")
            for w in self.weapons.values()
            if w["type"] == weapon_type and w.get("category")
        }
        ordered = [c for c in preferred if c in present]
        for c in sorted(present):
            if c not in ordered:
                ordered.append(c)
        return ordered
