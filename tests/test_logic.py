# -*- coding: utf-8 -*-
import json
import math
import unittest
from pathlib import Path

from endstone_arc_shooter_game.config import (
    ConfigStore,
    build_runtime_map_cfg,
    map_incomplete_reasons,
    migrate_legacy_map,
    match_kd_score,
    mode_incomplete_reasons,
    mode_playable,
    normalize_map,
    normalize_weapon,
    playable_modes,
    point_in_region,
    slot_layout,
    slot_range,
    validate_map,
    validate_weapon,
)
from endstone_arc_shooter_game.loadout import (
    ACQUIRE_ARMORY,
    ACQUIRE_PRESET,
    ACQUIRE_SHOP,
    REASON_ALREADY_OWNED,
    REASON_INSUFFICIENT,
    SlotCapacities,
    ArmoryAcquireStrategy,
    ShopAcquireStrategy,
    apply_shop_purchase,
    assign_default_loadout,
    assign_preset_loadout,
    normalize_acquire_key,
    quote_shop_purchase,
    resolve_acquire_strategy,
)
from endstone_arc_shooter_game.map_db import MapDatabase
from endstone_arc_shooter_game.session import (
    STATE_BUYING,
    STATE_COUNTDOWN,
    STATE_LOBBY,
    STATE_PLAYING,
    TEAM_A,
    TEAM_B,
    Lobby,
    PlayerState,
    apply_kill,
    first_empty_or_first,
    pick_spawn,
)


def sample_map():
    return normalize_map(
        {
            "id": "warehouse",
            "display_name": "仓库",
            "dimension": "overworld",
            "region": {
                "pos1": {"x": 0, "y": 60, "z": 0},
                "pos2": {"x": 20, "y": 80, "z": 20},
            },
            "modes": [
                {
                    "mode": "tdm",
                    "max_players_per_team": 2,
                    "target_score": 3,
                    "match_time_minutes": 5,
                    "teams": {
                        "a": {"name": "红队", "spawns": [{"x": 0, "y": 64, "z": 0, "radius": 0}]},
                        "b": {"name": "蓝队", "spawns": [{"x": 10, "y": 64, "z": 0, "radius": 5}]},
                    },
                }
            ],
        }
    )


class SlotLayoutTests(unittest.TestCase):
    def test_default_hotbar_layout(self):
        layout = slot_layout(1, 1, 1, 3)
        self.assertEqual(slot_range(layout, "primary"), (0, 1))
        self.assertEqual(slot_range(layout, "secondary"), (1, 2))
        self.assertEqual(slot_range(layout, "melee"), (2, 3))
        self.assertEqual(slot_range(layout, "gadget"), (3, 6))
        self.assertEqual(layout["reserved"], 6)


