"""
Core game state and turn management.
This is the central hub that all other modules interact with.
"""
from __future__ import annotations
import random
from enum import Enum, auto
from typing import Callable, Dict, List, Optional, Tuple

from .card import Card, CardType, Zone as ZoneEnum, Keyword
from .mana import Color, ManaPool
from .player import Player
from .zones import Battlefield, CommandZone, Exile, Stack, StackItem
from .effects import apply_all_sbas, end_of_phase_cleanup, end_of_turn_cleanup
from .combat import (
    CombatState, AttackAssignment, BlockAssignment,
    resolve_combat_damage, choose_attackers_ai, choose_blockers_ai
)

# Audit logger — optional, attached externally via game.audit = AuditLogger(...)
_AUDIT_STUB = None  # placeholder; real logger set in setup_game()


class Phase(Enum):
    BEGINNING = auto()
    UNTAP = auto()
    UPKEEP = auto()
    DRAW = auto()
    MAIN_1 = auto()
    COMBAT_BEGIN = auto()
    COMBAT_ATTACKERS = auto()
    COMBAT_BLOCKERS = auto()
    COMBAT_DAMAGE = auto()
    COMBAT_END = auto()
    MAIN_2 = auto()
    END = auto()
    CLEANUP = auto()


PHASE_ORDER = [
    Phase.UNTAP, Phase.UPKEEP, Phase.DRAW,
    Phase.MAIN_1,
    Phase.COMBAT_BEGIN, Phase.COMBAT_ATTACKERS, Phase.COMBAT_BLOCKERS,
    Phase.COMBAT_DAMAGE, Phase.COMBAT_END,
    Phase.MAIN_2,
    Phase.END, Phase.CLEANUP,
]

MAIN_PHASES = {Phase.MAIN_1, Phase.MAIN_2}


