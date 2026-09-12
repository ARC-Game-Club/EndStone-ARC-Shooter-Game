# -*- coding: utf-8 -*-
"""射击游戏插件离线测试共享的 endstone stub（覆盖其全部顶层导入）。"""
import sys
import types

endstone = types.ModuleType("endstone")
endstone.__path__ = []


class GameMode:
    SURVIVAL = "SURVIVAL"
    ADVENTURE = "ADVENTURE"
    CREATIVE = "CREATIVE"
    SPECTATOR = "SPECTATOR"


endstone.GameMode = GameMode


class Player:
    """占位类型（插件仅用于类型标注）。"""


endstone.Player = Player


def _mod(name):
    m = types.ModuleType(name)
    sys.modules[name] = m
    setattr(endstone, name.split(".", 1)[1], m)
    return m


cmd_mod = _mod("endstone.command")
cmd_mod.Command = type("Command", (), {})
cmd_mod.CommandSender = type("CommandSender", (), {})

evt_mod = _mod("endstone.event")


def event_handler(*a, **k):
    def deco(fn):
        return fn
    return deco


evt_mod.event_handler = event_handler
for cls_name in (
    "ActorDamageEvent", "PlayerDeathEvent", "PlayerDropItemEvent",
    "PlayerInteractEvent", "PlayerItemConsumeEvent", "PlayerJoinEvent",
    "PlayerQuitEvent", "PlayerRespawnEvent",
):
    setattr(evt_mod, cls_name, type(cls_name, (), {}))

plugin_mod = _mod("endstone.plugin")
plugin_mod.Plugin = type("Plugin", (), {})

form_mod = _mod("endstone.form")


class _Control:
    def __init__(self, *a, **k):
        pass


form_mod.ActionForm = type("ActionForm", (_Control,), {})
form_mod.ModalForm = type("ModalForm", (_Control,), {})
form_mod.Dropdown = type("Dropdown", (_Control,), {})
form_mod.TextInput = type("TextInput", (_Control,), {})

sys.modules["endstone"] = endstone


def add_src_to_path():
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))
