# -*- coding: utf-8 -*-
"""武器获取策略：商店（含差价升级/降级退差价）、预设、随机、武器大师等。

纯逻辑，不依赖 Endstone。插件只负责把结果落到背包 / UI。
"""
from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple

from endstone_arc_shooter_game.session import PlayerState, first_empty_or_first

# 模式配置里的 weapon_acquire 取值
ACQUIRE_SHOP = "shop"
ACQUIRE_ARMORY = "armory"
ACQUIRE_PRESET = "preset"
ACQUIRE_RANDOM = "random"
ACQUIRE_WEAPON_MASTER = "weapon_master"

KNOWN_ACQUIRE_MODES = (
    ACQUIRE_SHOP,
    ACQUIRE_ARMORY,
    ACQUIRE_PRESET,
    ACQUIRE_RANDOM,
    ACQUIRE_WEAPON_MASTER,
)

REASON_OK = "ok"
REASON_UNKNOWN = "unknown"
REASON_ALREADY_OWNED = "already_owned"
REASON_NO_SLOT = "no_slot"
REASON_INSUFFICIENT = "insufficient_points"
REASON_DISABLED = "shop_disabled"


@dataclass(frozen=True)
class SlotCapacities:
    primary: int = 1
    secondary: int = 1
    melee: int = 1
    gadget: int = 2
    armor: int = 1

    @classmethod
    def from_layout(cls, layout: Dict[str, Any]) -> "SlotCapacities":
        def span(key: str, default: int) -> int:
            pair = layout.get(key)
            if isinstance(pair, (tuple, list)) and len(pair) == 2:
                return max(0, int(pair[1]) - int(pair[0]))
            return default

        return cls(
            primary=span("primary", 1),
            secondary=span("secondary", 1),
            melee=span("melee", 1),
            gadget=span("gadget", 2),
            armor=1,
        )

    def for_type(self, wtype: str) -> int:
        return int(getattr(self, wtype, 0) or 0)


@dataclass(frozen=True)
class ShopQuote:
    weapon_id: str
    weapon_type: str
    full_cost: int
    pay: int
    credit: int
    trade_in_id: Optional[str]
    already_owned: bool
    no_slot: bool

    @property
    def is_trade(self) -> bool:
        return self.credit > 0 and not self.already_owned and not self.no_slot

    @property
    def is_upgrade(self) -> bool:
        return self.is_trade and self.pay > 0

    @property
    def is_downgrade(self) -> bool:
        return self.is_trade and self.pay < 0


@dataclass
class ShopPurchaseOutcome:
    ok: bool
    reason: str
    pay: int = 0
    credit: int = 0
    slot_index: int = 0
    old_id: Optional[str] = None
    weapon: Optional[Dict[str, Any]] = None
    points_left: int = 0


@dataclass
class OwnedEntry:
    weapon_id: str
    weapon_type: str
    slot_index: int = 0


def clear_owned_loadout(ps: PlayerState) -> None:
    ps.primary_id = None
    ps.secondary_id = None
    ps.melee_id = None
    ps.armor_id = None
    ps.gadgets = []


def owned_weapon_ids(ps: PlayerState) -> Set[str]:
    return set(filter(None, [ps.primary_id, ps.secondary_id, ps.melee_id, ps.armor_id, *ps.gadgets]))


def iter_owned_entries(ps: PlayerState) -> List[OwnedEntry]:
    rows: List[OwnedEntry] = []
    if ps.primary_id:
        rows.append(OwnedEntry(ps.primary_id, "primary", 0))
    if ps.secondary_id:
        rows.append(OwnedEntry(ps.secondary_id, "secondary", 0))
    if ps.melee_id:
        rows.append(OwnedEntry(ps.melee_id, "melee", 0))
    if ps.armor_id:
        rows.append(OwnedEntry(ps.armor_id, "armor", 0))
    for idx, gid in enumerate(ps.gadgets):
        if gid:
            rows.append(OwnedEntry(gid, "gadget", idx))
    return rows


def capacity_for_type(capacities: SlotCapacities, wtype: str) -> int:
    return capacities.for_type(wtype)


