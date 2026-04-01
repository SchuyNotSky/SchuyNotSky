"""
Deck storage: save, load, and manage deck list files.

Decks are stored as plain .txt files in mtg_cedh/decks/lists/.
A manifest JSON tracks metadata (name, commander, path, last_modified).
"""
from __future__ import annotations

import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

LISTS_DIR = Path(__file__).parent / "lists"
MANIFEST_PATH = LISTS_DIR / "manifest.json"


def _ensure_dirs():
    LISTS_DIR.mkdir(parents=True, exist_ok=True)


def _load_manifest() -> Dict[str, dict]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_manifest(manifest: Dict[str, dict]):
    _ensure_dirs()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def list_decks() -> List[dict]:
    """Return all registered decks as a list of metadata dicts."""
    manifest = _load_manifest()
    return list(manifest.values())


def get_deck_path(deck_id: str) -> Optional[Path]:
    """Return the Path for a registered deck, or None."""
    manifest = _load_manifest()
    entry = manifest.get(deck_id)
    if entry:
        p = Path(entry["path"])
        return p if p.exists() else None
    return None


def save_deck(
    deck_text: str,
    deck_id: str,
    name: Optional[str] = None,
    commander: Optional[str] = None,
    description: Optional[str] = None,
) -> Path:
    """
    Save a deck list string to disk and register it in the manifest.
    Returns the path where it was saved.

    deck_id: short identifier, e.g. 'thrasios_tymna'
    """
    _ensure_dirs()
    filename = f"{deck_id}.txt"
    path = LISTS_DIR / filename

    path.write_text(deck_text, encoding="utf-8")

    manifest = _load_manifest()
    manifest[deck_id] = {
        "id": deck_id,
        "name": name or deck_id,
        "commander": commander or "",
        "description": description or "",
        "path": str(path),
        "last_modified": datetime.now().isoformat(),
    }
    _save_manifest(manifest)
    print(f"[Storage] Saved deck '{deck_id}' to {path}")
    return path


def save_deck_file(
    source_path: str | Path,
    deck_id: str,
    name: Optional[str] = None,
    commander: Optional[str] = None,
    description: Optional[str] = None,
) -> Path:
    """
    Copy an existing deck list file into the decks/lists/ directory and register it.
    """
    _ensure_dirs()
    source = Path(source_path)
    dest = LISTS_DIR / f"{deck_id}.txt"
    shutil.copy2(source, dest)

    manifest = _load_manifest()
    manifest[deck_id] = {
        "id": deck_id,
        "name": name or source.stem,
        "commander": commander or "",
        "description": description or "",
        "path": str(dest),
        "last_modified": datetime.now().isoformat(),
    }
    _save_manifest(manifest)
    print(f"[Storage] Registered deck '{deck_id}' from {source}")
    return dest


def delete_deck(deck_id: str) -> bool:
    """Remove a deck from disk and manifest. Returns True if found."""
    manifest = _load_manifest()
    if deck_id not in manifest:
        return False
    path = Path(manifest[deck_id]["path"])
    if path.exists():
        path.unlink()
    del manifest[deck_id]
    _save_manifest(manifest)
    print(f"[Storage] Deleted deck '{deck_id}'.")
    return True


def get_deck_text(deck_id: str) -> Optional[str]:
    """Return raw deck list text for a registered deck."""
    path = get_deck_path(deck_id)
    if path:
        return path.read_text(encoding="utf-8")
    return None


def print_deck_list(deck_id: str):
    """Pretty-print a stored deck list."""
    meta = _load_manifest().get(deck_id)
    if not meta:
        print(f"Deck '{deck_id}' not found.")
        return
    print(f"\n{'='*50}")
    print(f"  {meta['name']}")
    if meta.get('commander'):
        print(f"  Commander: {meta['commander']}")
    if meta.get('description'):
        print(f"  {meta['description']}")
    print(f"{'='*50}")
    text = get_deck_text(deck_id)
    if text:
        print(text)
    print(f"{'='*50}\n")


