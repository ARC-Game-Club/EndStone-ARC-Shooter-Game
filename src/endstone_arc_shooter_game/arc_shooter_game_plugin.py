# -*- coding: utf-8 -*-
import json
import math
import random
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
    PlayerInteractEvent,
    PlayerItemConsumeEvent,
    PlayerJoinEvent,
    PlayerQuitEvent,
    PlayerRespawnEvent,
)
from endstone.form import ActionForm, Dropdown, ModalForm, TextInput
from endstone.plugin import Plugin

from endstone_arc_shooter_game.career_stats import (
    CareerStore,
    KD_TITLE_TIERS,
    titles_unlocked_by_kd,
)
from endstone_arc_shooter_game.config import (
    IMPLEMENTED_MODES,
    KNOWN_MODES,
    ConfigStore,
    build_runtime_map_cfg,
    get_mode_config,
    has_region,
    map_incomplete_reasons,
    mode_incomplete_reasons,
    mode_playable,
    playable_modes,
    point_in_region,
    calc_match_money,
    collect_assist_and_tk,
    match_performance_score,
    pick_team_mvp,
    slot_range,
)
from endstone_arc_shooter_game.inventory import (
    apply_armor_extras,
    bind_arc_inventory,
    clear_armor,
    delete_snapshot_disk,
    give_to_end_slots,
    load_snapshot_disk,
    remove_armor_extras,
    remove_item_count,
    restore_inventory,
    save_snapshot_disk,
    set_slot_item,
    snapshot_player,
)
from endstone_arc_shooter_game.language import LanguageManager
from endstone_arc_shooter_game.loadout import (
    REASON_ALREADY_OWNED,
    REASON_DISABLED,
    REASON_INSUFFICIENT,
    REASON_NO_SLOT,
    REASON_UNKNOWN,
    SlotCapacities,
    WeaponAcquireStrategy,
    owned_weapon_ids,
    resolve_acquire_strategy,
)
from endstone_arc_shooter_game.session import (
    STATE_BUYING,
    STATE_COUNTDOWN,
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

ARC_COIN_ITEM = "arc:arc_coin"
ARC_COIN_HOTBAR_SLOT = 8
SHOP_DEBOUNCE_SECONDS = 0.2
SPAWN_PROTECT_SECONDS = 3
MATCH_BUFF_DURATION_SECONDS = 1000000
# 基岩版玩家默认行走速度；购买期设为 0，开局再恢复
DEFAULT_MOVEMENT_SPEED = 0.1
TEAM_NAME_COLOR = {
    TEAM_A: "§c",
    TEAM_B: "§9",
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
    # 背包发放/扣除依赖弧光背包管理器
    load_after = ["arc_inventory"]

    commands = {
        "gs": {
            "description": "射击游戏菜单与离开",
            "usages": ["/gs", "/gs leave", "/gs reload"],
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
        self.career_store: Optional[CareerStore] = None
        self.lobbies: Dict[str, Lobby] = {}
        self.player_to_lobby: Dict[str, str] = {}
        self.backups: Dict[str, Dict[str, Any]] = {}
        self._last_attacker: Dict[str, Tuple[str, float]] = {}
        # victim -> {attacker_name: last_damage_unix}
        self._damage_log: Dict[str, Dict[str, float]] = {}
        self._shop_open_at: Dict[str, float] = {}
        self._saved_name_tags: Dict[str, str] = {}
        self._pending_restore: set[str] = set()
        self._spawn_protect_until: Dict[str, float] = {}
        self._buy_frozen: set[str] = set()
        self._tick_task = None
        self._fast_tick_task = None

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
        try:
            self.career_store = CareerStore(logger=getattr(self, "logger", None))
        except Exception as e:
            self.career_store = None
            self._safe_log("error", f"[ARCShooterGame] career store init failed: {e}")
        self._safe_log("info", "[ARCShooterGame] on_load")

    def on_enable(self) -> None:
        inv = None
        try:
            inv = self.server.plugin_manager.get_plugin("arc_inventory")
        except Exception:
            inv = None
        if inv is None:
            self._safe_log(
                "error",
                "[ARCShooterGame] 未找到 arc_inventory（弧光背包管理器）。"
                "请将 endstone_arc_inventory-*.whl 放入 plugins/ 后重启。",
            )
        else:
            bind_arc_inventory(inv)
            self._safe_log("info", "[ARCShooterGame] 已绑定 arc_inventory 背包 API")
        self._ensure_kd_title_definitions()
        self.register_events(self)
        try:
            self._tick_task = self.server.scheduler.run_task(self, self._on_tick, delay=20, period=20)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] Failed to register tick: {e}")
        try:
            self._fast_tick_task = self.server.scheduler.run_task(
                self, self._on_fast_tick, delay=5, period=5
            )
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] Failed to register fast tick: {e}")
        self._safe_log("info", "[ARCShooterGame] enabled")

    def on_disable(self) -> None:
        bind_arc_inventory(None)
        if self.career_store is not None:
            try:
                self.career_store.close()
            except Exception:
                pass
            self.career_store = None
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
                    member = self._get_player(ps.name)
                    if member:
                        self._restore_name_tag(member)
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

    def _playable_maps(self) -> List[Dict[str, Any]]:
        if self.config_store is None:
            return []
        return [
            map_cfg
            for map_cfg in self.config_store.maps.values()
            if has_region(map_cfg) and playable_modes(map_cfg)
        ]

    def _free_playable_maps(self, exclude_lobby_id: Optional[str] = None) -> List[Dict[str, Any]]:
        return [
            map_cfg
            for map_cfg in self._playable_maps()
            if not self._map_in_use(map_cfg["id"], exclude_lobby_id=exclude_lobby_id)
        ]

    def _can_create_lobby(self) -> bool:
        # 大厅数必须 <= 可玩地图数
        return len(self.lobbies) < len(self._playable_maps())

    def _assign_map_for_start(self, lobby: Lobby) -> Tuple[bool, str]:
        """开局时占用空余地图；随机偏好则抽图抽模式。"""
        assert self.config_store is not None
        free = self._free_playable_maps(exclude_lobby_id=lobby.lobby_id)
        if not lobby.prefer_random_map and lobby.map_id and lobby.mode and lobby.map_cfg:
            if self._map_in_use(lobby.map_id, exclude_lobby_id=lobby.lobby_id):
                return False, "busy"
            # 已手选且仍空闲：重新绑定最新配置
            map_cfg = self.config_store.maps.get(lobby.map_id)
            if map_cfg is None or not playable_modes(map_cfg):
                return False, "not_ready"
            ok, reason = lobby.set_map_and_mode(map_cfg, lobby.mode)
            return ok, reason if not ok else "ok"

        if not free:
            return False, "no_free_map"
        map_cfg = random.choice(free)
        modes = playable_modes(map_cfg)
        if not modes:
            return False, "no_free_map"
        if (
            not lobby.prefer_random_mode
            and lobby.mode
            and lobby.mode in modes
        ):
            mode = lobby.mode
        else:
            mode = random.choice(modes)
        ok, reason = lobby.set_map_and_mode(map_cfg, mode)
        return ok, reason if not ok else "ok"

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
        if sub == "leave":
            self._handle_leave(sender, confirm_match=True)
            return True
        if sub and sub not in ("leave",):
            sender.send_message(self._t("CMD_UNKNOWN_SUB").format(sub))
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
            if lobby.state in (STATE_LOBBY, STATE_COUNTDOWN):
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
        if lobby.state == STATE_BUYING or self._is_spawn_protected(victim_name):
            if hasattr(event, "is_cancelled"):
                event.is_cancelled = True
            return
        killer_name = self._killer_name_from_source(getattr(event, "damage_source", None))
        if killer_name and killer_name != victim_name and self._lobby_of(killer_name) is lobby:
            now = time.time()
            self._last_attacker[victim_name] = (killer_name, now)
            self._damage_log.setdefault(victim_name, {})[killer_name] = now

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
                        self._send_kill_toast(killer, victim_name)
                victim_player = self._get_player(victim_name)
                if victim_player:
                    victim_player.send_message(self._t("PLAYER_KILLED").format(killer_name or "未知"))
                self._credit_assists_and_tk(lobby, victim_name, killer_name)
                if result["friendly"]:
                    self._record_career_combat(killer_name, victim_name, friendly=True)
                else:
                    weapon_id = None
                    if killer is not None:
                        weapon_id = self._resolve_kill_weapon_id(
                            killer, lobby.players.get(killer_name)
                        )
                    self._record_career_combat(
                        killer_name,
                        victim_name,
                        weapon_id=weapon_id,
                        friendly=False,
                    )
                self._broadcast(
                    lobby,
                    self._t("SCORE_UPDATE").format(
                        lobby.team_name(TEAM_A), lobby.score_a, lobby.score_b, lobby.team_name(TEAM_B)
                    ),
                )
                if result["winner"]:
                    self._damage_log.pop(victim_name, None)
                    self._last_attacker.pop(victim_name, None)
                    self._end_match(lobby, result["winner"])
                    return
        elif ps is not None:
            ps.deaths += 1
            self._record_career_death(victim_name)
        self._damage_log.pop(victim_name, None)
        self._last_attacker.pop(victim_name, None)

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
            self.server.scheduler.run_task(
                self,
                lambda p=player, lb=lobby: (
                    self._respawn_in_match(p, lb),
                    self._apply_team_name_tag(p, lb),
                ),
                delay=1,
            )
        except Exception:
            self._respawn_in_match(player, lobby)
            self._apply_team_name_tag(player, lobby)

    @event_handler
    def on_player_interact(self, event: PlayerInteractEvent):
        player = getattr(event, "player", None)
        if player is None:
            return
        if self._hand_item_id(player) != ARC_COIN_ITEM:
            return
        if hasattr(event, "is_cancelled"):
            event.is_cancelled = True
        self._try_open_shop(player)

    @event_handler
    def on_player_item_consume(self, event: PlayerItemConsumeEvent):
        player = getattr(event, "player", None)
        if player is None:
            return
        item = getattr(event, "item", None)
        item_type = getattr(getattr(item, "type", None), "id", None) or str(getattr(item, "type", "") or "")
        if str(item_type) != ARC_COIN_ITEM:
            return
        if hasattr(event, "is_cancelled"):
            event.is_cancelled = True
        self._try_open_shop(player)

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
                if lobby.state == STATE_COUNTDOWN:
                    self._tick_start_countdown(lobby, now)
                    continue
                if lobby.state == STATE_BUYING and lobby.buy_remaining(now) <= 0:
                    self._enter_playing(lobby, now)
                if lobby.state == STATE_PLAYING:
                    self._tick_match_end_warnings(lobby, now)
                    if lobby.match_timed_out(now):
                        self._end_match(lobby, lobby.winner_by_score(), timed_out=True)
                        continue
                if lobby.state in (STATE_BUYING, STATE_PLAYING):
                    self._send_score_tips(lobby, now)
                    self._enforce_region(lobby)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] tick error: {e}\n{traceback.format_exc()}")

    def _on_fast_tick(self) -> None:
        try:
            for lobby in list(self.lobbies.values()):
                if lobby.state == STATE_BUYING:
                    self._enforce_buy_freeze(lobby)
                if lobby.state in (STATE_BUYING, STATE_PLAYING, STATE_COUNTDOWN, STATE_LOBBY):
                    self._update_sneak_name_tags(lobby)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] fast tick error: {e}\n{traceback.format_exc()}")

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
                match_remain = int(math.ceil(lobby.match_remaining(now)))
                msg = self._t("PLAYING_TIP").format(
                    match_remain, a_name, lobby.score_a, lobby.score_b, b_name, ps.points
                )
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
        if not self._playable_maps():
            player.send_message(self._t("CREATE_LOBBY_NO_MAPS"))
            return
        if not self._can_create_lobby():
            player.send_message(
                self._t("CREATE_LOBBY_FULL").format(len(self.lobbies), len(self._playable_maps()))
            )
            return
        lobby = Lobby(admin=player.name)
        lobby.set_prefer_random(map_=True, mode=True)
        self.lobbies[lobby.lobby_id] = lobby
        ok, reason = lobby.join(player.name, self.config_store.starting_points() if self.config_store else 1000)
        if not ok:
            self.lobbies.pop(lobby.lobby_id, None)
            player.send_message(self._t("JOIN_FAIL_FULL"))
            return
        self.player_to_lobby[player.name] = lobby.lobby_id
        self._notify(player, self._t("JOIN_OK_ADMIN"))
        self._apply_team_name_tag(player, lobby)
        self._broadcast_server(
            self._t("LOBBY_CREATED_BROADCAST").format(
                player.name,
                self._lobby_map_label(lobby),
                self._lobby_mode_label(lobby),
            )
        )
        self._refresh_lobby_menus(lobby)

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
            self._notify(player, self._t("JOIN_OK_MATCH"))
            strategy = self._acquire_strategy(lobby)
            weapons = self.config_store.weapons if self.config_store else {}
            strategy.assign_on_match_start(lobby.players[player.name], weapons, lobby.map_cfg or {})
            self._prepare_fighter(player, lobby)
            self._restore_player_loadout(player, lobby, gadgets=True)
            self._apply_team_name_tag(player, lobby)
            if lobby.state == STATE_BUYING and strategy.uses_buy_phase:
                self._set_buy_freeze(player)
            elif lobby.state == STATE_PLAYING:
                self._apply_match_buffs(player)
                self._apply_spawn_protect(player)
            self._show_match_menu(player, lobby)
            return
        count = lobby.player_count()
        max_players = lobby.max_per_team * 2
        self._notify(player, self._t("JOIN_OK").format(lobby.admin or "-"))
        self._notify_lobby_members_joined(lobby, player.name, count, max_players)
        self._apply_team_name_tag(player, lobby)
        self._refresh_lobby_menus(lobby)
        if lobby.state == STATE_COUNTDOWN:
            remain = int(math.ceil(lobby.countdown_remaining()))
            self._send_title(
                player,
                self._t("TITLE_COUNTDOWN").format(remain),
                self._t("TITLE_COUNTDOWN_SUB"),
                fade_in=0,
                stay=25,
                fade_out=5,
            )

    def _leave_lobby(self, player: Player, lobby: Lobby) -> None:
        leaver_name = player.name
        was_countdown = lobby.state == STATE_COUNTDOWN
        new_admin = lobby.leave(leaver_name)
        self.player_to_lobby.pop(leaver_name, None)
        self._restore_name_tag(player)
        player.send_message(self._t("LEAVE_OK"))
        self._schedule_root_menu(player)
        if lobby.player_count() == 0:
            self.lobbies.pop(lobby.lobby_id, None)
            return
        if was_countdown and not lobby.teams_ready_to_start():
            lobby.cancel_countdown()
            self._broadcast(lobby, self._t("COUNTDOWN_CANCELLED"))
        if new_admin:
            admin_player = self._get_player(new_admin)
            if admin_player:
                admin_player.send_message(self._t("ADMIN_TRANSFERRED"))
        self._notify_lobby_members_left(lobby, leaver_name)

    def _handle_leave(self, player: Player, confirm_match: bool) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is None:
            player.send_message(self._t("LEAVE_NOT_IN"))
            return
        if lobby.state in (STATE_LOBBY, STATE_COUNTDOWN):
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
        self._clear_buy_freeze(player.name)
        self._clear_match_effects(player.name)
        self._restore_player(player, after_match=True)
        self._restore_name_tag(player)
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
                self._restore_name_tag(player)
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
        assigned, assign_reason = self._assign_map_for_start(lobby)
        if not assigned:
            if assign_reason == "busy":
                name = self._map_display_name(lobby.map_id)
                if lobby.prefer_random_map:
                    lobby.clear_map_selection()
                else:
                    # 手选图被占：清掉无效选择，让房主重选
                    lobby.set_prefer_random(map_=True, mode=True)
                player.send_message(self._t("MAP_SELECT_TAKEN").format(name))
                self._show_map_select(player, lobby)
            elif assign_reason == "no_free_map":
                player.send_message(self._t("START_NO_FREE_MAP"))
            else:
                player.send_message(self._t("START_NEED_SPAWNS"))
            return
        # 分配后复核出生点等
        ok, reason = lobby.can_start()
        if not ok:
            if lobby.prefer_random_map:
                lobby.clear_map_selection()
            if reason == "need_spawns":
                player.send_message(self._t("START_NEED_SPAWNS"))
            else:
                player.send_message(self._t("START_NEED_PLAYERS"))
            return
        buy_seconds = self.config_store.buy_time() if self.config_store else 20
        countdown = self.config_store.start_countdown() if self.config_store else 5
        starting = self.config_store.starting_points() if self.config_store else 1000
        strategy = self._acquire_strategy(lobby)
        for ps in lobby.online_players():
            ps.points = starting
            ps.kills = 0
            ps.deaths = 0
            ps.assists = 0
            ps.team_kills = 0
            strategy.clear_for_match_start(ps)
        lobby.begin_countdown(countdown)
        self._broadcast(
            lobby,
            self._t("START_MAP_ASSIGNED").format(
                self._lobby_map_label(lobby),
                self._lobby_mode_label(lobby),
            ),
        )
        if strategy.uses_buy_phase:
            self._broadcast(lobby, self._t("START_BROADCAST").format(buy_seconds))
        else:
            self._broadcast(lobby, self._t("START_BROADCAST_NO_BUY"))
        self._apply_lobby_name_tags(lobby)
        remain = int(math.ceil(lobby.countdown_remaining()))
        self._title_lobby(
            lobby,
            self._t("TITLE_COUNTDOWN").format(remain),
            self._t("TITLE_COUNTDOWN_SUB"),
            fade_in=0,
            stay=25,
            fade_out=5,
        )
        lobby.mark_announced(f"cd:{remain}")
        self._refresh_lobby_menus(lobby)

    def _tick_start_countdown(self, lobby: Lobby, now: float) -> None:
        if not lobby.teams_ready_to_start():
            lobby.cancel_countdown()
            self._broadcast(lobby, self._t("COUNTDOWN_CANCELLED"))
            self._refresh_lobby_menus(lobby)
            return
        remain = lobby.countdown_remaining(now)
        if remain <= 0:
            self._finish_countdown_and_start(lobby, now)
            return
        sec = int(math.ceil(remain))
        key = f"cd:{sec}"
        if lobby.mark_announced(key):
            self._title_lobby(
                lobby,
                self._t("TITLE_COUNTDOWN").format(sec),
                self._t("TITLE_COUNTDOWN_SUB"),
                fade_in=0,
                stay=25,
                fade_out=5,
            )

    def _finish_countdown_and_start(self, lobby: Lobby, now: float) -> None:
        strategy = self._acquire_strategy(lobby)
        buy_seconds = self.config_store.buy_time() if self.config_store else 20
        if not strategy.uses_buy_phase:
            buy_seconds = 0
        weapons = self.config_store.weapons if self.config_store else {}
        mode_cfg = lobby.map_cfg or {}
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is None:
                continue
            strategy.assign_on_match_start(ps, weapons, mode_cfg)
            self._prepare_fighter(member, lobby)
            self._restore_player_loadout(member, lobby, gadgets=True)
            if strategy.uses_buy_phase:
                self._set_buy_freeze(member)
        self._apply_lobby_name_tags(lobby)
        lobby.begin_buy(buy_seconds, now)
        if buy_seconds <= 0:
            self._enter_playing(lobby, now)
            return
        self._title_lobby(
            lobby,
            self._t("TITLE_BUY"),
            self._t("TITLE_BUY_SUB").format(buy_seconds),
            fade_in=5,
            stay=40,
            fade_out=10,
        )

    def _enter_playing(self, lobby: Lobby, now: float) -> None:
        match_seconds = lobby.match_time_seconds
        lobby.begin_playing(match_seconds, now)
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is None:
                continue
            self._clear_buy_freeze(ps.name)
            self._apply_match_buffs(member)
        match_min = lobby.match_time_minutes
        self._broadcast(lobby, self._t("GAME_STARTED").format(match_min, lobby.target_score))
        self._title_lobby(
            lobby,
            self._t("TITLE_BATTLE"),
            self._t("TITLE_BATTLE_SUB").format(match_min, lobby.target_score),
            fade_in=5,
            stay=50,
            fade_out=10,
        )

    def _tick_match_end_warnings(self, lobby: Lobby, now: float) -> None:
        remain = lobby.match_remaining(now)
        sec = int(math.ceil(remain))
        if sec <= 0:
            return
        if sec == 60 and lobby.mark_announced("warn:60"):
            self._broadcast(lobby, self._t("MATCH_WARN_ONE_MINUTE"))
            return
        if 1 <= sec <= 10 and lobby.mark_announced(f"warn:{sec}"):
            self._broadcast(lobby, self._t("MATCH_WARN_SECONDS").format(sec))
            self._title_lobby(
                lobby,
                self._t("TITLE_MATCH_END_COUNT").format(sec),
                self._t("TITLE_MATCH_END_COUNT_SUB"),
                fade_in=0,
                stay=20,
                fade_out=5,
            )

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
        self._give_arc_coin(player)

    def _respawn_in_match(self, player: Player, lobby: Lobby) -> None:
        self._tp_to_team_spawn(player, lobby)
        self._clear_player(player.name)
        clear_armor(player)
        ps = lobby.players.get(player.name)
        if ps is not None and lobby.state == STATE_PLAYING:
            strategy = self._acquire_strategy(lobby)
            weapons = self.config_store.weapons if self.config_store else {}
            strategy.assign_on_respawn(ps, weapons, lobby.map_cfg or {})
        self._restore_player_loadout(player, lobby, gadgets=True)
        if ps is not None:
            try:
                self.server.scheduler.run_task(
                    self,
                    lambda p=player, s=ps: self._apply_owned_weapon_ammo(p, s),
                    delay=3,
                )
            except Exception:
                self._apply_owned_weapon_ammo(player, ps)
        try:
            if hasattr(player, "health"):
                player.health = getattr(player, "max_health", 20) or 20
        except Exception:
            pass
        if lobby.state == STATE_PLAYING:
            self._apply_match_buffs(player)
            self._apply_spawn_protect(player)
        elif lobby.state == STATE_BUYING:
            self._set_buy_freeze(player)

    def _give_arc_coin(self, player: Player) -> None:
        remove_item_count(player, ARC_COIN_ITEM, 64)
        set_slot_item(player, ARC_COIN_HOTBAR_SLOT, ARC_COIN_ITEM, 1, 0)

    def _try_open_shop(self, player: Player) -> bool:
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            return False
        strategy = self._acquire_strategy(lobby)
        if not strategy.uses_shop:
            player.send_message(self._t("SHOP_DISABLED_MODE"))
            return True
        now = time.time()
        last = self._shop_open_at.get(player.name, 0.0)
        if now - last < SHOP_DEBOUNCE_SECONDS:
            return True
        self._shop_open_at[player.name] = now
        self._show_shop(player)
        return True

    def _schedule_lobby_menu(self, player: Player, lobby: Lobby, delay: int = 5) -> None:
        try:
            self.server.scheduler.run_task(
                self,
                lambda p=player, lb=lobby: self._show_lobby_menu(p, lb),
                delay=delay,
            )
        except Exception:
            self._show_lobby_menu(player, lobby)

    def _schedule_root_menu(self, player: Player, delay: int = 5) -> None:
        try:
            self.server.scheduler.run_task(
                self,
                lambda p=player: self._show_root_menu(p),
                delay=delay,
            )
        except Exception:
            self._show_root_menu(player)

    def _set_weapon_ammo(self, player_name: str, weapon: Dict[str, Any]) -> None:
        objective = str(weapon.get("ammo_scoreboard") or "").strip()
        if not objective:
            return
        try:
            ammo = max(0, int(weapon.get("default_ammo") or 0))
        except (TypeError, ValueError):
            return
        cmd = f"scoreboard players set {format_player_name(player_name)} {objective} {ammo}"
        self.server.dispatch_command(self.server.command_sender, cmd)

    def _apply_weapon_ammo(self, player: Player, weapon: Dict[str, Any]) -> None:
        self._set_weapon_ammo(player.name, weapon)

    def _apply_owned_weapon_ammo(self, player: Player, ps: Any) -> None:
        if self.config_store is None:
            return
        weapons = self.config_store.weapons
        for wid in (ps.primary_id, ps.secondary_id):
            if not wid:
                continue
            weapon = weapons.get(wid)
            if weapon:
                self._apply_weapon_ammo(player, weapon)

    def _restore_player_loadout(self, player: Player, lobby: Lobby, *, gadgets: bool = True) -> None:
        if self.config_store is None:
            return
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        layout = self.config_store.layout()
        reserved = int(layout.get("reserved", 0))
        weapons = self.config_store.weapons

        def give_owned(wid: Optional[str], wtype: str, slot_index: int = 0) -> None:
            if not wid or wid not in weapons:
                return
            weapon = weapons[wid]
            if wtype == "armor":
                apply_armor_extras(player, weapon.get("extras") or {}, int(weapon.get("data") or 0))
                return
            start, end = slot_range(layout, wtype)
            if end <= start:
                return
            slot = start + slot_index
            if slot >= end:
                return
            set_slot_item(
                player,
                slot,
                weapon["item"],
                int(weapon.get("amount") or 1),
                int(weapon.get("data") or 0),
            )
            for extra_id, extra_count in (weapon.get("extras") or {}).items():
                give_to_end_slots(player, extra_id, extra_count, reserved, 0)

        give_owned(ps.primary_id, "primary")
        give_owned(ps.secondary_id, "secondary")
        give_owned(ps.armor_id, "armor")
        if gadgets:
            for idx, gid in enumerate(ps.gadgets):
                if gid:
                    give_owned(gid, "gadget", idx)
        self._give_arc_coin(player)

    def _hand_item_id(self, player: Player) -> str:
        inv = getattr(player, "inventory", None)
        if inv is None:
            return ""
        hand = getattr(inv, "item_in_main_hand", None) or getattr(inv, "item_in_hand", None)
        if hand is None:
            return ""
        item_type = getattr(hand, "type", None)
        ident = getattr(item_type, "id", None)
        if ident:
            return str(ident)
        return str(item_type or "")

    def _player_xuid(self, player: Optional[Player]) -> str:
        if player is None:
            return ""
        for attr in ("xuid", "uuid"):
            val = getattr(player, attr, None)
            if val:
                return str(val)
        return ""

    def _resolve_kill_weapon_id(self, killer: Player, ps: Any) -> Optional[str]:
        if self.config_store is None:
            return None
        held = self._hand_item_id(killer)
        weapons = self.config_store.weapons
        owned: List[str] = []
        if ps is not None:
            for wid in (ps.primary_id, ps.secondary_id, *(ps.gadgets or [])):
                if wid:
                    owned.append(str(wid))
        if held:
            for wid in owned:
                w = weapons.get(wid)
                if w and str(w.get("item") or "") == held:
                    return wid
            for wid, w in weapons.items():
                if str(w.get("item") or "") == held:
                    return wid
        if owned:
            return owned[0]
        return None

    def _record_career_death(self, name: str) -> None:
        if self.career_store is None:
            return
        player = self._get_player(name)
        try:
            self.career_store.record_death(name, xuid=self._player_xuid(player))
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] career death {name}: {e}")

    def _record_career_combat(
        self,
        killer_name: str,
        victim_name: str,
        *,
        weapon_id: Optional[str] = None,
        friendly: bool = False,
    ) -> None:
        if self.career_store is None:
            return
        killer = self._get_player(killer_name)
        victim = self._get_player(victim_name)
        try:
            # 友军误杀：不记杀手击杀，也不记受害者死亡（避免无端 KD 被误伤）
            if friendly:
                return
            self.career_store.record_death(victim_name, xuid=self._player_xuid(victim))
            stats = self.career_store.record_kill(
                killer_name,
                weapon_id=weapon_id,
                xuid=self._player_xuid(killer),
            )
            if killer is not None:
                self._sync_kd_titles(killer, stats.kd)
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] career combat: {e}")

    def _record_career_match(self, name: str, *, won: bool, mvp: bool = False) -> None:
        if self.career_store is None:
            return
        player = self._get_player(name)
        try:
            stats = self.career_store.record_match_end(
                name, won=won, mvp=mvp, xuid=self._player_xuid(player)
            )
            if player is not None:
                self._sync_kd_titles(player, stats.kd)
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] career match {name}: {e}")

    def _ensure_kd_title_definitions(self) -> None:
        try:
            core = self.server.plugin_manager.get_plugin("arc_core")
        except Exception:
            core = None
        if core is None or not hasattr(core, "api_ensure_title_definition"):
            return
        desc = self._t("CAREER_TITLE_DESC")
        for _threshold, rarity, title in KD_TITLE_TIERS:
            try:
                core.api_ensure_title_definition(title, rarity, desc, 0.0, [])
            except Exception as e:
                self._safe_log("warning", f"[ARCShooterGame] ensure title {title}/{rarity}: {e}")

    def _sync_kd_titles(self, player: Player, kd: float) -> None:
        try:
            core = self.server.plugin_manager.get_plugin("arc_core")
        except Exception:
            core = None
        if core is None:
            return
        unlocked = titles_unlocked_by_kd(kd)
        if not unlocked:
            return
        for rarity, title in unlocked:
            try:
                if hasattr(core, "api_ensure_title_definition"):
                    core.api_ensure_title_definition(
                        title, rarity, self._t("CAREER_TITLE_DESC"), 0.0, []
                    )
                if hasattr(core, "api_unlock_title"):
                    core.api_unlock_title(player, title, rarity)
            except Exception as e:
                self._safe_log("warning", f"[ARCShooterGame] unlock title {title}: {e}")

    def _weapon_display_name(self, weapon_id: str) -> str:
        if self.config_store is None:
            return weapon_id
        w = self.config_store.weapons.get(weapon_id)
        if w:
            return str(w.get("display_name") or weapon_id)
        return weapon_id

    def _rarity_color(self, rarity: str) -> str:
        return {
            "普通": "§7",
            "稀有": "§9",
            "史诗": "§5",
            "传奇": "§6",
            "神话": "§c",
        }.get(str(rarity), "§f")

    def _notify(self, player: Player, message: str) -> None:
        player.send_message(message)
        if hasattr(player, "send_tip"):
            try:
                player.send_tip(message)
            except Exception:
                pass

    def _send_title(
        self,
        player: Player,
        title: str,
        subtitle: str = "",
        *,
        fade_in: int = 10,
        stay: int = 70,
        fade_out: int = 20,
    ) -> None:
        if not hasattr(player, "send_title"):
            if title or subtitle:
                player.send_message(" ".join(x for x in (title, subtitle) if x))
            return
        try:
            player.send_title(str(title or ""), str(subtitle or ""), fade_in, stay, fade_out)
        except Exception:
            try:
                player.send_title(str(title or ""), str(subtitle or ""))
            except Exception:
                if title or subtitle:
                    player.send_message(" ".join(x for x in (title, subtitle) if x))

    def _send_toast(self, player: Player, title: str, content: str = "") -> None:
        title_s = str(title or "").strip() or self._t("MATCH_RESULT_TOAST_TITLE")
        content_s = str(content or "")
        if hasattr(player, "send_toast"):
            try:
                player.send_toast(title_s, content_s)
                return
            except Exception:
                pass
        player.send_message(f"[{title_s}] {content_s}".rstrip())

    def _send_kill_toast(self, player: Player, victim_name: str) -> None:
        # 基岩字形 \uE109 = 剑（与弧光核心 bedrock_glyphs.SWORD 一致）
        sword = "\uE109"
        title = self._t("KILL_TOAST_TITLE")
        if sword not in title:
            title = f"{sword} {title}".strip()
        self._send_toast(player, title, self._t("KILL_TOAST_CONTENT").format(victim_name))

    def _credit_assists_and_tk(
        self,
        lobby: Lobby,
        victim_name: str,
        killer_name: Optional[str],
    ) -> None:
        victim_ps = lobby.players.get(victim_name)
        if victim_ps is None:
            return
        window = 3.0
        if self.config_store is not None:
            window = self.config_store.assist_window_seconds()
        team_of = {name: p.team for name, p in lobby.players.items()}
        assists, tks = collect_assist_and_tk(
            self._damage_log.get(victim_name) or {},
            now=time.time(),
            window=window,
            killer_name=killer_name,
            victim_team=victim_ps.team,
            team_of=team_of,
        )
        for name in assists:
            lobby.apply_assist(name)
            helper = self._get_player(name)
            if helper is not None:
                helper.send_message(self._t("ASSIST_CREDIT").format(victim_name))
        for name in tks:
            lobby.apply_team_kill_credit(name)
        # 击杀者本人的友军击杀已在 apply_player_kill 计入 team_kills

    def _title_lobby(
        self,
        lobby: Lobby,
        title: str,
        subtitle: str = "",
        *,
        fade_in: int = 10,
        stay: int = 70,
        fade_out: int = 20,
    ) -> None:
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is None:
                continue
            self._send_title(member, title, subtitle, fade_in=fade_in, stay=stay, fade_out=fade_out)

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

    def _end_match(self, lobby: Lobby, winner: Optional[str], *, timed_out: bool = False) -> None:
        rewards, mvp_names = self._distribute_match_rewards(lobby, winner)
        result_content = self._match_result_content(
            lobby, winner, timed_out=timed_out, rewards=rewards, mvp_names=mvp_names
        )
        still = [ps.name for ps in lobby.online_players()]
        participants = {ps.name for ps in lobby.result_rows()}
        target_names = set(still) | participants
        team_by_name = {ps.name: ps.team for ps in lobby.result_rows()}
        a_name = lobby.team_name(TEAM_A)
        b_name = lobby.team_name(TEAM_B)
        score_a, score_b = lobby.score_a, lobby.score_b
        for ps in lobby.result_rows():
            won = bool(winner) and ps.team == winner
            self._record_career_match(ps.name, won=won, mvp=ps.name in mvp_names)
        for name in still:
            self.player_to_lobby.pop(name, None)
            member = self._get_player(name)
            if member:
                self._clear_buy_freeze(name)
                self._clear_match_effects(name)
                self._restore_player(member, after_match=True)
                self._restore_name_tag(member)
        for name in target_names:
            member = self._get_player(name)
            if member is None:
                continue
            self._send_match_result_toast(
                member,
                team_by_name.get(name),
                winner,
                a_name,
                score_a,
                score_b,
                b_name,
            )
            self._schedule_match_result_form(member, result_content)
        self.lobbies.pop(lobby.lobby_id, None)

    def _send_match_result_toast(
        self,
        player: Player,
        team: Optional[str],
        winner: Optional[str],
        a_name: str,
        score_a: int,
        score_b: int,
        b_name: str,
    ) -> None:
        title = self._t("MATCH_RESULT_TOAST_TITLE")
        a_disp = self._colored_label(a_name, TEAM_A)
        b_disp = self._colored_label(b_name, TEAM_B)
        if winner is None or team is None:
            content = self._t("MATCH_RESULT_TOAST_DRAW").format(a_disp, score_a, b_disp, score_b)
        elif team == winner:
            content = self._t("MATCH_RESULT_TOAST_WIN").format(a_disp, score_a, b_disp, score_b)
        else:
            content = self._t("MATCH_RESULT_TOAST_LOSE").format(a_disp, score_a, b_disp, score_b)
        self._send_toast(player, title, content)

    def _get_arc_core(self):
        try:
            return self.server.plugin_manager.get_plugin("arc_core")
        except Exception:
            return None

    def _distribute_match_rewards(
        self, lobby: Lobby, winner: Optional[str]
    ) -> Tuple[Dict[str, Dict[str, int]], set]:
        rewards: Dict[str, Dict[str, int]] = {}
        mvp_names: set = set()
        if self.config_store is None:
            return rewards, mvp_names
        money_per_kill = self.config_store.match_money_per_kill()
        win_bonus = self.config_store.match_win_bonus()
        mvp_bonus = self.config_store.match_mvp_bonus()
        contrib_mult = self.config_store.win_guild_contribution_per_kd()
        assist_weight = self.config_store.match_assist_weight()
        tk_weight = self.config_store.match_tk_weight()
        if money_per_kill <= 0 and win_bonus <= 0 and contrib_mult <= 0 and mvp_bonus <= 0:
            return rewards, mvp_names
        core = self._get_arc_core()
        if core is None:
            self._safe_log("warning", "[ARCShooterGame] arc_core not loaded; skip match rewards")
            return rewards, mvp_names

        rows = lobby.result_rows()
        for team_id in (TEAM_A, TEAM_B):
            members = [p for p in rows if p.team == team_id]
            mvp = pick_team_mvp(
                members, assist_weight=assist_weight, tk_weight=tk_weight
            )
            if mvp is not None:
                mvp_names.add(mvp.name)

        for ps in rows:
            won = bool(winner) and ps.team == winner
            money = calc_match_money(
                ps.kills,
                ps.deaths,
                ps.assists,
                ps.team_kills,
                money_per_kill=money_per_kill,
                win_bonus=win_bonus,
                won=won,
                assist_weight=assist_weight,
                tk_weight=tk_weight,
            )
            is_mvp = ps.name in mvp_names
            if is_mvp and mvp_bonus > 0:
                money += mvp_bonus
            perf = max(
                0.0,
                match_performance_score(
                    ps.kills,
                    ps.assists,
                    ps.team_kills,
                    assist_weight=assist_weight,
                    tk_weight=tk_weight,
                ),
            )
            contribution = (
                int(round(perf * contrib_mult))
                if won and contrib_mult > 0 and perf > 0
                else 0
            )
            entry = {"money": 0, "contribution": 0, "mvp": 1 if is_mvp else 0}
            if money > 0:
                try:
                    if core.api_change_player_money(ps.name, float(money), notify=True):
                        entry["money"] = money
                except Exception as e:
                    self._safe_log(
                        "warning",
                        f"[ARCShooterGame] match money reward for {ps.name}: {e}",
                    )
            if contribution > 0:
                try:
                    result = core.api_add_guild_contribution(ps.name, int(contribution))
                    if result.get("ok"):
                        entry["contribution"] = contribution
                    elif result.get("error") != "GUILD_NOT_IN_GUILD":
                        self._safe_log(
                            "warning",
                            f"[ARCShooterGame] guild contribution for {ps.name}: {result.get('error')}",
                        )
                except Exception as e:
                    self._safe_log(
                        "warning",
                        f"[ARCShooterGame] match guild contribution for {ps.name}: {e}",
                    )
            if entry["money"] > 0 or entry["contribution"] > 0 or is_mvp:
                rewards[ps.name] = entry
        return rewards, mvp_names

    def _match_result_content(
        self,
        lobby: Lobby,
        winner: Optional[str],
        *,
        timed_out: bool = False,
        rewards: Optional[Dict[str, Dict[str, int]]] = None,
        mvp_names: Optional[set] = None,
    ) -> str:
        a_name = self._colored_team_name(lobby, TEAM_A)
        b_name = self._colored_team_name(lobby, TEAM_B)
        mvps = mvp_names or set()
        parts: List[str] = []
        if timed_out:
            parts.append(self._t("MATCH_END_TIME_NOTE"))
        parts.append(self._t("MATCH_END_SCORE").format(a_name, lobby.score_a, b_name, lobby.score_b))
        if winner:
            parts.append(self._t("MATCH_END_WINNER").format(self._colored_team_name(lobby, winner)))
        else:
            parts.append(self._t("MATCH_END_DRAW"))
        parts.append("")
        rows = lobby.result_rows()
        for team_id in (TEAM_A, TEAM_B):
            parts.append(
                self._t("MATCH_END_STATS_TEAM").format(self._colored_team_name(lobby, team_id))
            )
            members = sorted(
                [p for p in rows if p.team == team_id],
                key=lambda p: (-int(p.kills), -int(p.assists), int(p.deaths), p.name),
            )
            if not members:
                parts.append(self._t("NO_PLAYER"))
            for ps in members:
                label = self._colored_label(ps.name, ps.team)
                if ps.name in mvps:
                    label = self._t("MATCH_END_MVP_TAG") + label
                parts.append(
                    self._t("MATCH_END_STATS_PLAYER").format(
                        label,
                        ps.kills,
                        ps.deaths,
                        ps.assists,
                        ps.team_kills,
                    )
                )
        reward_map = rewards or {}
        parts.append("")
        parts.append(self._t("MATCH_END_REWARDS_HEADER"))
        for ps in rows:
            colored = self._colored_label(ps.name, ps.team)
            if ps.name in mvps:
                colored = self._t("MATCH_END_MVP_TAG") + colored
            entry = reward_map.get(ps.name)
            if entry:
                money = int(entry.get("money", 0))
                contribution = int(entry.get("contribution", 0))
                if money > 0 and contribution > 0:
                    parts.append(
                        self._t("MATCH_END_REWARD_BOTH").format(colored, money, contribution)
                    )
                elif money > 0:
                    parts.append(self._t("MATCH_END_REWARD_MONEY").format(colored, money))
                elif contribution > 0:
                    parts.append(self._t("MATCH_END_REWARD_CONTRIB").format(colored, contribution))
                else:
                    parts.append(self._t("MATCH_END_REWARD_NONE").format(colored))
            else:
                parts.append(self._t("MATCH_END_REWARD_NONE").format(colored))
        return "\n".join(parts)

    def _show_match_result_form(self, player: Player, content: str) -> None:
        try:
            form = ActionForm(title=self._t("MATCH_END_TITLE"), content=content)
            form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] match result form: {e}\n{traceback.format_exc()}")
            for line in content.splitlines():
                if line.strip():
                    player.send_message(line)

    def _schedule_match_result_form(self, player: Player, content: str, delay: int = 5) -> None:
        try:
            self.server.scheduler.run_task(
                self,
                lambda p=player, c=content: self._show_match_result_form(p, c),
                delay=delay,
            )
        except Exception:
            self._show_match_result_form(player, content)

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

    def _dispatch_effect(
        self,
        player_name: str,
        effect: str,
        seconds: int,
        amplifier: int = 0,
        *,
        hide_particles: bool = True,
    ) -> None:
        hide = "true" if hide_particles else "false"
        self.server.dispatch_command(
            self.server.command_sender,
            (
                f"effect {format_player_name(player_name)} {effect} "
                f"{max(0, int(seconds))} {max(0, int(amplifier))} {hide}"
            ),
        )

    def _clear_effects(self, player_name: str) -> None:
        self.server.dispatch_command(
            self.server.command_sender,
            f"effect {format_player_name(player_name)} clear",
        )

    def _set_movement_speed(self, player_name: str, speed: float) -> None:
        try:
            self.server.dispatch_command(
                self.server.command_sender,
                (
                    f"attribute {format_player_name(player_name)} "
                    f"minecraft:movement base set {float(speed)}"
                ),
            )
        except Exception as e:
            self._safe_log(
                "warning",
                f"[ARCShooterGame] set movement speed for {player_name}: {e}",
            )

    def _is_spawn_protected(self, player_name: str) -> bool:
        until = self._spawn_protect_until.get(player_name)
        if until is None:
            return False
        if time.time() >= until:
            self._spawn_protect_until.pop(player_name, None)
            return False
        return True

    def _apply_spawn_protect(self, player: Player) -> None:
        # 仅用 ActorDamageEvent 取消伤害实现无敌，不加隐身/抗性效果
        self._spawn_protect_until[player.name] = time.time() + SPAWN_PROTECT_SECONDS
        lobby = self._lobby_of(player.name)
        if lobby is not None:
            self._apply_team_name_tag(player, lobby)

    def _apply_match_buffs(self, player: Player) -> None:
        self._dispatch_effect(player.name, "speed", MATCH_BUFF_DURATION_SECONDS, 0)
        self._dispatch_effect(player.name, "jump_boost", MATCH_BUFF_DURATION_SECONDS, 0)

    def _clear_match_effects(self, player_name: str) -> None:
        self._spawn_protect_until.pop(player_name, None)
        self._clear_effects(player_name)

    def _set_buy_freeze(self, player: Player) -> None:
        self._buy_frozen.add(player.name)
        self._set_movement_speed(player.name, 0.0)

    def _clear_buy_freeze(self, player_name: str) -> None:
        if player_name not in self._buy_frozen:
            return
        self._buy_frozen.discard(player_name)
        self._set_movement_speed(player_name, DEFAULT_MOVEMENT_SPEED)

    def _enforce_buy_freeze(self, lobby: Lobby) -> None:
        for ps in lobby.online_players():
            if ps.name in self._buy_frozen:
                continue
            player = self._get_player(ps.name)
            if player is not None:
                self._set_buy_freeze(player)

    def _player_is_sneaking(self, player: Player) -> bool:
        for attr in ("is_sneaking", "sneaking", "is_crouching"):
            val = getattr(player, attr, None)
            if isinstance(val, bool):
                return val
            if callable(val):
                try:
                    return bool(val())
                except Exception:
                    continue
        return False

    def _update_sneak_name_tags(self, lobby: Lobby) -> None:
        for ps in lobby.online_players():
            player = self._get_player(ps.name)
            if player is None:
                continue
            if self._player_is_sneaking(player):
                try:
                    if str(getattr(player, "name_tag", "") or "") != "":
                        player.name_tag = ""
                except Exception as e:
                    self._safe_log(
                        "warning",
                        f"[ARCShooterGame] clear sneak name_tag for {player.name}: {e}",
                    )
            else:
                self._apply_team_name_tag(player, lobby)

    def _colored_label(self, text: str, team_id: Optional[str]) -> str:
        color = TEAM_NAME_COLOR.get(team_id or "", "§f")
        return f"{color}{text}"

    def _colored_team_name(self, lobby: Lobby, team_id: str) -> str:
        return self._colored_label(lobby.team_name(team_id), team_id)

    def _broadcast(self, lobby: Lobby, message: str) -> None:
        for ps in lobby.online_players():
            player = self._get_player(ps.name)
            if player:
                player.send_message(message)

    def _broadcast_server(self, message: str) -> None:
        for player in self.server.online_players:
            player.send_message(message)

    def _notify_lobby_members_joined(
        self, lobby: Lobby, joiner_name: str, count: int, max_players: int
    ) -> None:
        for ps in lobby.online_players():
            if ps.name == joiner_name:
                continue
            member = self._get_player(ps.name)
            if member is None:
                continue
            if ps.name == lobby.admin:
                self._notify(
                    member,
                    self._t("LOBBY_PLAYER_JOINED_ADMIN").format(joiner_name, count, max_players),
                )
            else:
                self._notify(
                    member,
                    self._t("LOBBY_PLAYER_JOINED").format(joiner_name, count, max_players),
                )

    def _notify_lobby_members_left(self, lobby: Lobby, leaver_name: str) -> None:
        count = lobby.player_count()
        max_players = lobby.max_per_team * 2
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is None:
                continue
            if ps.name == lobby.admin:
                self._notify(
                    member,
                    self._t("LOBBY_PLAYER_LEFT_ADMIN").format(leaver_name, count, max_players),
                )
            else:
                self._notify(
                    member,
                    self._t("LOBBY_PLAYER_LEFT").format(leaver_name, count, max_players),
                )
        self._refresh_lobby_menus(lobby)

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
        if lobby.state == STATE_COUNTDOWN:
            return self._t("LOBBY_STATUS_COUNTDOWN")
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
        if lobby.prefer_random_map:
            return self._t("LOBBY_RANDOM_MAP")
        return self._t("LOBBY_LIST_NO_MAP")

    def _lobby_mode_label(self, lobby: Lobby) -> str:
        if lobby.mode:
            return self._mode_label(lobby.mode)
        if lobby.prefer_random_mode:
            return self._t("LOBBY_RANDOM_MODE")
        return self._t("LOBBY_LIST_NO_MODE")

    def _team_name_tag(self, player_name: str, team_id: str, *, invincible: bool = False) -> str:
        color = TEAM_NAME_COLOR.get(team_id, "§f")
        name_line = f"{color}{player_name}"
        if not invincible:
            return name_line
        prefix = self._t("NAME_TAG_INVINCIBLE")
        return f"{prefix}\n{name_line}"

    def _apply_team_name_tag(self, player: Player, lobby: Lobby) -> None:
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        if player.name not in self._saved_name_tags:
            self._saved_name_tags[player.name] = str(getattr(player, "name_tag", "") or "")
        try:
            player.name_tag = self._team_name_tag(
                player.name,
                ps.team,
                invincible=self._is_spawn_protected(player.name),
            )
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] set name_tag for {player.name}: {e}")

    def _restore_name_tag(self, player: Player) -> None:
        saved = self._saved_name_tags.pop(player.name, None)
        try:
            core = self.server.plugin_manager.get_plugin("arc_core")
            if core is not None and hasattr(core, "_update_player_name_tag"):
                core._update_player_name_tag(player)
                return
        except Exception as e:
            self._safe_log("warning", f"[ARCShooterGame] restore name_tag via arc_core for {player.name}: {e}")
        if saved is not None:
            try:
                player.name_tag = saved
            except Exception:
                pass

    def _apply_lobby_name_tags(self, lobby: Lobby) -> None:
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is not None:
                self._apply_team_name_tag(member, lobby)

    def _refresh_lobby_menus(self, lobby: Lobby, delay: int = 5) -> None:
        if lobby.state != STATE_LOBBY:
            return
        for ps in lobby.online_players():
            member = self._get_player(ps.name)
            if member is not None:
                self._schedule_lobby_menu(member, lobby, delay=delay)

    def _reason_status_text(self, reason: str) -> str:
        key_map = {
            "reason_missing_region": "MAP_STATUS_MISSING_REGION",
            "reason_no_modes": "MAP_STATUS_NO_MODES",
            "reason_missing_spawn_a": "MAP_STATUS_MISSING_SPAWN_A",
            "reason_missing_spawn_b": "MAP_STATUS_MISSING_SPAWN_B",
            "reason_unimplemented": "MAP_STATUS_UNIMPLEMENTED",
            "reason_mode_not_found": "MAP_STATUS_MODE_NOT_FOUND",
        }
        return self._t(key_map.get(reason, "MAP_STATUS_MODE_NOT_FOUND"))

    def _map_status_label(self, map_cfg: Dict[str, Any]) -> str:
        if playable_modes(map_cfg):
            return self._t("MAP_STATUS_READY")
        reasons = map_incomplete_reasons(map_cfg)
        if not reasons:
            return self._t("MAP_STATUS_READY")
        return self._reason_status_text(reasons[0])

    def _mode_button_label(self, map_cfg: Dict[str, Any], mode: str) -> str:
        mode_cfg = get_mode_config(map_cfg, mode)
        minutes = int(mode_cfg.get("match_time_minutes") or 5) if mode_cfg else 5
        label = self._mode_label(mode)
        if mode_playable(map_cfg, mode):
            return self._t("MODE_BUTTON_READY").format(label, minutes)
        reasons = mode_incomplete_reasons(map_cfg, mode)
        issue = self._reason_status_text(reasons[0]) if reasons else self._t("MAP_STATUS_MODE_NOT_FOUND")
        return self._t("MODE_BUTTON_ISSUE").format(label, issue)

    def _format_map_pos(self, point: Any) -> str:
        if not point or not isinstance(point, dict):
            return self._t("MAP_POS_UNSET")
        try:
            return self._t("MAP_POS_FMT").format(float(point["x"]), float(point["y"]), float(point["z"]))
        except (KeyError, TypeError, ValueError):
            return self._t("MAP_POS_UNSET")

    def _map_mode_status_lines(self, map_cfg: Dict[str, Any]) -> str:
        lines: List[str] = []
        for mode_cfg in map_cfg.get("modes") or []:
            mode = str(mode_cfg.get("mode") or "")
            label = self._mode_label(mode)
            if mode_playable(map_cfg, mode):
                minutes = int(mode_cfg.get("match_time_minutes") or 5)
                lines.append(self._t("MAP_MODE_LINE_READY").format(label, minutes))
            else:
                reasons = mode_incomplete_reasons(map_cfg, mode)
                issue = self._reason_status_text(reasons[0]) if reasons else self._t("MAP_STATUS_MODE_NOT_FOUND")
                lines.append(self._t("MAP_MODE_LINE").format(label, issue))
        return "\n".join(lines) if lines else self._t("MAP_MODES_NONE")

    def _lobby_hint_text(self, lobby: Lobby) -> str:
        if lobby.prefer_random_map:
            return self._t("LOBBY_CONTENT_HINT").format(self._t("LOBBY_HINT_RANDOM"))
        if not lobby.map_id:
            return self._t("LOBBY_CONTENT_HINT").format(self._t("LOBBY_HINT_NEED_MAP"))
        if not lobby.mode:
            return self._t("LOBBY_CONTENT_HINT").format(self._t("LOBBY_HINT_NEED_MODE"))
        return self._t("LOBBY_CONTENT_HINT").format(self._t("LOBBY_HINT_READY"))

    def _map_select_button_label(self, map_cfg: Dict[str, Any]) -> str:
        name = str(map_cfg.get("display_name") or map_cfg["id"])
        modes = playable_modes(map_cfg)
        if len(modes) == 1:
            mode_cfg = get_mode_config(map_cfg, modes[0])
            minutes = int(mode_cfg.get("match_time_minutes") or 5) if mode_cfg else 5
            return self._t("MAP_SELECT_BUTTON_DETAIL").format(name, self._mode_label(modes[0]), minutes)
        if len(modes) > 1:
            return self._t("MAP_SELECT_BUTTON_MULTI").format(name, len(modes))
        return self._t("MAP_SELECT_BUTTON").format(name)

    # ---------- shop / weapon acquire ----------

    def _acquire_strategy(self, lobby: Lobby) -> WeaponAcquireStrategy:
        return resolve_acquire_strategy(lobby.map_cfg)

    def _slot_capacities(self) -> SlotCapacities:
        assert self.config_store is not None
        return SlotCapacities.from_layout(self.config_store.layout())

    def _apply_purchase_items(
        self,
        player: Player,
        weapon: Dict[str, Any],
        *,
        old_id: Optional[str],
        slot_index: int,
    ) -> None:
        assert self.config_store is not None
        layout = self.config_store.layout()
        wtype = str(weapon.get("type") or "")
        if wtype == "armor":
            if old_id and old_id in self.config_store.weapons:
                remove_armor_extras(player, self.config_store.weapons[old_id].get("extras") or {})
            apply_armor_extras(player, weapon.get("extras") or {}, int(weapon.get("data") or 0))
            return
        if old_id and old_id in self.config_store.weapons:
            old = self.config_store.weapons[old_id]
            for extra_id, extra_count in (old.get("extras") or {}).items():
                remove_item_count(player, extra_id, extra_count)
        start, end = slot_range(layout, wtype)
        if end <= start:
            return
        slot = start + slot_index
        if slot >= end:
            return
        set_slot_item(
            player,
            slot,
            weapon["item"],
            int(weapon.get("amount") or 1),
            int(weapon.get("data") or 0),
        )
        reserved = int(layout["reserved"])
        for extra_id, extra_count in (weapon.get("extras") or {}).items():
            give_to_end_slots(player, extra_id, extra_count, reserved, 0)
        self._apply_weapon_ammo(player, weapon)

    def _buy_weapon(self, player: Player, weapon_id: str) -> None:
        assert self.config_store is not None
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        strategy = self._acquire_strategy(lobby)
        if not strategy.uses_shop:
            player.send_message(self._t("SHOP_DISABLED_MODE"))
            return
        weapon = self.config_store.weapons.get(weapon_id)
        if weapon is None:
            player.send_message(self._t("BUY_FAIL_UNKNOWN"))
            return
        ps = lobby.players.get(player.name)
        if ps is None:
            return
        outcome = strategy.purchase(
            ps,
            weapon,
            self.config_store.weapons,
            self._slot_capacities(),
        )
        wtype = str(weapon.get("type") or "")
        if not outcome.ok:
            if outcome.reason == REASON_ALREADY_OWNED:
                player.send_message(self._t("BUY_ALREADY_OWNED").format(weapon["display_name"]))
            elif outcome.reason == REASON_NO_SLOT:
                player.send_message(self._t("SHOP_NO_SLOT"))
            elif outcome.reason == REASON_INSUFFICIENT:
                player.send_message(self._t("BUY_FAIL_POINTS").format(outcome.pay, ps.points))
            elif outcome.reason == REASON_UNKNOWN:
                player.send_message(self._t("BUY_FAIL_UNKNOWN"))
            elif outcome.reason == REASON_DISABLED:
                player.send_message(self._t("SHOP_DISABLED_MODE"))
            self._show_shop_category(player, wtype)
            return
        self._apply_purchase_items(
            player,
            weapon,
            old_id=outcome.old_id,
            slot_index=outcome.slot_index,
        )
        if outcome.credit > 0:
            player.send_message(
                self._t("BUY_OK_UPGRADE").format(weapon["display_name"], outcome.pay, outcome.points_left)
            )
        else:
            player.send_message(self._t("BUY_OK").format(weapon["display_name"], outcome.points_left))
        self._show_shop_category(player, wtype)

    # ---------- ui ----------

    def _show_root_menu(self, player: Player) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is not None:
            if lobby.state in (STATE_LOBBY, STATE_COUNTDOWN):
                self._show_lobby_menu(player, lobby)
            else:
                self._show_match_menu(player, lobby)
            return
        try:
            form = ActionForm(title=self._t("MENU_TITLE"), content=self._t("MENU_CONTENT"))
            form.add_button(self._t("BTN_LOBBY_LIST"), on_click=lambda sender: self._show_lobby_list(sender))
            form.add_button(self._t("BTN_PROFILE"), on_click=lambda sender: self._show_profile(sender))
            if self._is_op(player):
                form.add_button(self._t("BTN_CONFIG_MAPS"), on_click=lambda sender: self._show_config_maps(sender))
            form.add_button(self._t("CLOSE"), on_click=lambda sender: None)
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] root menu: {e}\n{traceback.format_exc()}")
            player.send_message(self._t("PANEL_ERROR"))

    def _profile_content(self, stats) -> str:
        rarity = stats.title_rarity
        title = stats.title_name
        color = self._rarity_color(rarity)
        lines = [
            self._t("PROFILE_LINE_KD").format(stats.kills, stats.deaths, f"{stats.kd:.2f}"),
            self._t("PROFILE_LINE_MATCHES").format(stats.matches, stats.wins, stats.mvps),
            self._t("PROFILE_LINE_TITLE").format(color, rarity, title),
            "",
            self._t("PROFILE_WEAPON_HEADER"),
        ]
        if not stats.weapon_kills:
            lines.append(self._t("PROFILE_WEAPON_EMPTY"))
        else:
            for wid, kills in list(stats.weapon_kills.items())[:12]:
                lines.append(
                    self._t("PROFILE_WEAPON_LINE").format(
                        self._weapon_display_name(wid), kills
                    )
                )
        return "\n".join(lines)

    def _show_profile(self, player: Player) -> None:
        try:
            if self.career_store is None:
                player.send_message(self._t("PROFILE_UNAVAILABLE"))
                return
            stats = self.career_store.get(player.name)
            # 打开面板时同步头衔（含见习枪手）
            self._sync_kd_titles(player, stats.kd)
            form = ActionForm(
                title=self._t("PROFILE_TITLE").format(player.name),
                content=self._profile_content(stats),
            )
            form.add_button(self._t("BACK"), on_click=lambda sender: self._show_root_menu(sender))
            player.send_form(form)
        except Exception as e:
            self._safe_log("error", f"[ARCShooterGame] profile: {e}\n{traceback.format_exc()}")
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
            count = lobby.player_count()
            max_players = lobby.max_per_team * 2
            player_list = "、".join(ps.name for ps in lobby.online_players()) or self._t("NO_PLAYER")
            content = (
                self._t("LOBBY_PLAYER_COUNT").format(count, max_players)
                + "\n"
                + self._t("LOBBY_PLAYER_LIST").format(player_list)
                + "\n\n"
                + self._lobby_hint_text(lobby)
                + "\n\n"
                + self._t("LOBBY_CONTENT").format(
                    self._lobby_map_label(lobby),
                    self._lobby_mode_label(lobby),
                    lobby.admin or "-",
                    self._lobby_remaining_text(lobby),
                    lobby.target_score if lobby.map_cfg else "-",
                    lobby.match_time_minutes if lobby.map_cfg else "-",
                    lobby.max_per_team if lobby.map_cfg else "-",
                    self._team_block(lobby, TEAM_A),
                    self._team_block(lobby, TEAM_B),
                )
            )
            form = ActionForm(title=self._t("LOBBY_TITLE"), content=content)
            is_admin = lobby.admin == player.name
            if is_admin and lobby.state == STATE_LOBBY:
                if lobby.prefer_random_map:
                    map_mode_btn = self._t("BTN_SELECT_MAP_MODE")
                else:
                    map_mode_btn = self._t("BTN_CHANGE_MAP_MODE")
                form.add_button(
                    map_mode_btn,
                    on_click=lambda sender, lb=lobby: self._show_map_select(sender, lb),
                )
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
        form = ActionForm(title=self._t("MAP_SELECT_TITLE"), content=self._t("MAP_SELECT_CONTENT"))
        form.add_button(
            self._t("BTN_RANDOM_MAP_MODE"),
            on_click=lambda sender, lb=lobby: self._select_random_map_mode(sender, lb),
        )
        if not candidates:
            form = ActionForm(title=self._t("MAP_SELECT_TITLE"), content=self._t("MAP_SELECT_EMPTY"))
            form.add_button(
                self._t("BTN_RANDOM_MAP_MODE"),
                on_click=lambda sender, lb=lobby: self._select_random_map_mode(sender, lb),
            )
            form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
            player.send_form(form)
            return
        for map_cfg in candidates:
            label = self._map_select_button_label(map_cfg)
            mid = map_cfg["id"]
            form.add_button(label, on_click=lambda sender, lb=lobby, m=mid: self._select_map(sender, lb, m))
        form.add_button(self._t("BACK"), on_click=lambda sender, lb=lobby: self._show_lobby_menu(sender, lb))
        player.send_form(form)

    def _map_display_name(self, map_id: Optional[str]) -> str:
        if not map_id or self.config_store is None:
            return str(map_id or "?")
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg:
            return str(map_cfg.get("display_name") or map_id)
        return str(map_id)

    def _notify_map_taken_and_reselect(self, player: Player, lobby: Lobby, map_id: str) -> None:
        """选图瞬间被占用：提示并让房主重新打开选图。"""
        player.send_message(self._t("MAP_SELECT_TAKEN").format(self._map_display_name(map_id)))
        # 自己仍记着这张图、但实际已被别人占用 → 清掉脏状态
        if lobby.map_id == map_id and self._map_in_use(map_id, exclude_lobby_id=lobby.lobby_id):
            lobby.set_prefer_random(map_=True, mode=True)
        self._show_map_select(player, lobby)

    def _try_claim_map(self, lobby: Lobby, map_id: str) -> Tuple[bool, Optional[Dict[str, Any]]]:
        """点击选图时再次校验占用，通过则立刻写入 map_id 占住。"""
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None or not has_region(map_cfg) or not playable_modes(map_cfg):
            return False, None
        if self._map_in_use(map_id, exclude_lobby_id=lobby.lobby_id):
            return False, map_cfg
        lobby.prefer_random_map = False
        lobby.map_id = map_id
        return True, map_cfg

    def _select_random_map_mode(self, player: Player, lobby: Lobby) -> None:
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        lobby.set_prefer_random(map_=True, mode=True)
        player.send_message(self._t("MAP_SELECT_RANDOM_OK"))
        self._show_lobby_menu(player, lobby)

    def _select_map(self, player: Player, lobby: Lobby, map_id: str) -> None:
        assert self.config_store is not None
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None or not has_region(map_cfg) or not playable_modes(map_cfg):
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_map_select(player, lobby)
            return
        # 表单生成时可能空闲，点击时再验一次（防抢选）
        if self._map_in_use(map_id, exclude_lobby_id=lobby.lobby_id):
            self._notify_map_taken_and_reselect(player, lobby, map_id)
            return
        claimed, claimed_cfg = self._try_claim_map(lobby, map_id)
        if not claimed or claimed_cfg is None:
            # 极短窗口内再次被占用
            self._notify_map_taken_and_reselect(player, lobby, map_id)
            return
        map_cfg = claimed_cfg
        modes = playable_modes(map_cfg)
        if len(modes) == 1:
            lobby.prefer_random_mode = False
            ok, _reason = lobby.set_map_and_mode(map_cfg, modes[0])
            if ok:
                player.send_message(self._t("MAP_SELECT_OK").format(map_cfg.get("display_name") or map_id))
                player.send_message(self._t("MODE_SELECT_OK").format(self._mode_label(modes[0])))
                self._show_lobby_menu(player, lobby)
                return
            # 绑定失败则释放并重选
            lobby.set_prefer_random(map_=True, mode=True)
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_map_select(player, lobby)
            return
        lobby.prefer_random_mode = True
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
        if lobby.admin != player.name or lobby.state != STATE_LOBBY:
            player.send_message(self._t("CMD_NO_PERMISSION"))
            return
        map_id = lobby.map_id or ""
        map_cfg = self.config_store.maps.get(map_id)
        if map_cfg is None:
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_lobby_menu(player, lobby)
            return
        # 选模式前再确认该图仍由本大厅占用（防止异常状态）
        if self._map_in_use(map_id, exclude_lobby_id=lobby.lobby_id):
            self._notify_map_taken_and_reselect(player, lobby, map_id)
            return
        ok, reason = lobby.set_map_and_mode(map_cfg, mode)
        if not ok:
            player.send_message(self._t("MAP_SELECT_NOT_READY"))
            self._show_mode_select(player, lobby)
            return
        lobby.prefer_random_map = False
        lobby.prefer_random_mode = False
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
            self._show_assign_menu(player, lobby)
        elif ok:
            player.send_message(self._t("ASSIGN_DONE").format(target_name, lobby.team_name(other)))
            target = self._get_player(target_name)
            if target is not None:
                self._apply_team_name_tag(target, lobby)
            self._refresh_lobby_menus(lobby)
        else:
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
            self._restore_name_tag(target)
            target.send_message(self._t("KICKED"))
            self._schedule_root_menu(target)
        admin.send_message(self._t("KICK_OK").format(target_name))
        self._notify_lobby_members_left(lobby, target_name)
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
            ps.assists,
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
        strategy = self._acquire_strategy(lobby)
        if not strategy.uses_shop:
            player.send_message(self._t("SHOP_DISABLED_MODE"))
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
        form.add_button(self._t("SHOP_ARMOR"), on_click=lambda sender: self._show_shop_category(sender, "armor"))
        form.add_button(self._t("SHOP_GADGET"), on_click=lambda sender: self._show_shop_category(sender, "gadget"))
        form.add_button(self._t("BACK"), on_click=lambda sender: self._show_root_menu(sender))
        player.send_form(form)

    def _show_shop_category(self, player: Player, weapon_type: str) -> None:
        lobby = self._lobby_of(player.name)
        if lobby is None or lobby.state not in (STATE_BUYING, STATE_PLAYING):
            player.send_message(self._t("SHOP_NOT_IN_MATCH"))
            return
        strategy = self._acquire_strategy(lobby)
        if not strategy.uses_shop:
            player.send_message(self._t("SHOP_DISABLED_MODE"))
            return
        ps = lobby.players.get(player.name)
        if ps is None or self.config_store is None:
            return
        title_map = {
            "primary": self._t("SHOP_PRIMARY"),
            "secondary": self._t("SHOP_SECONDARY"),
            "armor": self._t("SHOP_ARMOR"),
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
        owned = owned_weapon_ids(ps)
        capacities = self._slot_capacities()
        for weapon in weapons:
            owned_mark = self._t("SHOP_OWNED") if weapon["id"] in owned else ""
            quote = strategy.quote(ps, weapon, self.config_store.weapons, capacities)
            if quote.is_upgrade:
                label = self._t("SHOP_ITEM_UPGRADE").format(
                    weapon["display_name"], quote.pay, weapon["cost"], owned_mark
                )
            else:
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
            name = str(map_cfg.get("display_name") or map_cfg["id"])
            label = self._t("CONFIG_MAP_BUTTON_STATUS").format(name, self._map_status_label(map_cfg))
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
        region = map_cfg.get("region") or {}
        pos1_text = self._format_map_pos(region.get("pos1"))
        pos2_text = self._format_map_pos(region.get("pos2"))
        modes_text = self._map_mode_status_lines(map_cfg)
        content = self._t("MAP_EDIT_BODY").format(
            map_cfg.get("dimension") or "overworld",
            pos1_text,
            pos2_text,
            modes_text,
        )
        form = ActionForm(title=self._t("MAP_EDIT_TITLE").format(map_cfg.get("display_name") or map_id), content=content)
        form.add_button(self._t("BTN_SET_POS1"), on_click=lambda sender, m=map_id: self._set_map_pos(sender, m, 1))
        form.add_button(self._t("BTN_SET_POS2"), on_click=lambda sender, m=map_id: self._set_map_pos(sender, m, 2))
        for mode_cfg in map_cfg.get("modes") or []:
            mode = str(mode_cfg.get("mode") or "")
            label = self._mode_button_label(map_cfg, mode)
            form.add_button(label, on_click=lambda sender, mid=map_id, md=mode: self._show_mode_edit(sender, mid, md))
        form.add_button(self._t("BTN_ADD_MODE"), on_click=lambda sender, m=map_id: self._show_add_mode_form(sender, m))
        form.add_button(self._t("BTN_RENAME_MAP"), on_click=lambda sender, m=map_id: self._show_rename_map_form(sender, m))
        form.add_button(self._t("BTN_DELETE_MAP"), on_click=lambda sender, m=map_id: self._show_delete_map_confirm(sender, m))
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
                    "match_time_minutes": 5,
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
            self._add_mode_to_map(player, map_id, available[0])
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
        status = self._t("MODE_STATUS_READY") if mode_playable(map_cfg, mode) else self._reason_status_text(
            mode_incomplete_reasons(map_cfg, mode)[0]
            if mode_incomplete_reasons(map_cfg, mode)
            else "reason_mode_not_found"
        )
        content = self._t("MODE_EDIT_BODY").format(
            mode_cfg.get("target_score", 50),
            mode_cfg.get("max_players_per_team", 8),
            mode_cfg.get("match_time_minutes", 5),
            a_count,
            b_count,
            status,
        )
        form = ActionForm(title=self._t("MODE_EDIT_TITLE").format(self._mode_label(mode)), content=content)
        form.add_button(
            self._t("BTN_EDIT_RULES"),
            on_click=lambda sender, m=map_id, md=mode: self._show_mode_settings_form(sender, m, md),
        )
        form.add_button(
            self._t("BTN_MANAGE_SPAWN_A"),
            on_click=lambda sender, m=map_id, md=mode: self._show_spawn_edit(sender, m, md, TEAM_A),
        )
        form.add_button(
            self._t("BTN_MANAGE_SPAWN_B"),
            on_click=lambda sender, m=map_id, md=mode: self._show_spawn_edit(sender, m, md, TEAM_B),
        )
        form.add_button(self._t("BACK"), on_click=lambda sender, m=map_id: self._show_map_edit(sender, m))
        player.send_form(form)

    def _show_spawn_edit(self, player: Player, map_id: str, mode: str, team_id: str) -> None:
        assert self.config_store is not None
        map_cfg = self.config_store.maps.get(map_id)
        mode_cfg = get_mode_config(map_cfg or {}, mode) if map_cfg else None
        if map_cfg is None or mode_cfg is None:
            self._show_mode_edit(player, map_id, mode)
            return
        teams = mode_cfg.get("teams") or {}
        team = teams.get(team_id) or {}
        spawns = list(team.get("spawns") or [])
        team_name = str(team.get("name") or ("红队" if team_id == TEAM_A else "蓝队"))
        lines = [
            self._t("SPAWN_EDIT_LINE").format(idx + 1, spawn.get("x", 0), spawn.get("y", 0), spawn.get("z", 0))
            for idx, spawn in enumerate(spawns)
        ]
        body_text = "\n".join(lines) if lines else self._t("SPAWN_EDIT_EMPTY")
        content = self._t("SPAWN_EDIT_BODY").format(len(spawns), body_text)
        form = ActionForm(title=self._t("SPAWN_EDIT_TITLE").format(team_name), content=content)
        form.add_button(
            self._t("BTN_ADD_SPAWN_HERE"),
            on_click=lambda sender, m=map_id, md=mode, t=team_id: self._add_spawn(sender, m, md, t),
        )
        for idx, spawn in enumerate(spawns):
            label = self._t("BTN_DELETE_SPAWN_COORD").format(
                idx + 1,
                float(spawn.get("x", 0)),
                float(spawn.get("y", 0)),
                float(spawn.get("z", 0)),
            )
            form.add_button(
                label,
                on_click=lambda sender, m=map_id, md=mode, t=team_id, i=idx: self._remove_spawn(sender, m, md, t, i),
            )
        form.add_button(self._t("BACK"), on_click=lambda sender, m=map_id, md=mode: self._show_mode_edit(sender, m, md))
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
        self._show_spawn_edit(player, map_id, mode, team_id)

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
        self._show_spawn_edit(player, map_id, mode, team_id)

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
                match_minutes = max(1, int(str(data[2] or "5")))
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
                    mode_item["match_time_minutes"] = match_minutes

            self.config_store.update_map(map_id, updater)
            p.send_message(self._t("MODE_SETTINGS_OK"))
            self._show_mode_edit(p, map_id, mode)

        form = ModalForm(
            title=self._t("MODE_SETTINGS_TITLE").format(self._mode_label(mode)),
            controls=[
                TextInput(label=self._t("MODE_SETTINGS_TARGET"), default_value=str(mode_cfg.get("target_score", 50))),
                TextInput(label=self._t("MODE_SETTINGS_MAX"), default_value=str(mode_cfg.get("max_players_per_team", 8))),
                TextInput(
                    label=self._t("MODE_SETTINGS_MATCH_TIME"),
                    default_value=str(mode_cfg.get("match_time_minutes", 5)),
                ),
            ],
            on_submit=on_submit,
        )
        player.send_form(form)
