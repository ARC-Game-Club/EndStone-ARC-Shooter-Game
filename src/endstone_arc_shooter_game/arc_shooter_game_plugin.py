# -*- coding: utf-8 -*-
import json
import math
import time
import traceback
from typing import Any, Dict, List, Optional, Tuple

from endstone import Player
from endstone.command import Command, CommandSender
from endstone.event import (
    ActorDamageEvent,
    event_handler,
    PlayerDeathEvent,
    PlayerDropItemEvent,
    PlayerJoinEvent,
    PlayerQuitEvent,
    PlayerRespawnEvent,
)
from endstone.form import ActionForm, Dropdown, ModalForm, TextInput
from endstone.plugin import Plugin

from endstone_arc_shooter_game.config import (
    IMPLEMENTED_MODES,
    KNOWN_MODES,
    ConfigStore,
    build_runtime_map_cfg,
    get_mode_config,
    has_region,
    mode_playable,
    playable_modes,
    point_in_region,
    slot_range,
)
from endstone_arc_shooter_game.inventory import (
    delete_snapshot_disk,
    give_to_end_slots,
    load_snapshot_disk,
    remove_item_count,
    restore_inventory,
    save_snapshot_disk,
    set_slot_item,
    snapshot_player,
)
from endstone_arc_shooter_game.language import LanguageManager
from endstone_arc_shooter_game.session import (
    STATE_BUYING,
    STATE_LOBBY,
    STATE_PLAYING,
    TEAM_A,
    TEAM_B,
    Lobby,
    pick_spawn,
)

_GAMEMODE_CMD = {
    "0": "0",
    "survival": "0",
    "s": "0",
    "gamemode_survival": "0",
    "1": "1",
    "creative": "1",
    "c": "1",
    "gamemode_creative": "1",
    "2": "2",
    "adventure": "2",
    "a": "2",
    "gamemode_adventure": "2",
    "3": "3",
    "spectator": "3",
    "sp": "3",
    "gamemode_spectator": "3",
}

_VANILLA_CMD_DIM = {
    "minecraft:overworld": "overworld",
    "overworld": "overworld",
    "minecraft:nether": "nether",
    "nether": "nether",
    "the_nether": "nether",
    "minecraft:the_end": "the_end",
    "the_end": "the_end",
}


def format_player_name(raw: str) -> str:
    name = str(raw or "")
    if " " in name:
        return f'"{name}"'
    return name


def dimension_id_of(location: Any) -> str:
    dim = getattr(location, "dimension", None) if location is not None else None
    if dim is None:
        return "overworld"
    for attr in ("id", "name"):
        val = getattr(dim, attr, None)
        if val:
            return str(val).strip()
    return str(dim).strip() or "overworld"


def dimension_for_command(dimension: str) -> str:
    raw = str(dimension or "overworld").strip()
    return _VANILLA_CMD_DIM.get(raw, _VANILLA_CMD_DIM.get(raw.lower(), raw))


def _actor_player_name(actor: Any) -> Optional[str]:
    if actor is None:
        return None
    name = getattr(actor, "name", None)
    if not name:
        return None
    if getattr(actor, "xuid", None) is not None:
        return str(name)
    type_id = str(getattr(actor, "type", "") or "").lower()
    if "player" in type_id:
        return str(name)
    return None


def _player_location_tuple(player: Player) -> Tuple[float, float, float, float, float, str]:
    loc = player.location
    return (
        float(loc.x),
        float(loc.y),
        float(loc.z),
        float(getattr(loc, "yaw", 0) or 0),
        float(getattr(loc, "pitch", 0) or 0),
        dimension_id_of(loc),
    )


def _parse_modal_form(json_str: Any) -> list:
    if isinstance(json_str, list):
        return json_str
    try:
        data = json.loads(json_str or "[]")
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, TypeError):
        return []


