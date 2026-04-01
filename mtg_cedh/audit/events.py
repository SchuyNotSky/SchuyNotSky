"""
Audit event types. Every meaningful game action produces one of these.
Each event is a plain dict for easy JSON serialization.

Event categories:
  GAME_*     — game lifecycle (start, end, setup)
  TURN_*     — turn/phase transitions
  CAST_*     — spells cast, countered, resolved
  STACK_*    — stack management
  LAND_*     — land plays
  MANA_*     — mana production
  DRAW_*     — card draws and discards
  COMBAT_*   — combat actions
  DAMAGE_*   — damage and life changes
  TUTOR_*    — tutor decisions (with AI reasoning)
  ABILITY_*  — activated/triggered abilities
  MOVE_*     — zone changes
  AI_*       — AI decision reasoning
  WIN_*      — win/loss conditions
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    # Game lifecycle
    GAME_START       = "GAME_START"
    GAME_END         = "GAME_END"
    PLAYER_SETUP     = "PLAYER_SETUP"
    OPENING_HAND     = "OPENING_HAND"

    # Turn / phase
    TURN_START       = "TURN_START"
    PHASE_START      = "PHASE_START"
    PRIORITY_PASS    = "PRIORITY_PASS"

    # Spells
    SPELL_CAST       = "SPELL_CAST"
    SPELL_RESOLVE    = "SPELL_RESOLVE"
    SPELL_COUNTERED  = "SPELL_COUNTERED"

    # Stack
    STACK_PUSH       = "STACK_PUSH"
    STACK_RESOLVE    = "STACK_RESOLVE"
    STACK_EMPTY      = "STACK_EMPTY"

    # Lands
    LAND_PLAYED      = "LAND_PLAYED"

    # Mana
    MANA_PRODUCED    = "MANA_PRODUCED"
    MANA_SPENT       = "MANA_SPENT"

    # Draw / discard
    CARD_DRAWN       = "CARD_DRAWN"
    CARD_DISCARDED   = "CARD_DISCARDED"
    HAND_WHEELED     = "HAND_WHEELED"
    LIBRARY_MILLED   = "LIBRARY_MILLED"
    LIBRARY_EXILED   = "LIBRARY_EXILED"

    # Combat
    ATTACKERS_DECLARED  = "ATTACKERS_DECLARED"
    BLOCKERS_DECLARED   = "BLOCKERS_DECLARED"
    COMBAT_DAMAGE       = "COMBAT_DAMAGE"

    # Damage / life
    DAMAGE_DEALT     = "DAMAGE_DEALT"
    LIFE_GAINED      = "LIFE_GAINED"
    LIFE_LOST        = "LIFE_LOST"

    # Tutors
    TUTOR_SEARCH     = "TUTOR_SEARCH"
    TUTOR_RESULT     = "TUTOR_RESULT"

    # Abilities
    ABILITY_ACTIVATED  = "ABILITY_ACTIVATED"
    ABILITY_TRIGGERED  = "ABILITY_TRIGGERED"

    # Zone moves
    PERMANENT_ETB    = "PERMANENT_ETB"
    PERMANENT_DIES   = "PERMANENT_DIES"
    CARD_EXILED      = "CARD_EXILED"
    CARD_BOUNCED     = "CARD_BOUNCED"
    COMMANDER_ZONE   = "COMMANDER_ZONE"

    # AI reasoning
    AI_DECISION      = "AI_DECISION"
    AI_TUTOR_CHOICE  = "AI_TUTOR_CHOICE"
    AI_COUNTER_EVAL  = "AI_COUNTER_EVAL"
    AI_PASS_PRIORITY = "AI_PASS_PRIORITY"

    # Win / loss
    WIN_CONDITION    = "WIN_CONDITION"
    PLAYER_LOST      = "PLAYER_LOST"
    GAME_DRAWN       = "GAME_DRAWN"
    STATE_BASED      = "STATE_BASED"


def make_event(
    event_type: EventType,
    turn: int,
    phase: str,
    player_id: Optional[str] = None,
    player_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict:
    """Create an audit event dict."""
    return {
        "type": event_type.value,
        "turn": turn,
        "phase": phase,
        "player_id": player_id,
        "player_name": player_name,
        "timestamp_ms": int(datetime.now().timestamp() * 1000),
        **kwargs,
    }
