"""方块分类词表——整个导航模块里"什么算实心/什么算空气/什么算液体"的唯一事实来源。

为什么单独一个文件：判定规则（standable.py）只管逻辑，方块名怎么归类全在这。
词表错了改这一个地方，不用翻逻辑。
"""

from __future__ import annotations

#: 液体——既不能当脚下的支撑，也不能当头顶的"空气"（人不能站水里）。
LIQUIDS = frozenset({
    "water", "flowing_water", "lava", "flowing_lava",
    "bubble_column", "waterlog",  # waterlog 一般是状态不是方块，防一手
})

#: 可穿过装饰——站在这种格子里等于站在空气里（草丛、花、火把……）。
#: 出现在头顶两格时**不阻碍站立**；但它们自己当不了脚下的支撑。
PASSABLE_DECOR = frozenset({
    # 草与花
    "tallgrass", "short_grass", "grass", "fern", "large_fern",
    "seagrass", "kelp", "kelp_plant", "sea_pickle", "turtle_egg",
    "dandelion", "poppy", "blue_orchid", "allium", "azure_bluet",
    "red_tulip", "orange_tulip", "white_tulip", "pink_tulip",
    "oxeye_daisy", "cornflower", "lily_of_the_valley",
    "wither_rose", "sweet_berry_bush", "deadbush", "nether_sprout",
    "crimson_roots", "warped_roots", "sapling",
    "wheat", "carrots", "potatoes", "beetroot_seeds", "beetroot",
    "nether_wart", "cocoa", "melon_stem", "pitcher_crop",
    # 挂件/功能件
    "torch", "soul_torch", "redstone_torch", "wall_torch",
    "soul_wall_torch", "redstone_wall_torch",
    "rail", "powered_rail", "detector_rail", "activator_rail",
    "button", "lever", "tripwire", "tripwire_hook", "string",
    "sign", "wall_sign", "hanging_sign", "banner", "wall_banner",
    "pressure_plate", "lightning_rod", "end_rod", "flower_pot",
    "structure_void", "air", "cave_air", "void_air",
    # 薄层
    "snow_layer", "carpet",  # 地毯有 16 色变体，见 _normalize 里的前缀处理
    "cobweb",
})

#: 挡路但站不住的薄片栅栏（2026-11-03 两轮实测的最终结论）：
#:   · 不能当支撑——顶面太薄站不住（0.4.41 前当实心 → "站在铁栏顶上"
#:     的幽灵节点，把假人吸附点抬到半空）；
#:   · 也不能当空气——Bedrock 里 iron_bars 有碰撞箱，实体**穿不过去**
#:     （0.4.42~0.4.44 当空气 → 导航路线穿过铁栏，假人卡进碰撞箱里
#:     一步不动，实测 arena 卡死 身=iron_bars）。
#: 所以它是第三类：阻挡（挡走廊/挡头空/挡切角），但不生成站立点。
BLOCKING_THIN = frozenset({"iron_bars"})
#: 活板门同属此类（2026-11-03 收官轮）：关着的活板门有碰撞箱——
#: 当空气会让路线穿过它把假人楔住（和铁栏同病）；它的后缀从
#: "可穿装饰" 挪到这里，走廊/头空/切角全部按阻挡处理，顶面也不生成
#: 站立点（消灭"站在活板门顶上"的幽灵节点）。
_BLOCKING_SUFFIXES = ("_trapdoor",)

#: 地毯按颜色命名（white_carpet …），词表记不住 16 个，认后缀。
#: 活板门同理（oak_trapdoor / spruce_trapdoor / …）：开着能穿、关着也
#: 站不住（0.2 厚），统一当空气——烘焙不看开合状态，从严宁可多放行。
_PASSABLE_DECOR_SUFFIXES = ("_carpet", "_tulip", "_sapling")

#: 到这里都还没认出来的方块 → 一律当**实心支撑**（默认从严：能站）。
#: 宁可多建一个点让可视化里看出来，也不要漏掉真实地形。


def short_name(full: str) -> str:
    """`minecraft:stone` → `stone`。"""
    s = str(full or "")
    return s.split(":", 1)[1] if ":" in s else s


def is_liquid(name: str) -> bool:
    return short_name(name).lower() in LIQUIDS


def is_air_space(name: str) -> bool:
    """这个方块占了格子，但身体可以穿过 → 站立判定里把它当空气。"""
    n = short_name(name).lower()
    if n in BLOCKING_THIN or n.endswith(_BLOCKING_SUFFIXES):
        return False
    if n in PASSABLE_DECOR:
        return True
    return n.endswith(_PASSABLE_DECOR_SUFFIXES)


def is_support(name: str) -> bool:
    """这个方块能不能当脚下的支撑（实心）。液体和装饰不行，其余一律行。"""
    n = short_name(name).lower()
    if n in LIQUIDS or n in BLOCKING_THIN or n.endswith(_BLOCKING_SUFFIXES):
        return False
    if n in PASSABLE_DECOR or n.endswith(_PASSABLE_DECOR_SUFFIXES):
        return False
    return True


#: 站立高度看方块状态的方块（2026-11-03 枪战服实测：炼狱小镇地面/出生点
#: 全是半砖，把半砖当整块实心会让节点脚位虚高 0.5 —— 假人实际站在
#: y+0.5 的半砖顶上，引擎收到"走到 y+1"的目标就规划不出、原地冻结）。
#:
#: 返回站上后的**脚部高度偏移**：底半砖/正楼梯 = 0.5（顶面在半格），
#: 顶半砖/倒楼梯/双半砖 = 1.0（顶面在整格）。其余方块一律 1.0。
def support_top_offset(name: str, states: dict | None = None) -> float:
    n = short_name(name).lower()
    if "double_slab" in n:
        return 1.0
    if n.endswith("_slab"):
        vh = str((states or {}).get("vertical_half", "bottom")).lower()
        return 1.0 if vh == "top" else 0.5
    if n.endswith("_stairs"):
        # 倒楼梯贴在天花板上，站上去是整格；正楼梯低半边是 0.5
        return 1.0 if (states or {}).get("upside_down_bit") else 0.5
    return 1.0


#: 实心支撑**上面铺的薄片**（它们自己是装饰当不了支撑，但会垫高站面）。
#: 地毯 1/16 格厚（2026-11-03 枪战服 harbor 实测：整格脚位比真实站面低
#: 0.0625 → 引擎目标"陷入方块"，全部寻路被拒、假人完全冻结）。
#: 雪片默认按 1 层 0.125（多层雪罕见于竞技场地面）。
def overlay_height(name: str) -> float:
    n = short_name(name).lower()
    if n.endswith("_carpet") or n == "moss_carpet":
        return 0.0625
    if n == "snow_layer":
        return 0.125
    return 0.0