def create_placeholder_decks():
    """
    Create empty placeholder deck list files for the 4 cEDH decks.
    The user fills these in with their actual lists.
    """
    _ensure_dirs()
    placeholders = [
        {
            "id": "thrasios_tymna",
            "name": "Thrasios + Tymna (4c Consultation)",
            "commander": "Thrasios, Triton Hero / Tymna the Weaver",
            "description": "4-color Oracle+Consultation / Tainted Pact combo",
            "template": _THRASIOS_TEMPLATE,
        },
        {
            "id": "najeela",
            "name": "Najeela, the Blade-Blossom (5c Warriors)",
            "commander": "Najeela, the Blade-Blossom",
            "description": "5-color Warrior tribal with infinite combat win",
            "template": _NAJEELA_TEMPLATE,
        },
        {
            "id": "kenrith",
            "name": "Kenrith, the Returned King (5c Goodstuff)",
            "commander": "Kenrith, the Returned King",
            "description": "5-color Iso+Rev / Doomsday / Flash+Hulk",
            "template": _KENRITH_TEMPLATE,
        },
        {
            "id": "tivit",
            "name": "Tivit, Seller of Secrets (UW Artifacts)",
            "commander": "Tivit, Seller of Secrets",
            "description": "UW Artifact combo with Ballot Broker / Clue tokens",
            "template": _TIVIT_TEMPLATE,
        },
    ]

    for p in placeholders:
        path = LISTS_DIR / f"{p['id']}.txt"
        if not path.exists():
            path.write_text(p["template"], encoding="utf-8")
            manifest = _load_manifest()
            manifest[p["id"]] = {
                "id": p["id"],
                "name": p["name"],
                "commander": p["commander"],
                "description": p["description"],
                "path": str(path),
                "last_modified": datetime.now().isoformat(),
            }
            _save_manifest(manifest)
            print(f"[Storage] Created placeholder: {path.name}")
        else:
            print(f"[Storage] Already exists: {path.name}")


# ---------------------------------------------------------------------------
# Deck list templates (paste your actual list between the dashes)
# ---------------------------------------------------------------------------

_THRASIOS_TEMPLATE = """\
// Thrasios, Triton Hero + Tymna the Weaver
// 4-color (WUBG) Oracle+Consultation
// Paste your full 99-card list below. One card per line: "1 Card Name"
// Commander section is auto-detected or use the header below.

Commander (2)
1 Thrasios, Triton Hero
1 Tymna the Weaver

Deck (99)
// --- Fast Mana ---
1 Sol Ring
1 Mana Crypt
1 Mana Vault
1 Chrome Mox
1 Mox Diamond
1 Lotus Petal
1 Jeweled Lotus
1 Dark Ritual
1 Cabal Ritual
// --- Win Conditions ---
1 Thassa's Oracle
1 Demonic Consultation
1 Tainted Pact
// --- Tutors ---
1 Demonic Tutor
1 Vampiric Tutor
1 Imperial Seal
1 Mystical Tutor
1 Enlightened Tutor
1 Lim-Dul's Vault
// --- Counterspells ---
1 Force of Will
1 Force of Negation
1 Counterspell
1 Fierce Guardianship
1 Pact of Negation
1 Mental Misstep
1 Flusterstorm
1 Swan Song
1 Dovin's Veto
// --- Card Draw ---
1 Rhystic Study
1 Mystic Remora
1 Ad Nauseam
1 Necropotence
1 Brainstorm
1 Ponder
1 Preordain
1 Gitaxian Probe
1 Night's Whisper
// --- Removal ---
1 Swords to Plowshares
1 Path to Exile
1 Chain of Vapor
1 Cyclonic Rift
1 Abrupt Decay
1 Assassin's Trophy
1 Nature's Claim
// --- Protection ---
1 Veil of Summer
1 Silence
1 Orim's Chant
// --- Lands ---
1 Command Tower
1 Ancient Tomb
1 Exotic Orchard
1 Gemstone Caverns
1 Polluted Delta
1 Flooded Strand
1 Bloodstained Mire
1 Windswept Heath
1 Misty Rainforest
1 Verdant Catacombs
1 Underground Sea
1 Tundra
1 Bayou
1 Savannah
1 Tropical Island
1 Scrubland
1 Watery Grave
1 Hallowed Fountain
1 Breeding Pool
1 Temple Garden
1 Godless Shrine
1 Overgrown Tomb
// Add remaining 27+ cards here
"""

