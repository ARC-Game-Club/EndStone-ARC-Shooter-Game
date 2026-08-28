# -*- coding: utf-8 -*-
"""大厅 / 对局状态机。不依赖 Endstone，便于单测。"""
from __future__ import annotations

import math
import random
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from endstone_arc_shooter_game.config import IMPLEMENTED_MODES, build_runtime_map_cfg, mode_playable

STATE_LOBBY = "lobby"
STATE_COUNTDOWN = "countdown"
STATE_BUYING = "buying"
STATE_PLAYING = "playing"

TEAM_A = "a"
TEAM_B = "b"


def pick_spawn(spawns: List[Dict[str, Any]]) -> Dict[str, float]:
    spawn = random.choice(spawns)
    radius = float(spawn.get("radius") or 0)
    x = float(spawn["x"])
    y = float(spawn["y"])
    z = float(spawn["z"])
    if radius > 0:
        angle = random.uniform(0, 2 * math.pi)
        dist = random.uniform(0, radius)
        x += dist * math.cos(angle)
        z += dist * math.sin(angle)
    return {
        "x": x,
        "y": y,
        "z": z,
        "yaw": spawn.get("yaw"),
        "pitch": spawn.get("pitch"),
    }


def apply_kill(
    score_a: int,
    score_b: int,
    killer_team: str,
    victim_team: str,
    target_score: int,
    kill_reward: int,
    killer_points: int,
) -> Dict[str, Any]:
    friendly = killer_team == victim_team
    if friendly:
        if killer_team == TEAM_A:
            score_a = max(0, score_a - 1)
        else:
            score_b = max(0, score_b - 1)
        reward = 0
    else:
        if killer_team == TEAM_A:
            score_a += 1
        else:
            score_b += 1
        reward = max(0, int(kill_reward))
        killer_points += reward
    winner = None
    if not friendly:
        if score_a >= target_score:
            winner = TEAM_A
        elif score_b >= target_score:
            winner = TEAM_B
    return {
        "score_a": score_a,
        "score_b": score_b,
        "killer_points": killer_points,
        "reward": reward,
        "friendly": friendly,
        "winner": winner,
    }


def first_empty_or_first(occupied: List[Optional[str]], capacity: int) -> int:
    if capacity <= 0:
        return 0
    for i in range(capacity):
        if i >= len(occupied) or not occupied[i]:
            return i
    return 0


@dataclass
class PlayerState:
    name: str
    team: str
    points: int
    kills: int = 0
    deaths: int = 0
    primary_id: Optional[str] = None
    secondary_id: Optional[str] = None
    armor_id: Optional[str] = None
    gadgets: List[Optional[str]] = field(default_factory=list)
    still_in: bool = True


