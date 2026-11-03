# -*- coding: utf-8 -*-
"""导航图体检：站立点 / 有向边按高差分布 / 词表敏感度。

用途：改 `nav/taxonomy.py` 或 `nav/standable.py` 之前/之后跑一遍，
对比"引擎做不了的边"（上 1 格 + 下坡）占多少——这个比例决定了
假人执行侧（行为包 JS）需要处理多少特殊动作。

用法：
    python scripts/nav_graph_stats.py \
        --map "C:/.../plugins/arc_shooter_game/nav/maps/harbor.json"

    # 对比：把铁栏/活板门这类薄片方块也当空气
    python scripts/nav_graph_stats.py --map ... --thin-as-air
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Dict, List, Tuple

# 允许直接跑源码树（不安装也能用）
_SRC = Path(__file__).resolve().parents[1] / "src"
if _SRC.is_dir():
    sys.path.insert(0, str(_SRC))

from endstone_arc_shooter_game.nav.blocks_v1 import load_map  # noqa: E402
from endstone_arc_shooter_game.nav.taxonomy import (  # noqa: E402
    LIQUIDS, PASSABLE_DECOR, short_name,
)

#: 上游 `_PASSABLE_DECOR_SUFFIXES`——注意里面有 "_carpet"，
#: 所以 16 种颜色变体即使不在词表里也按空气处理。
_PASSABLE_SUFFIXES = ("_carpet", "_tulip", "_sapling")

#: 薄片/栅栏类：游戏里**能穿过去**，但**站不住**。
#: 上游词表默认从严（未知方块当实心），这些没被列进去 →
#: 导航图里多出"站在铁栏顶上"的幽灵节点（实测 22 个，脚高 y=68），
#: 而且真实能走的格子被判成墙。
THIN_BLOCKS = ("iron_bars", "trapdoor", "ladder", "vine", "glow_lichen",
               "scaffolding", "cobweb")

ORTHOGONAL = ((1, 0), (-1, 0), (0, 1), (0, -1))
DIAGONAL = ((1, 1), (1, -1), (-1, 1), (-1, -1))


def make_pred(thin_as_air: bool):
    air_set = set(PASSABLE_DECOR)
    if thin_as_air:
        air_set |= set(THIN_BLOCKS)

    def is_air(name: str) -> bool:
        n = short_name(name).lower()
        if n in air_set:
            return True
        return n.endswith(_PASSABLE_SUFFIXES)

    def is_support(name: str) -> bool:
        n = short_name(name).lower()
        if n in LIQUIDS:
            return False
        if is_air(name):
            return False
        return True

    return is_air, is_support


def compute_nodes(bmap, is_air, is_support) -> List[Tuple[int, int, int]]:
    nodes: List[Tuple[int, int, int]] = []
    for (x, z), col in bmap.columns.items():
        for y, name in col.items():
            if not is_support(name):
                continue
            foot = y + 1
            b_foot = bmap.block_at(x, foot, z)
            b_head = bmap.block_at(x, foot + 1, z)
            if b_foot is not None and not is_air(b_foot):
                continue
            if b_head is not None and not is_air(b_head):
                continue
            nodes.append((x, foot, z))
    nodes.sort()
    return nodes


def compute_edges(bmap, nodes, is_air) -> Counter:
    index: Dict[Tuple[int, int], List[int]] = {}
    for i, (x, _y, z) in enumerate(nodes):
        index.setdefault((x, z), []).append(i)

    def air_at(x: int, y: int, z: int) -> bool:
        b = bmap.block_at(x, y, z)
        return b is None or is_air(b)

    cnt: Counter = Counter()
    for i, (x, y, z) in enumerate(nodes):
        for dx, dz in ORTHOGONAL + DIAGONAL:
            for j in index.get((x + dx, z + dz), ()):
                ny = nodes[j][1]
                dy = ny - y
                if dy > 1 or dy < -5:
                    continue
                if dy <= -2 and not all(air_at(x + dx, yy, z + dz)
                                        for yy in range(ny + 2, y + 2)):
                    continue
                if dx != 0 and dz != 0:
                    lo, hi = min(y, ny), max(y, ny) + 1
                    if not (all(air_at(x + dx, yy, z) for yy in range(lo, hi + 1))
                            and all(air_at(x, yy, z + dz) for yy in range(lo, hi + 1))):
                        continue
                cnt[dy] += 1
    return cnt


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--map", required=True, help="blocks-v1 JSON 路径")
    ap.add_argument("--thin-as-air", action="store_true",
                    help="把铁栏/活板门等薄片方块也当空气（对比实验）")
    args = ap.parse_args()

    bmap = load_map(args.map)
    is_air, is_support = make_pred(args.thin_as_air)
    nodes = compute_nodes(bmap, is_air, is_support)
    cnt = compute_edges(bmap, nodes, is_air)

    total = sum(cnt.values())
    flat = cnt.get(0, 0)
    up1 = cnt.get(1, 0)
    down = sum(v for k, v in cnt.items() if k < 0)

    print(f"地图 {bmap.map_id}  列={len(bmap.columns)}  "
          f"未加载列={bmap.unloaded_columns}/{bmap.total_columns}")
    print(f"词表: {'薄片方块当空气' if args.thin_as_air else '默认从严'}")
    print(f"站立点 = {len(nodes)}   有向边 = {total}")
    print(f"  平走 dy=0 : {flat:6d} ({flat*100.0/max(total,1):5.1f}%)")
    print(f"  上 1 格   : {up1:6d} ({up1*100.0/max(total,1):5.1f}%)")
    print(f"  下坡 1-5 : {down:6d} ({down*100.0/max(total,1):5.1f}%)")
    print(f"  → 引擎做不了的边 = {(up1+down)*100.0/max(total,1):5.1f}%")

    ghosts = [(x, y, z) for (x, y, z) in nodes
              if (b := bmap.block_at(x, y - 1, z))
              and short_name(b).lower() == "iron_bars"]
    if ghosts:
        ys = Counter(y for (_x, y, _z) in ghosts)
        print(f"「站在铁栏顶上」的幽灵节点 = {len(ghosts)} 个，"
              f"脚部高度 {dict(sorted(ys.items()))}")
    else:
        print("「站在铁栏顶上」的幽灵节点 = 0 个")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
