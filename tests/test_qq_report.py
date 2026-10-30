# -*- coding: utf-8 -*-
"""枪战战报 → QQ 群：战报文本 + 插件侧发送（不连服务器，全 Mock）。

覆盖三件事：
1. 战报文本拼得对不对（比分/胜方/战绩/名单）。
2. 插件在开赛、收尾两个点各发一次，且走的是群服互通插件的 custom 事件。
3. 开关关掉、群服互通插件不在、群服互通插件抛异常——都不许影响对局。
"""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _endstone_stub_shooter as stub  # noqa: E402  安装 endstone stub
stub.add_src_to_path()

from endstone_arc_shooter_game.arc_shooter_game_plugin import (  # noqa: E402
    ARCShooterGamePlugin,
)
from endstone_arc_shooter_game.qq_report import (  # noqa: E402
    build_end_report,
    build_start_report,
)


def make_player(name, team, kills=0, deaths=0, assists=0, tk=0, still_in=True):
    return SimpleNamespace(name=name, team=team, kills=kills, deaths=deaths,
                            assists=assists, team_kills=tk, still_in=still_in)


def make_lobby(players=None, score_a=0, score_b=0, map_name="ARCShooterGame",
               mode="tdm"):
    rows = list(players or [])

    def team_name(team_id):
        return "红队" if team_id == "a" else "蓝队"

    return SimpleNamespace(
        score_a=score_a,
        score_b=score_b,
        display_name=map_name,
        active_mode=mode,
        mode=mode,
        target_score=20,
        match_time_minutes=5,
        map_cfg={"display_name": map_name, "mode": mode},
        team_name=team_name,
        online_players=lambda: [p for p in rows if p.still_in],
        result_rows=lambda: list(rows),
    )


class FakeSettings:
    def __init__(self, values):
        self.values = dict(values)

    def GetSetting(self, key):
        return self.values.get(key)


class FakeConfigStore:
    def __init__(self, values):
        self.settings = FakeSettings(values)


class FakeQQPlugin:
    """群服互通插件的替身：只记 api_send_event 的调用。"""

    def __init__(self):
        self.calls = []

    def api_send_event(self, event_type, display_name, raw_player_name,
                       message="", **kwargs):
        self.calls.append({
            "event_type": event_type,
            "display_name": display_name,
            "raw_player_name": raw_player_name,
            "message": message,
            "kwargs": kwargs,
        })
        return True


class OldQQPlugin:
    """老版本群服互通插件：只认位置参数，不吃 message/force_text。"""

    def __init__(self):
        self.calls = []

    def api_send_event(self, event_type, display_name, raw_player_name,
                       message=""):
        self.calls.append((event_type, display_name, raw_player_name, message))
        return True


class BoomQQPlugin:
    def api_send_event(self, *a, **k):
        raise RuntimeError("中枢断了")


def make_plugin(qq=None, settings=None):
    """跳过 __init__（依赖文件存储），只挂战报这条链要用的属性。"""
    plugin = object.__new__(ARCShooterGamePlugin)
    plugin.logger = SimpleNamespace(info=lambda m: None,
                                    warning=lambda m: None,
                                    error=lambda m: None)
    plugin._t = lambda key, **kw: key
    plugin.config_store = FakeConfigStore(settings if settings is not None else {
        "QQ_REPORT_ENABLED": "1",
        "QQ_REPORT_START": "1",
        "QQ_REPORT_END": "1",
    })

    def get_plugin(name):
        return qq if (qq is not None and name == "arc_qq_sync_astrbot") else None

    plugin.server = SimpleNamespace(
        online_players=[],
        plugin_manager=SimpleNamespace(get_plugin=get_plugin),
    )
    return plugin


class ReportTextTests(unittest.TestCase):
    def test_start_report_has_map_mode_and_rosters(self):
        lobby = make_lobby([
            make_player("Aqing", "a"),
            make_player("BloodShot", "a"),
            make_player("lowkey", "b"),
        ])
        text = build_start_report(lobby, map_label="ARCShooterGame",
                                  mode_label="团队死斗")
        self.assertIn("开局", text)
        self.assertIn("ARCShooterGame", text)
        self.assertIn("团队死斗", text)
        self.assertIn("Aqing", text)
        self.assertIn("BloodShot", text)
        self.assertIn("lowkey", text)
        self.assertIn("20", text)
        self.assertIn("5", text)

    def test_start_report_splits_two_teams(self):
        lobby = make_lobby([make_player("Aqing", "a"),
                            make_player("lowkey", "b")])
        lines = build_start_report(lobby).splitlines()
        red = [ln for ln in lines if "Aqing" in ln]
        blue = [ln for ln in lines if "lowkey" in ln]
        self.assertEqual(len(red), 1)
        self.assertEqual(len(blue), 1)
        self.assertNotEqual(red[0], blue[0])

    def test_end_report_has_score_winner_and_stats(self):
        lobby = make_lobby([
            make_player("BloodShot", "a", kills=3, deaths=1, assists=2),
            make_player("v0lv3r", "a", kills=1, deaths=2, assists=0),
            make_player("lowkey", "b", kills=2, deaths=3, assists=1, tk=1),
        ], score_a=5, score_b=3)
        text = build_end_report(lobby, "a", map_label="ARCShooterGame")
        self.assertIn("战报", text)
        self.assertIn("5 - 3", text)
        self.assertIn("红队", text)
        self.assertIn("获胜", text)
        self.assertIn("BloodShot 3/1/2", text)
        self.assertIn("v0lv3r 1/2/0", text)
        self.assertIn("lowkey 2/3/1", text)
        self.assertIn("TK1", text)

    def test_end_report_sorts_by_kills(self):
        lobby = make_lobby([
            make_player("low", "a", kills=1),
            make_player("high", "a", kills=5),
        ], score_a=6, score_b=0)
        text = build_end_report(lobby, "a")
        self.assertLess(text.index("high"), text.index("low"))

    def test_end_report_draw(self):
        lobby = make_lobby([make_player("Aqing", "a")], score_a=3, score_b=3)
        self.assertIn("平局", build_end_report(lobby, None))

    def test_end_report_timeout_note(self):
        lobby = make_lobby([make_player("Aqing", "a")], score_a=4, score_b=2)
        self.assertIn("时间到", build_end_report(lobby, "a", timed_out=True))

    def test_empty_team_shows_placeholder(self):
        lobby = make_lobby([make_player("Aqing", "a")], score_a=1, score_b=0)
        self.assertIn("（无）", build_end_report(lobby, "a"))

    def test_broken_lobby_does_not_raise(self):
        class Broken:
            def __getattr__(self, name):
                raise RuntimeError("炸了")
        self.assertTrue(build_start_report(Broken()))
        self.assertTrue(build_end_report(Broken(), "a"))