class GameState:
    """
    Holds all shared game state.
    Shared zones: battlefield, stack, exile, command zone.
    Each player has their own library, hand, graveyard.
    """

    def __init__(self, players: List[Player], seed: Optional[int] = None):
        if seed is not None:
            random.seed(seed)

        self.players: List[Player] = players
        self.player_map: Dict[str, Player] = {p.player_id: p for p in players}

        # Shared zones
        self.battlefield = Battlefield()
        self.stack = Stack()
        self.exile = Exile()
        self.command_zone = CommandZone()

        # Turn tracking
        self.turn_number = 0
        self.active_player_index = 0
        self.phase = Phase.UNTAP
        self.priority_player_index = 0

        # Commander tax: {player_id: {commander_name: times_cast}}
        self.commander_cast_count: Dict[str, Dict[str, int]] = {
            p.player_id: {} for p in players
        }

        # Win/loss tracking
        self.winner: Optional[Player] = None
        self.game_over = False

        # Audit logger — attach with game.audit = AuditLogger(...)
        self.audit = None  # type: Optional[Any]

        # Log
        self.game_log: List[str] = []

        # Combat state
        self.combat = CombatState()

        # Triggers queued to be put on stack
        self.pending_triggers: List[Tuple[str, Callable]] = []

        # Static effect registry
        self._static_effects: List[Dict] = []  # {name, condition, effect}

        # Extra actions per turn
        self.najeela_activated_this_combat = False

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log(self, msg: str):
        self.game_log.append(msg)
        print(f"  [T{self.turn_number}] {msg}")

    def log_separator(self, label: str = ""):
        line = f"{'='*10} {label} {'='*10}" if label else "="*30
        print(line)
        self.game_log.append(line)

    # ------------------------------------------------------------------
    # Player helpers
    # ------------------------------------------------------------------

    def get_player(self, player_id: str) -> Optional[Player]:
        return self.player_map.get(player_id)

    def active_player(self) -> Optional[Player]:
        if not self.players:
            return None
        return self.players[self.active_player_index % len(self.players)]

    def next_player(self, current_id: str) -> Optional[Player]:
        idx = next((i for i, p in enumerate(self.players) if p.player_id == current_id), None)
        if idx is None:
            return None
        return self.players[(idx + 1) % len(self.players)]

    def opponents_of(self, player_id: str) -> List[Player]:
        return [p for p in self.players if p.player_id != player_id and not p.lost]

    def living_players(self) -> List[Player]:
        return [p for p in self.players if not p.lost]

    def remove_lost_players(self):
        """Remove permanents of lost players, etc."""
        for player in self.players:
            if player.lost:
                for card in self.battlefield.permanents_controlled_by(player.player_id):
                    self.battlefield.remove(card)

    # ------------------------------------------------------------------
    # Zone movement
    # ------------------------------------------------------------------

    def move_to_graveyard(self, card: Card):
        """Move a card from wherever it is to its owner's graveyard."""
        owner = self.get_player(card.owner_id)
        if not owner:
            return
        zone = card.zone
        if zone == ZoneEnum.BATTLEFIELD:
            self.battlefield.remove(card)
            if self.audit:
                self.audit.permanent_dies(
                    card.controller_id, owner.name, card.name
                )
            # Trigger "leaves the battlefield" effects
            if card.data.ltb_effect:
                card.data.ltb_effect(card, self)
        elif zone == ZoneEnum.HAND:
            owner.hand.remove(card)
        elif zone == ZoneEnum.LIBRARY:
            owner.library.remove(card)
        elif zone == ZoneEnum.EXILE:
            self.exile.remove(card)
        elif zone == ZoneEnum.STACK:
            self.stack._cards.remove(card) if card in self.stack._cards else None

        # Commander rule: can go to command zone instead
        if card.data.is_commander_eligible and card in [
            c for c in self.command_zone.commanders_for(card.owner_id) + [card]
        ]:
            # Check if it's actually a commander (registered)
            owner_cmds = [
                c.name for c in self.command_zone.commanders_for(card.owner_id)
            ]
            if card.name in owner_cmds or any(
                c.name == card.name for c in self.battlefield.cards()
                if c is card
            ):
                pass  # It was on the battlefield as commander

        owner.graveyard.add(card)

    def move_to_battlefield(self, card: Card, controller_id: Optional[str] = None):
        """Put a card onto the battlefield."""
        if controller_id:
            card.controller_id = controller_id
        owner = self.get_player(card.owner_id)
        zone = card.zone

        if zone == ZoneEnum.HAND and owner:
            owner.hand.remove(card)
        elif zone == ZoneEnum.LIBRARY and owner:
            owner.library.remove(card)
        elif zone == ZoneEnum.GRAVEYARD and owner:
            owner.graveyard.remove(card)
        elif zone == ZoneEnum.EXILE:
            self.exile.remove(card)
        elif zone == ZoneEnum.COMMAND:
            self.command_zone.remove(card)

        card.summoning_sick = True
        card.damage_taken = 0
        card.tapped = False
        self.battlefield.add(card)

        if self.audit:
            ctrl = self.get_player(card.controller_id)
            self.audit.permanent_etb(
                card.controller_id,
                ctrl.name if ctrl else card.controller_id,
                card.name,
                [t.value for t in card.data.card_types],
            )

        # Trigger ETB
        if card.data.etb_effect:
            card.data.etb_effect(card, self)

    def move_to_exile(self, card: Card):
        """Exile a card from any zone."""
        from .effects import exile_card
        exile_card(card, self)

    def return_commander_to_command_zone(self, card: Card) -> bool:
        """
        When a commander would go to graveyard or exile, its owner may redirect it
        to the command zone instead. Returns True if redirected.
        """
        # Check if it's registered as a commander
        owner = self.get_player(card.owner_id)
        if not owner:
            return False
        # Is this card actually a commander?
        cmd_names = [c.name for c in self.command_zone.commanders_for(card.owner_id)]
        # We track all commanders that have been in the command zone
        if card.name in self._commander_names_for(card.owner_id):
            card.zone = ZoneEnum.LIMBO
            self.command_zone.add(card)
            self.log(f"{card.name} returns to the command zone.")
            return True
        return False

    def _commander_names_for(self, owner_id: str) -> List[str]:
        """Get names of all commanders for a given player (past and present)."""
        return list(self.commander_cast_count.get(owner_id, {}).keys())

    # ------------------------------------------------------------------
    # Casting / Playing
    # ------------------------------------------------------------------

    def cast_spell(self, card: Card, player: Player, x_value: int = 0,
                   targets: Optional[list] = None) -> bool:
        """
        Cast a spell: pay its cost, put it on the stack.
        Returns True if successfully cast.
        """
        cost = card.data.mana_cost

        # Apply commander tax
        if card.zone == ZoneEnum.COMMAND:
            times_cast = self.commander_cast_count.get(player.player_id, {}).get(card.name, 0)
            from .mana import ManaCost
            tax = ManaCost(generic=times_cast * 2)
            # Add tax to cost (simplified: just increase generic)
            from dataclasses import replace
            cost = ManaCost(
                generic=cost.generic + tax.generic,
                pips=dict(cost.pips),
                phyrexian=dict(cost.phyrexian),
                hybrid=list(cost.hybrid),
                x_count=cost.x_count,
            )

        if not player.mana_pool.can_pay(cost, x_value):
            return False

        player.mana_pool.pay(cost, x_value)

        # Move to stack
        def resolve_effect(game: GameState):
            _resolve_cast(card, game, player.player_id, x_value, targets)

        item = StackItem(
            source=card,
            controller_id=player.player_id,
            effect=resolve_effect,
            name=card.name,
            targets=targets or [],
            x_value=x_value,
        )
        self.stack.push(item)
        self.log(f"{player.name} casts {card.name}.")
        if self.audit:
            self.audit.spell_cast(
                player.player_id, player.name, card.name,
                str(card.data.mana_cost), card.data.cmc,
                [t.value for t in card.data.card_types],
                targets=[getattr(t, 'name', str(t)) for t in (targets or [])],
                x_value=x_value,
            )

        # Storm trigger
        if Keyword.STORM in card.data.keywords:
            storm_count = getattr(self, '_spells_this_turn', 0)
            for _ in range(storm_count):
                copy_item = StackItem(
                    source=None,
                    controller_id=player.player_id,
                    effect=lambda game, c=card: _resolve_cast(c, game, player.player_id, x_value, targets),
                    name=f"{card.name} (storm copy)",
                    targets=targets or [],
                    x_value=x_value,
                    is_ability=True,
                )
                self.stack.push(copy_item)
            self.log(f"Storm: {storm_count} copies created.")

        # Track spell count for Storm
        self._spells_this_turn = getattr(self, '_spells_this_turn', 0) + 1

        # Update commander tax
        if card.zone == ZoneEnum.COMMAND:
            if player.player_id not in self.commander_cast_count:
                self.commander_cast_count[player.player_id] = {}
            name = card.name
            self.commander_cast_count[player.player_id][name] = (
                self.commander_cast_count[player.player_id].get(name, 0) + 1
            )

        return True

    def play_land(self, card: Card, player: Player) -> bool:
        """Play a land. Can only be done during your main phase."""
        if player.lands_played_this_turn >= player.max_lands_per_turn:
            return False
        if card.zone == ZoneEnum.HAND:
            player.hand.remove(card)
        player.lands_played_this_turn += 1
        self.move_to_battlefield(card, player.player_id)
        card.summoning_sick = False  # lands don't have summoning sickness
        self.log(f"{player.name} plays {card.name}.")
        if self.audit:
            self.audit.land_played(
                player.player_id, player.name, card.name,
                [t.value for t in card.data.card_types],
            )
        return True

    def activate_ability(self, card: Card, ability_index: int,
                         player: Player, x_value: int = 0,
                         targets: Optional[list] = None,
                         color_choice: Optional[Color] = None) -> bool:
        """Activate a card's activated ability."""
        if ability_index >= len(card.data.activated_abilities):
            return False
        ability = card.data.activated_abilities[ability_index]
        cost = ability.get("cost")
        effect_fn = ability.get("effect")

        if cost and not _pay_ability_cost(card, cost, player, self, color_choice):
            return False

        if effect_fn:
            def resolve_abil(game: GameState):
                effect_fn(card, game, player, x_value, targets)

            item = StackItem(
                source=card,
                controller_id=player.player_id,
                effect=resolve_abil,
                name=ability.get("name", f"{card.name} ability"),
                targets=targets or [],
                x_value=x_value,
                is_ability=True,
            )
            self.stack.push(item)
            self.log(f"{player.name} activates {ability.get('name', card.name)}.")
        return True

    # ------------------------------------------------------------------
    # Stack resolution
    # ------------------------------------------------------------------

    def resolve_stack(self):
        """Resolve the top item on the stack."""
        item = self.stack.pop()
        if item is None:
            return
        self.log(f"Resolving: {item.name}")
        if item.countered:
            if self.audit and item.source:
                self.audit.spell_countered(
                    item.name, item.controller_id,
                    countered_by="counter effect", countered_by_player="?"
                )
        else:
            if self.audit and item.source and not item.is_ability:
                ctrl = self.get_player(item.controller_id)
                self.audit.spell_resolve(
                    item.name, item.controller_id,
                    ctrl.name if ctrl else item.controller_id
                )
        item.resolve(self)
        apply_all_sbas(self)

    def resolve_all_stack(self):
        """Keep resolving until stack is empty (AI passes priority)."""
        while not self.stack.is_empty() and not self.game_over:
            self.resolve_stack()

    # ------------------------------------------------------------------
    # Turn structure
    # ------------------------------------------------------------------

    def run_game(self, max_turns: int = 20):
        """Main game loop."""
        self.log_separator("GAME START")
        for player in self.players:
            self.log(f"  {player.name}: {[c.name for c in player.hand.cards()]}")

        while not self.game_over and self.turn_number < max_turns:
            self._run_turn()
            # Check win conditions
            self._check_win_conditions()
            if self.game_over:
                break
            # Advance turn
            self.active_player_index = (self.active_player_index + 1) % len(self.players)
            # Skip lost players
            while self.active_player().lost:
                self.active_player_index = (self.active_player_index + 1) % len(self.players)
                if len(self.living_players()) == 1:
                    break

        if not self.winner and self.living_players():
            self.winner = self.living_players()[0]
        if self.winner:
            self.log_separator(f"GAME OVER — Winner: {self.winner.name}")
        else:
            self.log_separator("GAME OVER — Draw/Timeout")

        if self.audit:
            self.audit.game_end(
                winner_name=self.winner.name if self.winner else None,
                winner_id=self.winner.player_id if self.winner else None,
                win_condition=getattr(self, '_win_condition_name', "unknown"),
                total_turns=self.turn_number,
            )
            self.audit.save(self)

    def _run_turn(self):
        self.turn_number += 1
        active = self.active_player()
        self.log_separator(f"Turn {self.turn_number} — {active.name}")
        self._spells_this_turn = 0
        active.lands_played_this_turn = 0
        self.najeela_activated_this_combat = False

        if self.audit:
            life_totals = {p.player_id: p.life for p in self.players}
            hand_sizes  = {p.player_id: len(p.hand) for p in self.players}
            self.audit.turn_start(
                self.turn_number, active.player_id, active.name,
                life_totals, hand_sizes,
            )

        for phase in PHASE_ORDER:
            self.phase = phase
            self._run_phase(phase, active)
            self._check_win_conditions()
            if self.game_over:
                return

    def _run_phase(self, phase: Phase, active: Player):
        if phase == Phase.UNTAP:
            self._phase_untap(active)
        elif phase == Phase.UPKEEP:
            self._phase_upkeep(active)
        elif phase == Phase.DRAW:
            self._phase_draw(active)
        elif phase in MAIN_PHASES:
            self._phase_main(active, phase)
        elif phase == Phase.COMBAT_BEGIN:
            self._phase_combat_begin(active)
        elif phase == Phase.COMBAT_ATTACKERS:
            self._phase_declare_attackers(active)
        elif phase == Phase.COMBAT_BLOCKERS:
            self._phase_declare_blockers(active)
        elif phase == Phase.COMBAT_DAMAGE:
            self._phase_combat_damage(active)
        elif phase == Phase.COMBAT_END:
            self._phase_combat_end(active)
        elif phase == Phase.END:
            self._phase_end(active)
        elif phase == Phase.CLEANUP:
            self._phase_cleanup(active)

    def _phase_untap(self, active: Player):
        self.battlefield.untap_all(active.player_id)
        for card in self.battlefield.permanents_controlled_by(active.player_id):
            card.reset_for_turn()
        # Trigger "at the beginning of your untap step" effects
        active.has_drawn_this_turn = False

    def _phase_upkeep(self, active: Player):
        self.log(f"[Upkeep] {active.name}")
        # Trigger upkeep effects (Rhystic Study tax, Mystic Remora, etc.)
        self._fire_upkeep_triggers(active)
        self._give_priority(active)

    def _phase_draw(self, active: Player):
        if self.turn_number > 1 or active.player_id != self.players[0].player_id:
            drawn = active.draw(1)
            self.log(f"{active.name} draws a card. Hand size: {len(active.hand)}")
            if self.audit and drawn:
                self.audit.card_drawn(
                    active.player_id, active.name,
                    drawn[0].name, source="draw step"
                )
        active.has_drawn_this_turn = True

    def _phase_main(self, active: Player, phase: Phase):
        label = "Main Phase 1" if phase == Phase.MAIN_1 else "Main Phase 2"
        self.log(f"[{label}] {active.name}")
        self._give_priority(active)

    def _phase_combat_begin(self, active: Player):
        self.log(f"[Combat] {active.name} begins combat.")
        self._give_priority(active)

    def _phase_declare_attackers(self, active: Player):
        opponents = self.opponents_of(active.player_id)
        if not opponents:
            return

        if active.is_human:
            attacks = self._human_declare_attackers(active, opponents)
        else:
            attacks = active.ai.declare_attackers(active, opponents, self) if active.ai else \
                      choose_attackers_ai(self, active, opponents)

        self.combat.attackers = attacks
        if attacks:
            names = [f"{a.attacker.name}->{self.get_player(a.defending_player_id).name if a.defending_player_id else '?'}"
                     for a in attacks]
            self.log(f"{active.name} attacks with: {', '.join(names)}")
            # Tap attackers (without vigilance)
            for atk in attacks:
                if not atk.attacker.has_keyword(Keyword.VIGILANCE):
                    atk.attacker.tap()
        else:
            self.log(f"{active.name} doesn't attack.")

        self._give_priority(active)

    def _phase_declare_blockers(self, active: Player):
        if not self.combat.attackers:
            return
        for opp in self.opponents_of(active.player_id):
            if opp.is_human:
                blocks = self._human_declare_blockers(opp, self.combat.attackers)
            else:
                blocks = opp.ai.declare_blockers(opp, self.combat.attackers, self) if opp.ai else \
                         choose_blockers_ai(self, opp, self.combat.attackers)
            self.combat.blockers.extend(blocks)
        self._give_priority(active)

    def _phase_combat_damage(self, active: Player):
        if not self.combat.attackers:
            return
        msgs = resolve_combat_damage(self.combat, self)
        apply_all_sbas(self)

    def _phase_combat_end(self, active: Player):
        self.combat.clear()
        self._give_priority(active)

    def _phase_end(self, active: Player):
        self.log(f"[End Step] {active.name}")
        self._fire_end_step_triggers(active)
        self._give_priority(active)

    def _phase_cleanup(self, active: Player):
        # Clear damage
        for card in self.battlefield.cards():
            card.damage_taken = 0
        # Discard to hand size
        while len(active.hand) > active.must_discard_to:
            if active.is_human:
                self._human_discard(active)
            else:
                # AI discards the "least valuable" card
                worst = active.ai.choose_discard(active, self) if active.ai else active.hand.cards()[-1]
                active.discard(worst)
                self.log(f"{active.name} discards {worst.name}.")
        # Empty mana pools
        for player in self.players:
            player.mana_pool.empty()

    # ------------------------------------------------------------------
    # Priority passing
    # ------------------------------------------------------------------

    def _give_priority(self, active: Player):
        """
        Give priority to each player in turn order.
        Players take actions (cast spells, activate abilities) or pass.
        Stack resolves when all players pass in succession.
        """
        # Give each player a chance to act, starting with active player
        for player in [active] + self.opponents_of(active.player_id):
            if player.lost:
                continue
            player.passed_priority = False

        # Loop: give priority until all pass with empty stack
        passes_in_a_row = 0
        player_order = [active] + self.opponents_of(active.player_id)
        idx = 0

        while True:
            if self.game_over:
                return

            current = player_order[idx % len(player_order)]
            if current.lost:
                idx += 1
                passes_in_a_row += 1
                if passes_in_a_row >= len(player_order):
                    if self.stack.is_empty():
                        break
                    self.resolve_stack()
                    passes_in_a_row = 0
                continue

            action_taken = False
            if current.is_human:
                action_taken = self._human_priority_action(current, active)
            else:
                action_taken = self._ai_priority_action(current, active)

            if action_taken:
                passes_in_a_row = 0
            else:
                passes_in_a_row += 1

            if passes_in_a_row >= len([p for p in player_order if not p.lost]):
                if self.stack.is_empty():
                    break
                # Resolve top of stack
                self.resolve_stack()
                passes_in_a_row = 0
                idx = 0  # restart priority from active player
                continue

            idx += 1

    def _ai_priority_action(self, player: Player, active: Player) -> bool:
        """Ask AI what to do with priority. Returns True if action was taken."""
        if player.ai:
            is_active = player.player_id == active.player_id
            is_main = self.phase in MAIN_PHASES
            return player.ai.take_priority_action(player, active, self, is_active, is_main)
        return False

    def _human_priority_action(self, player: Player, active: Player) -> bool:
        """Human player takes a priority action via CLI."""
        from ..ui.cli import prompt_priority_action
        is_active = player.player_id == active.player_id
        is_main = self.phase in MAIN_PHASES
        return prompt_priority_action(player, active, self, is_active, is_main)

    def _human_declare_attackers(self, player: Player, opponents: List[Player]):
        from ..ui.cli import prompt_declare_attackers
        return prompt_declare_attackers(player, opponents, self)

    def _human_declare_blockers(self, player: Player, attackers):
        from ..ui.cli import prompt_declare_blockers
        return prompt_declare_blockers(player, attackers, self)

    def _human_discard(self, player: Player):
        from ..ui.cli import prompt_discard
        prompt_discard(player, self)

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------

    def _fire_upkeep_triggers(self, active: Player):
        """Fire 'at the beginning of your upkeep' triggered abilities."""
        for card in self.battlefield.cards():
            for trig in card.data.triggered_abilities:
                if trig.get("trigger") == "upkeep":
                    ctrl = self.get_player(card.controller_id)
                    if ctrl and (trig.get("each_player") or card.controller_id == active.player_id):
                        effect = trig.get("effect")
                        if effect:
                            effect(card, self, ctrl)

    def _fire_end_step_triggers(self, active: Player):
        """Fire 'at the beginning of the end step' triggered abilities."""
        for card in self.battlefield.cards():
            for trig in card.data.triggered_abilities:
                if trig.get("trigger") == "end_step":
                    ctrl = self.get_player(card.controller_id)
                    if ctrl and (trig.get("each_player") or card.controller_id == active.player_id):
                        effect = trig.get("effect")
                        if effect:
                            effect(card, self, ctrl)

    # ------------------------------------------------------------------
    # Win condition checks
    # ------------------------------------------------------------------

    def _check_win_conditions(self):
        # Check for players who have won
        for player in self.players:
            if player.won and not self.game_over:
                self.winner = player
                self.game_over = True
                self.log(f"*** {player.name} wins! ***")
                win_cond = getattr(self, '_win_condition_name', "unknown")
                if self.audit:
                    self.audit.win_condition(
                        player.player_id, player.name, win_cond,
                        self.turn_number, self.phase.name,
                    )
                return

        # Check for players who have lost (life ≤ 0, deck out, etc.)
        for player in self.players:
            if not player.lost and player.life <= 0:
                player.lost = True
                self.log(f"*** {player.name} is eliminated (life ≤ 0). ***")
                if self.audit:
                    self.audit.player_lost(
                        player.player_id, player.name, "life total",
                        self.turn_number, self.phase.name,
                    )
            elif not player.lost and len(player.library) == 0 and player.has_drawn_this_turn:
                player.lost = True
                self.log(f"*** {player.name} is eliminated (empty library). ***")
                if self.audit:
                    self.audit.player_lost(
                        player.player_id, player.name, "empty library",
                        self.turn_number, self.phase.name,
                    )

        living = self.living_players()
        if len(living) == 1:
            self.winner = living[0]
            self.game_over = True
            self.log(f"*** {living[0].name} wins (last player standing)! ***")
            if self.audit:
                self.audit.win_condition(
                    living[0].player_id, living[0].name, "last standing",
                    self.turn_number, self.phase.name,
                )
        elif len(living) == 0:
            self.game_over = True
            self.log("*** No winners — simultaneous loss. ***")

    def setup_game(self, deck_map: Dict[str, List[Card]], commander_map: Dict[str, List[Card]]):
        """
        Setup the game: put commanders in command zone, shuffle libraries, draw 7.
        deck_map: {player_id: [Card...]} — deck without commanders
        commander_map: {player_id: [Card...]} — commander(s)
        """
        for player in self.players:
            # Set up commander
            for cmd in commander_map.get(player.player_id, []):
                cmd.owner_id = player.player_id
                cmd.controller_id = player.player_id
                self.command_zone.add(cmd)
                # Register in cast count
                if player.player_id not in self.commander_cast_count:
                    self.commander_cast_count[player.player_id] = {}
                self.commander_cast_count[player.player_id][cmd.name] = 0

            # Set up library
            deck = deck_map.get(player.player_id, [])
            for card in deck:
                card.owner_id = player.player_id
                card.controller_id = player.player_id
                player.library.add(card, "bottom")
            player.library.shuffle()

            # Draw opening hand (7 cards)
            player.draw(7)
            self.log(f"{player.name} draws opening hand: {[c.name for c in player.hand.cards()]}")

        self.log_separator("GAME SETUP COMPLETE")

        if self.audit:
            self.audit.game_start(
                players=[
                    {"id": p.player_id, "name": p.name, "is_human": p.is_human}
                    for p in self.players
                ],
                commanders={
                    p.player_id: [c.name for c in commander_map.get(p.player_id, [])]
                    for p in self.players
                },
            )
            for player in self.players:
                self.audit.opening_hand(
                    player.player_id, player.name,
                    [c.name for c in player.hand.cards()],
                )


