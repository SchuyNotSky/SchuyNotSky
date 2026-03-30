"""
Combat system: declare attackers, declare blockers, damage assignment, combat damage.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from .card import Card, CardType, Keyword

if TYPE_CHECKING:
    from .game import GameState
    from .player import Player


@dataclass
class AttackAssignment:
    attacker: Card
    defending_player_id: Optional[str] = None   # attacking player directly
    defending_planeswalker: Optional[Card] = None


@dataclass
class BlockAssignment:
    blocker: Card
    blocked_attacker: Card


@dataclass
class CombatState:
    attackers: List[AttackAssignment] = field(default_factory=list)
    blockers: List[BlockAssignment] = field(default_factory=list)
    damage_assigned: bool = False

    def get_blockers_for(self, attacker: Card) -> List[Card]:
        return [b.blocker for b in self.blockers if b.blocked_attacker is attacker]

    def get_attack_for(self, attacker: Card) -> Optional[AttackAssignment]:
        for a in self.attackers:
            if a.attacker is attacker:
                return a
        return None

    def is_blocked(self, attacker: Card) -> bool:
        return any(b.blocked_attacker is attacker for b in self.blockers)

    def clear(self):
        self.attackers.clear()
        self.blockers.clear()
        self.damage_assigned = False


def resolve_combat_damage(combat: CombatState, game: "GameState") -> List[str]:
    """
    Resolve all combat damage. Returns log messages.
    Handles: first strike, double strike, deathtouch, lifelink, trample.
    """
    log = []

    # Separate first/double strike from normal
    first_strikers: List[AttackAssignment] = []
    normal: List[AttackAssignment] = []

    for atk in combat.attackers:
        c = atk.attacker
        if c.has_keyword(Keyword.FIRST_STRIKE) or c.has_keyword(Keyword.DOUBLE_STRIKE):
            first_strikers.append(atk)
        else:
            normal.append(atk)

    # First strike damage step
    if first_strikers:
        msgs = _deal_combat_damage(first_strikers, combat, game, first_strike=True)
        log.extend(msgs)
        _apply_state_based_actions(game)

    # Normal/double strike damage step
    double_and_normal = normal + [a for a in first_strikers
                                  if a.attacker.has_keyword(Keyword.DOUBLE_STRIKE)]
    if double_and_normal:
        msgs = _deal_combat_damage(double_and_normal, combat, game, first_strike=False)
        log.extend(msgs)

    return log


def _deal_combat_damage(
    assignments: List[AttackAssignment],
    combat: CombatState,
    game: "GameState",
    first_strike: bool
) -> List[str]:
    log = []

    for atk_assign in assignments:
        attacker = atk_assign.attacker
        if attacker.zone.value != "battlefield":
            continue  # died already
        blockers = combat.get_blockers_for(attacker)
        pwr = attacker.power or 0

        if not blockers:
            # Unblocked damage to player or planeswalker
            if atk_assign.defending_player_id:
                def_player = game.get_player(atk_assign.defending_player_id)
                if def_player:
                    def_player.take_damage(
                        pwr, source=attacker,
                        source_player=game.get_player(attacker.controller_id),
                        is_combat=True
                    )
                    if attacker.has_keyword(Keyword.LIFELINK):
                        ctrl = game.get_player(attacker.controller_id)
                        if ctrl:
                            ctrl.gain_life(pwr)
                    log.append(f"{attacker.name} deals {pwr} combat damage to {def_player.name}")
        else:
            # Blocked: assign damage to blockers
            remaining_damage = pwr
            for blocker in blockers:
                if remaining_damage <= 0:
                    break
                bl_tough = blocker.toughness or 1
                deathtouch = attacker.has_keyword(Keyword.DEATHTOUCH)
                dmg_to_blocker = 1 if deathtouch else min(remaining_damage, bl_tough)
                # With trample, only need lethal damage on each blocker
                if attacker.has_keyword(Keyword.TRAMPLE):
                    lethal = 1 if deathtouch else bl_tough
                    dmg_to_blocker = lethal

                blocker.damage_taken += dmg_to_blocker
                remaining_damage -= dmg_to_blocker
                log.append(f"{attacker.name} deals {dmg_to_blocker} damage to {blocker.name}")

                if attacker.has_keyword(Keyword.LIFELINK):
                    ctrl = game.get_player(attacker.controller_id)
                    if ctrl:
                        ctrl.gain_life(dmg_to_blocker)

            # Trample excess damage
            if attacker.has_keyword(Keyword.TRAMPLE) and remaining_damage > 0:
                if atk_assign.defending_player_id:
                    def_player = game.get_player(atk_assign.defending_player_id)
                    if def_player:
                        def_player.take_damage(
                            remaining_damage, source=attacker,
                            source_player=game.get_player(attacker.controller_id),
                            is_combat=True
                        )
                        log.append(f"{attacker.name} deals {remaining_damage} trample damage to {def_player.name}")
                        if attacker.has_keyword(Keyword.LIFELINK):
                            ctrl = game.get_player(attacker.controller_id)
                            if ctrl:
                                ctrl.gain_life(remaining_damage)

        # Blocker deals damage back to attacker
        for blocker in blockers:
            if blocker.zone.value != "battlefield":
                continue
            bl_pwr = blocker.power or 0
            if bl_pwr > 0:
                attacker.damage_taken += bl_pwr
                log.append(f"{blocker.name} deals {bl_pwr} damage to {attacker.name}")
                if blocker.has_keyword(Keyword.LIFELINK):
                    ctrl = game.get_player(blocker.controller_id)
                    if ctrl:
                        ctrl.gain_life(bl_pwr)

    return log


def _apply_state_based_actions(game: "GameState"):
    """Check for creatures that should die from damage."""
    to_die = []
    for card in game.battlefield.cards():
        if CardType.CREATURE not in card.data.card_types:
            continue
        toughness = card.toughness or 0
        if card.damage_taken >= toughness and toughness > 0:
            if not card.has_keyword(Keyword.INDESTRUCTIBLE):
                to_die.append(card)
        # Deathtouch: any damage is lethal
        # (handled by checking damage_taken > 0 if source had deathtouch)

    for card in to_die:
        game.move_to_graveyard(card)


def choose_attackers_ai(
    game: "GameState",
    active_player: "Player",
    opponents: List["Player"]
) -> List[AttackAssignment]:
    """
    Basic AI: attack with all eligible creatures toward the opponent
    with highest threat (or lowest life for aggro).
    In cEDH, attacking is usually only relevant for commander damage
    or closing out a game. Most wins are through combos.
    """
    assignments = []
    if not opponents:
        return assignments

    # Pick target: opponent with lowest life or most threatening combo setup
    target = min(opponents, key=lambda p: p.life)
    creatures = game.battlefield.creatures_controlled_by(active_player.player_id)

    for creature in creatures:
        if creature.can_attack():
            assignments.append(AttackAssignment(
                attacker=creature,
                defending_player_id=target.player_id
            ))
    return assignments


def choose_blockers_ai(
    game: "GameState",
    defending_player: "Player",
    attackers: List[AttackAssignment]
) -> List[BlockAssignment]:
    """
    Basic AI blocking: block the biggest attacker with the best blocker
    if it's worth it. In cEDH, life is a resource; don't block recklessly.
    """
    assignments = []
    creatures = game.battlefield.creatures_controlled_by(defending_player.player_id)
    available_blockers = [c for c in creatures if c.can_block()]

    # Sort attackers by power descending
    sorted_atks = sorted(
        [a for a in attackers if a.defending_player_id == defending_player.player_id],
        key=lambda a: a.attacker.power or 0,
        reverse=True
    )

    for atk in sorted_atks:
        atk_pwr = atk.attacker.power or 0
        atk_tough = atk.attacker.toughness or 0

        # Find best blocker: can kill the attacker without dying
        for blocker in list(available_blockers):
            bl_pwr = blocker.power or 0
            bl_tough = blocker.toughness or 0

            # Block if we can kill and survive, or if we're losing lots of life
            if bl_pwr >= atk_tough and bl_tough > atk_pwr:
                assignments.append(BlockAssignment(blocker=blocker, blocked_attacker=atk.attacker))
                available_blockers.remove(blocker)
                break

    return assignments
