# EndStone ARC Shooter Game / 弧光射击游戏

[![版本](https://img.shields.io/badge/版本-0.2.2-blue.svg)](https://github.com/ARC-Minecraft/EndStone-ARC-Shooter-Game)
[![EndStone](https://img.shields.io/badge/EndStone-0.10+-green.svg)](https://github.com/EndstoneMC/endstone)

服务器内可配置多张射击地图。目前实装 **团队死斗（TDM）**，通过 `/gs` 菜单创建大厅、选择地图与模式开局。

## 安装

```bash
pip install build
python -m build
```

把 `dist/endstone_arc_shooter_game-0.2.2-py3-none-any.whl` 放到服务器 `plugins/`，重启。首次启动会生成：

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
2. 房主在大厅内选择地图和游戏模式（仅显示已配置完成、且未被其它大厅占用的地图）。
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
4. 进入模式配置：站位添加红/蓝队复活点，可修改目标分数与单队人数上限

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
```

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

## 本地测试（不需要 Endstone）

```bash
python -m unittest tests.test_logic
```
