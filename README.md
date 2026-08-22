# EndStone ARC Shooter Game / 弧光射击游戏

[![版本](https://img.shields.io/badge/版本-0.2.6-blue.svg)](https://github.com/ARC-Minecraft/EndStone-ARC-Shooter-Game)
[![EndStone](https://img.shields.io/badge/EndStone-0.10+-green.svg)](https://github.com/EndstoneMC/endstone)

服务器内可配置多张射击地图。目前实装 **团队死斗（TDM）**，通过 `/gs` 菜单创建大厅、选择地图与模式开局。

## 安装

```bash
pip install build
python -m build
```

把 `dist/endstone_arc_shooter_game-0.2.6-py3-none-any.whl` 放到服务器 `plugins/`，重启。首次启动会生成：

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
| `/gs` | 主菜单：大厅列表 / 配置地图（OP） |
| `/gs buy` | 比赛开始后打开商店 |
| `/gs leave` | 离开大厅或比赛 |
| `/gs reload` | OP：重载地图、武器、设置 |

## 流程

1. 玩家 `/gs` → **大厅列表**，可创建或加入大厅。
2. 房主在大厅内点击 **选择地图与模式**（仅显示已配置完成、且未被其它大厅占用的地图）。
   - 若地图只有一种可玩模式（目前通常为团队死斗），选图后会自动选中该模式。
   - 若地图有多种可玩模式，选图后需再选模式。
3. 从首位玩家加入起计时，默认 **15 分钟**未开局则解散大厅。
4. 开局后：备份背包与位置 → `/clear` 清空背包 → `/gamemode 0` 生存模式 → 按队伍随机传送到出生点。
5. 默认 **10 秒**购买时间，期间（以及整场比赛）可用 `/gs buy` 花战争点数买武器。
6. 击杀敌对玩家：队伍 +1 分，杀手获得战争点数；误杀队友：队伍 -1 分（不低于 0）。
7. 先达到目标分数的队伍获胜。结算后 `/clear` 清空比赛背包，并传送回开局前位置、恢复原先游戏模式。
8. 比赛进行中若未满员，其他玩家仍可从大厅列表加入。

离开地图区域会被传送回复活点。死亡不掉落，并在己方出生点重生。

## OP 配置地图

`/gs` → **配置地图**：

1. 创建地图（输入名称）
2. 站在角落点按钮 **设为角点1 / 角点2** 划定 XYZ 区域
3. **添加游戏模式**（目前仅团队死斗可实装）
4. 进入模式配置：
   - **修改规则（分数 / 人数 / 时长）**：设置目标分数、单队人数上限、**比赛时长（分钟）**
   - **管理红/蓝队复活点**：在对应子页添加或删除复活点

地图列表与编辑页会显示每张地图、每种模式是否可开局（缺区域、缺复活点等会标出）。

## 设置 `settings.yml`

```
PRIMARY_WEAPON_SLOTS=1
SECONDARY_WEAPON_SLOTS=1
GADGET_SLOTS=3
STARTING_POINTS=1000
KILL_REWARD_POINTS=50
LOBBY_TIMEOUT_SECONDS=900
BUY_TIME_SECONDS=10
DEFAULT_LANGUAGE_CODE=ZH-CN
WIN_GUILD_CONTRIBUTION_PER_KD=10
MATCH_MONEY_PER_KD=100
```

赛后奖励（需安装 ARCCore）：所有玩家按 `max(0, K-D)` 获得金钱；胜队成员额外获得公会贡献点。倍率见上两项配置。

## 地图数据

地图配置存储在 `plugins/ARCShooterGame/shooter.db`（SQLite）。OP 通过 `/gs` 配置界面修改，无需手改 JSON。

若服务器上仍有旧的 `maps.json`，首次启动会自动迁移到 SQLite 并备份为 `maps.json.bak`。

## 武器 `weapons.json`

```json
{
  "id": "ak47",
  "display_name": "AK-47",
  "item": "custom:ak47",
  "cost": 500,
  "type": "primary",
  "amount": 1,
  "extras": { "custom:ammo_762": 60 }
}
```

`type` 为 `primary` / `secondary` / `gadget`。`item` 填 `namespace:identifier`。

枪械需与 Aplok 模组计分板一致（购买/重生时写入弹药数）：

| 字段 | 说明 |
|---|---|
| `ammo_scoreboard` | 模组使用的计分板 objective 名（通常与枪 id 相同） |
| `default_ammo` | 满弹匣弹药数（取自模组 `functions/weapons/reload/*.mcfunction`） |

可用 `python scripts/sync_ammo_from_mod.py` 从枪战服行为包自动同步；参考表见 `plugins/ARCShooterGame/aplok_ammo.json`。

## 本地测试（不需要 Endstone）

```bash
python -m unittest tests.test_logic
```

## 更新日志

### v0.2.6

- **大厅交互**：合并「选择地图与模式」；有人加入/离开时全员刷新大厅 Form；创建大厅时全服聊天广播
- **地图配置（OP）**：地图/模式就绪状态展示；规则（分数、人数、时长）置顶；红/蓝复活点分子页管理
- **比赛结算**：ActionForm 结算页；对接 ARCCore 赛后奖励（全员 `(K-D)×100` 金钱，胜队额外 `(K-D)×10` 公会贡献，倍率可配置）
- **阵营名牌**：比赛中显示红/蓝阵营色名牌，结束/离开时还原 ARCCore 头衔
- **武器经济**：子弹 extras ×3、道具价格 ÷5；铁剑副武器；弧光币固定快捷栏第 9 格（右键 200ms 防抖）
- **枪械弹药**：每枪配置 `ammo_scoreboard` + `default_ammo`，购买与死亡重生后重置弹药
- **语言与配置**：重写 `ZH-CN.txt`；`settings.yml` 新增 `WIN_GUILD_CONTRIBUTION_PER_KD`、`MATCH_MONEY_PER_KD`

### v0.2.2

- `/gs` 大厅流程、SQLite 地图库、Aplok 枪械商店经济

### v0.1.1

- 修复 config 属性与 Endstone 基类冲突导致插件无法加载
