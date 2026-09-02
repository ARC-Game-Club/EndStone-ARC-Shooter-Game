# -*- coding: utf-8 -*-
"""从弧光枪械 1.0 BP 的 gunConfig.maxAmmo 同步 ammo_scoreboard / default_ammo。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAIN_JS = (
    ROOT.parents[1]
    / "MCBEShooterGameServer"
    / "bedrock_server"
    / "worlds"
    / "ARCShooterGame"
    / "behavior_packs"
    / "弧光枪械1.0 BP"
    / "scripts"
    / "main.js"
)
WEAPONS_JSON = ROOT / "plugins" / "ARCShooterGame" / "weapons.json"
AMMO_REFERENCE = ROOT / "plugins" / "ARCShooterGame" / "aplok_ammo.json"

MAX_AMMO_RE = re.compile(
    r"'(arc:[a-z0-9_]+)':\s*\{\s*'maxAmmo':\s*(0x[0-9a-fA-F]+|\d+)"
)


def parse_gun_config(main_js: Path) -> dict[str, dict[str, int | str]]:
    if not main_js.is_file():
        raise FileNotFoundError(f"main.js not found: {main_js}")
    text = main_js.read_text(encoding="utf-8")
    out: dict[str, dict[str, int | str]] = {}
    for match in MAX_AMMO_RE.finditer(text):
        gun_id = match.group(1)
        raw = match.group(2)
        ammo = int(raw, 16) if raw.lower().startswith("0x") else int(raw)
        key = gun_id.split(":", 1)[1]
        out[key] = {"ammo_scoreboard": f"{key}Ammo", "default_ammo": ammo}
    return out


def apply_to_weapons(weapons_path: Path, ammo_map: dict[str, dict[str, int | str]]) -> list[str]:
    data = json.loads(weapons_path.read_text(encoding="utf-8"))
    changes: list[str] = []
    for weapon in data.get("weapons") or []:
        wid = str(weapon.get("id") or "")
        item = str(weapon.get("item") or "")
        if not wid or not item.startswith("arc:"):
            continue
        if wid not in ammo_map:
            continue
        spec = ammo_map[wid]
        objective = str(spec["ammo_scoreboard"])
        ammo = int(spec["default_ammo"])
        old_obj = weapon.get("ammo_scoreboard")
        old_ammo = weapon.get("default_ammo")
        if old_obj != objective or old_ammo != ammo:
            changes.append(f"{wid}: {old_obj}/{old_ammo} -> {objective}/{ammo}")
        weapon["ammo_scoreboard"] = objective
        weapon["default_ammo"] = ammo
    weapons_path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--main-js", type=Path, default=DEFAULT_MAIN_JS)
    parser.add_argument("--weapons", type=Path, default=WEAPONS_JSON)
    parser.add_argument("--reference", type=Path, default=AMMO_REFERENCE)
    args = parser.parse_args()

    ammo_map = parse_gun_config(args.main_js)
    args.reference.parent.mkdir(parents=True, exist_ok=True)
    args.reference.write_text(
        json.dumps(
            {
                "_comment": "从弧光枪械1.0 BP gunConfig.maxAmmo 提取；计分板为 {gunKey}Ammo",
                "_source": str(args.main_js),
                "weapons": ammo_map,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    changes = apply_to_weapons(args.weapons, ammo_map)
    print(f"parsed {len(ammo_map)} guns from {args.main_js}")
    print(f"updated reference: {args.reference}")
    if changes:
        print("weapons.json changes:")
        for line in changes:
            print(" ", line)
    else:
        print("weapons.json already matches mod ammo data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
