# -*- coding: utf-8 -*-
"""个人死斗（ffa）出生点池——从导航网格最大连通域采样。

只在第一次给地图创建 ffa 模式时算一次（插件侧 _generate_ffa_spawn_pool），
结果落 shooter.db 的 map_spawns（mode='ffa', team_id='a'），之后一直复用。

采样规则：
- 只取最大弱连通域：component 数组烘焙时已由 label_components 预计算，
  直接数众数即可（NavService.bake 的 biggest_component_pct 同款算法）。
- 过滤到地图 region 水平界（四边各收缩 border 格，别贴墙刷人）。
- 洗牌后贪心采样：与已选点水平间距 ≥ min_spacing 才收，直到 max_points。
  网格哈希加速（格子边长 = min_spacing，只需查 3×3 邻域）。
- 输出的出生点 radius=0：pick_spawn 不会再加随机抖动，避免把人推进墙里。
- yaw 朝采样区域水平质心：进场第一眼看到的是竞技场，不是一堵墙。

坐标细节：节点是脚部坐标，x/z 为整格、y 可为 .5（半砖/楼梯顶）。
传送点用 x+0.5 / z+0.5 落到方块中心（与假人 _center_path 同约定）。
"""

from __future__ import annotations

import math
import random
from collections import Counter
from typing import Any, Dict, List, Optional, Sequence, Tuple

#: region 四边默认收缩格数——别让玩家贴着边界复活
DEFAULT_BORDER = 2.0


def largest_component_id(component: Sequence[int]) -> Optional[int]:
    """最大弱连通域的 component id；空图返回 None。"""
    if not component:
        return None
    return Counter(component).most_common(1)[0][0]


def largest_component_nodes(nav: Any) -> List[int]:
    """最大连通域里所有节点的下标。"""
    comp = largest_component_id(nav.component)
    if comp is None:
        return []
    return [i for i, c in enumerate(nav.component) if c == comp]


def _yaw_towards(fx: float, fz: float, tx: float, tz: float) -> float:
    """面向 (tx,tz) 的 Minecraft yaw（0=+Z 南，顺时针增大）。"""
    dx, dz = tx - fx, tz - fz
    if dx == 0 and dz == 0:
        return 0.0
    # 方向向量→yaw：x=-sin(yaw)、z=cos(yaw) ⇒ yaw=atan2(-dx, dz)
    return math.degrees(math.atan2(-dx, dz)) % 360.0


def compute_ffa_spawn_pool(
    nav: Any,
    bounds: Optional[Sequence[float]] = None,
    *,
    min_spacing: float = 12.0,
    max_points: int = 64,
    border: float = DEFAULT_BORDER,
    seed: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """在最大连通域内采样一池互相拉开距离的出生点。

    bounds 是 region_bounds(map_cfg) 的 (x1,x2,y1,y2,z1,z2)；None 则不按
    region 过滤（整个 nav 图都算竞技场）。每次调用都是新随机布局；调用方
    负责把结果持久化（"只算一次"的语义在插件层，不在这里）。
    """
    cell = max(2.0, float(min_spacing))
    node_idx = largest_component_nodes(nav)

    lo_x = hi_x = lo_z = hi_z = None
    if bounds is not None and len(bounds) == 6:
        x1, x2, _y1, _y2, z1, z2 = (float(v) for v in bounds)
        lo_x, hi_x = x1 + border, x2 - border
        lo_z, hi_z = z1 + border, z2 - border
        if lo_x > hi_x or lo_z > hi_z:
            # region 太小收缩不出缓冲带 → 退回原界（总比刷不出点强）
            lo_x, hi_x, lo_z, hi_z = x1, x2, z1, z2
        node_idx = [
            i for i in node_idx
            if lo_x <= nav.nodes[i][0] <= hi_x and lo_z <= nav.nodes[i][2] <= hi_z
        ]
    if not node_idx:
        return []

    cx = sum(nav.nodes[i][0] for i in node_idx) / len(node_idx)
    cz = sum(nav.nodes[i][2] for i in node_idx) / len(node_idx)

    order = list(node_idx)
    random.Random(seed).shuffle(order)

    grid: Dict[Tuple[int, int], List[Tuple[float, float]]] = {}
    picked: List[int] = []
    min2 = cell * cell
    for i in order:
        x, _y, z = nav.nodes[i]
        gx, gz = math.floor(x / cell), math.floor(z / cell)
        spaced = True
        for ddx in (-1, 0, 1):
            if not spaced:
                break
            for ddz in (-1, 0, 1):
                near = grid.get((gx + ddx, gz + ddz))
                if not near:
                    continue
                if any(
                    (px - x) * (px - x) + (pz - z) * (pz - z) < min2
                    for px, pz in near
                ):
                    spaced = False
                    break
        if not spaced:
            continue
        grid.setdefault((gx, gz), []).append((x, z))
        picked.append(i)
        if len(picked) >= max_points:
            break

    spawns: List[Dict[str, Any]] = []
    for i in picked:
        x, y, z = nav.nodes[i]
        # yaw 按最终落点（方块中心）计算，别用整格角点算（差 3°+）
        fx, fz = x + 0.5, z + 0.5
        spawns.append({
            "x": fx,
            "y": y,
            "z": fz,
            "radius": 0,  # pick_spawn 遇 radius=0 不加抖动，保持精确脚位
            "yaw": round(_yaw_towards(fx, fz, cx, cz), 1),
            "pitch": 0.0,
        })
    return spawns
