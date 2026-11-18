# -*- coding: utf-8 -*-
"""NavService——导航网格的运行时管家：装填基线、懒烘焙、查询、出生点连通。

数据目录布局（都在插件数据目录 plugins/ARCShooterGame 下）：

    nav/maps/<map_id>.json        blocks-v1 地形（内置基线装填 or /gs bake 导出）
    nav/<map_id>.nav.json         烘焙产物（节点/CSR 边/分量），懒生成

内存缓存一张图只烘一次；`/gs bake` 重导后会重烘。
"""

from __future__ import annotations

import json
import math
import random
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .astar import DEFAULT_MAX_EXPANSIONS, astar
from .blocks_v1 import load_map
from .graph import DEFAULT_MAX_DOWN, DEFAULT_MAX_UP, build_graph, label_components
from .standable import all_standables

NAV_FORMAT = "nav-v1"

# ---------------------------------------------------------------------------
# 路径多样性（服主 2026-11-18："哪怕有多条支路，AI 只会走最短路径去干架"）
#
# A* 是确定性的：同起点同终点永远同一条路，全场 AI 挤同一条走廊。
# 两个旋钮（改完不用重启世界，只影响后续查询）：
#
# ① NAV_JITTER——每条边代价 × Uniform(1, 1+JITTER)：每次请求的路径
#    略有不同，等效于"同一张图上的随机最优"。0.25 对 10 格的路最多
#    绕 2.5 格的等效距离，肉眼仍是"合理的路"。
# ② NAV_HEAT——"拥堵热度"：别人 15 秒内走过的中途节点加价，后面的
#    AI 自动换支路；走廊冷却后自动变回可行。惩罚 8.0/节点 意味着
#    只要存在长度差 ≤8 格的替代支路就一定换道。热度按请求者记名：
#    自己的热度对自己不可见（RTC 滚动重规划时不会绕开自己正在走的
#    路，避免走位发酒疯），只挡别人。
# ---------------------------------------------------------------------------
NAV_JITTER = 0.25
NAV_HEAT_PENALTY = 8.0
NAV_HEAT_TTL = 15.0
_NAV_SQRT2 = 2.0 ** 0.5


class _LoadedNav:
    """一张图烘焙后的内存形态。"""

    __slots__ = ("map_id", "nodes", "grounds", "offsets", "targets",
                 "component", "index", "by_col", "stats",
                 "component_count", "top_components", "island_nodes")

    def __init__(self, map_id: str, nodes, grounds, offsets, targets,
                 component, stats) -> None:
        self.map_id = map_id
        self.nodes = nodes            # [(x, y, z), ...] 脚部坐标
        self.grounds = grounds        # [脚下方块短名, ...]
        self.offsets = offsets        # CSR
        self.targets = targets
        self.component = component
        self.stats = stats
        self.index: Dict[Tuple[int, int, int], int] = {p: i for i, p in enumerate(nodes)}
        #: (x, z) -> [节点下标...]（脚高升序）——吸附查询用，预计算
        by_col: Dict[Tuple[int, int], List[int]] = {}
        for i, (x, _y, z) in enumerate(nodes):
            by_col.setdefault((x, z), []).append(i)
        self.by_col = by_col
        # —— 孤岛统计（2026-11-18）——
        #
        # 烘焙图里"走不通"的地方一目了然：连通分量数 + 每个分量多大。
        # 实测炼狱小镇 47467 个节点分成 258 块，最大一块只占 78.4%，
        # 剩下 21.6%（一万多个节点）是孤岛——AI 走进去就出不来。
        # 这个统计直接进 api_nav_status，服主不用再翻 nav.json。
        from collections import Counter
        comp_sizes = Counter(component)
        self.component_count = len(comp_sizes)
        self.top_components = comp_sizes.most_common(8)
        biggest = comp_sizes.most_common(1)[0][1] if comp_sizes else 0
        self.island_nodes = max(0, len(nodes) - biggest)

    def out_degree(self, i: int) -> int:
        return self.offsets[i + 1] - self.offsets[i]


