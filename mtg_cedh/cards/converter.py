"""
Convert raw Scryfall JSON into our engine's CardData objects.

Scryfall gives us free: name, mana_cost, cmc, type_line, oracle_text,
power, toughness, loyalty, keywords, colors.

We layer on top: mana-tap data, effect callbacks, activated/triggered abilities.
These are registered separately in database.py for the cards that need them.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Set

from ..engine.card import CardData, CardType, Supertype, Keyword
from ..engine.mana import ManaCost, Color


# ---------------------------------------------------------------------------
# Type-line parsing
# ---------------------------------------------------------------------------

_CARD_TYPE_MAP: Dict[str, CardType] = {
    "land":          CardType.LAND,
    "creature":      CardType.CREATURE,
    "artifact":      CardType.ARTIFACT,
    "enchantment":   CardType.ENCHANTMENT,
    "instant":       CardType.INSTANT,
    "sorcery":       CardType.SORCERY,
    "planeswalker":  CardType.PLANESWALKER,
    "tribal":        CardType.TRIBAL,
    "battle":        CardType.BATTLE,
}

_SUPERTYPE_MAP: Dict[str, Supertype] = {
    "legendary": Supertype.LEGENDARY,
    "basic":     Supertype.BASIC,
    "snow":      Supertype.SNOW,
    "world":     Supertype.WORLD,
}

_KEYWORD_MAP: Dict[str, Keyword] = {
    "flying":         Keyword.FLYING,
    "first strike":   Keyword.FIRST_STRIKE,
    "double strike":  Keyword.DOUBLE_STRIKE,
    "deathtouch":     Keyword.DEATHTOUCH,
    "lifelink":       Keyword.LIFELINK,
    "trample":        Keyword.TRAMPLE,
    "haste":          Keyword.HASTE,
    "vigilance":      Keyword.VIGILANCE,
    "reach":          Keyword.REACH,
    "menace":         Keyword.MENACE,
    "hexproof":       Keyword.HEXPROOF,
    "indestructible": Keyword.INDESTRUCTIBLE,
    "shroud":         Keyword.SHROUD,
    "flash":          Keyword.FLASH,
    "protection":     Keyword.PROTECTION,
    "storm":          Keyword.STORM,
    "cascade":        Keyword.CASCADE,
    "annihilator":    Keyword.ANNIHILATOR,
    "infect":         Keyword.INFECT,
    "wither":         Keyword.WITHER,
    "persist":        Keyword.PERSIST,
    "undying":        Keyword.UNDYING,
    "partner":        Keyword.PARTNER,
    "ward":           Keyword.WARD,
}


def parse_type_line(type_line: str):
    """
    Parse a Scryfall type_line like 'Legendary Creature — Elf Wizard'
    into (supertypes, card_types, subtypes).
    """
    # Split on em dash (—) or hyphen ( - )
    parts = re.split(r"\s*[—\-]\s*", type_line, maxsplit=1)
    left = parts[0].lower().split()
    subtypes = parts[1].split() if len(parts) > 1 else []

    supertypes: List[Supertype] = []
    card_types: List[CardType] = []

    for word in left:
        if word in _SUPERTYPE_MAP:
            supertypes.append(_SUPERTYPE_MAP[word])
        elif word in _CARD_TYPE_MAP:
            card_types.append(_CARD_TYPE_MAP[word])

    return supertypes, card_types, subtypes


def parse_keywords(scryfall_keywords: List[str]) -> Set[Keyword]:
    """Convert Scryfall keywords list to our Keyword enum set."""
    result: Set[Keyword] = set()
    for kw in scryfall_keywords:
        mapped = _KEYWORD_MAP.get(kw.lower())
        if mapped:
            result.add(mapped)
    return result


def _infer_tap_mana(oracle_text: str, card_types: List[CardType],
                    subtypes: List[str]) -> Optional[Dict[Color, int]]:
    """
    Try to infer basic tap-for-mana behavior from oracle text.
    Handles the most common land/mana-rock patterns.
    """
    if not oracle_text:
        return None

    text = oracle_text.lower()

    # Basic lands
    if CardType.LAND in card_types:
        subtype_lower = [s.lower() for s in subtypes]
        if "plains" in subtype_lower:
            return {Color.WHITE: 1}
        if "island" in subtype_lower:
            return {Color.BLUE: 1}
        if "swamp" in subtype_lower:
            return {Color.BLACK: 1}
        if "mountain" in subtype_lower:
            return {Color.RED: 1}
        if "forest" in subtype_lower:
            return {Color.GREEN: 1}

    return None  # complex tap abilities handled by effect registry


def _infer_tap_mana_choice(oracle_text: str, card_types: List[CardType]) -> bool:
    """
    Returns True if the card has '{T}: Add one mana of any color' style ability.
    """
    if not oracle_text:
        return False
    text = oracle_text.lower()
    patterns = [
        r"\{t\}.*add one mana of any color",
        r"\{t\}.*add.*mana of any",
        r"add one mana of any color",
    ]
    return any(re.search(p, text) for p in patterns)


# ---------------------------------------------------------------------------
# Main converter
# ---------------------------------------------------------------------------

def scryfall_to_card_data(sf: dict) -> CardData:
    """
    Convert a Scryfall card JSON dict into a CardData object.
    Effect callbacks start as None; they are patched in by database.py.
    """
    name = sf.get("name", "Unknown")

    # Mana cost — double-faced cards may have no mana_cost on back face
    raw_cost = sf.get("mana_cost") or ""
    mana_cost = ManaCost.parse(raw_cost) if raw_cost else ManaCost.free()

    # Type line
    type_line = sf.get("type_line", "")
    supertypes, card_types, subtypes = parse_type_line(type_line)

    # Keywords
    keywords = parse_keywords(sf.get("keywords", []))

    # Oracle text
    oracle_text = sf.get("oracle_text", "")

    # Power / toughness (stored as strings in Scryfall, e.g. "*", "1+*")
    def _parse_pt(val) -> Optional[int]:
        if val is None:
            return None
        try:
            return int(val)
        except (ValueError, TypeError):
            return 0  # '*' etc. default to 0 base

    power = _parse_pt(sf.get("power"))
    toughness = _parse_pt(sf.get("toughness"))
    loyalty = _parse_pt(sf.get("loyalty"))

    # Tap-mana inference
    tap_mana = _infer_tap_mana(oracle_text, card_types, subtypes)
    tap_mana_choice = _infer_tap_mana_choice(oracle_text, card_types)

    return CardData(
        name=name,
        mana_cost=mana_cost,
        card_types=card_types,
        supertypes=supertypes,
        subtypes=subtypes,
        keywords=keywords,
        oracle_text=oracle_text,
        power=power,
        toughness=toughness,
        loyalty=loyalty,
        tap_mana=tap_mana,
        tap_mana_choice=tap_mana_choice,
    )
