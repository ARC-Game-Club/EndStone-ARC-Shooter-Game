# -*- coding: utf-8 -*-
"""从「弧光枪械 1.0 BP」生成 weapons.json / arc_ammo 参考表，并回写 DEFAULT_WEAPONS。"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BP = (
    ROOT.parents[1]
    / "MCBEShooterGameServer"
    / "bedrock_server"
    / "worlds"
    / "ARCShooterGame"
    / "behavior_packs"
    / "弧光枪械1.0 BP"
)
MAIN_JS = BP / "scripts" / "main.js"
LANG = BP / "texts" / "zh_CN.lang"
WEAPONS_JSON = ROOT / "plugins" / "ARCShooterGame" / "weapons.json"
AMMO_REF = ROOT / "plugins" / "ARCShooterGame" / "aplok_ammo.json"

# primary / secondary 分类（手枪作副武；冲锋枪为主武）
SECONDARY_IDS = {
    "m1911",
    "glock17",
    "pdp",
    "mpl1",
}

# 价格：起始 1000 可买普通主+副；贵枪需攒击杀点
COSTS: dict[str, int] = {
    # pistols
    "m1911": 250,
    "glock17": 300,
    "pdp": 320,
    "mpl1": 350,
    # SMGs (primary)
    "pp2000": 450,
    "pmx": 480,
    "mp5": 500,
    "ump45": 520,
    "k7": 550,
    "p90": 600,
    # rifles
    "m4": 650,
    "scarl": 700,
    "qbz95": 700,
    "qbz191": 720,
    "sar80": 720,
    "ak12": 750,
    "ak47": 800,
    "scarh": 900,
    "rpk74": 950,
    "qbb95": 1100,
    # shotguns
    "fp6": 700,
    "spas12": 850,
    "aa12": 1000,
    "ultraleggero": 1200,
    # DMR
    "saiga308": 900,
    "hcar": 1000,
    "svch": 1200,
    # LMG
    "m249": 1300,
    "minimi": 1300,
    # snipers
    "mrad": 1400,
    "vshk": 1450,
    "gm6_lynx": 1500,
}

# 商店展示顺序（同类内按价格）
PRIMARY_ORDER = [
    "m4",
    "scarl",
    "qbz95",
    "qbz191",
    "sar80",
    "ak12",
    "fp6",
    "ak47",
    "spas12",
    "scarh",
    "saiga308",
    "rpk74",
    "aa12",
    "hcar",
    "qbb95",
    "ultraleggero",
    "svch",
    "m249",
    "minimi",
    "mrad",
    "vshk",
    "gm6_lynx",
    "pp2000",
    "pmx",
    "mp5",
    "ump45",
    "k7",
    "p90",
]
SECONDARY_ORDER = [
    "m1911",
    "glock17",
    "pdp",
    "mpl1",
]

# category 筛选 + 军械库解锁等级（与计划表一致）
CATEGORIES: dict[str, str] = {
    "m4": "assault_rifle",
    "scarl": "assault_rifle",
    "qbz95": "assault_rifle",
    "qbz191": "assault_rifle",
    "sar80": "assault_rifle",
    "ak12": "assault_rifle",
    "ak47": "assault_rifle",
    "scarh": "assault_rifle",
    "rpk74": "lmg",
    "qbb95": "lmg",
    "m249": "lmg",
    "minimi": "lmg",
    "fp6": "shotgun",
    "spas12": "shotgun",
    "aa12": "shotgun",
    "ultraleggero": "shotgun",
    "saiga308": "dmr",
    "hcar": "dmr",
    "svch": "dmr",
    "mrad": "sniper",
    "vshk": "sniper",
    "gm6_lynx": "sniper",
    "shield": "shield",
    "m1911": "pistol",
    "glock17": "pistol",
    "pdp": "pistol",
    "mpl1": "pistol",
    "pp2000": "smg",
    "pmx": "smg",
    "mp5": "smg",
    "ump45": "smg",
    "k7": "smg",
    "p90": "smg",
    "silencefd": "knife",
    "m84_grenade": "flash",
    "mk2_grenade": "frag",
    "l83a1_grenade": "smoke",
    "landmine": "mine",
    "arc_armor": "armor",
}

UNLOCK_LEVELS: dict[str, int] = {
    "m4": 0,
    "m1911": 0,
    "silencefd": 0,
    "mk2_grenade": 0,
    "glock17": 2,
    "m84_grenade": 2,
    "pp2000": 4,
    "l83a1_grenade": 4,
    "fp6": 5,
    "pdp": 5,
    "scarl": 8,
    "landmine": 8,
    "mpl1": 8,
    "svch": 10,
    "qbz95": 10,
    "pmx": 10,
    "shield": 10,
    "spas12": 15,
    "mp5": 15,
    "arc_armor": 15,
    "ak12": 20,
    "sar80": 20,
    "qbz191": 20,
    "ump45": 20,
    "ak47": 25,
    "k7": 25,
    "saiga308": 25,
    "scarh": 30,
    "p90": 30,
    "rpk74": 30,
    "aa12": 40,
    "hcar": 40,
    "qbb95": 50,
    "ultraleggero": 50,
    "m249": 60,
    "minimi": 60,
    "mrad": 70,
    "vshk": 80,
    "gm6_lynx": 90,
}


def strip_color(text: str) -> str:
    return re.sub(r"§.", "", text or "").strip()


def parse_lang(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = strip_color(value)
    return out


def parse_max_ammo(path: Path) -> dict[str, int]:
    text = path.read_text(encoding="utf-8")
    pat = re.compile(r"'(arc:[a-z0-9_]+)':\s*\{\s*'maxAmmo':\s*(0x[0-9a-fA-F]+|\d+)")
    out: dict[str, int] = {}
    for m in pat.finditer(text):
        gun_id, raw = m.group(1), m.group(2)
        val = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
        out[gun_id] = val
    return out


def gun_entry(gun_id: str, max_ammo: int, names: dict[str, str], wtype: str) -> dict:
    key = gun_id.split(":", 1)[1]
    display = names.get(f"item.{gun_id}.name") or key.upper()
    return {
        "id": key,
        "display_name": display,
        "item": gun_id,
        "cost": int(COSTS.get(key, 800)),
        "type": wtype,
        "ammo_scoreboard": f"{key}Ammo",
        "default_ammo": int(max_ammo),
        "category": CATEGORIES.get(key, ""),
        "unlock_level": int(UNLOCK_LEVELS.get(key, 0)),
    }


def build_weapons(ammo: dict[str, int], names: dict[str, str]) -> list[dict]:
    weapons: list[dict] = []
    by_id = {gid.split(":", 1)[1]: (gid, ammo[gid]) for gid in ammo}

    for key in PRIMARY_ORDER:
        if key not in by_id:
            raise KeyError(f"missing primary gun in BP: {key}")
        gid, max_ammo = by_id[key]
        weapons.append(gun_entry(gid, max_ammo, names, "primary"))

    weapons.append(
        {
            "id": "shield",
            "display_name": "盾牌",
            "item": "minecraft:shield",
            "cost": 700,
            "type": "primary",
            "category": CATEGORIES["shield"],
            "unlock_level": UNLOCK_LEVELS["shield"],
        }
    )

    for key in SECONDARY_ORDER:
        if key not in by_id:
            raise KeyError(f"missing secondary gun in BP: {key}")
        gid, max_ammo = by_id[key]
        weapons.append(gun_entry(gid, max_ammo, names, "secondary"))

    weapons.append(
        {
            "id": "silencefd",
            "display_name": names.get("item.arc:silencefd.name") or "战术匕首",
            "item": "arc:silencefd",
            "cost": 100,
            "type": "melee",
            "category": CATEGORIES["silencefd"],
            "unlock_level": UNLOCK_LEVELS["silencefd"],
        }
    )

    weapons.append(
        {
            "id": "arc_armor",
            "display_name": "弧光防弹套装",
            "item": "arc:6b47_helmet",
            "cost": 500,
            "type": "armor",
            "category": CATEGORIES["arc_armor"],
            "unlock_level": UNLOCK_LEVELS["arc_armor"],
            "extras": {
                "arc:6b47_helmet": 1,
                "arc:6b45_vest": 1,
                "arc:emr_suit": 1,
                "arc:balaclava": 1,
            },
        }
    )

    weapons.extend(
        [
            {
                "id": "m84_grenade",
                "display_name": names.get("item.arc:m84_grenade.name") or "M84 闪光弹",
                "item": "arc:m84_grenade",
                "cost": 70,
                "type": "gadget",
                "category": CATEGORIES["m84_grenade"],
                "unlock_level": UNLOCK_LEVELS["m84_grenade"],
            },
            {
                "id": "mk2_grenade",
                "display_name": names.get("item.arc:mk2_grenade.name") or "Mk 2 破片手雷",
                "item": "arc:mk2_grenade",
                "cost": 90,
                "type": "gadget",
                "category": CATEGORIES["mk2_grenade"],
                "unlock_level": UNLOCK_LEVELS["mk2_grenade"],
            },
            {
                "id": "l83a1_grenade",
                "display_name": names.get("item.arc:l83a1_grenade.name") or "L83A1 烟雾弹",
                "item": "arc:l83a1_grenade",
                "cost": 90,
                "type": "gadget",
                "category": CATEGORIES["l83a1_grenade"],
                "unlock_level": UNLOCK_LEVELS["l83a1_grenade"],
            },
            {
                "id": "landmine",
                "display_name": names.get("item.arc:landmine_item.name") or "地雷",
                "item": "arc:landmine_item",
                "cost": 110,
                "type": "gadget",
                "category": CATEGORIES["landmine"],
                "unlock_level": UNLOCK_LEVELS["landmine"],
            },
        ]
    )

    known = set(PRIMARY_ORDER) | set(SECONDARY_ORDER)
    leftover = sorted(set(by_id) - known)
    if leftover:
        raise ValueError(f"guns not classified: {leftover}")
    return weapons


def main() -> None:
    if not MAIN_JS.is_file():
        raise SystemExit(f"BP main.js not found: {MAIN_JS}")
    ammo = parse_max_ammo(MAIN_JS)
    names = parse_lang(LANG)
    weapons = build_weapons(ammo, names)

    ammo_map = {
        w["id"]: {"ammo_scoreboard": w["ammo_scoreboard"], "default_ammo": w["default_ammo"]}
        for w in weapons
        if "ammo_scoreboard" in w
    }
    AMMO_REF.write_text(
        json.dumps(
            {
                "_comment": "从弧光枪械1.0 BP main.js gunConfig.maxAmmo 提取；计分板为 {gunKey}Ammo",
                "_source": str(MAIN_JS),
                "weapons": ammo_map,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    doc = {
        "_comment": "弧光枪械 1.0：弹药走计分板 {id}Ammo；起始 1000 可买普通主+副。",
        "weapons": weapons,
    }
    WEAPONS_JSON.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {len(weapons)} weapons -> {WEAPONS_JSON}")
    print(f"wrote ammo ref ({len(ammo_map)}) -> {AMMO_REF}")


if __name__ == "__main__":
    main()
