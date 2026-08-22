# -*- coding: utf-8 -*-
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
weapons = json.loads((ROOT / "plugins/ARCShooterGame/weapons.json").read_text(encoding="utf-8"))["weapons"]
lines = []
for w in weapons:
    parts = [
        f'"id": "{w["id"]}"',
        f'"display_name": "{w["display_name"]}"',
        f'"item": "{w["item"]}"',
        f'"cost": {w["cost"]}',
        f'"type": "{w["type"]}"',
    ]
    if w.get("amount", 1) != 1:
        parts.append(f'"amount": {w["amount"]}')
    if w.get("extras"):
        extras = ", ".join(f'"{k}": {v}' for k, v in w["extras"].items())
        parts.append(f'"extras": {{{extras}}}')
    if w.get("ammo_scoreboard"):
        parts.append(f'"ammo_scoreboard": "{w["ammo_scoreboard"]}"')
        parts.append(f'"default_ammo": {w["default_ammo"]}')
    lines.append("        {" + ", ".join(parts) + "},")
body = "\n".join(lines)
config_path = ROOT / "src/endstone_arc_shooter_game/config.py"
text = config_path.read_text(encoding="utf-8")
text = re.sub(
    r"DEFAULT_WEAPONS = \{.*?\n    \],\n\}",
    'DEFAULT_WEAPONS = {\n    "_comment": "起始 1000 可买普通主+副；击杀 +50 攒点。MP5/RPG 为副武器。",\n    "weapons": [\n'
    + body
    + "\n    ],\n}",
    text,
    count=1,
    flags=re.S,
)
config_path.write_text(text, encoding="utf-8")
print("updated", config_path)
