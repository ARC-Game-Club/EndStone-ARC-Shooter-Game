# -*- coding: utf-8 -*-
"""个人死斗（ffa）出生点池——从导航网格**强连通域**（互相可达）采样。

只在第一次给地图创建 ffa 模式时算一次（插件侧 _generate_ffa_spawn_pool），
结果落 shooter.db 的 map_spawns（mode='ffa', team_id='a'），之后一直复用。

采样规则：
- **只取最大强连通域**（2026-11-19 服主改判）："两个点互相可达才算连在
  一起"——屋顶平台是靠**单向落差边**被弱连通算进主城区那块大分量的，但
  从那里**爬不回去**（往上只允许跳 1 格）。按弱连通采样，人就被刷到房
  顶上去了。实测炼狱小镇：
      弱连通：152 块，最大 42348 节点（89.2%），其中 34% 的节点在 y≥69
      强连通：604 块，最大 16735 节点（35.3%），全是街道层
  现有 64 个复活点里 35 个落在主城区之外的小块（屋顶平台各自成块，
  61~707 节点）。改按强连通采样后：64 个点 y 全在 60~61，0 个在屋顶。
- 过滤到地图 region 水平界（四边各收缩 border 格，别贴墙刷人）。
- 洗牌后贪心采样：与已选点水平间距 ≥ min_spacing 才收，直到 max_points。
  网格哈希加速（格子边长 = min_spacing，只需查 3×3 邻域）。
- 输出的出生点 radius=0：pick_spawn 不会再加随机抖动，避免把人推进墙里。
- yaw 朝采样区域水平质心：进场第一眼看到的是竞技场，不是一堵墙。

兼容：老烘焙缓存没有强连通分量时（nav.scc 为空）自动退回弱连通采样，
不会采不出点；插件侧会把用的哪套口径写进日志。

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

#: 采样口径标识（返回给插件侧写日志）
MODE_SCC = "scc"
MODE_WEAK = "weak"


def largest_component_id(component: Sequence[int]) -> Optional[int]:
    """最大弱连通域的 component id；空图返回 None。"""
    if not component:
        return None
    return Counter(component).most_common(1)[0][0]


def largest_component_nodes(nav: Any) -> List[int]:
    """最大弱连通域里所有节点的下标。"""
    comp = largest_component_id(nav.component)
    if comp is None:
        return []
    return [i for i, c in enumerate(nav.component) if c == comp]


def largest_scc_id(scc: Sequence[int]) -> Optional[int]:
    """最大强连通域（互相可达）的 scc id；空图返回 None。"""
    if not scc:
        return None
    return Counter(scc).most_common(1)[0][0]


def largest_scc_nodes(nav: Any) -> List[int]:
    """最大强连通域里所有节点的下标。

    nav 没有强连通数据（旧烘焙缓存）时返回空列表 —— 调用方据此退回弱连通。
    """
    scc = getattr(nav, "scc", None)
    if not scc:
        return []
    sid = largest_scc_id(scc)
    if sid is None:
        return []
    return [i for i, c in enumerate(scc) if c == sid]


def _yaw_towards(fx: float, fz: float, tx: float, tz: float) -> float:
    """面向 (tx,tz) 的 Minecraft yaw（0=+Z 南，顺时针增大）。"""
    dx, dz = tx - fx, tz - fz
    if dx == 0 and dz == 0:
        return 0.0
    # 方向向量→yaw：x=-sin(yaw)、z=cos(yaw) ⇒ yaw=atan2(-dx, dz)
    return math.degrees(math.atan2(-dx, dz)) % 360.0


def compute_ffa_spawn_pool_ex(
    nav: Any,
    bounds: Optional[Sequence[float]] = None,
    *,
    min_spacing: float = 12.0,
    max_points: int = 64,
    border: float = DEFAULT_BORDER,
    seed: Optional[int] = None,
    strict: bool = True,
) -> Tuple[List[Dict[str, Any]], str]:
    """采样一池互相拉开距离的出生点，返回 (出生点列表, 采样口径)。

    bounds 是 region_bounds(map_cfg) 的 (x1,x2,y1,y2,z1,z2)；None 则不按
    region 过滤（整个 nav 图都算竞技场）。每次调用都是新随机布局；调用方
    负责把结果持久化（"只算一次"的语义在插件层，不在这里）。

    strict=True（默认）按**最大强连通域**采样——互相可达才算一整片；
    strict=False 退回弱连通（老缓存无强连通数据时自动走这条）。
    """
    cell = max(2.0, float(min_spacing))

    # —— 候选域：强连通优先，采不到就退回弱连通 ——
    mode = MODE_SCC
    node_idx = largest_scc_nodes(nav) if strict else []
    if not node_idx:
        mode = MODE_WEAK
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
        return [], mode

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
    return spawns, mode


def compute_ffa_spawn_pool(
    nav: Any,
    bounds: Optional[Sequence[float]] = None,
    *,
    min_spacing: float = 12.0,
    max_points: int = 64,
    border: float = DEFAULT_BORDER,
    seed: Optional[int] = None,
    strict: bool = True,
) -> List[Dict[str, Any]]:
    """兼容旧调用：只要出生点列表（采样口径见 compute_ffa_spawn_pool_ex）。"""
    spawns, _mode = compute_ffa_spawn_pool_ex(
        nav, bounds, min_spacing=min_spacing, max_points=max_points,
        border=border, seed=seed, strict=strict,
    )
    return spawns
