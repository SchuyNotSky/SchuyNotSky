"""
Zone management: Library, Hand, Battlefield, Graveyard, Exile, Stack, Command Zone.
"""
from __future__ import annotations
import random
from typing import Callable, Dict, Iterator, List, Optional, TYPE_CHECKING

from .card import Card, CardType, Zone as ZoneEnum, Keyword

if TYPE_CHECKING:
    from .game import GameState


class ZoneBase:
    def __init__(self, zone_type: ZoneEnum, owner_id: Optional[str] = None):
        self.zone_type = zone_type
        self.owner_id = owner_id
        self._cards: List[Card] = []

    def add(self, card: Card, position: str = "top"):
        """Add card to zone. position: 'top' | 'bottom' | 'random'."""
        card.zone = self.zone_type
        if position == "bottom":
            self._cards.append(card)
        elif position == "random":
            idx = random.randint(0, len(self._cards))
            self._cards.insert(idx, card)
        else:  # top
            self._cards.insert(0, card)

    def remove(self, card: Card) -> bool:
        if card in self._cards:
            self._cards.remove(card)
            card.zone = ZoneEnum.LIMBO
            return True
        return False

    def contains(self, card: Card) -> bool:
        return card in self._cards

    def find_by_name(self, name: str) -> Optional[Card]:
        for c in self._cards:
            if c.name.lower() == name.lower():
                return c
        return None

    def find_all_by_name(self, name: str) -> List[Card]:
        return [c for c in self._cards if c.name.lower() == name.lower()]

    def find_by_id(self, instance_id: str) -> Optional[Card]:
        for c in self._cards:
            if c.instance_id == instance_id:
                return c
        return None

    def cards(self) -> List[Card]:
        return list(self._cards)

    def __len__(self) -> int:
        return len(self._cards)

    def __iter__(self) -> Iterator[Card]:
        return iter(self._cards)

    def __repr__(self) -> str:
        return f"{self.zone_type.value}({len(self._cards)} cards)"


class Library(ZoneBase):
    def __init__(self, owner_id: str):
        super().__init__(ZoneEnum.LIBRARY, owner_id)

    def shuffle(self):
        random.shuffle(self._cards)

    def draw(self) -> Optional[Card]:
        """Draw from top of library. Returns None if empty (player loses)."""
        if not self._cards:
            return None
        card = self._cards.pop(0)
        card.zone = ZoneEnum.LIMBO
        return card

    def peek_top(self, n: int = 1) -> List[Card]:
        return self._cards[:n]

    def mill(self, n: int) -> List[Card]:
        """Put n cards from top into graveyard-bound limbo. Returns milled cards."""
        milled = []
        for _ in range(n):
            if not self._cards:
                break
            card = self._cards.pop(0)
            card.zone = ZoneEnum.LIMBO
            milled.append(card)
        return milled

    def exile_all(self) -> List[Card]:
        """Remove all cards (for Demonic Consultation / Tainted Pact effects)."""
        cards = list(self._cards)
        self._cards.clear()
        for c in cards:
            c.zone = ZoneEnum.LIMBO
        return cards

    def count_by_type(self, card_type: CardType) -> int:
        return sum(1 for c in self._cards if card_type in c.data.card_types)


class Hand(ZoneBase):
    def __init__(self, owner_id: str):
        super().__init__(ZoneEnum.HAND, owner_id)

    def add(self, card: Card, position: str = "top"):
        card.zone = ZoneEnum.HAND
        self._cards.append(card)  # order doesn't matter in hand

    def discard_random(self) -> Optional[Card]:
        if not self._cards:
            return None
        card = random.choice(self._cards)
        self._cards.remove(card)
        card.zone = ZoneEnum.LIMBO
        return card

    def discard_to_size(self, max_size: int) -> List[Card]:
        """Return list of cards that should be discarded (caller handles)."""
        excess = max(0, len(self._cards) - max_size)
        # For AI: discard lowest value. For now just return excess list.
        return self._cards[-excess:] if excess else []


