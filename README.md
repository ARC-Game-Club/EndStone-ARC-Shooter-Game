# EndStone ARC Shooter Game / 弧光射击游戏

[![版本](https://img.shields.io/badge/版本-0.4.32-blue.svg)](https://github.com/ARC-Game-Club/EndStone-ARC-Shooter-Game)
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
| `/gs quick` | 快速开始：有房就进、没房就开一间（纯命令路径，不弹表单，AI 假人也能用） |
| `/gs leave` | 离开大厅或比赛 |
| `/gs range` | 靶场开关：不在靶场 → 进靶场；已在靶场 → 退出靶场（恢复进入前的背包与位置） |
| `/gs armory` | 直接打开军械库表单 |
| `/gs reload` | OP：重载地图、武器、设置 |
| `/gs report [start\|end\|all] [on\|off]` | OP：查/切往 QQ 群发的开关。不带参数 = 看状态；`start` = 开局播报（房间创建），`end` = 终局战报，`all` = 总开关。**立即生效**，并写回 `settings.yml`（重启后仍然有效） |
| `/addspawn <模式> [队伍]` | OP：把脚下位置加为所在地图的出生点（红蓝队模式带队伍 red/blue/红/蓝，可简写 `/addspawn red`；个人死斗 `/addspawn ffa`） |
| `/rmspawn <模式> [队伍]` | OP：删除脚下 3 格内最近的指定出生点（参数同上） |
| `/setrange <pos1\|pos2\|entry\|show\|clear>` | OP：配置靶场范围两角与传送点（走到对应位置执行） |

比赛中 **弧光币（快捷栏第 9 格）右键** 打开军械库：仅在开局购买/配置窗或重生无敌窗内可换装；超时后弧光币收回。

> `/gs range` 与 `/gs armory` **只认"执行者"**：经 `execute as @s run gs range` 转发时，
> 作用对象是被 `as` 的那个玩家，所以命令方块 / 脚本能替别人调用。
> `/gs` 的权限对所有玩家开放（`default: True`）。

> ⚠ **命令最多两段**（`/gs` + 一个子命令）。BDS 的命令语法树不接受三段，
> 注册了 `/gs range exit` 这种用法后，BDS 会把 `range` 判成 Unexpected，
> 整条 `gs` 命令都进不到插件（客户端报 `Syntax error: Unexpected "range"`）。
> 所以靶场进出做成**一条 `/gs range` 的开关**，不另开子命令。
> 插件里有单测守着：`tests/test_logic.py::RangeCommandDispatchTests::
> test_gs_usages_never_exceed_two_segments`。

## 靶场

OP 用 `/setrange pos1`、`/setrange pos2` 圈出靶场范围，站在希望玩家落地的位置执行 `/setrange entry`。

玩家可以用 `/gs range` 直接进靶场，或从 `/gs` 主菜单点 **靶场**：清空并快照随身物品 → 传送到入口 → 按当前军械库配装发放测试武器 + 弧光币。靶场内开火免伤；手持弧光币右键打开靶场菜单（军械库换配装 / 补发弹药 / 回入口 / 退出）。退出或掉线会自动恢复进入前的背包、位置与游戏模式。

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
QQ_REPORT_ENABLED=1
QQ_REPORT_START=1
QQ_REPORT_END=1
```

| 键 | 说明 |
|---|---|
| `DEFAULT_*_WEAPON` | 军械库/开局默认武器 id |
| `XP_*` / `MAX_LEVEL` | 生涯经验与等级；MVP 额外经验为 `队伍人数 × XP_MVP_PER_TEAMMATE` |
| `BUY_TIME_SECONDS` | 开局购买/配置窗时长（无敌 + 弧光币换装） |
| `TEAM_A_DEFAULT_ARMOR` / `TEAM_B_DEFAULT_ARMOR` | 按队色开局自动发放的默认护甲（JSON 嵌套：头盔/胸甲/护腿） |
| `QQ_REPORT_ENABLED` | 战报总开关：`1` 开、`0` 关 |
| `QQ_REPORT_START` | 开赛时往 QQ 群发一条**开局播报**（= 房间创建播报：地图/模式/两边名单/目标分） |
| `QQ_REPORT_END` | 终局往 QQ 群发一条**战报**（比分 + 每人击杀/死亡/助攻） |

> 战报经**群服互通插件**（`arc_qq_sync_astrbot`）发进 QQ 群，消息前面自动带
> 服务器名。该插件不在、或没连上消息中枢时，战报静默跳过（不影响对局）。

> **运行时切换**：这三个键都能用 `/gs report <start|end|all> <on|off>` 改，
> 改完**立刻生效**（不用重启），同时写回 `settings.yml`（重启后仍然有效）。
> 嫌群里吵的时候 `/gs report all off` 一条命令就闭嘴；想恢复
> `/gs report all on`。注意 `settings.yml` 是**启动时**读的，光改文件
> 不重启不生效——用这条命令就绕开了这个限制。

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
python -m pytest tests/            # 全量（含 test_qq_report）
python -m unittest tests.test_logic # 只跑逻辑测试
```

插件模块依赖 endstone，测试用 `scripts/_endstone_stub_shooter.py` 顶替，
`tests/test_logic.py` 导入时自动把 `src/` 挂上 `sys.path`，**不需要设 PYTHONPATH**。

## 更新日志

### v0.4.54

- **群消息开关可运行时切换**：新增 `/gs report [start|end|all] [on|off]`（OP，控制台也能用）
  - `start` = 开局播报（房间创建那条：地图/模式/两边名单/目标分）
  - `end` = 终局战报（比分 + 每人击杀/死亡/助攻）
  - `all` = 总开关
  - 不带参数 = 看当前三个开关的状态
  - **立刻生效，不用重启服务器**；同时写回 `settings.yml`，重启后仍然有效
- 为什么加这条：以前只能手动改 `settings.yml` 再 `/gs reload` 或重启。群里太吵时
  服主想立刻闭嘴，不该被一次重启卡住
- 开关语义没变（`QQ_REPORT_ENABLED` 是总闸，`START`/`END` 是分项），只是多了一个
  运行时入口；`settings.yml` 里手改这三个键依然有效
- 补单测 `tests/test_qq_report.py` 的 `ReportCommandTests`（8 项）：关掉后确实
  不再发群、开回来能恢复、非 OP 改不了、查状态不碰开关

### v0.4.35

- **接上假人插件 3.10.0 的两个事件钩子**（上游重构后假人改成事件驱动，
  这两处不接就断）：
  - **大厅创建 → `api_shooter_lobby_created(lobby_id, event_id)`**：
    假人插件 3.10.0 移除了 30 秒 quick 轮询心跳，只剩「上线事件 +
    大厅创建事件」两个入口。而本插件原来的 `_maybe_fill_with_bots`
    **只在真人触发时补位**（假人触发会被跳过以防循环补人）——
    于是**假人自己建的那间房永远只有它自己**。现在每次建房都通知一次。
    不会递归：假人插件按 event_id 去重，补位又指定了 lobby_id，塞不下
    就失败，不会各自另开新房。
  - **对局结算 → `api_environment_event(name, text, settlement=True)`**：
    枪战模式下假人**不主动说话**（需求文档 §1），只在被点名或收到
    **结算类**事件时开口。⚠️ `settlement` 必须传 `True`——假人侧把非
    结算事件在枪战模式下一律拒收（`mode == "gun_game" and not
    settlement`），漏传就赛后再也不开口，而且**不报错**。
- 新增 `tests/test_ai_integration_hooks.py`（12 项），把上面两个钩子
  钉死，尤其钉住 `settlement=True` 这个参数。

### v0.4.34

- **无敌窗有日志了（开始 / 结束都能对上）**：服主实测「对局里打假人，
  突然三四秒掉血 0，而假人头顶没显示[无敌状态]」，从日志上分不清是
  复活保护、准备阶段整段无敌，还是判定串味。现在两条 INFO：
  - `[无敌] <玩家> 开始 3.0s（来源 复活，到 21:27:14）`
  - `[无敌] <玩家> 结束（进入对局）：来源 开局准备阶段，已持续 12.4s，取消时剩 7.6s`
  来源一共五种：`开局准备阶段` / `复活` / `中途加入·准备阶段` /
  `中途加入·对局中` / `准备阶段重新加入`，结束原因：`进入对局` /
  `自然到期` / `清场/离开对局`。
- **修 `_enter_playing` 不取消无敌窗的漏洞**：原来先 `_get_player()`，
  拿不到句柄就 `continue`，于是**句柄拿不到的人永远取消不了无敌窗**，
  只能等它自然到期（模拟玩家尤其容易踩）。现在清记账放在拿句柄之前，
  无条件执行 —— 对局一开始就该解除无敌。
- 新增 `tests/test_spawn_protect_log.py`（5 项），把这个顺序钉死。

### v0.4.33

- **修掉「命令进不去」**：v0.4.31/32 注册了 `/gs range exit`（三段），BDS 的命令语法树
  最多只认两段，于是把 `range` 判成 Unexpected，客户端报
  `Syntax error: Unexpected "range"`，命令根本进不到插件（日志里只有
  `issued server command: /gs range`，没有任何 `tp` 派发）
- **`/gs range` 改成开关**：不在靶场 → 进靶场；已在靶场 → 退出靶场。
  进出共用一条两段指令，不再需要 `/gs range exit`
- `/gs armory` 同理去掉 `[玩家名]`（三段也过不去）；替别人调用统一走
  `execute as <玩家名> run gs range`
- 删掉因此用不上的 `parse_range_command_args` / `parse_target_player_arg` /
  `_resolve_command_target` 与四个语言键
- **加回归护栏**：`tests/test_logic.py` 断言 `gs` 的 usage 永远不超过两段，
  以后再有人加三段子命令会被测试拦下

### v0.4.32

- **军械库快捷指令**：新增 `/gs armory`（`/gs arm` 同义）——直接弹军械库表单，不用先进主菜单
- ⚠ 本版的 `/gs range exit`（三段）会让 BDS 整条 `gs` 命令解析失败，已在 v0.4.33 修掉

### v0.4.31

- **靶场快捷指令**：新增 `/gs range`（`/gs tp` 同义）——直达靶场，不再走菜单
- 指令只认 sender 不认"谁敲的命令"，`execute as @s run gs range` 可替别人调用；`/gs` 权限保持 `default: True`，普通玩家可自行进出靶场
- **修掉"弹窗出不来"**：BDS 一个玩家同时只能挂一个表单，不先关就发新的客户端收不到。新增 `_close_open_form`，所有表单发送前先关旧表单（全插件 25 处表单受益），与弧光核心 `/arc` 的处理一致
- `_show_range_menu` 原先直接调 `player.send_form()` 绕过统一出口，顺手改走 `_send_form`，补上"模拟玩家无客户端"的防护
- 语言母版 `plugins/ARCShooterGame/ZH-CN.txt` 补齐缺失的 `RANGE_*` / `ARMOR_*` / `SPAWN_CMD_*` 共 43 个键（部署脚本会用它覆盖服务器那份，少键会在部署时被冲掉）

### v0.4.30

- **房间创建即补位**：真人建房后自动拉 AI 假人补位，不再出现"真人建了房没人来"
- **指定房间加入**：`api_quick_join(..., lobby_id=)` 只进指定房间，塞不下就失败、不新建房
- **全 AI 房间自动开局**：房里全是 AI 时自动开局；有真人不抢房主的开局权

### v0.4.29

- **战报转发到 QQ 群**：开赛和终局各发一条战报到 QQ 群——开局播报带地图/模式/两边名单/目标分，终局战报带终局比分、胜方和每人击杀/死亡/助攻（含 TK）。经群服互通插件 `arc_qq_sync_astrbot` 的 `custom` 事件发出，消息前自动带服务器名
- 开关在 `settings.yml`：`QQ_REPORT_ENABLED` / `QQ_REPORT_START` / `QQ_REPORT_END`，设 `0` 关闭
- 终局战报在 `_end_match` **最前面**取数——那个函数末尾会把大厅从 `lobbies` 里摘掉，晚一步就读不到终局比分了
- 群服互通插件不在、没连中枢、调用抛异常——一律静默跳过，不影响对局

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
