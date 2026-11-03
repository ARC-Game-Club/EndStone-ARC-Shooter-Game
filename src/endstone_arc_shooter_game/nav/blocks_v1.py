# -*- coding: utf-8 -*-
"""blocks-v1 地图数据读写。

格式与假人插件 4.1.6+ 的导出完全互通（它是这套格式的始作者，本包是
收编后的家）：

    columns: [{"x": -1028, "z": 972,
               "blocks": [{"y": 64, "name": "minecraft:stone", "states": {...}},
                          ...]}]

一列只列**非空气方块**；没列出的 y 就是空气。states（朝向等）读取端
（导航）现阶段用不到，加载时丢弃省内存；导出端仍会写入。
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

FORMAT = "blocks-v1"


@dataclass
class BlockMap:
    """整张图的非空气方块索引：{(x, z): {y: 方块短名}}。"""

    map_id: str
    display_name: str
    #: bounds 原样保留（含浮点，[x1,x2,y1,y2,z1,z2]）
    bounds: List[float]
    x_min: int
    x_max: int
    z_min: int
    z_max: int
    y_min: int
    y_max: int
    step: int
    total_columns: int
    unloaded_columns: int
    exported_at: str
    source_path: str
    #: (x, z) -> {y: name}
    columns: Dict[Tuple[int, int], Dict[int, str]] = field(default_factory=dict)

    # ------------------------------------------------------------------

    def block_at(self, x: int, y: int, z: int) -> Optional[str]:
        """这一格的方块短名；None = 空气（没记录就是空气）。"""
        col = self.columns.get((x, z))
        if not col:
            return None
        return col.get(y)

    def ys_at(self, x: int, z: int) -> List[int]:
        """这一列所有非空气方块的 y，升序。"""
        col = self.columns.get((x, z))
        return sorted(col) if col else []

    @property
    def coverage_pct(self) -> float:
        if not self.total_columns:
            return 0.0
        return 100.0 * (self.total_columns - self.unloaded_columns) / self.total_columns


def load_map(path: str | Path) -> BlockMap:
    """读一个 blocks-v1 JSON 成 BlockMap。"""
    p = Path(path)
    raw = json.loads(p.read_text(encoding="utf-8"))
    if raw.get("format") != FORMAT:
        raise ValueError(
            f"{p.name}: 期望 format={FORMAT}，拿到 {raw.get('format')!r}")
    b = [float(v) for v in raw["bounds"]]
    x1, x2, y1, y2, z1, z2 = b
    columns: Dict[Tuple[int, int], Dict[int, str]] = {}
    for col in raw["columns"]:
        key = (int(col["x"]), int(col["z"]))
        cells: Dict[int, str] = {}
        for blk in col.get("blocks", ()):
            name = blk.get("name") or ""
            if not name:
                continue
            cells[int(blk["y"])] = name.split(":", 1)[-1] if ":" in name else name
        if cells:
            columns[key] = cells
    return BlockMap(
        map_id=str(raw.get("map_id", p.stem)),
        display_name=str(raw.get("display_name", "")),
        bounds=b,
        x_min=int(min(x1, x2)), x_max=int(max(x1, x2)),
        z_min=int(min(z1, z2)), z_max=int(max(z1, z2)),
        y_min=int(min(y1, y2)), y_max=int(max(y1, y2)),
        step=int(raw.get("step", 1)),
        total_columns=int(raw.get("total_columns", 0)),
        unloaded_columns=int(raw.get("unloaded_columns", 0)),
        exported_at=str(raw.get("exported_at", "")),
        source_path=str(p),
        columns=columns,
    )


def write_map(path: str | Path, *, map_id: str, display_name: str,
              bounds: List[float], step: int,
              columns: List[Tuple[int, int, List[dict]]],
              total_columns: int, unloaded_columns: int) -> Path:
    """写一个 blocks-v1 JSON。

    columns: [(x, z, [{"y": 64, "name": "minecraft:stone", "states": {...}}, ...]), ...]
    states 为空时省略，与假人导出端一致。
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "map_id": map_id,
        "display_name": display_name,
        "bounds": bounds,
        "step": step,
        "block_size": 64,
        "format": FORMAT,
        "note": "columns[].blocks 只列非空气方块；未列出的方块即空气。"
                "每个方块含 y / name / states（朝向等状态属性，读不到则无此项）。",
        "exported_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "unloaded_columns": unloaded_columns,
        "unloaded_blocks": 0,
        "total_columns": total_columns,
        "block_count": sum(len(blocks) for _x, _z, blocks in columns),
        "columns": [
            {"x": x, "z": z, "blocks": [
                {k: v for k, v in blk.items() if v is not None}
                for blk in blocks]}
            for x, z, blocks in columns
        ],
    }
    tmp = p.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    tmp.replace(p)
    return p
