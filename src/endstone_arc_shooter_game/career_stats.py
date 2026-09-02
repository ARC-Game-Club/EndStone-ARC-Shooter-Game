# -*- coding: utf-8 -*-
"""枪战生涯 KD / XP / 武器击杀统计（SQLite）。"""
from __future__ import annotations

import math
import sqlite3
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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
    losses INTEGER NOT NULL DEFAULT 0,
    draws INTEGER NOT NULL DEFAULT 0,
    mvps INTEGER NOT NULL DEFAULT 0,
    win_mvps INTEGER NOT NULL DEFAULT 0,
    lose_mvps INTEGER NOT NULL DEFAULT 0,
    xp INTEGER NOT NULL DEFAULT 0,
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


def level_from_xp(xp: int, *, xp_per_level: int = 100, max_level: int = 100) -> int:
    per = max(1, int(xp_per_level))
    cap = max(1, int(max_level))
    return min(cap, max(0, int(xp)) // per)


def xp_progress(xp: int, *, xp_per_level: int = 100, max_level: int = 100) -> Tuple[int, int, int]:
    """返回 (level, xp_into_level, xp_per_level)。满级时 into=0。"""
    per = max(1, int(xp_per_level))
    level = level_from_xp(xp, xp_per_level=per, max_level=max_level)
    if level >= max_level:
        return level, 0, per
    return level, max(0, int(xp)) % per, per


def calc_match_settlement_xp(
    kills: int,
    *,
    won: bool,
    mvp: bool,
    xp_per_kill: int = 5,
    win_bonus_percent: int = 20,
    mvp_per_teammate: int = 10,
    team_size: int = 1,
) -> int:
    """结算补发：胜方对「击杀基础 XP」的加成 + MVP（队伍人数 × 单价）。击杀当场 XP 另计。"""
    base = max(0, int(kills)) * max(0, int(xp_per_kill))
    bonus = 0
    if won and base > 0 and win_bonus_percent > 0:
        bonus += int(math.floor(base * (max(0, int(win_bonus_percent)) / 100.0)))
    if mvp:
        size = max(1, int(team_size))
        bonus += size * max(0, int(mvp_per_teammate))
    return max(0, bonus)


@dataclass
class CareerStats:
    name: str
    xuid: str = ""
    kills: int = 0
    deaths: int = 0
    matches: int = 0
    wins: int = 0
    losses: int = 0
    draws: int = 0
    mvps: int = 0
    win_mvps: int = 0
    lose_mvps: int = 0
    xp: int = 0
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

    def level(self, *, xp_per_level: int = 100, max_level: int = 100) -> int:
        return level_from_xp(self.xp, xp_per_level=xp_per_level, max_level=max_level)


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
        for col in (
            "mvps",
            "xp",
            "losses",
            "draws",
            "win_mvps",
            "lose_mvps",
        ):
            if col not in cols:
                self._conn.execute(
                    f"ALTER TABLE player_career ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
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
        keys = row.keys()

        def col(name: str, default: int = 0) -> int:
            return int(row[name] or 0) if name in keys else default

        return CareerStats(
            name=str(row["name"]),
            xuid=str(row["xuid"] or ""),
            kills=col("kills"),
            deaths=col("deaths"),
            matches=col("matches"),
            wins=col("wins"),
            losses=col("losses"),
            draws=col("draws"),
            mvps=col("mvps"),
            win_mvps=col("win_mvps"),
            lose_mvps=col("lose_mvps"),
            xp=col("xp"),
            weapon_kills=weapon_kills,
        )

    def list_ranked_by_kd(self) -> List[CareerStats]:
        """全体生涯按 KD 降序；同 KD 时击杀多者靠前。"""
        rows = self._conn.execute(
            "SELECT name, xuid, kills, deaths, matches, wins, losses, draws, "
            "mvps, win_mvps, lose_mvps, xp FROM player_career"
        ).fetchall()
        stats: List[CareerStats] = []
        for row in rows:
            keys = row.keys()

            def col(name: str, default: int = 0) -> int:
                return int(row[name] or 0) if name in keys else default

            stats.append(
                CareerStats(
                    name=str(row["name"]),
                    xuid=str(row["xuid"] or ""),
                    kills=col("kills"),
                    deaths=col("deaths"),
                    matches=col("matches"),
                    wins=col("wins"),
                    losses=col("losses"),
                    draws=col("draws"),
                    mvps=col("mvps"),
                    win_mvps=col("win_mvps"),
                    lose_mvps=col("lose_mvps"),
                    xp=col("xp"),
                )
            )
        stats.sort(key=lambda s: (-s.kd, -s.kills, -s.wins, s.name.lower()))
        return stats

    def add_xp(self, name: str, amount: int, *, xuid: str = "") -> CareerStats:
        name_s = str(name or "").strip()
        gain = max(0, int(amount))
        if not name_s or gain <= 0:
            return self.get(name_s)
        self._ensure_player(name_s, xuid)
        now = time.time()
        self._conn.execute(
            "UPDATE player_career SET xp = xp + ?, updated_at = ? WHERE name = ?",
            (gain, now, name_s),
        )
        self._conn.commit()
        return self.get(name_s)

    def record_kill(
        self,
        name: str,
        *,
        weapon_id: Optional[str] = None,
        xuid: str = "",
        xp_gain: int = 0,
    ) -> CareerStats:
        name_s = str(name or "").strip()
        if not name_s:
            return CareerStats(name="")
        self._ensure_player(name_s, xuid)
        now = time.time()
        gain = max(0, int(xp_gain))
        self._conn.execute(
            "UPDATE player_career SET kills = kills + 1, xp = xp + ?, updated_at = ? WHERE name = ?",
            (gain, now, name_s),
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
        draw: bool = False,
        mvp: bool = False,
        xuid: str = "",
        settlement_xp: int = 0,
    ) -> CareerStats:
        name_s = str(name or "").strip()
        if not name_s:
            return CareerStats(name="")
        self._ensure_player(name_s, xuid)
        now = time.time()
        xp_bonus = max(0, int(settlement_xp))
        # 平局优先；否则按胜/负
        is_draw = bool(draw)
        is_win = (not is_draw) and bool(won)
        is_loss = (not is_draw) and (not is_win)
        win_mvp = bool(mvp) and is_win
        lose_mvp = bool(mvp) and is_loss
        self._conn.execute(
            """
            UPDATE player_career SET
                matches = matches + 1,
                wins = wins + ?,
                losses = losses + ?,
                draws = draws + ?,
                mvps = mvps + ?,
                win_mvps = win_mvps + ?,
                lose_mvps = lose_mvps + ?,
                xp = xp + ?,
                updated_at = ?
            WHERE name = ?
            """,
            (
                1 if is_win else 0,
                1 if is_loss else 0,
                1 if is_draw else 0,
                1 if mvp else 0,
                1 if win_mvp else 0,
                1 if lose_mvp else 0,
                xp_bonus,
                now,
                name_s,
            ),
        )
        self._conn.commit()
        return self.get(name_s)
