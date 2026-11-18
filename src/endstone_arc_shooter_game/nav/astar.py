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

#: 单次 A* 的展开预算上限（节点数）。超了就当这条路走不通。
#:
#: ⚠️ 这个上限**几乎不可能被触发**：`closed[]` 保证每个节点最多展开一次，
#: 所以展开数 ≤ 图的节点数。实测两张图分别 3586 / 47467 节点，离 20 万
#: 差着两个数量级。之前"超预算"和"真不可达"共用一句文案，把人引到了
#: 错误的方向（2026-11-18 服主问"怎么经常不可达了"）。
DEFAULT_MAX_EXPANSIONS = 200_000


def _octile(dx: int, dz: int) -> float:
    dx, dz = abs(dx), abs(dz)
    if dx < dz:
        dx, dz = dz, dx
    return (dx - dz) + _SQRT2 * dz


def astar(graph: NavGraph, start: int, goal: int,
          max_expansions: int = DEFAULT_MAX_EXPANSIONS, *,
          cost_scale=None, node_penalty=None,
          stats: Optional[dict] = None) -> Optional[List[int]]:
    """节点下标最短路。返回路径节点序列（含首尾）；不可达/超预算返回 None。

    路径多样性的两个钩子（都不填 = 原版确定性最短路，行为不变）：

    * ``cost_scale(cur, nxt) -> float``——边代价倍率。倍率 ≥1 时不破坏
      可采纳性（octile 启发仍低估），只是结果"不一定是绝对最短"。
      NavService 用它做每请求随机抖动：同起点同终点不再永远同一条路。
    * ``node_penalty(nxt) -> float``——进入该节点的附加代价（≥0）。
      NavService 用它做拥堵热度：别人刚走过的走廊加价，后面的 AI
      自动换支路。

    ``stats``（可选 dict，out 参数）——填失败原因，调用方好写日志：

    * ``stats["reason"]``：``"ok"`` / ``"budget"``（展开超预算）/
      ``"unreachable"``（堆空了还没到＝真的走不通，含单向边）。
    * ``stats["expansions"]``：实际展开的节点数。

    ⚠️ "超预算"和"真不可达"以前共用一句"不可达（分量断开或只有单向
    跳崖边）"，排查时被带偏过（2026-11-18）。现在分开报。
    """
    if stats is not None:
        stats.clear()
        stats["reason"] = "unreachable"
        stats["expansions"] = 0
    n = len(graph.nodes)
    if not (0 <= start < n and 0 <= goal < n):
        return None
    if start == goal:
        if stats is not None:
            stats["reason"] = "ok"
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
            if stats is not None:
                stats["reason"] = "ok"
                stats["expansions"] = expansions
            return path
        expansions += 1
        if expansions > max_expansions:
            if stats is not None:
                stats["reason"] = "budget"
                stats["expansions"] = expansions
            return None
        cx, _, cz = graph.nodes[cur]
        for k in range(graph.offsets[cur], graph.offsets[cur + 1]):
            nxt = graph.targets[k]
            if closed[nxt]:
                continue
            nx, _, nz = graph.nodes[nxt]
            step = (cost_scale(cur, nxt) if cost_scale is not None
                    else (_SQRT2 if (nx != cx and nz != cz) else 1.0))
            ng = g[cur] + step + (node_penalty(nxt) if node_penalty is not None
                                  else 0.0)
            if ng < g[nxt]:
                g[nxt] = ng
                came[nxt] = cur
                heapq.heappush(heap, (ng + _octile(nx - gx, nz - gz), nxt))
    if stats is not None:
        stats["reason"] = "unreachable"
        stats["expansions"] = expansions
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
