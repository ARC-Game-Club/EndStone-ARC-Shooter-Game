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
from endstone_arc_shooter_game.map_db import MapDatabase
from endstone_arc_shooter_game.session import (
    STATE_BUYING,
    STATE_LOBBY,
    STATE_PLAYING,
    TEAM_A,
    TEAM_B,
    Lobby,
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
        layout = slot_layout(1, 1, 3)
        self.assertEqual(slot_range(layout, "primary"), (0, 1))
        self.assertEqual(slot_range(layout, "secondary"), (1, 2))
        self.assertEqual(slot_range(layout, "gadget"), (2, 5))
        self.assertEqual(layout["reserved"], 5)


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
                "item": "trenbankai:ak47",
                "type": "primary",
                "cost": 900,
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
        lobby.join("alice", 800, now=1)
        lobby.join("bob", 800, now=2)
        ok, reason = lobby.can_start()
        self.assertFalse(ok)
        self.assertEqual(reason, "need_map")

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

    def test_match_reward_amounts(self):
        store = ConfigStore.__new__(ConfigStore)
        store.settings = type("S", (), {"GetSettingInt": lambda self, key, default=0: {
            "WIN_GUILD_CONTRIBUTION_PER_KD": 10,
            "MATCH_MONEY_PER_KD": 100,
        }.get(key, default)})()
        kd = match_kd_score(8, 3)
        self.assertEqual(kd * store.match_money_per_kd(), 500)
        self.assertEqual(kd * store.win_guild_contribution_per_kd(), 50)


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


if __name__ == "__main__":
    unittest.main()
