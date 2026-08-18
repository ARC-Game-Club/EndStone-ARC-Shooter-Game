# EndStone ARC Shooter Game / 弧光射击游戏

[![版本](https://img.shields.io/badge/版本-0.1.0-blue.svg)](https://github.com/ARC-Minecraft/EndStone-ARC-Shooter-Game)
[![EndStone](https://img.shields.io/badge/EndStone-0.10+-green.svg)](https://github.com/EndstoneMC/endstone)

服务器内可配置多张射击地图。目前实装 **团队死斗（TDM）**，地图配置里预留了个人死斗、夺旗战等 `mode`，后续按同样大厅流程加即可。

## 安装

```bash
pip install build
python -m build
```

把 `dist/endstone_arc_shooter_game-0.1.0-py3-none-any.whl` 放到服务器 `plugins/`，重启。首次启动会生成：

```
plugins/ARCShooterGame/
  settings.yml
  maps.json
  weapons.json
  ZH-CN.txt
```

## 指令

| 指令 | 说明 |
|---|---|
| `/tdm` | 地图列表 / 大厅 / 比赛菜单 |
| `/tdm buy` | 比赛开始后打开商店 |
| `/tdm leave` | 离开大厅或比赛 |
| `/tdm reload` | OP：重载地图、武器、设置 |
| `/tdm here` | OP：输出当前坐标，方便填 `maps.json` |

## 流程

1. 玩家 `/tdm` 看到每张地图的人数与状态，点进去加入**虚拟大厅**（此时不传送、不清背包）。
2. 第一个进入某地图的人成为大厅管理员，可调整分队、踢人、开始游戏。
3. 从首位玩家加入起计时，默认 **15 分钟**未开局则解散该地图大厅。
4. 开局后：备份背包与位置 → 清空背包 → 冒险模式 → 按队伍随机传送到出生点。
5. 默认 **10 秒**购买时间，期间（以及整场比赛）可用 `/tdm buy` 花战争点数买武器。
6. 击杀敌对玩家：队伍 +1 分，杀手获得战争点数；误杀队友：队伍 -1 分（不低于 0）。
7. 先达到地图 `target_score` 的队伍获胜。结算后所有人回到开局前位置并恢复背包，聊天输出胜者与各人击杀/死亡。

死亡不掉落，并在己方出生点重生。中途掉线或崩溃时，背包备份写在 `plugins/ARCShooterGame/backups/`，下次进服会尝试还原。

## 设置 `settings.yml`

```
PRIMARY_WEAPON_SLOTS=1
SECONDARY_WEAPON_SLOTS=1
GADGET_SLOTS=3
STARTING_POINTS=800
KILL_REWARD_POINTS=100
LOBBY_TIMEOUT_SECONDS=900
BUY_TIME_SECONDS=10
DEFAULT_LANGUAGE_CODE=ZH-CN
```

热键栏布局：主武器占前 n 格，副武器接着，道具再接着。换同类型武器会替换对应格子；子弹等 `extras` 放到背包末尾。道具默认 3 格，买第 4 个时替换第 1 个道具格。

## 地图 `maps.json`

`mode` 目前只有 `tdm` 能开局。每个队可配多个出生点，`radius` 为 0 表示精确出生在该点。

用 `/tdm here` 站在出生点上，把打印的 JSON 贴进 `spawns`。改完 `/tdm reload`。

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
