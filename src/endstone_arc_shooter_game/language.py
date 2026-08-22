# -*- coding: utf-8 -*-
from pathlib import Path

PLUGIN_DATA_DIR = Path("plugins/ARCShooterGame")

DEFAULT_TEXTS = {
    "MENU_TITLE": "射击游戏",
    "MENU_CONTENT": "选择大厅或配置地图。",
    "BTN_LOBBY_LIST": "大厅列表",
    "BTN_CONFIG_MAPS": "配置地图",
    "CLOSE": "关闭",
    "BACK": "返回",
    "CMD_PLAYER_ONLY": "该指令只能由玩家使用。",
    "CMD_UNKNOWN_SUB": "§c未知子命令：{0}。可用：/gs、/gs leave、/gs reload",
    "CMD_NO_PERMISSION": "§c你没有权限执行此操作。",
    "RELOAD_OK": "§a已重载地图、武器与设置。",
    "RELOAD_FAIL": "§c重载失败：{0}",
    "PANEL_ERROR": "§c打开菜单时出错，请查看服务端日志。",
    "MODE_tdm": "团队死斗",
    "MODE_ffa": "个人死斗",
    "MODE_ctf": "夺旗战",
    "LOBBY_STATUS_WAITING": "等待中",
    "LOBBY_STATUS_BUYING": "购买中",
    "LOBBY_STATUS_PLAYING": "进行中",
    "LOBBY_LIST_TITLE": "大厅列表",
    "LOBBY_LIST_CONTENT": "加入现有大厅，或创建新大厅。",
    "LOBBY_LIST_EMPTY": "当前没有大厅，点击下方创建。",
    "LOBBY_LIST_BUTTON": "{0} · {1} · {2} · {3}人 · {4}",
    "LOBBY_LIST_NO_MAP": "未选地图",
    "LOBBY_LIST_NO_MODE": "未选模式",
    "BTN_CREATE_LOBBY": "创建大厅",
    "JOIN_FAIL_IN_GAME": "§c你已经在另一个大厅/比赛中。先 /gs leave。",
    "JOIN_FAIL_FULL": "§c该大厅人数已满。",
    "JOIN_FAIL_UNKNOWN": "§c找不到这个大厅。",
    "JOIN_OK": "§a§l[大厅] §r§a已加入大厅。房主：§e§l{0}§r\n§e请等待房主选择地图并开始比赛。",
    "JOIN_OK_ADMIN": "§a§l[大厅] §r§a你已创建大厅并成为房主。\n§e请在 15 分钟内选择地图并开始，否则大厅将自动解散。",
    "JOIN_OK_MATCH": "§a§l[比赛] §r§a已加入进行中的比赛。",
    "LOBBY_PLAYER_JOINED": "§e§l[大厅] §r§a玩家 §e§l{0}§r§a 加入了大厅（§e{1}§a/§e{2}§a 人）。",
    "LOBBY_PLAYER_JOINED_ADMIN": "§e§l[大厅] §r§a玩家 §e§l{0}§r§a 加入了你的大厅（§e{1}§a/§e{2}§a 人）。",
    "LOBBY_PLAYER_LEFT": "§e§l[大厅] §r§e玩家 §e§l{0}§r§e 离开了大厅（§e{1}§a/§e{2}§a 人）。",
    "LOBBY_PLAYER_LEFT_ADMIN": "§e§l[大厅] §r§e玩家 §e§l{0}§r§e 离开了你的大厅（§e{1}§a/§e{2}§a 人）。",
    "LOBBY_CREATED_BROADCAST": "§e§l[大厅] §r§a玩家 §e§l{0}§r§a 创建了新大厅（地图：§e{1}§a，模式：§e{2}§a）。",
    "LEAVE_OK": "§e你已离开大厅。",
    "LEAVE_NOT_IN": "§c你不在任何大厅或比赛中。",
    "KICKED": "§c你被移出了大厅。",
    "KICK_OK": "§a已将 {0} 移出大厅。",
    "ADMIN_TRANSFERRED": "§e原房主已离开，你成为新房主。",
    "LOBBY_DISSOLVED_TIMEOUT": "§e大厅已超过 15 分钟未开始，已解散。",
    "LOBBY_DISSOLVED_EMPTY": "大厅已空，已解散。",
    "LOBBY_TITLE": "大厅",
    "LOBBY_PLAYER_COUNT": "当前人数：{0}/{1}",
    "LOBBY_PLAYER_LIST": "玩家：{0}",
    "BTN_REFRESH": "刷新",
    "LOBBY_CONTENT": "地图：{0}\n模式：{1}\n房主：{2}\n剩余准备时间：{3}\n目标分数：{4}\n比赛时长：{5} 分钟\n单队上限：{6}\n\n{7}\n{8}",
    "LOBBY_CONTENT_HINT": "§7{0}",
    "LOBBY_HINT_NEED_MAP": "请先点击下方「选择地图与模式」。",
    "LOBBY_HINT_NEED_MODE": "已选地图，请选择游戏模式。",
    "LOBBY_HINT_READY": "配置完成，可开始游戏。",
    "BTN_SELECT_MAP_MODE": "选择地图与模式",
    "BTN_CHANGE_MAP_MODE": "更换地图与模式",
    "TEAM_LINE": "{0}（{1}/{2}）\n{3}",
    "NO_PLAYER": "（无人）",
    "BTN_START": "开始游戏",
    "BTN_ASSIGN": "调整分队",
    "BTN_KICK": "踢出玩家",
    "BTN_SELECT_MAP": "选择地图",
    "BTN_SELECT_MODE": "选择模式",
    "BTN_LEAVE": "离开大厅",
    "START_NEED_PLAYERS": "§c至少需要两名玩家，且两队都要有人。",
    "START_NEED_MAP": "§c请先选择地图和游戏模式。",
    "START_NEED_SPAWNS": "§c地图出生点配置不完整。",
    "START_BROADCAST": "§a§l[比赛] §r§a比赛即将开始！正在清空背包并传送。\n§e购买时间 §l{0}§r§e 秒。§6右键弧光币§e打开商店。",
    "BUY_TIME_TIP": "§e§l购买 {0}s §r| {1} {2} §7-§r {3} {4} | 点数 {5} | §6右键弧光币",
    "PLAYING_TIP": "§c§l剩余 {0}s §r| {1} {2} §7-§r {3} {4} | 点数 {5} | §6右键弧光币",
    "GAME_STARTED": "§a§l[比赛] §r§a购买结束，战斗开始！§e限时 §l{0}§r§e 分钟，先达到 §l{1}§r§e 分或时间结束时比分高者获胜。",
    "MATCH_END_TIME": "§6§l[比赛] §r§e时间到！比赛结束。",
    "ASSIGN_TITLE": "调整分队",
    "ASSIGN_CONTENT": "点击玩家可在两队之间切换。",
    "ASSIGN_BUTTON": "{0} · 当前 {1}",
    "ASSIGN_DONE": "§a已将 {0} 分到 {1}。",
    "ASSIGN_TEAM_FULL": "§c目标队伍人数已满。",
    "KICK_TITLE": "踢出玩家",
    "KICK_CONTENT": "选择要移出大厅的玩家。",
    "KICK_SELF": "§c不能踢出自己，请直接离开。",
    "MATCH_TITLE": "比赛中 · {0}",
    "MATCH_CONTENT": "{0} {1}  -  {2} {3}\n你的队伍：{4}\n战争点数：{5}\n击杀 {6} / 死亡 {7}\n\n§6右键弧光币§r 打开商店。",
    "BTN_SHOP": "打开商店",
    "BTN_LEAVE_MATCH": "离开比赛",
    "LEAVE_MATCH_CONFIRM_TITLE": "确认离开比赛？",
    "LEAVE_MATCH_CONFIRM": "离开后将传送回原位并恢复背包，本局战绩仍会记入结算。",
    "BTN_CONFIRM": "确认离开",
    "BTN_CANCEL": "取消",
    "SHOP_NOT_IN_MATCH": "§c只有比赛开始后才能打开商店。",
    "SHOP_TITLE": "武器商店",
    "SHOP_CONTENT": "战争点数：§e§l{0}§r\n主武器前 {1} 格，副武器 {2} 格，道具 {3} 格。\n子弹等附属物品会放到背包末尾。",
    "SHOP_PRIMARY": "主武器",
    "SHOP_SECONDARY": "副武器",
    "SHOP_ARMOR": "护甲",
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
    "PLAYER_KILLED": "§c§l[死亡] §r§7你被 §c{0}§7 击杀。主副武器与弹药已重新发放。",
    "SCORE_UPDATE": "§e比分 {0} {1} - {2} {3}",
    "MATCH_END_HEADER": "§6========== 比赛结束 ==========",
    "MATCH_END_TITLE": "比赛结束",
    "MATCH_END_TIME_NOTE": "时间到！",
    "MATCH_END_SCORE": "最终比分：{0} {1} - {2} {3}",
    "MATCH_END_WINNER": "§a获胜：{0}",
    "MATCH_END_DRAW": "§e本局没有获胜队伍。",
    "MATCH_END_STATS_TEAM": "§l{0}",
    "MATCH_END_STATS_PLAYER": "{0}：击杀{1} 死亡{2}",
    "MATCH_END_REWARDS_HEADER": "§6§l赛后奖励",
    "MATCH_END_REWARD_MONEY": "{0}：§a金钱 +{1}",
    "MATCH_END_REWARD_CONTRIB": "{0}：§b公会贡献 +{1}",
    "MATCH_END_REWARD_BOTH": "{0}：§a金钱 +{1} §7| §b公会贡献 +{2}",
    "MATCH_END_REWARD_NONE": "{0}：§7无奖励（K-D ≤ 0）",
    "MATCH_END_FOOTER": "§6==============================",
    "RESTORED": "§a已恢复比赛前的背包与位置。",
    "BACKUP_RECOVERED": "§a检测到未完成的比赛备份，已恢复你的背包与位置。",
    "MAP_SELECT_TITLE": "选择地图",
    "MAP_SELECT_CONTENT": "仅显示区域完整、且至少有一种可玩模式的地图。",
    "MAP_SELECT_EMPTY": "当前没有可玩地图。请让 OP 用 /gs 配置地图。",
    "MAP_SELECT_BUTTON": "{0}",
    "MAP_SELECT_BUTTON_DETAIL": "{0} · {1} · {2}分钟",
    "MAP_SELECT_BUTTON_MULTI": "{0} · {1}种模式",
    "MAP_SELECT_OK": "§a已选择地图：{0}",
    "MAP_SELECT_BUSY": "§c该地图正被其他大厅使用。",
    "MAP_SELECT_NOT_READY": "§c该地图尚未配置完成。",
    "MODE_SELECT_TITLE": "选择模式",
    "MODE_SELECT_CONTENT": "地图：{0}\n仅显示该地图已配置且可开局的模式。",
    "MODE_SELECT_EMPTY": "该地图没有可开局模式，请先配置。",
    "MODE_SELECT_BUTTON": "{0}",
    "MODE_SELECT_OK": "§a已选择模式：{0}",
    "CONFIG_MAPS_TITLE": "配置地图",
    "CONFIG_MAPS_CONTENT": "OP 可创建地图、设置区域角点与游戏模式。",
    "CONFIG_MAPS_EMPTY": "还没有地图，点击下方创建。",
    "CONFIG_MAP_BUTTON": "{0}",
    "CONFIG_MAP_BUTTON_STATUS": "{0} · {1}",
    "MAP_STATUS_READY": "可开局",
    "MAP_STATUS_MISSING_REGION": "缺区域",
    "MAP_STATUS_NO_MODES": "无模式",
    "MAP_STATUS_MISSING_SPAWN_A": "缺红队复活点",
    "MAP_STATUS_MISSING_SPAWN_B": "缺蓝队复活点",
    "MAP_STATUS_UNIMPLEMENTED": "模式未实装",
    "MAP_STATUS_MODE_NOT_FOUND": "模式缺失",
    "BTN_CREATE_MAP": "创建地图",
    "CREATE_MAP_TITLE": "创建地图",
    "CREATE_MAP_NAME": "地图名称",
    "CREATE_MAP_OK": "§a已创建地图：{0}",
    "CREATE_MAP_FAIL": "§c创建失败：{0}",
    "MAP_EDIT_TITLE": "编辑地图 · {0}",
    "MAP_EDIT_CONTENT": "维度：{0}\n区域：{1}\n已配置模式：{2}",
    "MAP_EDIT_BODY": "维度：{0}\n角点1：{1}\n角点2：{2}\n\n模式状态：\n{3}",
    "MAP_POS_UNSET": "未设置",
    "MAP_POS_FMT": "{0:.1f}, {1:.1f}, {2:.1f}",
    "MAP_MODE_LINE": "· {0}：{1}",
    "MAP_MODE_LINE_READY": "· {0}：可开局 · {1}分钟",
    "MAP_REGION_NONE": "未设置",
    "MAP_REGION_SET": "已设置",
    "MAP_MODES_NONE": "无",
    "BTN_SET_POS1": "设为角点1（当前位置）",
    "BTN_SET_POS2": "设为角点2（当前位置）",
    "BTN_ADD_MODE": "添加游戏模式",
    "BTN_RENAME_MAP": "修改地图名称",
    "BTN_DELETE_MAP": "删除地图",
    "RENAME_MAP_TITLE": "修改地图名称",
    "RENAME_MAP_OK": "§a地图已改名为：{0}",
    "RENAME_MAP_FAIL": "§c改名失败：{0}",
    "DELETE_MAP_CONFIRM_TITLE": "确认删除地图？",
    "DELETE_MAP_CONFIRM": "将永久删除地图「{0}」及其所有模式配置，此操作不可撤销。",
    "DELETE_MAP_OK": "§a已删除地图：{0}",
    "DELETE_MAP_BUSY": "§c该地图正被大厅使用，无法删除。",
    "POS_SET_OK": "§a已记录角点{0}：{1:.1f}, {2:.1f}, {3:.1f}",
    "ADD_MODE_TITLE": "添加游戏模式",
    "ADD_MODE_DROPDOWN": "游戏模式",
    "ADD_MODE_OK": "§a已添加模式：{0}",
    "ADD_MODE_EXISTS": "§c该地图已有此模式。",
    "ADD_MODE_UNIMPLEMENTED": "§c该模式尚未实装，无法添加。",
    "MODE_EDIT_TITLE": "编辑模式 · {0}",
    "MODE_EDIT_CONTENT": "目标分数：{0}\n单队人数上限：{1}\n比赛时长：{2} 分钟\n红队复活点：{3}\n蓝队复活点：{4}",
    "MODE_EDIT_BODY": "目标分数：{0}\n单队人数上限：{1}\n比赛时长：{2} 分钟\n红队复活点：{3} 个\n蓝队复活点：{4} 个\n\n状态：{5}",
    "MODE_STATUS_READY": "可开局",
    "MODE_BUTTON_READY": "{0} · {1}分钟 · 可开局",
    "MODE_BUTTON_ISSUE": "{0} · {1}",
    "BTN_EDIT_RULES": "修改规则（分数 / 人数 / 时长）",
    "BTN_MANAGE_SPAWN_A": "管理红队复活点",
    "BTN_MANAGE_SPAWN_B": "管理蓝队复活点",
    "SPAWN_EDIT_TITLE": "复活点 · {0}",
    "SPAWN_EDIT_BODY": "共 {0} 个复活点。\n\n{1}",
    "SPAWN_EDIT_EMPTY": "（暂无复活点）",
    "SPAWN_EDIT_LINE": "#{0}  {1:.1f}, {2:.1f}, {3:.1f}",
    "BTN_ADD_SPAWN_HERE": "添加当前位置",
    "BTN_DELETE_SPAWN_COORD": "删除 #{0} ({1:.1f}, {2:.1f}, {3:.1f})",
    "BTN_ADD_SPAWN_A": "当前位置加入红队复活点",
    "BTN_ADD_SPAWN_B": "当前位置加入蓝队复活点",
    "BTN_EDIT_MODE_SETTINGS": "修改模式设置",
    "BTN_DELETE_SPAWN": "删除复活点 #{0} ({1})",
    "SPAWN_ADDED": "§a已添加{0}复活点。",
    "SPAWN_REMOVED": "§a已删除复活点。",
    "MODE_SETTINGS_TITLE": "模式设置 · {0}",
    "MODE_SETTINGS_TARGET": "目标分数",
    "MODE_SETTINGS_MAX": "单队人数上限",
    "MODE_SETTINGS_MATCH_TIME": "比赛时长（分钟）",
    "MODE_SETTINGS_OK": "§a模式设置已保存。",
    "REGION_PULLBACK": "§e你已离开地图区域，已传送回复活点。",
}


def _decode_lang_value(value: str) -> str:
    return value.replace("\\n", "\n")


def _encode_lang_value(value: str) -> str:
    return value.replace("\n", "\\n")


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
                    bucket[key.strip()] = _decode_lang_value(value.strip())

    def _ensure_defaults(self):
        bucket = LanguageManager.language_dict[self.language_code]
        missing = [(k, v) for k, v in DEFAULT_TEXTS.items() if not bucket.get(k)]
        if not missing:
            return
        with self.language_file_path.open("a", encoding="utf-8") as f:
            for key, value in missing:
                bucket[key] = value
                f.write(f"{key}={_encode_lang_value(value)}\n")

    def GetText(self, key: str, lang_code=None) -> str:
        target_lang = (lang_code or self.language_code).upper()
        if target_lang not in LanguageManager.language_dict:
            LanguageManager(target_lang)
        bucket = LanguageManager.language_dict.get(target_lang, {})
        text = bucket.get(key)
        if text:
            return text
        return DEFAULT_TEXTS.get(key, key)
