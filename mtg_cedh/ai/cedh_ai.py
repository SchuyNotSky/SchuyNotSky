"""
Deck-specific cEDH AI strategies.
Each class knows the win lines for its deck and pursues them actively.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from .base import BaseAI

if TYPE_CHECKING:
    from ..engine.player import Player
    from ..engine.game import GameState


class ConsultationAI(BaseAI):
    """
    Thrasios + Tymna (4c Consultation).
    Win line: Thassa's Oracle + Demonic Consultation / Tainted Pact.
    Secondary: Ad Nauseam into combo, Necropotence into combo.
    """

    def __init__(self, player_id: str):
        super().__init__(player_id, "thrasios_tymna")

    def choose_tutor_target(self, player: "Player", game: "GameState") -> str:
        hand = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None
        pool = player.mana_pool.total()

        # Step 1: close out immediately if we have one half of combo
        if "thassa's oracle" in hand:
            for consult in ["Demonic Consultation", "Tainted Pact"]:
                if lib_has(consult):
                    return consult
        for consult in ["demonic consultation", "tainted pact"]:
            if consult.replace("demonic consultation","Demonic Consultation").replace("tainted pact","Tainted Pact") in {c.name for c in player.hand.cards()}:
                if lib_has("Thassa's Oracle"):
                    return "Thassa's Oracle"

        # Step 2: get Ad Nauseam / Necropotence to build resources
        for name in ["Ad Nauseam", "Necropotence"]:
            if lib_has(name) and name.lower() not in hand:
                if game.turn_number >= 2:
                    return name

        # Step 3: get Thassa's Oracle as first combo piece
        if lib_has("Thassa's Oracle"):
            return "Thassa's Oracle"

        # Step 4: get mana acceleration early
        if game.turn_number <= 2:
            for name in ["Mana Crypt", "Sol Ring", "Dark Ritual", "Jeweled Lotus"]:
                if lib_has(name) and name.lower() not in hand:
                    return name

        # Step 5: get protection for our combo turn
        if game.turn_number >= 3:
            for name in ["Veil of Summer", "Silence", "Grand Abolisher"]:
                if lib_has(name):
                    return name

        return super().choose_tutor_target(player, game)

    def _score_spell(self, card, player, game) -> int:
        base = super()._score_spell(card, player, game)
        name = card.name.lower()

        # Prioritize Tymna draw if we attacked
        damaged = getattr(player, '_damaged_opponents_this_turn', 0)
        if name == "tymna the weaver" and damaged > 0:
            return 95

        # Boost protection spells when going for combo
        if self._combo_ready(player, game):
            protection = {"veil of summer": 95, "silence": 95, "orim's chant": 95,
                          "grand abolisher": 90}
            if name in protection:
                return protection[name]

        return base

    def _combo_ready(self, player, game) -> bool:
        """Check if we have one half of the Oracle combo in hand."""
        hand = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None
        return (
            ("thassa's oracle" in hand and
             (lib_has("Demonic Consultation") or lib_has("Tainted Pact")))
            or
            (("demonic consultation" in hand or "tainted pact" in hand) and
             lib_has("Thassa's Oracle"))
        )


class NajeelaAI(BaseAI):
    """
    Najeela, the Blade-Blossom (5c Warriors).
    Win line: attack with warriors, activate Najeela with WUBRG for infinite combats.
    Secondary: Oracle+Consult if available.
    """

    def __init__(self, player_id: str):
        super().__init__(player_id, "najeela")

    def declare_attackers(self, player, opponents, game) -> list:
        from ..engine.combat import AttackAssignment
        from ..engine.card import CardType
        attacks = []
        creatures = game.battlefield.creatures_controlled_by(player.player_id)
        if not opponents:
            return attacks
        target = min(opponents, key=lambda p: p.life)

        for c in creatures:
            if c.can_attack():
                attacks.append(AttackAssignment(attacker=c,
                                                defending_player_id=target.player_id))
        return attacks

    def _take_main_phase_action(self, player, game) -> bool:
        acted = super()._take_main_phase_action(player, game)
        if acted:
            return True
        # Try to activate Najeela for infinite combat
        najeela = game.battlefield.find_by_name("Najeela, the Blade-Blossom",
                                                 player.player_id)
        if najeela and not game.najeela_activated_this_combat:
            if game.phase.name.startswith("COMBAT"):
                return game.activate_ability(najeela, 0, player)
        return False

    def choose_tutor_target(self, player, game) -> str:
        hand = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None

        # Najeela in hand? Get WUBRG mana sources
        has_najeela = "najeela, the blade-blossom" in hand or \
                      game.battlefield.find_by_name("Najeela, the Blade-Blossom",
                                                     player.player_id) is not None

        if has_najeela:
            for name in ["Bloom Tender", "Faeburrow Elder", "Selvala, Heart of the Wilds"]:
                if lib_has(name):
                    return name

        # Oracle+Consult as backup
        if "thassa's oracle" in hand:
            if lib_has("Demonic Consultation"):
                return "Demonic Consultation"
        if lib_has("Thassa's Oracle") and \
           ("demonic consultation" in hand or "tainted pact" in hand):
            return "Thassa's Oracle"

        return super().choose_tutor_target(player, game)


class KenrithAI(BaseAI):
    """
    Kenrith, the Returned King (5c Goodstuff).
    Win lines: Iso+Rev (infinite mana -> Kenrith draw), Flash+Hulk, Oracle+Consult.
    """

    def __init__(self, player_id: str):
        super().__init__(player_id, "kenrith")

    def choose_tutor_target(self, player, game) -> str:
        hand = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None

        # Iso+Rev line
        if "isochron scepter" in hand and lib_has("Dramatic Reversal"):
            return "Dramatic Reversal"
        if "dramatic reversal" in hand and lib_has("Isochron Scepter"):
            return "Isochron Scepter"

        # Flash+Hulk line
        if "flash" in hand and lib_has("Protean Hulk"):
            return "Protean Hulk"
        if "protean hulk" in hand and lib_has("Flash"):
            return "Flash"

        # Oracle+Consult
        if "thassa's oracle" in hand:
            for consult in ["Demonic Consultation", "Tainted Pact"]:
                if lib_has(consult):
                    return consult
        if lib_has("Thassa's Oracle"):
            return "Thassa's Oracle"

        # Setup: get Scepter first
        if lib_has("Isochron Scepter") and "isochron scepter" not in hand:
            return "Isochron Scepter"

        return super().choose_tutor_target(player, game)

    def _score_spell(self, card, player, game) -> int:
        base = super()._score_spell(card, player, game)
        name = card.name.lower()
        hand = {c.name.lower() for c in player.hand.cards()}

        # Boost Iso/Rev when we have the partner
        if name == "isochron scepter" and "dramatic reversal" in hand:
            return 95
        if name == "dramatic reversal" and "isochron scepter" in hand:
            return 95
        if name == "flash" and player.library.find_by_name("Protean Hulk"):
            return 90

        return base


class TivitAI(BaseAI):
    """
    Tivit, Seller of Secrets (UW Artifacts).
    Win line: Iso+Rev with artifact mana rocks for infinite mana, then Tivit draw.
    Secondary: Oracle+Consult.
    """

    def __init__(self, player_id: str):
        super().__init__(player_id, "tivit")

    def choose_tutor_target(self, player, game) -> str:
        hand = {c.name.lower() for c in player.hand.cards()}
        lib_has = lambda n: player.library.find_by_name(n) is not None

        # Iso+Rev
        if "isochron scepter" in hand and lib_has("Dramatic Reversal"):
            return "Dramatic Reversal"
        if "dramatic reversal" in hand and lib_has("Isochron Scepter"):
            return "Isochron Scepter"

        # Oracle+Consult
        if "thassa's oracle" in hand and lib_has("Demonic Consultation"):
            return "Demonic Consultation"
        if lib_has("Thassa's Oracle"):
            return "Thassa's Oracle"

        # Get artifact mana rocks
        if game.turn_number <= 2:
            for name in ["Mana Vault", "Grim Monolith", "Basalt Monolith",
                         "Mana Crypt", "Sol Ring"]:
                if lib_has(name) and name.lower() not in hand:
                    return name

        return super().choose_tutor_target(player, game)

    def _score_spell(self, card, player, game) -> int:
        base = super()._score_spell(card, player, game)
        from ..engine.card import CardType
        # Tivit values artifacts highly
        if CardType.ARTIFACT in card.data.card_types:
            return base + 10
        return base


def make_ai(player_id: str, deck_id: str) -> BaseAI:
    """Factory: create the right AI for a given deck."""
    mapping = {
        "thrasios_tymna": ConsultationAI,
        "najeela":        NajeelaAI,
        "kenrith":        KenrithAI,
        "tivit":          TivitAI,
    }
    cls = mapping.get(deck_id, BaseAI)
    return cls(player_id)
