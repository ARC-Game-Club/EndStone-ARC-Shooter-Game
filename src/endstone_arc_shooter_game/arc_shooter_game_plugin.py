# -*- coding: utf-8 -*-
from __future__ import annotations

import math
import time
import traceback
from typing import Any, Dict, Optional, Tuple

from endstone import Player
from endstone.command import Command, CommandSender
from endstone.event import (
    ActorDamageEvent,
    event_handler,
    PlayerDeathEvent,
    PlayerJoinEvent,
    PlayerQuitEvent,
    PlayerRespawnEvent,
)
from endstone.form import ActionForm
from endstone.plugin import Plugin

from endstone_arc_shooter_game.config import IMPLEMENTED_MODES, ConfigStore, slot_range
from endstone_arc_shooter_game.inventory import (
    clear_player_inventory,
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
    STATE_IDLE,
    STATE_LOBBY,
    STATE_PLAYING,
    TEAM_A,
    TEAM_B,
    MapInstance,
    pick_spawn,
)

try:
    from endstone.event import PlayerDropItemEvent
except ImportError:  # pragma: no cover
    PlayerDropItemEvent = None

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


class ARCShooterGamePlugin(Plugin):
    prefix = "ARCShooterGame"
    api_version = "0.10"
    load = "POSTWORLD"

    commands = {
        "tdm": {
            "description": "射击游戏菜单、商店与离开",
            "usages": ["/tdm", "/tdm buy", "/tdm leave", "/tdm reload", "/tdm here"],
            "permissions": ["arc_shooter_game.command.tdm"],
        }
    }

    permissions = {
        "arc_shooter_game.command.tdm": {
            "description": "允许使用 /tdm",
            "default": True,
        }
    }

    def __init__(self):
        super().__init__()
        self.config_store: Optional[ConfigStore] = None
        self.language_manager: Optional[LanguageManager] = None
        self.instances: Dict[str, MapInstance] = {}
        self.player_to_map: Dict[str, str] = {}
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
        self._rebuild_instances()
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
        for inst in list(self.instances.values()):
            if inst.state in (STATE_BUYING, STATE_PLAYING):
                self._end_match(inst, winner=None)
            elif inst.state == STATE_LOBBY:
                for ps in list(inst.online_players()):
                    self.player_to_map.pop(ps.name, None)
                inst.reset_idle()
        self._safe_log("info", "[ARCShooterGame] disabled")

    def _rebuild_instances(self) -> None:
        assert self.config_store is not None
        maps = self.config_store.maps
        for map_id, inst in list(self.instances.items()):
            if map_id not in maps:
                if inst.state == STATE_IDLE:
                    del self.instances[map_id]
            elif inst.state == STATE_IDLE:
                inst.map_cfg = maps[map_id]
        for map_id, cfg in maps.items():
            if map_id not in self.instances:
                self.instances[map_id] = MapInstance(cfg)

    def _instance_of(self, player_name: str) -> Optional[MapInstance]:
        map_id = self.player_to_map.get(player_name)
        if not map_id:
            return None
        return self.instances.get(map_id)

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
        if command.name != "tdm":
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
                self._rebuild_instances()
                sender.send_message(self._t("RELOAD_OK"))
            except Exception as e:
                sender.send_message(self._t("RELOAD_FAIL").format(e))
            return True
        if not isinstance(sender, Player):
            sender.send_message(self._t("CMD_PLAYER_ONLY"))
            return True
        if sub == "here":
            if not self._is_op(sender):
                sender.send_message(self._t("CMD_NO_PERMISSION"))
                return True
            loc = sender.location
            dim = dimension_id_of(loc)
            sender.send_message(self._t("HERE_POS").format(loc.x, loc.y, loc.z, dim))
            sender.send_message(self._t("HERE_JSON").format(loc.x, loc.y, loc.z))
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
        if self._instance_of(player.name) is not None:
            return
        snap = self.backups.get(player.name) or load_snapshot_disk(player.name)
        if snap:
            self.backups[player.name] = snap
            self._restore_player(player)
            player.send_message(self._t("BACKUP_RECOVERED"))

    @event_handler
    def on_player_quit(self, event: PlayerQuitEvent):
        player = event.player
        inst = self._instance_of(player.name)
        if inst is not None:
            if inst.state == STATE_LOBBY:
                self._leave_lobby(player, inst)
            elif inst.state in (STATE_BUYING, STATE_PLAYING):
                self._leave_match(player, inst)
        if player.name in self._pending_restore:
            self._restore_player(player, force=True)

    @event_handler
    def on_actor_damage(self, event: ActorDamageEvent):
        victim = getattr(event, "actor", None)
        victim_name = _actor_player_name(victim)
        if not victim_name:
            return
        inst = self._instance_of(victim_name)
        if inst is None or inst.state not in (STATE_BUYING, STATE_PLAYING):
            return
        killer_name = self._killer_name_from_source(getattr(event, "damage_source", None))
        if killer_name and killer_name != victim_name and self._instance_of(killer_name) is inst:
            self._last_attacker[victim_name] = (killer_name, time.time())

    @event_handler
    def on_player_death(self, event: PlayerDeathEvent):
        victim = getattr(event, "player", None) or getattr(event, "actor", None)
        if victim is None:
            return
        victim_name = getattr(victim, "name", None)
        if not victim_name:
            return
        inst = self._instance_of(victim_name)
        if inst is None or inst.state not in (STATE_BUYING, STATE_PLAYING):
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
        ps = inst.players.get(victim_name)
        if killer_name and self._instance_of(killer_name) is inst:
            result = inst.apply_player_kill(killer_name, victim_name, self.config_store.kill_reward())
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
                    inst,
                    self._t("SCORE_UPDATE").format(
                        inst.team_name(TEAM_A), inst.score_a, inst.score_b, inst.team_name(TEAM_B)
                    ),
                )
                if result["winner"]:
                    self._end_match(inst, result["winner"])
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
        inst = self._instance_of(player.name)
        if inst is None or inst.state not in (STATE_BUYING, STATE_PLAYING):
            return
        try:
            self.server.scheduler.run_task(self, lambda p=player, i=inst: self._tp_to_team_spawn(p, i), delay=1)
        except Exception:
            self._tp_to_team_spawn(player, inst)

    if PlayerDropItemEvent is not None:
        @event_handler
        def on_player_drop_item(self, event: PlayerDropItemEvent):
            player = getattr(event, "player", None)
            if player is None:
                return
            inst = self._instance_of(player.name)
            if inst is not None and inst.state in (STATE_BUYING, STATE_PLAYING):
                event.is_cancelled = True

    # ---------- tick ----------

    def _on_tick(self) -> None:
        try:
            now = time.time()
            timeout = self.config_store.lobby_timeout() if self.config_store else 900
            for inst in list(self.instances.values()):
                if inst.state == STATE_LOBBY and inst.lobby_timed_out(timeout, now):
                    self._dissolve_lobby(inst, timeout=True)
                    continue
                if inst.state == STATE_BUYING and inst.buy_remaining(now) <= 0:
                    inst.begin_playing()
                    self._broadcast(inst, self._t("GAME_STARTED").format(inst.target_score))
                if inst.state in (STATE_BUYING, STATE_PLAYING):
                    self._send_score_tips(inst, now)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] tick error: {e}\n{traceback.format_exc()}")

    def _send_score_tips(self, inst: MapInstance, now: float) -> None:
        a_name = inst.team_name(TEAM_A)
        b_name = inst.team_name(TEAM_B)
        remain = int(math.ceil(inst.buy_remaining(now))) if inst.state == STATE_BUYING else 0
        for ps in inst.online_players():
            player = self._get_player(ps.name)
            if player is None:
                continue
            if inst.state == STATE_BUYING:
                msg = self._t("BUY_TIME_TIP").format(remain, a_name, inst.score_a, inst.score_b, b_name, ps.points)
            else:
                msg = self._t("PLAYING_TIP").format(a_name, inst.score_a, inst.score_b, b_name, ps.points)
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

    # ---------- match flow ----------

    def _join_map(self, player: Player, map_id: str) -> None:
        assert self.config_store is not None
        if self._instance_of(player.name) is not None:
            player.send_message(self._t("JOIN_FAIL_IN_GAME"))
            return
        inst = self.instances.get(map_id)
        cfg = self.config_store.maps.get(map_id)
        if inst is None or cfg is None:
            player.send_message(self._t("JOIN_FAIL_UNKNOWN"))
            return
        if cfg.get("mode") not in IMPLEMENTED_MODES:
            player.send_message(self._t("JOIN_FAIL_MODE"))
            return
        ok, reason = inst.join(player.name, self.config_store.starting_points())
        if not ok:
            player.send_message(self._t("JOIN_FAIL_PLAYING" if reason == "playing" else "JOIN_FAIL_FULL"))
            return
        self.player_to_map[player.name] = map_id
        if reason == "admin":
            player.send_message(self._t("JOIN_OK_ADMIN").format(inst.display_name))
        else:
            player.send_message(self._t("JOIN_OK").format(inst.display_name, inst.admin or "-"))
        self._show_lobby_menu(player, inst)

    def _leave_lobby(self, player: Player, inst: MapInstance) -> None:
        new_admin = inst.leave(player.name)
        self.player_to_map.pop(player.name, None)
        player.send_message(self._t("LEAVE_OK").format(inst.display_name))
        if inst.state == STATE_IDLE:
            return
        if new_admin:
            admin_player = self._get_player(new_admin)
            if admin_player:
                admin_player.send_message(self._t("ADMIN_TRANSFERRED").format(inst.display_name))

    def _handle_leave(self, player: Player, confirm_match: bool) -> None:
        inst = self._instance_of(player.name)
        if inst is None:
            player.send_message(self._t("LEAVE_NOT_IN"))
            return
        if inst.state == STATE_LOBBY:
            self._leave_lobby(player, inst)
            return
        if inst.state in (STATE_BUYING, STATE_PLAYING):
            if confirm_match:
                self._show_leave_match_confirm(player)
                return
            self._leave_match(player, inst)

    def _leave_match(self, player: Player, inst: MapInstance) -> None:
        inst.leave(player.name)
        self.player_to_map.pop(player.name, None)
        self._restore_player(player)
        player.send_message(self._t("LEAVE_OK").format(inst.display_name))
        if inst.state not in (STATE_BUYING, STATE_PLAYING):
            return
        if inst.player_count() == 0:
            self._end_match(inst, winner=None)
            return
        winner = inst.remaining_winner()
        if winner is not None:
            self._end_match(inst, winner)

    def _dissolve_lobby(self, inst: MapInstance, timeout: bool) -> None:
        names = [p.name for p in inst.online_players()]
        key = "LOBBY_DISSOLVED_TIMEOUT" if timeout else "LOBBY_DISSOLVED_EMPTY"
        msg = self._t(key).format(inst.display_name)
        for name in names:
            self.player_to_map.pop(name, None)
            player = self._get_player(name)
            if player:
                player.send_message(msg)
        inst.reset_idle()

    def _start_match(self, player: Player, inst: MapInstance) -> None:
        if inst.admin != player.name:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        ok, reason = inst.can_start()
        if not ok:
            player.send_message(self._t("START_NEED_SPAWNS" if reason == "need_spawns" else "START_NEED_PLAYERS"))
            return
        buy_seconds = self.config_store.buy_time() if self.config_store else 10
        starting = self.config_store.starting_points() if self.config_store else 800
        for ps in inst.online_players():
            ps.points = starting
            ps.kills = 0
            ps.deaths = 0
            ps.primary_id = None
            ps.secondary_id = None
            ps.gadgets = []
        inst.begin_buy(buy_seconds)
        if buy_seconds <= 0:
            inst.begin_playing()
        self._broadcast(inst, self._t("START_BROADCAST").format(buy_seconds))
        for ps in inst.online_players():
            member = self._get_player(ps.name)
            if member is None:
                continue
            self._prepare_fighter(member, inst)
        if inst.state == STATE_PLAYING:
            self._broadcast(inst, self._t("GAME_STARTED").format(inst.target_score))

    def _prepare_fighter(self, player: Player, inst: MapInstance) -> None:
        snap = snapshot_player(player, dimension_id_of(player.location))
        self.backups[player.name] = snap
        try:
            save_snapshot_disk(player.name, snap)
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] backup disk fail for {player.name}: {e}")
        clear_player_inventory(player)
        self._set_gamemode(player.name, "adventure")
        try:
            if hasattr(player, "health"):
                player.health = getattr(player, "max_health", 20) or 20
        except Exception:
            pass
        self._tp_to_team_spawn(player, inst)

    def _tp_to_team_spawn(self, player: Player, inst: MapInstance) -> None:
        ps = inst.players.get(player.name)
        if ps is None:
            return
        spawns = inst.team_spawns(ps.team)
        if not spawns:
            return
        pos = pick_spawn(spawns)
        self._tp_player(
            player.name,
            pos["x"],
            pos["y"],
            pos["z"],
            inst.map_cfg.get("dimension") or "overworld",
            pos.get("yaw"),
            pos.get("pitch"),
        )

    def _end_match(self, inst: MapInstance, winner: Optional[str]) -> None:
        lines = self._result_lines(inst, winner)
        still = [ps.name for ps in inst.online_players()]
        participants = {ps.name for ps in inst.result_rows()}
        for name in still:
            member = self._get_player(name)
            self.player_to_map.pop(name, None)
            if member:
                self._restore_player(member)
        for name in participants:
            member = self._get_player(name)
            if member is None:
                continue
            for line in lines:
                member.send_message(line)
        inst.reset_idle()

    def _result_lines(self, inst: MapInstance, winner: Optional[str]) -> list[str]:
        lines = [self._t("MATCH_END_HEADER")]
        if winner:
            lines.append(self._t("MATCH_END_WINNER").format(inst.team_name(winner)))
        else:
            lines.append(self._t("MATCH_END_DRAW"))
        rows = inst.result_rows()
        for team_id in (TEAM_A, TEAM_B):
            lines.append(self._t("MATCH_END_STATS_TEAM").format(inst.team_name(team_id)))
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

    def _restore_player(self, player: Player, force: bool = False) -> None:
        if not force and self._is_probably_dead(player):
            self._pending_restore.add(player.name)
            return
        self._pending_restore.discard(player.name)
        snap = self.backups.pop(player.name, None) or load_snapshot_disk(player.name)
        if snap is None:
            return
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

    def _set_gamemode(self, player_name: str, mode: str) -> None:
        raw = str(mode or "survival").split(".")[-1].lower().replace("gamemode_", "")
        if raw not in ("survival", "creative", "adventure", "spectator"):
            raw = "survival"
        self.server.dispatch_command(
            self.server.command_sender,
            f"gamemode {raw} {format_player_name(player_name)}",
        )

    def _broadcast(self, inst: MapInstance, message: str) -> None:
        for ps in inst.online_players():
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

    def _status_label(self, inst: MapInstance) -> str:
        if inst.map_cfg.get("mode") not in IMPLEMENTED_MODES:
            return self._t("MAP_STATUS_UNIMPLEMENTED")
        if inst.state == STATE_IDLE:
            return self._t("MAP_STATUS_IDLE")
        if inst.state == STATE_LOBBY:
            return self._t("MAP_STATUS_LOBBY")
        return self._t("MAP_STATUS_PLAYING")

    def _lobby_remaining_text(self, inst: MapInstance) -> str:
        timeout = self.config_store.lobby_timeout() if self.config_store else 900
        remain = max(0, int(timeout - (time.time() - inst.lobby_started_at)))
        minutes, seconds = divmod(remain, 60)
        return f"{minutes:02d}:{seconds:02d}"

    def _team_block(self, inst: MapInstance, team_id: str) -> str:
        names = [p.name for p in inst.online_players() if p.team == team_id]
        body = "、".join(names) if names else self._t("NO_PLAYER")
        return self._t("TEAM_LINE").format(
            inst.team_name(team_id),
            inst.team_count(team_id),
            inst.max_per_team,
            body,
        )

    # ---------- shop ----------

    def _buy_weapon(self, player: Player, weapon_id: str) -> None:
        assert self.config_store is not None
        inst = self._instance_of(player.name)
        if inst is None or inst.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        weapon = self.config_store.weapons.get(weapon_id)
        if weapon is None:
            player.send_message(self._t("BUY_FAIL_UNKNOWN"))
            return
        ps = inst.players.get(player.name)
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
        idx, old_id = inst.record_purchase(player.name, weapon, capacity)
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
        inst = self._instance_of(player.name)
        if inst is None:
            self._show_map_list(player)
            return
        if inst.state == STATE_LOBBY:
            self._show_lobby_menu(player, inst)
            return
        self._show_match_menu(player, inst)

    def _show_map_list(self, player: Player) -> None:
        try:
            form = ActionForm(title=self._t("MENU_TITLE"), content=self._t("MENU_CONTENT"))
            if not self.instances:
                form = ActionForm(title=self._t("MENU_TITLE"), content=self._t("MENU_NO_MAPS"))
                form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
                player.send_form(form)
                return
            for inst in self.instances.values():
                cfg = inst.map_cfg
                label = self._t("MAP_BUTTON").format(
                    cfg.get("display_name") or cfg["id"],
                    self._mode_label(cfg.get("mode") or "tdm"),
                    inst.player_count(),
                    self._status_label(inst),
                )
                map_id = cfg["id"]
                form.add_button(label, on_click=lambda sender, mid=map_id: self._join_map(sender, mid))
            form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] map list: {e}\n{traceback.format_exc()}")
            player.send_message(self._t("PANEL_ERROR"))

    def _show_lobby_menu(self, player: Player, inst: MapInstance) -> None:
        try:
            content = self._t("LOBBY_CONTENT").format(
                self._mode_label(inst.mode),
                inst.admin or "-",
                self._lobby_remaining_text(inst),
                inst.target_score,
                inst.max_per_team,
                self._team_block(inst, TEAM_A),
                self._team_block(inst, TEAM_B),
            )
            form = ActionForm(title=self._t("LOBBY_TITLE").format(inst.display_name), content=content)
            is_admin = inst.admin == player.name
            if is_admin:
                form.add_button(self._t("BTN_START"), on_click=lambda sender, i=inst: self._start_match(sender, i))
                form.add_button(self._t("BTN_ASSIGN"), on_click=lambda sender, i=inst: self._show_assign_menu(sender, i))
                form.add_button(self._t("BTN_KICK"), on_click=lambda sender, i=inst: self._show_kick_menu(sender, i))
            form.add_button(self._t("BTN_LEAVE"), on_click=lambda sender: self._handle_leave(sender, confirm_match=False))
            form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] lobby menu: {e}\n{traceback.format_exc()}")
            player.send_message(self._t("PANEL_ERROR"))

    def _show_assign_menu(self, player: Player, inst: MapInstance) -> None:
        if inst.admin != player.name or inst.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        form = ActionForm(title=self._t("ASSIGN_TITLE"), content=self._t("ASSIGN_CONTENT"))
        for ps in inst.online_players():
            label = self._t("ASSIGN_BUTTON").format(ps.name, inst.team_name(ps.team))
            form.add_button(
                label,
                on_click=lambda sender, n=ps.name, i=inst: self._toggle_team(sender, i, n),
            )
        form.add_button(self._t("BACK"), on_click=lambda sender, i=inst: self._show_lobby_menu(sender, i))
        player.send_form(form)

    def _toggle_team(self, player: Player, inst: MapInstance, target_name: str) -> None:
        ps = inst.players.get(target_name)
        if ps is None:
            self._show_assign_menu(player, inst)
            return
        other = TEAM_B if ps.team == TEAM_A else TEAM_A
        ok, reason = inst.set_team(target_name, other)
        if not ok and reason == "full":
            player.send_message(self._t("ASSIGN_TEAM_FULL"))
        elif ok:
            player.send_message(self._t("ASSIGN_DONE").format(target_name, inst.team_name(other)))
        self._show_assign_menu(player, inst)

    def _show_kick_menu(self, player: Player, inst: MapInstance) -> None:
        if inst.admin != player.name or inst.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        form = ActionForm(title=self._t("KICK_TITLE"), content=self._t("KICK_CONTENT"))
        for ps in inst.online_players():
            form.add_button(ps.name, on_click=lambda sender, n=ps.name, i=inst: self._kick_player(sender, i, n))
        form.add_button(self._t("BACK"), on_click=lambda sender, i=inst: self._show_lobby_menu(sender, i))
        player.send_form(form)

    def _kick_player(self, admin: Player, inst: MapInstance, target_name: str) -> None:
        if target_name == admin.name:
            admin.send_message(self._t("KICK_SELF"))
            self._show_kick_menu(admin, inst)
            return
        if not inst.kick(target_name):
            self._show_kick_menu(admin, inst)
            return
        self.player_to_map.pop(target_name, None)
        target = self._get_player(target_name)
        if target:
            target.send_message(self._t("KICKED").format(inst.display_name))
        admin.send_message(self._t("KICK_OK").format(target_name))
        self._show_kick_menu(admin, inst)

    def _show_match_menu(self, player: Player, inst: MapInstance) -> None:
        ps = inst.players.get(player.name)
        if ps is None:
            return
        content = self._t("MATCH_CONTENT").format(
            inst.team_name(TEAM_A),
            inst.score_a,
            inst.team_name(TEAM_B),
            inst.score_b,
            inst.team_name(ps.team),
            ps.points,
            ps.kills,
            ps.deaths,
        )
        form = ActionForm(title=self._t("MATCH_TITLE").format(inst.display_name), content=content)
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
        inst = self._instance_of(player.name)
        if inst is None or inst.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        ps = inst.players.get(player.name)
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
        inst = self._instance_of(player.name)
        if inst is None or inst.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        ps = inst.players.get(player.name)
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
