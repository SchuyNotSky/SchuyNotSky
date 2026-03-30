"""
Card classes: base Card and all subtypes.
Each card holds its data, current state, and a reference to its effect functions.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Set, TYPE_CHECKING
import uuid

from .mana import ManaCost, Color

if TYPE_CHECKING:
    from .game import GameState
    from .player import Player


class CardType(Enum):
    LAND = "Land"
    CREATURE = "Creature"
    ARTIFACT = "Artifact"
    ENCHANTMENT = "Enchantment"
    INSTANT = "Instant"
    SORCERY = "Sorcery"
    PLANESWALKER = "Planeswalker"
    TRIBAL = "Tribal"
    BATTLE = "Battle"


class Supertype(Enum):
    LEGENDARY = "Legendary"
    BASIC = "Basic"
    SNOW = "Snow"
    WORLD = "World"


class Zone(Enum):
    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
    STACK = "stack"
    COMMAND = "command_zone"
    LIMBO = "limbo"  # temporarily nowhere (e.g. being moved)


class Keyword(Enum):
    FLYING = auto()
    FIRST_STRIKE = auto()
    DOUBLE_STRIKE = auto()
    DEATHTOUCH = auto()
    LIFELINK = auto()
    TRAMPLE = auto()
    HASTE = auto()
    VIGILANCE = auto()
    REACH = auto()
    MENACE = auto()
    HEXPROOF = auto()
    INDESTRUCTIBLE = auto()
    SHROUD = auto()
    FLASH = auto()
    PROTECTION = auto()  # protection from color(s)
    CONVOKE = auto()
    CYCLING = auto()
    STORM = auto()
    CASCADE = auto()
    ANNIHILATOR = auto()
    INFECT = auto()
    WITHER = auto()
    PERSIST = auto()
    UNDYING = auto()
    PARTNER = auto()
    PARTNER_WITH = auto()
    BACKGROUND = auto()
    WARD = auto()


@dataclass
class CardData:
    """
    Immutable card definition — the 'oracle text' version.
    """
    name: str
    mana_cost: ManaCost
    card_types: List[CardType]
    supertypes: List[Supertype] = field(default_factory=list)
    subtypes: List[str] = field(default_factory=list)
    keywords: Set[Keyword] = field(default_factory=set)
    oracle_text: str = ""
    power: Optional[int] = None
    toughness: Optional[int] = None
    loyalty: Optional[int] = None
    color_indicator: Optional[Set[Color]] = None  # for cards without mana cost

    # Effect callbacks — set by the card database
    # Signature: (card_instance, game_state, player, **kwargs) -> None/result
    cast_effect: Optional[Callable] = field(default=None, repr=False)
    etb_effect: Optional[Callable] = field(default=None, repr=False)
    ltb_effect: Optional[Callable] = field(default=None, repr=False)
    activated_abilities: List[Dict] = field(default_factory=list)  # list of {cost, effect, name}
    triggered_abilities: List[Dict] = field(default_factory=list)  # list of {trigger, effect, name}
    static_abilities: List[Dict] = field(default_factory=list)

    # Tap abilities for lands / mana producers
    tap_mana: Optional[Dict[Color, int]] = None  # {Color: amount}
    tap_mana_choice: bool = False  # produces one of any color

    @property
    def cmc(self) -> int:
        return self.mana_cost.cmc

    @property
    def colors(self) -> Set[Color]:
        base = set(self.mana_cost.color_identity)
        if self.color_indicator:
            base |= self.color_indicator
        return base

    @property
    def is_permanent(self) -> bool:
        return any(t in self.card_types for t in [
            CardType.LAND, CardType.CREATURE, CardType.ARTIFACT,
            CardType.ENCHANTMENT, CardType.PLANESWALKER, CardType.BATTLE
        ])

    @property
    def is_spell(self) -> bool:
        return any(t in self.card_types for t in [
            CardType.INSTANT, CardType.SORCERY
        ])

    @property
    def is_legendary(self) -> bool:
        return Supertype.LEGENDARY in self.supertypes

    @property
    def is_commander_eligible(self) -> bool:
        return self.is_legendary and CardType.CREATURE in self.card_types

    def has_subtype(self, subtype: str) -> bool:
        return subtype.lower() in [s.lower() for s in self.subtypes]

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        return isinstance(other, CardData) and self.name == other.name

    def type_line(self) -> str:
        supers = " ".join(s.value for s in self.supertypes)
        types = " ".join(t.value for t in self.card_types)
        subs = " ".join(self.subtypes)
        line = f"{supers} {types}".strip()
        if subs:
            line += f" — {subs}"
        return line

    def __str__(self) -> str:
        lines = [f"=== {self.name} ==="]
        lines.append(f"  Cost: {self.mana_cost}  CMC: {self.cmc}")
        lines.append(f"  Type: {self.type_line()}")
        if self.oracle_text:
            lines.append(f"  Text: {self.oracle_text}")
        if self.power is not None:
            lines.append(f"  P/T: {self.power}/{self.toughness}")
        if self.loyalty is not None:
            lines.append(f"  Loyalty: {self.loyalty}")
        return "\n".join(lines)


class Card:
    """
    A card instance on the battlefield or in a zone.
    Holds mutable state: tapped, counters, damage, attachments, etc.
    """
    def __init__(self, data: CardData, owner_id: str):
        self.data = data
        self.owner_id = owner_id
        self.controller_id = owner_id
        self.instance_id = str(uuid.uuid4())[:8]
        self.zone = Zone.LIBRARY

        # State
        self.tapped = False
        self.summoning_sick = True   # creatures can't attack/tap until their controller's next turn
        self.damage_taken = 0
        self.counters: Dict[str, int] = {}  # "+1/+1", "-1/-1", "loyalty", etc.
        self.attachments: List[Card] = []   # auras/equipment attached TO this card
        self.attached_to: Optional[Card] = None  # this card is attached to...
        self.marked_for_death = False       # state-based action pending

        # Modifier overrides (from buffs/auras)
        self._power_mod = 0
        self._toughness_mod = 0
        self._added_keywords: Set[Keyword] = set()
        self._removed_keywords: Set[Keyword] = set()

        # For flip/transform/meld cards
        self.transformed = False
        self.face_up = True

        # Commander specific
        self.commander_tax_paid = 0  # times cast from command zone

    @property
    def name(self) -> str:
        return self.data.name

    @property
    def power(self) -> Optional[int]:
        if self.data.power is None:
            return None
        base = self.data.power
        base += self.counters.get("+1/+1", 0)
        base -= self.counters.get("-1/-1", 0)
        base += self._power_mod
        return max(0, base)

    @property
    def toughness(self) -> Optional[int]:
        if self.data.toughness is None:
            return None
        base = self.data.toughness
        base += self.counters.get("+1/+1", 0)
        base -= self.counters.get("-1/-1", 0)
        base += self._toughness_mod
        return max(0, base)

    @property
    def loyalty(self) -> Optional[int]:
        if self.data.loyalty is None:
            return None
        return self.data.loyalty + self.counters.get("loyalty", 0)

    @property
    def keywords(self) -> Set[Keyword]:
        return (self.data.keywords | self._added_keywords) - self._removed_keywords

    def has_keyword(self, kw: Keyword) -> bool:
        return kw in self.keywords

    def is_tapped(self) -> bool:
        return self.tapped

    def tap(self):
        self.tapped = True

    def untap(self):
        self.tapped = False

    def add_counter(self, counter_type: str, amount: int = 1):
        self.counters[counter_type] = self.counters.get(counter_type, 0) + amount
        # Remove +1/+1 and -1/-1 counters that cancel out
        if "+1/+1" in self.counters and "-1/-1" in self.counters:
            net = self.counters["+1/+1"] - self.counters["-1/-1"]
            if net >= 0:
                self.counters["+1/+1"] = net
                del self.counters["-1/-1"]
            else:
                self.counters["-1/-1"] = -net
                del self.counters["+1/+1"]

    def remove_counter(self, counter_type: str, amount: int = 1) -> bool:
        have = self.counters.get(counter_type, 0)
        if have < amount:
            return False
        self.counters[counter_type] = have - amount
        if self.counters[counter_type] == 0:
            del self.counters[counter_type]
        return True

    def can_attack(self) -> bool:
        if CardType.CREATURE not in self.data.card_types:
            return False
        if self.tapped:
            return False
        if self.summoning_sick and not self.has_keyword(Keyword.HASTE):
            return False
        return True

    def can_block(self) -> bool:
        if CardType.CREATURE not in self.data.card_types:
            return False
        if self.tapped:
            return False
        return True

    def can_tap_for_mana(self) -> bool:
        if self.tapped:
            return False
        if CardType.CREATURE in self.data.card_types and self.summoning_sick:
            # Creatures with summoning sickness can't use tap abilities UNLESS
            # the tap is part of a mana ability with {T} in cost.
            # For simplicity we allow land-like mana taps on non-creatures only.
            return False
        return True

    def reset_for_turn(self):
        """Called at start of player's turn to reset summoning sickness."""
        self.summoning_sick = False

    def __repr__(self) -> str:
        zone_str = self.zone.value if self.zone else "?"
        tap_str = "(T)" if self.tapped else ""
        return f"Card({self.name}{tap_str} [{zone_str}])"

    def short_str(self) -> str:
        parts = [self.name]
        if CardType.CREATURE in self.data.card_types:
            parts.append(f"{self.power}/{self.toughness}")
        if self.tapped:
            parts.append("[T]")
        if self.counters:
            parts.append(str(self.counters))
        return " ".join(parts)
