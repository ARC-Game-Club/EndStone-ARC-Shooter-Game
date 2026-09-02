# -*- coding: utf-8 -*-
"""按 player_career 当前战绩回填单场/累计应得 XP（击杀×5 + 胜场加成 + MVP×10/场）。"""
from __future__ import annotations

import shutil
import sqlite3
import time
from pathlib import Path

DB = Path(
    r"C:\Users\81135\Documents\SERVO\MCBE\MCBEShooterGameServer\bedrock_server\plugins\ARCShooterGame\shooter.db"
)
XP_PER_KILL = 5
WIN_BONUS_PERCENT = 20
MVP_PER_MATCH = 10


def expected_xp(kills: int, wins: int, mvps: int) -> int:
    kill_xp = max(0, kills) * XP_PER_KILL
    # 无法还原逐场明细时：按胜场估算胜方加成（每场用该玩家总击杀/总场次近似）
    matches = max(1, wins) if wins > 0 else 0
    win_bonus = 0
    if wins > 0 and matches > 0:
        avg_kills = kills / max(1, wins + 0)  # wins only as proxy for rough estimate
        base = avg_kills * XP_PER_KILL
        win_bonus = int(base * WIN_BONUS_PERCENT / 100) * wins
    settlement_mvp = max(0, mvps) * MVP_PER_MATCH
    return kill_xp + win_bonus + settlement_mvp


def expected_xp_simple(row) -> int:
    """仅用于首次入库、场次很少的玩家：击杀 XP + 每场 MVP + 胜场加成。"""
    kills = int(row["kills"] or 0)
    wins = int(row["wins"] or 0)
    losses = int(row["losses"] or 0)
    draws = int(row["draws"] or 0)
    mvps = int(row["mvps"] or 0)
    matches = int(row["matches"] or 0)
    kill_xp = kills * XP_PER_KILL
    mvp_xp = mvps * MVP_PER_MATCH
    # 胜场加成：假设胜场平均击杀 = 总击杀/总场次（1v1 单场时精确）
    win_bonus = 0
    if wins > 0 and matches > 0:
        avg_k = kills / matches
        win_bonus = int(avg_k * XP_PER_KILL * WIN_BONUS_PERCENT / 100) * wins
    return kill_xp + mvp_xp + win_bonus


def main() -> None:
    backup = DB.with_suffix(f".db.bak-xp-{int(time.time())}")
    shutil.copy2(DB, backup)
    print(f"backup: {backup}")

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    targets = ["VLC Melody"]
    for name in targets:
        row = conn.execute("SELECT * FROM player_career WHERE name = ?", (name,)).fetchone()
        if row is None:
            print(f"missing: {name}")
            continue
        old = int(row["xp"] or 0)
        exp = expected_xp_simple(row)
        print(f"{name}: kills={row['kills']} wins={row['wins']} mvps={row['mvps']} matches={row['matches']}")
        print(f"  xp {old} -> {exp} (Lv{old//100} -> Lv{exp//100})")
        if exp != old:
            conn.execute(
                "UPDATE player_career SET xp = ?, updated_at = ? WHERE name = ?",
                (exp, time.time(), name),
            )
            print("  updated")
        else:
            print("  ok, no change")
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
