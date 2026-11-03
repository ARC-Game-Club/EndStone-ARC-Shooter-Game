# -*- coding: utf-8 -*-
"""导航网格子系统：blocks-v1 地图 → 可站立点 → 8 邻接有向图 → A*。

规则（服主 2026-11-03 定稿）：
  · 可站立：脚下有实体方块（液体/装饰不算，树叶算），头顶两格空气
  · 邻接：8 邻接有向边，向上落差 ≤1（跳一格），向下落差 ≤5（无伤落地）；
    斜向防切角；落差 ≥2 时目标列下落走廊必须全空
  · A*：octile 启发式（xz 平面）

由 navlab 独立模块收编（2026-11-03），独立验证记录见
MCBE/navlab/README.md。
"""

from .astar import astar, find_path
from .blocks_v1 import BlockMap, load_map, write_map
from .graph import NavGraph, build_graph, label_components
from .standable import all_standables, column_standables

__all__ = [
    "BlockMap", "load_map", "write_map",
    "all_standables", "column_standables",
    "NavGraph", "build_graph", "label_components",
    "astar", "find_path",
]
