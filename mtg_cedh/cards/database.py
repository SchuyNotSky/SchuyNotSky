"""
cEDH Effects Registry.
Maps card names to their effect callbacks, tap-mana data, and activated/triggered abilities.
Imported by the deck loader to patch CardData objects after Scryfall fetch.
"""
from __future__ import annotations
from typing import TYPE_CHECKING
from ..engine.mana import Color, ManaCost
from ..engine.card import CardType, Keyword

if TYPE_CHECKING:
    from ..engine.card import Card
    from ..engine.game import GameState
    from ..engine.player import Player

from ._effects_mana import register_mana_effects
from ._effects_tutors import register_tutor_effects
from ._effects_counterspells import register_counterspell_effects
from ._effects_draw import register_draw_effects
from ._effects_wincons import register_wincon_effects
from ._effects_removal import register_removal_effects
from ._effects_lands import register_land_effects
from ._effects_protection import register_protection_effects


def build_registry() -> dict:
    """Return the full effects registry: {card_name_lower: patch_dict}."""
    registry = {}
    register_mana_effects(registry)
    register_tutor_effects(registry)
    register_counterspell_effects(registry)
    register_draw_effects(registry)
    register_wincon_effects(registry)
    register_removal_effects(registry)
    register_land_effects(registry)
    register_protection_effects(registry)
    return registry


REGISTRY = build_registry()


def patch_card_data(card_data) -> None:
    """Apply effect callbacks from registry onto a CardData object in-place."""
    patch = REGISTRY.get(card_data.name.lower())
    if not patch:
        return
    for key, val in patch.items():
        setattr(card_data, key, val)


CEDH_STAPLE_NAMES = [
    # Fast mana
    "Sol Ring", "Mana Crypt", "Mana Vault", "Chrome Mox", "Mox Diamond",
    "Lotus Petal", "Dark Ritual", "Cabal Ritual", "Ancient Tomb",
    "Grim Monolith", "Basalt Monolith", "Jeweled Lotus",
    "Elvish Spirit Guide", "Simian Spirit Guide",
    # Win conditions
    "Thassa's Oracle", "Demonic Consultation", "Tainted Pact",
    "Isochron Scepter", "Dramatic Reversal",
    "Underworld Breach", "Brain Freeze", "Lion's Eye Diamond",
    "Thassa's Oracle", "Flash", "Protean Hulk",
    # Tutors
    "Demonic Tutor", "Vampiric Tutor", "Imperial Seal",
    "Mystical Tutor", "Worldly Tutor", "Enlightened Tutor",
    "Merchant Scroll", "Lim-Dul's Vault", "Intuition", "Gamble",
    "Fabricate", "Transmute Artifact", "Whir of Invention",
    # Counterspells
    "Force of Will", "Force of Negation", "Counterspell",
    "Fierce Guardianship", "Deflecting Swat", "Pact of Negation",
    "Mental Misstep", "Flusterstorm", "Swan Song", "Dovin's Veto",
    "Mana Drain", "Spell Pierce", "Arcane Denial",
    # Card draw
    "Rhystic Study", "Mystic Remora", "Sylvan Library",
    "Ad Nauseam", "Necropotence", "Windfall", "Timetwister",
    "Wheel of Fortune", "Night's Whisper", "Brainstorm",
    "Ponder", "Preordain", "Gitaxian Probe",
    # Removal
    "Swords to Plowshares", "Path to Exile", "Chain of Vapor",
    "Cyclonic Rift", "Toxic Deluge", "Abrupt Decay",
    "Assassin's Trophy", "Nature's Claim", "Force of Vigor",
    "Wear // Tear", "Winds of Abandon",
    # Lands
    "Command Tower", "Ancient Tomb", "Exotic Orchard",
    "Gemstone Caverns", "Cavern of Souls",
    "Polluted Delta", "Flooded Strand", "Bloodstained Mire",
    "Windswept Heath", "Wooded Foothills", "Misty Rainforest",
    "Scalding Tarn", "Marsh Flats", "Arid Mesa", "Verdant Catacombs",
    "Underground Sea", "Volcanic Island", "Tundra", "Bayou",
    "Savannah", "Taiga", "Scrubland", "Plateau", "Tropical Island",
    "Badlands",
    "Watery Grave", "Steam Vents", "Hallowed Fountain",
    "Overgrown Tomb", "Stomping Ground", "Sacred Foundry",
    "Godless Shrine", "Temple Garden", "Breeding Pool", "Blood Crypt",
    # Protection
    "Silence", "Veil of Summer", "Grand Abolisher",
    "Autumn's Veil", "Orim's Chant", "Drannith Magistrate",
    "Collector Ouphe", "Null Rod", "Cursed Totem",
    "Thalia, Guardian of Thraben",
    # Commanders
    "Thrasios, Triton Hero", "Tymna the Weaver",
    "Najeela, the Blade-Blossom", "Kenrith, the Returned King",
    "Tivit, Seller of Secrets", "Kraum, Ludevic's Opus",
]