class PluginSideTests(unittest.TestCase):
    def test_start_sends_one_custom_event(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq)
        plugin._qq_report_start(make_lobby([make_player("Aqing", "a")]))
        self.assertEqual(len(qq.calls), 1)
        call = qq.calls[0]
        self.assertEqual(call["event_type"], "custom")
        self.assertIn("开局", call["message"])
        self.assertTrue(call["kwargs"].get("force_text"))

    def test_end_sends_score_of_that_moment(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq)
        lobby = make_lobby([make_player("Aqing", "a", kills=5)], score_a=5,
                           score_b=2)
        plugin._qq_report_end(lobby, "a")
        self.assertEqual(len(qq.calls), 1)
        self.assertIn("5 - 2", qq.calls[0]["message"])
        self.assertIn("Aqing 5/0/0", qq.calls[0]["message"])

    def test_dissolved_lobby_sends_nothing(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq)
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), None)
        self.assertEqual(qq.calls, [])

    def test_timeout_sends_report(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq)
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), None,
                              timed_out=True)
        self.assertEqual(len(qq.calls), 1)
        self.assertIn("时间到", qq.calls[0]["message"])

    def test_master_switch_off_sends_nothing(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq, settings={"QQ_REPORT_ENABLED": "0",
                                           "QQ_REPORT_START": "1",
                                           "QQ_REPORT_END": "1"})
        plugin._qq_report_start(make_lobby([make_player("Aqing", "a")]))
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), "a")
        self.assertEqual(qq.calls, [])

    def test_start_only_switch(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq, settings={"QQ_REPORT_ENABLED": "1",
                                           "QQ_REPORT_START": "0",
                                           "QQ_REPORT_END": "1"})
        plugin._qq_report_start(make_lobby([make_player("Aqing", "a")]))
        self.assertEqual(qq.calls, [])
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), "a")
        self.assertEqual(len(qq.calls), 1)

    def test_end_only_switch(self):
        qq = FakeQQPlugin()
        plugin = make_plugin(qq, settings={"QQ_REPORT_ENABLED": "1",
                                           "QQ_REPORT_START": "1",
                                           "QQ_REPORT_END": "0"})
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), "a")
        self.assertEqual(qq.calls, [])
        plugin._qq_report_start(make_lobby([make_player("Aqing", "a")]))
        self.assertEqual(len(qq.calls), 1)

    def test_flag_parsing(self):
        plugin = make_plugin(settings={"QQ_REPORT_ENABLED": "1",
                                       "QQ_REPORT_START": "false",
                                       "QQ_REPORT_END": "OFF"})
        self.assertTrue(plugin._qq_report_flag("QQ_REPORT_ENABLED"))
        self.assertFalse(plugin._qq_report_flag("QQ_REPORT_START"))
        self.assertFalse(plugin._qq_report_flag("QQ_REPORT_END"))

    def test_missing_qq_plugin_is_silent(self):
        plugin = make_plugin(qq=None)
        plugin._qq_report_start(make_lobby([make_player("Aqing", "a")]))
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), "a")

    def test_qq_plugin_exception_does_not_break_match(self):
        plugin = make_plugin(qq=BoomQQPlugin())
        plugin._qq_report_start(make_lobby([make_player("Aqing", "a")]))
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), "a")

    def test_old_qq_plugin_signature_still_works(self):
        qq = OldQQPlugin()
        plugin = make_plugin(qq)
        plugin._qq_report_end(make_lobby([make_player("Aqing", "a")]), "a")
        self.assertEqual(len(qq.calls), 1)
        self.assertEqual(qq.calls[0][0], "custom")
        self.assertIn("战报", qq.calls[0][3])


if __name__ == "__main__":
    unittest.main()
