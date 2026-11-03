# -*- coding: utf-8 -*-
"""TickingAreaMapExporter——用 /tickingarea 加载区块的离线地图导出器。

为什么能完全自包含（不再依赖假人传送）：
    `/tickingarea add x1 y1 z1 x2 y2 z2 <name>` 造一块常加载区域，
    没人在线区块也加载着，`get_block_at` 就读得到。扫完一块
    `tickingarea remove <name>`，换下一块。

    （服主 2026-11-03："其实可以用命令来添加常加载区块的。"）

流程（每块走一遍状态机，由插件调度器每 tick 推进）：

    add  → 下 tickingarea 命令，等区块加载（探角点，超时 120 tick）
    scan → 自适应预算扫这一块的所有列（每 tick 花在扫描上 ≤ TARGET_TICK_MS）
    done → remove 这块的 tickingarea，进下一块；全完落盘 blocks-v1 + 回调

⚠️ 同图有对局进行中时拒绝启动（tickingarea 会强制跑区块逻辑、可能刷怪，
   且扫图要独占）。每块常加载区只存活几秒。
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from .blocks_v1 import write_map
from .taxonomy import is_air_space, is_liquid

#: 方块名判断"是空气"用的短名集合（与假人导出端一致）
_AIR_NAMES = ("air", "cave_air", "void_air", "")


def _short(name: Any) -> str:
    s = str(name or "")
    return s.split(":", 1)[1] if ":" in s else s


def _is_air(name: str) -> bool:
    return _short(name).lower() in _AIR_NAMES


def split_tiles(x1: int, x2: int, z1: int, z2: int,
                tile: int = 64) -> List[Dict[str, int]]:
    """把 region 切成 ≤tile×tile 的块（纯函数，单测用）。"""
    tiles: List[Dict[str, int]] = []
    x = x1
    while x <= x2:
        z = z1
        while z <= z2:
            tiles.append({"x1": x, "x2": min(x2, x + tile - 1),
                          "z1": z, "z2": min(z2, z + tile - 1)})
            z += tile
        x += tile
    return tiles


class TickingAreaMapExporter:
    """导出一张图。插件调度器每 tick 调 `tick()`，不要自己开线程。"""

    #: 每 tick 花在扫描上的毫秒预算（一 tick 50ms，留足余量）
    TARGET_TICK_MS = 25.0
    #: 等区块加载最多等多少 tick
    LOAD_TIMEOUT = 120
    #: 探点加载成功但边角未上时，最多再等多少 tick 就开扫
    PARTIAL_TIMEOUT = 40
    #: 探测角点加载的采样 y（region 顶/中/底各一）
    TILE = 64
    AREA_PREFIX = "arcgs_nav"

    def __init__(self, plugin: Any, nav_dir: Path,
                 on_done: Optional[Callable[[str, bool, str], None]] = None
                 ) -> None:
        self._plugin = plugin
        self._nav_dir = Path(nav_dir)
        self._maps_dir = self._nav_dir / "maps"
        self._on_done = on_done
        self._job: Optional[Dict[str, Any]] = None
        self._ms_per_read = 0.0

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> Optional[Dict[str, Any]]:
        job = self._job
        if not job:
            return None
        tiles = job["tiles"]
        ti = min(job["tile_cursor"], max(0, len(tiles) - 1))
        t = tiles[ti] if tiles else None
        cols = job["cols"]
        return {
            "map_id": job["map_id"],
            "phase": job["phase"],
            "tiles": len(tiles), "tile": ti + 1,
            "tile_range": (t["x1"], t["x2"], t["z1"], t["z2"]) if t else None,
            "cursor": job["cursor"], "cols": cols,
            "progress": job["cursor"] / cols if cols else 0.0,
            "unloaded": job["unloaded"],
            "done": job["done"],
        }

    def cancel(self, remove_area: bool = True) -> None:
        job = self._job
        if job and not job["done"] and remove_area:
            self._dispatch_remove(job.get("area_name") or "")
        self._job = None

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def start(self, map_id: str, display_name: str, dimension: Any,
              bounds: List[float], y_pad_below: int = 12,
              y_pad_above: int = 8) -> bool:
        """开始导出。bounds = [x1, x2, y1, y2, z1, z2]（region_bounds 归一序）。"""
        if self._job and not self._job["done"]:
            return False
        try:
            x1, x2, y1, y2, z1, z2 = [float(v) for v in bounds]
        except (TypeError, ValueError, IndexError):
            return False
        if not (x2 > x1 and z2 > z1) or dimension is None:
            return False
        y_lo = int(min(y1, y2)) - int(y_pad_below)
        y_hi = int(max(y1, y2)) + int(y_pad_above)
        y_lo = max(-64, y_lo)
        y_hi = min(319, y_hi)
        tiles = split_tiles(int(x1), int(x2), int(z1), int(z2), self.TILE)
        # tickingarea 名字只留安全字符（中文/特殊符号会被命令解析吃掉）
        safe = "".join(ch for ch in str(map_id) if ch.isascii() and ch.isalnum()) or "map"
        self._job = {
            "map_id": str(map_id), "display_name": str(display_name or map_id),
            "dimension": dimension,
            "bounds": [x1, x2, y1, y2, z1, z2],
            "y_lo": y_lo, "y_hi": y_hi,
            "tiles": tiles, "tile_cursor": 0, "tile_pos": 0,
            "phase": "add", "load_wait": 0,
            "cols": sum((t["x2"] - t["x1"] + 1) * (t["z2"] - t["z1"] + 1)
                        for t in tiles),
            "cursor": 0, "unloaded": 0,
            "columns": [],          # [(x, z, [block dicts])]
            "done": not tiles, "started": time.time(),
            "area_name": f"{self.AREA_PREFIX}_{safe[:24]}",
        }
        self._ms_per_read = 0.0
        self._plugin.logger.info(
            f"地图导出开始 {map_id}：{self._job['cols']} 列，"
            f"{len(tiles)} 块（每块 {self.TILE}×{self.TILE}），"
            f"y {y_lo}~{y_hi}（region ± padding），tickingarea 加载")
        return True

    # ------------------------------------------------------------------
    # 每 tick 推进
    # ------------------------------------------------------------------

    def tick(self) -> Optional[Dict[str, Any]]:
        job = self._job
        if not job:
            return None
        if job["done"]:
            return self.status()
        phase = job["phase"]
        if phase == "add":
            return self._phase_add(job)
        if phase == "load":
            return self._phase_load(job)
        if phase == "scan":
            return self._phase_scan(job)
        return self.status()

    # -- add：下 tickingarea 命令 ---------------------------------------

    def _phase_add(self, job: Dict[str, Any]) -> Dict[str, Any]:
        t = job["tiles"][job["tile_cursor"]]
        name = job["area_name"]
        # 区域 y 取 region 的一个薄层（tickingarea 只认 xz，y 给两端点即可）
        self._dispatch(
            f"tickingarea add {t['x1']} {job['y_lo']} {t['z1']} "
            f"{t['x2']} {job['y_lo']} {t['z2']} {name}")
        job["phase"] = "load"
        job["load_wait"] = 0
        return self.status()

    def _phase_load(self, job: Dict[str, Any]) -> Dict[str, Any]:
        t = job["tiles"][job["tile_cursor"]]
        dim = job["dimension"]
        job["load_wait"] += 1
        loaded, total = self._probe(dim, t, job["y_lo"], job["y_hi"])
        if loaded >= total or (loaded >= 1
                               and job["load_wait"] > self.PARTIAL_TIMEOUT) \
                or job["load_wait"] > self.LOAD_TIMEOUT:
            if loaded < total:
                self._plugin.logger.warning(
                    f"地图导出 {job['map_id']}：第 {job['tile_cursor'] + 1} 块"
                    f"加载 {loaded}/{total}，没加载的列单独计")
            job["phase"] = "scan"
            job["tile_pos"] = 0
            job["tile_cells"] = self._tile_cells(t)
            return self.status()
        return self.status()

    def _phase_scan(self, job: Dict[str, Any]) -> Dict[str, Any]:
        t = job["tiles"][job["tile_cursor"]]
        dim = job["dimension"]
        cells: List[Tuple[int, int]] = job["tile_cells"]
        y_lo, y_hi = job["y_lo"], job["y_hi"]
        y_height = y_hi - y_lo + 1
        budget = self._columns_per_tick(y_height)
        scanned = 0
        t0 = time.perf_counter()
        while job["tile_pos"] < len(cells) and scanned < budget:
            bx, bz = cells[job["tile_pos"]]
            job["tile_pos"] += 1
            scanned += 1
            blocks, unloaded = self._scan_column(dim, bx, bz, y_lo, y_hi)
            if unloaded:
                job["unloaded"] += 1
                job["cursor"] += 1
                continue
            job["cursor"] += 1
            if blocks:
                job["columns"].append((bx, bz, blocks))
        elapsed = (time.perf_counter() - t0) * 1000.0
        reads = scanned * y_height
        if reads > 0:
            inst = elapsed / reads
            self._ms_per_read = (inst if self._ms_per_read <= 0
                                 else self._ms_per_read * 0.7 + inst * 0.3)
        if job["tile_pos"] >= len(cells):
            self._dispatch_remove(job["area_name"])
            self._plugin.logger.info(
                f"地图导出 {job['map_id']}：第 {job['tile_cursor'] + 1}/"
                f"{len(job['tiles'])} 块扫完（累计 {len(job['columns'])} 列有方块，"
                f"未加载 {job['unloaded']}）")
            job["tile_cursor"] += 1
            job["tile_pos"] = 0
            if job["tile_cursor"] >= len(job["tiles"]):
                self._finish(job)
            else:
                job["phase"] = "add"
        return self.status()

    # ------------------------------------------------------------------
    # 收尾落盘
    # ------------------------------------------------------------------

    def _finish(self, job: Dict[str, Any]) -> None:
        job["done"] = True
        job["phase"] = "done"
        path = self._maps_dir / f"{job['map_id']}.json"
        try:
            write_map(path, map_id=job["map_id"],
                      display_name=job["display_name"],
                      bounds=job["bounds"], step=1,
                      columns=job["columns"],
                      total_columns=job["cols"],
                      unloaded_columns=job["unloaded"])
            job["path"] = str(path)
            cov = 100.0 * (job["cols"] - job["unloaded"]) / job["cols"] if job["cols"] else 0.0
            self._plugin.logger.info(
                f"地图导出完成 {job['map_id']}：{len(job['columns'])} 列有方块，"
                f"未加载 {job['unloaded']}/{job['cols']}（{cov:.0f}% 覆盖），"
                f"耗时 {time.time() - job['started']:.0f}s → {path}")
            if self._on_done:
                try:
                    self._on_done(job["map_id"], True, str(path))
                except Exception as exc:
                    self._plugin.logger.warning(f"地图导出回调失败: {exc}")
        except Exception as exc:
            self._plugin.logger.warning(f"地图导出写文件失败: {exc}")
            if self._on_done:
                try:
                    self._on_done(job["map_id"], False, str(exc))
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # 辅助
    # ------------------------------------------------------------------

    def _dispatch(self, cmd: str) -> None:
        try:
            self._plugin.server.dispatch_command(
                self._plugin.server.command_sender, cmd)
        except Exception as exc:
            self._plugin.logger.warning(f"tickingarea 命令失败 [{cmd}]: {exc}")

    def _dispatch_remove(self, name: str) -> None:
        if name:
            self._dispatch(f"tickingarea remove {name}")

    @staticmethod
    def _tile_cells(t: Dict[str, int]) -> List[Tuple[int, int]]:
        cells = []
        for x in range(t["x1"], t["x2"] + 1):
            for z in range(t["z1"], t["z2"] + 1):
                cells.append((x, z))
        return cells

    def _columns_per_tick(self, y_height: int) -> int:
        limit = 240
        if self._ms_per_read > 0:
            reads = max(1, int(self.TARGET_TICK_MS / self._ms_per_read))
            limit = max(4, reads // max(1, y_height))
        return max(1, limit)

    def _block_or_none(self, dim: Any, x: int, y: int, z: int):
        try:
            return dim.get_block_at(int(x), int(y), int(z))
        except Exception:
            return None

    def _probe(self, dim: Any, t: Dict[str, int],
               y_lo: int, y_hi: int) -> Tuple[int, int]:
        pts = [((t["x1"] + t["x2"]) // 2, (t["z1"] + t["z2"]) // 2),
               (t["x1"], t["z1"]), (t["x2"], t["z2"]),
               (t["x1"], t["z2"]), (t["x2"], t["z1"])]
        ys = [y_lo, (y_lo + y_hi) // 2, y_hi]
        loaded = 0
        for (x, z) in pts:
            for y in ys:
                b = self._block_or_none(dim, x, y, z)
                if b is not None:
                    loaded += 1
                    break
        return loaded, len(pts)

    def _scan_column(self, dim: Any, bx: int, bz: int,
                     y_lo: int, y_hi: int) -> Tuple[List[dict], bool]:
        """扫一列：返回 (方块列表, 是否因区块未加载而中断)。"""
        out: List[dict] = []
        for y in range(y_lo, y_hi + 1):
            block = self._block_or_none(dim, bx, y, bz)
            if block is None:
                return out, True
            try:
                name = str(block.type or "")
            except Exception:
                return out, True
            if not name or _is_air(name):
                continue
            item: Dict[str, Any] = {"y": y, "name": name}
            states = self._block_states(block)
            if states:
                item["states"] = states
            out.append(item)
        return out, False

    @staticmethod
    def _block_states(block: Any) -> Dict[str, Any]:
        """方块状态属性（朝向等），读不到返回空——与假人导出端同一取法。"""
        try:
            data = getattr(block, "data", None)
            if data is None:
                return {}
            states = getattr(data, "block_states", None)
            if not isinstance(states, dict) or not states:
                return {}
            return {str(k): v for k, v in states.items()}
        except Exception:
            return {}
