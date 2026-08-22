# -*- coding: utf-8 -*-
"""地图配置 SQLite 存储。"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from endstone_arc_shooter_game.config import migrate_legacy_map, normalize_map, validate_map
from endstone_arc_shooter_game.language import PLUGIN_DATA_DIR

_SCHEMA = """
CREATE TABLE IF NOT EXISTS maps (
    id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    dimension TEXT NOT NULL DEFAULT 'overworld',
    pos1_x REAL, pos1_y REAL, pos1_z REAL,
    pos2_x REAL, pos2_y REAL, pos2_z REAL
);
CREATE TABLE IF NOT EXISTS map_modes (
    map_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    max_players_per_team INTEGER NOT NULL DEFAULT 8,
    target_score INTEGER NOT NULL DEFAULT 50,
    team_a_name TEXT NOT NULL DEFAULT '红队',
    team_b_name TEXT NOT NULL DEFAULT '蓝队',
    PRIMARY KEY (map_id, mode),
    FOREIGN KEY (map_id) REFERENCES maps(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS map_spawns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    map_id TEXT NOT NULL,
    mode TEXT NOT NULL,
    team_id TEXT NOT NULL,
    x REAL NOT NULL,
    y REAL NOT NULL,
    z REAL NOT NULL,
    radius REAL NOT NULL DEFAULT 0,
    yaw REAL,
    pitch REAL,
    FOREIGN KEY (map_id) REFERENCES maps(id) ON DELETE CASCADE
);
"""


class MapDatabase:
    def __init__(self, db_path: Optional[Path] = None, logger=None):
        self.db_path = db_path or (PLUGIN_DATA_DIR / "shooter.db")
        self.logger = logger
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._init_schema()
        self._migrate_from_json_if_needed()

    def _log(self, level: str, message: str) -> None:
        if self.logger is not None:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(message)
                return
        print(f"[{level.upper()}] {message}")

    def _init_schema(self) -> None:
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def _migrate_from_json_if_needed(self) -> None:
        json_path = PLUGIN_DATA_DIR / "maps.json"
        count = self._conn.execute("SELECT COUNT(*) AS c FROM maps").fetchone()["c"]
        if count > 0 or not json_path.exists():
            return
        try:
            doc = json.loads(json_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            self._log("warning", f"[ARCShooterGame] maps.json migration skipped: {e}")
            return
        items = doc.get("maps") if isinstance(doc, dict) else []
        if not isinstance(items, list) or not items:
            return
        imported = 0
        for raw in items:
            if not isinstance(raw, dict):
                continue
            entry = normalize_map(raw)
            if validate_map(entry):
                continue
            self.save_map(entry)
            imported += 1
        if imported <= 0:
            return
        backup = json_path.with_suffix(".json.bak")
        try:
            json_path.rename(backup)
            self._log("info", f"[ARCShooterGame] Migrated {imported} map(s) from maps.json to SQLite ({self.db_path.name})")
        except OSError as e:
            self._log("warning", f"[ARCShooterGame] maps.json migrated but backup failed: {e}")

    def load_all(self) -> Dict[str, Dict[str, Any]]:
        result: Dict[str, Dict[str, Any]] = {}
        rows = self._conn.execute("SELECT * FROM maps ORDER BY id").fetchall()
        for row in rows:
            map_id = row["id"]
            region: Dict[str, Any] = {}
            if row["pos1_x"] is not None:
                region["pos1"] = {"x": row["pos1_x"], "y": row["pos1_y"], "z": row["pos1_z"]}
            if row["pos2_x"] is not None:
                region["pos2"] = {"x": row["pos2_x"], "y": row["pos2_y"], "z": row["pos2_z"]}
            modes: List[Dict[str, Any]] = []
            mode_rows = self._conn.execute(
                "SELECT * FROM map_modes WHERE map_id = ? ORDER BY mode",
                (map_id,),
            ).fetchall()
            for mode_row in mode_rows:
                mode = mode_row["mode"]
                teams = {
                    "a": {"name": mode_row["team_a_name"], "spawns": []},
                    "b": {"name": mode_row["team_b_name"], "spawns": []},
                }
                spawn_rows = self._conn.execute(
                    "SELECT * FROM map_spawns WHERE map_id = ? AND mode = ? ORDER BY id",
                    (map_id, mode),
                ).fetchall()
                for spawn_row in spawn_rows:
                    spawn: Dict[str, Any] = {
                        "x": spawn_row["x"],
                        "y": spawn_row["y"],
                        "z": spawn_row["z"],
                        "radius": spawn_row["radius"] or 0,
                    }
                    if spawn_row["yaw"] is not None:
                        spawn["yaw"] = spawn_row["yaw"]
                    if spawn_row["pitch"] is not None:
                        spawn["pitch"] = spawn_row["pitch"]
                    team_id = spawn_row["team_id"]
                    if team_id in teams:
                        teams[team_id]["spawns"].append(spawn)
                modes.append(
                    {
                        "mode": mode,
                        "max_players_per_team": mode_row["max_players_per_team"],
                        "target_score": mode_row["target_score"],
                        "teams": teams,
                    }
                )
            result[map_id] = normalize_map(
                {
                    "id": map_id,
                    "display_name": row["display_name"],
                    "dimension": row["dimension"],
                    "region": region,
                    "modes": modes,
                }
            )
        return result

    def save_map(self, entry: Dict[str, Any]) -> Dict[str, Any]:
        entry = normalize_map(entry)
        map_id = entry["id"]
        region = entry.get("region") or {}
        pos1 = region.get("pos1") or {}
        pos2 = region.get("pos2") or {}
        with self._conn:
            self._conn.execute("DELETE FROM maps WHERE id = ?", (map_id,))
            self._conn.execute(
                """
                INSERT INTO maps (
                    id, display_name, dimension,
                    pos1_x, pos1_y, pos1_z,
                    pos2_x, pos2_y, pos2_z
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    map_id,
                    entry["display_name"],
                    entry.get("dimension") or "overworld",
                    pos1.get("x"),
                    pos1.get("y"),
                    pos1.get("z"),
                    pos2.get("x"),
                    pos2.get("y"),
                    pos2.get("z"),
                ),
            )
            for mode_cfg in entry.get("modes") or []:
                mode = mode_cfg["mode"]
                teams = mode_cfg.get("teams") or {}
                team_a = teams.get("a") or {}
                team_b = teams.get("b") or {}
                self._conn.execute(
                    """
                    INSERT INTO map_modes (
                        map_id, mode, max_players_per_team, target_score, team_a_name, team_b_name
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        map_id,
                        mode,
                        mode_cfg.get("max_players_per_team", 8),
                        mode_cfg.get("target_score", 50),
                        team_a.get("name", "红队"),
                        team_b.get("name", "蓝队"),
                    ),
                )
                for team_id in ("a", "b"):
                    team = teams.get(team_id) or {}
                    for spawn in team.get("spawns") or []:
                        self._conn.execute(
                            """
                            INSERT INTO map_spawns (
                                map_id, mode, team_id, x, y, z, radius, yaw, pitch
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                map_id,
                                mode,
                                team_id,
                                spawn["x"],
                                spawn["y"],
                                spawn["z"],
                                spawn.get("radius") or 0,
                                spawn.get("yaw"),
                                spawn.get("pitch"),
                            ),
                        )
        return entry

    def delete_map(self, map_id: str) -> bool:
        with self._conn:
            cur = self._conn.execute("DELETE FROM maps WHERE id = ?", (map_id,))
        return cur.rowcount > 0

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None
