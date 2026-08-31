# -*- coding: utf-8 -*-
"""枪战生涯 KD / 武器击杀统计（SQLite）。"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from endstone_arc_shooter_game.language import PLUGIN_DATA_DIR

# (最低 KD, 稀有度, 头衔名)
KD_TITLE_TIERS: List[Tuple[float, str, str]] = [
    (5.0, "神话", "传奇枪王"),
    (3.0, "传奇", "枪械大师"),
    (2.0, "史诗", "精英枪手"),
    (1.0, "稀有", "熟练枪手"),
    (0.0, "普通", "见习枪手"),
]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS player_career (
    name TEXT PRIMARY KEY,
    xuid TEXT,
    kills INTEGER NOT NULL DEFAULT 0,
    deaths INTEGER NOT NULL DEFAULT 0,
    matches INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    mvps INTEGER NOT NULL DEFAULT 0,
    updated_at REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS player_weapon_kills (
    name TEXT NOT NULL,
    weapon_id TEXT NOT NULL,
    kills INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (name, weapon_id)
);
CREATE INDEX IF NOT EXISTS idx_career_xuid ON player_career(xuid);
"""


def career_kd(kills: int, deaths: int) -> float:
    k = max(0, int(kills))
    d = max(0, int(deaths))
    if d <= 0:
        return float(k)
    return float(k) / float(d)


def title_for_kd(kd: float) -> Tuple[str, str]:
    """返回 (稀有度, 头衔名)。"""
    kd = float(kd)
    for threshold, rarity, title in KD_TITLE_TIERS:
        if kd >= threshold:
            return rarity, title
    return "普通", "见习枪手"


def titles_unlocked_by_kd(kd: float) -> List[Tuple[str, str]]:
    """当前 KD 应解锁的全部档位（含更低档）。"""
    kd = float(kd)
    out: List[Tuple[str, str]] = []
    for threshold, rarity, title in reversed(KD_TITLE_TIERS):
        if kd >= threshold:
            out.append((rarity, title))
    return out


@dataclass
class CareerStats:
    name: str
    xuid: str = ""
    kills: int = 0
    deaths: int = 0
    matches: int = 0
    wins: int = 0
    mvps: int = 0
    weapon_kills: Dict[str, int] = field(default_factory=dict)

    @property
    def kd(self) -> float:
        return career_kd(self.kills, self.deaths)

    @property
    def title_rarity(self) -> str:
        return title_for_kd(self.kd)[0]

    @property
    def title_name(self) -> str:
        return title_for_kd(self.kd)[1]


class CareerStore:
    def __init__(self, db_path: Optional[Path] = None, logger=None):
        self.db_path = db_path or (PLUGIN_DATA_DIR / "shooter.db")
        self.logger = logger
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()

    def _migrate(self) -> None:
        cols = {
            str(r[1])
            for r in self._conn.execute("PRAGMA table_info(player_career)").fetchall()
        }
        if "mvps" not in cols:
            self._conn.execute(
                "ALTER TABLE player_career ADD COLUMN mvps INTEGER NOT NULL DEFAULT 0"
            )

    def _log(self, level: str, message: str) -> None:
        if self.logger is not None:
            fn = getattr(self.logger, level, None)
            if callable(fn):
                fn(message)
                return
        print(f"[{level.upper()}] {message}")

    def close(self) -> None:
        try:
            self._conn.close()
        except Exception:
            pass

    def _ensure_player(self, name: str, xuid: str = "") -> None:
        name_s = str(name or "").strip()
        if not name_s:
            return
        now = time.time()
        self._conn.execute(
            "INSERT OR IGNORE INTO player_career (name, xuid, updated_at) VALUES (?, ?, ?)",
            (name_s, str(xuid or ""), now),
        )
        if xuid:
            self._conn.execute(
                "UPDATE player_career SET xuid = ? WHERE name = ? AND (xuid IS NULL OR xuid = '')",
                (str(xuid), name_s),
            )

    def get(self, name: str) -> CareerStats:
        name_s = str(name or "").strip()
        row = self._conn.execute(
            "SELECT * FROM player_career WHERE name = ?", (name_s,)
        ).fetchone()
        weapon_rows = self._conn.execute(
            "SELECT weapon_id, kills FROM player_weapon_kills WHERE name = ? ORDER BY kills DESC",
            (name_s,),
        ).fetchall()
        weapon_kills = {str(r["weapon_id"]): int(r["kills"]) for r in weapon_rows}
        if row is None:
            return CareerStats(name=name_s, weapon_kills=weapon_kills)
        return CareerStats(
            name=str(row["name"]),
            xuid=str(row["xuid"] or ""),
            kills=int(row["kills"] or 0),
            deaths=int(row["deaths"] or 0),
            matches=int(row["matches"] or 0),
            wins=int(row["wins"] or 0),
            mvps=int(row["mvps"] or 0) if "mvps" in row.keys() else 0,
            weapon_kills=weapon_kills,
        )

    def record_kill(
        self,
        name: str,
        *,
        weapon_id: Optional[str] = None,
        xuid: str = "",
    ) -> CareerStats:
        name_s = str(name or "").strip()
        if not name_s:
            return CareerStats(name="")
        self._ensure_player(name_s, xuid)
        now = time.time()
        self._conn.execute(
            "UPDATE player_career SET kills = kills + 1, updated_at = ? WHERE name = ?",
            (now, name_s),
        )
        wid = str(weapon_id or "").strip()
        if wid:
            self._conn.execute(
                "INSERT INTO player_weapon_kills (name, weapon_id, kills) VALUES (?, ?, 1) "
                "ON CONFLICT(name, weapon_id) DO UPDATE SET kills = kills + 1",
                (name_s, wid),
            )
        self._conn.commit()
        return self.get(name_s)

    def record_death(self, name: str, *, xuid: str = "") -> CareerStats:
        name_s = str(name or "").strip()
        if not name_s:
            return CareerStats(name="")
        self._ensure_player(name_s, xuid)
        now = time.time()
        self._conn.execute(
            "UPDATE player_career SET deaths = deaths + 1, updated_at = ? WHERE name = ?",
            (now, name_s),
        )
        self._conn.commit()
        return self.get(name_s)

    def record_match_end(
        self,
        name: str,
        *,
        won: bool = False,
        mvp: bool = False,
        xuid: str = "",
    ) -> CareerStats:
        name_s = str(name or "").strip()
        if not name_s:
            return CareerStats(name="")
        self._ensure_player(name_s, xuid)
        now = time.time()
        if won and mvp:
            self._conn.execute(
                "UPDATE player_career SET matches = matches + 1, wins = wins + 1, "
                "mvps = mvps + 1, updated_at = ? WHERE name = ?",
                (now, name_s),
            )
        elif won:
            self._conn.execute(
                "UPDATE player_career SET matches = matches + 1, wins = wins + 1, updated_at = ? WHERE name = ?",
                (now, name_s),
            )
        elif mvp:
            self._conn.execute(
                "UPDATE player_career SET matches = matches + 1, mvps = mvps + 1, updated_at = ? WHERE name = ?",
                (now, name_s),
            )
        else:
            self._conn.execute(
                "UPDATE player_career SET matches = matches + 1, updated_at = ? WHERE name = ?",
                (now, name_s),
            )
        self._conn.commit()
        return self.get(name_s)