class NavService:
    """导航网格服务。插件持有单例，所有方法主线程调用。"""

    def __init__(self, data_dir: Path, logger: Any,
                 bundled_dir: Optional[Path] = None, *,
                 max_up: int = DEFAULT_MAX_UP,
                 max_down: int = DEFAULT_MAX_DOWN) -> None:
        self._data_dir = Path(data_dir)
        self._nav_dir = self._data_dir / "nav"
        self._maps_dir = self._nav_dir / "maps"
        self._logger = logger
        #: 内置基线目录（随 wheel 分发）；装填到数据目录，不覆盖
        self._bundled_dir = Path(bundled_dir) if bundled_dir else None
        self._cache: Dict[str, _LoadedNav] = {}
        self._failed: Dict[str, str] = {}
        #: map_id → {节点下标: (标记时刻, 请求者名)}——拥堵热度
        self._heat: Dict[str, Dict[int, tuple]] = {}
        #: 连通性规则（向上最多跳几格 / 向下最多摔几格）——可配置
        #: （settings.yml 的 NAV_MAX_UP / NAV_MAX_DOWN）。改完**自动重烘**：
        #: 烘焙产物里记着当时的规则，对不上就当缓存失效重烘一遍。
        self.max_up = int(max_up)
        self.max_down = int(max_down)

    # ------------------------------------------------------------------
    # 装填 / 烘焙
    # ------------------------------------------------------------------

    def install_bundled(self) -> int:
        """把内置基线铺到数据目录（已有同名文件不覆盖）。返回铺了几个。

        两类：maps/*.json（blocks-v1 地形）和 ../baked/*.nav.json（预烘焙
        导航缓存——带着它首次查询只做一次文件解析，不用现场烘焙）。
        """
        if not self._bundled_dir or not self._bundled_dir.is_dir():
            return 0
        self._maps_dir.mkdir(parents=True, exist_ok=True)
        n = 0
        for src in sorted(self._bundled_dir.glob("*.json")):
            dst = self._maps_dir / src.name
            if dst.exists():
                continue
            try:
                raw = json.loads(src.read_text(encoding="utf-8"))
                if raw.get("format") != "blocks-v1":
                    continue
                dst.write_bytes(src.read_bytes())
                n += 1
            except Exception as exc:
                self._logger.warning(f"导航基线装填失败 {src.name}: {exc}")
        # 预烘焙导航缓存：nav/baked/*.nav.json → 数据目录 nav/*.nav.json
        baked_dir = self._bundled_dir.parent / "baked"
        if baked_dir.is_dir():
            self._nav_dir.mkdir(parents=True, exist_ok=True)
            for src in sorted(baked_dir.glob("*.nav.json")):
                dst = self._nav_dir / src.name
                if dst.exists():
                    continue
                try:
                    dst.write_bytes(src.read_bytes())
                    n += 1
                except Exception as exc:
                    self._logger.warning(f"预烘焙导航装填失败 {src.name}: {exc}")
        return n

    def _blocks_path(self, map_id: str) -> Optional[Path]:
        p = self._maps_dir / f"{map_id}.json"
        if p.exists():
            return p
        if self._bundled_dir:
            q = self._bundled_dir / f"{map_id}.json"
            if q.exists():
                return q
        return None

    def available_maps(self) -> List[str]:
        """有哪些 blocks-v1 地形可用（数据目录 ∪ 内置）。"""
        ids = set()
        for d in (self._maps_dir, self._bundled_dir):
            if d and d.is_dir():
                for f in d.glob("*.json"):
                    ids.add(f.stem)
        return sorted(ids)

    def has_blocks(self, map_id: str) -> bool:
        """这张图有没有 blocks-v1 地形（能烘焙/能查）。"""
        return self._blocks_path(map_id) is not None

    def bake(self, map_id: str, force: bool = False) -> _LoadedNav:
        """烘焙一张图（有缓存文件就先读，force=True 无视缓存文件重烘）。"""
        cached = self._cache.get(map_id)
        if cached and not force:
            return cached
        nav_path = self._nav_dir / f"{map_id}.nav.json"
        if not force and nav_path.exists() and self._load_nav_file(map_id, nav_path):
            return self._cache[map_id]

        blocks_path = self._blocks_path(map_id)
        if blocks_path is None:
            raise FileNotFoundError(f"地图 {map_id} 没有 blocks-v1 地形数据"
                                    f"（先 /gs bake {map_id} 导出）")
        t0 = time.perf_counter()
        bmap = load_map(blocks_path)
        standables = all_standables(bmap)
        nodes = [p for p, _ in standables]
        grounds = [n for _, n in standables]
        graph = build_graph(bmap, nodes, grounds,
                            max_up=self.max_up, max_down=self.max_down)
        n_comp = label_components(graph)
        from collections import Counter
        comp_sizes = Counter(graph.component)
        loaded = _LoadedNav(map_id, nodes, grounds, graph.offsets, graph.targets,
                            graph.component, {
                                "standables": len(nodes),
                                "edges": len(graph.targets),
                                "components": n_comp,
                                "biggest_component_pct": round(
                                    100.0 * comp_sizes.most_common(1)[0][1] / len(nodes), 1) if nodes else 0.0,
                                "block_count": 0,
                                "bake_ms": round((time.perf_counter() - t0) * 1000),
                            })
        self._cache[map_id] = loaded
        self._failed.pop(map_id, None)
        self._write_nav_file(nav_path, loaded, bmap)
        return loaded

    # -- nav-v1 文件读写（重启后免重烘） ----------------------------------

    def _write_nav_file(self, path: Path, nav: _LoadedNav, bmap: Any) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "format": NAV_FORMAT, "map_id": nav.map_id,
                "baked_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source_exported_at": bmap.exported_at,
                "rule": {"max_up": self.max_up, "max_down": self.max_down,
                         "neighbors": 8},
                "nodes": [list(p) for p in nav.nodes],
                "grounds": nav.grounds,
                "edges": {"offsets": nav.offsets, "targets": nav.targets},
                "component": nav.component,
                "stats": nav.stats,
            }
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:
            self._logger.warning(f"导航缓存写文件失败 {path}: {exc}")

    def _load_nav_file(self, map_id: str, path: Path) -> bool:
        try:
            d = json.loads(path.read_text(encoding="utf-8"))
            if d.get("format") != NAV_FORMAT:
                return False
            # 规则对不上 → 缓存作废，重烘一遍（2026-11-18）。
            # 落差上限改了却还用老图，就是"改了设置没反应"。
            rule = d.get("rule") or {}
            if (int(rule.get("max_up", -1)) != self.max_up
                    or int(rule.get("max_down", -1)) != self.max_down):
                self._logger.info(
                    f"导航缓存规则已变（max_up {rule.get('max_up')}→{self.max_up}, "
                    f"max_down {rule.get('max_down')}→{self.max_down}），重烘 {map_id}")
                return False
            nav = _LoadedNav(map_id,
                             [tuple(p) for p in d["nodes"]], list(d["grounds"]),
                             d["edges"]["offsets"], d["edges"]["targets"],
                             list(d["component"]), dict(d.get("stats", {})))
            self._cache[map_id] = nav
            return True
        except Exception as exc:
            self._logger.warning(f"导航缓存读文件失败 {path}: {exc}")
            return False

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def ensure(self, map_id: str) -> _LoadedNav:
        """加载（必要时烘焙）。失败抛异常并记一次失败原因（短时间内不重试）。"""
        err = self._failed.get(map_id)
        if err:
            raise RuntimeError(err)
        try:
            return self.bake(map_id)
        except Exception as exc:
            self._failed[map_id] = str(exc)
            raise

    def snap(self, nav: _LoadedNav, pos) -> Optional[int]:
        """坐标 → 站立点下标。本列精确脚位 → 邻近列（**高度优先**，再比水平距离）。

        ⚠️ 排序键必须是 **(高度差, 水平距离)**，不能反过来（2026-11-03）：
        原来按 (水平距离, 高度差) 排，于是"同列但高 4 格"的节点会赢过
        "隔壁列、同高度"的节点——假人被吸附到 4 格高的铁栏顶上，
        路径第一步就变成"向上 4 格"，引擎寻路走不到 → 原地罚站
        （日志：`arena 卡死 … 本段已走 0.0 格`）。
        物理上假人只能在**当前高度层**活动，高度差必须优先。
        """
        fx, fy, fz = float(pos[0]), float(pos[1]), float(pos[2])
        bx, bz = math.floor(fx), math.floor(fz)
        # 脚位可为 .5（半砖/楼梯顶）——直接按浮点精确匹配
        foot = float(fy)
        exact = nav.index.get((bx, foot, bz))
        if exact is None and fy != int(fy):
            # 位置略偏（跳跃中/微浮空）→ 试整格与半格两个候选
            for cand in (float(math.floor(fy)) + 0.5, float(math.floor(fy))):
                exact = nav.index.get((bx, cand, bz))
                if exact is not None:
                    break
        if exact is not None:
            return exact
        best = None
        best_key = None
        # 半径 2 找不到（站在掩体/薄片结构旁很常见）→ 扩到 5：
        # 拿不到起点节点 = 永远要不到路径 = 假人罚站（2026-11-03 实测）
        for radius in (2, 5):
            hit = _snap_near(nav, bx, bz, foot, radius)
            if hit is not None:
                return hit
        return None

    def nearest_node(self, nav: "_LoadedNav", pos):
        """全图找离 pos 最近的节点（高度差优先）。吸附半径兜底用。"""
        fx, fy, fz = float(pos[0]), float(pos[1]), float(pos[2])
        bx, bz = math.floor(fx), math.floor(fz)
        hit = _snap_near(nav, bx, bz, float(fy), 8)
        if hit is not None:
            return hit
        best, best_key = None, None
        for i, (x, y, z) in enumerate(nav.nodes):
            key = (abs(y - fy), max(abs(x - bx), abs(z - bz)))
            if best_key is None or key < best_key:
                best_key, best = key, i
        return best

    def query(self, map_id: Optional[str], start, goal,
              requester: str = "") -> Dict[str, Any]:
        """A* 查询。map_id 为 None 时不定位（调用方自己解析好再传）。

        ``requester`` 是发起请求的假人名：热度按请求者记名，自己的热度
        对自己不可见（RTC 重规划不绕自己正在走的路），只挡别人。
        返回 {"ok", "text", "path": [[x,y,z],...]}（api_* 约定）。
        """
        try:
            if not map_id:
                return {"ok": False, "text": "api_request_path: map_id 为空", "path": []}
            nav = self.ensure(map_id)
            s = self.snap(nav, start)
            t = self.snap(nav, goal)
            if s is None:
                # 吸附失效（站位刁钻/薄片包围）：给最近可用节点让调用方
                # 把假人传送过去再要路径（2026-11-03 服主："吸附失效就
                # 传送到最近的可用起点"）
                near = self.nearest_node(nav, start)
                if near is None:
                    return {"ok": False, "text": "api_request_path: 图内无节点", "path": []}
                return {"ok": False, "text": "start_snap_failed",
                        "snap_to": list(nav.nodes[near]), "path": []}
            if t is None:
                return {"ok": False, "text": f"api_request_path: 终点 {goal} 附近无站立点", "path": []}
            now = time.monotonic()
            heat = self._heat.setdefault(map_id, {})
            astat: Dict[str, Any] = {}
            path = astar(
                nav, s, t,
                max_expansions=DEFAULT_MAX_EXPANSIONS,
                cost_scale=self._make_scale(nav),
                node_penalty=self._make_penalty(heat, now, requester),
                stats=astat,
            )
            if path is None:
                # —— 失败原因分三类（2026-11-18）——
                #
                # 以前一律报"不可达（分量断开或只有单向跳崖边）"，把三种
                # 完全不同的病混成一句，排查时被带偏（服主："怎么经常不可
                # 达了，是不是多样性寻路有问题"——实测不是，是图本身断开）。
                # 现在:
                #   budget        —— A* 展开超预算（图太大）。实测两张图
                #                     3586 / 47467 节点，离 20 万预算差两个
                #                     数量级，基本不会发生。
                #   component_split —— 起终点分属不同连通分量：两块区域之
                #                     间根本没有连起来的路（地图有孤岛）。
                #   oneway        —— 同在个分量，但边是有向的（跳崖/单向
                #                     通道），这个方向走不通。
                sc = nav.component[s]
                tc = nav.component[t]
                reason = astat.get("reason", "unreachable")
                if reason == "budget":
                    kind = "budget"
                    detail = (f"A* 展开超预算（>{DEFAULT_MAX_EXPANSIONS} 节点）"
                              f"，图太大，换条近路或重烘")
                elif sc != tc:
                    kind = "component_split"
                    detail = (f"分属不同连通分量（起点 #{sc}，目标 #{tc}），"
                              f"两块区域之间没有连起来的路")
                else:
                    kind = "oneway"
                    detail = (f"同在连通分量 #{sc}，但这条路是单向的"
                              f"（跳崖/单向通道），这个方向走不通")
                return {"ok": False,
                        "text": f"api_request_path: {nav.nodes[s]} → {nav.nodes[t]} "
                                f"不可达：{detail}",
                        "path": [],
                        "reason": kind,
                        "start_component": sc,
                        "goal_component": tc,
                        "start_node": list(nav.nodes[s]),
                        "goal_node": list(nav.nodes[t]),
                        "expansions": astat.get("expansions", 0)}
            self._stamp_heat(heat, path, now, requester)
            return {"ok": True, "text": f"{len(path)} 路径点",
                    "path": [list(nav.nodes[i]) for i in path]}
        except Exception as exc:
            return {"ok": False, "text": f"api_request_path: {exc}", "path": []}

    # -- 路径多样性（抖动 + 拥堵热度） --------------------------------

    @staticmethod
    def _base_step(nav: "_LoadedNav", a: int, b: int) -> float:
        ax, _, az = nav.nodes[a]
        bx, _, bz = nav.nodes[b]
        return _NAV_SQRT2 if (ax != bx and az != bz) else 1.0

    def _make_scale(self, nav: "_LoadedNav"):
        rng = random.Random()

        def scale(a: int, b: int) -> float:
            return self._base_step(nav, a, b) * (1.0 + rng.uniform(0.0, NAV_JITTER))
        return scale

    def _make_penalty(self, heat: Dict[int, tuple], now: float,
                      requester: str):
        def penalty(n: int) -> float:
            hit = heat.get(n)
            if hit is None:
                return 0.0
            t, who = hit
            if who == requester:
                return 0.0            # 自己的热度对自己不可见
            age = now - t
            if age >= NAV_HEAT_TTL:
                heat.pop(n, None)
                return 0.0
            return NAV_HEAT_PENALTY * (1.0 - age / NAV_HEAT_TTL)
        return penalty

    def _stamp_heat(self, heat: Dict[int, tuple],
                    path: List[int], now: float, requester: str) -> None:
        # 中途节点记热度：起点是自己站的、终点是目标，都不算"路过"
        for n in path[1:-1]:
            heat[n] = (now, requester)
        self._prune_heat(heat, now)

    def _prune_heat(self, heat: Dict[int, tuple], now: float) -> None:
        if len(heat) <= 4000:
            return
        stale = [k for k, (t, _w) in heat.items()
                 if now - t >= NAV_HEAT_TTL]
        for k in stale:
            heat.pop(k, None)

    def status(self, map_id: Optional[str] = None) -> Dict[str, Any]:
        """api_nav_status：烘焙状态与统计。"""
        try:
            ids = [map_id] if map_id else self.available_maps()
            maps_info = []
            for mid in ids:
                if mid in self._cache:
                    nav = self._cache[mid]
                    st = dict(nav.stats)
                    st.update({"map_id": mid, "state": "已烘焙",
                               "nodes": len(nav.nodes),
                               "components": nav.component_count,
                               "island_nodes": nav.island_nodes,
                               "island_pct": (round(100.0 * nav.island_nodes
                                                   / len(nav.nodes), 1)
                                              if nav.nodes else 0.0),
                               "top_components": nav.top_components})
                elif self._nav_dir.joinpath(f"{mid}.nav.json").exists():
                    st = {"map_id": mid, "state": "有缓存（未加载）"}
                elif self._blocks_path(mid) is not None:
                    st = {"map_id": mid, "state": "有地形未烘焙"}
                else:
                    continue
                maps_info.append(st)
            return {"ok": True, "text": f"{len(maps_info)} 张图",
                    "maps": maps_info}
        except Exception as exc:
            return {"ok": False, "text": f"api_nav_status: {exc}", "maps": []}

    # ------------------------------------------------------------------
    # 出生点连通性（地图验收用）
    # ------------------------------------------------------------------

    def spawn_check(self, map_id: str,
                    spawns: List[Tuple[str, float, float, float]]) -> Dict[str, Any]:
        """出生点两两双向可达检查。

        spawns: [(名字, x, y, z), ...]；y 含 .5 视为半砖脚位取上整。
        返回 {"ok", "text", "pairs", "oneway", "unreachable"}。
        """
        try:
            nav = self.ensure(map_id)
            resolved: Dict[str, Optional[int]] = {}
            lines = []
            for name, fx, fy, fz in spawns:
                n = self.snap(nav, (fx, fy, fz))
                resolved[name] = n
                if n is None:
                    lines.append(f"{name}: 附近无站立点")
                else:
                    lines.append(
                        f"{name} ({fx:.1f},{fy:.1f},{fz:.1f}) → {nav.nodes[n]}"
                        f" 出度{nav.out_degree(n)}")
            names = [n for n in resolved if resolved[n] is not None]
            matrix: Dict[Tuple[str, str], Optional[int]] = {}
            for a in names:
                for b in names:
                    if a == b:
                        continue
                    p = astar(nav, resolved[a], resolved[b])
                    matrix[(a, b)] = len(p) if p else None
            weak_ok = len({nav.component[resolved[n]] for n in names}) == 1 if names else False
            oneway = [[a, b, v] for (a, b), v in matrix.items()
                      if v is not None and matrix.get((b, a)) is None]
            unreachable = [[a, b] for (a, b), v in matrix.items() if v is None]
            ok = (not oneway and not unreachable
                  and len(names) == len(spawns) and weak_ok)
            summary = (f"{len(names)}/{len(spawns)} 命中站立点，"
                       f"{'全部双向可达' if ok else '存在问题'}")
            if oneway:
                summary += f"；单向 {len(oneway)} 对"
            if unreachable:
                summary += f"；不可达 {len(unreachable)} 对"
            return {"ok": ok, "text": summary, "detail": lines,
                    "matrix": {f"{a}->{b}": v for (a, b), v in matrix.items()},
                    "oneway": oneway, "unreachable": unreachable}
        except Exception as exc:
            return {"ok": False, "text": f"spawn_check: {exc}", "detail": [],
                    "matrix": {}, "oneway": [], "unreachable": []}


def _snap_near(nav: "_LoadedNav", bx: int, bz: int, foot: float,
               radius: int) -> Optional[int]:
    """bx/bz 附近 radius 格内找高度差最小、列最近的节点。"""
    best = None
    best_key = None
    for ddx in range(-radius, radius + 1):
        for ddz in range(-radius, radius + 1):
            d = max(abs(ddx), abs(ddz))
            idxs = nav.by_col.get((bx + ddx, bz + ddz))
            if not idxs:
                continue
            for i in idxs:
                # 高度差优先：同高度层里再挑最近的列
                key = (abs(nav.nodes[i][1] - foot), d)
                if best_key is None or key < best_key:
                    best_key = key
                    best = i
    return best