def trade_in_weapon_id(ps: PlayerState, wtype: str, capacity: int) -> Optional[str]:
    """本次购买会顶替的已有装备；空槽则无抵扣。"""
    if wtype == "primary":
        return ps.primary_id
    if wtype == "secondary":
        return ps.secondary_id
    if wtype == "melee":
        return ps.melee_id
    if wtype == "armor":
        return ps.armor_id
    if wtype == "gadget":
        if capacity <= 0:
            return None
        idx = first_empty_or_first(ps.gadgets, capacity)
        if idx < len(ps.gadgets):
            return ps.gadgets[idx]
        return None
    return None


def purchase_pay_amount(
    weapon: Dict[str, Any],
    trade_in_id: Optional[str],
    weapons: Dict[str, Dict[str, Any]],
    *,
    wtype: str = "",
    default_weapons: Optional[Dict[str, str]] = None,
) -> Tuple[int, int]:
    """返回 (实付, 抵扣)。实付可为负，表示降级退差价。默认武器抵扣为 0。"""
    cost = max(0, int(weapon.get("cost") or 0))
    if not trade_in_id or trade_in_id == weapon.get("id"):
        return cost, 0
    defaults = default_weapons or {}
    default_id = str(defaults.get(wtype) or "").strip()
    if default_id and trade_in_id == default_id:
        return cost, 0
    old = weapons.get(trade_in_id)
    if not old:
        return cost, 0
    credit = max(0, int(old.get("cost") or 0))
    return cost - credit, credit


def record_owned(
    ps: PlayerState,
    weapon: Dict[str, Any],
    capacity: int,
) -> Tuple[int, Optional[str]]:
    """写入玩家持有记录，返回 (槽位下标, 被替换的旧 id)。"""
    wtype = str(weapon.get("type") or "")
    wid = str(weapon.get("id") or "")
    if wtype == "primary":
        old = ps.primary_id
        ps.primary_id = wid
        return 0, old
    if wtype == "secondary":
        old = ps.secondary_id
        ps.secondary_id = wid
        return 0, old
    if wtype == "melee":
        old = ps.melee_id
        ps.melee_id = wid
        return 0, old
    if wtype == "armor":
        old = ps.armor_id
        ps.armor_id = wid
        return 0, old
    if wtype == "gadget":
        if len(ps.gadgets) < capacity:
            ps.gadgets.extend([None] * (capacity - len(ps.gadgets)))
        idx = first_empty_or_first(ps.gadgets, capacity)
        old = ps.gadgets[idx] if idx < len(ps.gadgets) else None
        if idx >= len(ps.gadgets):
            ps.gadgets.append(wid)
        else:
            ps.gadgets[idx] = wid
        return idx, old
    return 0, None


def quote_shop_purchase(
    ps: PlayerState,
    weapon: Dict[str, Any],
    weapons: Dict[str, Dict[str, Any]],
    capacities: SlotCapacities,
    *,
    default_weapons: Optional[Dict[str, str]] = None,
) -> ShopQuote:
    wtype = str(weapon.get("type") or "")
    wid = str(weapon.get("id") or "")
    capacity = capacity_for_type(capacities, wtype)
    full_cost = max(0, int(weapon.get("cost") or 0))
    if capacity <= 0:
        return ShopQuote(
            weapon_id=wid,
            weapon_type=wtype,
            full_cost=full_cost,
            pay=full_cost,
            credit=0,
            trade_in_id=None,
            already_owned=False,
            no_slot=True,
        )
    trade_in = trade_in_weapon_id(ps, wtype, capacity)
    already = trade_in == wid
    pay, credit = (full_cost, 0) if already else purchase_pay_amount(
        weapon,
        trade_in,
        weapons,
        wtype=wtype,
        default_weapons=default_weapons,
    )
    return ShopQuote(
        weapon_id=wid,
        weapon_type=wtype,
        full_cost=full_cost,
        pay=pay,
        credit=credit,
        trade_in_id=trade_in,
        already_owned=already,
        no_slot=False,
    )


