# -*- coding: utf-8 -*-
"""枪战对局战报 → QQ 群（经群服互通插件 arc_qq_sync_astrbot）。

为什么是这个插件干这活
----------------------
"往群里发消息"的接口**只有群服互通插件有**（api_send_event /
api_send_message / api_send_raw），枪战插件自己不往群里发任何东西。
但对局的开始和结束只有枪战插件知道——它掌握大厅状态、比分、每个
人的战绩。所以由枪战插件在**开赛**和**收尾**这两个瞬间调群服互通
插件把战报发出去。

为什么不复用游戏内那份战报文本
------------------------------
``_match_result_content`` 是给游戏内弹窗用的：带 § 颜色码、还跟着
一整段"赛后奖励（金钱 / 公会贡献）"。QQ 是纯文本，群里也没人关心
公会贡献，逐行读起来像日志。这里自己拼一份紧凑的：比分 + 每人
击杀/死亡/助攻。

失败一律静默
------------
群服互通插件不在、没连中枢、调用失败——全部跳过。战报是锦上添花，
绝不能因为发不出去把一场对局搞崩。
"""

from typing import Any, List, Optional

#: 队伍常量——和 session.py 里的 TEAM_A / TEAM_B 一致。
TEAM_A = "a"
TEAM_B = "b"

#: 队名前面的图标（QQ 群是纯文本，emoji 没问题）。
_ICON = {TEAM_A: "🔴", TEAM_B: "🔵"}

#: 队名拿不到时的兜底。
_DEFAULT_TEAM = {TEAM_A: "红队", TEAM_B: "蓝队"}


def _attr(obj: Any, name: str, default: Any = None) -> Any:
    """安全取属性：Lobby 是 dataclass，字段名/类型都可能变，
    战报读不到字段最多少一行字，不能把对局搞崩。"""
    try:
        value = getattr(obj, name, default)
    except Exception:
        return default
    return default if value is None else value


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def team_name(lobby: Any, team_id: str) -> str:
    """队名（红队/蓝队，或地图自定义名）。"""
    fn = _attr(lobby, "team_name", None)
    if callable(fn):
        try:
            name = fn(team_id)
            if name:
                return str(name)
        except Exception:
            pass
    return _DEFAULT_TEAM.get(team_id, str(team_id))


def _online(lobby: Any) -> List[Any]:
    """还在大厅里的玩家（开局名单）。"""
    fn = _attr(lobby, "online_players", None)
    if callable(fn):
        try:
            return list(fn())
        except Exception:
            pass
    return []


def _rows(lobby: Any) -> List[Any]:
    """全部参战者（**含中途离开的人**，终局战报要留全）。"""
    fn = _attr(lobby, "result_rows", None)
    if callable(fn):
        try:
            rows = list(fn())
            if rows:
                return rows
        except Exception:
            pass
    players = _attr(lobby, "players", None)
    try:
        return list(players.values()) if players else []
    except Exception:
        return []


def _members(lobby: Any, team_id: str) -> List[Any]:
    out = []
    for ps in _rows(lobby):
        if str(_attr(ps, "team", "")) == team_id:
            out.append(ps)
    return out


def _sort_key(ps: Any):
    """排序：击杀多 → 助攻多 → 死亡少 → 名字。和游戏内统计一致。"""
    return (
        -_int(_attr(ps, "kills", 0)),
        -_int(_attr(ps, "assists", 0)),
        _int(_attr(ps, "deaths", 0)),
        str(_attr(ps, "name", "")),
    )


def _stat_line(ps: Any) -> str:
    """一个人物的战绩：``名字 3/1/2（TK1）``（击杀/死亡/助攻）。"""
    name = str(_attr(ps, "name", "?"))
    kills = _int(_attr(ps, "kills", 0))
    deaths = _int(_attr(ps, "deaths", 0))
    assists = _int(_attr(ps, "assists", 0))
    tk = _int(_attr(ps, "team_kills", 0))
    text = "{0} {1}/{2}/{3}".format(name, kills, deaths, assists)
    if tk:
        text += "（TK{0}）".format(tk)
    return text


def build_start_report(lobby: Any, *, map_label: str = "",
                       mode_label: str = "") -> str:
    """开局播报：地图、模式、两边名单、目标分与限时。"""
    map_label = map_label or str(_attr(lobby, "display_name", "") or "未知地图")
    mode_label = mode_label or str(_attr(lobby, "active_mode", "") or "")
    a_name = team_name(lobby, TEAM_A)
    b_name = team_name(lobby, TEAM_B)
    a_players = [str(_attr(p, "name", "")) for p in _online(lobby)
                 if str(_attr(p, "team", "")) == TEAM_A]
    b_players = [str(_attr(p, "name", "")) for p in _online(lobby)
                 if str(_attr(p, "team", "")) == TEAM_B]
    lines = [
        "🏁 弧光枪战 · 开局",
        "地图：{0} · 模式：{1}".format(map_label, mode_label),
        "{0} {1}：{2}".format(
            _ICON[TEAM_A], a_name,
            "、".join(a_players) if a_players else "（无）"),
        "{0} {1}：{2}".format(
            _ICON[TEAM_B], b_name,
            "、".join(b_players) if b_players else "（无）"),
    ]
    target = _int(_attr(lobby, "target_score", 0))
    minutes = _int(_attr(lobby, "match_time_minutes", 0))
    if target or minutes:
        lines.append("目标 {0} 分 · 限时 {1} 分钟".format(target, minutes))
    return "\n".join(lines)


def build_end_report(lobby: Any, winner: Optional[str], *,
                     timed_out: bool = False, map_label: str = "") -> str:
    """终局战报：比分、结果、两队每人 击杀/死亡/助攻。"""
    map_label = map_label or str(_attr(lobby, "display_name", "") or "未知地图")
    a_name = team_name(lobby, TEAM_A)
    b_name = team_name(lobby, TEAM_B)
    score_a = _int(_attr(lobby, "score_a", 0))
    score_b = _int(_attr(lobby, "score_b", 0))
    if winner == TEAM_A:
        result = "{0} {1} 获胜".format(_ICON[TEAM_A], a_name)
    elif winner == TEAM_B:
        result = "{0} {1} 获胜".format(_ICON[TEAM_B], b_name)
    else:
        result = "平局"
    if timed_out:
        result = "时间到 · " + result

    def _team_text(team_id: str) -> str:
        members = sorted(_members(lobby, team_id), key=_sort_key)
        if not members:
            return "（无）"
        return "、".join(_stat_line(ps) for ps in members)

    lines = [
        "🏁 弧光枪战 · 战报",
        "地图：{0}".format(map_label),
        "比分：{0} {1} - {2} {3}".format(a_name, score_a, score_b, b_name),
        "结果：{0}".format(result),
        "战绩（击杀/死亡/助攻）：",
        "{0} {1}：{2}".format(_ICON[TEAM_A], a_name, _team_text(TEAM_A)),
        "{0} {1}：{2}".format(_ICON[TEAM_B], b_name, _team_text(TEAM_B)),
    ]
    return "\n".join(lines)
