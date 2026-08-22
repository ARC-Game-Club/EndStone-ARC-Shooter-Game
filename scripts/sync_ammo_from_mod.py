# -*- coding: utf-8 -*-
"""从 Aplok 枪械 BP 的 reload 函数同步 ammo_scoreboard / default_ammo 到 weapons.json。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MOD_RELOAD = (
    ROOT.parents[1]
    / "MCBEShooterGameServer"
    / "bedrock_server"
    / "worlds"
    / "ARCShooterGame"
    / "behavior_packs"
    / "Aplok枪械BP"
    / "functions"
    / "weapons"
    / "reload"
)
WEAPONS_JSON = ROOT / "plugins" / "ARCShooterGame" / "weapons.json"
AMMO_REFERENCE = ROOT / "plugins" / "ARCShooterGame" / "aplok_ammo.json"

SET_RE = re.compile(
    r"scoreboard\s+players\s+set\s+.+?\s+(?P<objective>[a-zA-Z0-9_]+)\s+(?P<value>\d+)",
    re.IGNORECASE,
)


def parse_reload_dir(reload_dir: Path) -> dict[str, dict[str, int | str]]:
    if not reload_dir.is_dir():
        raise FileNotFoundError(f"reload dir not found: {reload_dir}")
    out: dict[str, dict[str, int | str]] = {}
    for path in sorted(reload_dir.glob("*.mcfunction")):
        weapon_id = path.stem
        objectives: dict[str, int] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            match = SET_RE.search(line)
            if not match:
                continue
            objective = match.group("objective")
            value = int(match.group("value"))
            objectives[objective] = max(objectives.get(objective, 0), value)
        if not objectives:
            continue
        if len(objectives) != 1:
            raise ValueError(f"{path.name}: expected one scoreboard objective, got {objectives}")
        objective, ammo = next(iter(objectives.items()))
        out[weapon_id] = {"ammo_scoreboard": objective, "default_ammo": ammo}
    return out


def apply_to_weapons(weapons_path: Path, ammo_map: dict[str, dict[str, int | str]]) -> list[str]:
    data = json.loads(weapons_path.read_text(encoding="utf-8"))
    changes: list[str] = []
    for weapon in data.get("weapons") or []:
        wid = str(weapon.get("id") or "")
        item = str(weapon.get("item") or "")
        if not wid or not item.startswith("trenbankai:"):
            continue
        spec = ammo_map.get(wid)
        if spec is None:
            continue
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
    parser.add_argument(
        "--reload-dir",
        type=Path,
        default=DEFAULT_MOD_RELOAD,
        help="Aplok BP functions/weapons/reload directory",
    )
    parser.add_argument("--weapons", type=Path, default=WEAPONS_JSON)
    parser.add_argument("--reference", type=Path, default=AMMO_REFERENCE)
    args = parser.parse_args()

    ammo_map = parse_reload_dir(args.reload_dir)
    args.reference.parent.mkdir(parents=True, exist_ok=True)
    args.reference.write_text(
        json.dumps(
            {
                "_comment": "从 Aplok 枪械 BP reload 函数自动提取；运行 scripts/sync_ammo_from_mod.py 更新",
                "_source": str(args.reload_dir),
                "weapons": ammo_map,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    changes = apply_to_weapons(args.weapons, ammo_map)
    print(f"parsed {len(ammo_map)} weapons from {args.reload_dir}")
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
