"""
ProfileAI — an AI player driven entirely by a JSON profile.

This replaces the hardcoded subclasses (ConsultationAI, NajeelaAI, etc.)
with a data-driven approach. Any deck can get smart AI behavior just by
adding a profile JSON file — no Python code required.
"""
from __future__ import annotations
from typing import TYPE_CHECKING, Optional
from .base import BaseAI
from .profile_loader import load_profile
from .threat import (
    assess_threat, evaluate_priority_window,
    THREAT_HIGH, THREAT_MEDIUM, THREAT_CRITICAL,
)

if TYPE_CHECKING:
    from ..engine.player import Player
    from ..engine.game import GameState
    from ..engine.card import Card


class ProfileAI(BaseAI):
    """
    AI whose behavior is defined by a JSON profile.
    Falls back to BaseAI defaults for any decision not covered by the profile.

    priority_policy JSON keys:
      counter_hard_threshold  (int, default 70) — threat score at which we use any counter
      counter_free_threshold  (int, default 50) — threat score at which we use a free counter
      always_respond_to       ([str])            — spell names we always counter regardless
      never_counter           ([str])            — spell names we let resolve (table politics)
      hold_up_mana_end_step   (bool)             — keep mana open on opponents' end steps
      pass_on_mana_positive   (bool)             — if opponent's spell helps us, let it resolve
    """

    def __init__(self, player_id: str, deck_id: str):
        super().__init__(player_id, deck_id)
        self.profile = load_profile(deck_id) or {}
        self._strategy = self.profile.get("strategy", "combo")
        self._aggression = float(self.profile.get("aggression", 0.1))
        self._score_overrides: dict = {
            k.lower(): v for k, v in
            self.profile.get("card_score_overrides", {}).items()
        }
        self._always_counter: set = {
            n.lower() for n in self.profile.get("always_counter", [])
        }
        self._life_thresholds: dict = self.profile.get("life_thresholds", {})
        self._artifact_priority: bool = self.profile.get("artifact_priority", False)
        self._attack_strategy: dict = self.profile.get("attack_strategy", {})

        # Priority policy — drives game-theory decisions
        pp = self.profile.get("priority_policy", {})
        self.COUNTER_HARD_THRESHOLD = int(pp.get("counter_hard_threshold", THREAT_HIGH))
        self.COUNTER_FREE_THRESHOLD = int(pp.get("counter_free_threshold", THREAT_MEDIUM))
        self._always_respond_to: set = {
            n.lower() for n in pp.get("always_respond_to", [])
        }
        self._never_counter: set = {
            n.lower() for n in pp.get("never_counter", [])
        }
        self._hold_up_mana_end_step: bool = pp.get("hold_up_mana_end_step", False)
        self._pass_on_mana_positive: bool = pp.get("pass_on_mana_positive", False)

    # ------------------------------------------------------------------
    # Tutor target — core of profile-driven behavior
    # ------------------------------------------------------------------

    def choose_tutor_target(self, player: "Player", game: "GameState") -> str:
        hand_lower = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None
        bf_has = lambda n: game.battlefield.find_by_name(n, player.player_id) is not None

        for rule in self.profile.get("tutor_priority", []):
            condition = rule.get("condition")
            fetch_list = rule.get("fetch", [])

            if condition == "have_piece":
                piece = rule.get("piece", "")
                if piece.lower() in hand_lower or bf_has(piece):
                    for name in fetch_list:
                        if lib_has(name) and name.lower() not in hand_lower:
                            return name

            elif condition == "commander_on_battlefield":
                commander = rule.get("commander", "")
                if bf_has(commander):
                    for name in fetch_list:
                        if lib_has(name) and name.lower() not in hand_lower:
                            return name

            elif condition == "turn_lte":
                max_turn = rule.get("turn", 0)
                if game.turn_number <= max_turn:
                    for name in fetch_list:
                        if lib_has(name) and name.lower() not in hand_lower:
                            return name

            elif condition == "always":
                for name in fetch_list:
                    if lib_has(name) and name.lower() not in hand_lower:
                        return name

        # Fall through to BaseAI default
        return super().choose_tutor_target(player, game)

    # ------------------------------------------------------------------
    # Card scoring
    # ------------------------------------------------------------------

    def _score_spell(self, card, player: "Player", game: "GameState") -> int:
        name_lower = card.name.lower()

        # Profile overrides take priority
        if name_lower in self._score_overrides:
            score = self._score_overrides[name_lower]
            # Boost combo-completing cards even higher when we're close
            if self._is_completing_combo(card, player, game):
                score = min(score + 30, 150)
            return score

        # Artifact bonus for artifact-priority decks (e.g. Tivit)
        if self._artifact_priority:
            from ..engine.card import CardType
            if CardType.ARTIFACT in card.data.card_types:
                return super()._score_spell(card, player, game) + 10

        return super()._score_spell(card, player, game)

    def _is_completing_combo(self, card, player, game) -> bool:
        """Check if casting this card completes a win line."""
        hand_lower = {c.name.lower() for c in player.hand.cards()}
        for line in self.profile.get("win_lines", []):
            pieces_lower = {p.lower() for p in line.get("pieces", [])}
            # Does this card + what's in hand complete the line?
            needed = pieces_lower - {card.name.lower()}
            if needed.issubset(hand_lower):
                return True
        return False

    # ------------------------------------------------------------------
    # Counter decisions — profile-aware game theory
    # ------------------------------------------------------------------

    def _should_counter(self, stack_item, player, game) -> bool:
        """
        Override: checks always_respond_to and never_counter profile lists
        before falling through to ThreatAssessment.
        """
        if not stack_item.source:
            return False
        name = stack_item.source.name.lower()

        # Profile: always counter these regardless of score
        if name in self._always_counter or name in self._always_respond_to:
            return True

        # Profile: never counter these (table politics, deal-making)
        if name in self._never_counter:
            return False

        # Delegate to game theory
        return super()._should_counter(stack_item, player, game)

    def _respond_to_stack(self, player, game) -> bool:
        """
        Profile-aware override. Also checks pass_on_mana_positive heuristic:
        if an opponent's spell gives everyone mana/cards (wheel, rhystic tax, etc.)
        and we benefit too, consider passing.
        """
        top = game.stack.peek()
        if not top or top.controller_id == player.player_id:
            return False

        spell_name = (top.source.name if top.source else top.name).lower()

        # Explicit always-respond list bypasses all other logic
        if spell_name in self._always_respond_to:
            counter = self._find_counterspell(player, game)
            if counter:
                self._tap_mana_sources(player, game)
                acted = game.cast_spell(counter, player, targets=[top])
                if acted and game.audit:
                    game.audit.ai_decision(
                        player.player_id, player.name,
                        action="counter",
                        card_name=counter.name,
                        score=100,
                        reasoning=f"always_respond_to list: {spell_name}",
                    )
                return acted

        # Mana-positive pass: let opponent's group hug spell go through
        _mana_positive = {"rhystic study", "mystic remora", "smothering tithe",
                          "windfall", "timetwister"}
        if self._pass_on_mana_positive and spell_name in _mana_positive:
            if game.audit:
                game.audit.ai_counter_eval(
                    player.player_id, player.name,
                    target_spell=top.name,
                    decision="pass",
                    reason="pass_on_mana_positive policy",
                )
            return False

        # Delegate to base game theory (ThreatAssessment)
        return super()._respond_to_stack(player, game)

    # ------------------------------------------------------------------
    # Combat — respect aggression setting
    # ------------------------------------------------------------------

    def declare_attackers(self, player, opponents, game) -> list:
        import random
        from ..engine.combat import AttackAssignment
        from ..engine.card import CardType

        attack_strat = self._attack_strategy
        always_attack = attack_strat.get("attack_always", False)

        # Aggro/combo decks (Najeela): always swing
        if always_attack or self._aggression >= 0.8:
            creatures = game.battlefield.creatures_controlled_by(player.player_id)
            if not opponents:
                return []
            prefer_weakest = attack_strat.get("prefer_weakest_opponent", True)
            target = min(opponents, key=lambda p: p.life) if prefer_weakest \
                     else max(opponents, key=lambda p: p.life)
            attacks = []
            for c in creatures:
                if c.can_attack():
                    attacks.append(AttackAssignment(
                        attacker=c,
                        defending_player_id=target.player_id,
                    ))
            return attacks

        # Low-aggression decks: only attack if random roll < aggression
        # or if we can deal lethal
        if random.random() < self._aggression:
            return super().declare_attackers(player, opponents, game)

        # Always swing if lethal
        creatures = game.battlefield.creatures_controlled_by(player.player_id)
        if not opponents:
            return []
        for opp in sorted(opponents, key=lambda p: p.life):
            total_power = sum(c.power or 0 for c in creatures if c.can_attack())
            if total_power >= opp.life:
                return [
                    AttackAssignment(attacker=c, defending_player_id=opp.player_id)
                    for c in creatures if c.can_attack()
                ]

        return []

    # ------------------------------------------------------------------
    # Life threshold helpers (used by effects)
    # ------------------------------------------------------------------

    def ad_nauseam_stop_life(self) -> int:
        return self._life_thresholds.get("ad_nauseam_stop", 5)

    def shock_land_threshold(self) -> int:
        return self._life_thresholds.get("shock_land_pay", 4)

    def necropotence_target_life(self) -> int:
        return self._life_thresholds.get("necropotence_draw_to", 12)
