# EndStone ARC Shooter Game / 弧光射击游戏

[![版本](https://img.shields.io/badge/版本-0.4.18-blue.svg)](https://github.com/ARC-Minecraft/EndStone-ARC-Shooter-Game)
[![EndStone](https://img.shields.io/badge/EndStone-0.10+-green.svg)](https://github.com/EndstoneMC/endstone)

服务器内可配置多张射击地图。目前实装 **团队死斗（TDM）**，通过 `/gs` 菜单创建大厅、选择地图与模式开局。

TDM 固定使用 **军械库（armory）** 配装：赛外配置 5 套预设，开局进入购买/配置窗（全员无敌、可自由跑动）后右键弧光币换装，正式开赛后收回弧光币。

## 安装

```bash
pip install build
python -m build
```

依赖插件：`arc_attribute_core`（对局 buff：速度/跳跃提升经其 buff 队列统一管理，清场只撤自己来源）与 `arc_inventory`（配装背包）。

把 `dist/endstone_arc_shooter_game-0.4.17-py3-none-any.whl` 放到服务器 `plugins/`，重启。首次启动会生成：

```
plugins/ARCShooterGame/
  shooter.db
  settings.yml
  weapons.json
  ZH-CN.txt
```

## 指令

| 指令 | 说明 |
|---|---|
| `/gs` | 主菜单：大厅列表 / 军械库 / 枪手排行榜 / 个人信息 / 配置地图（OP） |
| `/gs leave` | 离开大厅或比赛 |
| `/gs reload` | OP：重载地图、武器、设置 |

比赛中 **弧光币（快捷栏第 9 格）右键** 打开军械库：仅在开局购买/配置窗或重生无敌窗内可换装；超时后弧光币收回。

## 军械库与等级

1. `/gs` → **军械库**（大厅等待中也可编辑；比赛中仅购买/配置窗内可改）。
2. **5 套预设**：每人 5 套，初始均为 Lv.0 默认配装（`m4` / `m1911` / `silencefd` / `mk2_grenade`）。
3. 按槽位（主/副/近战/护甲/道具）→ 分类 → 已解锁武器；未解锁显示所需等级。
4. 配装写入 `shooter.db`（`player_loadout_presets` + 当前激活套）；开局按等级校验，非法槽位回退默认。

**经验 / 等级 / 排行榜**

| 规则 | 数值 |
|---|---|
| 击杀当场 XP | `XP_PER_KILL`（默认 5） |
| 每级所需 XP | `XP_PER_LEVEL`（默认 100） |
| 最高等级 | `MAX_LEVEL`（默认 100，满级后仍可累计 XP） |
| 胜方结算加成 | 对击杀基础 XP 再补 `floor(kills×XP_PER_KILL×XP_WIN_BONUS_PERCENT/100)` |
| 队内 MVP | 结算再 `队伍人数 × XP_MVP_PER_TEAMMATE`（默认每人 10，双方各一名） |

资料页展示等级、场次（胜/负/平）、MVP 细分；`/gs` → **枪手排行榜** 按 KD 降序展示全体玩家及头衔。

## 流程

1. 玩家 `/gs` → **大厅列表**，可创建或加入大厅；可先配置 **军械库**。
2. 房主在大厅内点击 **选择地图与模式**（仅显示已配置完成、且未被其它大厅占用的地图）。
3. 从首位玩家加入起计时，默认 **15 分钟**未开局则解散大厅。
4. 房主点击开始后先进入 **传送倒计时**（默认 5 秒），结束后备份背包、清空、切生存并传送到出生点。
5. **购买/配置阶段**（`BUY_TIME_SECONDS`，默认 20 秒）：全员无敌、可自由跑动；发放弧光币，右键打开军械库切换 5 套预设或改配。
6. 配置时间结束 → **toast 通知开赛**、收回弧光币，进入战斗。
7. 击杀敌对玩家队伍 +1 分；误杀队友 -1 分（不低于 0）。击杀当场获得 XP。
8. 先达到目标分数或时间到比分高者获胜。结算补发胜方 XP 加成与 MVP 奖励；toast + 战绩表单后还原背包。

离开地图区域会被传送回复活点。死亡不掉落，并在己方出生点重生。

## OP 配置地图

`/gs` → **配置地图**：

1. 创建地图（输入名称）
2. 站在角落点按钮 **设为角点1 / 角点2** 划定 XYZ 区域
3. **添加游戏模式**（目前仅团队死斗可实装；TDM 固定 `weapon_acquire=armory`）
4. 进入模式配置：规则（分数 / 人数 / 时长）与红/蓝队复活点

存量 TDM 地图在启动 / `/gs reload` 时会强制纠正为 `armory`。

## 设置 `settings.yml`

```
DEFAULT_LANGUAGE_CODE=ZH-CN
PRIMARY_WEAPON_SLOTS=1
SECONDARY_WEAPON_SLOTS=1
MELEE_WEAPON_SLOTS=1
GADGET_SLOTS=2
DEFAULT_PRIMARY_WEAPON=m4
DEFAULT_SECONDARY_WEAPON=m1911
DEFAULT_MELEE_WEAPON=silencefd
DEFAULT_GADGET_WEAPON=mk2_grenade
DEFAULT_ARMOR_WEAPON=
STARTING_POINTS=1000
KILL_REWARD_POINTS=50
LOBBY_TIMEOUT_SECONDS=900
BUY_TIME_SECONDS=20
START_COUNTDOWN_SECONDS=5
MATCH_TIME_SECONDS=300
WIN_GUILD_CONTRIBUTION_PER_KD=10
MATCH_MONEY_PER_KILL=200
MATCH_WIN_BONUS=2000
MATCH_MVP_BONUS=500
ASSIST_WINDOW_SECONDS=3
MATCH_ASSIST_WEIGHT=0.5
MATCH_TK_WEIGHT=1.5
XP_PER_KILL=5
XP_PER_LEVEL=100
MAX_LEVEL=100
XP_WIN_BONUS_PERCENT=20
XP_MVP_PER_TEAMMATE=10
```

| 键 | 说明 |
|---|---|
| `DEFAULT_*_WEAPON` | 军械库/开局默认武器 id |
| `XP_*` / `MAX_LEVEL` | 生涯经验与等级；MVP 额外经验为 `队伍人数 × XP_MVP_PER_TEAMMATE` |
| `BUY_TIME_SECONDS` | 开局购买/配置窗时长（无敌 + 弧光币换装） |
| `TEAM_A_DEFAULT_ARMOR` / `TEAM_B_DEFAULT_ARMOR` | 按队色开局自动发放的默认护甲（JSON 嵌套：头盔/胸甲/护腿） |

## 武器 `weapons.json`

```json
{
  "id": "ak47",
  "display_name": "AK-47",
  "item": "arc:ak47",
  "cost": 800,
  "type": "primary",
  "category": "assault_rifle",
  "unlock_level": 25,
  "ammo_scoreboard": "ak47Ammo",
  "default_ammo": 30
}
```

- `type`：槽位 `primary` / `secondary` / `melee` / `gadget` / `armor`
- `category`：筛选分类（如 `assault_rifle` / `smg` / `pistol` …）
- `unlock_level`：军械库解锁所需等级（0–100）

可用 `python scripts/generate_weapons_from_arc_bp.py` 从枪战服行为包整表生成。

## 本地测试（不需要 Endstone）

```bash
python -m unittest tests.test_logic
```

## 更新日志

### v0.4.18

- **清理本地 NBT 回退死代码**：`inventory.py` 本地回退的序列化/还原此前调用了 endstone 0.11.x 不存在的 `CompoundTag.dump()` / `endstone.nbt.load()`，异常被静默吞掉，`nbt_b64` 从未真正写入或还原过。直接移除这两段（行为等价），本地回退只保底 type/count/data，完整 NBT 往返交由 arc_inventory（需 ≥ 0.2.0，其 `api_serialize_item` / `api_make_item_stack` 已修复并可用）
- 依赖顺序本就有 `load_after = ["arc_inventory"]`，未安装时仍可运行（仅告警），本次不改为硬依赖

### v0.4.17

- **对局 buff 接入属性核心**：速度/跳跃提升改由 `arc_attribute_core` 的 buff 队列统一管理（`depend` 硬依赖），不再走 `/effect` 命令——不顶掉其他插件挂的效果，清场只撤自己来源（`shooter:match`）；玩家离线时由属性核心在退出事件里自清
- **彻底移除移速残留路径**：删掉 `attribute`/`effect` 命令封装与准备阶段每 tick 重压逻辑，准备阶段保持自由跑动
- **默认配置补全**：`settings.yml` 新增 `TEAM_A_DEFAULT_ARMOR` / `TEAM_B_DEFAULT_ARMOR`（按队色开局自动发放护甲，JSON 嵌套）
- **冒烟测试**：新增 `scripts/smoke_test_attribute_integration.py`（stub endstone，离线验证 buff 下发/撤销/缓存/核心缺失告警）

### v0.4.5

- **TDM 固定军械库**：团队死斗强制 `weapon_acquire=armory`（存量库启动时也会纠正），暂不用商店

### v0.4.4

- **开局购买/配置窗**：全员无敌 + 移速锁定为 0（缓速加压，每 tick 重压）
- **开局 toast**：比赛开始 / 购买配置结束并收回弧光币；军械库模式同样进入配置阶段

### v0.4.3

- **5 套军械库预设**：每人 5 套，初始均为 Lv.0 默认配装；局内无敌窗右键弧光币切换/改配
- **无敌=购买窗**：换装与买枪仅在无敌期内；结束自动收回弧光币（时长用 `BUY_TIME_SECONDS`）

### v0.4.2

- **枪手排行榜**：`/gs` 主菜单按 KD 降序展示全体玩家及 KD 头衔（分页）

### v0.4.1

- **生涯场次细分**：总场次 / 胜 / 负 / 平；MVP / 胜方 MVP / 败方 MVP（平局 MVP 只计入总 MVP）

### v0.4.0

- **军械库模式**：赛外配装、进场即用；TDM 默认 `armory`，无购买阶段
- **生涯等级**：击杀 XP、胜方 20% 加成、MVP = 队伍人数 × 10（可配）
- **武器 meta**：`category` + `unlock_level`；军械库/商店按分类筛选
- **持久 loadout**：`player_loadout` 表；未解锁拒绝保存并回退默认
- **map_db**：持久读写 `weapon_acquire`；存量 TDM 迁移为 armory

### v0.3.7

- **商店差价**：同栏位降级换枪时退回差价（升级仍补差价；等价免费置换）
- **默认武器**：开局免费发放，可在 `settings.yml` 按分类配置
- **近战分类**：新增 `melee` 类型与快捷栏槽位；战术匕首 `silencefd` 从副武器改到近战
- **死亡播报**：局内击杀/阵亡提示带队伍色玩家名与比分
- **提示配色**：主色白 §f、重点橙 §6、次要灰 §7/§8

### v0.2.7

- 开赛传送倒计时、阶段 title、临近结束提醒、结算 toast

### v0.2.6

- 大厅交互、地图配置、比赛结算、阵营名牌、武器经济、枪械弹药

### v0.2.2

- `/gs` 大厅流程、SQLite 地图库、Aplok 枪械商店经济

### v0.1.1

- 修复 config 属性与 Endstone 基类冲突导致插件无法加载
