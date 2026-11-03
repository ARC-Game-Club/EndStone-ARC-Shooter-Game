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
    # 薄片栅栏（2026-11-03 枪战服实测）：游戏里**能穿但站不住**——判成
    # 实心会造出"站在铁栏顶上"的幽灵节点（harbor 22 个、脚高全 y=68，
    # 把假人吸附点抬到半空），还会把真实能走的路当墙判死。
    "iron_bars",
    "cobweb",
})

#: 地毯按颜色命名（white_carpet …），词表记不住 16 个，认后缀。
#: 活板门同理（oak_trapdoor / spruce_trapdoor / …）：开着能穿、关着也
#: 站不住（0.2 厚），统一当空气——烘焙不看开合状态，从严宁可多放行。
_PASSABLE_DECOR_SUFFIXES = ("_carpet", "_tulip", "_sapling", "_trapdoor")

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
    if n in PASSABLE_DECOR:
        return True
    return n.endswith(_PASSABLE_DECOR_SUFFIXES)


def is_support(name: str) -> bool:
    """这个方块能不能当脚下的支撑（实心）。液体和装饰不行，其余一律行。"""
    n = short_name(name).lower()
    if n in LIQUIDS:
        return False
    if n in PASSABLE_DECOR or n.endswith(_PASSABLE_DECOR_SUFFIXES):
        return False
    return True