class Battlefield(ZoneBase):
    def __init__(self, owner_id: Optional[str] = None):
        """owner_id=None for shared battlefield (typical)."""
        super().__init__(ZoneEnum.BATTLEFIELD, owner_id)

    def permanents_controlled_by(self, controller_id: str) -> List[Card]:
        return [c for c in self._cards if c.controller_id == controller_id]

    def creatures_controlled_by(self, controller_id: str) -> List[Card]:
        return [c for c in self._cards if c.controller_id == controller_id
                and CardType.CREATURE in c.data.card_types]

    def lands_controlled_by(self, controller_id: str) -> List[Card]:
        return [c for c in self._cards if c.controller_id == controller_id
                and CardType.LAND in c.data.card_types]

    def artifacts_controlled_by(self, controller_id: str) -> List[Card]:
        return [c for c in self._cards if c.controller_id == controller_id
                and CardType.ARTIFACT in c.data.card_types]

    def enchantments_controlled_by(self, controller_id: str) -> List[Card]:
        return [c for c in self._cards if c.controller_id == controller_id
                and CardType.ENCHANTMENT in c.data.card_types]

    def untapped_mana_sources(self, controller_id: str) -> List[Card]:
        """All untapped permanents that can produce mana."""
        result = []
        for c in self._cards:
            if c.controller_id != controller_id:
                continue
            if c.tapped:
                continue
            if c.data.tap_mana or c.data.tap_mana_choice:
                if CardType.CREATURE in c.data.card_types and c.summoning_sick:
                    continue  # summoning sick creatures can't tap
                result.append(c)
        return result

    def find_by_name(self, name: str, controller_id: Optional[str] = None) -> Optional[Card]:
        for c in self._cards:
            if c.name.lower() == name.lower():
                if controller_id is None or c.controller_id == controller_id:
                    return c
        return None

    def untap_all(self, controller_id: str):
        for c in self._cards:
            if c.controller_id == controller_id:
                c.untap()

    def untap_all_creatures(self, controller_id: str):
        for c in self._cards:
            if c.controller_id == controller_id and CardType.CREATURE in c.data.card_types:
                c.untap()

    def max_mana_available(self, controller_id: str) -> int:
        """Estimate total mana available from untapped sources."""
        total = 0
        for c in self.untapped_mana_sources(controller_id):
            if c.data.tap_mana:
                total += sum(c.data.tap_mana.values())
            elif c.data.tap_mana_choice:
                total += 1
        return total


class Graveyard(ZoneBase):
    def __init__(self, owner_id: str):
        super().__init__(ZoneEnum.GRAVEYARD, owner_id)

    def add(self, card: Card, position: str = "top"):
        card.zone = ZoneEnum.GRAVEYARD
        self._cards.insert(0, card)  # GY is ordered, newest on top

    def top(self) -> Optional[Card]:
        return self._cards[0] if self._cards else None

    def cards_of_type(self, card_type: CardType) -> List[Card]:
        return [c for c in self._cards if card_type in c.data.card_types]


class Exile(ZoneBase):
    def __init__(self, owner_id: Optional[str] = None):
        super().__init__(ZoneEnum.EXILE, owner_id)

    def add(self, card: Card, position: str = "top"):
        card.zone = ZoneEnum.EXILE
        self._cards.append(card)


class CommandZone(ZoneBase):
    def __init__(self):
        super().__init__(ZoneEnum.COMMAND)

    def add(self, card: Card, position: str = "top"):
        card.zone = ZoneEnum.COMMAND
        self._cards.append(card)

    def commanders_for(self, owner_id: str) -> List[Card]:
        return [c for c in self._cards if c.owner_id == owner_id]


class Stack(ZoneBase):
    """
    The stack: spells and abilities are added here and resolve LIFO.
    Each item is a StackItem (not just a Card).
    """
    def __init__(self):
        super().__init__(ZoneEnum.STACK)
        self._items: List[StackItem] = []

    def push(self, item: "StackItem"):
        self._items.append(item)
        if item.source:
            item.source.zone = ZoneEnum.STACK

    def pop(self) -> Optional["StackItem"]:
        if not self._items:
            return None
        return self._items.pop()

    def peek(self) -> Optional["StackItem"]:
        return self._items[-1] if self._items else None

    def is_empty(self) -> bool:
        return len(self._items) == 0

    def size(self) -> int:
        return len(self._items)

    def items(self) -> List["StackItem"]:
        return list(reversed(self._items))  # top first

    def __len__(self) -> int:
        return len(self._items)

    def __repr__(self) -> str:
        return f"Stack({len(self._items)} items)"


class StackItem:
    """
    Represents a spell or ability on the stack.
    """
    def __init__(
        self,
        source: Optional[Card],
        controller_id: str,
        effect: Callable,
        name: str,
        targets: Optional[List] = None,
        x_value: int = 0,
        is_ability: bool = False,
        is_mana_ability: bool = False,
        has_split_second: bool = False,
        copies: int = 1,  # for Storm
    ):
        self.source = source
        self.controller_id = controller_id
        self.effect = effect       # callable(game_state) -> None
        self.name = name
        self.targets = targets or []
        self.x_value = x_value
        self.is_ability = is_ability
        self.is_mana_ability = is_mana_ability
        self.has_split_second = has_split_second
        self.copies = copies
        self.countered = False

    def resolve(self, game: "GameState"):
        if not self.countered:
            self.effect(game)

    def __repr__(self) -> str:
        return f"StackItem({self.name} by {self.controller_id})"