_NAJEELA_TEMPLATE = """\
// Najeela, the Blade-Blossom
// 5-color Warriors — Infinite Combat Win
// Paste your full list below.

Commander (1)
1 Najeela, the Blade-Blossom

Deck (99)
// --- Fast Mana ---
1 Sol Ring
1 Mana Crypt
1 Chrome Mox
1 Mox Diamond
1 Lotus Petal
1 Jeweled Lotus
1 Dark Ritual
1 Cabal Ritual
1 Elvish Spirit Guide
1 Simian Spirit Guide
// --- Warriors ---
// Add your warrior package here
// --- Counterspells ---
1 Force of Will
1 Force of Negation
1 Fierce Guardianship
1 Deflecting Swat
1 Counterspell
1 Mental Misstep
1 Swan Song
// --- Card Draw ---
1 Rhystic Study
1 Mystic Remora
1 Brainstorm
1 Ponder
// --- Removal ---
1 Swords to Plowshares
1 Path to Exile
1 Cyclonic Rift
1 Nature's Claim
// --- Lands ---
1 Command Tower
1 Ancient Tomb
1 Exotic Orchard
1 Polluted Delta
1 Flooded Strand
1 Bloodstained Mire
1 Windswept Heath
1 Misty Rainforest
1 Wooded Foothills
1 Scalding Tarn
1 Arid Mesa
1 Verdant Catacombs
1 Underground Sea
1 Volcanic Island
1 Tundra
1 Bayou
1 Savannah
1 Taiga
1 Scrubland
1 Tropical Island
1 Badlands
1 Plateau
// Add remaining cards here
"""

_KENRITH_TEMPLATE = """\
// Kenrith, the Returned King
// 5-color Iso+Rev / Flash+Hulk / Doomsday
// Paste your full list below.

Commander (1)
1 Kenrith, the Returned King

Deck (99)
// --- Fast Mana ---
1 Sol Ring
1 Mana Crypt
1 Mana Vault
1 Grim Monolith
1 Basalt Monolith
1 Chrome Mox
1 Mox Diamond
1 Lotus Petal
1 Jeweled Lotus
// --- Win Conditions ---
1 Isochron Scepter
1 Dramatic Reversal
1 Thassa's Oracle
1 Demonic Consultation
1 Flash
1 Protean Hulk
// --- Tutors ---
1 Demonic Tutor
1 Vampiric Tutor
1 Imperial Seal
1 Mystical Tutor
1 Enlightened Tutor
1 Merchant Scroll
1 Intuition
// --- Counterspells ---
1 Force of Will
1 Force of Negation
1 Counterspell
1 Fierce Guardianship
1 Pact of Negation
1 Mana Drain
1 Mental Misstep
1 Flusterstorm
1 Swan Song
// --- Card Draw ---
1 Rhystic Study
1 Mystic Remora
1 Sylvan Library
1 Ad Nauseam
1 Windfall
1 Timetwister
1 Brainstorm
1 Ponder
1 Preordain
// --- Removal ---
1 Swords to Plowshares
1 Cyclonic Rift
1 Toxic Deluge
1 Force of Vigor
// --- Lands ---
1 Command Tower
1 Ancient Tomb
1 Exotic Orchard
1 Polluted Delta
1 Flooded Strand
1 Bloodstained Mire
1 Windswept Heath
1 Misty Rainforest
1 Wooded Foothills
1 Scalding Tarn
1 Underground Sea
1 Volcanic Island
1 Tundra
1 Bayou
1 Savannah
1 Taiga
1 Tropical Island
// Add remaining cards here
"""

_TIVIT_TEMPLATE = """\
// Tivit, Seller of Secrets
// UW Artifacts — Council's Dilemma / Clue / Treasure combo
// Paste your full list below.

Commander (1)
1 Tivit, Seller of Secrets

Deck (99)
// --- Fast Mana ---
1 Sol Ring
1 Mana Crypt
1 Mana Vault
1 Grim Monolith
1 Basalt Monolith
1 Chrome Mox
1 Lotus Petal
1 Jeweled Lotus
// --- Win Conditions ---
1 Isochron Scepter
1 Dramatic Reversal
1 Thassa's Oracle
1 Demonic Consultation
// --- Tutors ---
1 Mystical Tutor
1 Enlightened Tutor
1 Merchant Scroll
1 Fabricate
// --- Counterspells ---
1 Force of Will
1 Force of Negation
1 Counterspell
1 Fierce Guardianship
1 Pact of Negation
1 Mana Drain
1 Mental Misstep
1 Flusterstorm
1 Swan Song
// --- Card Draw ---
1 Rhystic Study
1 Mystic Remora
1 Brainstorm
1 Ponder
1 Preordain
1 Gitaxian Probe
1 Windfall
// --- Removal ---
1 Swords to Plowshares
1 Path to Exile
1 Chain of Vapor
1 Cyclonic Rift
// --- Stax/Hate ---
1 Collector Ouphe
1 Null Rod
1 Cursed Totem
// --- Lands ---
1 Command Tower
1 Ancient Tomb
1 Exotic Orchard
1 Polluted Delta
1 Flooded Strand
1 Misty Rainforest
1 Scalding Tarn
1 Underground Sea
1 Volcanic Island
1 Tundra
1 Watery Grave
1 Steam Vents
1 Hallowed Fountain
1 Breeding Pool
// Add remaining cards here
"""
