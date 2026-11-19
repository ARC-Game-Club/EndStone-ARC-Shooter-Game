"""寻路网格构建——把站立点连成 8 邻接导航图。

用户 2026-11-03 规格（邻接部分）：

    "分别对自己邻近的所有可站立方块进行计算，判断是否可达
    （从下到上高度落差<=1，因为只能跳一格高，
     从上到下高度落差小于等于5，这个高度落地没有伤害）"

规则落死（8 邻接，用户确认）：

  · 向上：邻列站立面比当前高 ≤ 1（跳一格）
  · 向下：邻列站立面比当前低 ≤ 5（落地无伤害）
  · 斜向防切角：斜边两侧的直行列，在过渡高度窗口
    [min(y, y'), max(y, y')+1] 内不得有实体方块（可以切空气/洞的角，
    不可以穿墙角）
  · 下落物理净空：落差 ≥ 2 时，目标列从落点脚部往上到自己当前
    头顶 (y'+2 .. y+1) 必须全空——不然就是"穿石头往下掉"，不可达
  · 同列多层站立面各自成节点，3D 图

一个节点到同列邻柱可能有多个合法高度的邻居（台阶上方还有一层
掉落面之类）——全建边，让 A* 自己挑。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .blocks_v1 import BlockMap
from .taxonomy import is_air_space

#: (x, z) 的 8 个邻向；前 4 个直行，后 4 个斜向
ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))
NEIGHBORS = ORTHOGONAL + DIAGONAL

MAX_UP = 1     # 只能跳一格
MAX_DOWN = 5   # 5 格落地无伤害

#: 枪战服（和平难度）实际使用的落差上限（2026-11-18）。
#:
#: ⚠️ **为什么不是 5**（这条规格来自生存服场景，枪战服不适用）：
#: `MAX_DOWN=5` 的原话理由是"5 格内落地没有伤害"——那是 **hard 难度**
#: 生存服的诉求（假人摔死是大事）。但枪战服 `difficulty=peaceful`，
#: **摔落一点血都不掉**，用 5 当连通性判据纯属过度保守：
#:
#:   实测（重建整张图，炼狱小镇 47467 节点）：
#:     MAX_DOWN=5  → 258 个连通分量，孤岛 10262 节点（21.6%）
#:     MAX_DOWN=8  → 179 个分量，孤岛 6134（12.9%）
#:     MAX_DOWN=10 → 152 个分量，孤岛 5119（10.8%）
#:     MAX_DOWN=12 → 132 个分量，孤岛 5037（10.6%）
#:   harbor（3586 节点）：5 → 26 个分量/孤岛 14.8%；10 → 10 个/孤岛 2.8%
#:
#: 那些"孤岛"其实都是**同一张图里走下 6~8 格坎就能到的地方**（实测
#: 炼狱小镇 #50 的 323 个节点与主分量**在同一列 (x,z)**，只差 6~8 格高），
#: 现实里走下坡就到，图里却被这条规则切断了 —— 表现就是 AI 站着不动、
#: 日志刷"不可达"。
#:
#: 现在做成**可配置**（settings.yml 的 `NAV_MAX_DOWN` / `NAV_MAX_UP`），
#: 改完自动重烘，不用重新发版。
DEFAULT_MAX_UP = 1
DEFAULT_MAX_DOWN = 10


@dataclass
class NavGraph:
    """CSR 邻接的**有向**导航图。节点顺序 = standables 的顺序。

    ⚠️ 边是有向的：A→B 表示"站在 A 能迈/跳/落到 B"。规则天然不对称
    （落差 2 往下能跳、往上爬不了），所以同一条物理路线往往是
    A→B、B→A 两条独立判定的边。
    """

    #: 节点坐标 (x, y, z)（y 是脚部高度）
    nodes: List[Tuple[int, int, int]]
    #: 节点脚下方块短名（上色/悬停信息用）
    grounds: List[str]
    #: CSR：offsets[i]..offsets[i+1] 是节点 i 的出边在 targets 里的切片
    offsets: List[int]
    targets: List[int]
    #: 弱连通分量编号（-1 = 未算）；同号 = 忽略方向后互相连通
    component: List[int] = field(default_factory=list)

    # ------------------------------------------------------------------

    def degree(self, i: int) -> int:
        """出度（能迈出去几步）。"""
        return self.offsets[i + 1] - self.offsets[i]

    def neighbors_of(self, i: int) -> List[int]:
        return self.targets[self.offsets[i]:self.offsets[i + 1]]

    def node_index(self) -> Dict[Tuple[int, int, int], int]:
        return {pos: i for i, pos in enumerate(self.nodes)}


def _air(bmap: BlockMap, x: int, y: int, z: int) -> bool:
    """这一格是不是"空气"（没方块 / 可穿装饰）。液体不算。"""
    name = bmap.block_at(x, y, z)
    return name is None or is_air_space(name)


def build_graph(bmap: BlockMap,
                nodes: List[Tuple[int, int, int]],
                grounds: List[str], *,
                max_up: int = MAX_UP,
                max_down: int = MAX_DOWN) -> NavGraph:
    """由站立点列表建 8 邻接导航图。

    nodes/grounds 来自 standable.all_standables()（(z,x,y) 序）。

    ``max_up`` / ``max_down`` 是连通性规则（可配置，见 DEFAULT_MAX_DOWN
    的说明）：向上最多跳几格、向下最多能摔几格。
    """
    column_index: Dict[Tuple[int, int], List[int]] = {}
    for i, (x, _y, z) in enumerate(nodes):
        column_index.setdefault((x, z), []).append(i)

    adj: List[List[int]] = [[] for _ in nodes]

    for i, (x, y, z) in enumerate(nodes):
        for dx, dz in NEIGHBORS:
            col = column_index.get((x + dx, z + dz))
            if not col:
                continue
            nx, nz = x + dx, z + dz
            diagonal = dx != 0 and dz != 0
            for j in col:
                _, ny, _ = nodes[j]
                dy = ny - y
                if dy > max_up or dy < -max_down:
                    continue
                # 脚位可能带 .5（半砖/楼梯）——格子级检查一律用 floor 取整格
                yi, nyi = int(y), int(ny)
                # 下落净空：落差 ≥ 2 时，目标列落点上方至出发头顶必须全空
                # （落点相邻格由可站立判定保证空气，走廊从 floor(ny)+2 起查）
                if dy <= -2 and not all(
                        _air(bmap, nx, yy, nz)
                        for yy in range(nyi + 2, yi + 2)):
                    continue
                # 斜向防切角：两侧直行列在过渡窗口内不得有实体
                if diagonal:
                    lo, hi = min(yi, nyi), max(yi, nyi) + 1
                    ok = True
                    for cx, cz in ((x + dx, z), (x, z + dz)):
                        if not all(_air(bmap, cx, yy, cz) for yy in range(lo, hi + 1)):
                            ok = False
                            break
                    if not ok:
                        continue
                # 有向边：只记 i→j（j→i 由 j 自己那一轮按它的高度重新判）
                adj[i].append(j)

    offsets = [0]
    targets: List[int] = []
    for lst in adj:
        targets.extend(lst)
        offsets.append(len(targets))
    return NavGraph(nodes=list(nodes), grounds=list(grounds),
                    offsets=offsets, targets=targets,
                    component=[-1] * len(nodes))


def label_components(graph: NavGraph) -> int:
    """弱连通分量（并查集，忽略边的方向），返回分量个数。

    用弱连通而不是强连通：玩家寻路只关心"这堆点是不是同一片能互相
    走到的地形"——单向的跳崖边不影响这个判断。
    """
    n = len(graph.nodes)
    parent = list(range(n))

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i in range(n):
        for k in range(graph.offsets[i], graph.offsets[i + 1]):
            ra, rb = find(i), find(graph.targets[k])
            if ra != rb:
                parent[ra] = rb

    comp = [-1] * n
    n_comp = 0
    for i in range(n):
        r = find(i)
        if comp[r] == -1:
            comp[r] = n_comp
            n_comp += 1
        comp[i] = comp[r]
    graph.component = comp
    return n_comp


def label_strong_components(graph: NavGraph) -> List[int]:
    """强连通分量（Tarjan，迭代版）——"互相可达"才算一整片。

    为什么弱连通不够（2026-11-19 服主质疑后加的）：
    `label_components` 用并查集**忽略边的方向**，所以"只能往下跳、爬不
    回去"的单向落差边会把屋顶平台也算进主城区那个大块里。实测炼狱小镇：

        弱连通：152 块，最大 42348 节点（89.2%）
        强连通：604 块，最大 16735 节点（35.3%）

    现有 64 个死斗复活点里 35 个落在"主城区"以外的小块中——屋顶平台
    各自成块（61~707 节点），跟街面**不是互相可达的一片**。按弱连通
    采样就会把人刷到房顶上。

    图是有向的（A→B = "站在 A 能落到 B"），Tarjan 直接吃 CSR 邻接。
    迭代实现：47k 节点 / 28 万条边，递归版会爆栈。
    """
    n = len(graph.nodes)
    offsets = graph.offsets
    targets = graph.targets
    index = [0] * n
    low = [0] * n
    on_stack = bytearray(n)
    stack: List[int] = []
    comp = [-1] * n
    counter = 0
    scc_id = 0
    for root in range(n):
        if index[root]:
            continue
        # (节点, 邻接游标)
        work: List[Tuple[int, int]] = [(root, 0)]
        while work:
            v, pi = work[-1]
            if pi == 0:
                index[v] = low[v] = counter
                counter += 1
                stack.append(v)
                on_stack[v] = 1
            recursed = False
            for k in range(offsets[v], offsets[v + 1]):
                w = targets[k]
                if index[w] == 0:
                    work[-1] = (v, k + 1)
                    work.append((w, 0))
                    recursed = True
                    break
                if on_stack[w] and index[w] < low[v]:
                    low[v] = index[w]
            if recursed:
                continue
            if low[v] == index[v]:
                while True:
                    w = stack.pop()
                    on_stack[w] = 0
                    comp[w] = scc_id
                    if w == v:
                        break
                scc_id += 1
            work.pop()
            if work:
                pv = work[-1][0]
                if low[v] < low[pv]:
                    low[pv] = low[v]
    return comp