def apply_shop_purchase(
    ps: PlayerState,
    weapon: Dict[str, Any],
    weapons: Dict[str, Dict[str, Any]],
    capacities: SlotCapacities,
    *,
    default_weapons: Optional[Dict[str, str]] = None,
) -> ShopPurchaseOutcome:
    wid = str(weapon.get("id") or "")
    if wid not in weapons and weapon.get("id"):
        # 允许传入已规范化的 weapon 字典
        pass
    if not wid:
        return ShopPurchaseOutcome(ok=False, reason=REASON_UNKNOWN, points_left=ps.points)

    quote = quote_shop_purchase(
        ps,
        weapon,
        weapons,
        capacities,
        default_weapons=default_weapons,
    )
    if quote.no_slot:
        return ShopPurchaseOutcome(ok=False, reason=REASON_NO_SLOT, weapon=weapon, points_left=ps.points)
    if quote.already_owned:
        return ShopPurchaseOutcome(
            ok=False,
            reason=REASON_ALREADY_OWNED,
            weapon=weapon,
            points_left=ps.points,
            credit=0,
            pay=0,
            old_id=quote.trade_in_id,
        )
    if quote.pay > 0 and ps.points < quote.pay:
        return ShopPurchaseOutcome(
            ok=False,
            reason=REASON_INSUFFICIENT,
            pay=quote.pay,
            credit=quote.credit,
            weapon=weapon,
            points_left=ps.points,
        )

    capacity = capacity_for_type(capacities, quote.weapon_type)
    idx, old_id = record_owned(ps, weapon, capacity)
    ps.points -= quote.pay
    return ShopPurchaseOutcome(
        ok=True,
        reason=REASON_OK,
        pay=quote.pay,
        credit=quote.credit,
        slot_index=idx,
        old_id=old_id,
        weapon=weapon,
        points_left=ps.points,
    )


def assign_default_loadout(
    ps: PlayerState,
    weapons: Dict[str, Dict[str, Any]],
    defaults: Optional[Dict[str, str]] = None,
) -> None:
    """按配置发放免费默认武器（不扣点数）。"""
    cfg = defaults or {}
    for wtype, slot_attr in (
        ("primary", "primary_id"),
        ("secondary", "secondary_id"),
        ("melee", "melee_id"),
        ("armor", "armor_id"),
    ):
        wid = str(cfg.get(wtype) or "").strip()
        if wid and wid in weapons and str(weapons[wid].get("type") or "") == wtype:
            setattr(ps, slot_attr, wid)
    gadget_default = str(cfg.get("gadget") or "").strip()
    if gadget_default and gadget_default in weapons and weapons[gadget_default].get("type") == "gadget":
        ps.gadgets = [gadget_default]


def assign_preset_loadout(
    ps: PlayerState,
    weapons: Dict[str, Dict[str, Any]],
    preset: Dict[str, Any],
) -> None:
    """按预设写入持有记录（不扣点数）。"""
    clear_owned_loadout(ps)
    primary = str(preset.get("primary") or "").strip()
    secondary = str(preset.get("secondary") or "").strip()
    melee = str(preset.get("melee") or "").strip()
    armor = str(preset.get("armor") or "").strip()
    if primary and primary in weapons:
        ps.primary_id = primary
    if secondary and secondary in weapons:
        ps.secondary_id = secondary
    if melee and melee in weapons:
        ps.melee_id = melee
    if armor and armor in weapons:
        ps.armor_id = armor
    gadgets = preset.get("gadgets") or []
    if isinstance(gadgets, str):
        gadgets = [gadgets]
    out: List[Optional[str]] = []
    for gid in gadgets:
        gid_s = str(gid or "").strip()
        if gid_s and gid_s in weapons:
            out.append(gid_s)
    ps.gadgets = out


def assign_random_loadout(
    ps: PlayerState,
    weapons: Dict[str, Dict[str, Any]],
    *,
    rng: Optional[random.Random] = None,
    include_armor: bool = True,
    gadget_count: int = 0,
) -> None:
    """随机主/副武器（及可选护甲、道具）。"""
    rng = rng or random.Random()
    clear_owned_loadout(ps)

    def pick(wtype: str) -> Optional[str]:
        pool = [w["id"] for w in weapons.values() if w.get("type") == wtype]
        return rng.choice(pool) if pool else None

    ps.primary_id = pick("primary")
    ps.secondary_id = pick("secondary")
    if include_armor:
        ps.armor_id = pick("armor")
    count = max(0, int(gadget_count))
    pool = [w["id"] for w in weapons.values() if w.get("type") == "gadget"]
    if count and pool:
        ps.gadgets = [rng.choice(pool) for _ in range(count)]