@dataclass
class Lobby:
    admin: str
    lobby_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    map_id: Optional[str] = None
    mode: Optional[str] = None
    map_cfg: Optional[Dict[str, Any]] = None
    state: str = STATE_LOBBY
    lobby_started_at: float = 0.0
    countdown_ends_at: float = 0.0
    buy_ends_at: float = 0.0
    match_ends_at: float = 0.0
    players: Dict[str, PlayerState] = field(default_factory=dict)
    score_a: int = 0
    score_b: int = 0
    history: List[PlayerState] = field(default_factory=list)
    # 已提示过的秒数标记，避免 tick 重复广播（如 "60"、"10"…"1"）
    announced_secs: Set[str] = field(default_factory=set)

    @property
    def display_name(self) -> str:
        if self.map_cfg:
            return str(self.map_cfg.get("display_name") or self.map_cfg.get("id") or self.lobby_id)
        return self.lobby_id

    @property
    def active_mode(self) -> str:
        if self.map_cfg:
            return str(self.map_cfg.get("mode") or self.mode or "tdm").lower()
        return str(self.mode or "").lower()

    @property
    def max_per_team(self) -> int:
        if self.map_cfg:
            return int(self.map_cfg.get("max_players_per_team") or 8)
        return 8

    @property
    def target_score(self) -> int:
        if self.map_cfg:
            return int(self.map_cfg.get("target_score") or 50)
        return 50

    @property
    def match_time_minutes(self) -> int:
        if self.map_cfg:
            try:
                return max(1, int(self.map_cfg.get("match_time_minutes") or 5))
            except (TypeError, ValueError):
                return 5
        return 5

    @property
    def match_time_seconds(self) -> int:
        return self.match_time_minutes * 60

    def team_name(self, team_id: str) -> str:
        team = (self.map_cfg.get("teams") or {}).get(team_id) if self.map_cfg else {}
        team = team or {}
        return str(team.get("name") or ("红队" if team_id == TEAM_A else "蓝队"))

    def team_spawns(self, team_id: str) -> List[Dict[str, Any]]:
        if not self.map_cfg:
            return []
        team = (self.map_cfg.get("teams") or {}).get(team_id) or {}
        return list(team.get("spawns") or [])

    def online_players(self) -> List[PlayerState]:
        return [p for p in self.players.values() if p.still_in]

    def team_count(self, team_id: str) -> int:
        return sum(1 for p in self.online_players() if p.team == team_id)

    def player_count(self) -> int:
        return len(self.online_players())

    def pick_join_team(self) -> Optional[str]:
        a = self.team_count(TEAM_A)
        b = self.team_count(TEAM_B)
        cap = self.max_per_team
        if a < cap and (a <= b or b >= cap):
            return TEAM_A
        if b < cap:
            return TEAM_B
        if a < cap:
            return TEAM_A
        return None

    def can_join(self) -> Tuple[bool, str]:
        if self.pick_join_team() is None:
            return False, "full"
        return True, "ok"

    def join(self, player_name: str, starting_points: int, now: Optional[float] = None) -> Tuple[bool, str]:
        now = time.time() if now is None else now
        ok, reason = self.can_join()
        if not ok:
            return False, reason
        team = self.pick_join_team()
        if team is None:
            return False, "full"
        became_admin = self.player_count() == 0
        if self.lobby_started_at <= 0:
            self.lobby_started_at = now
        if not self.admin:
            self.admin = player_name
            became_admin = True
        self.players[player_name] = PlayerState(
            name=player_name,
            team=team,
            points=int(starting_points),
        )
        return True, "admin" if became_admin else "ok"

    def leave(self, player_name: str) -> Optional[str]:
        ps = self.players.pop(player_name, None)
        if ps is None:
            return None
        ps.still_in = False
        if self.state in (STATE_BUYING, STATE_PLAYING):
            self.history.append(ps)
        new_admin = None
        if self.admin == player_name:
            remaining = self.online_players()
            self.admin = remaining[0].name if remaining else None
            new_admin = self.admin
        return new_admin

    def kick(self, target_name: str) -> bool:
        if target_name not in self.players:
            return False
        if target_name == self.admin:
            return False
        self.players.pop(target_name, None)
        return True

    def set_team(self, player_name: str, team: str) -> Tuple[bool, str]:
        ps = self.players.get(player_name)
        if ps is None:
            return False, "missing"
        if team not in (TEAM_A, TEAM_B):
            return False, "bad_team"
        if ps.team == team:
            return True, "same"
        if self.team_count(team) >= self.max_per_team:
            return False, "full"
        ps.team = team
        return True, "ok"

    def set_map_and_mode(self, map_cfg: Dict[str, Any], mode: str) -> Tuple[bool, str]:
        mode_key = str(mode or "").strip().lower()
        if mode_key not in IMPLEMENTED_MODES:
            return False, "unimplemented"
        if not mode_playable(map_cfg, mode_key):
            return False, "not_ready"
        runtime = build_runtime_map_cfg(map_cfg, mode_key)
        if runtime is None:
            return False, "not_ready"
        self.map_id = map_cfg["id"]
        self.mode = mode_key
        self.map_cfg = runtime
        return True, "ok"

    def can_start(self) -> Tuple[bool, str]:
        if self.state != STATE_LOBBY:
            return False, "not_lobby"
        if not self.map_id or not self.mode or self.map_cfg is None:
            return False, "need_map"
        if self.active_mode not in IMPLEMENTED_MODES:
            return False, "unimplemented"
        if self.player_count() < 2:
            return False, "need_players"
        if self.team_count(TEAM_A) == 0 or self.team_count(TEAM_B) == 0:
            return False, "need_players"
        if not self.team_spawns(TEAM_A) or not self.team_spawns(TEAM_B):
            return False, "need_spawns"
        return True, "ok"

    def begin_countdown(self, countdown_seconds: int, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self.state = STATE_COUNTDOWN
        self.countdown_ends_at = now + max(1, int(countdown_seconds))
        self.announced_secs = set()

    def begin_buy(self, buy_seconds: int, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self.state = STATE_BUYING
        self.buy_ends_at = now + max(0, int(buy_seconds))
        self.score_a = 0
        self.score_b = 0
        self.announced_secs = set()

    def begin_playing(self, match_seconds: int = 300, now: Optional[float] = None) -> None:
        now = time.time() if now is None else now
        self.state = STATE_PLAYING
        self.match_ends_at = now + max(1, int(match_seconds))
        self.announced_secs = set()

    def cancel_countdown(self) -> None:
        self.state = STATE_LOBBY
        self.countdown_ends_at = 0.0
        self.announced_secs = set()

    def lobby_timed_out(self, timeout_seconds: int, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if self.state != STATE_LOBBY:
            return False
        return now - self.lobby_started_at >= timeout_seconds

    def countdown_remaining(self, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        return max(0.0, self.countdown_ends_at - now)

    def buy_remaining(self, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        return max(0.0, self.buy_ends_at - now)

    def match_remaining(self, now: Optional[float] = None) -> float:
        now = time.time() if now is None else now
        return max(0.0, self.match_ends_at - now)

    def match_timed_out(self, now: Optional[float] = None) -> bool:
        now = time.time() if now is None else now
        if self.state != STATE_PLAYING:
            return False
        return self.match_ends_at > 0 and now >= self.match_ends_at

    def mark_announced(self, key: str) -> bool:
        """首次标记成功返回 True，已提示过则 False。"""
        if key in self.announced_secs:
            return False
        self.announced_secs.add(key)
        return True

    def teams_ready_to_start(self) -> bool:
        return (
            self.player_count() >= 2
            and self.team_count(TEAM_A) > 0
            and self.team_count(TEAM_B) > 0
        )

    def winner_by_score(self) -> Optional[str]:
        if self.score_a > self.score_b:
            return TEAM_A
        if self.score_b > self.score_a:
            return TEAM_B
        return None

    def apply_player_kill(self, killer_name: str, victim_name: str, kill_reward: int) -> Optional[Dict[str, Any]]:
        killer = self.players.get(killer_name)
        victim = self.players.get(victim_name)
        if killer is None or victim is None:
            return None
        if not killer.still_in or not victim.still_in:
            return None
        if self.state not in (STATE_BUYING, STATE_PLAYING):
            return None
        result = apply_kill(
            self.score_a,
            self.score_b,
            killer.team,
            victim.team,
            self.target_score,
            kill_reward,
            killer.points,
        )
        self.score_a = result["score_a"]
        self.score_b = result["score_b"]
        killer.points = result["killer_points"]
        victim.deaths += 1
        if not result["friendly"]:
            killer.kills += 1
        result["killer"] = killer
        result["victim"] = victim
        return result

    def remaining_winner(self) -> Optional[str]:
        a = self.team_count(TEAM_A)
        b = self.team_count(TEAM_B)
        if a == 0 and b == 0:
            return None
        if a == 0:
            return TEAM_B
        if b == 0:
            return TEAM_A
        return None

    def result_rows(self) -> List[PlayerState]:
        rows = list(self.history)
        seen = {p.name for p in rows}
        for ps in self.players.values():
            if ps.name not in seen:
                rows.append(ps)
        return rows

    def record_purchase(self, player_name: str, weapon: Dict[str, Any], gadget_capacity: int) -> Tuple[int, Optional[str]]:
        ps = self.players.get(player_name)
        if ps is None:
            return 0, None
        wtype = weapon["type"]
        wid = weapon["id"]
        if wtype == "primary":
            old = ps.primary_id
            ps.primary_id = wid
            return 0, old
        if wtype == "secondary":
            old = ps.secondary_id
            ps.secondary_id = wid
            return 0, old
        if wtype == "armor":
            old = ps.armor_id
            ps.armor_id = wid
            return 0, old
        if len(ps.gadgets) < gadget_capacity:
            ps.gadgets.extend([None] * (gadget_capacity - len(ps.gadgets)))
        idx = first_empty_or_first(ps.gadgets, gadget_capacity)
        old = ps.gadgets[idx] if idx < len(ps.gadgets) else None
        if idx >= len(ps.gadgets):
            ps.gadgets.append(wid)
        else:
            ps.gadgets[idx] = wid
        return idx, old


# 兼容旧测试/引用
MapInstance = Lobby
