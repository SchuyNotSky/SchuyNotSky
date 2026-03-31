"""
Deck loader: parse text deck lists, fetch card data from Scryfall,
apply the effects registry, and return Card instances ready for a game.

Supported deck list formats:
  - MTGO / plain:     "1 Sol Ring"
  - Moxfield/EDHREC:  "1x Sol Ring"
  - With sections:    "Commander (1)\n1 Thrasios, Triton Hero\n\nDeck (99)\n..."
  - Comments:         lines starting with '#' or '//' are ignored
  - Sideboard:        lines after 'Sideboard' are ignored
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..engine.card import Card, CardData
from ..cards.scryfall import get_card, bulk_fetch
from ..cards.converter import scryfall_to_card_data
from ..cards.database import patch_card_data

# Cache of CardData objects so each unique card is only built once per session
_card_data_cache: Dict[str, CardData] = {}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_deck_file(path: str | Path) -> Tuple[List[CardData], List[CardData]]:
    """
    Parse a deck list file.
    Returns (commanders, deck_cards) — lists of CardData.
    Fetches any missing cards from Scryfall and patches effects.
    """
    text = Path(path).read_text(encoding="utf-8")
    return parse_deck_text(text)


def parse_deck_text(text: str) -> Tuple[List[CardData], List[CardData]]:
    """
    Parse deck list text. Returns (commanders, deck_cards).
    """
    commanders: List[CardData] = []
    deck_cards: List[CardData] = []

    in_sideboard = False
    current_section = "deck"  # default section

    for raw_line in text.splitlines():
        line = raw_line.strip()

        # Skip blank lines and comments
        if not line or line.startswith("#") or line.startswith("//"):
            continue

        # Section headers
        lower = line.lower()
        if lower.startswith("sideboard"):
            in_sideboard = True
            continue
        if in_sideboard:
            continue

        if re.match(r"^commander\s*(\(\d+\))?$", lower):
            current_section = "commander"
            continue
        if re.match(r"^(deck|main(deck|board)?|library)\s*(\(\d+\))?$", lower):
            current_section = "deck"
            continue

        # Parse "N Card Name" or "Nx Card Name"
        m = re.match(r"^(\d+)x?\s+(.+)$", line)
        if not m:
            # Could be just a card name with no count
            m2 = re.match(r"^(.+)$", line)
            if m2:
                name = m2.group(1).strip()
                count = 1
            else:
                continue
        else:
            count = int(m.group(1))
            name = m.group(2).strip()

        # Strip set codes like "(ELD) 123" at end
        name = re.sub(r"\s*\([A-Z0-9]+\)\s*\d*$", "", name).strip()
        # Strip trailing asterisks (foil markers)
        name = name.rstrip("*").strip()

        if not name:
            continue

        card_data = get_card_data(name)
        if card_data is None:
            print(f"[Loader] Warning: could not load card '{name}', skipping.")
            continue

        if current_section == "commander" or count == 1 and card_data.is_commander_eligible:
            # Ambiguous: let section header decide; otherwise trust explicit 'commander' section
            if current_section == "commander":
                commanders.append(card_data)
                continue

        for _ in range(count):
            deck_cards.append(card_data)

    return commanders, deck_cards


def get_card_data(name: str) -> Optional[CardData]:
    """
    Get a CardData for a named card.
    1. Check session cache
    2. Fetch from Scryfall (uses disk cache)
    3. Convert Scryfall JSON -> CardData
    4. Patch with effects registry
    """
    key = name.lower().strip()
    if key in _card_data_cache:
        return _card_data_cache[key]

    sf_data = get_card(name)
    if sf_data is None:
        return None

    # Handle double-faced cards — use front face
    if sf_data.get("layout") in ("transform", "modal_dfc", "adventure") and "card_faces" in sf_data:
        face = sf_data["card_faces"][0]
        # Merge top-level fields with front face
        merged = dict(sf_data)
        merged.update({k: v for k, v in face.items() if k not in ("object",)})
        sf_data = merged

    card_data = scryfall_to_card_data(sf_data)
    patch_card_data(card_data)

    _card_data_cache[key] = card_data
    return card_data


def make_card_instances(
    card_data_list: List[CardData],
    owner_id: str
) -> List[Card]:
    """Turn CardData objects into Card instances for a specific player."""
    return [Card(cd, owner_id) for cd in card_data_list]


def prefetch_deck(path: str | Path):
    """
    Pre-fetch all cards in a deck file to populate the Scryfall disk cache.
    Call this once per deck list to avoid per-card network delays during play.
    """
    text = Path(path).read_text(encoding="utf-8")
    names = _extract_names(text)
    print(f"[Loader] Pre-fetching {len(names)} cards for {Path(path).name} …")
    bulk_fetch(names)
    print(f"[Loader] Done.")


def _extract_names(text: str) -> List[str]:
    """Extract all card names from a deck list text."""
    names = []
    in_sb = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("//"):
            continue
        if line.lower().startswith("sideboard"):
            in_sb = True
            continue
        if in_sb:
            continue
        if re.match(r"^(commander|deck|main|library)\s*(\(\d+\))?$", line.lower()):
            continue
        m = re.match(r"^(\d+)x?\s+(.+)$", line)
        if m:
            name = re.sub(r"\s*\([A-Z0-9]+\)\s*\d*$", "", m.group(2)).strip().rstrip("*")
            if name:
                names.append(name)
    return names