class WeaponAcquireStrategy(ABC):
    """模式级武器获取策略。"""

    key: str = ""

    @property
    @abstractmethod
    def uses_shop(self) -> bool:
        ...

    @property
    @abstractmethod
    def uses_buy_phase(self) -> bool:
        ...

    def clear_for_match_start(self, ps: PlayerState) -> None:
        clear_owned_loadout(ps)

    def assign_on_match_start(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        defaults: Optional[Dict[str, str]] = None,
        saved_loadout: Any = None,
        player_level: int = 0,
        gadget_slots: int = 2,
    ) -> None:
        """开局发放（预设/随机/军械库等）。"""
        return

    def assign_on_respawn(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        defaults: Optional[Dict[str, str]] = None,
        saved_loadout: Any = None,
        player_level: int = 0,
        gadget_slots: int = 2,
    ) -> None:
        """重生时是否重抽装备。默认保留已有持有记录。"""
        return

    def quote(
        self,
        ps: PlayerState,
        weapon: Dict[str, Any],
        weapons: Dict[str, Dict[str, Any]],
        capacities: SlotCapacities,
        *,
        default_weapons: Optional[Dict[str, str]] = None,
    ) -> ShopQuote:
        raise NotImplementedError

    def purchase(
        self,
        ps: PlayerState,
        weapon: Dict[str, Any],
        weapons: Dict[str, Dict[str, Any]],
        capacities: SlotCapacities,
        *,
        default_weapons: Optional[Dict[str, str]] = None,
    ) -> ShopPurchaseOutcome:
        return ShopPurchaseOutcome(
            ok=False,
            reason=REASON_DISABLED,
            points_left=ps.points,
            weapon=weapon,
        )


class ShopAcquireStrategy(WeaponAcquireStrategy):
    """点数商店：同栏位升级补差价、降级退差价，重生按持有记录补发。"""

    key = ACQUIRE_SHOP

    @property
    def uses_shop(self) -> bool:
        return True

    @property
    def uses_buy_phase(self) -> bool:
        return True

    def assign_on_match_start(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        defaults: Optional[Dict[str, str]] = None,
        saved_loadout: Any = None,
        player_level: int = 0,
        gadget_slots: int = 2,
    ) -> None:
        assign_default_loadout(ps, weapons, defaults)

    def quote(
        self,
        ps: PlayerState,
        weapon: Dict[str, Any],
        weapons: Dict[str, Dict[str, Any]],
        capacities: SlotCapacities,
        *,
        default_weapons: Optional[Dict[str, str]] = None,
    ) -> ShopQuote:
        return quote_shop_purchase(
            ps,
            weapon,
            weapons,
            capacities,
            default_weapons=default_weapons,
        )

    def purchase(
        self,
        ps: PlayerState,
        weapon: Dict[str, Any],
        weapons: Dict[str, Dict[str, Any]],
        capacities: SlotCapacities,
        *,
        default_weapons: Optional[Dict[str, str]] = None,
    ) -> ShopPurchaseOutcome:
        return apply_shop_purchase(
            ps,
            weapon,
            weapons,
            capacities,
            default_weapons=default_weapons,
        )


class ArmoryAcquireStrategy(WeaponAcquireStrategy):
    """军械库：赛外/开局配置窗换装；无商店，但开局仍有购买/配置阶段（冻结+无敌）。"""

    key = ACQUIRE_ARMORY

    @property
    def uses_shop(self) -> bool:
        return False

    @property
    def uses_buy_phase(self) -> bool:
        return True

    def assign_on_match_start(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        defaults: Optional[Dict[str, str]] = None,
        saved_loadout: Any = None,
        player_level: int = 0,
        gadget_slots: int = 2,
    ) -> None:
        from endstone_arc_shooter_game.loadout_store import (
            SavedLoadout,
            apply_saved_loadout_to_player,
            sanitize_loadout,
        )

        defaults = defaults or {}
        if saved_loadout is None:
            saved_loadout = SavedLoadout(name=ps.name)
        cleaned = sanitize_loadout(
            saved_loadout,
            weapons,
            defaults,
            int(player_level),
            gadget_slots=int(gadget_slots),
        )
        apply_saved_loadout_to_player(ps, cleaned)


