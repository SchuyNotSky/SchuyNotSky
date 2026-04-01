"""
AI Profile loader.

Profiles live in ai/profiles/<deck_id>.json.
Any deck can have a profile — if none exists the BaseAI defaults apply.

Profile schema:
  deck_id          str   — matches the deck storage ID
  display_name     str   — human-readable name
  strategy         str   — "combo" | "aggro_combo" | "stax" | "midrange"
  aggression       float — 0.0 (never attack) to 1.0 (always attack)

  win_lines        list  — ordered list of win conditions to pursue
    name           str
    pieces         list[str]  — card names needed
    mana_required  list[str]  — optional WUBRG mana symbols needed
    description    str

  tutor_priority   list  — rules for what to tutor, checked top-to-bottom
    condition      str   — "have_piece" | "commander_on_battlefield" |
                           "turn_lte" | "always"
    piece          str   — (have_piece) card we already have
    commander      str   — (commander_on_battlefield) commander name
    turn           int   — (turn_lte) max turn number
    fetch          list[str]  — cards to look for, in priority order

  card_score_overrides  dict[str, int]  — override default AI card scoring
  always_counter        list[str]       — spell names to always counter
  protection_spells     list[str]       — spells to cast before going off
  attack_strategy       dict            — attack behavior flags
  life_thresholds       dict[str, int]  — life levels for various decisions
  artifact_priority     bool            — score artifacts higher (Tivit)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional

PROFILES_DIR = Path(__file__).parent / "profiles"

_profile_cache: Dict[str, dict] = {}


def load_profile(deck_id: str) -> Optional[dict]:
    """Load the JSON profile for a deck. Returns None if no profile exists."""
    if deck_id in _profile_cache:
        return _profile_cache[deck_id]

    path = PROFILES_DIR / f"{deck_id}.json"
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        # Strip comment keys
        data = {k: v for k, v in data.items() if not k.startswith("_")}
        _profile_cache[deck_id] = data
        return data
    except (json.JSONDecodeError, OSError) as e:
        print(f"[Profile] Warning: could not load profile for '{deck_id}': {e}")
        return None


def save_profile(deck_id: str, profile: dict):
    """Save or overwrite a profile JSON file."""
    PROFILES_DIR.mkdir(parents=True, exist_ok=True)
    path = PROFILES_DIR / f"{deck_id}.json"
    path.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    _profile_cache[deck_id] = profile
    print(f"[Profile] Saved profile for '{deck_id}' → {path}")


def list_profiles() -> list:
    """Return metadata for all available profiles."""
    profiles = []
    for path in sorted(PROFILES_DIR.glob("*.json")):
        if path.name == "__init__.py":
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profiles.append({
                "deck_id": data.get("deck_id", path.stem),
                "display_name": data.get("display_name", path.stem),
                "strategy": data.get("strategy", "unknown"),
            })
        except Exception:
            pass
    return profiles


def create_blank_profile(deck_id: str, display_name: str = "", strategy: str = "combo") -> dict:
    """
    Create a minimal blank profile template for a new deck.
    Saves it to disk and returns the dict.
    """
    profile = {
        "deck_id": deck_id,
        "display_name": display_name or deck_id,
        "strategy": strategy,
        "aggression": 0.1,
        "win_lines": [
            {
                "name": "My Win Line",
                "pieces": ["Card A", "Card B"],
                "description": "Describe the win line here."
            }
        ],
        "tutor_priority": [
            {
                "condition": "have_piece",
                "piece": "Card A",
                "fetch": ["Card B"]
            },
            {
                "condition": "always",
                "fetch": ["Card A", "Mana Crypt", "Sol Ring"]
            }
        ],
        "card_score_overrides": {
            "Card A": 95,
            "Card B": 90
        },
        "always_counter": [
            "Thassa's Oracle",
            "Flash",
            "Demonic Consultation"
        ],
        "life_thresholds": {
            "shock_land_pay": 4,
            "ad_nauseam_stop": 8,
            "necropotence_draw_to": 12
        }
    }
    save_profile(deck_id, profile)
    return profile
