"""可站立判定——用户 2026-11-03 的原话就是规格：

    "脚下有方块，上方有两格高的空气作为站立空间"

翻译成格子语言，(x, y, z) 是一个站立点（脚部占 y 格）⟺

  1. 脚下有方块   ：(x, y-1, z) 有实体支撑方块（液体/花草装饰不算，树叶算）
  2. 头顶两格空气 ：(x, y, z) 和 (x, y+1, z) 都是"空气"——
                   没有方块，或只有可穿过装饰（草丛/火把/告示牌……）。
                   液体不算空气（不能站在水/岩浆里）。

分类词表见 taxonomy.py，本文件只管逻辑。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .blocks_v1 import BlockMap
from .taxonomy import is_air_space, is_support

#: 站立点：((x, y, z), 脚下方块短名)
StandPoint = Tuple[Tuple[int, int, int], str]


def column_standables(bmap: BlockMap, x: int, z: int) -> List[Tuple[int, str]]:
    """一列里所有站立高度：[(脚部 y, 脚下方块名), ...]，按 y 升序。

    一列可以有好几层（楼上楼、楼梯井）——全部返回，导航是 3D 的。
    """
    col = bmap.columns.get((x, z))
    if not col:
        return []
    out: List[Tuple[int, str]] = []
    for y, name in col.items():
        # 1) 脚下方块：列里记录的就是非空气方块，还得是实体支撑
        if not is_support(name):
            continue
        foot = y + 1
        # 2) 头顶两格空气：读不到方块（None=空气）或可穿装饰
        b_foot = bmap.block_at(x, foot, z)
        b_head = bmap.block_at(x, foot + 1, z)
        if b_foot is not None and not is_air_space(b_foot):
            continue
        if b_head is not None and not is_air_space(b_head):
            continue
        out.append((foot, name))
    out.sort()
    return out


def all_standables(bmap: BlockMap) -> List[StandPoint]:
    """整张图所有站立点。顺序按 (z, x, y) 排——节点 id 分配和俯视图都吃这个序。"""
    out: List[StandPoint] = []
    for (x, z), col in bmap.columns.items():
        for y, name in col.items():
            if not is_support(name):
                continue
            foot = y + 1
            b_foot = bmap.block_at(x, foot, z)
            b_head = bmap.block_at(x, foot + 1, z)
            if b_foot is not None and not is_air_space(b_foot):
                continue
            if b_head is not None and not is_air_space(b_head):
                continue
            out.append(((x, foot, z), name))
    out.sort(key=lambda p: (p[0][2], p[0][0], p[0][1]))
    return out


def build_column_index(standables: List[StandPoint]) -> Dict[Tuple[int, int], List[int]]:
    """{(x, z): [节点下标…]}——建边时按列取邻居用。

    下标按 y 升序（standables 本来就按 (z,x,y) 排，追加天然有序）。
    """
    index: Dict[Tuple[int, int], List[int]] = {}
    for i, (pos, _name) in enumerate(standables):
        index.setdefault((pos[0], pos[2]), []).append(i)
    return index
