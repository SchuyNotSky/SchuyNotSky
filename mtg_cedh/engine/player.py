"""
Player class: state, resources, and zone references.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from .mana import ManaPool, Color
from .card import Card, CardType, Zone as ZoneEnum
from .zones import Library, Hand, Graveyard, Exile, CommandZone

if TYPE_CHECKING:
    from .game import GameState


class Player:
    def __init__(self, player_id: str, name: str, is_human: bool = False):
        self.player_id = player_id
        self.name = name
        self.is_human = is_human

        # Life
        self.life = 40  # EDH starts at 40

        # Mana
        self.mana_pool = ManaPool()

        # Zones (personal)
        self.library = Library(player_id)
        self.hand = Hand(player_id)
        self.graveyard = Graveyard(player_id)
        self.exile = Exile(player_id)

        # Commander damage received from each opponent's commanders
        # {source_commander_name: damage_taken}
        self.commander_damage: Dict[str, int] = {}

        # State flags
        self.has_drawn_this_turn = False
        self.lands_played_this_turn = 0
        self.max_lands_per_turn = 1
        self.lost = False
        self.won = False

        # Poison/infect counters
        self.poison_counters = 0

        # Priority / turn state
        self.passed_priority = False

        # Extra turns queued
        self.extra_turns = 0

        # Tracking for forced effects
        self.must_discard_to = 7  # max hand size

        # AI reference (set externally)
        self.ai = None  # will be an AIPlayer instance if not human

    def take_damage(self, amount: int, source: Optional[Card] = None,
                    source_player: Optional["Player"] = None,
                    is_combat: bool = False) -> int:
        """Apply damage. Returns actual damage dealt."""
        if amount <= 0:
            return 0
        self.life -= amount
        # Track commander damage
        if is_combat and source and source_player:
            key = f"{source_player.player_id}:{source.name}"
            self.commander_damage[key] = self.commander_damage.get(key, 0) + amount
        return amount

    def gain_life(self, amount: int):
        self.life = min(self.life + amount, 999)

    def lose_life(self, amount: int):
        self.life -= amount

    def add_poison(self, amount: int = 1):
        self.poison_counters += amount

    def is_dead(self) -> bool:
        if self.lost:
            return True
        if self.life <= 0:
            return True
        if self.poison_counters >= 10:
            return True
        # Commander damage: 21 from same commander
        for damage in self.commander_damage.values():
            if damage >= 21:
                return True
        return False

    def check_mill_loss(self) -> bool:
        """Returns True if player must draw but can't."""
        return len(self.library) == 0

    def draw(self, count: int = 1) -> List[Card]:
        """Draw cards from library to hand. Returns drawn cards."""
        drawn = []
        for _ in range(count):
            card = self.library.draw()
            if card is None:
                self.lost = True  # drew from empty library
                break
            self.hand.add(card)
            drawn.append(card)
        return drawn

    def discard(self, card: Card) -> bool:
        """Discard a card from hand to graveyard."""
        if self.hand.remove(card):
            self.graveyard.add(card)
            return True
        return False

    def discard_hand(self) -> List[Card]:
        """Discard entire hand."""
        cards = self.hand.cards()
        for c in cards:
            self.hand.remove(c)
            self.graveyard.add(c)
        return cards

    def can_cast_at_speed(self, card: Card, main_phase: bool, is_active: bool) -> bool:
        """
        Determine if a card can be cast based on timing restrictions.
        Instants / abilities with flash can be cast anytime.
        Sorceries / permanents only during your main phase with empty stack.
        """
        from .card import Keyword
        has_flash = card.has_keyword(Keyword.FLASH)
        is_instant = CardType.INSTANT in card.data.card_types
        is_land = CardType.LAND in card.data.card_types
        if is_land:
            return main_phase and is_active and self.lands_played_this_turn < self.max_lands_per_turn
        if is_instant or has_flash:
            return True
        return main_phase and is_active

    def produce_mana_from_permanent(self, permanent: Card,
                                    color_choice: Optional[Color] = None) -> bool:
        """Tap a permanent to produce mana. Returns True if successful."""
        if permanent.tapped:
            return False
        if permanent.controller_id != self.player_id:
            return False
        if CardType.CREATURE in permanent.data.card_types and permanent.summoning_sick:
            return False

        if permanent.data.tap_mana:
            permanent.tap()
            for color, amount in permanent.data.tap_mana.items():
                self.mana_pool.add(color, amount)
            return True
        elif permanent.data.tap_mana_choice:
            if color_choice is None:
                color_choice = Color.COLORLESS
            permanent.tap()
            self.mana_pool.add(color_choice, 1)
            return True
        return False

    def total_mana_available(self, battlefield) -> int:
        """Estimate total tappable mana from battlefield."""
        return battlefield.max_mana_available(self.player_id)

    def __repr__(self) -> str:
        return f"Player({self.name}, {self.life} life, hand={len(self.hand)})"