class ARCShooterGamePlugin(Plugin):
    prefix = "ARCShooterGame"
    api_version = "0.10"
    load = "POSTWORLD"

    commands = {
        "gs": {
            "description": "射击游戏菜单、商店与离开",
            "usages": ["/gs", "/gs buy", "/gs leave", "/gs reload"],
            "permissions": ["arc_shooter_game.command.gs"],
        }
    }

    permissions = {
        "arc_shooter_game.command.gs": {
            "description": "允许使用 /gs",
            "default": True,
        }
    }

    def __init__(self):
        super().__init__()
        self.config_store: Optional[ConfigStore] = None
        self.language_manager: Optional[LanguageManager] = None
        self.lobbies: Dict[str, Lobby] = {}
        self.player_to_lobby: Dict[str, str] = {}
        self.backups: Dict[str, Dict[str, Any]] = {}
        self._last_attacker: Dict[str, Tuple[str, float]] = {}
        self._pending_restore: set[str] = set()
        self._tick_task = None

    def _safe_log(self, level: str, message: str) -> None:
        if hasattr(self, "logger") and self.logger is not None:
            fn = getattr(self.logger, level.lower(), None)
            if callable(fn):
                fn(message)
                return
            self.logger.info(message)
        else:
            print(f"[{level.upper()}] {message}")

    def _t(self, key: str) -> str:
        if self.language_manager is None:
            return key
        return self.language_manager.GetText(key)

    def on_load(self) -> None:
        self.config_store = ConfigStore(logger=getattr(self, "logger", None))
        lang = self.config_store.settings.GetSetting("DEFAULT_LANGUAGE_CODE") or "ZH-CN"
        self.language_manager = LanguageManager(lang)
        self._safe_log("info", "[ARCShooterGame] on_load")

    def on_enable(self) -> None:
        self.register_events(self)
        try:
            self._tick_task = self.server.scheduler.run_task(self, self._on_tick, delay=20, period=20)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] Failed to register tick: {e}")
        self._safe_log("info", "[ARCShooterGame] enabled")

    def on_disable(self) -> None:
        try:
            self.server.scheduler.cancel_tasks(self)
        except Exception:
            pass
        for lobby in list(self.lobbies.values()):
            if lobby.state in (STATE_BUYING, STATE_PLAYING):
                self._end_match(lobby, winner=None)
            else:
                for ps in list(lobby.online_players()):
                    self.player_to_lobby.pop(ps.name, None)
                self.lobbies.pop(lobby.lobby_id, None)
        self._safe_log("info", "[ARCShooterGame] disabled")

    def _lobby_of(self, player_name: str) -> Optional[Lobby]:
        lobby_id = self.player_to_lobby.get(player_name)
        if not lobby_id:
            return None
        return self.lobbies.get(lobby_id)

    def _map_in_use(self, map_id: str, exclude_lobby_id: Optional[str] = None) -> bool:
        for lobby in self.lobbies.values():
            if exclude_lobby_id and lobby.lobby_id == exclude_lobby_id:
                continue
            if lobby.map_id == map_id:
                return True
        return False

    def _get_player(self, name: str) -> Optional[Player]:
        getter = getattr(self.server, "get_player", None)
        if callable(getter):
            try:
                player = getter(name)
                if player is not None:
                    return player
            except Exception:
                pass
        for player in self.server.online_players:
            if player.name == name:
                return player
        return None

    def _is_op(self, sender: CommandSender) -> bool:
        if not isinstance(sender, Player):
            return True
        return bool(getattr(sender, "is_op", False))

    # ---------- commands ----------

    def on_command(self, sender: CommandSender, command: Command, args: list[str]) -> bool:
        if command.name != "gs":
            return False
        sub = args[0].lower() if args else ""
        if sub == "reload":
            if not self._is_op(sender):
                sender.send_message(self._t("CMD_NO_PERMISSION"))
                return True
            try:
                assert self.config_store is not None
                self.config_store.reload()
                lang = self.config_store.settings.GetSetting("DEFAULT_LANGUAGE_CODE") or "ZH-CN"
                self.language_manager = LanguageManager(lang)
                sender.send_message(self._t("RELOAD_OK"))
            except Exception as e:
                sender.send_message(self._t("RELOAD_FAIL").format(e))
            return True
        if not isinstance(sender, Player):
            sender.send_message(self._t("CMD_PLAYER_ONLY"))
            return True
        if sub == "buy":
            self._show_shop(sender)
            return True
        if sub == "leave":
            self._handle_leave(sender, confirm_match=True)
            return True
        self._show_root_menu(sender)
        return True

    # ---------- events ----------

    @event_handler
    def on_player_join(self, event: PlayerJoinEvent):
        player = event.player
        if self._lobby_of(player.name) is not None:
            return
        snap = self.backups.get(player.name) or load_snapshot_disk(player.name)
        if snap:
            self.backups[player.name] = snap
            self._restore_player(player)
            player.send_message(self._t("BACKUP_RECOVERED"))

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent):
        player = event.player
        lobby = self._lobby_of(player.name)
        if lobby is not None:
            if lobby.state == STATE_LOBBY:
                self._leave_lobby(player, lobby)
            elif lobby.state in (STATE_BUYING, STATE_PLAYING):
                self._leave_match(player, lobby)
        if player.name in self._pending_restore:
            self._restore_player(player, force=True)

    @event_handler
    def on_actor_damage(self, event: ActorDamageEvent):
        victim = getattr(event, "actor", None)
        victim_name = _actor_player_name(victim)
        if not victim_name:
            return
        lobby = self._lobby_of(victim_name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            return
        killer_name = self._killer_name_from_source(getattr(event, "damage_source", None))
        if killer_name and killer_name != victim_name and self._lobby_of(killer_name) is lobby:
            self._last_attacker[victim_name] = (killer_name, time.time())

    @event_handler
    def on_player_death(self, event: PlayerDeathEvent):
        victim = getattr(event, "player", None) or getattr(event, "actor", None)
        if victim is None:
            return
        victim_name = getattr(victim, "name", None)
        if not victim_name:
            return
        lobby = self._lobby_of(victim_name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            return
        if hasattr(event, "keep_inventory"):
            event.keep_inventory = True
        drops = getattr(event, "drops", None)
        if drops is not None:
            try:
                event.drops = []
            except Exception:
                try:
                    drops.clear()
                except Exception:
                    pass
        killer_name = self._killer_name_from_source(getattr(event, "damage_source", None))
        if not killer_name:
            last = self._last_attacker.get(victim_name)
            if last and time.time() - last[1] <= 12:
                killer_name = last[0]
        if killer_name == victim_name:
            killer_name = None
        ps = lobby.players.get(victim_name)
        if killer_name and self._lobby_of(killer_name) is lobby:
            result = lobby.apply_player_kill(killer_name, victim_name, self.config_store.kill_reward())
            if result:
                killer = self._get_player(killer_name)
                if killer:
                    if result["friendly"]:
                        killer.send_message(self._t("KILL_TEAM").format(victim_name))
                    else:
                        killer.send_message(
                            self._t("KILL_ENEMY").format(victim_name, result["reward"], result["killer_points"])
                        )
                victim_player = self._get_player(victim_name)
                if victim_player:
                    victim_player.send_message(self._t("PLAYER_KILLED").format(killer_name))
                self._broadcast(
                    lobby,
                    self._t("SCORE_UPDATE").format(
                        lobby.team_name(TEAM_A), lobby.score_a, lobby.score_b, lobby.team_name(TEAM_B)
                    ),
                )
                if result["winner"]:
                    self._end_match(lobby, result["winner"])
                    return
        elif ps is not None:
            ps.deaths += 1

    @event_handler
    def on_player_respawn(self, event: PlayerRespawnEvent):
        player = event.player
        if player.name in self._pending_restore:
            try:
                self.server.scheduler.run_task(
                    self, lambda p=player: self._restore_player(p, force=True), delay=1
                )
            except Exception:
                self._restore_player(player, force=True)
            return
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            return
        try:
            self.server.scheduler.run_task(self, lambda p=player, lb=lobby: self._tp_to_team_spawn(p, lb), delay=1)
        except Exception:
            self._tp_to_team_spawn(player, lobby)

    @event_handler
    def on_player_drop_item(self, event: PlayerDropItemEvent):
        player = getattr(event, "player", None)
        if player is None:
            return
        lobby = self._lobby_of(player.name)
        if lobby is not None and lobby.state in (STATE_BUYING, STATE_PLAYING):
            event.is_cancelled = True

    # ---------- tick ----------

    def _on_tick(self) -> None:
        try:
            now = time.time()
            timeout = self.config_store.lobby_timeout() if self.config_store else 900
            for lobby in list(self.lobbies.values()):
                if lobby.state == STATE_LOBBY and lobby.lobby_timed_out(timeout, now):
                    self._dissolve_lobby(lobby, timeout=True)
                    continue
                if lobby.state == STATE_BUYING and lobby.buy_remaining(now) <= 0:
                    lobby.begin_playing()
                    self._broadcast(lobby, self._t("GAME_STARTED").format(lobby.target_score))
                if lobby.state in (STATE_BUYING, STATE_PLAYING):
                    self._send_score_tips(lobby, now)
                    self._enforce_region(lobby)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] tick error: {e}\n{traceback.format_exc()}")

    def _enforce_region(self, lobby: Lobby) -> None:
        if lobby.map_cfg is None:
            return
        dim = str(lobby.map_cfg.get("dimension") or "overworld")
        for ps in lobby.online_players():
            player = self._get_player(ps.name)
            if player is None:
                continue
            loc = player.location
            if dimension_id_of(loc) != dim:
                self._tp_to_team_spawn(player, lobby)
                player.send_message(self._t("REGION_PULLBACK"))
                continue
            if not point_in_region(lobby.map_cfg, float(loc.x), float(loc.y), float(loc.z)):
                self._tp_to_team_spawn(player, lobby)
                player.send_message(self._t("REGION_PULLBACK"))

    def _send_score_tips(self, lobby: Lobby, now: float) -> None:
        a_name = lobby.team_name(TEAM_A)
        b_name = lobby.team_name(TEAM_B)
        remain = int(math.ceil(lobby.buy_remaining(now))) if lobby.state == STATE_BUYING else 0
        for ps in lobby.online_players():
            player = self._get_player(ps.name)
            if player is None:
                continue
            if lobby.state == STATE_BUYING:
                msg = self._t("BUY_TIME_TIP").format(remain, a_name, lobby.score_a, lobby.score_b, b_name, ps.points)
            else:
                msg = self._t("PLAYING_TIP").format(a_name, lobby.score_a, lobby.score_b, b_name, ps.points)
            if hasattr(player, "send_tip"):
                try:
                    player.send_tip(msg)
                    continue
                except Exception:
                    pass
            if hasattr(player, "send_popup"):
                try:
                    player.send_popup(msg)
                except Exception:
                    pass

    # ---------- lobby flow ----------

    def _create_lobby(self, player: Player) -> None:
        if self._lobby_of(player.name) is not None:
            player.send_message(self._t("JOIN_FAIL_IN_GAME"))
            return
        lobby = Lobby(admin=player.name)
        self.lobbies[lobby.lobby_id] = lobby
        ok, reason = lobby.join(player.name, self.config_store.starting_points() if self.config_store else 1000)
        if not ok:
            self.lobbies.pop(lobby.lobby_id, None)
            player.send_message(self._t("JOIN_FAIL_FULL"))
            return
        self.player_to_lobby[player.name] = lobby.lobby_id
        player.send_message(self._t("JOIN_OK_ADMIN"))
        self._show_lobby_menu(player, lobby)

    def _join_lobby(self, player: Player, lobby_id: str) -> None:
        if self._lobby_of(player.name) is not None:
            player.send_message(self._t("JOIN_FAIL_IN_GAME"))
            return
        lobby = self.lobbies.get(lobby_id)
        if lobby is None:
            player.send_message(self._t("JOIN_FAIL_UNKNOWN"))
            return
        ok, reason = lobby.join(player.name, self.config_store.starting_points() if self.config_store else 1000)
        if not ok:
            player.send_message(self._t("JOIN_FAIL_FULL"))
            return
        self.player_to_lobby[player.name] = lobby.lobby_id
        if lobby.state in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("JOIN_OK_MATCH"))
            self._prepare_fighter(player, lobby)
            self._show_match_menu(player, lobby)
            return
        player.send_message(self._t("JOIN_OK").format(lobby.admin or "-"))
        self._show_lobby_menu(player, lobby)

    def _leave_lobby(self, player: Player, lobby: Lobby) -> None:
        new_admin = lobby.leave(player.name)
        self.player_to_lobby.pop(player.name, None)
        player.send_message(self._t("LEAVE_OK"))
        if lobby.player_count() == 0:
            self.lobbies.pop(lobby.lobby_id, None)
            return
        if new_admin:
            admin_player = self._get_player(new_admin)
            if admin_player:
                admin_player.send_message(self._t("ADMIN_TRANSFERRED"))

    def _handle_leave(self, player: Player, confirm_match: bool) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is None:
            player.send_message(self._t("LEAVE_NOT_IN"))
            return
        if lobby.state == STATE_LOBBY:
            self._leave_lobby(player, lobby)
            return
        if lobby.state in (STATE_BUYING, STATE_PLAYING):
            if confirm_match:
                self._show_leave_match_confirm(player)
                return
            self._leave_match(player, lobby)

    def _leave_match(self, player: Player, lobby: Lobby) -> None:
        lobby.leave(player.name)
        self.player_to_lobby.pop(player.name, None)
        self._restore_player(player, after_match=True)
        player.send_message(self._t("LEAVE_OK"))
        if lobby.state not in (STATE_BUYING, STATE_PLAYING):
            return
        if lobby.player_count() == 0:
            self._end_match(lobby, winner=None)
            return
        winner = lobby.remaining_winner()
        if winner is not None:
            self._end_match(lobby, winner)

    def _dissolve_lobby(self, lobby: Lobby, timeout: bool) -> None:
        names = [p.name for p in lobby.online_players()]
        key = "LOBBY_DISSOLVED_TIMEOUT" if timeout else "LOBBY_DISSOLVED_EMPTY"
        msg = self._t(key)
        for name in names:
            self.player_to_lobby.pop(name, None)
            player = self._get_player(name)
            if player:
                player.send_message(msg)
        self.lobbies.pop(lobby.lobby_id, None)

    def _start_match(self, player: Player, lobby: Lobby) -> None:
        if lobby.admin != player.name:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        ok, reason = lobby.can_start()
        if not ok:
            if reason == "need_map":
                player.send_message(self._t("START_NEED_MAP"))
            elif reason == "need_spawns":
                player.send_message(self._t("START_NEED_SPAWNS"))
            else:
                player.send_message(self._t("START_NEED_PLAYERS"))
            return
        buy_seconds = self.config_store.buy_time() if self.config_store else 10
        starting = self.config_store.starting_points() if self.config_store else 1000
        for ps in lobby.online_players():
            ps.points = starting
            ps.kills = 0
            ps.deaths = 0
            ps.primary_id = None
            ps.secondary_id = None
            ps.gadgets = []
        lobby.begin_buy(buy_seconds)
        if buy_seconds <= 0:
            lobby.begin_playing()
        self._broadcast(lobby, self._t("START_BROADCAST").format(buy_seconds))
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is None:
                continue
            self._prepare_fighter(member, lobby)
        if lobby.state == STATE_PLAYING:
            self._broadcast(lobby, self._t("GAME_STARTED").format(lobby.target_score))

    def _prepare_fighter(self, player: Player, lobby: Lobby) -> None:
        snap = snapshot_player(player, dimension_id_of(player.location))
        self.backups[player.name] = snap
        try:
            save_snapshot_disk(player.name, snap)
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] backup disk fail for {player.name}: {e}")
        self._clear_player(player.name)
        self._set_gamemode(player.name, "0")
        try:
            if hasattr(player, "health"):
                player.health = getattr(player, "max_health", 20) or 20
        except Exception:
            pass
        self._tp_to_team_spawn(player, lobby)

    def _tp_to_team_spawn(self, player: Player, lobby: Lobby) -> None:
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        spawns = lobby.team_spawns(ps.team)
        if not spawns:
            return
        pos = pick_spawn(spawns)
        self._tp_player(
            player.name,
            pos["x"],
            pos["y"],
            pos["z"],
            lobby.map_cfg.get("dimension") if lobby.map_cfg else "overworld",
            pos.get("yaw"),
            pos.get("pitch"),
        )

    def _end_match(self, lobby: Lobby, winner: Optional[str]) -> None:
        lines = self._result_lines(lobby, winner)
        still = [ps.name for ps in lobby.online_players()]
        participants = {ps.name for ps in lobby.result_rows()}
        for name in still:
            member = self._get_player(name)
            self.player_to_lobby.pop(name, None)
            if member:
                self._restore_player(member, after_match=True)
        for name in participants:
            member = self._get_player(name)
            if member is None:
                continue
            for line in lines:
                member.send_message(line)
        self.lobbies.pop(lobby.lobby_id, None)

    def _result_lines(self, lobby: Lobby, winner: Optional[str]) -> list[str]:
        lines = [self._t("MATCH_END_HEADER")]
        if winner:
            lines.append(self._t("MATCH_END_WINNER").format(lobby.team_name(winner)))
        else:
            lines.append(self._t("MATCH_END_DRAW"))
        rows = lobby.result_rows()
        for team_id in (TEAM_A, TEAM_B):
            lines.append(self._t("MATCH_END_STATS_TEAM").format(lobby.team_name(team_id)))
            members = [p for p in rows if p.team == team_id]
            if not members:
                lines.append(self._t("NO_PLAYER"))
            for ps in members:
                lines.append(self._t("MATCH_END_STATS_PLAYER").format(ps.name, ps.kills, ps.deaths))
        lines.append(self._t("MATCH_END_FOOTER"))
        return lines

    def _is_probably_dead(self, player: Player) -> bool:
        if bool(getattr(player, "is_dead", False)):
            return True
        health = getattr(player, "health", None)
        try:
            if health is not None and float(health) <= 0:
                return True
        except (TypeError, ValueError):
            pass
        return False

    def _restore_player(self, player: Player, force: bool = False, after_match: bool = False) -> None:
        if not force and self._is_probably_dead(player):
            self._pending_restore.add(player.name)
            return
        self._pending_restore.discard(player.name)
        snap = self.backups.pop(player.name, None) or load_snapshot_disk(player.name)
        if snap is None:
            return
        if after_match:
            self._clear_player(player.name)
        else:
            try:
                restore_inventory(player, snap)
            except Exception as e:
                self._safe_log("error", f"[ARCShooterGame] restore inventory {player.name}: {e}")
        loc = snap.get("location") or {}
        self._tp_player(
            player.name,
            float(loc.get("x") or 0),
            float(loc.get("y") or 64),
            float(loc.get("z") or 0),
            str(loc.get("dimension") or "overworld"),
            loc.get("yaw"),
            loc.get("pitch"),
        )
        gm = str(snap.get("game_mode") or "survival")
        self._set_gamemode(player.name, gm)
        delete_snapshot_disk(player.name)
        player.send_message(self._t("RESTORED"))

    def _tp_player(
        self,
        player_name: str,
        x: float,
        y: float,
        z: float,
        dimension: str,
        yaw: Any = None,
        pitch: Any = None,
    ) -> None:
        dim = dimension_for_command(dimension)
        name = format_player_name(player_name)
        if yaw is not None:
            cmd = (
                f"execute in {dim} run tp {name} {float(x):.2f} {float(y):.2f} {float(z):.2f} "
                f"{float(yaw)} {float(pitch or 0)}"
            )
        else:
            cmd = f"execute in {dim} run tp {name} {float(x):.2f} {float(y):.2f} {float(z):.2f}"
        self.server.dispatch_command(self.server.command_sender, cmd)

    def _clear_player(self, player_name: str) -> None:
        self.server.dispatch_command(
            self.server.command_sender,
            f"clear {format_player_name(player_name)}",
        )

    def _set_gamemode(self, player_name: str, mode: str) -> None:
        raw = str(mode or "0").strip().lower().split(".")[-1].replace("gamemode_", "")
        cmd_mode = _GAMEMODE_CMD.get(raw, "0")
        self.server.dispatch_command(
            self.server.command_sender,
            f"gamemode {cmd_mode} {format_player_name(player_name)}",
        )

    def _broadcast(self, lobby: Lobby, message: str) -> None:
        for ps in lobby.online_players():
            player = self._get_player(ps.name)
            if player:
                player.send_message(message)

    def _killer_name_from_source(self, source: Any) -> Optional[str]:
        if source is None:
            return None
        for attr in ("actor", "damaging_actor", "damaging_entity", "entity", "attacker"):
            name = _actor_player_name(getattr(source, attr, None))
            if name:
                return name
        return None

    def _mode_label(self, mode: str) -> str:
        text = self._t(f"MODE_{mode}")
        return text if text and text != f"MODE_{mode}" else mode

    def _lobby_status_label(self, lobby: Lobby) -> str:
        if lobby.state == STATE_LOBBY:
            return self._t("LOBBY_STATUS_WAITING")
        if lobby.state == STATE_BUYING:
            return self._t("LOBBY_STATUS_BUYING")
        return self._t("LOBBY_STATUS_PLAYING")

    def _lobby_remaining_text(self, lobby: Lobby) -> str:
        timeout = self.config_store.lobby_timeout() if self.config_store else 900
        remain = max(0, int(timeout - (time.time() - lobby.lobby_started_at)))
        minutes, seconds = divmod(remain, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _team_block(self, lobby: Lobby, team_id: str) -> str:
        names = [p.name for p in lobby.online_players() if p.team == team_id]
        body = "、".join(names) if names else self._t("NO_PLAYER")
        return self._t("TEAM_LINE").format(
            lobby.team_name(team_id),
            lobby.team_count(team_id),
            lobby.max_per_team,
            body,
        )

    def _lobby_map_label(self, lobby: Lobby) -> str:
        if lobby.map_cfg:
            return str(lobby.map_cfg.get("display_name") or lobby.map_id)
        return self._t("LOBBY_LIST_NO_MAP")

    def _lobby_mode_label(self, lobby: Lobby) -> str:
        if lobby.mode:
            return self._mode_label(lobby.mode)
        return self._t("LOBBY_LIST_NO_MODE")

    # ---------- shop ----------

    def _buy_weapon(self, player: Player, weapon_id: str) -> None:
        assert self.config_store is not None
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        weapon = self.config_store.weapons.get(weapon_id)
        if weapon is None:
            player.send_message(self._t("BUY_FAIL_UNKNOWN"))
            return
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        cost = int(weapon["cost"])
        if ps.points < cost:
            player.send_message(self._t("BUY_FAIL_POINTS").format(cost, ps.points))
            self._show_shop_category(player, weapon["type"])
            return
        layout = self.config_store.layout()
        start, end = slot_range(layout, weapon["type"])
        capacity = end - start
        if capacity <= 0:
            player.send_message(self._t("SHOP_NO_SLOT"))
            return
        idx, old_id = lobby.record_purchase(player.name, weapon, capacity)
        ps.points -= cost
        if old_id and old_id in self.config_store.weapons:
            old = self.config_store.weapons[old_id]
            for extra_id, extra_count in (old.get("extras") or {}).items():
                remove_item_count(player, extra_id, extra_count)
        slot = start + idx
        set_slot_item(player, slot, weapon["item"], int(weapon.get("amount") or 1), int(weapon.get("data") or 0))
        reserved = int(layout["reserved"])
        for extra_id, extra_count in (weapon.get("extras") or {}).items():
            give_to_end_slots(player, extra_id, extra_count, reserved, 0)
        player.send_message(self._t("BUY_OK").format(weapon["display_name"], ps.points))
        self._show_shop_category(player, weapon["type"])

    # ---------- ui ----------

    def _show_root_menu(self, player: Player) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is not None:
            if lobby.state == STATE_LOBBY:
                self._show_lobby_menu(player, lobby)
            else:
                self._show_match_menu(player, lobby)
            return
        try:
            form = ActionForm(title=self._t("MENU_TITLE"), content=self._t("MENU_CONTENT"))
            form.add_button(self._t("BTN_LOBBY_LIST"), on_click=lambda sender: self._show_lobby_list(sender))
            if self._is_op(player):
                form.add_button(self._t("BTN_CONFIG_MAPS"), on_click=lambda sender: self._show_config_maps(sender))
            form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] root menu: {e}\n{traceback.format_exc()}")
            player.send_message(self._t("PANEL_ERROR"))

    def _show_lobby_list(self, player: Player) -> None:
        try:
            lobbies = list(self.lobbies.values())
            content = self._t("LOBBY_LIST_CONTENT") if lobbies else self._t("LOBBY_LIST_EMPTY")
            form = ActionForm(title=self._t("LOBBY_LIST_TITLE"), content=content)
            for lobby in lobbies:
                label = self._t("LOBBY_LIST_BUTTON").format(
                    lobby.admin or "-",
                    self._lobby_map_label(lobby),
                    self._lobby_mode_label(lobby),
                    lobby.player_count(),
                    self._lobby_status_label(lobby),
                )
                lid = lobby.lobby_id
                form.add_button(label, on_click=lambda sender, i=lid: self._join_lobby(sender, i))
            form.add_button(self._t("BTN_CREATE_LOBBY"), on_click=lambda sender: self._create_lobby(sender))
            form.add_button(self._t("BACK"), on_click=lambda sender: self._show_root_menu(sender))
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] lobby list: {e}\n{traceback.format_exc()}")
            player.send_message(self._t("PANEL_ERROR"))

    def _show_lobby_menu(self, player: Player, lobby: Lobby) -> None:
        try:
            content = self._t("LOBBY_CONTENT").format(
                self._lobby_map_label(lobby),
                self._lobby_mode_label(lobby),
                lobby.admin or "-",
                self._lobby_remaining_text(lobby),
                lobby.target_score if lobby.map_cfg else "-",
                lobby.max_per_team if lobby.map_cfg else "-",
                self._team_block(lobby, TEAM_A),
                self._team_block(lobby, TEAM_B),
            )
            form = ActionForm(title=self._t("LOBBY_TITLE"), content=content)
            is_admin = lobby.admin == player.name
            if is_admin:
                form.add_button(self._t("BTN_SELECT_MAP"), on_click=lambda sender, lb=lobby: self._show_map_select(sender, lb))
                form.add_button(self._t("BTN_SELECT_MODE"), on_click=lambda sender, lb=lobby: self._show_mode_select(sender, lb))
                form.add_button(self._t("BTN_START"), on_click=lambda sender, lb=lobby: self._start_match(sender, lb))
                form.add_button(self._t("BTN_ASSIGN"), on_click=lambda sender, lb=lobby: self._show_assign_menu(sender, lb))
                form.add_button(self._t("BTN_KICK"), on_click=lambda sender, lb=lobby: self._show_kick_menu(sender, lb))
            form.add_button(self._t("BTN_LEAVE"), on_click=lambda sender: self._handle_leave(sender, confirm_match=False))
            form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] lobby menu: {e}\n{traceback.format_exc()}")
            player.send_message(self._t("PANEL_ERROR"))

    def _show_map_select(self, player: Player, lobby: Lobby) -> None:
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        assert self.config_store is not None
        candidates: List[Dict[str, Any]] = []
        for map_cfg in self.config_store.maps.values():
            if not has_region(map_cfg):
                continue
            if not playable_modes(map_cfg):
                continue
            if self._map_in_use(map_cfg["id"], exclude_lobby_id=lobby.lobby_id):
                continue
            candidates.append(map_cfg)
        if not candidates:
            form = ActionForm(title=self._t("MAP_SELECT_TITLE"), content=self._t("MAP_SELECT_EMPTY"))
            form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
            player.send_form(form)
            return
        form = ActionForm(title=self._t("MAP_SELECT_TITLE"), content=self._t("MAP_SELECT_CONTENT"))
        for map_cfg in candidates:
            label = self._t("MAP_SELECT_BUTTON").format(map_cfg.get("display_name") or map_cfg["id"])
            mid = map_cfg["id"]
            form.add_button(label, on_click=lambda sender, lb=lobby, m=mid: self._select_map(sender, lb, m))
        form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
        player.send_form(form)

    def _select_map(self, player: Player, lobby: Lobby, map_id: str) -> None:
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None or not has_region(map_cfg) or not playable_modes(map_cfg):
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_map_select(player, lobby)
            return
        if self._map_in_use(map_id, exclude_lobby_id=lobby.lobby_id):
            player.send_message(self._t("MAP_SELECT_BUSY"))
            self._show_map_select(player, lobby)
            return
        lobby.map_id = map_id
        lobby.mode = None
        lobby.map_cfg = None
        player.send_message(self._t("MAP_SELECT_OK").format(map_cfg.get("display_name") or map_id))
        self._show_mode_select(player, lobby)

    def _show_mode_select(self, player: Player, lobby: Lobby) -> None:
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        assert self.config_store is not None
        if not lobby.map_id:
            player.send_message(self._t("START_NEED_MAP"))
            self._show_lobby_menu(player, lobby)
            return
        map_cfg = self.config_store.maps.get(lobby.map_id)
        if map_cfg is None:
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_lobby_menu(player, lobby)
            return
        modes = playable_modes(map_cfg)
        if not modes:
            form = ActionForm(title=self._t("MODE_SELECT_TITLE"), content=self._t("MODE_SELECT_EMPTY"))
            form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
            player.send_form(form)
            return
        form = ActionForm(
            title=self._t("MODE_SELECT_TITLE"),
            content=self._t("MODE_SELECT_CONTENT").format(map_cfg.get("display_name") or map_cfg["id"]),
        )
        for mode in modes:
            label = self._t("MODE_SELECT_BUTTON").format(self._mode_label(mode))
            form.add_button(label, on_click=lambda sender, lb=lobby, m=mode: self._select_mode(sender, lb, m))
        form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
        player.send_form(form)

    def _select_mode(self, player: Player, lobby: Lobby, mode: str) -> None:
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(lobby.map_id or "")
        if map_cfg is None:
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_lobby_menu(player, lobby)
            return
        ok, reason = lobby.set_map_and_mode(map_cfg, mode)
        if not ok:
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_mode_select(player, lobby)
            return
        player.send_message(self._t("MODE_SELECT_OK").format(self._mode_label(mode)))
        self._show_lobby_menu(player, lobby)

    def _show_assign_menu(self, player: Player, lobby: Lobby) -> None:
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        form = ActionForm(title=self._t("ASSIGN_TITLE"), content=self._t("ASSIGN_CONTENT"))
        for ps in lobby.online_players():
            label = self._t("ASSIGN_BUTTON").format(ps.name, lobby.team_name(ps.team))
            form.add_button(
                label,
                on_click=lambda sender, n=ps.name, lb=lobby: self._toggle_team(sender, lb, n),
            )
        form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
        player.send_form(form)

    def _toggle_team(self, player: Player, lobby: Lobby, target_name: str) -> None:
        ps = lobby.players.get(target_name)
        if ps is None:
            self._show_assign_menu(player, lobby)
            return
        other = TEAM_B if ps.team == TEAM_A else TEAM_A
        ok, reason = lobby.set_team(target_name, other)
        if not ok and reason == "full":
            player.send_message(self._t("ASSIGN_TEAM_FULL"))
        elif ok:
            player.send_message(self._t("ASSIGN_DONE").format(target_name, lobby.team_name(other)))
        self._show_assign_menu(player, lobby)

    def _show_kick_menu(self, player: Player, lobby: Lobby) -> None:
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        form = ActionForm(title=self._t("KICK_TITLE"), content=self._t("KICK_CONTENT"))
        for ps in lobby.online_players():
            form.add_button(ps.name, on_click=lambda sender, n=ps.name, lb=lobby: self._kick_player(sender, lb, n))
        form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
        player.send_form(form)

    def _kick_player(self, admin: Player, lobby: Lobby, target_name: str) -> None:
        if target_name == admin.name:
            admin.send_message(self._t("KICK_SELF"))
            self._show_kick_menu(admin, lobby)
            return
        if not lobby.kick(target_name):
            self._show_kick_menu(admin, lobby)
            return
        self.player_to_lobby.pop(target_name, None)
        target = self._get_player(target_name)
        if target:
            target.send_message(self._t("KICKED"))
        admin.send_message(self._t("KICK_OK").format(target_name))
        self._show_kick_menu(admin, lobby)

    def _show_match_menu(self, player: Player, lobby: Lobby) -> None:
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        content = self._t("MATCH_CONTENT").format(
            lobby.team_name(TEAM_A),
            lobby.score_a,
            lobby.team_name(TEAM_B),
            lobby.score_b,
            lobby.team_name(ps.team),
            ps.points,
            ps.kills,
            ps.deaths,
        )
        form = ActionForm(title=self._t("MATCH_TITLE").format(lobby.display_name), content=content)
        form.add_button(self._t("BTN_SHOP"), on_click=lambda sender: self._show_shop(sender))
        form.add_button(self._t("BTN_LEAVE_MATCH"), on_click=lambda sender: self._show_leave_match_confirm(sender))
        form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
        player.send_form(form)

    def _show_leave_match_confirm(self, player: Player) -> None:
        form = ActionForm(
            title=self._t("LEAVE_MATCH_CONFIRM_TITLE"),
            content=self._t("LEAVE_MATCH_CONFIRM"),
        )
        form.add_button(
            self._t("BTN_CONFIRM"),
            on_click=lambda sender: self._handle_leave(sender, confirm_match=False),
        )
        form.add_button(self._t("BTN_CANCEL"), on_click=lambda sender: None)
        player.send_form(form)

    def _show_shop(self, player: Player) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        layout = self.config_store.layout() if self.config_store else {}
        p0, p1 = slot_range(layout, "primary")
        s0, s1 = slot_range(layout, "secondary")
        g0, g1 = slot_range(layout, "gadget")
        form = ActionForm(
            title=self._t("SHOP_TITLE"),
            content=self._t("SHOP_CONTENT").format(ps.points, p1 - p0, s1 - s0, g1 - g0),
        )
        form.add_button(self._t("SHOP_PRIMARY"), on_click=lambda sender: self._show_shop_category(sender, "primary"))
        form.add_button(self._t("SHOP_SECONDARY"), on_click=lambda sender: self._show_shop_category(sender, "secondary"))
        form.add_button(self._t("SHOP_GADGET"), on_click=lambda sender: self._show_shop_category(sender, "gadget"))
        form.add_button(self._t("BACK"), on_click=lambda sender: self._show_root_menu(sender))
        player.send_form(form)

    def _show_shop_category(self, player: Player, weapon_type: str) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        ps = lobby.players.get(player.name)
        if ps is None or self.config_store is None:
            return
        title_map = {
            "primary": self._t("SHOP_PRIMARY"),
            "secondary": self._t("SHOP_SECONDARY"),
            "gadget": self._t("SHOP_GADGET"),
        }
        weapons = self.config_store.weapons_of_type(weapon_type)
        form = ActionForm(
            title=self._t("SHOP_CAT_TITLE").format(title_map.get(weapon_type, weapon_type)),
            content=self._t("SHOP_CAT_CONTENT").format(ps.points),
        )
        if not weapons:
            form = ActionForm(
                title=self._t("SHOP_CAT_TITLE").format(title_map.get(weapon_type, weapon_type)),
                content=self._t("SHOP_EMPTY"),
            )
            form.add_button(self._t("BACK"), on_click=lambda sender: self._show_shop(sender))
            player.send_form(form)
            return
        owned = set(filter(None, [ps.primary_id, ps.secondary_id, *ps.gadgets]))
        for weapon in weapons:
            owned_mark = self._t("SHOP_OWNED") if weapon["id"] in owned else ""
            label = self._t("SHOP_ITEM").format(weapon["display_name"], weapon["cost"], owned_mark)
            wid = weapon["id"]
            form.add_button(label, on_click=lambda sender, w=wid: self._buy_weapon(sender, w))
        form.add_button(self._t("BACK"), on_click=lambda sender: self._show_shop(sender))
        player.send_form(form)

    # ---------- map config ui ----------

    def _show_config_maps(self, player: Player) -> None:
        if not self._is_op(player):
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        assert self.config_store is not None
        maps = list(self.config_store.maps.values())
        content = self._t("CONFIG_MAPS_CONTENT") if maps else self._t("CONFIG_MAPS_EMPTY")
        form = ActionForm(title=self._t("CONFIG_MAPS_TITLE"), content=content)
        for map_cfg in maps:
            label = self._t("CONFIG_MAP_BUTTON").format(map_cfg.get("display_name") or map_cfg["id"])
            mid = map_cfg["id"]
            form.add_button(label, on_click=lambda sender, m=mid: self._show_map_edit(sender, m))
        form.add_button(self._t("BTN_CREATE_MAP"), on_click=lambda sender: self._show_create_map_form(sender))
        form.add_button(self._t("BACK"), on_click=lambda sender: self._show_root_menu(sender))
        player.send_form(form)

    def _show_create_map_form(self, player: Player) -> None:
        if not self._is_op(player):
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return

        def on_submit(p: Player, json_str: str) -> None:
            data = _parse_modal_form(json_str)
            name = str(data[0] or "").strip() if data else ""
            if not name:
                p.send_message(self._t("CREATE_MAP_FAIL").format("empty name"))
                self._show_config_maps(p)
                return
            assert self.config_store is not None
            x, y, z, yaw, pitch, dim = _player_location_tuple(p)
            entry = self.config_store.create_map(name, dim)
            self.config_store.update_map(
                entry["id"],
                lambda m: m.update({"dimension": dim}),
            )
            p.send_message(self._t("CREATE_MAP_OK").format(name))
            self._show_map_edit(p, entry["id"])

        form = ModalForm(
            title=self._t("CREATE_MAP_TITLE"),
            controls=[TextInput(label=self._t("CREATE_MAP_NAME"), placeholder="仓库")],
            on_submit=on_submit,
        )
        player.send_form(form)

    def _show_map_edit(self, player: Player, map_id: str) -> None:
        if not self._is_op(player):
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None:
            self._show_config_maps(player)
            return
        region_text = self._t("MAP_REGION_SET") if has_region(map_cfg) else self._t("MAP_REGION_NONE")
        mode_names = [self._mode_label(str(m.get("mode") or "")) for m in map_cfg.get("modes") or []]
        modes_text = "、".join(mode_names) if mode_names else self._t("MAP_MODES_NONE")
        content = self._t("MAP_EDIT_CONTENT").format(
            map_cfg.get("dimension") or "overworld",
            region_text,
            modes_text,
        )
        form = ActionForm(title=self._t("MAP_EDIT_TITLE").format(map_cfg.get("display_name") or map_id), content=content)
        form.add_button(self._t("BTN_SET_POS1"), on_click=lambda sender, m=map_id: self._set_map_pos(sender, m, 1))
        form.add_button(self._t("BTN_SET_POS2"), on_click=lambda sender, m=map_id: self._set_map_pos(sender, m, 2))
        form.add_button(self._t("BTN_ADD_MODE"), on_click=lambda sender, m=map_id: self._show_add_mode_form(sender, m))
        form.add_button(self._t("BTN_RENAME_MAP"), on_click=lambda sender, m=map_id: self._show_rename_map_form(sender, m))
        form.add_button(self._t("BTN_DELETE_MAP"), on_click=lambda sender, m=map_id: self._show_delete_map_confirm(sender, m))
        for mode_cfg in map_cfg.get("modes") or []:
            mode = str(mode_cfg.get("mode") or "")
            label = self._mode_label(mode)
            form.add_button(label, on_click=lambda sender, mid=map_id, md=mode: self._show_mode_edit(sender, mid, md))
        form.add_button(self._t("BACK"), on_click=lambda sender: self._show_config_maps(sender))
        player.send_form(form)

    def _show_rename_map_form(self, player: Player, map_id: str) -> None:
        if not self._is_op(player):
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None:
            self._show_config_maps(player)
            return

        def on_submit(p: Player, json_str: str) -> None:
            data = _parse_modal_form(json_str)
            name = str(data[0] or "").strip() if data else ""
            if not name:
                p.send_message(self._t("RENAME_MAP_FAIL").format("empty name"))
                self._show_map_edit(p, map_id)
                return
            self.config_store.update_map(map_id, lambda entry: entry.update({"display_name": name}))
            p.send_message(self._t("RENAME_MAP_OK").format(name))
            self._show_map_edit(p, map_id)

        form = ModalForm(
            title=self._t("RENAME_MAP_TITLE"),
            controls=[
                TextInput(
                    label=self._t("CREATE_MAP_NAME"),
                    placeholder="仓库",
                    default_value=str(map_cfg.get("display_name") or map_id),
                )
            ],
            on_submit=on_submit,
        )
        player.send_form(form)

    def _show_delete_map_confirm(self, player: Player, map_id: str) -> None:
        if not self._is_op(player):
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None:
            self._show_config_maps(player)
            return
        display_name = str(map_cfg.get("display_name") or map_id)
        form = ActionForm(
            title=self._t("DELETE_MAP_CONFIRM_TITLE"),
            content=self._t("DELETE_MAP_CONFIRM").format(display_name),
        )
        form.add_button(
            self._t("BTN_CONFIRM"),
            on_click=lambda sender, m=map_id, n=display_name: self._delete_map(sender, m, n),
        )
        form.add_button(self._t("BTN_CANCEL"), on_click=lambda sender, m=map_id: self._show_map_edit(sender, m))
        player.send_form(form)

    def _delete_map(self, player: Player, map_id: str, display_name: str) -> None:
        if not self._is_op(player):
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        if self._map_in_use(map_id):
            player.send_message(self._t("DELETE_MAP_BUSY"))
            self._show_map_edit(player, map_id)
            return
        assert self.config_store is not None
        if not self.config_store.delete_map(map_id):
            self._show_config_maps(player)
            return
        player.send_message(self._t("DELETE_MAP_OK").format(display_name))
        self._show_config_maps(player)

    def _set_map_pos(self, player: Player, map_id: str, which: int) -> None:
        assert self.config_store is not None
        x, y, z, yaw, pitch, dim = _player_location_tuple(player)
        key = "pos1" if which == 1 else "pos2"

        def updater(entry: Dict[str, Any]) -> None:
            region = entry.get("region") or {}
            region[key] = {"x": x, "y": y, "z": z}
            entry["region"] = region
            entry["dimension"] = dim

        self.config_store.update_map(map_id, updater)
        player.send_message(self._t("POS_SET_OK").format(which, x, y, z))
        self._show_map_edit(player, map_id)

    def _add_mode_to_map(self, player: Player, map_id: str, mode: str) -> None:
        assert self.config_store is not None

        def updater(entry: Dict[str, Any]) -> None:
            modes = list(entry.get("modes") or [])
            modes.append(
                {
                    "mode": mode,
                    "max_players_per_team": 8,
                    "target_score": 50,
                    "teams": {
                        "a": {"name": "红队", "spawns": []},
                        "b": {"name": "蓝队", "spawns": []},
                    },
                }
            )
            entry["modes"] = modes

        self.config_store.update_map(map_id, updater)
        player.send_message(self._t("ADD_MODE_OK").format(self._mode_label(mode)))
        self._show_mode_edit(player, map_id, mode)

    def _show_add_mode_form(self, player: Player, map_id: str) -> None:
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None:
            self._show_config_maps(player)
            return
        existing = {str(m.get("mode") or "").lower() for m in map_cfg.get("modes") or []}
        available = [mode for mode in KNOWN_MODES if mode not in existing and mode in IMPLEMENTED_MODES]
        if not available:
            player.send_message(self._t("ADD_MODE_EXISTS"))
            self._show_map_edit(player, map_id)
            return
        if len(available) == 1:
            mode = available[0]
            form = ActionForm(
                title=self._t("ADD_MODE_TITLE"),
                content=self._t("MODE_SELECT_BUTTON").format(self._mode_label(mode)),
            )
            form.add_button(
                self._t("BTN_CONFIRM"),
                on_click=lambda sender, m=map_id, md=mode: self._add_mode_to_map(sender, m, md),
            )
            form.add_button(self._t("BTN_CANCEL"), on_click=lambda sender, m=map_id: self._show_map_edit(sender, m))
            player.send_form(form)
            return

        options = [self._mode_label(mode) for mode in available]

        def on_submit(p: Player, json_str: str) -> None:
            data = _parse_modal_form(json_str)
            try:
                idx = int(data[0]) if data and data[0] is not None else 0
            except (TypeError, ValueError):
                idx = 0
            if idx < 0 or idx >= len(available):
                p.send_message(self._t("ADD_MODE_UNIMPLEMENTED"))
                self._show_map_edit(p, map_id)
                return
            self._add_mode_to_map(p, map_id, available[idx])

        form = ModalForm(
            title=self._t("ADD_MODE_TITLE"),
            controls=[Dropdown(label=self._t("ADD_MODE_DROPDOWN"), options=options, default_index=0)],
            on_submit=on_submit,
        )
        player.send_form(form)

    def _show_mode_edit(self, player: Player, map_id: str, mode: str) -> None:
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        mode_cfg = get_mode_config(map_cfg or {}, mode) if map_cfg else None
        if map_cfg is None or mode_cfg is None:
            self._show_map_edit(player, map_id)
            return
        teams = mode_cfg.get("teams") or {}
        a_count = len((teams.get("a") or {}).get("spawns") or [])
        b_count = len((teams.get("b") or {}).get("spawns") or [])
        content = self._t("MODE_EDIT_CONTENT").format(
            mode_cfg.get("target_score", 50),
            mode_cfg.get("max_players_per_team", 8),
            a_count,
            b_count,
        )
        form = ActionForm(title=self._t("MODE_EDIT_TITLE").format(self._mode_label(mode)), content=content)
        form.add_button(self._t("BTN_ADD_SPAWN_A"), on_click=lambda sender, m=map_id, md=mode: self._add_spawn(sender, m, md, TEAM_A))
        form.add_button(self._t("BTN_ADD_SPAWN_B"), on_click=lambda sender, m=map_id, md=mode: self._add_spawn(sender, m, md, TEAM_B))
        form.add_button(self._t("BTN_EDIT_MODE_SETTINGS"), on_click=lambda sender, m=map_id, md=mode: self._show_mode_settings_form(sender, m, md))
        for team_id in (TEAM_A, TEAM_B):
            team = teams.get(team_id) or {}
            for idx, spawn in enumerate(team.get("spawns") or []):
                label = self._t("BTN_DELETE_SPAWN").format(idx + 1, team.get("name") or team_id)
                form.add_button(
                    label,
                    on_click=lambda sender, m=map_id, md=mode, t=team_id, i=idx: self._remove_spawn(sender, m, md, t, i),
                )
        form.add_button(self._t("BACK"), on_click=lambda sender, m=map_id: self._show_map_edit(sender, m))
        player.send_form(form)

    def _add_spawn(self, player: Player, map_id: str, mode: str, team_id: str) -> None:
        assert self.config_store is not None
        x, y, z, yaw, pitch, _dim = _player_location_tuple(player)
        spawn = {"x": x, "y": y, "z": z, "radius": 0, "yaw": yaw, "pitch": pitch}

        def updater(entry: Dict[str, Any]) -> None:
            for mode_cfg in entry.get("modes") or []:
                if str(mode_cfg.get("mode") or "").lower() != mode:
                    continue
                teams = mode_cfg.setdefault("teams", {})
                team = teams.setdefault(team_id, {"name": "红队" if team_id == TEAM_A else "蓝队", "spawns": []})
                team.setdefault("spawns", []).append(spawn)

        self.config_store.update_map(map_id, updater)
        team_name = "红队" if team_id == TEAM_A else "蓝队"
        player.send_message(self._t("SPAWN_ADDED").format(team_name))
        self._show_mode_edit(player, map_id, mode)

    def _remove_spawn(self, player: Player, map_id: str, mode: str, team_id: str, index: int) -> None:
        assert self.config_store is not None

        def updater(entry: Dict[str, Any]) -> None:
            for mode_cfg in entry.get("modes") or []:
                if str(mode_cfg.get("mode") or "").lower() != mode:
                    continue
                team = (mode_cfg.get("teams") or {}).get(team_id) or {}
                spawns = list(team.get("spawns") or [])
                if 0 <= index < len(spawns):
                    spawns.pop(index)
                team["spawns"] = spawns
                mode_cfg.setdefault("teams", {})[team_id] = team

        self.config_store.update_map(map_id, updater)
        player.send_message(self._t("SPAWN_REMOVED"))
        self._show_mode_edit(player, map_id, mode)

    def _show_mode_settings_form(self, player: Player, map_id: str, mode: str) -> None:
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        mode_cfg = get_mode_config(map_cfg or {}, mode) if map_cfg else None
        if mode_cfg is None:
            self._show_mode_edit(player, map_id, mode)
            return

        def on_submit(p: Player, json_str: str) -> None:
            data = _parse_modal_form(json_str)
            try:
                target = max(1, int(str(data[0] or "50")))
                max_team = max(1, int(str(data[1] or "8")))
            except ValueError:
                p.send_message(self._t("CREATE_MAP_FAIL").format("invalid number"))
                self._show_mode_edit(p, map_id, mode)
                return

            def updater(entry: Dict[str, Any]) -> None:
                for mode_item in entry.get("modes") or []:
                    if str(mode_item.get("mode") or "").lower() != mode:
                        continue
                    mode_item["target_score"] = target
                    mode_item["max_players_per_team"] = max_team

            self.config_store.update_map(map_id, updater)
            p.send_message(self._t("MODE_SETTINGS_OK"))
            self._show_mode_edit(p, map_id, mode)

        form = ModalForm(
            title=self._t("MODE_SETTINGS_TITLE").format(self._mode_label(mode)),
            controls=[
                TextInput(label=self._t("MODE_SETTINGS_TARGET"), default_value=str(mode_cfg.get("target_score", 50))),
                TextInput(label=self._t("MODE_SETTINGS_MAX"), default_value=str(mode_cfg.get("max_players_per_team", 8))),
            ],
            on_submit=on_submit,
        )
        player.send_form(form)