# ------------------------------------------------------------------
# Internal helpers
# ------------------------------------------------------------------

def _resolve_cast(card: Card, game: GameState, controller_id: str,
                  x_value: int, targets: Optional[list]):
    """Handle spell resolution after it pops off the stack."""
    player = game.get_player(controller_id)
    if not player:
        return

    if card.data.is_permanent:
        # Permanent: enters the battlefield
        game.move_to_battlefield(card, controller_id)
    else:
        # Non-permanent: resolve effect, then graveyard
        if card.data.cast_effect:
            card.data.cast_effect(card, game, player, x_value=x_value, targets=targets)
        player.graveyard.add(card)
        card.zone = ZoneEnum.GRAVEYARD


def _pay_ability_cost(card: Card, cost: dict, player: Player,
                      game: GameState, color_choice: Optional[Color] = None) -> bool:
    """
    Pay an activated ability's cost.
    cost: dict with optional keys: 'tap', 'mana', 'life', 'sacrifice'
    """
    if cost.get("tap"):
        if card.tapped:
            return False
        if CardType.CREATURE in card.data.card_types and card.summoning_sick:
            return False
        card.tap()

    if cost.get("mana"):
        mana_cost = cost["mana"]
        if not player.mana_pool.can_pay(mana_cost):
            return False
        player.mana_pool.pay(mana_cost)

    if cost.get("life"):
        amount = cost["life"]
        if player.life <= amount:
            return False
        player.lose_life(amount)

    if cost.get("sacrifice"):
        target_name = cost["sacrifice"]
        if target_name == "self":
            game.move_to_graveyard(card)
        else:
            victim = game.battlefield.find_by_name(target_name, player.player_id)
            if victim:
                game.move_to_graveyard(victim)
            else:
                return False

    if cost.get("discard"):
        count = cost["discard"]
        for _ in range(count):
            if len(player.hand) == 0:
                return False
            # Discard least valuable (AI) or let human choose
            c = player.hand.cards()[-1]
            player.discard(c)

    return True
