# -*- coding: utf-8 -*-
"""按生涯击杀数回填 XP（击杀 × XP_PER_KILL），用于等级系统上线前的数据校准。"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(
    r"C:\Users\81135\Documents\SERVO\MCBE\MCBEShooterGameServer\bedrock_server\plugins\ARCShooterGame\shooter.db"
)
XP_PER_KILL = 5
XP_PER_LEVEL = 100


def main() -> None:
    if not DB_PATH.is_file():
        raise SystemExit(f"database not found: {DB_PATH}")

    backup = DB_PATH.with_suffix(f".db.bak-{int(time.time())}")
    shutil.copy2(DB_PATH, backup)
    print(f"backup: {backup}")

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT name, kills, xp FROM player_career ORDER BY kills DESC"
    ).fetchall()
    now = time.time()
    updated = 0
    print(f"players={len(rows)}  formula= kills * {XP_PER_KILL}")
    for row in rows:
        name = str(row["name"])
        kills = max(0, int(row["kills"] or 0))
        old_xp = max(0, int(row["xp"] or 0))
        new_xp = kills * XP_PER_KILL
        if new_xp == old_xp:
            print(
                f"  skip {name}: kills={kills} xp={old_xp} (Lv{old_xp // XP_PER_LEVEL})"
            )
            continue
        conn.execute(
            "UPDATE player_career SET xp = ?, updated_at = ? WHERE name = ?",
            (new_xp, now, name),
        )
        updated += 1
        print(
            f"  {name}: kills={kills} xp {old_xp}(Lv{old_xp // XP_PER_LEVEL})"
            f" -> {new_xp}(Lv{new_xp // XP_PER_LEVEL})"
        )
    conn.commit()
    conn.close()
    print(f"done: updated {updated} player(s)")


if __name__ == "__main__":
    main()
