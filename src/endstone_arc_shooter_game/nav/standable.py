# -*- coding: utf-8 -*-
"""可站立判定——用户 2026-11-03 的原话就是规格：

    "脚下有方块，上方有两格高的空气作为站立空间"

翻译成格子语言，(x, foot, z) 是一个站立点（**脚部高度 foot 可为 .5**）⟺

  1. 脚下有方块   ：支撑格 (x, Y, z) 有实体方块（液体/花草装饰不算，树叶算）
  2. 脚部高度     ：整块 / 顶半砖 / 倒楼梯 → Y+1.0；底半砖 / 正楼梯 → Y+0.5
                   （2026-11-03 枪战服实测：炼狱小镇地面/出生点全是半砖，
                    脚位记整格会虚高 0.5 —— 假人实际站在半砖顶 y+0.5，
                    引擎收到"走到 y+1"的日标规划不出，原地冻结）
  3. 头顶两格空气 ：支撑格上方两格（Y+1、Y+2）没有方块，或只有可穿装饰。
                   液体不算空气。

分类词表见 taxonomy.py（`support_top_offset` 管半格高度），本文件只管逻辑。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .blocks_v1 import BlockMap
from .taxonomy import (is_air_space, is_support, overlay_height,
                       support_top_offset)

#: 站立点：((x, 脚部y, z), 脚下方块短名)
StandPoint = Tuple[Tuple[int, float, int], str]


def column_standables(bmap: BlockMap, x: int, z: int) -> List[Tuple[float, str]]:
    """一列里所有站立高度：[(脚部 y, 脚下方块名), ...]，按 y 升序。

    一列可以有好几层（楼上楼、楼梯井）——全部返回，导航是 3D 的。
    """
    col = bmap.columns.get((x, z))
    if not col:
        return []
    states_col = bmap.col_states.get((x, z)) or {}
    out: List[Tuple[float, str]] = []
    for y, name in col.items():
        # 1) 脚下方块：列里记录的就是非空气方块，还得是实体支撑
        if not is_support(name):
            continue
        # 2) 脚部高度看方块类别与状态（半砖/楼梯是半格）
        foot = y + support_top_offset(name, states_col.get(y))
        # 3) 头顶两格空气（支撑格上方 Y+1 / Y+2）
        b_low = bmap.block_at(x, y + 1, z)
        b_high = bmap.block_at(x, y + 2, z)
        if b_low is not None and not is_air_space(b_low):
            continue
        if b_high is not None and not is_air_space(b_high):
            continue
        # 4) 支撑上铺的薄片（地毯/雪）垫高站面——引擎不吃"低于真实站面的目标"
        if b_low is not None:
            foot += overlay_height(b_low)
        out.append((foot, name))
    out.sort()
    return out


def all_standables(bmap: BlockMap) -> List[StandPoint]:
    """整张图所有站立点。顺序按 (z, x, y) 排——节点 id 分配和俯视图都吃这个序。"""
    out: List[StandPoint] = []
    for (x, z), col in bmap.columns.items():
        states_col = bmap.col_states.get((x, z)) or {}
        for y, name in col.items():
            if not is_support(name):
                continue
            foot = y + support_top_offset(name, states_col.get(y))
            b_low = bmap.block_at(x, y + 1, z)
            b_high = bmap.block_at(x, y + 2, z)
            if b_low is not None and not is_air_space(b_low):
                continue
            if b_high is not None and not is_air_space(b_high):
                continue
            if b_low is not None:
                foot += overlay_height(b_low)
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
