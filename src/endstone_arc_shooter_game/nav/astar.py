"""A* 寻路——在 NavGraph 的 CSR 邻接上跑。

代价：直行 1、斜行 √2（垂直落差折进同一条边，不加价）。
启发：xz 平面 octile 距离（不含 y，保证 admissible——y 只会让真实
代价更大，不会更小）。
"""

from __future__ import annotations

import heapq
from typing import List, Optional, Tuple

from .graph import NavGraph

_SQRT2 = 2.0 ** 0.5


def _octile(dx: int, dz: int) -> float:
    dx, dz = abs(dx), abs(dz)
    if dx < dz:
        dx, dz = dz, dx
    return (dx - dz) + _SQRT2 * dz


def astar(graph: NavGraph, start: int, goal: int,
          max_expansions: int = 200_000) -> Optional[List[int]]:
    """节点下标最短路。返回路径节点序列（含首尾）；不可达/超预算返回 None。"""
    n = len(graph.nodes)
    if not (0 <= start < n and 0 <= goal < n):
        return None
    if start == goal:
        return [start]
    gx, _, gz = graph.nodes[goal]

    INF = float("inf")
    g = [INF] * n
    came: List[int] = [-1] * n
    closed = [False] * n
    g[start] = 0.0
    heap: List[Tuple[float, int]] = [(_octile(graph.nodes[start][0] - gx,
                                              graph.nodes[start][2] - gz), start)]
    expansions = 0
    while heap:
        _f, cur = heapq.heappop(heap)
        if closed[cur]:
            continue
        closed[cur] = True
        if cur == goal:
            path = [cur]
            while came[cur] != -1:
                cur = came[cur]
                path.append(cur)
            path.reverse()
            return path
        expansions += 1
        if expansions > max_expansions:
            return None
        cx, _, cz = graph.nodes[cur]
        for k in range(graph.offsets[cur], graph.offsets[cur + 1]):
            nxt = graph.targets[k]
            if closed[nxt]:
                continue
            nx, _, nz = graph.nodes[nxt]
            step = _SQRT2 if (nx != cx and nz != cz) else 1.0
            ng = g[cur] + step
            if ng < g[nxt]:
                g[nxt] = ng
                came[nxt] = cur
                heapq.heappush(heap, (ng + _octile(nx - gx, nz - gz), nxt))
    return None


def find_path(graph: NavGraph,
              start_pos: Tuple[int, int, int],
              goal_pos: Tuple[int, int, int]) -> Optional[List[Tuple[int, int, int]]]:
    """坐标版：起终点直接给 (x, y, z)，返回坐标路径点队列。"""
    idx = graph.node_index()
    s = idx.get(tuple(start_pos))
    t = idx.get(tuple(goal_pos))
    if s is None or t is None:
        return None
    path = astar(graph, s, t)
    if path is None:
        return None
    return [graph.nodes[i] for i in path]