class PresetAcquireStrategy(WeaponAcquireStrategy):
    """开局发固定预设；无商店、无购买阶段。"""

    key = ACQUIRE_PRESET

    @property
    def uses_shop(self) -> bool:
        return False

    @property
    def uses_buy_phase(self) -> bool:
        return False

    def assign_on_match_start(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        **_kwargs: Any,
    ) -> None:
        preset = (mode_cfg or {}).get("preset_loadout") or {}
        if not isinstance(preset, dict):
            preset = {}
        assign_preset_loadout(ps, weapons, preset)


class RandomAcquireStrategy(WeaponAcquireStrategy):
    """开局（及可选重生）随机武器；无商店。"""

    key = ACQUIRE_RANDOM

    def __init__(self, *, reroll_on_respawn: bool = True):
        self.reroll_on_respawn = bool(reroll_on_respawn)

    @property
    def uses_shop(self) -> bool:
        return False

    @property
    def uses_buy_phase(self) -> bool:
        return False

    def _roll(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]],
        rng: Optional[random.Random],
    ) -> None:
        cfg = mode_cfg or {}
        gadget_count = int(cfg.get("random_gadget_count") or 0)
        include_armor = bool(cfg.get("random_include_armor", True))
        assign_random_loadout(
            ps,
            weapons,
            rng=rng,
            include_armor=include_armor,
            gadget_count=gadget_count,
        )

    def assign_on_match_start(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        **_kwargs: Any,
    ) -> None:
        self._roll(ps, weapons, mode_cfg, rng)

    def assign_on_respawn(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        **_kwargs: Any,
    ) -> None:
        if self.reroll_on_respawn:
            self._roll(ps, weapons, mode_cfg, rng)


class WeaponMasterAcquireStrategy(WeaponAcquireStrategy):
    """武器大师：后续按击杀推进武器列表；当前为占位实现。"""

    key = ACQUIRE_WEAPON_MASTER

    @property
    def uses_shop(self) -> bool:
        return False

    @property
    def uses_buy_phase(self) -> bool:
        return False

    def assign_on_match_start(
        self,
        ps: PlayerState,
        weapons: Dict[str, Dict[str, Any]],
        mode_cfg: Optional[Dict[str, Any]] = None,
        *,
        rng: Optional[random.Random] = None,
        **_kwargs: Any,
    ) -> None:
        # 占位：先发列表第一把主武器（若配置了 master_weapon_ids）
        clear_owned_loadout(ps)
        ids = (mode_cfg or {}).get("master_weapon_ids") or []
        if isinstance(ids, str):
            ids = [ids]
        for wid in ids:
            wid_s = str(wid or "").strip()
            w = weapons.get(wid_s)
            if w and w.get("type") == "primary":
                ps.primary_id = wid_s
                break


_STRATEGY_CACHE: Dict[str, WeaponAcquireStrategy] = {
    ACQUIRE_SHOP: ShopAcquireStrategy(),
    ACQUIRE_ARMORY: ArmoryAcquireStrategy(),
    ACQUIRE_PRESET: PresetAcquireStrategy(),
    ACQUIRE_RANDOM: RandomAcquireStrategy(),
    ACQUIRE_WEAPON_MASTER: WeaponMasterAcquireStrategy(),
}


def normalize_acquire_key(raw: Any) -> str:
    key = str(raw or ACQUIRE_ARMORY).strip().lower()
    if key not in KNOWN_ACQUIRE_MODES:
        return ACQUIRE_ARMORY
    return key


def resolve_acquire_strategy(
    mode_cfg: Optional[Dict[str, Any]] = None,
    *,
    key: Optional[str] = None,
) -> WeaponAcquireStrategy:
    if key is None:
        key = (mode_cfg or {}).get("weapon_acquire")
    resolved = normalize_acquire_key(key)
    return _STRATEGY_CACHE[resolved]
