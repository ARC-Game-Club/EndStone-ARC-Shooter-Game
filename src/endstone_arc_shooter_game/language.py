# -*- coding: utf-8 -*-
from pathlib import Path

PLUGIN_DATA_DIR = Path("plugins/ARCShooterGame")

DEFAULT_TEXTS = {
    "MENU_TITLE": "射击游戏",
    "MENU_CONTENT": "选择一张地图加入大厅。",
    "MENU_NO_MAPS": "当前没有可用地图。请管理员编辑 plugins/ARCShooterGame/maps.json 后使用 /tdm reload。",
    "MAP_BUTTON": "{0} [{1}] {2}人 · {3}",
    "MAP_STATUS_IDLE": "空闲",
    "MAP_STATUS_LOBBY": "等待中",
    "MAP_STATUS_PLAYING": "进行中",
    "MAP_STATUS_UNIMPLEMENTED": "模式未实装",
    "MODE_tdm": "团队死斗",
    "MODE_ffa": "个人死斗",
    "MODE_ctf": "夺旗战",
    "CLOSE": "关闭",
    "BACK": "返回",
    "CMD_PLAYER_ONLY": "该指令只能由玩家使用。",
    "CMD_NO_PERMISSION": "§c你没有权限执行此操作。",
    "RELOAD_OK": "§a已重载地图、武器与设置。",
    "RELOAD_FAIL": "§c重载失败：{0}",
    "HERE_POS": "当前坐标 x={0:.2f} y={1:.2f} z={2:.2f} 维度={3}",
    "HERE_JSON": '出生点 JSON：{{"x": {0:.2f}, "y": {1:.2f}, "z": {2:.2f}, "radius": 0}}',
    "JOIN_FAIL_IN_GAME": "§c你已经在另一张地图的对局/大厅中。先 /tdm leave。",
    "JOIN_FAIL_PLAYING": "§c该地图正在比赛中，请等本局结束。",
    "JOIN_FAIL_FULL": "§c该地图人数已满。",
    "JOIN_FAIL_MODE": "§c该游戏模式尚未实装。",
    "JOIN_FAIL_UNKNOWN": "§c找不到这张地图。",
    "JOIN_OK": "§a已加入地图 {0}。当前大厅管理员：{1}",
    "JOIN_OK_ADMIN": "§a你加入了地图 {0}，并成为本局大厅管理员。15 分钟内未开始将自动解散。",
    "LEAVE_OK": "§e你已离开 {0}。",
    "LEAVE_NOT_IN": "§c你不在任何大厅或比赛中。",
    "KICKED": "§c你被移出了地图 {0} 的大厅。",
    "KICK_OK": "§a已将 {0} 移出大厅。",
    "ADMIN_TRANSFERRED": "§e原管理员已离开，你成为地图 {0} 的新大厅管理员。",
    "LOBBY_DISSOLVED_TIMEOUT": "§e地图 {0} 的大厅已超过 15 分钟未开始，已解散。",
    "LOBBY_DISSOLVED_EMPTY": "地图 {0} 大厅已空，已解散。",
    "LOBBY_TITLE": "大厅 · {0}",
    "LOBBY_CONTENT": "模式：{0}\n管理员：{1}\n剩余准备时间：{2}\n目标分数：{3}\n单队上限：{4}\n\n{5}\n{6}",
    "TEAM_LINE": "{0}（{1}/{2}）\n{3}",
    "NO_PLAYER": "（无人）",
    "BTN_START": "开始游戏",
    "BTN_ASSIGN": "调整分队",
    "BTN_KICK": "踢出玩家",
    "BTN_LEAVE": "离开大厅",
    "START_NEED_PLAYERS": "§c至少需要两名玩家，且两队都要有人。",
    "START_NEED_SPAWNS": "§c地图出生点配置不完整。",
    "START_BROADCAST": "§a比赛即将开始！正在传送并清空背包，购买时间 {0} 秒。输入 /tdm buy 打开商店。",
    "BUY_TIME_TIP": "§e购买时间剩余 {0} 秒 | {1} {2} §7-§r {3} {4} | 点数 {5}",
    "PLAYING_TIP": "{0} {1} §7-§r {2} {3} | 点数 {4} | /tdm buy",
    "GAME_STARTED": "§a购买时间结束，战斗开始！先达到 {0} 分的队伍获胜。",
    "ASSIGN_TITLE": "调整分队",
    "ASSIGN_CONTENT": "点击玩家可在两队之间切换。",
    "ASSIGN_BUTTON": "{0} · 当前 {1}",
    "ASSIGN_DONE": "§a已将 {0} 分到 {1}。",
    "ASSIGN_TEAM_FULL": "§c目标队伍人数已满。",
    "KICK_TITLE": "踢出玩家",
    "KICK_CONTENT": "选择要移出大厅的玩家。",
    "KICK_SELF": "§c不能踢出自己，请直接离开。",
    "MATCH_TITLE": "比赛中 · {0}",
    "MATCH_CONTENT": "{0} {1}  -  {2} {3}\n你的队伍：{4}\n战争点数：{5}\n击杀 {6} / 死亡 {7}\n\n输入 /tdm buy 打开商店。",
    "BTN_SHOP": "打开商店",
    "BTN_LEAVE_MATCH": "离开比赛",
    "LEAVE_MATCH_CONFIRM_TITLE": "确认离开比赛？",
    "LEAVE_MATCH_CONFIRM": "离开后将传送回原位并恢复背包，本局战绩仍会记入结算。",
    "BTN_CONFIRM": "确认离开",
    "BTN_CANCEL": "取消",
    "SHOP_NOT_IN_MATCH": "§c只有比赛开始后才能打开商店。",
    "SHOP_TITLE": "武器商店",
    "SHOP_CONTENT": "战争点数：§e{0}§r\n主武器占用前 {1} 格，副武器随后 {2} 格，道具随后 {3} 格。\n子弹等附属物品会放到背包末尾。",
    "SHOP_PRIMARY": "主武器",
    "SHOP_SECONDARY": "副武器",
    "SHOP_GADGET": "道具",
    "SHOP_CAT_TITLE": "{0}商店",
    "SHOP_CAT_CONTENT": "战争点数：§e{0}§r\n点击购买。已有同类型武器时会替换对应格子。",
    "SHOP_ITEM": "{0} §7-§r {1}点{2}",
    "SHOP_OWNED": " §a(已持有)",
    "SHOP_EMPTY": "该分类暂无武器，请编辑 weapons.json。",
    "BUY_OK": "§a购买 {0}，剩余点数 {1}。",
    "BUY_FAIL_POINTS": "§c点数不足。需要 {0}，当前 {1}。",
    "BUY_FAIL_UNKNOWN": "§c未知武器。",
    "SHOP_NO_SLOT": "§c该武器类型的持有数量配置为 0。",
    "KILL_ENEMY": "§a击杀 {0}！队伍 +1，奖励 {1} 点数（当前 {2}）。",
    "KILL_TEAM": "§c误杀队友 {0}，队伍分数 -1。",
    "PLAYER_KILLED": "§7你被 {0} 击杀。",
    "SCORE_UPDATE": "§e比分 {0} {1} - {2} {3}",
    "MATCH_END_HEADER": "§6========== 比赛结束 ==========",
    "MATCH_END_WINNER": "§a获胜：{0}",
    "MATCH_END_DRAW": "§e本局没有获胜队伍。",
    "MATCH_END_STATS_TEAM": "§l{0}",
    "MATCH_END_STATS_PLAYER": "{0}：击杀{1} 死亡{2}",
    "MATCH_END_FOOTER": "§6==============================",
    "RESTORED": "§a已恢复比赛前的背包与位置。",
    "BACKUP_RECOVERED": "§a检测到未完成的比赛备份，已恢复你的背包与位置。",
    "PANEL_ERROR": "§c打开菜单时出错，请查看服务端日志。",
}