class ConfigValidateTests(unittest.TestCase):
    def test_legacy_map_migrates(self):
        legacy = {
            "id": "old",
            "display_name": "旧图",
            "mode": "tdm",
            "teams": {
                "a": {"spawns": [{"x": 1, "y": 64, "z": 1}]},
                "b": {"spawns": [{"x": 2, "y": 64, "z": 2}]},
            },
        }
        migrated = migrate_legacy_map(legacy)
        self.assertIsInstance(migrated.get("modes"), list)
        self.assertEqual(migrated["modes"][0]["mode"], "tdm")

    def test_map_requires_modes_array(self):
        errors = validate_map({"id": "x", "display_name": "x"})
        self.assertTrue(errors)

    def test_runtime_map_includes_match_time(self):
        cfg = sample_map()
        runtime = build_runtime_map_cfg(cfg, "tdm")
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime["match_time_minutes"], 5)
        cfg["modes"][0]["match_time_minutes"] = 12
        runtime2 = build_runtime_map_cfg(cfg, "tdm")
        self.assertEqual(runtime2["match_time_minutes"], 12)
        cfg = sample_map()
        self.assertTrue(mode_playable(cfg, "tdm"))
        self.assertIn("tdm", playable_modes(cfg))
        runtime = build_runtime_map_cfg(cfg, "tdm")
        self.assertIsNotNone(runtime)
        self.assertEqual(runtime["mode"], "tdm")

    def test_point_in_region(self):
        cfg = sample_map()
        self.assertTrue(point_in_region(cfg, 5, 64, 5))
        self.assertFalse(point_in_region(cfg, 100, 64, 5))

    def test_mode_incomplete_reasons(self):
        cfg = sample_map()
        self.assertEqual(mode_incomplete_reasons(cfg, "tdm"), [])
        cfg_no_region = normalize_map(
            {
                "id": "x",
                "display_name": "x",
                "modes": cfg["modes"],
            }
        )
        self.assertIn("reason_missing_region", mode_incomplete_reasons(cfg_no_region, "tdm"))
        cfg_no_b = sample_map()
        cfg_no_b["modes"][0]["teams"]["b"]["spawns"] = []
        self.assertIn("reason_missing_spawn_b", mode_incomplete_reasons(cfg_no_b, "tdm"))

    def test_map_incomplete_reasons(self):
        cfg = sample_map()
        self.assertEqual(map_incomplete_reasons(cfg), [])
        cfg_no_region = normalize_map({"id": "x", "display_name": "x", "modes": cfg["modes"]})
        self.assertIn("reason_missing_region", map_incomplete_reasons(cfg_no_region))
        cfg_empty = normalize_map({"id": "y", "display_name": "y", "modes": []})
        self.assertIn("reason_no_modes", map_incomplete_reasons(cfg_empty))

    def test_single_playable_mode_auto_bind(self):
        cfg = sample_map()
        modes = playable_modes(cfg)
        self.assertEqual(modes, ["tdm"])
        lobby = Lobby(admin="alice")
        ok, _ = lobby.set_map_and_mode(cfg, modes[0])
        self.assertTrue(ok)
        self.assertEqual(lobby.mode, "tdm")
        self.assertIsNotNone(lobby.map_cfg)
        assert lobby.map_cfg is not None
        self.assertEqual(lobby.map_cfg.get("match_time_minutes"), 5)

    def test_weapon_type_and_extras(self):
        errors = validate_weapon(
            {"id": "ak", "item": "custom:ak", "type": "primary", "cost": 10, "extras": {"custom:ammo": 30}}
        )
        self.assertEqual(errors, [])
        weapon = normalize_weapon(
            {"id": "ak", "item": "custom:ak", "type": "primary", "cost": 10, "extras": {"custom:ammo": 30}}
        )
        self.assertEqual(weapon["extras"]["custom:ammo"], 30)

    def test_weapon_ammo_scoreboard(self):
        weapon = normalize_weapon(
            {
                "id": "ak47",
                "item": "arc:ak47",
                "type": "primary",
                "cost": 800,
                "default_ammo": 30,
            }
        )
        self.assertEqual(weapon["ammo_scoreboard"], "ak47")
        self.assertEqual(weapon["default_ammo"], 30)
        plain = normalize_weapon({"id": "iron_sword", "item": "minecraft:iron_sword", "type": "secondary", "cost": 100})
        self.assertNotIn("ammo_scoreboard", plain)

    def test_weapons_json_matches_aplok_ammo(self):
        root = Path(__file__).resolve().parents[1]
        ammo_ref = json.loads((root / "plugins/ARCShooterGame/aplok_ammo.json").read_text(encoding="utf-8"))
        weapons = json.loads((root / "plugins/ARCShooterGame/weapons.json").read_text(encoding="utf-8"))
        by_id = {w["id"]: w for w in weapons["weapons"]}
        for wid, spec in ammo_ref["weapons"].items():
            weapon = by_id[wid]
            self.assertEqual(weapon["ammo_scoreboard"], spec["ammo_scoreboard"], wid)
            self.assertEqual(weapon["default_ammo"], spec["default_ammo"], wid)

    def test_reject_bad_weapon_type(self):
        errors = validate_weapon({"id": "x", "item": "minecraft:stick", "type": "ultimate"})
        self.assertTrue(any("type" in e for e in errors))

    def test_rename_and_delete_map(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "test.db"
            store = ConfigStore()
            store.map_db = MapDatabase(db_path=db_path)
            store.maps = {}
            entry = store.create_map("测试图", "overworld")
            map_id = entry["id"]
            store.update_map(map_id, lambda m: m.update({"display_name": "新名称"}))
            self.assertEqual(store.maps[map_id]["display_name"], "新名称")
            self.assertTrue(store.delete_map(map_id))
            self.assertNotIn(map_id, store.maps)
            self.assertEqual(store.map_db.load_all(), {})
            store.map_db.close()

    def test_sqlite_roundtrip(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            db = MapDatabase(db_path=Path(tmp) / "roundtrip.db")
            saved = db.save_map(sample_map())
            loaded = db.load_all()
            self.assertIn(saved["id"], loaded)
            self.assertEqual(loaded[saved["id"]]["display_name"], "仓库")
            db.close()


class SpawnTests(unittest.TestCase):
    def test_radius_zero_is_exact(self):
        pos = pick_spawn([{"x": 3, "y": 64, "z": 7, "radius": 0}])
        self.assertEqual(pos["x"], 3)
        self.assertEqual(pos["z"], 7)
        self.assertEqual(pos["y"], 64)

    def test_radius_stays_inside_circle(self):
        spawn = {"x": 0, "y": 64, "z": 0, "radius": 4}
        for _ in range(40):
            pos = pick_spawn([spawn])
            dist = math.hypot(pos["x"] - 0, pos["z"] - 0)
            self.assertLessEqual(dist, 4.0001)


class KillScoreTests(unittest.TestCase):
    def test_enemy_kill_scores_and_rewards(self):
        result = apply_kill(2, 1, TEAM_A, TEAM_B, 3, 100, 50)
        self.assertEqual(result["score_a"], 3)
        self.assertEqual(result["killer_points"], 150)
        self.assertEqual(result["winner"], TEAM_A)
        self.assertFalse(result["friendly"])

    def test_friendly_fire_subtracts_and_no_reward(self):
        result = apply_kill(2, 1, TEAM_A, TEAM_A, 10, 100, 50)
        self.assertEqual(result["score_a"], 1)
        self.assertEqual(result["reward"], 0)
        self.assertEqual(result["killer_points"], 50)
        self.assertIsNone(result["winner"])

    def test_friendly_fire_does_not_go_negative(self):
        result = apply_kill(0, 0, TEAM_B, TEAM_B, 10, 100, 0)
        self.assertEqual(result["score_b"], 0)


class LobbyTests(unittest.TestCase):
    def _lobby_with_map(self) -> Lobby:
        lobby = Lobby(admin="alice")
        lobby.set_map_and_mode(sample_map(), "tdm")
        return lobby

    def test_create_and_join(self):
        lobby = Lobby(admin="alice")
        ok, reason = lobby.join("alice", 800, now=1000)
        self.assertTrue(ok)
        self.assertEqual(reason, "admin")
        self.assertEqual(lobby.state, STATE_LOBBY)
        ok, reason = lobby.join("bob", 800, now=1001)
        self.assertTrue(ok)
        self.assertEqual(lobby.player_count(), 2)

    def test_fourth_player_rejected_when_teams_full(self):
        lobby = self._lobby_with_map()
        for name in ("a", "b", "c", "d"):
            self.assertTrue(lobby.join(name, 1, now=1)[0])
        ok, reason = lobby.join("eve", 1, now=2)
        self.assertFalse(ok)
        self.assertEqual(reason, "full")

    def test_cannot_start_without_map(self):
        lobby = Lobby(admin="alice")
        lobby.prefer_random_map = False
        lobby.prefer_random_mode = False
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        ok, reason = lobby.can_start()
        self.assertFalse(ok)
        self.assertEqual(reason, "need_map")

    def test_can_start_with_random_preference(self):
        lobby = Lobby(admin="alice")
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        self.assertTrue(lobby.prefer_random_map)
        ok, reason = lobby.can_start()
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_cancel_countdown_releases_random_map(self):
        lobby = self._lobby_with_map()
        lobby.prefer_random_map = True
        lobby.prefer_random_mode = True
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        lobby.begin_countdown(5, now=10)
        self.assertIsNotNone(lobby.map_id)
        lobby.cancel_countdown()
        self.assertIsNone(lobby.map_id)
        self.assertIsNone(lobby.mode)
        self.assertIsNone(lobby.map_cfg)

    def test_can_start_with_map_and_mode(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        ok, reason = lobby.can_start()
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_mid_match_join_allowed_when_not_full(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        lobby.begin_buy(10, now=3)
        ok, reason = lobby.can_join()
        self.assertTrue(ok)
        self.assertEqual(reason, "ok")

    def test_lobby_timeout(self):
        lobby = Lobby(admin="alice")
        lobby.join("alice", 800, now=0)
        self.assertFalse(lobby.lobby_timed_out(900, now=899))
        self.assertTrue(lobby.lobby_timed_out(900, now=900))

    def test_start_countdown_state(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        lobby.begin_countdown(5, now=10)
        self.assertEqual(lobby.state, STATE_COUNTDOWN)
        self.assertAlmostEqual(lobby.countdown_remaining(now=12), 3.0)
        self.assertTrue(lobby.mark_announced("cd:3"))
        self.assertFalse(lobby.mark_announced("cd:3"))
        lobby.cancel_countdown()
        self.assertEqual(lobby.state, STATE_LOBBY)
        self.assertEqual(lobby.countdown_remaining(now=20), 0.0)

    def test_teams_ready_to_start(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        self.assertFalse(lobby.teams_ready_to_start())
        lobby.join("bob", 800, now=2)
        self.assertTrue(lobby.teams_ready_to_start())

    def test_admin_leave_transfers(self):
        lobby = Lobby(admin="alice")
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        new_admin = lobby.leave("alice")
        self.assertEqual(new_admin, "bob")
        self.assertEqual(lobby.admin, "bob")

    def test_kill_ends_match_at_target(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        lobby.begin_buy(0)
        lobby.begin_playing()
        lobby.apply_player_kill("alice", "bob", 100)
        lobby.apply_player_kill("alice", "bob", 100)
        result = lobby.apply_player_kill("alice", "bob", 100)
        self.assertEqual(result["winner"], TEAM_A)
        self.assertEqual(lobby.players["alice"].kills, 3)
        self.assertEqual(lobby.players["bob"].deaths, 3)
        self.assertEqual(lobby.players["alice"].points, 1100)

    def test_friendly_fire_skips_match_kd(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        lobby.players["bob"].team = lobby.players["alice"].team
        lobby.begin_buy(0)
        lobby.begin_playing()
        result = lobby.apply_player_kill("alice", "bob", 100)
        self.assertTrue(result["friendly"])
        self.assertEqual(lobby.players["alice"].kills, 0)
        self.assertEqual(lobby.players["bob"].deaths, 0)

    def test_gadget_fills_then_replaces_first(self):
        lobby = Lobby(admin="alice")
        lobby.join("alice", 800, now=1)
        w1 = {"id": "g1", "type": "gadget"}
        w2 = {"id": "g2", "type": "gadget"}
        w3 = {"id": "g3", "type": "gadget"}
        w4 = {"id": "g4", "type": "gadget"}
        self.assertEqual(lobby.record_purchase("alice", w1, 3)[0], 0)
        self.assertEqual(lobby.record_purchase("alice", w2, 3)[0], 1)
        self.assertEqual(lobby.record_purchase("alice", w3, 3)[0], 2)
        idx, old = lobby.record_purchase("alice", w4, 3)
        self.assertEqual(idx, 0)
        self.assertEqual(old, "g1")
        self.assertEqual(lobby.players["alice"].gadgets[0], "g4")

    def test_first_empty_or_first(self):
        self.assertEqual(first_empty_or_first([None, "a"], 2), 0)
        self.assertEqual(first_empty_or_first(["a", None], 2), 1)
        self.assertEqual(first_empty_or_first(["a", "b"], 2), 0)

    def test_match_timeout_by_score(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        lobby.begin_buy(0, now=3)
        lobby.begin_playing(300, now=10)
        lobby.score_a = 5
        lobby.score_b = 3
        self.assertTrue(lobby.match_timed_out(now=310))
        self.assertEqual(lobby.winner_by_score(), TEAM_A)
        lobby.score_b = 5
        self.assertIsNone(lobby.winner_by_score())

    def test_armor_purchase_record(self):
        lobby = Lobby(admin="alice")
        lobby.join("alice", 800, now=1)
        armor = {"id": "iron_armor", "type": "armor"}
        idx, old = lobby.record_purchase("alice", armor, 1)
        self.assertEqual(idx, 0)
        self.assertIsNone(old)
        self.assertEqual(lobby.players["alice"].armor_id, "iron_armor")
        idx2, old2 = lobby.record_purchase("alice", {"id": "diamond_armor", "type": "armor"}, 1)
        self.assertEqual(old2, "iron_armor")
        self.assertEqual(lobby.players["alice"].armor_id, "diamond_armor")

    def test_mode_match_time_from_runtime_map(self):
        lobby = self._lobby_with_map()
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        assert lobby.map_cfg is not None
        lobby.map_cfg["match_time_minutes"] = 8
        self.assertEqual(lobby.match_time_minutes, 8)
        self.assertEqual(lobby.match_time_seconds, 480)
        lobby.begin_buy(0, now=3)
        lobby.begin_playing(lobby.match_time_seconds, now=10)
        self.assertFalse(lobby.match_timed_out(now=100))
        self.assertTrue(lobby.match_timed_out(now=490))

    def test_match_kd_score(self):
        self.assertEqual(match_kd_score(5, 2), 3)
        self.assertEqual(match_kd_score(2, 5), 0)
        self.assertEqual(match_kd_score(3, 3), 0)

    def test_match_kda_coefficient_and_money(self):
        from endstone_arc_shooter_game.config import (
            calc_match_money,
            collect_assist_and_tk,
            match_reward_coefficient,
        )

        # 10/12/5 无 TK → (10+2.5)/12
        coeff = match_reward_coefficient(10, 12, 5, 0)
        self.assertAlmostEqual(coeff, 12.5 / 12.0, places=5)
        money = calc_match_money(
            10, 12, 5, 0, money_per_kill=200, win_bonus=2000, won=False
        )
        self.assertEqual(money, int(round(2000 * (12.5 / 12.0))))
        win_money = calc_match_money(
            10, 12, 5, 0, money_per_kill=200, win_bonus=2000, won=True
        )
        self.assertEqual(win_money, int(round(4000 * (12.5 / 12.0))))
        # 死亡为 0 时按 1 除
        self.assertAlmostEqual(match_reward_coefficient(5, 0, 0, 0), 5.0)
        from endstone_arc_shooter_game.config import match_mvp_score, pick_team_mvp
        from endstone_arc_shooter_game.session import PlayerState, TEAM_A

        self.assertAlmostEqual(match_mvp_score(10, 12, 5, 0), 12.5 / 12.0 + 1.0, places=5)
        a = PlayerState(name="a", team=TEAM_A, points=0, kills=10, deaths=12, assists=5)
        b = PlayerState(name="b", team=TEAM_A, points=0, kills=8, deaths=2, assists=0)
        # b: coeff=8/2=4 + 0.8 = 4.8 > a ≈ 2.04
        self.assertEqual(pick_team_mvp([a, b]).name, "b")
        assists, tks = collect_assist_and_tk(
            {"alice": 10.0, "bob": 9.5, "carol": 1.0, "dave": 9.8},
            now=10.0,
            window=3.0,
            killer_name="alice",
            victim_team="a",
            team_of={"alice": "b", "bob": "b", "carol": "b", "dave": "a"},
        )
        self.assertEqual(assists, ["bob"])
        self.assertEqual(tks, ["dave"])

    def test_match_reward_amounts(self):
        store = ConfigStore.__new__(ConfigStore)
        store.settings = type("S", (), {
            "GetSettingInt": lambda self, key, default=0: {
                "WIN_GUILD_CONTRIBUTION_PER_KD": 10,
                "MATCH_MONEY_PER_KILL": 200,
                "MATCH_WIN_BONUS": 2000,
            }.get(key, default),
            "GetSettingFloat": lambda self, key, default=0.0: {
                "MATCH_ASSIST_WEIGHT": 0.5,
                "MATCH_TK_WEIGHT": 1.5,
                "ASSIST_WINDOW_SECONDS": 3.0,
            }.get(key, default),
        })()
        from endstone_arc_shooter_game.config import calc_match_money

        money = calc_match_money(
            8, 3, 2, 0,
            money_per_kill=store.match_money_per_kill(),
            win_bonus=store.match_win_bonus(),
            won=True,
            assist_weight=store.match_assist_weight(),
            tk_weight=store.match_tk_weight(),
        )
        # base=(8*200+2000)=3600, coeff=(8+1)/3=3 → 10800
        self.assertEqual(money, 10800)


class ShopLoadoutTests(unittest.TestCase):
    def setUp(self):
        self.weapons = {
            "cheap": {
                "id": "cheap",
                "display_name": "便宜枪",
                "item": "minecraft:stick",
                "cost": 500,
                "type": "primary",
            },
            "pricey": {
                "id": "pricey",
                "display_name": "贵枪",
                "item": "minecraft:bow",
                "cost": 900,
                "type": "primary",
            },
            "nade": {
                "id": "nade",
                "display_name": "手雷",
                "item": "minecraft:snowball",
                "cost": 90,
                "type": "gadget",
            },
        }
        self.caps = SlotCapacities(primary=1, secondary=1, melee=1, gadget=2, armor=1)
        self.ps = PlayerState(name="p1", team=TEAM_A, points=1000)

    def test_upgrade_pays_difference(self):
        cheap = self.weapons["cheap"]
        pricey = self.weapons["pricey"]
        first = apply_shop_purchase(self.ps, cheap, self.weapons, self.caps)
        self.assertTrue(first.ok)
        self.assertEqual(first.pay, 500)
        self.assertEqual(self.ps.points, 500)
        quote = quote_shop_purchase(self.ps, pricey, self.weapons, self.caps)
        self.assertEqual(quote.pay, 400)
        self.assertEqual(quote.credit, 500)
        self.assertTrue(quote.is_upgrade)
        second = apply_shop_purchase(self.ps, pricey, self.weapons, self.caps)
        self.assertTrue(second.ok)
        self.assertEqual(second.pay, 400)
        self.assertEqual(self.ps.primary_id, "pricey")
        self.assertEqual(self.ps.points, 100)

    def test_already_owned(self):
        cheap = self.weapons["cheap"]
        apply_shop_purchase(self.ps, cheap, self.weapons, self.caps)
        again = apply_shop_purchase(self.ps, cheap, self.weapons, self.caps)
        self.assertFalse(again.ok)
        self.assertEqual(again.reason, REASON_ALREADY_OWNED)

    def test_insufficient_even_with_credit(self):
        self.ps.points = 600
        apply_shop_purchase(self.ps, self.weapons["cheap"], self.weapons, self.caps)
        self.assertEqual(self.ps.points, 100)
        # upgrade needs 400 but only 100 left
        outcome = apply_shop_purchase(self.ps, self.weapons["pricey"], self.weapons, self.caps)
        self.assertFalse(outcome.ok)
        self.assertEqual(outcome.reason, REASON_INSUFFICIENT)
        self.assertEqual(outcome.pay, 400)
        self.assertEqual(self.ps.primary_id, "cheap")
        self.assertEqual(self.ps.points, 100)

    def test_downgrade_refunds_difference(self):
        mid = {
            "id": "mid",
            "display_name": "中价枪",
            "item": "minecraft:iron_sword",
            "cost": 700,
            "type": "primary",
        }
        weapons = {**self.weapons, "mid": mid}
        apply_shop_purchase(self.ps, self.weapons["cheap"], weapons, self.caps)
        apply_shop_purchase(self.ps, self.weapons["pricey"], weapons, self.caps)
        self.assertEqual(self.ps.primary_id, "pricey")
        self.assertEqual(self.ps.points, 100)
        # 降级退差价 200，点数回到 300
        downgrade = apply_shop_purchase(self.ps, mid, weapons, self.caps)
        self.assertTrue(downgrade.ok)
        self.assertEqual(downgrade.pay, -200)
        self.assertEqual(downgrade.credit, 900)
        self.assertEqual(self.ps.primary_id, "mid")
        self.assertEqual(self.ps.points, 300)
        # 再换回贵枪只需补 200
        quote = quote_shop_purchase(self.ps, self.weapons["pricey"], weapons, self.caps)
        self.assertEqual(quote.pay, 200)
        self.assertEqual(quote.credit, 700)
        self.assertTrue(quote.is_upgrade)
        swap_back = apply_shop_purchase(self.ps, self.weapons["pricey"], weapons, self.caps)
        self.assertTrue(swap_back.ok)
        self.assertEqual(swap_back.pay, 200)
        self.assertEqual(self.ps.primary_id, "pricey")
        self.assertEqual(self.ps.points, 100)

    def test_assign_default_loadout(self):
        weapons = {
            **self.weapons,
            "m1911": {
                "id": "m1911",
                "display_name": "M1911",
                "item": "arc:m1911",
                "cost": 250,
                "type": "secondary",
            },
            "knife": {
                "id": "knife",
                "display_name": "战术匕首",
                "item": "arc:silencefd",
                "cost": 100,
                "type": "melee",
            },
        }
        defaults = {
            "primary": "",
            "secondary": "m1911",
            "melee": "knife",
            "gadget": "",
            "armor": "",
        }
        assign_default_loadout(self.ps, weapons, defaults)
        self.assertIsNone(self.ps.primary_id)
        self.assertEqual(self.ps.secondary_id, "m1911")
        self.assertEqual(self.ps.melee_id, "knife")
        self.assertIsNone(self.ps.armor_id)
        self.assertEqual(self.ps.gadgets, [])

    def test_default_weapon_has_no_trade_in_credit(self):
        weapons = {
            **self.weapons,
            "m1911": {
                "id": "m1911",
                "display_name": "M1911",
                "item": "arc:m1911",
                "cost": 250,
                "type": "secondary",
            },
            "glock": {
                "id": "glock",
                "display_name": "Glock",
                "item": "arc:glock17",
                "cost": 300,
                "type": "secondary",
            },
        }
        defaults = {"secondary": "m1911"}
        assign_default_loadout(self.ps, weapons, defaults)
        quote = quote_shop_purchase(
            self.ps,
            weapons["glock"],
            weapons,
            self.caps,
            default_weapons=defaults,
        )
        self.assertEqual(quote.pay, 300)
        self.assertEqual(quote.credit, 0)

    def test_preset_and_strategy_resolve(self):
        assign_preset_loadout(
            self.ps,
            self.weapons,
            {"primary": "pricey", "gadgets": ["nade"]},
        )
        self.assertEqual(self.ps.primary_id, "pricey")
        self.assertEqual(self.ps.gadgets, ["nade"])
        shop = resolve_acquire_strategy(key=ACQUIRE_SHOP)
        preset = resolve_acquire_strategy({"weapon_acquire": ACQUIRE_PRESET})
        self.assertTrue(shop.uses_shop)
        self.assertTrue(isinstance(shop, ShopAcquireStrategy))
        self.assertFalse(preset.uses_shop)
        self.assertFalse(preset.uses_buy_phase)
        self.assertEqual(normalize_acquire_key("nope"), ACQUIRE_ARMORY)
        armory = resolve_acquire_strategy(key=ACQUIRE_ARMORY)
        self.assertTrue(isinstance(armory, ArmoryAcquireStrategy))
        self.assertFalse(armory.uses_shop)
        self.assertTrue(armory.uses_buy_phase)

    def test_normalize_mode_keeps_weapon_acquire(self):
        raw = sample_map()
        # TDM 固定军械库，显式写 shop 也会被纠正
        raw["modes"][0]["weapon_acquire"] = "shop"
        normalized = normalize_map(raw)
        self.assertEqual(normalized["modes"][0]["weapon_acquire"], ACQUIRE_ARMORY)
        # 非 TDM 仍可保留其它获取方式
        raw2 = sample_map()
        raw2["modes"][0]["mode"] = "ffa"
        raw2["modes"][0]["weapon_acquire"] = "preset"
        raw2["modes"][0]["preset_loadout"] = {"primary": "ak47"}
        mode = normalize_map(raw2)["modes"][0]
        self.assertEqual(mode["weapon_acquire"], "preset")
        self.assertEqual(mode["preset_loadout"]["primary"], "ak47")

    def test_tdm_defaults_to_armory(self):
        mode = normalize_map(sample_map())["modes"][0]
        self.assertEqual(mode["weapon_acquire"], ACQUIRE_ARMORY)
        forced = sample_map()
        forced["modes"][0]["weapon_acquire"] = "shop"
        self.assertEqual(normalize_map(forced)["modes"][0]["weapon_acquire"], ACQUIRE_ARMORY)


class MapOccupancyTests(unittest.TestCase):
    def test_two_lobbies_cannot_share_map(self):
        map_cfg = sample_map()
        lobby_a = Lobby(admin="alice")
        lobby_b = Lobby(admin="bob")
        lobby_a.set_map_and_mode(map_cfg, "tdm")
        occupied = {lobby_a.map_id}
        lobby_b.set_map_and_mode(map_cfg, "tdm")
        self.assertIn(map_cfg["id"], occupied)
        self.assertEqual(lobby_b.map_id, map_cfg["id"])


class CareerKdTitleTests(unittest.TestCase):
    def test_career_kd(self):
        from endstone_arc_shooter_game.career_stats import career_kd

        self.assertEqual(career_kd(0, 0), 0.0)
        self.assertEqual(career_kd(5, 0), 5.0)
        self.assertEqual(career_kd(10, 5), 2.0)
        self.assertEqual(career_kd(3, 4), 0.75)

    def test_title_for_kd(self):
        from endstone_arc_shooter_game.career_stats import title_for_kd, titles_unlocked_by_kd

        self.assertEqual(title_for_kd(5.0), ("神话", "传奇枪王"))
        self.assertEqual(title_for_kd(3.0), ("传奇", "枪械大师"))
        self.assertEqual(title_for_kd(2.0), ("史诗", "精英枪手"))
        self.assertEqual(title_for_kd(1.0), ("稀有", "熟练枪手"))
        self.assertEqual(title_for_kd(0.9), ("普通", "见习枪手"))
        unlocked = titles_unlocked_by_kd(2.5)
        self.assertEqual(
            unlocked,
            [
                ("普通", "见习枪手"),
                ("稀有", "熟练枪手"),
                ("史诗", "精英枪手"),
            ],
        )

    def test_match_result_counters(self):
        import tempfile
        from pathlib import Path

        from endstone_arc_shooter_game.career_stats import CareerStore

        with tempfile.TemporaryDirectory() as tmp:
            store = CareerStore(db_path=Path(tmp) / "t.db")
            store.record_match_end("p", won=True, mvp=True)
            store.record_match_end("p", won=False, mvp=True)
            store.record_match_end("p", draw=True, mvp=True)
            store.record_match_end("p", won=False, mvp=False)
            s = store.get("p")
            self.assertEqual(s.matches, 4)
            self.assertEqual(s.wins, 1)
            self.assertEqual(s.losses, 2)
            self.assertEqual(s.draws, 1)
            self.assertEqual(s.mvps, 3)
            self.assertEqual(s.win_mvps, 1)
            self.assertEqual(s.lose_mvps, 1)
            store.close()

    def test_list_ranked_by_kd(self):
        import tempfile
        from pathlib import Path

        from endstone_arc_shooter_game.career_stats import CareerStore

        with tempfile.TemporaryDirectory() as tmp:
            store = CareerStore(db_path=Path(tmp) / "t.db")
            store.record_kill("low", xp_gain=0)
            store.record_death("low")
            store.record_death("low")
            for _ in range(4):
                store.record_kill("high", xp_gain=0)
            store.record_death("high")
            store.record_kill("mid", xp_gain=0)
            ranked = store.list_ranked_by_kd()
            self.assertEqual([s.name for s in ranked], ["high", "mid", "low"])
            self.assertGreater(ranked[0].kd, ranked[1].kd)
            store.close()


class ArmoryLevelTests(unittest.TestCase):
    def test_level_from_xp_and_progress(self):
        from endstone_arc_shooter_game.career_stats import level_from_xp, xp_progress

        self.assertEqual(level_from_xp(0), 0)
        self.assertEqual(level_from_xp(99), 0)
        self.assertEqual(level_from_xp(100), 1)
        self.assertEqual(level_from_xp(10000), 100)
        self.assertEqual(level_from_xp(99999), 100)
        self.assertEqual(xp_progress(250), (2, 50, 100))
        self.assertEqual(xp_progress(10000), (100, 0, 100))

    def test_settlement_xp(self):
        from endstone_arc_shooter_game.career_stats import calc_match_settlement_xp

        # 10 kill * 5 = 50 base; win +20% = 10; MVP = 2人×10 = 20
        self.assertEqual(
            calc_match_settlement_xp(10, won=True, mvp=True, team_size=2),
            10 + 20,
        )
        self.assertEqual(
            calc_match_settlement_xp(10, won=False, mvp=True, team_size=2),
            20,
        )
        self.assertEqual(calc_match_settlement_xp(10, won=True, mvp=False, team_size=2), 10)
        # 单人队 MVP 仅 +10，避免一人刷经验过快
        self.assertEqual(
            calc_match_settlement_xp(0, won=True, mvp=True, team_size=1),
            10,
        )
        self.assertEqual(
            calc_match_settlement_xp(0, won=False, mvp=True, team_size=3, mvp_per_teammate=10),
            30,
        )

    def test_sanitize_loadout_fallback(self):
        from endstone_arc_shooter_game.loadout_store import SavedLoadout, sanitize_loadout

        weapons = {
            "m4": {"id": "m4", "type": "primary", "unlock_level": 0, "category": "assault_rifle"},
            "ak47": {"id": "ak47", "type": "primary", "unlock_level": 25, "category": "assault_rifle"},
            "m1911": {"id": "m1911", "type": "secondary", "unlock_level": 0, "category": "pistol"},
        }
        defaults = {"primary": "m4", "secondary": "m1911"}
        raw = SavedLoadout(name="p", primary_id="ak47", secondary_id="m1911")
        cleaned = sanitize_loadout(raw, weapons, defaults, level=0)
        self.assertEqual(cleaned.primary_id, "m4")
        self.assertEqual(cleaned.secondary_id, "m1911")
        cleaned2 = sanitize_loadout(raw, weapons, defaults, level=25)
        self.assertEqual(cleaned2.primary_id, "ak47")

    def test_five_presets_default(self):
        import tempfile
        from pathlib import Path

        from endstone_arc_shooter_game.loadout_store import PRESET_COUNT, LoadoutStore

        defaults = {
            "primary": "m4",
            "secondary": "m1911",
            "melee": "silencefd",
            "gadget": "mk2_grenade",
            "armor": "",
        }
        with tempfile.TemporaryDirectory() as tmp:
            store = LoadoutStore(db_path=Path(tmp) / "l.db")
            presets = store.list_presets("p", defaults=defaults)
            self.assertEqual(len(presets), PRESET_COUNT)
            for i, p in enumerate(presets):
                self.assertEqual(p.slot, i)
                self.assertEqual(p.primary_id, "m4")
                self.assertEqual(p.secondary_id, "m1911")
                self.assertEqual(p.melee_id, "silencefd")
                self.assertEqual(p.gadgets, ["mk2_grenade"])
            store.set_active_slot("p", 2)
            store.set_slot(
                "p",
                "primary",
                None,
                preset=2,
                weapons={"m4": {"id": "m4", "type": "primary", "unlock_level": 0}},
                level=0,
                defaults=defaults,
            )
            active = store.get("p", defaults=defaults)
            self.assertEqual(active.slot, 2)
            self.assertIsNone(active.primary_id)
            store.close()

    def test_normalize_weapon_category_unlock(self):
        w = normalize_weapon(
            {
                "id": "m4",
                "display_name": "M4",
                "item": "arc:m4",
                "cost": 650,
                "type": "primary",
                "category": "assault_rifle",
                "unlock_level": 0,
            }
        )
        self.assertEqual(w["category"], "assault_rifle")
        self.assertEqual(w["unlock_level"], 0)
        errors = validate_weapon(
            {
                "id": "x",
                "display_name": "X",
                "item": "arc:x",
                "cost": 1,
                "type": "primary",
                "category": "nope",
                "unlock_level": -1,
            }
        )
        self.assertTrue(any("category" in e for e in errors))

    def test_armory_assign_uses_saved(self):
        from endstone_arc_shooter_game.loadout_store import SavedLoadout

        weapons = {
            "m4": {"id": "m4", "type": "primary", "unlock_level": 0},
            "m1911": {"id": "m1911", "type": "secondary", "unlock_level": 0},
            "silencefd": {"id": "silencefd", "type": "melee", "unlock_level": 0},
            "mk2_grenade": {"id": "mk2_grenade", "type": "gadget", "unlock_level": 0},
        }
        ps = PlayerState(name="alice", team=TEAM_A, points=0)
        strategy = ArmoryAcquireStrategy()
        strategy.assign_on_match_start(
            ps,
            weapons,
            {},
            defaults={
                "primary": "m4",
                "secondary": "m1911",
                "melee": "silencefd",
                "gadget": "mk2_grenade",
            },
            saved_loadout=SavedLoadout(
                name="alice",
                primary_id="m4",
                secondary_id="m1911",
                melee_id="silencefd",
                gadgets=["mk2_grenade"],
            ),
            player_level=0,
            gadget_slots=2,
        )
        self.assertEqual(ps.primary_id, "m4")
        self.assertEqual(ps.secondary_id, "m1911")
        self.assertEqual(ps.melee_id, "silencefd")
        self.assertEqual(ps.gadgets, ["mk2_grenade"])


if __name__ == "__main__":
    unittest.main()
