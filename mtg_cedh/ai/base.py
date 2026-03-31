"""
Base AI player class.
All deck-specific AIs subclass this and override decision methods.
"""
from __future__ import annotations
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..engine.player import Player
    from ..engine.game import GameState
    from ..engine.card import Card
    from ..engine.combat import AttackAssignment, BlockAssignment


class BaseAI:
    """
    Base AI with sensible defaults for cEDH.
    Subclass and override methods for deck-specific behavior.
    """

    def __init__(self, player_id: str, deck_id: str = ""):
        self.player_id = player_id
        self.deck_id = deck_id

    # ------------------------------------------------------------------
    # Priority action — called each time this player has priority
    # ------------------------------------------------------------------

    def take_priority_action(
        self,
        player: "Player",
        active_player: "Player",
        game: "GameState",
        is_active: bool,
        is_main: bool,
    ) -> bool:
        """
        Decide what to do with priority.
        Returns True if an action was taken, False to pass priority.
        """
        # Check for silenced state
        if getattr(player, '_silenced_until_eot', False):
            return False

        # 1. Respond to threats on the stack
        if not game.stack.is_empty():
            response = self._respond_to_stack(player, game)
            if response:
                return True

        # 2. On our own turn during main phase, take proactive actions
        if is_active and is_main:
            acted = self._take_main_phase_action(player, game)
            if acted:
                return True

        # 3. Play lands during opponent's turn? No — only on our turn
        # 4. Flash / instant-speed interaction on opponents' turns
        if not is_active:
            acted = self._take_instant_speed_action(player, game)
            if acted:
                return True

        return False  # pass priority

    # ------------------------------------------------------------------
    # Main phase actions
    # ------------------------------------------------------------------

    def _take_main_phase_action(self, player: "Player", game: "GameState") -> bool:
        from ..engine.card import CardType, Keyword

        # Play a land first
        if player.lands_played_this_turn < player.max_lands_per_turn:
            land = self._pick_land_to_play(player, game)
            if land:
                game.play_land(land, player)
                return True

        # Tap mana sources to fill pool
        self._tap_mana_sources(player, game)

        # Try to cast the highest-priority spell we can afford
        spell = self._pick_spell_to_cast(player, game, is_main=True, is_active=True)
        if spell:
            success = game.cast_spell(spell, player)
            if success:
                return True

        # Activate mana abilities (Thrasios, etc.)
        acted = self._activate_abilities(player, game, is_main=True)
        return acted

    def _take_instant_speed_action(self, player: "Player", game: "GameState") -> bool:
        """Take instant-speed actions on opponents' turns."""
        self._tap_mana_sources(player, game)
        spell = self._pick_spell_to_cast(player, game, is_main=False, is_active=False)
        if spell:
            return game.cast_spell(spell, player)
        return False

    # ------------------------------------------------------------------
    # Stack responses
    # ------------------------------------------------------------------

    def _respond_to_stack(self, player: "Player", game: "GameState") -> bool:
        """Decide whether to counter or respond to the top stack item."""
        top = game.stack.peek()
        if not top:
            return False

        # Don't counter our own spells
        if top.controller_id == player.player_id:
            return False

        # Counter opponent win conditions
        if self._should_counter(top, player, game):
            counter = self._find_counterspell(player, game)
            if counter:
                self._tap_mana_sources(player, game)
                if game.cast_spell(counter, player, targets=[top]):
                    return True

        return False

    def _should_counter(self, stack_item, player: "Player", game: "GameState") -> bool:
        """Decide if a stack item is worth countering."""
        if not stack_item.source:
            return False
        name = stack_item.source.name.lower()
        # Always counter these
        must_counter = {
            "thassa's oracle", "demonic consultation", "tainted pact",
            "ad nauseam", "flash", "underworld breach", "timetwister",
        }
        if name in must_counter:
            return True
        # Counter tutors if we can
        tutors = {"demonic tutor", "vampiric tutor", "imperial seal"}
        if name in tutors and player.life > 15:
            return True
        return False

    def _find_counterspell(self, player: "Player", game: "GameState"):
        """Find the best counterspell to use."""
        from ..engine.card import CardType, Keyword
        priority = [
            "fierce guardianship", "deflecting swat",  # free first
            "force of will", "force of negation",       # pitch
            "pact of negation",                          # free but has cost
            "mana drain", "counterspell",               # hard counters
            "flusterstorm", "swan song", "spell pierce", # soft
            "mental misstep",
        ]
        hand = player.hand.cards()
        for name in priority:
            for c in hand:
                if c.name.lower() == name:
                    if self._can_cast(c, player, game):
                        return c
        return None

    # ------------------------------------------------------------------
    # Spell selection
    # ------------------------------------------------------------------

    def _pick_spell_to_cast(
        self, player: "Player", game: "GameState",
        is_main: bool, is_active: bool
    ):
        """
        Pick the best spell to cast. Returns a Card or None.
        Subclasses override this to implement deck-specific priority.
        """
        from ..engine.card import CardType, Keyword
        hand = player.hand.cards()
        castable = [c for c in hand if self._can_cast_timing(c, player, game, is_main, is_active)]

        if not castable:
            return None

        # Score each card
        scored = [(self._score_spell(c, player, game), c) for c in castable]
        scored.sort(key=lambda x: -x[0])
        best_score, best_card = scored[0]
        if best_score > 0:
            return best_card
        return None

    def _score_spell(self, card, player: "Player", game: "GameState") -> int:
        """Score a card (higher = cast sooner). Override in subclasses."""
        name = card.name.lower()

        # Win condition combos
        win_con_score = {
            "thassa's oracle": 100 if self._library_empty_or_near(player) else 50,
            "demonic consultation": 90 if self._has_oracle_in_hand(player) else 40,
            "tainted pact": 90 if self._has_oracle_in_hand(player) else 40,
            "ad nauseam": 80,
            "underworld breach": 70,
            "isochron scepter": 60,
            "dramatic reversal": 55,
        }
        if name in win_con_score:
            return win_con_score[name]

        # Tutors
        tutor_score = {
            "demonic tutor": 75, "vampiric tutor": 72, "imperial seal": 70,
            "mystical tutor": 68, "merchant scroll": 65,
            "enlightened tutor": 63, "worldly tutor": 60,
            "lim-dul's vault": 58, "gamble": 55,
        }
        if name in tutor_score:
            return tutor_score[name]

        # Fast mana (early turns)
        turn = game.turn_number
        mana_score = {
            "mana crypt": 85, "sol ring": 80, "mana vault": 78,
            "lotus petal": 70, "dark ritual": 65, "cabal ritual": 60,
            "chrome mox": 62, "mox diamond": 62, "jeweled lotus": 75,
            "grim monolith": 58, "basalt monolith": 55,
        }
        if name in mana_score:
            return mana_score[name] - (turn * 3)  # less valuable later

        # Draw engines
        draw_score = {
            "rhystic study": 50, "mystic remora": 48, "necropotence": 55,
            "sylvan library": 45, "windfall": 42, "timetwister": 44,
            "brainstorm": 35, "ponder": 33, "preordain": 31,
            "night's whisper": 30, "gitaxian probe": 28,
        }
        if name in draw_score:
            return draw_score[name]

        # Lands (handled separately)
        from ..engine.card import CardType
        if CardType.LAND in card.data.card_types:
            return 0

        return max(0, 20 - card.data.cmc)

    # ------------------------------------------------------------------
    # Tutor target selection
    # ------------------------------------------------------------------

    def choose_tutor_target(self, player: "Player", game: "GameState") -> str:
        """
        Choose what to tutor for. Override in deck-specific subclasses.
        Default: work toward the Oracle+Consult combo.
        """
        hand_names = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None

        # If we have Oracle, get Consultation
        if "thassa's oracle" in hand_names and lib_has("Demonic Consultation"):
            return "Demonic Consultation"
        if "thassa's oracle" in hand_names and lib_has("Tainted Pact"):
            return "Tainted Pact"

        # If we have Consultation, get Oracle
        if "demonic consultation" in hand_names and lib_has("Thassa's Oracle"):
            return "Thassa's Oracle"
        if "tainted pact" in hand_names and lib_has("Thassa's Oracle"):
            return "Thassa's Oracle"

        # Get Oracle as first piece
        if lib_has("Thassa's Oracle"):
            return "Thassa's Oracle"

        # Get fast mana if early
        if game.turn_number <= 2:
            for name in ["Mana Crypt", "Sol Ring", "Mana Vault"]:
                if lib_has(name) and name.lower() not in hand_names:
                    return name

        # Get a draw spell
        for name in ["Ad Nauseam", "Necropotence", "Rhystic Study"]:
            if lib_has(name):
                return name

        return ""

    def choose_discard(self, player: "Player", game: "GameState"):
        """Choose a card to discard. Returns the least-valuable card in hand."""
        hand = player.hand.cards()
        if not hand:
            return None
        scored = [(self._score_spell(c, player, game), c) for c in hand]
        scored.sort(key=lambda x: x[0])
        return scored[0][1]  # lowest score = discard first

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def declare_attackers(
        self, player: "Player", opponents: list, game: "GameState"
    ) -> list:
        """Default: don't attack (cEDH wins via combo, not combat)."""
        from ..engine.combat import AttackAssignment
        # Only attack if we can deal lethal combat damage or commander damage
        attacks = []
        creatures = game.battlefield.creatures_controlled_by(player.player_id)
        target = min(opponents, key=lambda p: p.life)
        for c in creatures:
            if c.can_attack() and target.life <= (c.power or 0):
                attacks.append(AttackAssignment(attacker=c,
                                                defending_player_id=target.player_id))
        return attacks

    def declare_blockers(
        self, player: "Player", attackers: list, game: "GameState"
    ) -> list:
        """Default: block if it saves significant life."""
        from ..engine.combat import choose_blockers_ai
        return choose_blockers_ai(game, player, attackers)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _can_cast(self, card, player: "Player", game: "GameState") -> bool:
        """Can we pay for this card right now?"""
        return player.mana_pool.can_pay(card.data.mana_cost)

    def _can_cast_timing(self, card, player, game, is_main, is_active) -> bool:
        """Can this card be cast at this time?"""
        from ..engine.card import CardType, Keyword
        if CardType.LAND in card.data.card_types:
            return False  # handled separately
        if not self._can_cast(card, player, game):
            return False
        is_instant = (CardType.INSTANT in card.data.card_types or
                      card.has_keyword(Keyword.FLASH))
        if is_instant:
            return True
        return is_main and is_active

    def _tap_mana_sources(self, player: "Player", game: "GameState"):
        """Tap all available mana sources to fill the mana pool."""
        for card in game.battlefield.untapped_mana_sources(player.player_id):
            if card.data.activated_abilities:
                for abil in card.data.activated_abilities:
                    cost = abil.get("cost", {})
                    if cost.get("tap") and not cost.get("mana") and not cost.get("life"):
                        game.activate_ability(card, 0, player)
                        break
            elif card.data.tap_mana:
                player.produce_mana_from_permanent(card)
            elif card.data.tap_mana_choice:
                color = self._pick_color_for_source(player, game)
                player.produce_mana_from_permanent(card, color)

    def _pick_color_for_source(self, player, game):
        """Pick which color to produce from a choice-land."""
        from ..engine.mana import Color
        from ..engine.card import CardType
        color_needs = {c: 0 for c in Color if c != Color.GENERIC}
        for c in player.hand.cards():
            if CardType.LAND not in c.data.card_types:
                for col, n in c.data.mana_cost.pips.items():
                    color_needs[col] = color_needs.get(col, 0) + n
        if any(v > 0 for v in color_needs.values()):
            return max(color_needs, key=lambda c: color_needs[c])
        return Color.COLORLESS

    def _pick_land_to_play(self, player: "Player", game: "GameState"):
        """Pick the best land to play from hand."""
        from ..engine.card import CardType
        lands = [c for c in player.hand.cards()
                 if CardType.LAND in c.data.card_types]
        if not lands:
            return None
        # Prefer untapped dual/shock lands, then basics
        def land_priority(land):
            name = land.name.lower()
            if any(d in name for d in ["sea", "island", "fountain", "grave", "tomb",
                                        "vents", "foundry", "shrine", "pool", "crypt"]):
                return 3
            if "command tower" in name or "exotic orchard" in name:
                return 2
            return 1
        return max(lands, key=land_priority)

    def _library_empty_or_near(self, player: "Player") -> bool:
        return len(player.library) <= 5

    def _has_oracle_in_hand(self, player: "Player") -> bool:
        return any(c.name.lower() == "thassa's oracle" for c in player.hand.cards())

    def _activate_abilities(self, player: "Player", game: "GameState",
                            is_main: bool) -> bool:
        """Activate non-mana activated abilities."""
        for card in game.battlefield.permanents_controlled_by(player.player_id):
            for i, abil in enumerate(card.data.activated_abilities):
                cost = abil.get("cost", {})
                if cost.get("tap") and cost.get("mana"):
                    # Non-mana tap ability (e.g. Thrasios)
                    mana_cost = cost["mana"]
                    if player.mana_pool.can_pay(mana_cost):
                        game.activate_ability(card, i, player)
                        return True
        return False
