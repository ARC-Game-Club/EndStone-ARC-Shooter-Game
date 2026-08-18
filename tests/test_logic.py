# -*- coding: utf-8 -*-
import math
import unittest

from endstone_arc_shooter_game.config import (
    normalize_map,
    normalize_weapon,
    slot_layout,
    slot_range,
    validate_map,
    validate_weapon,
)
from endstone_arc_shooter_game.session import (
    STATE_IDLE,
    STATE_LOBBY,
    TEAM_A,
    TEAM_B,
    MapInstance,
    apply_kill,
    first_empty_or_first,
    pick_spawn,
)


def sample_map():
    return normalize_map(
        {
            "id": "warehouse",
            "display_name": "仓库",
            "mode": "tdm",
            "max_players_per_team": 2,
            "target_score": 3,
            "dimension": "overworld",
            "teams": {
                "a": {"name": "红队", "spawns": [{"x": 0, "y": 64, "z": 0, "radius": 0}]},
                "b": {"name": "蓝队", "spawns": [{"x": 10, "y": 64, "z": 0, "radius": 5}]},
            },
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
    def test_map_requires_spawns(self):
        errors = validate_map({"id": "x", "mode": "tdm", "teams": {"a": {"spawns": []}, "b": {}}})
        self.assertTrue(errors)

    def test_weapon_type_and_extras(self):
        errors = validate_weapon(
            {"id": "ak", "item": "custom:ak", "type": "primary", "cost": 10, "extras": {"custom:ammo": 30}}
        )
        self.assertEqual(errors, [])
        weapon = normalize_weapon(
            {"id": "ak", "item": "custom:ak", "type": "primary", "cost": 10, "extras": {"custom:ammo": 30}}
        )
        self.assertEqual(weapon["extras"]["custom:ammo"], 30)

    def test_reject_bad_weapon_type(self):
        errors = validate_weapon({"id": "x", "item": "minecraft:stick", "type": "ultimate"})
        self.assertTrue(any("type" in e for e in errors))


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


class SessionTests(unittest.TestCase):
    def test_first_join_becomes_admin_and_balances_teams(self):
        inst = MapInstance(sample_map())
        ok, reason = inst.join("alice", 800, now=1000)
        self.assertTrue(ok)
        self.assertEqual(reason, "admin")
        self.assertEqual(inst.state, STATE_LOBBY)
        self.assertEqual(inst.admin, "alice")
        inst.join("bob", 800, now=1001)
        inst.join("carol", 800, now=1002)
        self.assertEqual(inst.players["alice"].team, TEAM_A)
        self.assertEqual(inst.players["bob"].team, TEAM_B)
        self.assertEqual(inst.players["carol"].team, TEAM_A)

    def test_fourth_player_rejected_when_teams_full(self):
        inst = MapInstance(sample_map())
        for name in ("a", "b", "c", "d"):
            self.assertTrue(inst.join(name, 1, now=1)[0])
        ok, reason = inst.join("eve", 1, now=2)
        self.assertFalse(ok)
        self.assertEqual(reason, "full")

    def test_lobby_timeout(self):
        inst = MapInstance(sample_map())
        inst.join("alice", 800, now=0)
        self.assertFalse(inst.lobby_timed_out(900, now=899))
        self.assertTrue(inst.lobby_timed_out(900, now=900))

    def test_admin_leave_transfers(self):
        inst = MapInstance(sample_map())
        inst.join("alice", 800, now=1)
        inst.join("bob", 800, now=2)
        new_admin = inst.leave("alice")
        self.assertEqual(new_admin, "bob")
        self.assertEqual(inst.admin, "bob")

    def test_empty_lobby_resets(self):
        inst = MapInstance(sample_map())
        inst.join("alice", 800, now=1)
        inst.leave("alice")
        self.assertEqual(inst.state, STATE_IDLE)
        self.assertEqual(inst.player_count(), 0)

    def test_cannot_start_same_team(self):
        inst = MapInstance(sample_map())
        inst.join("alice", 800, now=1)
        inst.join("bob", 800, now=2)
        inst.set_team("bob", TEAM_A)
        ok, reason = inst.can_start()
        self.assertFalse(ok)
        self.assertEqual(reason, "need_players")

    def test_kill_ends_match_at_target(self):
        inst = MapInstance(sample_map())
        inst.join("alice", 800, now=1)
        inst.join("bob", 800, now=2)
        inst.begin_buy(0)
        inst.begin_playing()
        inst.apply_player_kill("alice", "bob", 100)
        inst.apply_player_kill("alice", "bob", 100)
        result = inst.apply_player_kill("alice", "bob", 100)
        self.assertEqual(result["winner"], TEAM_A)
        self.assertEqual(inst.players["alice"].kills, 3)
        self.assertEqual(inst.players["bob"].deaths, 3)
        self.assertEqual(inst.players["alice"].points, 1100)

    def test_gadget_fills_then_replaces_first(self):
        inst = MapInstance(sample_map())
        inst.join("alice", 800, now=1)
        w1 = {"id": "g1", "type": "gadget"}
        w2 = {"id": "g2", "type": "gadget"}
        w3 = {"id": "g3", "type": "gadget"}
        w4 = {"id": "g4", "type": "gadget"}
        self.assertEqual(inst.record_purchase("alice", w1, 3)[0], 0)
        self.assertEqual(inst.record_purchase("alice", w2, 3)[0], 1)
        self.assertEqual(inst.record_purchase("alice", w3, 3)[0], 2)
        idx, old = inst.record_purchase("alice", w4, 3)
        self.assertEqual(idx, 0)
        self.assertEqual(old, "g1")
        self.assertEqual(inst.players["alice"].gadgets[0], "g4")

    def test_first_empty_or_first(self):
        self.assertEqual(first_empty_or_first([None, "a"], 2), 0)
        self.assertEqual(first_empty_or_first(["a", None], 2), 1)
        self.assertEqual(first_empty_or_first(["a", "b"], 2), 0)


if __name__ == "__main__":
    unittest.main()