class LanguageManager:
    language_dict = {}

    def __init__(self, default_language_code: str):
        self.language_code = (default_language_code or "ZH-CN").upper()
        if self.language_code not in LanguageManager.language_dict:
            LanguageManager.language_dict[self.language_code] = {}
        self.language_file_path = PLUGIN_DATA_DIR / f"{self.language_code}.txt"
        self._load_language_file()
        self._ensure_defaults()

    def _load_language_file(self):
        PLUGIN_DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not self.language_file_path.exists():
            self.language_file_path.touch()
        bucket = LanguageManager.language_dict[self.language_code]
        with self.language_file_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    key, value = line.split("=", 1)
                    bucket[key.strip()] = value.strip()

    def _ensure_defaults(self):
        bucket = LanguageManager.language_dict[self.language_code]
        missing = [(k, v) for k, v in DEFAULT_TEXTS.items() if not bucket.get(k)]
        if not missing:
            return
        with self.language_file_path.open("a", encoding="utf-8") as f:
            for key, value in missing:
                bucket[key] = value
                f.write(f"{key}={value}\n")

    def GetText(self, key: str, lang_code=None) -> str:
        target_lang = (lang_code or self.language_code).upper()
        if target_lang not in LanguageManager.language_dict:
            LanguageManager(target_lang)
        bucket = LanguageManager.language_dict.get(target_lang, {})
        text = bucket.get(key)
        if text:
            return text
        return DEFAULT_TEXTS.get(key, key)
